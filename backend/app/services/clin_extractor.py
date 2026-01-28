"""
CLIN Extraction Service
Extracts Contract Line Item Numbers (CLINs) from government contract documents using LLM.
"""
import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from typing import List as TypingList

# LLM extraction (optional - for unstructured text)
try:
    from langchain_anthropic import ChatAnthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    logging.warning("LangChain Anthropic not available. Claude LLM disabled.")

try:
    from langchain_groq import ChatGroq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False
    logging.debug("LangChain Groq not available. Groq fallback disabled.")

try:
    from pydantic import BaseModel, Field
    try:
        from pydantic.v1 import BaseModel as V1BaseModel, Field as V1Field
        PYDANTIC_V1_AVAILABLE = True
    except ImportError:
        # Fallback: use v1 directly if available
        try:
            import pydantic.v1 as pydantic_v1
            V1BaseModel = pydantic_v1.BaseModel
            V1Field = pydantic_v1.Field
            PYDANTIC_V1_AVAILABLE = True
        except ImportError:
            PYDANTIC_V1_AVAILABLE = False
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    PYDANTIC_V1_AVAILABLE = False
    logging.warning("Pydantic not available. CLIN extraction disabled.")

from ..core.config import settings
from .text_extractor import TextExtractor

logger = logging.getLogger(__name__)


# Pydantic schema for LLM extraction
# Note: LangChain's create_extraction_chain_pydantic uses Pydantic v1 internally
# So we must use v1 BaseModel for compatibility
if LANGCHAIN_AVAILABLE and PYDANTIC_V1_AVAILABLE:
    class CLINItem(V1BaseModel):
        """
        Pydantic v1 schema for CLIN extraction using LLM.
        
        Extract Contract Line Item Numbers (CLINs) from government solicitation documents.
        Look for structured tables with item numbers, descriptions, quantities, and pricing information.
        """
        item_number: str = V1Field(description="The CLIN or line item number. This is the primary identifier, typically numeric like '0001', '0002', or alphanumeric like '0001AA'. Extract exactly as written in the document.")
        base_item_number: Optional[str] = V1Field(None, description="Base item number or supplementary reference code, often found in adjacent columns. Examples: 'S01', 'AA', 'BASE001'. Only extract if clearly labeled as base item or supplementary code.")
        description: str = V1Field(description="The full description of the product or service. This field is labeled 'Supplies/Services' in many forms. Extract the complete text description, including all details about what is being procured.")
        quantity: Optional[int] = V1Field(None, description="The quantity required as an integer. Extract numeric values only (e.g., 250, 2, 100). Do not include units or text.")
        unit: Optional[str] = V1Field(None, description="The unit of measure for the quantity. Common values: 'Each', 'Lot', 'Set', 'Unit', 'EA'. Extract exactly as written in the document.")
        contract_type: Optional[str] = V1Field(None, description="Contract type or pricing arrangement. Examples: 'Firm Fixed Price', 'Cost Plus Fixed Fee', 'FFP', 'CPFF'. Extract if clearly stated in the CLIN row or table.")
        extended_price: Optional[float] = V1Field(None, description="Extended price or total price for the line item. This may be calculated (quantity × unit price) or explicitly stated. Extract as a numeric value without currency symbols (e.g., 150.00, 18750.00).")
        part_number: Optional[str] = V1Field(None, description="Manufacturer part number if specified. Extract from 'Part Number', 'P/N', 'Part No.' fields, or from Bill of Materials (BOM) in technical drawings. Examples: 'RTVX2C', '50032173', '55222BF'.")
        model_number: Optional[str] = V1Field(None, description="Product model number if specified. Extract from 'Model Number', 'Model', or product descriptions. Examples: 'X1100C Diesel', 'REV E'.")
        manufacturer: Optional[str] = V1Field(None, description="Manufacturer name or brand name if specified. Extract from 'Brand Name', 'Manufacturer', 'by [Company]' patterns, or Q&A responses. Examples: 'Kubota', 'Leuze Electronics'. If custom/specification-based, extract 'Custom' or 'Per specifications'.")
        product_name: Optional[str] = V1Field(None, description="Short product name or title. This is often a condensed version of the description (e.g., 'Stack and Rack Carts', 'Desktop Computers'). Extract if clearly distinguishable from the full description.")
        drawing_number: Optional[str] = V1Field(None, description="Technical drawing number or reference if specified. Extract from 'Drawing', 'DWG NO', 'Attachment' references. Examples: '55222AD REV E', 'Drawing 55222AD'.")
        scope_of_work: Optional[str] = V1Field(None, description="Scope of work or service requirements for this CLIN. Extract from Statement of Work (SOW) sections, performance requirements, or service descriptions. Include timeline, testing requirements, acceptance criteria if mentioned.")
        delivery_timeline: Optional[str] = V1Field(None, description="Delivery timeline or schedule requirements. Extract phrases like 'within X days', 'X days after contract award', 'staggered delivery', 'preferred delivery time'. Examples: '60 days after contract award', 'Within 30 days'.")
        source_document: Optional[str] = V1Field(None, description="Name or identifier of the document where this CLIN was found. Used when processing multiple documents together.")
    
    class CLINExtractionResult(V1BaseModel):
        """
        Schema for batch CLIN extraction from multiple documents.
        """
        clins: List[CLINItem] = V1Field(description="List of all CLINs found across all documents")
elif LANGCHAIN_AVAILABLE:
    # Fallback: define empty class if v1 not available
    class CLINItem:
        pass


class CLINExtractor:
    """Service for extracting CLINs from government contract documents"""
    
    # CLIN patterns (for regex fallback)
    # CLINs are typically: 0001, 0002, 1, 2, or with suffix like 0001AA, 0001A
    # NOT short numbers with letters like 45B (those are usually base items)
    CLIN_PATTERNS = [
        r'CLIN\s*(\d{3,}[A-Z]*)',  # At least 3 digits (0001, 0002, etc.)
        r'CLIN\s*(\d{1,2}[A-Z]{2,})',  # 1-2 digits with 2+ letters (0001AA)
        r'Contract\s+Line\s+Item\s+Number\s*(\d{3,}[A-Z]*)',
        r'Line\s+Item\s+(\d{3,}[A-Z]*)',
        r'Item\s+No\.?\s*(\d{3,}[A-Z]*)',  # Item No. with at least 3 digits
    ]
    
    def __init__(self, text_extractor: Optional[TextExtractor] = None):
        """
        Initialize the CLIN extractor
        
        Args:
            text_extractor: Optional TextExtractor instance for text cleaning and document classification
        """
        self.text_extractor = text_extractor or TextExtractor()
        self.llm = None  # Primary LLM (Claude)
        self.fallback_llm = None  # Fallback LLM (Groq)
        
        # Initialize primary LLM (Claude) - optional - requires ANTHROPIC_API_KEY
        if LANGCHAIN_AVAILABLE and ANTHROPIC_AVAILABLE and settings.ANTHROPIC_API_KEY:
            try:
                self.llm = ChatAnthropic(
                    model=settings.ANTHROPIC_MODEL,
                    temperature=0,
                    api_key=settings.ANTHROPIC_API_KEY
                )
                logger.info(f"Claude LLM initialized: {settings.ANTHROPIC_MODEL}")
            except Exception as e:
                logger.warning(f"Failed to initialize Claude LLM: {str(e)}. Will use Groq fallback if available.")
                self.llm = None
        
        # Initialize fallback LLM (Groq) - optional - requires GROQ_API_KEY
        if LANGCHAIN_AVAILABLE and GROQ_AVAILABLE and settings.GROQ_API_KEY:
            try:
                self.fallback_llm = ChatGroq(
                    model=settings.GROQ_MODEL,
                    temperature=0,
                    api_key=settings.GROQ_API_KEY
                )
                logger.info(f"Groq LLM initialized as fallback: {settings.GROQ_MODEL}")
            except Exception as e:
                logger.warning(f"Failed to initialize Groq LLM: {str(e)}. Groq fallback disabled.")
                self.fallback_llm = None
        
        # Warn if no LLM is available
        if not self.llm and not self.fallback_llm:
            if not settings.ANTHROPIC_API_KEY and not settings.GROQ_API_KEY:
                logger.warning("Neither ANTHROPIC_API_KEY nor GROQ_API_KEY set. CLIN extraction disabled.")
            elif not LANGCHAIN_AVAILABLE:
                logger.warning("LangChain not available. CLIN extraction disabled.")
    
    def _clean_text(self, text: str) -> str:
        """Delegate to text extractor for text cleaning"""
        return self.text_extractor._clean_text(text)
    
    @staticmethod
    def _is_valid_clin_number(cell_value: str) -> bool:
        """
        Check if cell value looks like a valid CLIN number.
        CLINs are typically: 0001, 0002, 1, 2, or with suffix like 0001AA, 0001A
        NOT short numbers with single letters like 45B (those are usually base items)
        """
        if not cell_value or len(cell_value.strip()) == 0:
            return False
        # Match: at least 3 digits, OR 1-2 digits with 2+ letters (like 1AA, 2AB)
        return bool(re.match(r'^(\d{3,}[A-Z]*|\d{1,2}[A-Z]{2,})$', cell_value.strip()))
    
    def _try_extract_with_llm(self, document_instruction: str, document_text: str, use_claude: bool = True) -> List:
        """
        Helper method to try extraction with a specific LLM (Claude or Groq).
        
        Args:
            document_instruction: The prompt instruction
            document_text: The document text to extract from
            use_claude: If True, use Claude; if False, use Groq
            
        Returns:
            List of CLINItem objects or empty list if failed
        """
        import time
        
        # Select which LLM to use
        llm_to_use = self.llm if use_claude else self.fallback_llm
        llm_name = "Claude" if use_claude else "Groq"
        
        if not llm_to_use:
            logger.debug(f"{llm_name} LLM not available, skipping")
            return []
        
        max_retries = 3
        retry_delay = 2  # seconds
        
        for attempt in range(max_retries):
            try:
                document_prompt = document_instruction + document_text
                
                # Use LangChain 1.x API: with_structured_output
                # Use CLINExtractionResult which wraps the list of CLINItems
                try:
                    # Try function_calling first (better compatibility), fallback to json_schema
                    try:
                        structured_llm = llm_to_use.with_structured_output(CLINExtractionResult, method="function_calling")
                    except Exception as method_error:
                        logger.debug(f"{llm_name} function_calling failed, trying json_schema: {str(method_error)}")
                        structured_llm = llm_to_use.with_structured_output(CLINExtractionResult, method="json_schema")
                    extraction_result = structured_llm.invoke(document_prompt)
                    # Extract the list from the result
                    if isinstance(extraction_result, CLINExtractionResult):
                        result = extraction_result.clins
                    elif isinstance(extraction_result, dict) and 'clins' in extraction_result:
                        result = extraction_result['clins']
                    else:
                        result = extraction_result if isinstance(extraction_result, list) else []
                except Exception as e:
                    # Check if it's a rate limit error
                    error_str = str(e).lower()
                    if '429' in error_str or 'rate limit' in error_str or 'too many requests' in error_str:
                        if attempt < max_retries - 1:
                            wait_time = retry_delay * (attempt + 1)
                            logger.warning(f"{llm_name} rate limit hit, waiting {wait_time}s before retry {attempt + 2}/{max_retries}")
                            time.sleep(wait_time)
                            continue
                        else:
                            logger.error(f"{llm_name} rate limit exceeded after {max_retries} attempts")
                            return []
                    
                    # Log the actual error for debugging
                    logger.warning(f"{llm_name} with_structured_output failed: {str(e)}")
                    
                    # Fallback: try direct invoke with JSON parsing
                    try:
                        logger.debug(f"Trying {llm_name} direct invoke with JSON parsing")
                        response = llm_to_use.invoke(document_prompt + "\n\nReturn the CLINs as a JSON array.")
                        # Try to parse response content
                        if hasattr(response, 'content'):
                            import json
                            try:
                                # Try to parse as JSON
                                result = json.loads(response.content)
                                if isinstance(result, list):
                                    result = [CLINItem(**item) if isinstance(item, dict) else item for item in result]
                            except:
                                result = response.content
                        else:
                            result = str(response)
                    except Exception as fallback_error:
                        logger.error(f"{llm_name} all extraction methods failed: {str(fallback_error)}")
                        result = None
                
                # Extract results from response
                clins = []
                if isinstance(result, list):
                    clins = result
                elif isinstance(result, CLINItem):
                    clins = [result]
                elif isinstance(result, dict):
                    # Check if it's a single CLINItem dict
                    if 'item_number' in result:
                        clins = [result]
                    else:
                        # Try to find list in dict values
                        for value in result.values():
                            if isinstance(value, list):
                                clins = value
                                break
                            elif isinstance(value, CLINItem):
                                clins = [value]
                                break
                
                if clins:
                    logger.info(f"{llm_name} found {len(clins)} CLINs in document")
                else:
                    logger.debug(f"{llm_name} found no CLINs in document")
                
                # Success - return results
                return clins
                    
            except Exception as doc_error:
                error_str = str(doc_error).lower()
                # Check if it's a rate limit or temporary error
                if ('429' in error_str or 'rate limit' in error_str or 'too many requests' in error_str) and attempt < max_retries - 1:
                    wait_time = retry_delay * (attempt + 1)
                    logger.warning(f"{llm_name} rate limit error, waiting {wait_time}s before retry {attempt + 2}/{max_retries}")
                    time.sleep(wait_time)
                    continue
                elif attempt == max_retries - 1:
                    logger.error(f"{llm_name} failed to process document after {max_retries} attempts: {str(doc_error)}")
                    return []
                else:
                    logger.warning(f"{llm_name} error processing document (attempt {attempt + 1}/{max_retries}): {str(doc_error)}")
                    time.sleep(retry_delay)
                    continue
        
        return []
    
    def _extract_clins_with_llm(self, text: str) -> List[Dict]:
        """
        Extract CLINs using LLM (Claude primary, Groq fallback) with batch processing
        Best for unstructured text like SOW, amendments
        
        Returns:
            List of CLIN dictionaries
        """
        if not LANGCHAIN_AVAILABLE or not PYDANTIC_V1_AVAILABLE:
            if not PYDANTIC_V1_AVAILABLE:
                logger.warning("Pydantic v1 not available. LLM extraction requires Pydantic v1 for LangChain compatibility.")
            return []
        
        if not self.llm and not self.fallback_llm:
            logger.warning("No LLM available (neither Claude nor Groq). CLIN extraction disabled.")
            return []
        
        try:
            # Skip Q&A documents
            text_lower = text.lower()
            qa_indicators = ['could the government', 'question', 'government clarify', 'q&a']
            if any(indicator in text_lower[:500] for indicator in qa_indicators):
                logger.debug("Skipping LLM extraction from Q&A document")
                return []
            
            # Clean text before LLM processing
            cleaned_text = self._clean_text(text)
            
            if not cleaned_text.strip():
                logger.debug("Cleaned text is empty, skipping LLM extraction")
                return []
            
            # Process entire document at once (send full document, no truncation)
            # Claude 3 Haiku supports up to 200k tokens, so we can send full documents
            document_text = cleaned_text
            
            if not document_text.strip():
                return []
            
            logger.info(f"Processing full document for LLM extraction ({len(document_text)} chars)")
            
            # Detailed prompt for CLIN extraction
            document_instruction = """You are a specialized data extraction assistant for government contract documents. Your task is to extract Contract Line Item Numbers (CLINs) and their associated details from ANY government solicitation document format.

## INPUT
You will receive one or more government contract documents in text/PDF format. These may include:
- SF1449 forms
- SF30 forms
- Statements of Work (SOW)
- Amendments/Modifications
- Price schedules
- Technical specifications
- Any combination of the above

## TASK
Find and extract ALL Contract Line Item Numbers (CLINs) regardless of format or naming convention. Look for:

### CLIN IDENTIFIERS (any of these):
- "CLIN" or "CLIN:"
- "Line Item" or "Line Item No." or "Line Item Number"
- "Item No." or "Item Number" or "Item #"
- "Schedule Item"
- "0001", "0002", "0001AA", "0001AB" (standalone numbered items)
- Table rows with numerical identifiers
- Sections titled "Schedule of Supplies/Services"

### DATA TO EXTRACT (Core + Enhanced fields per CLIN):
**Core Fields (Required):**
1. **CLIN Number**: The exact identifier (e.g., "0001", "0001AA", "0001AB", "Line Item 1")
2. **Item Description**: Full product/service description text
3. **Quantity**: Numeric value (digits only, ignore text like "Lot" or "as required")
4. **Unit of Measure**: Exact unit (e.g., "Each", "Lot", "Set", "EA", "Unit")

**Enhanced Fields (Extract if available):**
5. **Manufacturer/Brand Name**: Extract from "Brand Name", "Manufacturer", "by [Company]" patterns, or Q&A responses
6. **Part Number**: Extract from "Part Number", "P/N", "Part No." fields, or Bill of Materials (BOM)
7. **Model Number**: Extract from "Model Number", "Model", or product descriptions
8. **Drawing Number**: Extract technical drawing references like "Drawing 55222AD REV E"
9. **Product Name**: Short product title (e.g., "Stack and Rack Carts")
10. **Scope of Work**: Service requirements, performance specs, usage specifications from SOW sections
11. **Delivery Timeline**: Extract phrases like "within X days", "X days after contract award", "preferred delivery time"

## SEARCH LOCATIONS
Scan ALL document sections for CLINs, especially:
- Tables with column headers containing "Item", "CLIN", "Line Item", "Description"
- Sections with "Schedule of Supplies/Services" or "Pricing Schedule"
- Numbered lists following patterns like "0001.", "0002.", "a.", "b."
- Any structured data with clear item numbering
- Amendments that modify/add line items
- Attachment files with pricing information

## RULES
- Extract ALL CLINs found across ALL input documents
- If a CLIN appears in multiple places (e.g., base document and amendment), use the most recent/specific version
- For amendments, note if they modify existing CLINs or add new ones
- If quantity is described textually (e.g., "as required", "TBD"), extract the text as-is
- If no CLINs are found, return empty array: []
- Ignore: general clauses, certifications, terms/conditions, repetitive boilerplate

## OUTPUT FORMAT
Return structured data matching the CLINItem schema. Each CLIN must include:
- "item_number" (string) - The CLIN identifier
- "description" (string) - Full product/service description
- "quantity" (number or null) - Numeric quantity if available
- "unit" (string or null) - Unit of measure
- **Enhanced fields** (extract if available):
  - "manufacturer" (string) - Brand name or manufacturer (e.g., "Kubota", "Custom")
  - "part_number" (string) - Part number from BOM or specifications (e.g., "RTVX2C", "55222BF")
  - "model_number" (string) - Model number (e.g., "X1100C Diesel")
  - "drawing_number" (string) - Technical drawing reference (e.g., "55222AD REV E")
  - "product_name" (string) - Short product name (e.g., "Stack and Rack Carts")
  - "scope_of_work" (string) - Service requirements, performance specs, usage specifications
  - "delivery_timeline" (string) - Delivery schedule (e.g., "60 days after contract award")
- Additional optional fields: base_item_number, contract_type, extended_price, source_document

DOCUMENT TEXT:
"""
            
            # Try Claude first, then Groq if Claude fails
            clins = self._try_extract_with_llm(document_instruction, document_text, use_claude=True)
            
            # If Claude failed and we have Groq fallback, try Groq
            if not clins and self.fallback_llm:
                logger.info("Claude extraction failed or returned no results, trying Groq fallback...")
                clins = self._try_extract_with_llm(document_instruction, document_text, use_claude=False)
            
            # Convert results to our format
            if clins:
                converted_clins = self._convert_llm_results_to_dicts(clins)
                if len(converted_clins) != len(clins):
                    logger.warning(f"CLIN conversion filtered out {len(clins) - len(converted_clins)} CLIN(s) (found {len(clins)}, kept {len(converted_clins)})")
                return converted_clins
            else:
                return []
            
        except Exception as e:
            logger.error(f"LLM extraction failed: {str(e)}")
            logger.debug(f"Error details: {type(e).__name__}", exc_info=True)
            return []
            
    def _convert_llm_results_to_dicts(self, results: List) -> List[Dict]:
        """Convert LLM results (CLINItem objects or dicts) to our standard dict format"""
        clins = []
        if not isinstance(results, list):
            return clins
        
        for item in results:
            try:
                # Handle both CLINItem objects and dicts
                if isinstance(item, CLINItem):
                    # Extract from Pydantic model
                    item_number = item.item_number
                    description = self._clean_text(item.description) if item.description else None
                    product_name = self._clean_text(item.product_name) if item.product_name else None
                    quantity = float(item.quantity) if item.quantity else None
                    unit = item.unit
                    base_item_number = getattr(item, 'base_item_number', None)
                    contract_type = getattr(item, 'contract_type', None)
                    extended_price = float(item.extended_price) if getattr(item, 'extended_price', None) else None
                    part_number = item.part_number
                    model_number = item.model_number
                    manufacturer = item.manufacturer
                    drawing_number = getattr(item, 'drawing_number', None)
                    scope_of_work = getattr(item, 'scope_of_work', None)
                    delivery_timeline = getattr(item, 'delivery_timeline', None)
                elif isinstance(item, dict):
                    # Extract from dict (in case LLM returns dict instead of model)
                    item_number = item.get('item_number', '')
                    description = self._clean_text(item.get('description', '')) if item.get('description') else None
                    product_name = self._clean_text(item.get('product_name', '')) if item.get('product_name') else None
                    quantity = float(item['quantity']) if item.get('quantity') else None
                    unit = item.get('unit')
                    base_item_number = item.get('base_item_number')
                    contract_type = item.get('contract_type')
                    extended_price = float(item['extended_price']) if item.get('extended_price') else None
                    part_number = item.get('part_number')
                    model_number = item.get('model_number')
                    manufacturer = item.get('manufacturer')
                    drawing_number = item.get('drawing_number')
                    scope_of_work = item.get('scope_of_work')
                    delivery_timeline = item.get('delivery_timeline')
                else:
                    continue
                
                # Validate CLIN number (must be valid format)
                if not item_number:
                    logger.debug(f"Skipping CLIN with empty item_number")
                    continue
                if not self._is_valid_clin_number(str(item_number)):
                    logger.debug(f"Skipping CLIN with invalid item_number format: '{item_number}'")
                    continue
                
                # Validate description (must be readable, not corrupted)
                if description:
                    desc_clean = description.strip()
                    if len(desc_clean) < 3:
                        description = None
                    elif not any(c.isalpha() for c in desc_clean):
                        description = None
                    elif re.search(r'^;[A-Z0-9<>=:]+(?:;[A-Z0-9<>=:]+)+;?$', desc_clean):
                        description = None
                    else:
                        letter_count = len(re.findall(r'[a-zA-Z]', desc_clean))
                        alnum_count = len(re.findall(r'[a-zA-Z0-9]', desc_clean))
                        if len(desc_clean) > 10 and (letter_count < 3 or (alnum_count / len(desc_clean)) < 0.3):
                            description = None
                
                # Only add if we have at least a CLIN number and some valid data
                if item_number:
                    clin_data = {
                        'clin_number': str(item_number).strip(),
                        'base_item_number': str(base_item_number).strip() if base_item_number else None,
                        'product_description': description,
                        'quantity': quantity,
                        'unit_of_measure': str(unit).strip() if unit else None,
                        'contract_type': str(contract_type).strip() if contract_type else None,
                        'extended_price': extended_price,
                        'product_name': product_name,
                        'manufacturer_name': str(manufacturer).strip() if manufacturer else None,
                        'part_number': str(part_number).strip() if part_number else None,
                        'model_number': str(model_number).strip() if model_number else None,
                        'drawing_number': str(drawing_number).strip() if drawing_number else None,
                        'scope_of_work': str(scope_of_work).strip() if scope_of_work else None,
                        'delivery_timeline': str(delivery_timeline).strip() if delivery_timeline else None,
                    }
                    clins.append(clin_data)
                        
            except Exception as item_error:
                logger.warning(f"Error converting LLM result item: {str(item_error)}")
                continue
        
        return clins
    
    def extract_clins(self, text: str, file_path: Optional[Path] = None) -> List[Dict]:
        """
        Extract CLINs using ONLY AI/LLM extraction.
        No table extraction, no regex fallback - AI only.
        
        Args:
            text: Document text content
            file_path: Optional path to document file (for document type classification)
            
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
        
        # ONLY use LLM extraction - no fallbacks
        if not self.llm and not self.fallback_llm:
            logger.warning("No LLM available (neither Claude nor Groq). Cannot extract CLINs (AI-only mode).")
            return []
        
        # Classify document type for logging
        doc_type = 'unknown'
        if file_path:
            doc_type = self.text_extractor.classify_document_type(file_path, text)
        
        logger.info(f"Using AI/LLM extraction for {doc_type} (AI-only mode)")
        llm_clins = self._extract_clins_with_llm(text)
        
        if llm_clins:
            logger.info(f"AI extraction found {len(llm_clins)} CLINs")
        else:
            logger.info("AI extraction found 0 CLINs")
        
        return llm_clins
    
    def extract_clins_batch(self, documents: List[Tuple[str, str]]) -> List[Dict]:
        """
        Extract CLINs from multiple documents in a single LLM call.
        Sends all documents together for batch processing.
        
        Args:
            documents: List of tuples (document_name, document_text)
            
        Returns:
            List of CLIN dictionaries with extracted data
        """
        if not LANGCHAIN_AVAILABLE or not PYDANTIC_V1_AVAILABLE:
            logger.warning("LangChain or Pydantic v1 not available for batch extraction")
            return []
        
        if not self.llm and not self.fallback_llm:
            logger.warning("No LLM available (neither Claude nor Groq) for batch extraction")
            return []
        
        if not documents:
            return []
        
        try:
            # Filter out Q&A documents
            filtered_docs = []
            for doc_name, doc_text in documents:
                text_lower = doc_text.lower()
                qa_indicators = ['could the government', 'question', 'government clarify', 'q&a']
                if not any(indicator in text_lower[:500] for indicator in qa_indicators):
                    cleaned_text = self._clean_text(doc_text)
                    if cleaned_text.strip():
                        filtered_docs.append((doc_name, cleaned_text))
            
            if not filtered_docs:
                logger.debug("No valid documents for batch CLIN extraction")
                return []
            
            # Combine all documents into one prompt
            total_chars = sum(len(text) for _, text in filtered_docs)
            logger.info(f"Batch processing {len(filtered_docs)} documents ({total_chars} total chars)")
            
            # Build combined prompt for batch processing
            batch_instruction = """You are a specialized data extraction assistant for government contract documents. Your task is to extract Contract Line Item Numbers (CLINs) and their associated details from ANY government solicitation document format.

## INPUT
You will receive multiple government contract documents in text/PDF format. These may include:
- SF1449 forms
- SF30 forms
- Statements of Work (SOW)
- Amendments/Modifications
- Price schedules
- Technical specifications
- Any combination of the above

## TASK
Find and extract ALL Contract Line Item Numbers (CLINs) from ALL documents regardless of format or naming convention. Look for:

### CLIN IDENTIFIERS (any of these):
- "CLIN" or "CLIN:"
- "Line Item" or "Line Item No." or "Line Item Number"
- "Item No." or "Item Number" or "Item #"
- "Schedule Item"
- "0001", "0002", "0001AA", "0001AB" (standalone numbered items)
- Table rows with numerical identifiers
- Sections titled "Schedule of Supplies/Services"

### DATA TO EXTRACT (Core + Enhanced fields per CLIN):
**Core Fields (Required):**
1. **CLIN Number**: The exact identifier (e.g., "0001", "0001AA", "0001AB", "Line Item 1")
2. **Item Description**: Full product/service description text
3. **Quantity**: Numeric value (digits only, ignore text like "Lot" or "as required")
4. **Unit of Measure**: Exact unit (e.g., "Each", "Lot", "Set", "EA", "Unit")
5. **Source Document**: Name of the document where this CLIN was found

**Enhanced Fields (Extract if available):**
6. **Manufacturer/Brand Name**: Extract from "Brand Name", "Manufacturer", "by [Company]" patterns
7. **Part Number**: Extract from "Part Number", "P/N", "Part No." fields, or Bill of Materials (BOM)
8. **Model Number**: Extract from "Model Number", "Model", or product descriptions
9. **Drawing Number**: Extract technical drawing references like "Drawing 55222AD REV E"
10. **Product Name**: Short product title (e.g., "Stack and Rack Carts")
11. **Scope of Work**: Service requirements, performance specs, usage specifications from SOW sections
12. **Delivery Timeline**: Extract phrases like "within X days", "X days after contract award", "preferred delivery time"

## SEARCH LOCATIONS
Scan ALL document sections for CLINs, especially:
- Tables with column headers containing "Item", "CLIN", "Line Item", "Description"
- Sections with "Schedule of Supplies/Services" or "Pricing Schedule"
- Numbered lists following patterns like "0001.", "0002.", "a.", "b."
- Any structured data with clear item numbering
- Amendments that modify/add line items
- Attachment files with pricing information

## RULES
- Extract ALL CLINs found across ALL input documents
- For each CLIN, include the source_document field to indicate which document it came from
- If a CLIN appears in multiple places (e.g., base document and amendment), use the most recent/specific version and note all source documents
- For amendments, note if they modify existing CLINs or add new ones
- If quantity is described textually (e.g., "as required", "TBD"), extract the text as-is
- If no CLINs are found, return empty array: []
- Ignore: general clauses, certifications, terms/conditions, repetitive boilerplate

## OUTPUT FORMAT
Return structured data matching the CLINItem schema. Each CLIN must include:
- "item_number" (string) - The CLIN identifier
- "description" (string) - Full product/service description
- "quantity" (number or null) - Numeric quantity if available
- "unit" (string or null) - Unit of measure
- "source_document" (string) - Name of the document where this CLIN was found
- Additional optional fields: base_item_number, contract_type, extended_price, part_number, model_number, manufacturer, product_name

DOCUMENTS:
"""
            
            combined_text = ""
            for doc_name, doc_text in filtered_docs:
                combined_text += f"\n{'='*80}\nDOCUMENT: {doc_name}\n{'='*80}\n{doc_text}\n"
            
            batch_prompt = batch_instruction + combined_text
            
            # Try Claude first, then Groq if Claude fails
            clins = self._try_extract_with_llm(batch_instruction, combined_text, use_claude=True)
            
            # If Claude failed and we have Groq fallback, try Groq
            if not clins and self.fallback_llm:
                logger.info("Claude batch extraction failed or returned no results, trying Groq fallback...")
                clins = self._try_extract_with_llm(batch_instruction, combined_text, use_claude=False)
            
            if clins:
                logger.info(f"Batch extraction found {len(clins)} CLINs across {len(filtered_docs)} documents")
                converted_clins = self._convert_llm_results_to_dicts(clins)
                return converted_clins
            else:
                logger.info("Batch extraction found 0 CLINs")
                return []
            
        except Exception as e:
            logger.error(f"Batch CLIN extraction failed: {str(e)}")
            return []
    
    def _find_clin_description_in_text(self, text: str, clin_number: str) -> Optional[str]:
        """
        Search for CLIN number in text and extract nearby description
        Used as fallback when table extraction finds CLIN but description is corrupted
        """
        # Search for CLIN number patterns in text
        patterns = [
            rf'CLIN\s+{re.escape(clin_number)}[:\s]+([^.\n]{20,500})',
            rf'Item\s+{re.escape(clin_number)}[:\s]+([^.\n]{20,500})',
            rf'Line\s+Item\s+{re.escape(clin_number)}[:\s]+([^.\n]{20,500})',
            rf'{re.escape(clin_number)}[:\s]+([^.\n]{20,500})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                desc = match.group(1).strip()
                # Clean and validate the description
                desc = self._clean_text(desc)
                # Check if it's valid (not corrupted)
                if desc and len(desc) >= 10:
                    letter_count = len(re.findall(r'[a-zA-Z]', desc))
                    if letter_count >= 5:  # At least 5 letters
                        # Take first sentence or first 200 chars
                        sentences = re.split(r'[.!?]\s+', desc)
                        if sentences:
                            result = sentences[0][:200].strip()
                            if len(result) >= 10:
                                return result
        
        # If no direct match, look for product/service descriptions near the CLIN
        # Search for common description patterns
        clin_pos = text.find(clin_number)
        if clin_pos != -1:
            # Look in a window around the CLIN number
            start = max(0, clin_pos - 500)
            end = min(len(text), clin_pos + 1000)
            window = text[start:end]
            
            # Look for description patterns
            desc_patterns = [
                r'Supplies/Services[:\s]+([^.\n]{20,300})',
                r'Description[:\s]+([^.\n]{20,300})',
                r'Item\s+Description[:\s]+([^.\n]{20,300})',
            ]
            
            for pattern in desc_patterns:
                match = re.search(pattern, window, re.IGNORECASE)
                if match:
                    desc = match.group(1).strip()
                    desc = self._clean_text(desc)
                    if desc and len(desc) >= 10:
                        letter_count = len(re.findall(r'[a-zA-Z]', desc))
                        if letter_count >= 5:
                            return desc[:200].strip()
        
        return None
    
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
                'base_item_number': None,
                'product_name': None,
                'product_description': None,
                'manufacturer_name': None,
                'part_number': None,
                'model_number': None,
                'contract_type': None,
                'extended_price': None,
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
            
            # Extract unit of measure
            unit_patterns = [r'unit[:\s]+([A-Za-z]+)', r'uom[:\s]+([A-Za-z]+)', r'\b(each|lot|set|unit|piece|ea)\b']
            for pattern in unit_patterns:
                match = re.search(pattern, clin_text, re.IGNORECASE)
                if match:
                    clin_data['unit_of_measure'] = match.group(1).capitalize()
                    break
            
            # Extract base item number
            base_item_match = re.search(r'base\s+item[:\s]+([A-Z]{1,3}\d{1,3}|[A-Z]{2,4})', clin_text, re.IGNORECASE)
            if base_item_match:
                clin_data['base_item_number'] = base_item_match.group(1)
            
            # Extract contract type
            contract_patterns = [
                r'contract\s+type[:\s]+([^,\n]+)',
                r'(firm\s+fixed\s+price|cost\s+plus|time\s+and\s+materials|fixed\s+price|ffp|cpff)',
            ]
            for pattern in contract_patterns:
                match = re.search(pattern, clin_text, re.IGNORECASE)
                if match:
                    clin_data['contract_type'] = match.group(1).strip()
                    break
            
            # Extract extended price
            price_patterns = [
                r'extended\s+price[:\s]*[\$]?\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)',
                r'total[:\s]*[\$]?\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)',
            ]
            for pattern in price_patterns:
                match = re.search(pattern, clin_text, re.IGNORECASE)
                if match:
                    try:
                        price_str = match.group(1).replace(',', '')
                        clin_data['extended_price'] = float(price_str)
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
