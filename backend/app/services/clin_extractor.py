"""
CLIN Extraction Service - Simplified
Extracts Contract Line Item Numbers (CLINs) from government contract documents using LLM.
"""
import json
import logging
import re
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import dateutil.parser

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
    from pydantic.v1 import BaseModel as V1BaseModel, Field as V1Field
    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False
    logging.warning("Pydantic v1 not available. CLIN extraction disabled.")

from ..core.config import settings
from .text_extractor import TextExtractor

logger = logging.getLogger(__name__)


# Pydantic schema for LLM extraction
if PYDANTIC_AVAILABLE:
    class CLINItem(V1BaseModel):
        item_number: str = V1Field(description="The CLIN number (e.g., '0001', '0002')")
        description: str = V1Field(description="Full product/service description")
        quantity: Optional[int] = V1Field(None, description="Quantity as integer")
        unit: Optional[str] = V1Field(None, description="Unit of measure (e.g., 'Each', 'Lot')")
        product_name: Optional[str] = V1Field(None, description="Short product name")
        contract_type: Optional[str] = V1Field(None, description="Contract type (e.g., 'Firm Fixed Price')")
        manufacturer: Optional[str] = V1Field(None, description="Manufacturer name")
        part_number: Optional[str] = V1Field(None, description="Part number")
        model_number: Optional[str] = V1Field(None, description="Model number")
        drawing_number: Optional[str] = V1Field(None, description="Drawing number from filename or document")
        scope_of_work: Optional[str] = V1Field(None, description="Complete scope of work text including all requirements")
        service_requirements: Optional[str] = V1Field(None, description="Service-specific requirements, SLAs, and service deliverables")
        delivery_address: Optional[str] = V1Field(None, description="Complete delivery address including facility name, street address, city, state, ZIP code")
        special_delivery_instructions: Optional[str] = V1Field(None, description="Special delivery instructions, requirements, or constraints")
        delivery_timeline: Optional[str] = V1Field(None, description="Complete delivery timeline with full context including required delivery date")
        base_item_number: Optional[str] = V1Field(None, description="Base item number")
        extended_price: Optional[float] = V1Field(None, description="Extended price")
        source_document: Optional[str] = V1Field(None, description="Document name where CLIN was found")
    
    class DeadlineItem(V1BaseModel):
        due_date: str = V1Field(description="Deadline date in YYYY-MM-DD format")
        due_time: Optional[str] = V1Field(None, description="Deadline time in HH:MM format (24-hour)")
        timezone: Optional[str] = V1Field(None, description="Timezone abbreviation (EST, EDT, CST, CDT, MST, MDT, PST, PDT, UTC)")
        deadline_type: str = V1Field(description="Type of deadline: 'offers_due', 'submission', 'questions_due', or 'other'")
        description: Optional[str] = V1Field(None, description="Brief description of what the deadline is for")
        is_primary: bool = V1Field(False, description="True if this is the primary submission deadline")
    
    class CLINExtractionResult(V1BaseModel):
        clins: List[CLINItem] = V1Field(default_factory=list, description="List of CLINs")
        deadlines: List[DeadlineItem] = V1Field(default_factory=list, description="List of deadlines")


class CLINExtractor:
    """Simple CLIN extractor using Claude (primary) and Groq (fallback)"""
    
    def __init__(self, text_extractor: Optional[TextExtractor] = None):
        self.text_extractor = text_extractor or TextExtractor()
        self.llm = None
        self.fallback_llm = None
        
        # Initialize Claude
        if ANTHROPIC_AVAILABLE and settings.ANTHROPIC_API_KEY:
            try:
                self.llm = ChatAnthropic(
                    model=settings.ANTHROPIC_MODEL,
                    temperature=0,
                    api_key=settings.ANTHROPIC_API_KEY
                )
                logger.info(f"Claude LLM initialized: {settings.ANTHROPIC_MODEL}")
            except Exception as e:
                logger.warning(f"Failed to initialize Claude: {e}")
        
        # Initialize Groq fallback
        if GROQ_AVAILABLE and settings.GROQ_API_KEY:
            try:
                self.fallback_llm = ChatGroq(
                    model=settings.GROQ_MODEL,
                    temperature=0,
                    api_key=settings.GROQ_API_KEY
                )
                logger.info(f"Groq LLM initialized: {settings.GROQ_MODEL}")
            except Exception as e:
                logger.warning(f"Failed to initialize Groq: {e}")
    
    def _clean_text(self, text: str) -> str:
        """Clean text using text extractor"""
        return self.text_extractor._clean_text(text)
    
    def _extract_with_llm(self, prompt: str, use_claude: bool = True) -> Tuple[List, List]:
        """Extract CLINs and deadlines using LLM - returns tuple (clins, deadlines)"""
        llm_to_use = self.llm if use_claude else self.fallback_llm
        llm_name = "Claude" if use_claude else "Groq"
        
        if not llm_to_use:
            return ([], [])
        
        # Prompt already includes JSON format instructions
        try:
            # Try structured output first (best method)
            structured_llm = llm_to_use.with_structured_output(CLINExtractionResult, method="function_calling")
            result = structured_llm.invoke(prompt)
            
            # Log raw structured output result
            logger.info(f"{llm_name} RAW STRUCTURED OUTPUT RESULT:")
            logger.info(f"Type: {type(result)}")
            if isinstance(result, CLINExtractionResult):
                logger.info(f"CLINExtractionResult.clins type: {type(result.clins)}, length: {len(result.clins) if isinstance(result.clins, list) else 'N/A'}")
                logger.info(f"CLINExtractionResult.clins content: {result.clins}")
            elif isinstance(result, dict):
                logger.info(f"Dict keys: {result.keys()}")
                logger.info(f"Dict content: {result}")
            else:
                logger.info(f"Result: {result}")
            
            # Save raw structured output to debug file
            try:
                from pathlib import Path
                debug_dir = settings.DEBUG_EXTRACTS_DIR if hasattr(settings, 'DEBUG_EXTRACTS_DIR') else None
                if debug_dir:
                    debug_dir = Path(debug_dir)
                    debug_dir.mkdir(parents=True, exist_ok=True)
                    raw_response_file = debug_dir / f"raw_ai_response_{llm_name.lower()}_structured.txt"
                    with open(raw_response_file, 'w', encoding='utf-8') as f:
                        f.write(f"{llm_name} RAW STRUCTURED OUTPUT RESULT\n")
                        f.write("=" * 80 + "\n")
                        f.write(f"Type: {type(result)}\n")
                        if isinstance(result, CLINExtractionResult):
                            f.write(f"CLINExtractionResult.clins type: {type(result.clins)}\n")
                            f.write(f"CLINExtractionResult.clins length: {len(result.clins) if isinstance(result.clins, list) else 'N/A'}\n")
                            f.write("=" * 80 + "\n")
                            f.write("CLINS CONTENT:\n")
                            f.write("=" * 80 + "\n")
                            try:
                                f.write(json.dumps([item.dict() if hasattr(item, 'dict') else str(item) for item in result.clins], indent=2, default=str))
                            except:
                                f.write(str(result.clins))
                        elif isinstance(result, dict):
                            f.write(f"Dict keys: {list(result.keys())}\n")
                            f.write("=" * 80 + "\n")
                            f.write("DICT CONTENT:\n")
                            f.write("=" * 80 + "\n")
                            f.write(json.dumps(result, indent=2, default=str))
                        else:
                            f.write(f"Result: {result}\n")
                    logger.info(f"Saved raw {llm_name} structured output to {raw_response_file}")
            except Exception as debug_err:
                logger.debug(f"Could not save raw structured output to file: {debug_err}")
            
            # Extract clins and deadlines
            clins_list = []
            deadlines_list = []
            
            if isinstance(result, CLINExtractionResult):
                clins_list = result.clins if isinstance(result.clins, list) else []
                deadlines_list = result.deadlines if hasattr(result, 'deadlines') and isinstance(result.deadlines, list) else []
            elif isinstance(result, dict):
                clins_list = result.get('clins', [])
                deadlines_list = result.get('deadlines', [])
            elif isinstance(result, list):
                # If it's a list, assume it's CLINs (backward compatibility)
                clins_list = result
            
            # Return tuple: (clins, deadlines)
            return (clins_list, deadlines_list if deadlines_list else [])
        except Exception as e:
            logger.debug(f"{llm_name} structured output failed, trying direct JSON: {e}")
            # Fallback: direct JSON extraction with robust parsing
            try:
                response = llm_to_use.invoke(prompt)
                content = response.content if hasattr(response, 'content') else str(response)
                
                # Log raw response content
                logger.info(f"{llm_name} RAW RESPONSE CONTENT:")
                logger.info(f"Response type: {type(response)}")
                logger.info(f"Content type: {type(content)}")
                logger.info(f"Content length: {len(content) if isinstance(content, str) else 'N/A'}")
                logger.info(f"Content preview (first 2000 chars): {content[:2000] if isinstance(content, str) else content}")
                if isinstance(content, str) and len(content) > 2000:
                    logger.info(f"Content preview (last 500 chars): {content[-500:]}")
                
                # Save full raw response to debug file
                try:
                    from pathlib import Path
                    debug_dir = settings.DEBUG_EXTRACTS_DIR if hasattr(settings, 'DEBUG_EXTRACTS_DIR') else None
                    if debug_dir:
                        debug_dir = Path(debug_dir)
                        debug_dir.mkdir(parents=True, exist_ok=True)
                        raw_response_file = debug_dir / f"raw_ai_response_{llm_name.lower()}.txt"
                        with open(raw_response_file, 'w', encoding='utf-8') as f:
                            f.write(f"{llm_name} RAW RESPONSE\n")
                            f.write("=" * 80 + "\n")
                            f.write(f"Response type: {type(response)}\n")
                            f.write(f"Content type: {type(content)}\n")
                            f.write(f"Content length: {len(content) if isinstance(content, str) else 'N/A'}\n")
                            f.write("=" * 80 + "\n")
                            f.write("FULL CONTENT:\n")
                            f.write("=" * 80 + "\n")
                            f.write(str(content))
                        logger.info(f"Saved raw {llm_name} response to {raw_response_file}")
                except Exception as debug_err:
                    logger.debug(f"Could not save raw response to file: {debug_err}")
                
                # Clean content - remove any markdown, code blocks, or extra text
                content = content.strip()
                
                # Try multiple extraction strategies
                extracted_json = None
                
                # Strategy 1: Remove markdown code blocks if present
                json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
                if json_match:
                    extracted_json = json_match.group(1)
                else:
                    # Strategy 2: Find JSON object with "clins" key
                    json_match = re.search(r'\{\s*"clins"\s*:\s*\[.*?\]\s*\}', content, re.DOTALL)
                    if json_match:
                        extracted_json = json_match.group(0)
                    else:
                        # Strategy 3: Find any JSON object that might contain clins
                        json_match = re.search(r'\{[^{}]*"clins"[^{}]*\[.*?\][^{}]*\}', content, re.DOTALL)
                        if json_match:
                            extracted_json = json_match.group(0)
                        else:
                            # Strategy 4: Find outermost JSON object
                            json_match = re.search(r'\{.*\}', content, re.DOTALL)
                            if json_match:
                                extracted_json = json_match.group(0)
                
                if not extracted_json:
                    logger.warning(f"{llm_name} could not extract JSON from response")
                    logger.debug(f"Content preview: {content[:500]}")
                    return []
                
                # Parse JSON
                parsed = json.loads(extracted_json)
                
                # Extract clins and deadlines arrays - handle various response formats
                clins_list = []
                deadlines_list = []
                
                if isinstance(parsed, dict):
                    if 'clins' in parsed:
                        clins_list = parsed['clins'] if isinstance(parsed['clins'], list) else []
                    else:
                        # Check if dict itself is a CLIN item
                        if 'item_number' in parsed or 'clin_number' in parsed:
                            clins_list = [parsed]
                    
                    if 'deadlines' in parsed:
                        deadlines_list = parsed['deadlines'] if isinstance(parsed['deadlines'], list) else []
                elif isinstance(parsed, list):
                    # If it's a list, assume it's CLINs (backward compatibility)
                    clins_list = parsed
                
                if not isinstance(clins_list, list):
                    logger.warning(f"{llm_name} returned unexpected structure: {type(clins_list)}")
                    return ([], [])
                
                logger.info(f"{llm_name} extracted {len(clins_list)} CLINs and {len(deadlines_list)} deadlines from JSON response")
                return (clins_list, deadlines_list)
                
            except json.JSONDecodeError as json_err:
                logger.error(f"{llm_name} JSON parsing failed: {json_err}")
                logger.debug(f"Content preview: {content[:500] if 'content' in locals() else 'N/A'}")
                # Try to find and extract clins and deadlines arrays
                try:
                    # Look for clins array directly
                    clins_match = re.search(r'"clins"\s*:\s*\[(.*?)\]', content, re.DOTALL)
                    deadlines_match = re.search(r'"deadlines"\s*:\s*\[(.*?)\]', content, re.DOTALL)
                    
                    clins_list = []
                    deadlines_list = []
                    
                    if clins_match:
                        # Try to parse as array
                        array_str = '[' + clins_match.group(1) + ']'
                        try:
                            clins_list = json.loads(array_str)
                            logger.info(f"{llm_name} extracted {len(clins_list)} CLINs from clins array directly")
                        except:
                            pass
                    
                    if deadlines_match:
                        # Try to parse deadlines array
                        array_str = '[' + deadlines_match.group(1) + ']'
                        try:
                            deadlines_list = json.loads(array_str)
                            logger.info(f"{llm_name} extracted {len(deadlines_list)} deadlines from deadlines array directly")
                        except:
                            pass
                    
                    return (clins_list if isinstance(clins_list, list) else [], deadlines_list if isinstance(deadlines_list, list) else [])
                except:
                    pass
                return ([], [])
            except Exception as fallback_error:
                logger.error(f"{llm_name} JSON fallback failed: {fallback_error}")
                return ([], [])
    
    def extract_clins(self, text: str, file_path: Optional[str] = None) -> Tuple[List[Dict], List[Dict]]:
        """Extract CLINs and deadlines from a single document"""
        if not self.llm and not self.fallback_llm:
            logger.warning("No LLM available")
            return ([], [])
        
        # Use raw text without cleaning to preserve all information
        if not text or not text.strip():
            return []
        
        # Enhanced prompt for comprehensive CLIN extraction
        prompt = f"""You are a government contracting analyst. Analyze this solicitation document and extract ALL Contract Line Item Numbers (CLINs) and their complete details.

CRITICAL: Extract EVERY CLIN found in the document. Search SYSTEMATICALLY through the ENTIRE document. Look for:
- Tables with headers containing "CLIN", "Line Item", "Item Number", "Schedule Item", "Item No"
- Sections titled "Schedule of Supplies/Services", "Pricing Schedule", "CLIN Schedule", "SECTION B", "Schedule"
- Lists following numbering like "0001.", "0002.", "0003.", "a.", "b."
- Any clearly defined line items in pricing schedules, amendments, attachments
- Numbered items with quantities, descriptions, and pricing information
- DO NOT stop after finding one CLIN - continue searching until you have found ALL CLINs in the document

For EACH CLIN found, extract ALL available information:

1. BASIC CLIN INFORMATION:
   - item_number (required): CLIN number exactly as written
   - description (required): Complete product/service description - extract the FULL text
   - quantity (optional): Quantity as integer or float
   - unit (optional): Unit of measure
   - contract_type (optional): Contract type
   - base_item_number (optional): Base item number or supplementary code
   - extended_price (optional): Extended price as float

2. PRODUCT/SERVICE DETAILS:
   - product_name (optional): Product name and description - extract product name if clearly distinguishable from description
   - description (required): Complete product/service description - extract the FULL text
   - manufacturer (optional): Manufacturer name - extract manufacturer name from BOM, specifications, or product descriptions
   - part_number (optional): Part number - extract manufacturer part number from BOM, specifications, or part number fields
   - model_number (optional): Model number - extract product model number from descriptions or specifications
   - quantity (optional): Quantity required - extract quantity as integer or float
   - drawing_number (optional): Technical drawing reference including revision (check filenames, document titles, attachment names)

3. SERVICE/SCOPE INFORMATION:
   - scope_of_work (optional): COMPLETE Statement of Work (SOW) text for this CLIN including:
     * Performance requirements and specifications
     * Testing and acceptance criteria
     * Usage requirements and operational context
     * Quality standards and compliance requirements
     * Any SOW sections describing work/services required
     * Extract the FULL text, not just a summary
   - service_requirements (optional): For service CLINs, extract specific service requirements including:
     * Service specifications and deliverables
     * Performance standards and metrics
     * Service level agreements (SLAs)
     * Any additional service-specific requirements

4. DELIVERY INFORMATION:
   - delivery_address (optional): Complete delivery address including:
     * Facility name (e.g., "Fort Worth, T.X. Facility (WCF)")
     * Street address (e.g., "9000 Blue Mound Road")
     * City, State, ZIP code
     * Extract complete address from "Place of Delivery", "Deliver To", "Delivery Address", "Ship To" sections
   - special_delivery_instructions (optional): Special delivery instructions, requirements, or constraints including:
     * Testing requirements before delivery
     * Staggered delivery schedules
     * Delivery method requirements
     * Acceptance criteria
     * Inspection requirements
     * Any special constraints or requirements
   - delivery_timeline (optional): COMPLETE delivery schedule requirements including:
     * "within X days" or "X days after contract award" or "X days ARO"
     * Delivery deadlines and dates
     * Required delivery date if specified
     * Staggered delivery schedules
     * Preferred delivery times
     * Extract the COMPLETE timeline phrase with full context

SEARCH STRATEGY - SEARCH THE ENTIRE DOCUMENT THOROUGHLY FOR ALL FIELDS:

CRITICAL: You MUST extract ALL available information for EACH CLIN. Do not leave fields as null if the information exists in the documents.

1. For CLIN identification: Search ENTIRE document systematically for ALL CLIN tables, line items, and numbered items. Look in ALL sections including amendments, attachments, schedules, and appendices.

2. For product_name: Extract from the CLIN description, product title, or SOW sections. If description mentions a product name, extract it as product_name.

3. For scope_of_work and service_requirements: Search ALL sections titled "Statement of Work", "SOW", "Performance Requirements", "Specifications", "Technical Requirements", "SECTION III", "SECTION IV", "SECTION VI", "Performance/Delivery Period", "SECTION II: Purpose", "SECTION III: Technical Requirements". Extract COMPLETE text from these sections including:
   - Purpose and background
   - Technical requirements and specifications
   - Performance requirements
   - Testing and acceptance criteria
   - Quality standards
   - Usage requirements
   If SOW applies to all CLINs, include it for each CLIN. Extract the FULL text, not summaries.

4. For delivery_address: Search ALL sections for "Place of Delivery", "Deliver To", "Delivery Address", "Ship To", "Destination", "Receiving Address", "SECTION VII". Extract complete delivery address including facility name, street address, city, state, ZIP code. If address is specified for a specific CLIN, associate it with that CLIN.

5. For special_delivery_instructions: Search for special delivery instructions, requirements, or constraints that apply to specific CLINs including testing requirements, delivery methods, acceptance criteria, inspection requirements.

6. For delivery_timeline: Search ALL sections for "Delivery", "Performance", "Schedule", "Timeline", "Performance/Delivery Period", "SECTION VII", phrases like "within X days", "X days after contract award", "X days ARO", "X days after receipt of order", "X days after receipt of contract award", "required delivery date". Extract COMPLETE timeline phrases with full context including days, dates, required delivery date, and conditions.

7. For drawing_number: Extract from:
   - Document filenames - parse drawing numbers by removing file extensions and keeping revision information
   - Document content references to "Drawing", "Drawing Number", "Attachment A", "Technical Drawing"
   - Extract drawing numbers with revision information when present

6. For Manufacturer/Part/Model: Search Bill of Materials (BOM), specification tables, Q&A documents, technical specifications, attachment lists, and any product detail sections.

IMPORTANT RULES:
- Extract ALL CLINs found - search systematically through the ENTIRE document, do not skip any CLINs
- Extract scope_of_work COMPLETELY - if found in ANY SOW section, include the FULL text even if it's very long
- Extract delivery_timeline COMPLETELY - include the complete phrase with all context including days, dates, and conditions
- Extract drawing_number from filenames AND document content - check both sources
- Extract product_name from description or SOW if clearly identifiable
- Match information across sections - if scope_of_work or delivery_timeline is in a different section than the CLIN table, still extract it and associate with the CLIN
- DO NOT leave fields as null if the information exists in the documents - search thoroughly before marking as null
- If a field is truly not found after exhaustive search, use null (not empty string or "N/A")
- Distinguish CLINs from BOM items - CLINs are top-level contract items, BOM items are components

RETURN FORMAT:
- Return ONLY valid JSON matching this exact schema:
{{
  "clins": [
    {{
      "item_number": "string (required)",
      "description": "string (required)",
      "quantity": "number or null",
      "unit": "string or null",
      "product_name": "string or null",
      "contract_type": "string or null",
      "manufacturer": "string or null",
      "part_number": "string or null",
      "model_number": "string or null",
      "drawing_number": "string or null",
      "scope_of_work": "string or null",
      "service_requirements": "string or null",
      "delivery_address": "string or null",
      "special_delivery_instructions": "string or null",
      "delivery_timeline": "string or null",
      "base_item_number": "string or null",
      "extended_price": "number or null",
      "source_document": "string or null"
    }}
  ]
}}
- Return ONLY the JSON object. No explanations, no markdown, no code blocks, no text before or after.
- If no CLINs found, return: {{"clins": []}}

DOCUMENT TEXT:
{text}"""
        
        # Try Claude first
        clins, deadlines = self._extract_with_llm(prompt, use_claude=True)
        
        # Try Groq if Claude failed
        if not clins and self.fallback_llm:
            logger.info("Claude failed, trying Groq...")
            clins, deadlines = self._extract_with_llm(prompt, use_claude=False)
        
        # Convert to dict format
        clins_dicts = self._convert_to_dicts(clins)
        deadlines_dicts = self._convert_deadlines_to_dicts(deadlines)
        
        # Check if 20% or more fields are null - if so, do a second pass to fill missing values
        if clins_dicts:
            missing_fields_count, total_fields_count = self._count_missing_fields(clins_dicts)
            missing_percentage = (missing_fields_count / total_fields_count * 100) if total_fields_count > 0 else 0
            if missing_percentage >= 20:
                logger.info(f"Found {missing_fields_count} missing fields ({missing_percentage:.1f}%) across {len(clins_dicts)} CLINs. Attempting second pass to fill missing values...")
                clins_dicts = self._fill_missing_fields(clins_dicts, text)
            elif missing_fields_count > 0:
                logger.debug(f"Found {missing_fields_count} missing fields ({missing_percentage:.1f}%) - below 20% threshold, skipping second pass")
        
        return (clins_dicts, deadlines_dicts)
    
    def extract_clins_batch(self, documents: List[Tuple[str, str]]) -> Tuple[List[Dict], List[Dict]]:
        """Extract CLINs from multiple documents - try all at once, else per document"""
        if not self.llm and not self.fallback_llm:
            logger.warning("No LLM available")
            return []
        
        if not documents:
            return []
        
        # Try all documents at once first - use raw text without cleaning
        all_text = []
        for doc_name, doc_text in documents:
            if doc_text and doc_text.strip():
                all_text.append(f"=== DOCUMENT: {doc_name} ===\n{doc_text}")
        
        if not all_text:
            return []
        
        combined_text = "\n\n".join(all_text)
        
        # Enhanced prompt for batch extraction
        prompt = f"""You are a government contracting analyst. Analyze these solicitation documents and extract ALL Contract Line Item Numbers (CLINs) and their complete details.

Each document is separated by "=== DOCUMENT: [name] ===".

CRITICAL: Extract EVERY CLIN found across ALL documents. Search SYSTEMATICALLY through EACH document. Look for:
- Tables with headers containing "CLIN", "Line Item", "Item Number", "Schedule Item", "Item No"
- Sections titled "Schedule of Supplies/Services", "Pricing Schedule", "CLIN Schedule", "SECTION B", "Schedule"
- Lists following numbering like "0001.", "0002.", "0003.", "a.", "b."
- Any clearly defined line items in pricing schedules, amendments, attachments across ALL documents
- Numbered items with quantities, descriptions, and pricing information
- DO NOT stop after finding one CLIN - continue searching EACH document until you have found ALL CLINs

For EACH CLIN found, extract ALL available information:

1. BASIC CLIN INFORMATION:
   - item_number (required): CLIN number exactly as written
   - description (required): Complete product/service description - extract the FULL text
   - quantity (optional): Quantity as integer or float
   - unit (optional): Unit of measure
   - contract_type (optional): Contract type
   - base_item_number (optional): Base item number or supplementary code
   - extended_price (optional): Extended price as float
   - source_document (optional): Document name where CLIN was found

2. PRODUCT/SERVICE DETAILS:
   - product_name (optional): Product name and description - extract product name if clearly distinguishable from description
   - description (required): Complete product/service description - extract the FULL text
   - manufacturer (optional): Manufacturer name - extract manufacturer name from BOM, specifications, or product descriptions
   - part_number (optional): Part number - extract manufacturer part number from BOM, specifications, or part number fields
   - model_number (optional): Model number - extract product model number from descriptions or specifications
   - quantity (optional): Quantity required - extract quantity as integer or float
   - drawing_number (optional): Technical drawing reference including revision (check filenames, document titles, attachment names)

3. SERVICE/SCOPE INFORMATION:
   - scope_of_work (optional): COMPLETE Statement of Work (SOW) text for this CLIN including:
     * Performance requirements and specifications
     * Testing and acceptance criteria
     * Usage requirements and operational context
     * Quality standards and compliance requirements
     * Any SOW sections describing work/services required
     * Extract the FULL text, not just a summary
   - service_requirements (optional): For service CLINs, extract specific service requirements including:
     * Service specifications and deliverables
     * Performance standards and metrics
     * Service level agreements (SLAs)
     * Any additional service-specific requirements

4. DELIVERY INFORMATION:
   - delivery_address (optional): Complete delivery address including:
     * Facility name (e.g., "Fort Worth, T.X. Facility (WCF)")
     * Street address (e.g., "9000 Blue Mound Road")
     * City, State, ZIP code
     * Extract complete address from "Place of Delivery", "Deliver To", "Delivery Address", "Ship To" sections
   - special_delivery_instructions (optional): Special delivery instructions, requirements, or constraints including:
     * Testing requirements before delivery
     * Staggered delivery schedules
     * Delivery method requirements
     * Acceptance criteria
     * Inspection requirements
     * Any special constraints or requirements
   - delivery_timeline (optional): COMPLETE delivery schedule requirements including:
     * "within X days" or "X days after contract award" or "X days ARO"
     * Delivery deadlines and dates
     * Required delivery date if specified
     * Staggered delivery schedules
     * Preferred delivery times
     * Extract the COMPLETE timeline phrase with full context

SEARCH STRATEGY - SEARCH ALL DOCUMENTS THOROUGHLY FOR ALL FIELDS:

CRITICAL: You MUST extract ALL available information for EACH CLIN from ALL documents. Do not leave fields as null if the information exists in any document.

1. For CLIN identification: Search EACH document systematically for ALL CLIN tables, line items, and numbered items. Look in ALL sections including amendments, attachments, schedules, and appendices across ALL documents.

2. For product_name: Extract from the CLIN description, product title, or SOW sections in ANY document. If description mentions a product name, extract it as product_name.

3. For scope_of_work: Search ALL documents for sections titled "Statement of Work", "SOW", "Performance Requirements", "Specifications", "Technical Requirements", "SECTION III", "SECTION IV", "SECTION VI", "Performance/Delivery Period", "SECTION II: Purpose", "SECTION III: Technical Requirements". Extract COMPLETE text from these sections including:
   - Purpose and background
   - Technical requirements and specifications
   - Performance requirements
   - Testing and acceptance criteria
   - Quality standards
   - Usage requirements
   If SOW applies to all CLINs, include it for each CLIN. Extract the FULL text, not summaries.

4. For delivery_timeline: Search ALL documents for "Delivery", "Performance", "Schedule", "Timeline", "Performance/Delivery Period", "SECTION VII", phrases like "within X days", "X days after contract award", "X days ARO", "X days after receipt of order", "X days after receipt of contract award". Extract COMPLETE timeline phrases with full context including days, dates, and conditions.

7. For drawing_number: Extract from:
   - Document filenames across ALL documents - parse drawing numbers by removing file extensions and keeping revision information
   - Document content references to "Drawing", "Drawing Number", "Attachment A", "Technical Drawing" in ANY document
   - Extract drawing numbers with revision information when present

8. For Manufacturer/Part/Model: Search ALL documents for Bill of Materials (BOM), specification tables, Q&A documents, technical specifications, attachment lists, and any product detail sections.

IMPORTANT RULES:
- Extract ALL CLINs from ALL documents - search systematically through EACH document, do not skip any CLINs
- Extract scope_of_work COMPLETELY - if found in ANY document's SOW sections, include the FULL text even if it's very long
- Extract delivery_timeline COMPLETELY - include the complete phrase with all context including days, dates, and conditions
- Extract drawing_number from filenames AND document content - check both sources across ALL documents
- Extract product_name from description or SOW if clearly identifiable
- Match information across documents - if scope_of_work or delivery_timeline is in a different document than the CLIN table, still extract it and associate with the CLIN
- DO NOT leave fields as null if the information exists in ANY document - search thoroughly across ALL documents before marking as null
- If a field is truly not found after exhaustive search across all documents, use null (not empty string or "N/A")
- Distinguish CLINs from BOM items - CLINs are top-level contract items, BOM items are components

RETURN FORMAT:
- Return ONLY valid JSON matching this exact schema:
{{
  "clins": [
    {{
      "item_number": "string (required)",
      "description": "string (required)",
      "quantity": "number or null",
      "unit": "string or null",
      "product_name": "string or null",
      "contract_type": "string or null",
      "manufacturer": "string or null",
      "part_number": "string or null",
      "model_number": "string or null",
      "drawing_number": "string or null",
      "scope_of_work": "string or null",
      "service_requirements": "string or null",
      "delivery_address": "string or null",
      "special_delivery_instructions": "string or null",
      "delivery_timeline": "string or null",
      "base_item_number": "string or null",
      "extended_price": "number or null",
      "source_document": "string or null"
    }}
  ]
}}
- Return ONLY the JSON object. No explanations, no markdown, no code blocks, no text before or after.
- If no CLINs found, return: {{"clins": []}}

DOCUMENTS:
{combined_text}"""
        
        # Log combined text info
        logger.info(f"Combining {len(documents)} documents into single request")
        logger.info(f"Total combined text length: {len(combined_text)} characters")
        for doc_name, _ in documents:
            logger.info(f"  - {doc_name}")
        
        # Try Claude first with all documents combined
        logger.info("Sending ALL documents combined in ONE request to Claude for CLIN and deadline extraction...")
        all_clins, all_deadlines = self._extract_with_llm(prompt, use_claude=True)
        
        # If failed, try Groq
        if not all_clins and self.fallback_llm:
            logger.info("Claude batch failed, trying Groq with ALL documents combined...")
            all_clins, all_deadlines = self._extract_with_llm(prompt, use_claude=False)
        
        # Log extraction results
        if all_clins:
            logger.info(f"Successfully extracted {len(all_clins)} CLINs from combined documents")
        else:
            logger.warning("No CLINs extracted from combined documents")
        
        if all_deadlines:
            logger.info(f"Successfully extracted {len(all_deadlines)} deadlines from combined documents")
        else:
            logger.info("No deadlines extracted from combined documents")
        
        # Convert to dicts
        clins_dicts = self._convert_to_dicts(all_clins)
        deadlines_dicts = self._convert_deadlines_to_dicts(all_deadlines)
        
        # Check if 20% or more fields are null - if so, do a second pass to fill missing values
        if clins_dicts:
            missing_fields_count, total_fields_count = self._count_missing_fields(clins_dicts)
            missing_percentage = (missing_fields_count / total_fields_count * 100) if total_fields_count > 0 else 0
            if missing_percentage >= 20:
                logger.info(f"Found {missing_fields_count} missing fields ({missing_percentage:.1f}%) across {len(clins_dicts)} CLINs. Attempting second pass to fill missing values...")
                clins_dicts = self._fill_missing_fields(clins_dicts, combined_text)
            elif missing_fields_count > 0:
                logger.debug(f"Found {missing_fields_count} missing fields ({missing_percentage:.1f}%) - below 20% threshold, skipping second pass")
        
        return clins_dicts
    
    def _count_missing_fields(self, clins: List[Dict]) -> tuple[int, int]:
        """Count how many important fields are missing across all CLINs
        Returns: (missing_count, total_fields_count)"""
        important_fields = ['product_name', 'manufacturer_name', 'part_number', 'model_number', 
                          'drawing_number', 'scope_of_work', 'service_requirements', 'delivery_address', 
                          'special_delivery_instructions', 'delivery_timeline']
        missing_count = 0
        total_fields_count = len(clins) * len(important_fields)
        for clin in clins:
            for field in important_fields:
                if not clin.get(field):
                    missing_count += 1
        return (missing_count, total_fields_count)
    
    def _fill_missing_fields(self, clins: List[Dict], document_text: str) -> List[Dict]:
        """Second pass: Ask AI to find and fill missing fields for existing CLINs"""
        if not self.llm and not self.fallback_llm:
            logger.warning("No LLM available for second pass")
            return clins
        
        # Create a summary of existing CLINs with missing fields
        clins_summary = []
        for clin in clins:
            clin_summary = {
                'item_number': clin.get('clin_number'),
                'description': clin.get('product_description', ''),
                'missing_fields': []
            }
            if not clin.get('product_name'):
                clin_summary['missing_fields'].append('product_name')
            if not clin.get('manufacturer_name'):
                clin_summary['missing_fields'].append('manufacturer')
            if not clin.get('part_number'):
                clin_summary['missing_fields'].append('part_number')
            if not clin.get('model_number'):
                clin_summary['missing_fields'].append('model_number')
            if not clin.get('drawing_number'):
                clin_summary['missing_fields'].append('drawing_number')
            if not clin.get('scope_of_work'):
                clin_summary['missing_fields'].append('scope_of_work')
            if not clin.get('service_requirements'):
                clin_summary['missing_fields'].append('service_requirements')
            if not clin.get('delivery_address'):
                clin_summary['missing_fields'].append('delivery_address')
            if not clin.get('special_delivery_instructions'):
                clin_summary['missing_fields'].append('special_delivery_instructions')
            if not clin.get('delivery_timeline'):
                clin_summary['missing_fields'].append('delivery_timeline')
            
            if clin_summary['missing_fields']:
                clins_summary.append(clin_summary)
        
        if not clins_summary:
            logger.info("No missing fields to fill")
            return clins
        
        # Create prompt for filling missing fields
        clins_json = json.dumps(clins_summary, indent=2)
        prompt = f"""You are a government contracting analyst. You have already extracted CLINs from these documents, but some fields are missing.

EXISTING CLINS WITH MISSING FIELDS:
{clins_json}

DOCUMENTS:
{document_text}

TASK: For EACH CLIN listed above, search the documents and fill in ONLY the missing fields. Do NOT change existing fields.

INSTRUCTIONS:
1. For each CLIN, search the documents for the missing fields listed
2. Extract ONLY the missing fields - do not modify existing data
3. For product_name: Extract from description or SOW sections if clearly identifiable
4. For manufacturer: Search BOM, specifications, or product descriptions
5. For part_number: Search BOM, part number fields, or product descriptions
6. For model_number: Search specifications or product descriptions
7. For drawing_number: Extract from filenames or document content references to "Drawing"
8. For scope_of_work: Search "Statement of Work", "SOW", "Performance Requirements", "Specifications", "Technical Requirements" sections - extract COMPLETE text
9. For service_requirements: For service CLINs, extract specific service requirements, SLAs, service deliverables, and performance standards
10. For delivery_address: Search "Place of Delivery", "Deliver To", "Delivery Address", "Ship To", "Destination" sections - extract complete address including facility name, street address, city, state, ZIP code
11. For special_delivery_instructions: Search for special delivery instructions, requirements, or constraints including testing requirements, delivery methods, acceptance criteria, inspection requirements
12. For delivery_timeline: Search "Delivery", "Performance", "Schedule", "Timeline" sections for phrases like "within X days", "X days after contract award", "required delivery date" - extract COMPLETE phrases including required delivery date

RETURN FORMAT:
Return ONLY valid JSON matching this exact schema:
{{
  "clins": [
    {{
      "item_number": "string (required - must match existing CLIN)",
      "product_name": "string or null",
      "manufacturer": "string or null",
      "part_number": "string or null",
      "model_number": "string or null",
      "drawing_number": "string or null",
      "scope_of_work": "string or null",
      "service_requirements": "string or null",
      "delivery_address": "string or null",
      "special_delivery_instructions": "string or null",
      "delivery_timeline": "string or null"
    }}
  ]
}}
- Return ONLY the JSON object. No explanations, no markdown, no code blocks.
- Include ALL CLINs from the list above, even if you cannot find missing fields (use null for those)
- Only fill fields that are listed as missing - do not include other fields"""
        
        try:
            # Try Claude first
            filled_clins = self._extract_with_llm(prompt, use_claude=True)
            
            # If failed, try Groq
            if not filled_clins and self.fallback_llm:
                logger.info("Claude second pass failed, trying Groq...")
                filled_clins = self._extract_with_llm(prompt, use_claude=False)
            
            if filled_clins:
                # Merge filled fields back into original CLINs
                filled_dicts = self._convert_to_dicts(filled_clins)
                clins_map = {clin['clin_number']: clin for clin in clins}
                
                for filled_clin in filled_dicts:
                    clin_number = filled_clin.get('clin_number')
                    if clin_number and clin_number in clins_map:
                        original_clin = clins_map[clin_number]
                        # Only update fields that were missing
                        if not original_clin.get('product_name') and filled_clin.get('product_name'):
                            original_clin['product_name'] = filled_clin['product_name']
                        # Handle both 'manufacturer' and 'manufacturer_name' keys
                        manufacturer_value = filled_clin.get('manufacturer_name') or filled_clin.get('manufacturer')
                        if not original_clin.get('manufacturer_name') and manufacturer_value:
                            original_clin['manufacturer_name'] = manufacturer_value
                        if not original_clin.get('part_number') and filled_clin.get('part_number'):
                            original_clin['part_number'] = filled_clin['part_number']
                        if not original_clin.get('model_number') and filled_clin.get('model_number'):
                            original_clin['model_number'] = filled_clin['model_number']
                        if not original_clin.get('drawing_number') and filled_clin.get('drawing_number'):
                            original_clin['drawing_number'] = filled_clin['drawing_number']
                        if not original_clin.get('scope_of_work') and filled_clin.get('scope_of_work'):
                            original_clin['scope_of_work'] = filled_clin['scope_of_work']
                        if not original_clin.get('service_requirements') and filled_clin.get('service_requirements'):
                            original_clin['service_requirements'] = filled_clin['service_requirements']
                        if not original_clin.get('delivery_address') and filled_clin.get('delivery_address'):
                            original_clin['delivery_address'] = filled_clin['delivery_address']
                            logger.info(f"Second pass filled delivery_address for CLIN {clin_number}: {filled_clin.get('delivery_address')[:100] if filled_clin.get('delivery_address') else 'None'}...")
                        if not original_clin.get('special_delivery_instructions') and filled_clin.get('special_delivery_instructions'):
                            original_clin['special_delivery_instructions'] = filled_clin['special_delivery_instructions']
                            logger.info(f"Second pass filled special_delivery_instructions for CLIN {clin_number}: {filled_clin.get('special_delivery_instructions')[:100] if filled_clin.get('special_delivery_instructions') else 'None'}...")
                        if not original_clin.get('delivery_timeline') and filled_clin.get('delivery_timeline'):
                            original_clin['delivery_timeline'] = filled_clin['delivery_timeline']
                
                logger.info(f"Second pass completed: filled missing fields for {len(filled_dicts)} CLINs")
                # Log what was actually filled
                for filled_clin in filled_dicts:
                    logger.debug(f"Second pass filled CLIN {filled_clin.get('clin_number')}: delivery_address={bool(filled_clin.get('delivery_address'))}, special_delivery_instructions={bool(filled_clin.get('special_delivery_instructions'))}")
            else:
                logger.warning("Second pass failed to extract missing fields")
        except Exception as e:
            logger.warning(f"Error in second pass to fill missing fields: {e}", exc_info=True)
        
        return clins
    
    def _is_cdrl_item(self, clin_dict: Dict) -> bool:
        """Check if a CLIN is a CDRL/documentation item that should be excluded"""
        description = (clin_dict.get('product_description') or '').upper()
        product_name = (clin_dict.get('product_name') or '').upper()
        source_doc = (clin_dict.get('source_document') or '').upper()
        contract_type = (clin_dict.get('contract_type') or '').upper()
        quantity = clin_dict.get('quantity')
        unit = (clin_dict.get('unit_of_measure') or '').upper()
        part_number = clin_dict.get('part_number')
        model_number = clin_dict.get('model_number')
        drawing_number = clin_dict.get('drawing_number')
        
        # Positive indicators that this is a REAL product/service CLIN
        has_product_indicators = (
            (quantity and quantity > 1) or  # Multiple units
            part_number or  # Has part number
            model_number or  # Has model number
            drawing_number or  # Has drawing number
            'NSN' in description or  # Has NSN reference
            unit in ['EA', 'EACH', 'SET', 'LOT', 'UNIT', 'PIECE']  # Real product units
        )
        
        # If it has strong product indicators, it's likely a real CLIN
        if has_product_indicators:
            return False
        
        # Specific CDRL item names (exact matches or very specific patterns)
        specific_cdrl_patterns = [
            'COUNTERFEIT PREVENTION PLAN',
            'QUALITY ASSURANCE PLAN',
            'TEST REPORT',
            'DATA REQUIREMENT',
            'CDRL A001',
            'CDRL A002',
            'CONTRACT DATA REQUIREMENT',
        ]
        
        text_to_check = f"{description} {product_name}"
        
        # Check for specific CDRL patterns
        for pattern in specific_cdrl_patterns:
            if pattern in text_to_check:
                # Double-check: if it has product indicators, don't filter
                if has_product_indicators:
                    return False
                return True
        
        # Check for "Not Separately Priced" + CDRL indicators
        if 'NOT SEPARATELY PRICED' in contract_type or 'NSP' in contract_type:
            if 'CDRL' in text_to_check or 'CDRL' in source_doc:
                # But allow if it has strong product indicators
                if has_product_indicators:
                    return False
                return True
        
        # Check source document - if it's clearly a CDRL document
        if 'CDRL' in source_doc or 'CPP' in source_doc:
            # But allow if it has strong product indicators
            if has_product_indicators:
                return False
            # If unit is "LO" (Line Item) and quantity is 1, and description contains CDRL keywords
            if unit == 'LO' and quantity == 1:
                if any(pattern in text_to_check for pattern in specific_cdrl_patterns):
                    return True
        
        return False
    
    def _convert_to_dicts(self, clins: List) -> List[Dict]:
        """Convert CLINItem objects or dicts to standard dict format for database storage"""
        result = []
        
        if not isinstance(clins, list):
            logger.warning(f"Expected list, got {type(clins)}")
            return result
        
        for idx, item in enumerate(clins):
            try:
                clin_dict = {}
                
                # Handle CLINItem object
                if isinstance(item, CLINItem):
                    clin_dict = {
                        'clin_number': str(item.item_number).strip() if item.item_number else None,
                        'product_description': str(item.description).strip() if item.description else None,
                        'quantity': float(item.quantity) if item.quantity is not None else None,
                        'unit_of_measure': str(item.unit).strip() if item.unit else None,
                        'product_name': str(item.product_name).strip() if item.product_name else None,
                        'contract_type': str(item.contract_type).strip() if item.contract_type else None,
                        'manufacturer_name': str(item.manufacturer).strip() if item.manufacturer else None,
                        'part_number': str(item.part_number).strip() if item.part_number else None,
                        'model_number': str(item.model_number).strip() if item.model_number else None,
                        'drawing_number': str(item.drawing_number).strip() if item.drawing_number else None,
                        'scope_of_work': str(item.scope_of_work).strip() if item.scope_of_work else None,
                        'service_requirements': str(item.service_requirements).strip() if hasattr(item, 'service_requirements') and item.service_requirements else None,
                        'delivery_address': str(item.delivery_address).strip() if hasattr(item, 'delivery_address') and item.delivery_address else None,
                        'special_delivery_instructions': str(item.special_delivery_instructions).strip() if hasattr(item, 'special_delivery_instructions') and item.special_delivery_instructions else None,
                        'delivery_timeline': str(item.delivery_timeline).strip() if item.delivery_timeline else None,
                        'base_item_number': str(item.base_item_number).strip() if item.base_item_number else None,
                        'extended_price': float(item.extended_price) if item.extended_price is not None else None,
                    }
                    # Preserve source_document if present
                    if hasattr(item, 'source_document') and item.source_document:
                        clin_dict['source_document'] = str(item.source_document).strip()
                # Handle dict
                elif isinstance(item, dict):
                    # Handle both 'item_number' and 'clin_number' keys
                    item_number = item.get('item_number') or item.get('clin_number', '')
                    
                    clin_dict = {
                        'clin_number': str(item_number).strip() if item_number else None,
                        'product_description': self._safe_str(item.get('description')),
                        'quantity': self._safe_float(item.get('quantity')),
                        'unit_of_measure': self._safe_str(item.get('unit')),
                        'product_name': self._safe_str(item.get('product_name')),
                        'contract_type': self._safe_str(item.get('contract_type')),
                        'manufacturer_name': self._safe_str(item.get('manufacturer')),
                        'part_number': self._safe_str(item.get('part_number')),
                        'model_number': self._safe_str(item.get('model_number')),
                        'drawing_number': self._safe_str(item.get('drawing_number')),
                        'scope_of_work': self._safe_str(item.get('scope_of_work')),
                        'service_requirements': self._safe_str(item.get('service_requirements')),
                        'delivery_address': self._safe_str(item.get('delivery_address')),
                        'special_delivery_instructions': self._safe_str(item.get('special_delivery_instructions')),
                        'delivery_timeline': self._safe_str(item.get('delivery_timeline')),
                        'base_item_number': self._safe_str(item.get('base_item_number')),
                        'extended_price': self._safe_float(item.get('extended_price')),
                    }
                    # Preserve source_document if present
                    if 'source_document' in item:
                        clin_dict['source_document'] = str(item['source_document']).strip()
                else:
                    logger.debug(f"Skipping item {idx}: unexpected type {type(item)}")
                    continue
                
                # Convert "<UNKNOWN>", empty strings, and None to None
                for key, value in list(clin_dict.items()):
                    if isinstance(value, str):
                        value_upper = value.strip().upper()
                        if value_upper == '<UNKNOWN>' or value_upper == 'NULL' or value_upper == 'N/A' or value_upper == '':
                            clin_dict[key] = None
                        else:
                            clin_dict[key] = value.strip()
                    elif value is None:
                        clin_dict[key] = None
                
                # Validate: must have CLIN number
                if not clin_dict.get('clin_number'):
                    logger.debug(f"Skipping CLIN {idx}: missing clin_number")
                    continue
                
                # Filter out CDRL items
                if self._is_cdrl_item(clin_dict):
                    logger.info(f"Filtering out CDRL item: {clin_dict.get('clin_number')} - {clin_dict.get('product_description')}")
                    continue
                
                # Ensure required fields are present (even if None)
                result.append(clin_dict)
                
            except Exception as e:
                logger.warning(f"Error converting CLIN item {idx}: {e}", exc_info=True)
                continue
        
        logger.info(f"Converted {len(result)} CLINs to dict format")
        return result
    
    def _convert_deadlines_to_dicts(self, deadlines: List) -> List[Dict]:
        """Convert DeadlineItem objects or dicts to standard dict format"""
        result = []
        
        if not isinstance(deadlines, list):
            logger.warning(f"Expected list for deadlines, got {type(deadlines)}")
            return result
        
        for deadline in deadlines:
            try:
                deadline_dict = {}
                
                if isinstance(deadline, DeadlineItem):
                    deadline_dict = {
                        'due_date': deadline.due_date,
                        'due_time': deadline.due_time,
                        'timezone': deadline.timezone,
                        'deadline_type': deadline.deadline_type,
                        'description': deadline.description,
                        'is_primary': deadline.is_primary,
                    }
                elif isinstance(deadline, dict):
                    deadline_dict = {
                        'due_date': deadline.get('due_date'),
                        'due_time': deadline.get('due_time'),
                        'timezone': deadline.get('timezone'),
                        'deadline_type': deadline.get('deadline_type', 'submission'),
                        'description': deadline.get('description'),
                        'is_primary': deadline.get('is_primary', False),
                    }
                else:
                    logger.debug(f"Skipping deadline: unexpected type {type(deadline)}")
                    continue
                
                # Parse date string to datetime
                if deadline_dict.get('due_date'):
                    try:
                        due_date_str = deadline_dict['due_date']
                        if deadline_dict.get('due_time'):
                            datetime_str = f"{due_date_str} {deadline_dict['due_time']}"
                        else:
                            datetime_str = due_date_str
                        deadline_dict['due_date'] = dateutil.parser.parse(datetime_str, fuzzy=True, default=datetime(1900, 1, 1))
                    except Exception as e:
                        logger.warning(f"Could not parse deadline date: {deadline_dict.get('due_date')}, error: {e}")
                        continue
                
                result.append(deadline_dict)
            except Exception as e:
                logger.warning(f"Error converting deadline: {e}", exc_info=True)
                continue
        
        logger.info(f"Converted {len(result)} deadlines to dict format")
        return result
    
    def _safe_str(self, value) -> Optional[str]:
        """Safely convert value to string, handling None and empty values"""
        if value is None:
            return None
        if isinstance(value, str):
            return value.strip() if value.strip() else None
        return str(value).strip() if str(value).strip() else None
    
    def _safe_float(self, value) -> Optional[float]:
        """Safely convert value to float, handling None and invalid values"""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            value = value.strip()
            if not value or value.upper() in ['<UNKNOWN>', 'NULL', 'N/A', '']:
                return None
            try:
                return float(value)
            except ValueError:
                return None
        return None
    
    def extract_deadlines_llm(self, text: str) -> List[Dict]:
        """Extract deadlines using LLM"""
        if not self.llm and not self.fallback_llm:
            logger.warning("No LLM available for deadline extraction")
            return []
        
        if not text or not text.strip():
            return []
        
        prompt = f"""You are a government contracting analyst. Extract ALL submission deadlines from this solicitation document.

CRITICAL: Extract EVERY deadline found in the document. Look for:
- Submission due dates and times
- Offer due dates
- Quote due dates
- Proposal due dates
- Question/inquiry deadlines
- Any other deadline mentioned

For EACH deadline found, extract:
1. due_date: The date in YYYY-MM-DD format
2. due_time: The time in HH:MM format (24-hour) if specified
3. timezone: Timezone abbreviation (EST, EDT, CST, CDT, MST, MDT, PST, PDT, UTC) if specified
4. deadline_type: Type of deadline:
   - "offers_due" for offer submission deadlines
   - "submission" for general submission deadlines
   - "questions_due" for question/inquiry deadlines
   - "other" for any other deadline type
5. description: Brief description of what the deadline is for
6. is_primary: true if this is the primary submission deadline, false otherwise

RETURN FORMAT:
Return ONLY valid JSON matching this exact schema:
{{
  "deadlines": [
    {{
      "due_date": "YYYY-MM-DD",
      "due_time": "HH:MM" or null,
      "timezone": "EST" or null,
      "deadline_type": "offers_due|submission|questions_due|other",
      "description": "string",
      "is_primary": true or false
    }}
  ]
}}
- Return ONLY the JSON object. No explanations, no markdown, no code blocks.
- Extract ALL deadlines found - do not skip any
- If timezone is not specified, use null
- If time is not specified, use null for due_time
- Mark the most important submission deadline as is_primary: true

DOCUMENT TEXT:
{text}"""
        
        try:
            # Try Claude first
            response = self._extract_with_llm(prompt, use_claude=True)
            
            if not response and self.fallback_llm:
                logger.info("Claude deadline extraction failed, trying Groq...")
                response = self._extract_with_llm(prompt, use_claude=False)
            
            if not response:
                return []
            
            # Parse response - handle both list and dict formats
            deadlines_list = []
            if isinstance(response, list):
                deadlines_list = response
            elif isinstance(response, dict):
                if 'deadlines' in response:
                    deadlines_list = response['deadlines'] if isinstance(response['deadlines'], list) else []
                elif 'due_date' in response:
                    deadlines_list = [response]
            
            # Convert to deadline dict format
            result = []
            for deadline in deadlines_list:
                if isinstance(deadline, dict):
                    try:
                        # Parse date
                        due_date_str = deadline.get('due_date')
                        if not due_date_str:
                            continue
                        
                        # Combine date and time if both present
                        if deadline.get('due_time'):
                            datetime_str = f"{due_date_str} {deadline['due_time']}"
                        else:
                            datetime_str = due_date_str
                        
                        parsed_date = dateutil.parser.parse(datetime_str, fuzzy=True, default=datetime(1900, 1, 1))
                        
                        result.append({
                            'due_date': parsed_date,
                            'due_time': deadline.get('due_time'),
                            'timezone': deadline.get('timezone'),
                            'deadline_type': deadline.get('deadline_type', 'submission'),
                            'description': deadline.get('description', ''),
                            'is_primary': deadline.get('is_primary', False),
                        })
                    except Exception as e:
                        logger.warning(f"Could not parse deadline: {deadline}, error: {e}")
                        continue
            
            logger.info(f"LLM extracted {len(result)} deadlines")
            return result
            
        except Exception as e:
            logger.error(f"LLM deadline extraction failed: {str(e)}", exc_info=True)
            return []