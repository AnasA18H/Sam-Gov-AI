"""
Document Analyzer Service
Extracts text and data from PDF, Word, and Excel documents
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
    
    # CLIN patterns
    CLIN_PATTERNS = [
        r'CLIN\s*(\d+)',
        r'Contract\s+Line\s+Item\s+Number\s*(\d+)',
        r'Line\s+Item\s+(\d+)',
        r'Item\s+(\d+)',
        r'CLIN\s*(\d+[A-Z]?)',
        r'CLIN\s*([0-9]+[A-Z]*)',
    ]
    
    # Deadline patterns
    DATE_PATTERNS = [
        r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',  # MM/DD/YYYY or MM-DD-YYYY
        r'(\d{4}[/-]\d{1,2}[/-]\d{1,2})',  # YYYY/MM/DD
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
        if SPACY_AVAILABLE:
            try:
                # Try to load spaCy model (requires: python -m spacy download en_core_web_sm)
                self.nlp = spacy.load("en_core_web_sm")
                logger.info("spaCy model loaded successfully")
            except OSError:
                logger.warning("spaCy model 'en_core_web_sm' not found. Install with: python -m spacy download en_core_web_sm")
                logger.warning("Using keyword-based classification only")
    
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
            # Try relative to project root
            project_root = Path(settings.PROJECT_ROOT)
            abs_path = project_root / file_path
            if abs_path.exists():
                file_path_obj = abs_path
            # Try relative to STORAGE_BASE_PATH
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
        # Combine all text sources
        combined_text = " ".join([
            title or "",
            description or "",
            text
        ]).lower()
        
        # Count keyword matches
        product_matches = sum(1 for keyword in self.PRODUCT_KEYWORDS if keyword in combined_text)
        service_matches = sum(1 for keyword in self.SERVICE_KEYWORDS if keyword in combined_text)
        
        # Calculate confidence (simple keyword ratio)
        total_matches = product_matches + service_matches
        if total_matches == 0:
            return SolicitationType.UNKNOWN, 0.0
        
        product_ratio = product_matches / total_matches
        service_ratio = service_matches / total_matches
        
        # Determine classification
        if product_ratio > 0.6:
            classification = SolicitationType.PRODUCT
            confidence = product_ratio
        elif service_ratio > 0.6:
            classification = SolicitationType.SERVICE
            confidence = service_ratio
        else:
            classification = SolicitationType.BOTH
            confidence = 1.0 - abs(product_ratio - service_ratio)
        
        # Use spaCy for more advanced classification if available
        if self.nlp and len(combined_text) > 100:
            try:
                doc = self.nlp(combined_text[:5000])  # Limit text for performance
                # Extract nouns and verbs to improve classification
                nouns = [token.text.lower() for token in doc if token.pos_ == "NOUN"]
                verbs = [token.text.lower() for token in doc if token.pos_ == "VERB"]
                
                # Check for product/service indicators in nouns/verbs
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
    
    def extract_clins(self, text: str) -> List[Dict]:
        """
        Extract CLINs (Contract Line Item Numbers) from text
        
        Args:
            text: Document text content
            
        Returns:
            List of CLIN dictionaries with extracted data
        """
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
            # Find text context around this CLIN (next 500-1000 characters)
            start_pos = position
            end_pos = clin_matches[i + 1][1] if i + 1 < len(clin_matches) else min(position + 2000, len(text))
            clin_text = text[start_pos:end_pos]
            
            # Extract CLIN details
            clin_data = self._parse_clin_details(clin_num, clin_text)
            clins.append(clin_data)
        
        logger.info(f"Extracted {len(clins)} CLINs from document")
        return clins
    
    def _parse_clin_details(self, clin_number: str, clin_text: str) -> Dict:
        """Parse details for a single CLIN from its text context"""
        clin_data = {
            'clin_number': clin_number,
            'clin_name': None,
            'product_name': None,
            'product_description': None,
            'manufacturer_name': None,
            'part_number': None,
            'model_number': None,
            'quantity': None,
            'unit_of_measure': None,
            'service_description': None,
            'scope_of_work': None,
            'timeline': None,
            'service_requirements': None,
        }
        
        # Extract quantity
        qty_patterns = [
            r'quantity[:\s]+(\d+(?:\.\d+)?)',
            r'qty[:\s]+(\d+(?:\.\d+)?)',
            r'(\d+(?:\.\d+)?)\s*(units?|each|pieces?|lots?)',
        ]
        for pattern in qty_patterns:
            match = re.search(pattern, clin_text, re.IGNORECASE)
            if match:
                try:
                    clin_data['quantity'] = float(match.group(1))
                    # Extract unit of measure if present
                    unit_match = re.search(r'(?:units?|each|pieces?|lots?|pairs?|sets?)', clin_text[match.end():match.end()+50], re.IGNORECASE)
                    if unit_match:
                        clin_data['unit_of_measure'] = unit_match.group(0).lower()
                except ValueError:
                    pass
                break
        
        # Extract part/model numbers
        part_patterns = [
            r'part\s+number[:\s]+([A-Z0-9\-]+)',
            r'p/n[:\s]+([A-Z0-9\-]+)',
            r'model\s+number[:\s]+([A-Z0-9\-]+)',
            r'model[:\s]+([A-Z0-9\-]+)',
        ]
        for pattern in part_patterns:
            match = re.search(pattern, clin_text, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                if 'part' in pattern.lower():
                    clin_data['part_number'] = value
                elif 'model' in pattern.lower():
                    clin_data['model_number'] = value
                break
        
        # Extract manufacturer
        mfr_patterns = [
            r'manufacturer[:\s]+([A-Z][A-Za-z\s&.,]+)',
            r'manufactured\s+by[:\s]+([A-Z][A-Za-z\s&.,]+)',
        ]
        for pattern in mfr_patterns:
            match = re.search(pattern, clin_text[:500], re.IGNORECASE)
            if match:
                manufacturer = match.group(1).strip()
                # Limit manufacturer name length
                if len(manufacturer) <= 255:
                    clin_data['manufacturer_name'] = manufacturer
                break
        
        # Extract product/service description (first 2-3 sentences after CLIN)
        sentences = re.split(r'[.!?]\s+', clin_text[:1000])
        if sentences:
            # Look for description patterns
            desc_start = None
            for i, sent in enumerate(sentences):
                if any(keyword in sent.lower() for keyword in ['provide', 'furnish', 'deliver', 'supply', 'perform', 'complete']):
                    desc_start = i
                    break
            
            if desc_start is not None:
                description = ' '.join(sentences[desc_start:desc_start+3])
                if 'product' in clin_text.lower() or clin_data['part_number'] or clin_data['model_number']:
                    clin_data['product_description'] = description[:2000]  # Limit length
                else:
                    clin_data['service_description'] = description[:2000]
        
        return clin_data
    
    def extract_deadlines(self, text: str) -> List[Dict]:
        """
        Extract deadlines from document text
        
        Args:
            text: Document text content
            
        Returns:
            List of deadline dictionaries
        """
        deadlines = []
        
        # Find deadline keywords and nearby dates
        deadline_pattern = r'(?:' + '|'.join(self.DEADLINE_KEYWORDS) + r')[:\s]*([^.\n]{10,200})'
        deadline_matches = re.finditer(deadline_pattern, text, re.IGNORECASE)
        
        for match in deadline_matches:
            deadline_context = match.group(0)
            
            # Extract date from context
            for date_pattern in self.DATE_PATTERNS:
                date_match = re.search(date_pattern, deadline_context)
                if date_match:
                    try:
                        # Parse date
                        date_str = date_match.group(0)
                        parsed_date = dateutil.parser.parse(date_str, fuzzy=True, default=datetime(1900, 1, 1))
                        
                        # Extract time if present
                        time_str = None
                        timezone_str = None
                        
                        for time_pattern in self.TIME_PATTERNS:
                            time_match = re.search(time_pattern, deadline_context)
                            if time_match:
                                time_str = time_match.group(0)
                                break
                        
                        # Extract timezone
                        tz_patterns = [r'\b(EST|EDT|CST|CDT|MST|MDT|PST|PDT|UTC)\b']
                        for tz_pattern in tz_patterns:
                            tz_match = re.search(tz_pattern, deadline_context, re.IGNORECASE)
                            if tz_match:
                                timezone_str = tz_match.group(1).upper()
                                break
                        
                        # Determine deadline type from context
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
                            'description': deadline_context[:500],  # Limit length
                            'is_primary': False,  # Will be set based on type
                        })
                    except (ParserError, ValueError) as e:
                        logger.debug(f"Could not parse date from context: {deadline_context[:100]}")
                        continue
                    break
        
        # Mark primary deadline (usually the offers due date)
        for deadline in deadlines:
            if deadline['deadline_type'] in ['offers_due', 'submission']:
                deadline['is_primary'] = True
                break
        
        logger.info(f"Extracted {len(deadlines)} deadlines from document")
        return deadlines
