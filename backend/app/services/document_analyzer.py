"""
Document Analyzer Service
Facade for text extraction and CLIN detection services.
Maintains backward compatibility with existing code.
"""
import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import dateutil.parser
from dateutil.parser import ParserError

# NLP (optional - spaCy for advanced classification)
try:
    import spacy
    SPACY_AVAILABLE = True
except ImportError:
    SPACY_AVAILABLE = False
    logging.warning("spaCy not available. Using keyword-based classification only.")

from ..core.config import settings
from ..models.opportunity import SolicitationType
from .text_extractor import TextExtractor
from .clin_extractor import CLINExtractor

logger = logging.getLogger(__name__)


class DocumentAnalyzer:
    """
    Analyzer for extracting text and structured data from solicitation documents.
    
    This class acts as a facade that delegates to:
    - TextExtractor: for text extraction from various document formats
    - CLINExtractor: for CLIN detection and extraction
    
    Maintains backward compatibility with existing code.
    """
    
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
        self.text_extractor = TextExtractor()
        self.clin_extractor = CLINExtractor(self.text_extractor)
        
        # Initialize spaCy (optional)
        if SPACY_AVAILABLE:
            try:
                self.nlp = spacy.load("en_core_web_sm")
                logger.info("spaCy model loaded successfully")
            except OSError:
                logger.warning("spaCy model 'en_core_web_sm' not found. Using keyword-based classification only.")
    
    def classify_document_type(self, file_path: Path, text: str) -> str:
        """
        Classify document type to route to correct extraction method
        
        Returns:
            Document type: 'sf1449', 'sf30', 'sow', 'amendment', or 'unknown'
        """
        return self.text_extractor.classify_document_type(file_path, text)
    
    def extract_text(self, file_path: str) -> str:
        """
        Extract text from a document file with automatic format detection.
        Supports PDF, Word, Excel, PowerPoint, Images, and Text formats.
        
        Args:
            file_path: Path to the document file
            
        Returns:
            Extracted text content
        """
        return self.text_extractor.extract_text(file_path)
    
    def extract_clins(self, text: str, file_path: Optional[Path] = None) -> List[Dict]:
        """
        Extract CLINs using ONLY AI/LLM extraction.
        No table extraction, no regex fallback - AI only.
        
        Args:
            text: Document text content
            file_path: Optional path to document file (not used, kept for compatibility)
            
        Returns:
            List of CLIN dictionaries with extracted data
        """
        return self.clin_extractor.extract_clins(text, file_path)
    
    def extract_clins_batch(self, documents: List[Tuple[str, str]]) -> List[Dict]:
        """
        Extract CLINs from multiple documents in a single LLM call.
        Sends all documents together for batch processing.
        
        Args:
            documents: List of tuples (document_name, document_text)
            
        Returns:
            List of CLIN dictionaries with extracted data
        """
        return self.clin_extractor.extract_clins_batch(documents)
    
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
        Extract deadlines from document text using LLM (primary) with regex fallback
        
        Args:
            text: Document text content
            
        Returns:
            List of deadline dictionaries
        """
        # Try LLM-based extraction first
        try:
            llm_deadlines = self.clin_extractor.extract_deadlines_llm(text)
            if llm_deadlines:
                logger.info(f"LLM extracted {len(llm_deadlines)} deadlines")
                return llm_deadlines
        except Exception as e:
            logger.warning(f"LLM deadline extraction failed, falling back to regex: {str(e)}")
        
        # Fallback to regex-based extraction
        logger.info("Falling back to regex-based deadline extraction")
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
    