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
    import spacy as _spacy_module
    SPACY_AVAILABLE = True
except ImportError:
    _spacy_module = None  # type: ignore[assignment]
    SPACY_AVAILABLE = False
    logging.warning("spaCy not available. Using keyword-based classification only.")

try:
    from langchain_anthropic import ChatAnthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ChatAnthropic = None  # type: ignore[misc, assignment]
    ANTHROPIC_AVAILABLE = False
try:
    from langchain_groq import ChatGroq
    GROQ_AVAILABLE = True
except ImportError:
    ChatGroq = None  # type: ignore[misc, assignment]
    GROQ_AVAILABLE = False

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
        self._classification_llm = None
        self._classification_llm_fallback = None

        # LLM for solicitation type classification (product/service/both/unknown)
        if ANTHROPIC_AVAILABLE and ChatAnthropic is not None and getattr(settings, "ANTHROPIC_API_KEY", None):
            try:
                from pydantic import SecretStr
                self._classification_llm = ChatAnthropic(
                    model_name=getattr(settings, "ANTHROPIC_MODEL", "claude-3-sonnet-20240229"),
                    temperature=0,
                    api_key=SecretStr(settings.ANTHROPIC_API_KEY),
                    timeout=60,
                    max_tokens=64,
                )
                logger.info("DocumentAnalyzer: Claude LLM initialized for solicitation classification")
            except Exception as e:
                logger.warning("DocumentAnalyzer: Claude init for classification failed: %s", e)
        if (self._classification_llm is None) and GROQ_AVAILABLE and ChatGroq is not None and getattr(settings, "GROQ_API_KEY", None):
            try:
                from pydantic import SecretStr
                self._classification_llm_fallback = ChatGroq(
                    model=getattr(settings, "GROQ_MODEL", "llama-3.3-70b-versatile"),
                    temperature=0,
                    api_key=SecretStr(settings.GROQ_API_KEY),
                    max_tokens=64,
                )
                logger.info("DocumentAnalyzer: Groq LLM initialized for solicitation classification")
            except Exception as e:
                logger.warning("DocumentAnalyzer: Groq init for classification failed: %s", e)

        # Initialize spaCy (optional)
        if SPACY_AVAILABLE and _spacy_module is not None:
            try:
                self.nlp = _spacy_module.load("en_core_web_sm")
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
        file_path_str: Optional[str] = str(file_path) if file_path is not None else None
        clins, _ = self.clin_extractor.extract_clins(text, file_path_str)
        return clins
    
    def extract_clins_batch(self, documents: List[Tuple[str, str]]) -> Tuple[List[Dict], List[Dict]]:
        """
        Extract CLINs and deadlines from multiple documents in a single LLM call.
        Sends all documents together for batch processing.
        
        Args:
            documents: List of tuples (document_name, document_text)
            
        Returns:
            Tuple of (list of CLIN dicts, list of deadline dicts)
        """
        return self.clin_extractor.extract_clins_batch(documents)
    
    def _classify_solicitation_type_llm(
        self, text: str, title: Optional[str] = None, description: Optional[str] = None
    ) -> Optional[Tuple[SolicitationType, float]]:
        """
        Use LLM to classify solicitation as product, service, both, or unknown.
        Returns (SolicitationType, confidence) or None if LLM unavailable or fails.
        """
        llm = self._classification_llm or self._classification_llm_fallback
        if not llm:
            return None
        combined = " ".join([title or "", description or "", (text or "")[:4000]]).strip()
        if not combined or len(combined) < 50:
            return None
        prompt = """You are classifying a government solicitation/opportunity. Based only on the content below, decide whether it is primarily about:
- product: supplies, equipment, parts, materials, tangible items to be delivered
- service: labor, maintenance, support, training, consulting, or other performed work
- both: clear mix of product and service line items
- unknown: cannot determine from the text

Reply with exactly one word: product, service, both, or unknown. No explanation.

Content:
"""
        prompt += combined[:3500] + "\n\nYour one-word classification:"
        try:
            response = llm.invoke(prompt)
            raw = (getattr(response, "content", None) or str(response) or "").strip().lower()
            if not raw:
                return None
            # Check first line for one of the four labels (LLM may say "product" or "Classification: product")
            first_line = raw.split("\n")[0].strip()
            if "both" in first_line:
                return SolicitationType.BOTH, 0.92
            if "unknown" in first_line:
                return SolicitationType.UNKNOWN, 0.7
            if "product" in first_line and "service" not in first_line:
                return SolicitationType.PRODUCT, 0.92
            if "service" in first_line and "product" not in first_line:
                return SolicitationType.SERVICE, 0.92
            first_word = (first_line.split()[0] or "").strip(".,;:")
            for label, st in [
                ("product", SolicitationType.PRODUCT),
                ("service", SolicitationType.SERVICE),
                ("both", SolicitationType.BOTH),
                ("unknown", SolicitationType.UNKNOWN),
            ]:
                if first_word == label or first_word.startswith(label):
                    return (st, 0.92 if st != SolicitationType.UNKNOWN else 0.7)
            return None
        except Exception as e:
            logger.warning("LLM solicitation classification failed: %s", e)
            return None

    def classify_solicitation_type(self, text: str, title: Optional[str] = None, description: Optional[str] = None) -> Tuple[SolicitationType, float]:
        """
        Classify solicitation type as product, service, both, or unknown.
        Uses LLM first (so non-product opportunities are not mislabeled as product); falls back to keyword/spaCy.
        """
        # Prefer LLM so classification reflects actual content (e.g. service-only stays service)
        llm_result = self._classify_solicitation_type_llm(text, title=title, description=description)
        if llm_result is not None:
            classification, confidence = llm_result
            logger.info("Classification (LLM): %s, confidence: %.2f", classification.value, confidence)
            return classification, confidence

        # Fallback: keyword and optional spaCy
        combined_text = " ".join([title or "", description or "", text or ""]).lower()
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
                logger.warning("spaCy classification failed: %s", e)
        logger.info("Classification (fallback): %s, confidence: %.2f", classification.value, confidence)
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

    def extract_rfp_summary(self, combined_text: str) -> Optional[Dict]:
        """
        Extract RFP/solicitation summary (SF 1449 A–M style) for form filling and review.
        Uses the same documents/SAM text as CLIN extraction. Returns a dict with cover_page,
        delivery_schedule, statement_of_work, section_l_instructions_to_offerors, section_m_evaluation, etc.
        """
        if not combined_text or not combined_text.strip():
            return None
        return self.clin_extractor.extract_rfp_summary_llm(combined_text)
