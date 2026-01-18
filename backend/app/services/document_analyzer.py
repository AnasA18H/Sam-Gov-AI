"""
Document Analyzer Service
Extracts text and data from PDF, Word, and Excel documents using hybrid approach:
- Table parsing for structured forms (SF1449, SF30)
- LLM extraction for unstructured text (SOW, amendments)
"""
import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import dateutil.parser
from dateutil.parser import ParserError

# Document processing libraries
import pdfplumber
from docx import Document as DocxDocument
from openpyxl import load_workbook

# Table extraction (optional - for structured forms)
try:
    import camelot
    CAMELOT_AVAILABLE = True
except ImportError:
    CAMELOT_AVAILABLE = False
    logging.warning("camelot-py not available. Table extraction will use pdfplumber fallback.")

try:
    import tabula
    TABULA_AVAILABLE = True
except ImportError:
    TABULA_AVAILABLE = False
    logging.debug("tabula-py not available. Using camelot or pdfplumber for tables.")

# LLM extraction (optional - for unstructured text)
try:
    from langchain_groq import ChatGroq
    from langchain.chains import create_extraction_chain_pydantic
    from pydantic import BaseModel, Field
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    logging.warning("LangChain Groq not available. Using regex-based extraction only.")

# NLP (optional - spaCy for advanced classification)
try:
    import spacy
    SPACY_AVAILABLE = True
except ImportError:
    SPACY_AVAILABLE = False
    logging.warning("spaCy not available. Using keyword-based classification only.")

from ..core.config import settings
from ..models.opportunity import SolicitationType
from ..models.clin import CLIN
from ..models.deadline import Deadline

logger = logging.getLogger(__name__)


# Pydantic schema for LLM extraction
if LANGCHAIN_AVAILABLE:
    class CLINItem(BaseModel):
        """Pydantic schema for CLIN extraction using LLM"""
        item_number: str = Field(description="The CLIN or line item number, e.g., '0001', '0001AA', '2', '3'")
        description: str = Field(description="The description of the product or service")
        quantity: Optional[int] = Field(None, description="The quantity required")
        unit: Optional[str] = Field(None, description="The unit of measure, e.g., 'Each', 'Lot', 'Set'")
        part_number: Optional[str] = Field(None, description="Part number if applicable")
        model_number: Optional[str] = Field(None, description="Model number if applicable")
        manufacturer: Optional[str] = Field(None, description="Manufacturer name if applicable")
        product_name: Optional[str] = Field(None, description="Product name if applicable")


class DocumentAnalyzer:
    """Analyzer for extracting text and structured data from solicitation documents"""
    
    # Product-related keywords
    PRODUCT_KEYWORDS = [
        'product', 'item', 'manufacturer', 'part number', 'model number', 'catalog',
        'equipment', 'supply', 'material', 'component', 'hardware', 'device',
        'unit', 'piece', 'quantity', 'delivery', 'ship', 'furnish', 'provide'
    ]
    
    # Service-related keywords
    SERVICE_KEYWORDS = [
        'service', 'work', 'task', 'perform', 'maintain', 'repair', 'install',
        'support', 'consult', 'training', 'hours', 'labor', 'personnel',
        'contractor', 'vendor', 'timeline', 'schedule', 'duration', 'period'
    ]
    
    # Document type classification patterns
    DOCUMENT_TYPE_PATTERNS = {
        'sf1449': [r'SF\s*1449', r'Standard Form\s*1449', r'Form\s*1449'],
        'sf30': [r'SF\s*30', r'Standard Form\s*30', r'Amendment'],
        'sow': [r'Statement\s+of\s+Work', r'SOW', r'Scope\s+of\s+Work'],
        'amendment': [r'Amendment', r'Modification', r'Change\s+Order'],
    }
    
    # CLIN patterns (for regex fallback)
    CLIN_PATTERNS = [
        r'CLIN\s*(\d+[A-Z]*)',
        r'Contract\s+Line\s+Item\s+Number\s*(\d+[A-Z]*)',
        r'Line\s+Item\s+(\d+[A-Z]*)',
        r'Item\s+(\d+[A-Z]*)',
    ]
    
    # Deadline patterns
    DATE_PATTERNS = [
        r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
        r'(\d{4}[/-]\d{1,2}[/-]\d{1,2})',
        r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})',
        r'(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})',
    ]
    
    TIME_PATTERNS = [
        r'(\d{1,2}):(\d{2})\s*(AM|PM|am|pm)',
        r'(\d{1,2})\s*(AM|PM|am|pm)',
        r'(\d{4})\s*hours?',
    ]
    
    DEADLINE_KEYWORDS = [
        'due', 'deadline', 'submission', 'offer', 'proposal', 'response',
        'quote', 'bid', 'close', 'receipt', 'must be received'
    ]
    
    def __init__(self):
        """Initialize the document analyzer"""
        self.nlp = None
        self.llm = None
        
        # Initialize spaCy (optional)
        if SPACY_AVAILABLE:
            try:
                self.nlp = spacy.load("en_core_web_sm")
                logger.info("spaCy model loaded successfully")
            except OSError:
                logger.warning("spaCy model 'en_core_web_sm' not found. Using keyword-based classification only.")
        
        # Initialize LLM (optional - requires GROQ_API_KEY)
        if LANGCHAIN_AVAILABLE and settings.GROQ_API_KEY:
            try:
                self.llm = ChatGroq(
                    model=settings.GROQ_MODEL,
                    temperature=0,
                    groq_api_key=settings.GROQ_API_KEY
                )
                logger.info(f"Groq LLM initialized: {settings.GROQ_MODEL}")
            except Exception as e:
                logger.warning(f"Failed to initialize Groq LLM: {str(e)}. Using regex-based extraction only.")
                self.llm = None
        elif LANGCHAIN_AVAILABLE and not settings.GROQ_API_KEY:
            logger.warning("GROQ_API_KEY not set. LLM extraction disabled. Using regex-based extraction only.")
    
    def classify_document_type(self, file_path: Path, text: str) -> str:
        """
        Classify document type to route to correct extraction method
        
        Returns:
            Document type: 'sf1449', 'sf30', 'sow', 'amendment', or 'unknown'
        """
        # Check filename first
        filename_lower = file_path.name.lower()
        for doc_type, patterns in self.DOCUMENT_TYPE_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, filename_lower, re.IGNORECASE):
                    logger.info(f"Document classified as {doc_type} based on filename")
                    return doc_type
        
        # Check text content
        text_lower = text[:2000].lower()  # Check first 2000 chars
        for doc_type, patterns in self.DOCUMENT_TYPE_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text_lower, re.IGNORECASE):
                    logger.info(f"Document classified as {doc_type} based on content")
                    return doc_type
        
        return 'unknown'
    
    def extract_text(self, file_path: str) -> str:
        """
        Extract text from a document file
        
        Args:
            file_path: Path to the document file
            
        Returns:
            Extracted text content
        """
        file_path_obj = Path(file_path)
        
        # Handle relative paths (for Digital Ocean compatibility)
        if not file_path_obj.is_absolute():
            project_root = Path(settings.PROJECT_ROOT)
            abs_path = project_root / file_path
            if abs_path.exists():
                file_path_obj = abs_path
            elif hasattr(settings, 'STORAGE_BASE_PATH'):
                storage_base = Path(settings.STORAGE_BASE_PATH)
                abs_path = storage_base.parent / file_path if 'backend/data' in file_path else storage_base / file_path
                if abs_path.exists():
                    file_path_obj = abs_path
        
        if not file_path_obj.exists():
            raise FileNotFoundError(f"Document file not found: {file_path}")
        
        file_ext = file_path_obj.suffix.lower()
        
        try:
            if file_ext == '.pdf':
                return self._extract_from_pdf(file_path_obj)
            elif file_ext in ['.doc', '.docx']:
                return self._extract_from_word(file_path_obj)
            elif file_ext in ['.xls', '.xlsx']:
                return self._extract_from_excel(file_path_obj)
            else:
                logger.warning(f"Unsupported file type: {file_ext}")
                return ""
        except Exception as e:
            logger.error(f"Error extracting text from {file_path}: {str(e)}", exc_info=True)
            return ""
    
    def _extract_from_pdf(self, file_path: Path) -> str:
        """Extract text from PDF file"""
        text_parts = []
        try:
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
            return "\n\n".join(text_parts)
        except Exception as e:
            logger.error(f"Error extracting text from PDF {file_path}: {str(e)}")
            return ""
    
    def _extract_from_word(self, file_path: Path) -> str:
        """Extract text from Word document"""
        try:
            doc = DocxDocument(file_path)
            text_parts = []
            for paragraph in doc.paragraphs:
                if paragraph.text.strip():
                    text_parts.append(paragraph.text)
            return "\n".join(text_parts)
        except Exception as e:
            logger.error(f"Error extracting text from Word doc {file_path}: {str(e)}")
            return ""
    
    def _extract_from_excel(self, file_path: Path) -> str:
        """Extract text from Excel file"""
        try:
            workbook = load_workbook(file_path, data_only=True)
            text_parts = []
            for sheet_name in workbook.sheetnames:
                sheet = workbook[sheet_name]
                sheet_text = []
                for row in sheet.iter_rows(values_only=True):
                    row_text = " | ".join([str(cell) if cell else "" for cell in row])
                    if row_text.strip():
                        sheet_text.append(row_text)
                if sheet_text:
                    text_parts.append(f"\n--- Sheet: {sheet_name} ---\n" + "\n".join(sheet_text))
            return "\n\n".join(text_parts)
        except Exception as e:
            logger.error(f"Error extracting text from Excel {file_path}: {str(e)}")
            return ""
    
    def _extract_clins_from_table(self, file_path: Path) -> List[Dict]:
        """
        Extract CLINs from PDF tables using camelot-py or tabula-py
        Best for structured forms like SF1449, SF30
        
        Returns:
            List of CLIN dictionaries
        """
        if file_path.suffix.lower() != '.pdf':
            return []
        
        clins = []
        
        # Try camelot first
        if CAMELOT_AVAILABLE:
            try:
                tables = camelot.read_pdf(str(file_path), pages='all', flavor='lattice')
                logger.info(f"Found {len(tables)} tables with camelot")
                
                for table in tables:
                    df = table.df
                    # Look for CLIN column (usually first column)
                    for idx, row in df.iterrows():
                        # Check if first column looks like a CLIN number
                        first_cell = str(row.iloc[0]).strip() if len(row) > 0 else ""
                        if re.match(r'^\d+[A-Z]*$', first_cell):  # Simple CLIN pattern
                            clin_data = {
                                'clin_number': first_cell,
                                'product_description': str(row.iloc[1]) if len(row) > 1 else None,
                                'quantity': None,
                                'unit_of_measure': None,
                                'part_number': None,
                                'model_number': None,
                                'manufacturer_name': None,
                            }
                            # Try to extract quantity from other columns
                            for col in df.columns:
                                cell_value = str(row[col]).lower()
                                qty_match = re.search(r'(\d+(?:\.\d+)?)', cell_value)
                                if qty_match and not clin_data['quantity']:
                                    try:
                                        clin_data['quantity'] = float(qty_match.group(1))
                                    except ValueError:
                                        pass
                            
                            clins.append(clin_data)
            except Exception as e:
                logger.warning(f"camelot table extraction failed: {str(e)}")
        
        # Fallback to pdfplumber tables
        if not clins:
            try:
                with pdfplumber.open(file_path) as pdf:
                    for page in pdf.pages:
                        tables = page.extract_tables()
                        for table in tables:
                            if len(table) > 1:  # Has header row
                                for row in table[1:]:  # Skip header
                                    if row and len(row) > 0:
                                        first_cell = str(row[0]).strip() if row[0] else ""
                                        if re.match(r'^\d+[A-Z]*$', first_cell):
                                            clin_data = {
                                                'clin_number': first_cell,
                                                'product_description': str(row[1]) if len(row) > 1 else None,
                                                'quantity': None,
                                                'unit_of_measure': None,
                                            }
                                            clins.append(clin_data)
            except Exception as e:
                logger.warning(f"pdfplumber table extraction failed: {str(e)}")
        
        return clins
    
    def _extract_clins_with_llm(self, text: str) -> List[Dict]:
        """
        Extract CLINs using LLM (LangChain + Groq with Llama models)
        Best for unstructured text like SOW, amendments
        
        Returns:
            List of CLIN dictionaries
        """
        if not self.llm or not LANGCHAIN_AVAILABLE:
            return []
        
        try:
            # Skip Q&A documents
            text_lower = text.lower()
            qa_indicators = ['could the government', 'question', 'government clarify', 'q&a']
            if any(indicator in text_lower[:500] for indicator in qa_indicators):
                logger.debug("Skipping LLM extraction from Q&A document")
                return []
            
            # Limit text length for LLM (keep first 8000 chars for context)
            text_for_llm = text[:8000]
            
            # Create extraction chain
            chain = create_extraction_chain_pydantic(pydantic_schema=CLINItem, llm=self.llm)
            
            # Extract CLINs
            results = chain.run(text_for_llm)
            
            # Convert to our format
            clins = []
            if isinstance(results, list):
                for item in results:
                    if isinstance(item, CLINItem):
                        clin_data = {
                            'clin_number': item.item_number,
                            'product_description': item.description if item.description else None,
                            'product_name': item.product_name,
                            'quantity': float(item.quantity) if item.quantity else None,
                            'unit_of_measure': item.unit,
                            'part_number': item.part_number,
                            'model_number': item.model_number,
                            'manufacturer_name': item.manufacturer,
                        }
                        clins.append(clin_data)
            
            logger.info(f"LLM extracted {len(clins)} CLINs")
            return clins
            
        except Exception as e:
            logger.error(f"LLM extraction failed: {str(e)}", exc_info=True)
            return []
    
    def extract_clins(self, text: str, file_path: Optional[Path] = None) -> List[Dict]:
        """
        Extract CLINs using hybrid approach:
        1. Classify document type
        2. Use table extraction for structured forms (SF1449, SF30)
        3. Use LLM extraction for unstructured text (SOW, amendments)
        4. Fallback to regex extraction
        
        Args:
            text: Document text content
            file_path: Optional path to document file (for table extraction)
            
        Returns:
            List of CLIN dictionaries with extracted data
        """
        # Skip Q&A documents early
        text_lower = text.lower()
        qa_patterns = [
            r'could\s+the\s+government',
            r'question\s*\d+',
            r'government\s+clarif',
            r'q&a',
            r'q/a',
        ]
        if any(re.search(pattern, text_lower[:500]) for pattern in qa_patterns):
            logger.debug("Skipping CLIN extraction from Q&A document")
            return []
        
        clins = []
        doc_type = 'unknown'
        
        # Step 1: Classify document type
        if file_path:
            doc_type = self.classify_document_type(file_path, text)
        
        # Step 2: Route to appropriate extraction method
        if doc_type in ['sf1449', 'sf30'] and file_path:
            # Structured forms: Use table extraction
            logger.info(f"Using table extraction for {doc_type}")
            clins = self._extract_clins_from_table(file_path)
            if clins:
                logger.info(f"Table extraction found {len(clins)} CLINs")
                return clins
        
        # Step 3: For SOW, amendments, or unknown: Try LLM extraction
        if doc_type in ['sow', 'amendment', 'unknown'] and self.llm:
            logger.info(f"Attempting LLM extraction for {doc_type}")
            llm_clins = self._extract_clins_with_llm(text)
            if llm_clins:
                logger.info(f"LLM extraction found {len(llm_clins)} CLINs")
                return llm_clins
        
        # Step 4: Fallback to regex-based extraction
        logger.info("Using regex-based extraction (fallback)")
        return self._extract_clins_regex(text)
    
    def _extract_clins_regex(self, text: str) -> List[Dict]:
        """Fallback regex-based CLIN extraction (original method)"""
        clins = []
        
        # Find all CLIN numbers in the text
        clin_matches = []
        for pattern in self.CLIN_PATTERNS:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                clin_num = match.group(1)
                position = match.start()
                clin_matches.append((clin_num, position, match))
        
        # Sort by position in document
        clin_matches.sort(key=lambda x: x[1])
        
        # Extract details for each CLIN
        for i, (clin_num, position, match) in enumerate(clin_matches):
            start_pos = position
            end_pos = clin_matches[i + 1][1] if i + 1 < len(clin_matches) else min(position + 2000, len(text))
            clin_text = text[start_pos:end_pos]
            
            # Skip Q&A text
            if any(re.search(pattern, clin_text[:200].lower()) for pattern in [
                r'could\s+the\s+government', r'question\s*\d+', r'government\s+clarif'
            ]):
                logger.debug(f"Skipping CLIN {clin_num} - appears to be Q&A text")
                continue
            
            # Extract CLIN details using regex
            clin_data = {
                'clin_number': clin_num,
                'product_name': None,
                'product_description': None,
                'manufacturer_name': None,
                'part_number': None,
                'model_number': None,
                'quantity': None,
                'unit_of_measure': None,
                'service_description': None,
            }
            
            # Extract quantity
            qty_patterns = [r'quantity[:\s]+(\d+(?:\.\d+)?)', r'qty[:\s]+(\d+(?:\.\d+)?)']
            for pattern in qty_patterns:
                match = re.search(pattern, clin_text, re.IGNORECASE)
                if match:
                    try:
                        clin_data['quantity'] = float(match.group(1))
                    except ValueError:
                        pass
                    break
            
            # Extract description (first sentence after CLIN)
            sentences = re.split(r'[.!?]\s+', clin_text[:1000])
            if sentences and len(sentences) > 1:
                clin_data['product_description'] = sentences[1][:500]
            
            clins.append(clin_data)
        
        logger.info(f"Regex extraction found {len(clins)} CLINs")
        return clins
    
    def classify_solicitation_type(self, text: str, title: Optional[str] = None, description: Optional[str] = None) -> Tuple[SolicitationType, float]:
        """
        Classify solicitation type as product, service, or both
        
        Args:
            text: Extracted text from documents
            title: Opportunity title (optional)
            description: Opportunity description (optional)
            
        Returns:
            Tuple of (SolicitationType, confidence_score)
        """
        combined_text = " ".join([title or "", description or "", text]).lower()
        
        product_matches = sum(1 for keyword in self.PRODUCT_KEYWORDS if keyword in combined_text)
        service_matches = sum(1 for keyword in self.SERVICE_KEYWORDS if keyword in combined_text)
        
        total_matches = product_matches + service_matches
        if total_matches == 0:
            return SolicitationType.UNKNOWN, 0.0
        
        product_ratio = product_matches / total_matches
        service_ratio = service_matches / total_matches
        
        if product_ratio > 0.6:
            classification = SolicitationType.PRODUCT
            confidence = product_ratio
        elif service_ratio > 0.6:
            classification = SolicitationType.SERVICE
            confidence = service_ratio
        else:
            classification = SolicitationType.BOTH
            confidence = 1.0 - abs(product_ratio - service_ratio)
        
        if self.nlp and len(combined_text) > 100:
            try:
                doc = self.nlp(combined_text[:5000])
                nouns = [token.text.lower() for token in doc if token.pos_ == "NOUN"]
                verbs = [token.text.lower() for token in doc if token.pos_ == "VERB"]
                
                product_nouns = sum(1 for noun in nouns if any(kw in noun for kw in self.PRODUCT_KEYWORDS))
                service_verbs = sum(1 for verb in verbs if any(kw in verb for kw in self.SERVICE_KEYWORDS))
                
                if product_nouns > 0 or service_verbs > 0:
                    if product_nouns > service_verbs * 2:
                        classification = SolicitationType.PRODUCT
                        confidence = min(0.95, product_nouns / (product_nouns + service_verbs))
                    elif service_verbs > product_nouns * 2:
                        classification = SolicitationType.SERVICE
                        confidence = min(0.95, service_verbs / (product_nouns + service_verbs))
                    else:
                        classification = SolicitationType.BOTH
                        confidence = 0.85
            except Exception as e:
                logger.warning(f"spaCy classification failed: {str(e)}")
        
        logger.info(f"Classification: {classification.value}, confidence: {confidence:.2f}")
        return classification, confidence
    
    def extract_deadlines(self, text: str) -> List[Dict]:
        """
        Extract deadlines from document text
        
        Args:
            text: Document text content
            
        Returns:
            List of deadline dictionaries
        """
        deadlines = []
        
        deadline_pattern = r'(?:' + '|'.join(self.DEADLINE_KEYWORDS) + r')[:\s]*([^.\n]{10,200})'
        deadline_matches = re.finditer(deadline_pattern, text, re.IGNORECASE)
        
        for match in deadline_matches:
            deadline_context = match.group(0)
            
            for date_pattern in self.DATE_PATTERNS:
                date_match = re.search(date_pattern, deadline_context)
                if date_match:
                    try:
                        date_str = date_match.group(0)
                        parsed_date = dateutil.parser.parse(date_str, fuzzy=True, default=datetime(1900, 1, 1))
                        
                        time_str = None
                        timezone_str = None
                        
                        for time_pattern in self.TIME_PATTERNS:
                            time_match = re.search(time_pattern, deadline_context)
                            if time_match:
                                time_str = time_match.group(0)
                                break
                        
                        tz_patterns = [r'\b(EST|EDT|CST|CDT|MST|MDT|PST|PDT|UTC)\b']
                        for tz_pattern in tz_patterns:
                            tz_match = re.search(tz_pattern, deadline_context, re.IGNORECASE)
                            if tz_match:
                                timezone_str = tz_match.group(1).upper()
                                break
                        
                        deadline_type = "submission"
                        if any(kw in deadline_context.lower() for kw in ['question', 'inquiry']):
                            deadline_type = "questions_due"
                        elif any(kw in deadline_context.lower() for kw in ['quote', 'bid', 'proposal']):
                            deadline_type = "submission"
                        elif any(kw in deadline_context.lower() for kw in ['offer']):
                            deadline_type = "offers_due"
                        
                        deadlines.append({
                            'due_date': parsed_date,
                            'due_time': time_str,
                            'timezone': timezone_str,
                            'deadline_type': deadline_type,
                            'description': deadline_context[:500],
                            'is_primary': False,
                        })
                    except (ParserError, ValueError) as e:
                        logger.debug(f"Could not parse date from context: {deadline_context[:100]}")
                        continue
                    break
        
        for deadline in deadlines:
            if deadline['deadline_type'] in ['offers_due', 'submission']:
                deadline['is_primary'] = True
                break
        
        logger.info(f"Extracted {len(deadlines)} deadlines from document")
        return deadlines