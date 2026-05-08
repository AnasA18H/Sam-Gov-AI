"""
CLIN Extraction Service - Simplified
Extracts Contract Line Item Numbers (CLINs) from government contract documents using LLM.
"""
# Conditional imports (V1BaseModel/V1Field, ChatAnthropic, ChatGroq) are used only when available
# pyright: reportUnboundVariable=none
import json
import logging
import re
from pathlib import Path
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


# Pydantic schema for LLM extraction (V1BaseModel/V1Field only defined when import succeeds)
if PYDANTIC_AVAILABLE:
    class CLINItem(V1BaseModel):  # type: ignore[misc, valid-type]
        class Config:
            protected_namespaces = ()
            
        item_number: str = V1Field(description="The CLIN number (e.g., '0001', '0002')")
        description: str = V1Field(description="Full product/service description")
        quantity: Optional[int] = V1Field(None, description="Quantity as integer")
        unit: Optional[str] = V1Field(None, description="Unit of measure (e.g., 'Each', 'Lot')")
        product_name: Optional[str] = V1Field(None, description="Short product name")
        contract_type: Optional[str] = V1Field(None, description="Contract type (e.g., 'Firm Fixed Price')")
        manufacturer: Optional[str] = V1Field(
            None,
            description="Manufacturer company name (e.g. BAE Systems, North Atlantic Industries Inc.). "
            "Use the organization/company name only—not CAGE codes alone. When the document lists "
            "'Company Name - CAGE code' or 'qualified source(s): Company A - CAGE X / Company B - CAGE Y', "
            "extract the company name(s). If the line item references only CAGE codes but the same document "
            "lists company names with those CAGE codes elsewhere, use the corresponding company name(s)."
        )
        part_number: Optional[str] = V1Field(
            None,
            description="Manufacturer/vendor part number(s) ONLY when explicitly stated in the document. "
            "Extract from 'Manufacturer Part Number', 'Part No', 'Part Number', 'P/N', or BOM/spec tables. "
            "Do not include CAGE codes. Multiple: comma-separated. If not found in the document, leave null."
        )
        model_number: Optional[str] = V1Field(
            None,
            description="Model number or OEM model number ONLY when explicitly stated. "
            "Extract from 'Model No', 'Model Number', 'M/N', 'OEM number'. If not found, leave null."
        )
        drawing_number: Optional[str] = V1Field(
            None,
            description="Drawing or technical document number when present. "
            "Extract from filenames, 'Drawing Number', 'DWG', attachment names, or CDRL. If not found, leave null."
        )
        scope_of_work: Optional[str] = V1Field(None, description="Complete scope of work text including all requirements")
        service_requirements: Optional[str] = V1Field(None, description="Service-specific requirements, SLAs, and service deliverables")
        delivery_address: Optional[str] = V1Field(None, description="Complete delivery address when present in document")
        special_delivery_instructions: Optional[str] = V1Field(None, description="Special delivery instructions when present")
        delivery_timeline: Optional[str] = V1Field(None, description="Complete delivery timeline when present")
        base_item_number: Optional[str] = V1Field(
            None,
            description="National Stock Number (NSN) ONLY when explicitly stated in the document. "
            "NSN format is typically XXXX-XX-XXX-XXXX (e.g. 5998-01-505-7062) or 13 digits. "
            "Extract from 'NSN:', 'National Stock Number', 'Base item number', 'Schedule item'. "
            "If the document does not contain an NSN for this line item, leave null. Do not guess or invent."
        )
        nsn: Optional[str] = V1Field(
            None,
            description="Alias for NSN (National Stock Number) if found; same as base_item_number. Use when document says 'NSN' explicitly. If not found, leave null."
        )
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
        
        # LLM client timeout (seconds): same for both so autofill treats them equally. Must be >= autofill wrapper timeout.
        _llm_client_timeout = 90
        # Initialize Claude (primary for autofill and CLIN extraction)
        if ANTHROPIC_AVAILABLE and ChatAnthropic is not None and settings.ANTHROPIC_API_KEY:
            try:
                from pydantic import SecretStr
                self.llm = ChatAnthropic(  # type: ignore[call-arg]
                    model_name=getattr(settings, "ANTHROPIC_MODEL", "claude-3-sonnet-20240229"),
                    temperature=0,
                    api_key=SecretStr(settings.ANTHROPIC_API_KEY),
                    timeout=_llm_client_timeout,
                    max_tokens=4096,
                    stop=None,
                )
                logger.info(f"Claude LLM initialized: model={getattr(settings, 'ANTHROPIC_MODEL', 'claude-3-sonnet-20240229')} timeout={_llm_client_timeout}s")
            except Exception as e:
                logger.warning(f"Failed to initialize Claude: {e}")
        
        # Initialize Groq fallback (same client timeout as Claude for fair comparison)
        if GROQ_AVAILABLE and settings.GROQ_API_KEY:
            try:
                from pydantic import SecretStr
                self.fallback_llm = ChatGroq(
                    model=getattr(settings, "GROQ_MODEL", "llama-3.3-70b-versatile"),
                    temperature=0,
                    api_key=SecretStr(settings.GROQ_API_KEY),
                    max_tokens=4096,
                )  # type: ignore[call-arg]
                logger.info(f"Groq LLM initialized: model={getattr(settings, 'GROQ_MODEL', 'llama-3.3-70b-versatile')} timeout={_llm_client_timeout}s")
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
            structured_llm = llm_to_use.with_structured_output(CLINExtractionResult, method="function_calling")  # type: ignore[arg-type]
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
                raw_content = response.content if hasattr(response, 'content') else str(response)
                # Normalize to str (LLM may return list of content blocks)
                if isinstance(raw_content, list):
                    content = "".join(
                        (b.get("text", "") if isinstance(b, dict) else str(b)) for b in raw_content
                    ).strip()
                else:
                    content = (raw_content if isinstance(raw_content, str) else str(raw_content)).strip()
                
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
                
                # Try multiple extraction strategies (content is already normalized to str and stripped)
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
                    return ([], [])
                
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
                # Try multiple fallback strategies to extract partial data
                clins_list = []
                deadlines_list = []
                
                try:
                    # Strategy 1: Try to repair common JSON errors (extracted_json/content set in try above)
                    repaired_json_str = (extracted_json if extracted_json is not None else content)
                    if not isinstance(repaired_json_str, str):
                        repaired_json_str = str(repaired_json_str)
                    repaired_json = repaired_json_str
                    
                    # Fix unclosed strings (common in truncated responses)
                    repaired_json = re.sub(r'("special_delivery_instructions":\s*"[^"]*?)([^"]*)$', r'\1"', repaired_json, flags=re.MULTILINE)
                    repaired_json = re.sub(r'("delivery_address":\s*"[^"]*?)([^"]*)$', r'\1"', repaired_json, flags=re.MULTILINE)
                    repaired_json = re.sub(r'("delivery_timeline":\s*"[^"]*?)([^"]*)$', r'\1"', repaired_json, flags=re.MULTILINE)
                    
                    # Try to close incomplete JSON structures
                    open_braces = repaired_json.count('{')
                    close_braces = repaired_json.count('}')
                    open_brackets = repaired_json.count('[')
                    close_brackets = repaired_json.count(']')
                    
                    # Add missing closing brackets/braces
                    repaired_json += ']' * (open_brackets - close_brackets)
                    repaired_json += '}' * (open_braces - close_braces)
                    
                    try:
                        parsed = json.loads(repaired_json)
                        if isinstance(parsed, dict):
                            clins_list = parsed.get('clins', []) if isinstance(parsed.get('clins'), list) else []
                            deadlines_list = parsed.get('deadlines', []) if isinstance(parsed.get('deadlines'), list) else []
                        logger.info(f"{llm_name} extracted {len(clins_list)} CLINs after JSON repair")
                    except:
                        pass
                except Exception as repair_err:
                    logger.debug(f"JSON repair failed: {repair_err}")
                
                # Strategy 2: Extract individual CLIN objects even if outer structure is broken
                if not clins_list:
                    try:
                        # Find all CLIN objects in the content (content is str from normalization above)
                        content_str: str = content if isinstance(content, str) else str(content)
                        clin_pattern = r'\{\s*"item_number"\s*:\s*"[^"]+".*?\}'
                        clin_matches = re.finditer(clin_pattern, content_str, re.DOTALL)
                        
                        for match in clin_matches:
                            clin_str = match.group(0)
                            # Try to close incomplete objects
                            open_braces = clin_str.count('{')
                            close_braces = clin_str.count('}')
                            clin_str += '}' * (open_braces - close_braces)
                            
                            try:
                                clin_obj = json.loads(clin_str)
                                if isinstance(clin_obj, dict) and 'item_number' in clin_obj:
                                    clins_list.append(clin_obj)
                            except:
                                # Try to extract fields individually with regex
                                item_num_match = re.search(r'"item_number"\s*:\s*"([^"]+)"', clin_str)
                                if item_num_match:
                                    clin_obj = {'item_number': item_num_match.group(1)}
                                    # Extract other fields
                                    for field in ['product_name', 'manufacturer', 'part_number', 'delivery_address', 'special_delivery_instructions', 'delivery_timeline']:
                                        field_match = re.search(f'"{field}"\\s*:\\s*"([^"]*)"', clin_str)
                                        if field_match:
                                            clin_obj[field] = field_match.group(1)
                                    clins_list.append(clin_obj)
                        
                        if clins_list:
                            logger.info(f"{llm_name} extracted {len(clins_list)} CLINs using individual object extraction")
                    except Exception as extract_err:
                        logger.debug(f"Individual CLIN extraction failed: {extract_err}")
                
                # Strategy 3: Try to find and extract clins array directly (original fallback)
                if not clins_list:
                    try:
                        content_str = content if isinstance(content, str) else str(content)  # str from normalization
                        clins_match = re.search(r'"clins"\s*:\s*\[(.*?)\]', content_str, re.DOTALL)
                        deadlines_match = re.search(r'"deadlines"\s*:\s*\[(.*?)\]', content_str, re.DOTALL)
                        
                        if clins_match:
                            array_str = '[' + clins_match.group(1) + ']'
                            try:
                                clins_list = json.loads(array_str)
                                logger.info(f"{llm_name} extracted {len(clins_list)} CLINs from clins array directly")
                            except:
                                pass
                        
                        if deadlines_match:
                            array_str = '[' + deadlines_match.group(1) + ']'
                            try:
                                deadlines_list = json.loads(array_str)
                                logger.info(f"{llm_name} extracted {len(deadlines_list)} deadlines from deadlines array directly")
                            except:
                                pass
                    except:
                        pass
                
                return (clins_list if isinstance(clins_list, list) else [], deadlines_list if isinstance(deadlines_list, list) else [])  # type: ignore[return-value]
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
            return ([], [])
        
        # Enhanced prompt for comprehensive CLIN extraction
        prompt = f"""You are a government contracting analyst. Analyze this solicitation document and extract ALL Contract Line Item Numbers (CLINs) and their complete details.

CRITICAL: Extract EVERY CLIN found in the document. Search SYSTEMATICALLY through the ENTIRE document. Look for:
- Tables with headers containing "CLIN", "Line Item", "Item Number", "Schedule Item", "Item No", "ITEM NUMBER", "B.3 PRICE/COST SCHEDULE"
- Sections titled "Schedule of Supplies/Services", "Pricing Schedule", "CLIN Schedule", "SECTION B", "Schedule"
- Lists following numbering like "0001.", "0002.", "0003.", "a.", "b." or 4-digit item numbers
- Any clearly defined line items in pricing schedules, amendments, attachments
- Numbered items with quantities, descriptions, and pricing information
- DO NOT stop after finding one CLIN - continue searching until you have found ALL CLINs. Read the ENTIRE price/schedule section to the end; later line items are often at the bottom of the table.
- INCLUDE warranty, training, and service line items when they appear in the schedule with an item number. Extract them as CLINs; do not skip them because they are services.

For EACH CLIN found, extract ALL available information:

1. BASIC CLIN INFORMATION:
   - item_number (required): CLIN number exactly as written
   - description (required): Complete product/service description - extract the FULL text
   - quantity (optional): Quantity as integer or float
   - unit (optional): Unit of measure
   - contract_type (optional): Contract type
   - base_item_number (optional): CRITICAL. NSN (National Stock Number) or base/schedule item ID. Extract when you see "NSN: XXXX-XX-XXX-XXXX" (e.g. 5998-01-505-7062), "National Stock Number", "Base item number", or schedule item identifier. Use exact format as written.
   - extended_price (optional): Extended price as float

2. PRODUCT/SERVICE DETAILS (part/model/NSN/drawing numbers are CRITICAL):
   - product_name (optional): Product name and description - extract product name if clearly distinguishable from description
   - description (required): Complete product/service description - extract the FULL text
   - manufacturer (optional): Manufacturer as COMPANY NAME only (e.g. "BAE Systems", "North Atlantic Industries Inc.").
     * CRITICAL: The buyer/contracting agency is NEVER the manufacturer. The manufacturer is the commercial company that makes the product. The issuing office  is the BUYER, not the manufacturer. If the only name you find in a source/manufacturer context is the buying agency, leave manufacturer null.
     * Search for "qualified source(s)", "restricted to", "approved source", "manufacturer's name", "CAGE" with company name. Use only commercial company names that supply or make the product.
     * When the document states "Company Name - CAGE 12345" or "restricted to qualified source(s): Company A - CAGE X / Company B - CAGE Y", use the company name(s). If multiple approved manufacturers, you may list them (e.g. "BAE Systems / North Atlantic Industries Inc.").
     * If the line item or part number references only CAGE codes (e.g. 0VGU1, 12436) but the same document lists company names with those CAGE codes elsewhere (e.g. on page 1 or in a schedule header), map CAGE to company name and use the company name(s). Do NOT output only CAGE codes as manufacturer unless no company name appears anywhere in the document.
   - part_number (optional): CRITICAL. Manufacturer/vendor part number(s) only—not CAGE codes. Look for "Manufacturer Part Number", "Part No", "Part Number", "P/N", or BOM/spec tables. If text says "Manufacturer Part Number 0VGU1 5388-F12 12436 6012315-001", extract part numbers like "5388-F12", "6012315-001" (exclude 0VGU1/12436 if those are CAGE codes). Multiple part numbers: comma-separated.
   - model_number (optional): Model number or OEM model. Look for "Model No", "Model Number", "M/N", "OEM number" in line item or specs. Use when distinct from part number.
   - quantity (optional): Quantity required - extract quantity as integer or float
   - drawing_number (optional): CRITICAL. Drawing/technical doc number with revision. Check document filenames, "Drawing Number", "DWG", "Drawing", attachment list, CDRL. Include revision if present (e.g. "DWG-12345 Rev A").

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

2. For product_name: Extract from the CLIN description, product title, or SOW sections. If description mentions a product name, extract it as product_name. When the schedule table has only a description column and no separate "name" or "title" column for a line, set product_name to that description (or its first phrase) so the CLIN has a display name—do not leave product_name null when the CLIN has a non-empty description.

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

7. For part_number, model_number, base_item_number, drawing_number (CRITICAL—extract every identifier found):
   - base_item_number: Search for "NSN:", "NSN ", "National Stock Number", "Base item number". NSN format is usually XXXX-XX-XXX-XXXX (e.g. 5998-01-505-7062). Extract exactly as written.
   - part_number: Search line item description, "Manufacturer Part Number", "Part No", "Part Number", "P/N", BOM, spec tables. Extract only actual part numbers (e.g. 5388-F12, 6012315-001); exclude 5-digit CAGE codes when they appear mixed in. If multiple part numbers, list all comma-separated.
   - model_number: Search "Model No", "Model Number", "M/N", "OEM number", product/spec text. Use when different from part number.
   - drawing_number: Search document filenames (strip extension, keep number/revision), "Drawing Number", "Drawing", "DWG", attachment names, CDRL. Include revision (e.g. Rev A) when present.

8. For Manufacturer: Search the ENTIRE document for manufacturer/source info: look for "qualified source(s)", "restricted to", "approved source", "manufacturer's name", "Commercial and Government Entity (CAGE)" followed by a company name, schedule headers, and Block 15/16 text. Use the company/organization name, not CAGE codes alone. If only CAGE codes appear in the line item, find where those CAGE codes are listed with company names in the same document and use those names. THE BUYER IS NEVER THE MANUFACTURER: do not put the contracting/issuing agency (e.g. Bureau of Engraving and Printing, DLA, DOD, GSA, or any government office) as manufacturer—leave manufacturer null if the only name in that context is the buyer.

CRITICAL - EXTRACT ONLY FROM DOCUMENT, NO FALSE VALUES:
- CAGE (in manufacturer/source text), part number, model number, and NSN (National Stock Number) are HIGH PRIORITY. Search the document thoroughly for each.
- ONLY add part_number, model_number, base_item_number (NSN), drawing_number, and manufacturer when you find them EXPLICITLY in the document. Do NOT guess, infer, or use placeholders like "N/A", "TBD", "Unknown", or "-". If not found, leave null. For manufacturer: use only commercial suppliers; never use the buying/contracting agency as manufacturer.
- NSN: Put in base_item_number (or nsn) ONLY when the document states "NSN:", "National Stock Number", or gives format XXXX-XX-XXX-XXXX. If no NSN in the document for this line item, leave null.
- Add CAGE, part #, model, and NSN when available in the document—only when available. No fabricated or default values.

IMPORTANT RULES:
- Extract ALL CLINs found - search systematically through the ENTIRE document, do not skip any CLINs. Pay special attention to the end of price/schedule tables and to warranty, training, or service line items that have item numbers.
- The buyer/contracting agency is NEVER the manufacturer. Manufacturer must be the commercial company that makes or supplies the product. Never put government agencies (e.g. Bureau of Engraving and Printing, DLA, DOD, GSA) as manufacturer—leave manufacturer null in that case.
- Extract part_number, model_number, base_item_number (NSN), and drawing_number ONLY when present in the document—critical for procurement when available
- Extract scope_of_work COMPLETELY - if found in ANY SOW section, include the FULL text even if it's very long
- Extract delivery_timeline COMPLETELY - include the complete phrase with all context including days, dates, and conditions
- Extract drawing_number from filenames AND document content when present
- Extract product_name from description or SOW if clearly identifiable
- Match information across sections - if scope_of_work or delivery_timeline is in a different section than the CLIN table, still extract it and associate with the CLIN
- Only populate a field when the information exists in the document. If not found after searching, use null (not empty string, "N/A", or "TBD")
- Distinguish CLINs from BOM items - CLINs are top-level contract items, BOM items are components

5. DEADLINES - EXTRACT ALL SUBMISSION AND QUESTION DEADLINES:
- Search the ENTIRE document (and any SAM.gov page text) for EVERY deadline mentioned. Do NOT return only one deadline.
- Look for: "Questions are due by...", "Quotes are due by...", "Offers due...", "Proposals due...", "Submission deadline...", "Response due...", date/time in description or headers.
- For EACH deadline found, add one entry to the "deadlines" array with:
  - due_date: YYYY-MM-DD
  - due_time: time in 24-hour HH:MM (e.g. 12:00 for noon, 14:00 for 2:00 PM)
  - timezone: EST, EDT, CST, CDT, MST, MDT, PST, PDT, or UTC when stated
  - deadline_type: use exactly one of:
    * "questions_due" for questions/inquiries/clarifications due (e.g. "Questions are due by January 12, 2026 at 12:00 PM")
    * "offers_due" for quotes/offers/proposals due (e.g. "Quotes are due by February 02, 2026 at 2:00 PM")
    * "submission" for general submission deadlines
    * "other" for any other deadline
  - description: brief label (e.g. "Questions due", "Quotes due")
  - is_primary: true ONLY for the main quote/offer/proposal submission deadline (the one that matters most for submitting the bid); false for questions_due and other earlier deadlines

RETURN FORMAT:
- Return ONLY valid JSON matching this exact schema (include BOTH "clins" AND "deadlines"):
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
      "base_item_number": "string or null (NSN when present)",
      "nsn": "string or null (National Stock Number; use when document states NSN)",
      "extended_price": "number or null",
      "source_document": "string or null"
    }}
  ],
  "deadlines": [
    {{
      "due_date": "YYYY-MM-DD",
      "due_time": "HH:MM or null (24-hour)",
      "timezone": "EST or null",
      "deadline_type": "questions_due|offers_due|submission|other",
      "description": "string or null",
      "is_primary": true or false
    }}
  ]
}}
- Return ONLY the JSON object. No explanations, no markdown, no code blocks, no text before or after.
- If no CLINs found, return: {{"clins": [], "deadlines": [...]}}
- Always extract and return ALL deadlines found (questions due, quotes due, etc.); "deadlines" must not be empty when the document mentions multiple due dates.

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
    
    def _extract_price_schedule_section(self, text: str, max_chars: int = 40000) -> Optional[str]:
        """
        Extract the targeted Section B / Price Schedule block based on standard government formats.
        Prioritizes SECTION B and identified pricing schedules.
        """
        if not text or len(text) < 200:
            return None
        
        text_lower = text.lower()
        
        # Start markers based on user requirements
        start_markers = [
            "section b - supplies or services and prices/costs",
            "section b - schedule of supplies/services",
            "section b - pricing schedule",
            "section b - contract line items",
            "section b - price/cost schedule",
            "b.3 price/cost schedule",
            "b.3 price schedule",
            "block 11 - schedule",
            "price/cost schedule",
            "pricing schedule",
            "schedule of supplies",
            "clin schedule",
            "item number",
            "material/nsn:",
            "pr:",
            "\nsection b\n",
        ]
        
        start_pos = -1
        matched_marker = None
        for m in start_markers:
            i = text_lower.find(m)
            if i != -1 and (start_pos == -1 or i < start_pos):
                start_pos = i
                matched_marker = m
        
        if start_pos == -1:
            # Final fallback: search for "SECTION B" alone if it's a standalone line
            standalone_b = re.search(r'\n\s*SECTION\s+B\s*\n', text, re.IGNORECASE)
            if standalone_b:
                start_pos = standalone_b.start()
                matched_marker = "SECTION B (standalone)"
            else:
                return None
        
        logger.info(f"Targeted Section B extraction starting at: '{matched_marker}'")
        
        # Segment starting from Section B
        segment = text[start_pos : start_pos + max_chars]
        segment_lower = segment.lower()
        
        # End markers for Section B (where Section C or other sections start)
        # In standard solicitations, Section B is followed by C, D, E, etc.
        end_markers = [
            "\nsection c",
            "\nsection d",
            "\nsection e",
            "\nsection f",
            "\nsection g",
            "grand total",
            "total price",
            "\nb.4 ",
            "b.4 delivery",
            "delivery schedule",
            "specifications/statement of work",
            "description/specifications",
            "end of section b",
        ]
        
        end_pos = len(segment)
        for m in end_markers:
            # We look for markers that appear AFTER the start marker in the original text
            j = segment_lower.find(m)
            # Skip the marker if it's too close to the start (might be part of the header)
            if j != -1 and j > 50 and j < end_pos:
                end_pos = j
        
        extracted = segment[:end_pos].strip()
        
        # If extraction is too small, it might have failed to find the end correctly, 
        # or Section B is indeed short.
        if len(extracted) < 100:
             # Try a larger segment if we hit an early end marker
             pass
             
        return extracted or None

    def extract_clins_batch(self, documents: List[Tuple[str, str]]) -> Tuple[List[Dict], List[Dict]]:
        """Extract CLINs from multiple documents - try all at once, else per document"""
        if not self.llm and not self.fallback_llm:
            logger.warning("No LLM available")
            return ([], [])
        
        if not documents:
            return ([], [])
        
        # Try all documents at once first - use raw text without cleaning
        all_text = []
        for doc_name, doc_text in documents:
            if doc_text and doc_text.strip():
                all_text.append(f"=== DOCUMENT: {doc_name} ===\n{doc_text}")
        
        if not all_text:
            return ([], [])
        
        combined_text = "\n\n".join(all_text)
        
        # Prepend the price/schedule section so line items at the end of the table are always in context
        schedule_section = self._extract_price_schedule_section(combined_text)
        
        # Detect document type for classification
        doc_type = "unknown"
        if documents:
            # Check the first document or the one with the schedule section
            first_doc_path = Path(documents[0][0])
            doc_type = self.text_extractor.classify_document_type(first_doc_path, documents[0][1])

        docs_for_prompt = combined_text
        if schedule_section:
            logger.info(f"Prepending targeted Section B context ({len(schedule_section)} chars). DocType: {doc_type}")
            docs_for_prompt = f"""[PRIORITY REFERENCE INFO: TARGETED SECTION B / PRICING SCHEDULE]
This section is extracted from the solicitation's primary pricing area (e.g. Section B). 
It contains the core CLIN data. You MUST extract EVERY line item from here.

--- SECTION B START ---
{schedule_section}
--- SECTION B END ---

[ADDITIONAL DOCUMENT CONTEXT]
The following is the full text of all documents for cross-referencing manufacturer info, SOW, and delivery details.
{combined_text}"""
        
        # Enhanced prompt for batch extraction
        prompt = f"""You are a government contracting analyst. Analyze these solicitation documents and extract ALL Contract Line Item Numbers (CLINs) and their complete details.

### THE GOLDEN RULE: WHERE TO FIND CLINS
CLINs are primarily located in **SECTION B**. Use this table to focus your search based on the document type:

| Document Type | Form | CLIN Location |
| :--- | :--- | :--- |
| RFP / IFB (SF33) | Standard | SECTION B - "Supplies or Services and Prices/Costs" |
| RFQ (SF1449) | Commercial | Section B - "Schedule of Supplies/Services" |
| RFQ (SF18) | Simplified | Block 11 - "Schedule" (continuation sheets) |
| VA Solicitation | VA-specific | SECTION B or Price/Cost Schedule |
| DLA Solicitation (DIBBS) | DLA | SECTION B with PR/PRLI/UI table |
| GSA Schedule | GSA | Price List or Attachment |

**CRITICAL HEADERS TO LOOK FOR:**
- SECTION B - SUPPLIES OR SERVICES AND PRICES/COSTS
- SECTION B - SCHEDULE OF SUPPLIES/SERVICES
- B.3 PRICE/COST SCHEDULE
- SECTION B - PRICING SCHEDULE
- SECTION B - CONTRACT LINE ITEMS

### WHERE CLINS ARE NEVER LOCATED (Ignore these for CLIN extraction):
- SECTION A (Cover Sheet)
- SECTION C (Statement of Work / Specifications)
- SECTION D through I (Packaging, Inspection, Delivery, Admin, Clauses)
- SECTION K, L, M (Provisions, Instructions, Evaluation)

CRITICAL: Extract EVERY CLIN found in the [PRIORITY REFERENCE INFO] section and cross-reference with ALL documents. Search SYSTEMATICALLY through EACH document. Look for:
- Tables with headers containing "CLIN", "Line Item", "Item Number", "Schedule Item", "Item No", "ITEM NUMBER", "B.3 PRICE/COST SCHEDULE"
- Lists following numbering like "0001.", "0002.", "0003.", "a.", "b." or 4-digit item numbers
- Any clearly defined line items in pricing schedules, amendments, attachments across ALL documents
- Numbered items with quantities, descriptions, and pricing information
- DO NOT stop after finding one CLIN - continue searching EACH document until you have found ALL CLINs. Read the ENTIRE price/schedule section to the end; later line items are often at the bottom of the table.
- INCLUDE warranty, training, and service line items when they appear in the schedule with an item number. Extract them as CLINs with their item_number, description, and quantity; do not skip them because they are services rather than products.

For EACH CLIN found, extract ALL available information:

1. BASIC CLIN INFORMATION:
   - item_number (required): CLIN number exactly as written
   - description (required): Complete product/service description - extract the FULL text
   - quantity (optional): Quantity as integer or float
   - unit (optional): Unit of measure
   - contract_type (optional): Contract type
   - base_item_number (optional): CRITICAL. NSN (National Stock Number) or base/schedule item ID. Extract "NSN: XXXX-XX-XXX-XXXX", "National Stock Number", "Base item number" from ANY document. Use exact format as written (e.g. 5998-01-505-7062).
   - extended_price (optional): Extended price as float
   - source_document (optional): Document name where CLIN was found

2. PRODUCT/SERVICE DETAILS (part/model/NSN/drawing numbers are CRITICAL—extract from any document):
   - product_name (optional): Product name and description - extract product name if clearly distinguishable from description
   - description (required): Complete product/service description - extract the FULL text
   - manufacturer (optional): Manufacturer as COMPANY NAME only (e.g. "BAE Systems", "North Atlantic Industries Inc.").
     * CRITICAL: The buyer/contracting agency is NEVER the manufacturer. The manufacturer is the commercial company that makes the product. The issuing office (e.g. "Bureau of Engraving and Printing", "DLA", "DOD", "GSA", any government agency or federal office) is the BUYER, not the manufacturer. If the only name you find in a source/manufacturer context is the buying agency, leave manufacturer null.
     * Search ALL documents for "qualified source(s)", "restricted to", "approved source", "manufacturer's name", "CAGE" with company name. Use only commercial company names that supply or make the product.
     * When any document states "Company Name - CAGE 12345" or "restricted to qualified source(s): Company A - CAGE X / Company B - CAGE Y", use the company name(s). If multiple approved manufacturers, you may list them (e.g. "BAE Systems / North Atlantic Industries Inc.").
     * If the line item or part number references only CAGE codes but another part of the same or another document lists company names with those CAGE codes, map CAGE to company name and use the company name(s). Do NOT output only CAGE codes as manufacturer unless no company name appears in any document.
   - part_number (optional): CRITICAL. Manufacturer/vendor part number(s) only—not CAGE codes. Search ALL docs for "Manufacturer Part Number", "Part No", "Part Number", "P/N", BOM/spec tables. If mixed with CAGE codes, extract only part numbers (e.g. 5388-F12, 6012315-001). Multiple: comma-separated.
   - model_number (optional): Model number or OEM model. Search "Model No", "Model Number", "M/N", "OEM number" in ANY document. Use when distinct from part number.
   - quantity (optional): Quantity required - extract quantity as integer or float
   - drawing_number (optional): CRITICAL. Drawing/technical doc number with revision. Search ALL document filenames, "Drawing Number", "DWG", "Drawing", attachment lists, CDRL. Include revision when present.

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

7. For part_number, model_number, base_item_number, drawing_number (CRITICAL—extract every identifier from ANY document):
   - base_item_number: Search ALL documents for "NSN:", "NSN ", "National Stock Number", "Base item number". NSN format XXXX-XX-XXX-XXXX. Extract exactly as written.
   - part_number: Search line item text, "Manufacturer Part Number", "Part No", "P/N", BOM, spec tables across ALL documents. Extract only part numbers; exclude 5-digit CAGE codes. Multiple part numbers: comma-separated.
   - model_number: Search "Model No", "Model Number", "M/N", "OEM number" in ANY document.
   - drawing_number: Search ALL document filenames (strip extension), "Drawing Number", "DWG", "Drawing", attachment names, CDRL. Include revision when present.

8. For Manufacturer: Search ALL documents for manufacturer/source info: look for "qualified source(s)", "restricted to", "approved source", "manufacturer's name", "Commercial and Government Entity (CAGE)" followed by a company name, schedule headers, and contract form blocks. Use the company/organization name, not CAGE codes alone. If only CAGE codes appear in the line item, find where those CAGE codes are listed with company names in the same or another document and use those names. THE BUYER IS NEVER THE MANUFACTURER: do not put the contracting/issuing agency (e.g. Bureau of Engraving and Printing, DLA, DOD, GSA, or any government office) as manufacturer—leave manufacturer null if the only name in that context is the buyer.

CRITICAL - EXTRACT ONLY FROM DOCUMENTS, NO FALSE VALUES:
- CAGE (in manufacturer/source text), part number, model number, and NSN (National Stock Number) are HIGH PRIORITY. Search ALL documents thoroughly for each.
- ONLY add part_number, model_number, base_item_number (NSN), drawing_number, and manufacturer when you find them EXPLICITLY in the documents. Do NOT guess, infer, or use placeholders like "N/A", "TBD", "Unknown", or "-". If not found, leave null. For manufacturer: use only commercial suppliers; never use the buying/contracting agency as manufacturer.
- NSN: Put in base_item_number (or nsn) ONLY when a document states "NSN:", "National Stock Number", or gives format XXXX-XX-XXX-XXXX. If no NSN in any document for this line item, leave null.
- Add CAGE, part #, model, and NSN when available in the documents—only when available. No fabricated or default values.

IMPORTANT RULES:
- Extract ALL CLINs from ALL documents - search systematically through EACH document, do not skip any CLINs. Pay special attention to the end of price/schedule tables and to warranty, training, or service line items that have item numbers.
- The buyer/contracting agency is NEVER the manufacturer. Manufacturer must be the commercial company that makes or supplies the product. Never put government agencies (e.g. Bureau of Engraving and Printing, DLA, DOD, GSA) as manufacturer—leave manufacturer null in that case.
- Extract part_number, model_number, base_item_number (NSN), and drawing_number ONLY when present in ANY document—critical for procurement when available
- Extract scope_of_work COMPLETELY - if found in ANY document's SOW sections, include the FULL text even if it's very long
- Extract delivery_timeline COMPLETELY - include the complete phrase with all context including days, dates, and conditions
- Extract drawing_number from filenames AND document content when present
- Extract product_name from description or SOW if clearly identifiable
- Match information across documents - if scope_of_work or delivery_timeline is in a different document than the CLIN table, still extract it and associate with the CLIN
- Only populate a field when the information exists in the documents. If not found after searching all documents, use null (not empty string, "N/A", or "TBD")
- Distinguish CLINs from BOM items - CLINs are top-level contract items, BOM items are components

5. DEADLINES - EXTRACT ALL SUBMISSION AND QUESTION DEADLINES FROM ALL DOCUMENTS:
- Search EVERY document (including "SAM.gov Opportunity Page" if present) for EVERY deadline mentioned. Do NOT return only one deadline.
- Look for: "Questions are due by...", "Quotes are due by...", "Offers due...", "Proposals due...", "Submission deadline...", "Response due...", date/time in description or headers.
- For EACH deadline found, add one entry to the "deadlines" array with:
  - due_date: YYYY-MM-DD
  - due_time: time in 24-hour HH:MM (e.g. 12:00 for noon, 14:00 for 2:00 PM)
  - timezone: EST, EDT, CST, CDT, MST, MDT, PST, PDT, or UTC when stated
  - deadline_type: use exactly one of:
    * "questions_due" for questions/inquiries/clarifications due (e.g. "Questions are due by January 12, 2026 at 12:00 PM")
    * "offers_due" for quotes/offers/proposals due (e.g. "Quotes are due by February 02, 2026 at 2:00 PM")
    * "submission" for general submission deadlines
    * "other" for any other deadline
  - description: brief label (e.g. "Questions due", "Quotes due")
  - is_primary: true ONLY for the main quote/offer/proposal submission deadline; false for questions_due and other earlier deadlines

RETURN FORMAT:
- Return ONLY valid JSON matching this exact schema (include BOTH "clins" AND "deadlines"):
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
      "base_item_number": "string or null (NSN when present)",
      "nsn": "string or null (National Stock Number; use when document states NSN)",
      "extended_price": "number or null",
      "source_document": "string or null"
    }}
  ],
  "deadlines": [
    {{
      "due_date": "YYYY-MM-DD",
      "due_time": "HH:MM or null (24-hour)",
      "timezone": "EST or null",
      "deadline_type": "questions_due|offers_due|submission|other",
      "description": "string or null",
      "is_primary": true or false
    }}
  ]
}}
- Return ONLY the JSON object. No explanations, no markdown, no code blocks, no text before or after.
- If no CLINs found, return: {{"clins": [], "deadlines": [...]}}
- Always extract and return ALL deadlines found (questions due, quotes due, etc.); "deadlines" must not be empty when the document mentions multiple due dates.

DOCUMENTS:
{docs_for_prompt}"""
        
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
        
        return (clins_dicts, deadlines_dicts)
    
    def _count_missing_fields(self, clins: List[Dict]) -> tuple[int, int]:
        """Count how many important fields are missing across all CLINs
        Returns: (missing_count, total_fields_count)"""
        important_fields = ['product_name', 'manufacturer_name', 'part_number', 'model_number', 
                          'base_item_number', 'drawing_number', 'scope_of_work', 'service_requirements', 'delivery_address', 
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
            if not clin.get('base_item_number'):
                clin_summary['missing_fields'].append('base_item_number')
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
4. For manufacturer: Search for "qualified source(s)", company name with CAGE, BOM, or specifications. The buyer/contracting agency is NEVER the manufacturer (e.g. Bureau of Engraving and Printing, DLA, DOD, GSA)—leave manufacturer null if the only name found is the buyer.
5. For part_number: Search "Manufacturer Part Number", "Part No", "P/N", BOM, line item description—extract part numbers only (not CAGE codes)
6. For model_number: Search "Model No", "Model Number", "M/N", "OEM number", specifications
7. For base_item_number: Search "NSN:", "NSN ", "National Stock Number", "Base item number"—NSN format XXXX-XX-XXX-XXXX
8. For drawing_number: Extract from filenames (strip extension), "Drawing Number", "DWG", "Drawing", attachment names
9. For scope_of_work: Search "Statement of Work", "SOW", "Performance Requirements", "Specifications", "Technical Requirements" sections - extract COMPLETE text
10. For service_requirements: For service CLINs, extract specific service requirements, SLAs, service deliverables, and performance standards
11. For delivery_address: Search "Place of Delivery", "Deliver To", "Delivery Address", "Ship To", "Destination" sections - extract complete address including facility name, street address, city, state, ZIP code
12. For special_delivery_instructions: Search for special delivery instructions, requirements, or constraints including testing requirements, delivery methods, acceptance criteria, inspection requirements
13. For delivery_timeline: Search "Delivery", "Performance", "Schedule", "Timeline" sections for phrases like "within X days", "X days after contract award", "required delivery date" - extract COMPLETE phrases including required delivery date

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
      "base_item_number": "string or null (NSN when present)",
      "nsn": "string or null (National Stock Number when present)",
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
            filled_clins, _ = self._extract_with_llm(prompt, use_claude=True)  # Ignore deadlines in second pass
            
            # If failed, try Groq
            if not filled_clins and self.fallback_llm:
                logger.info("Claude second pass failed, trying Groq...")
                filled_clins, _ = self._extract_with_llm(prompt, use_claude=False)  # Ignore deadlines in second pass
            
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
                        if not original_clin.get('base_item_number') and filled_clin.get('base_item_number'):
                            original_clin['base_item_number'] = filled_clin['base_item_number']
                        if not original_clin.get('scope_of_work') and filled_clin.get('scope_of_work'):
                            original_clin['scope_of_work'] = filled_clin['scope_of_work']
                        if not original_clin.get('service_requirements') and filled_clin.get('service_requirements'):
                            original_clin['service_requirements'] = filled_clin['service_requirements']
                        if not original_clin.get('delivery_address') and filled_clin.get('delivery_address'):
                            original_clin['delivery_address'] = filled_clin['delivery_address']
                            logger.info(f"Second pass filled delivery_address for CLIN {clin_number}: {(filled_clin.get('delivery_address') or '')[:100]}...")
                        if not original_clin.get('special_delivery_instructions') and filled_clin.get('special_delivery_instructions'):
                            original_clin['special_delivery_instructions'] = filled_clin['special_delivery_instructions']
                            logger.info(f"Second pass filled special_delivery_instructions for CLIN {clin_number}: {(filled_clin.get('special_delivery_instructions') or '')[:100]}...")
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
        base_item_number = clin_dict.get('base_item_number')
        
        # Positive indicators that this is a REAL product/service CLIN
        has_product_indicators = (
            (quantity and quantity > 1) or  # Multiple units
            part_number or  # Has part number
            model_number or  # Has model number
            drawing_number or  # Has drawing number
            base_item_number or  # Has NSN/base item
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
                        'base_item_number': str(item.base_item_number or getattr(item, 'nsn', None) or '').strip() or None,
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
                        'manufacturer_name': self._safe_str(item.get('manufacturer_name') or item.get('manufacturer')),
                        'part_number': self._safe_str(item.get('part_number')),
                        'model_number': self._safe_str(item.get('model_number')),
                        'drawing_number': self._safe_str(item.get('drawing_number')),
                        'scope_of_work': self._safe_str(item.get('scope_of_work')),
                        'service_requirements': self._safe_str(item.get('service_requirements')),
                        'delivery_address': self._safe_str(item.get('delivery_address')),
                        'special_delivery_instructions': self._safe_str(item.get('special_delivery_instructions')),
                        'delivery_timeline': self._safe_str(item.get('delivery_timeline')),
                        'base_item_number': self._safe_str(item.get('base_item_number') or item.get('nsn')),
                        'extended_price': self._safe_float(item.get('extended_price')),
                    }
                    # Preserve source_document if present
                    if 'source_document' in item:
                        clin_dict['source_document'] = str(item['source_document']).strip()
                else:
                    logger.debug(f"Skipping item {idx}: unexpected type {type(item)}")
                    continue
                
                # Convert placeholders and empty strings to None (no false values)
                _placeholders = frozenset({'', '<UNKNOWN>', 'NULL', 'N/A', 'TBD', 'UNKNOWN', 'NONE', '-', '--', 'T.B.D.'})
                for key, value in list(clin_dict.items()):
                    if isinstance(value, str):
                        value_stripped = value.strip()
                        if value_stripped.upper() in _placeholders or not value_stripped:
                            clin_dict[key] = None
                        else:
                            clin_dict[key] = value_stripped
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
    
    @staticmethod
    def _normalize_due_time(due_time: Optional[str]) -> Optional[str]:
        """Normalize due_time to 24-hour HH:MM for consistent dedup and storage. Returns None if empty or unparseable."""
        if not due_time or not isinstance(due_time, str):
            return None
        s = due_time.strip()
        if not s:
            return None
        # Already HH:MM or HH:MM:SS 24h
        match = re.match(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?\s*$", s)
        if match:
            h, m = int(match.group(1)), int(match.group(2))
            if 0 <= h <= 23 and 0 <= m <= 59:
                return f"{h:02d}:{m:02d}"
        # 12-hour with AM/PM
        match = re.match(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(AM|PM|am|pm)?\s*$", s, re.IGNORECASE)
        if match:
            h, m = int(match.group(1)), int(match.group(2))
            ampm = (match.group(4) or "").upper()
            if ampm == "PM" and h != 12:
                h += 12
            elif ampm == "AM" and h == 12:
                h = 0
            if 0 <= h <= 23 and 0 <= m <= 59:
                return f"{h:02d}:{m:02d}"
        try:
            dt = dateutil.parser.parse(f"1970-01-01 {s}", fuzzy=True)
            return dt.strftime("%H:%M")
        except Exception:
            return None

    def _convert_deadlines_to_dicts(self, deadlines: List) -> List[Dict]:
        """Convert DeadlineItem objects or dicts to standard dict format. Normalizes due_time to 24h HH:MM."""
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
                
                # Normalize due_time to 24h HH:MM for consistent dedup and DB storage
                raw_time = deadline_dict.get('due_time')
                deadline_dict['due_time'] = self._normalize_due_time(raw_time) if raw_time else None
                if raw_time and not deadline_dict['due_time']:
                    deadline_dict['due_time'] = str(raw_time).strip() or None  # keep original if unparseable
                
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
                    deadlines_list = response.get('deadlines', []) if isinstance(response.get('deadlines'), list) else []
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
                        due_time = deadline.get('due_time')
                        if due_time:
                            datetime_str = f"{due_date_str} {due_time}"
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

    def extract_rfp_summary_llm(self, combined_text: str) -> Optional[Dict]:
        """
        Extract RFP/solicitation summary (SF 1449 A–M style) for form filling and review.
        Returns a single JSON object with cover, pricing, delivery, SOW, Section L/M, etc.
        """
        if not self.llm and not self.fallback_llm:
            logger.warning("No LLM available for RFP summary extraction")
            return None
        if not combined_text or not combined_text.strip():
            return None
        prompt = """You are a government contracting analyst. Extract key RFP/solicitation information from the documents below (SF 1449 / solicitation elements A through M). Use ONLY information explicitly stated. Do not invent or guess. Use null when not found.

Output a single JSON object with these keys (all optional): cover_page (object: solicitation_number, offer_due_date, naics_codes, set_aside, contract_type), pricing_clins (object: structure_note, unit_price_required, total_required), delivery_schedule (object: period_of_performance_start, period_of_performance_end, ship_to_address, cor_poc with name/phone/email), statement_of_work (object: summary, background, clearances_required, staffing_resume_requirements), sca_wage_determination (object: mentioned, labor_categories_note), reps_and_certs (object: complete_in_sam, complete_rfp_specific_in_solicitation, note), section_l_instructions_to_offerors (object: technical_approach_required, past_performance_required, pricing_required, other_requirements), section_m_evaluation (object: evaluation_type "LPTA" or "best_value" or "other", description, weights_note).

CRITICAL: Respond with nothing but the JSON object. No markdown, no code block, no introductory text. Start your response with { and end with }.

DOCUMENTS:
"""
        prompt += combined_text[:120000]
        if len(combined_text) > 120000:
            prompt += "\n\n[Document text truncated for length.]"
        raw = ""
        try:
            llm_to_use = self.llm or self.fallback_llm
            if not llm_to_use:
                return None
            response = llm_to_use.invoke(prompt)
            raw = response.content if hasattr(response, "content") else str(response)
            # Normalize content (AIMessage can have list of blocks with "text" or "content" key)
            if isinstance(raw, list):
                parts = []
                for b in raw:
                    if isinstance(b, dict):
                        parts.append(b.get("text") or b.get("content") or "")
                    else:
                        parts.append(str(b))
                raw = "".join(parts).strip()
            else:
                raw = (raw if isinstance(raw, str) else str(raw)).strip()
            if not raw:
                logger.warning("RFP summary extraction: LLM returned empty content")
                return None
            # Strip markdown code block if present
            if raw.startswith("```"):
                raw = re.sub(r"^```(?:json)?\s*", "", raw)
                raw = re.sub(r"\s*```\s*$", "", raw)
                raw = raw.strip()
            # If still no JSON start, try to extract first {...} object
            if not raw.startswith("{"):
                match = re.search(r"\{[\s\S]*\}", raw)
                if match:
                    raw = match.group(0)
            data = json.loads(raw)
            if isinstance(data, dict):
                logger.info("RFP summary extraction succeeded")
                return data
            return None
        except json.JSONDecodeError as e:
            logger.warning("RFP summary JSON parse failed: %s (content preview: %s)", e, (raw[:500] if raw else "empty"))
            return None
        except Exception as e:
            logger.warning("RFP summary extraction failed: %s", e)
            return None