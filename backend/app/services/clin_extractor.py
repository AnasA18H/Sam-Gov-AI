"""
CLIN Extraction Service - Simplified
Extracts Contract Line Item Numbers (CLINs) from government contract documents using LLM.
"""
# Conditional imports (V1BaseModel/V1Field, ChatAnthropic, ChatGroq) are used only when available
# pyright: reportUnboundVariable=none
import json
import logging
import re
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
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
    LARGE_BATCH_THRESHOLD_CHARS = 120000
    CHUNK_TARGET_CHARS = 45000
    CHUNK_OVERLAP_CHARS = 2000
    
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
                    model_kwargs={"max_tokens": 4096},
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
                    timeout=_llm_client_timeout,
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
    
    def extract_clins(
        self,
        text: str,
        file_path: Optional[str] = None,
        run_missing_fields_second_pass: bool = True,
    ) -> Tuple[List[Dict], List[Dict]]:
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
        
        # Optional second pass to fill missing fields.
        if clins_dicts and run_missing_fields_second_pass:
            missing_fields_count, total_fields_count = self._count_missing_fields(clins_dicts)
            missing_percentage = (missing_fields_count / total_fields_count * 100) if total_fields_count > 0 else 0
            if missing_percentage >= 20:
                logger.info(f"Found {missing_fields_count} missing fields ({missing_percentage:.1f}%) across {len(clins_dicts)} CLINs. Attempting second pass to fill missing values...")
                clins_dicts = self._fill_missing_fields(clins_dicts, text)
            elif missing_fields_count > 0:
                logger.debug(f"Found {missing_fields_count} missing fields ({missing_percentage:.1f}%) - below 20% threshold, skipping second pass")
        elif clins_dicts:
            logger.info("Skipping per-chunk missing-fields second pass (chunk mode)")
        
        return (clins_dicts, deadlines_dicts)
    
    def _extract_price_schedule_section(self, text: str, max_chars: int = 35000) -> Optional[str]:
        """Extract the price/CLIN schedule block so line items at the end of the table are never truncated.
        Returns the section from B.3/ITEM NUMBER through GRAND TOTAL or B.4, or None if not found."""
        if not text or len(text) < 200:
            return None
        text_lower = text.lower()
        start_markers = [
            "b.3 price",
            "price/cost schedule",
            "item number",
            "schedule of supplies",
            "clin schedule",
            "pricing schedule",
        ]
        start_pos = -1
        for m in start_markers:
            i = text_lower.find(m)
            if i != -1 and (start_pos == -1 or i < start_pos):
                start_pos = i
        if start_pos == -1:
            return None
        # End at GRAND TOTAL, B.4, or after max_chars
        segment = text[start_pos : start_pos + max_chars]
        end_markers = ["grand total", "\nb.4 ", "section b.4", "b.4 delivery", "delivery schedule"]
        end_pos = len(segment)
        for m in end_markers:
            j = segment.lower().find(m)
            if j != -1 and j < end_pos:
                end_pos = j
        return segment[:end_pos].strip() or None

    def _fit_text_for_budget(self, text: str, budget: int) -> str:
        """
        Fit text into a character budget while preserving both beginning and end,
        because CLIN tables often continue near the end of documents.
        """
        if not text or budget <= 0:
            return ""
        if len(text) <= budget:
            return text
        if budget < 800:
            return text[:budget]
        head = int(budget * 0.55)
        tail = budget - head - 40
        return f"{text[:head]}\n\n...[TRUNCATED]...\n\n{text[-max(0, tail):]}"

    def _build_docs_text_for_budget(
        self,
        documents: List[Tuple[str, str]],
        max_total_chars: int,
        prepend_schedule_max_chars: int,
    ) -> Tuple[str, int]:
        """
        Build prompt document text under a total character budget.
        Returns (docs_for_prompt, raw_combined_chars_before_budget).
        """
        all_text = []
        for doc_name, doc_text in documents:
            if doc_text and doc_text.strip():
                all_text.append(f"=== DOCUMENT: {doc_name} ===\n{doc_text}")
        combined_text = "\n\n".join(all_text)
        if not combined_text:
            return "", 0

        schedule_section = self._extract_price_schedule_section(combined_text, max_chars=prepend_schedule_max_chars)
        docs_for_prompt = combined_text
        if schedule_section:
            docs_for_prompt = f"""PRICE/COST SCHEDULE SECTION BELOW — You MUST extract EVERY line item from this section, including all items at the END of the table. Do not stop early.

---
{schedule_section}
---

FULL DOCUMENTS (for additional context and fields):
{combined_text}"""

        fitted = self._fit_text_for_budget(docs_for_prompt, max_total_chars)
        return fitted, len(combined_text)

    def _split_text_into_chunks(self, text: str, target_chars: int, overlap_chars: int) -> List[str]:
        """Split large text into overlapping chunks."""
        if not text:
            return []
        if len(text) <= target_chars:
            return [text]
        chunks: List[str] = []
        start = 0
        n = len(text)
        while start < n:
            end = min(n, start + target_chars)
            # Try to end near a paragraph boundary for cleaner chunks
            if end < n:
                boundary = text.rfind("\n\n", start + int(target_chars * 0.6), end)
                if boundary != -1:
                    end = boundary + 2
            chunk = text[start:end]
            if chunk.strip():
                chunks.append(chunk)
            if end >= n:
                break
            start = max(0, end - overlap_chars)
        return chunks

    def _merge_and_dedupe_clins(self, clins: List[Dict]) -> List[Dict]:
        """Merge duplicate CLIN rows by (clin_number + part/base item), preferring richer records."""
        def _norm(v: Optional[str]) -> str:
            return (v or "").strip().lower()
        def _score(c: Dict) -> int:
            important = [
                'product_description', 'quantity', 'unit_of_measure', 'product_name',
                'manufacturer_name', 'part_number', 'model_number', 'drawing_number',
                'base_item_number', 'scope_of_work', 'service_requirements',
                'delivery_address', 'special_delivery_instructions', 'delivery_timeline',
            ]
            return sum(1 for k in important if c.get(k))

        merged: Dict[Tuple[str, str, str], Dict] = {}
        for c in clins:
            clin_no = _norm(c.get('clin_number'))
            part = _norm(c.get('part_number'))
            base = _norm(c.get('base_item_number'))
            key = (clin_no, part, base)
            if key not in merged:
                merged[key] = c
                continue
            existing = merged[key]
            # Keep richer row; fill blanks from the other row
            primary, secondary = (existing, c) if _score(existing) >= _score(c) else (c, existing)
            out = dict(primary)
            for k, v in secondary.items():
                if (out.get(k) is None or out.get(k) == "") and v not in (None, ""):
                    out[k] = v
            merged[key] = out
        return list(merged.values())

    def _merge_and_dedupe_deadlines(self, deadlines: List[Dict]) -> List[Dict]:
        """Dedupe deadlines and drop stale/noisy dates far outside current solicitation window."""
        cleaned: List[Dict] = []
        for d in deadlines:
            if not isinstance(d, dict):
                continue
            # Must have a parseable due_date
            due_dt = d.get('due_date')
            if not isinstance(due_dt, datetime):
                continue
            # Normalize blank timezone to None to avoid duplicate rows with "" vs null
            tz = d.get('timezone')
            if isinstance(tz, str):
                tz = tz.strip().upper() or None
            d = dict(d)
            d['timezone'] = tz
            cleaned.append(d)

        # Remove stale deadlines: keep dates within ~13 months before latest due date.
        # This filters legacy dates from old amendments/templates.
        if cleaned:
            max_due = max(d['due_date'] for d in cleaned if isinstance(d.get('due_date'), datetime))
            floor = max_due - timedelta(days=400)
            cleaned = [d for d in cleaned if isinstance(d.get('due_date'), datetime) and d['due_date'] >= floor]

        seen = set()
        out: List[Dict] = []
        for d in cleaned:
            due_date = str(d.get('due_date') or '')
            due_time = str(d.get('due_time') or '')
            dtype = str(d.get('deadline_type') or '')
            desc = str(d.get('description') or '')
            key = (due_date, due_time, str(d.get('timezone') or ''), dtype, desc[:80])
            if key in seen:
                continue
            seen.add(key)
            out.append(d)
        return out

    def _reconcile_merged_clins_llm(self, clins: List[Dict]) -> List[Dict]:
        """
        Final small LLM pass over merged JSON only to normalize/fill obvious missing values.
        Safe fallback: return original merged list on any parse/model issue.
        """
        llm_to_use = self.llm or self.fallback_llm
        if not llm_to_use or not clins:
            return clins
        try:
            payload = json.dumps(clins, default=str)
            payload = self._fit_text_for_budget(payload, 45000)
            prompt = f"""Normalize and lightly reconcile these merged CLIN JSON objects.

Rules:
- Output valid JSON array only.
- Keep one object per CLIN line item (do not invent new CLINs).
- Do not delete non-empty fields.
- If two synonymous fields exist, keep canonical keys already present.
- If obvious normalization is needed (spacing/case/empty placeholders), normalize it.
- Do not hallucinate values.

CLINS JSON:
{payload}
"""
            def _parse_llm_json(raw_msg) -> Optional[List[Dict]]:
                raw_local = raw_msg.content if hasattr(raw_msg, "content") else str(raw_msg)
                if isinstance(raw_local, list):
                    raw_local = "".join((b.get("text", "") if isinstance(b, dict) else str(b)) for b in raw_local)
                txt_local = (raw_local if isinstance(raw_local, str) else str(raw_local)).strip()
                if txt_local.startswith("```"):
                    txt_local = re.sub(r"^```(?:json)?\s*", "", txt_local)
                    txt_local = re.sub(r"\s*```\s*$", "", txt_local)
                # Direct parse: array or object with clins key
                try:
                    parsed_local = json.loads(txt_local)
                    if isinstance(parsed_local, list):
                        return [p for p in parsed_local if isinstance(p, dict)]
                    if isinstance(parsed_local, dict) and isinstance(parsed_local.get("clins"), list):
                        return [p for p in parsed_local["clins"] if isinstance(p, dict)]
                except Exception:
                    pass
                # Fallback: extract first JSON array block
                array_match = re.search(r"\[[\s\S]*\]", txt_local)
                if array_match:
                    try:
                        parsed_arr = json.loads(array_match.group(0))
                        if isinstance(parsed_arr, list):
                            return [p for p in parsed_arr if isinstance(p, dict)]
                    except Exception:
                        pass
                return None

            parsed = _parse_llm_json(llm_to_use.invoke(prompt))
            if parsed:
                return parsed

            retry_prompt = prompt + "\n\nIMPORTANT: Return JSON ONLY. Start with '[' and end with ']'. No prose."
            parsed_retry = _parse_llm_json(llm_to_use.invoke(retry_prompt))
            if parsed_retry:
                return parsed_retry
            logger.warning("CLIN reconcile pass returned non-JSON; using merged result")
            return clins
        except Exception as e:
            logger.warning("CLIN reconcile pass failed, using merged result: %s", e)
            return clins

    def _is_clause_or_form_noise(self, clin_dict: Dict) -> bool:
        """Detect non-pricing/legal clause items that should not be treated as true CLIN rows."""
        text = f"{clin_dict.get('product_description') or ''} {clin_dict.get('product_name') or ''}".upper()
        has_strong_pricing_or_item_signal = any([
            clin_dict.get('quantity') not in (None, 0),
            bool(clin_dict.get('unit_of_measure')),
            clin_dict.get('extended_price') not in (None, 0),
            bool(clin_dict.get('part_number')),
            bool(clin_dict.get('model_number')),
            bool(clin_dict.get('base_item_number')),
            bool(clin_dict.get('drawing_number')),
            bool(clin_dict.get('delivery_timeline')),
            bool(clin_dict.get('delivery_address')),
            bool(clin_dict.get('scope_of_work')),
            bool(clin_dict.get('service_requirements')),
            "NSN" in text,
        ])
        # If row has actual pricing/item signals, keep it.
        if has_strong_pricing_or_item_signal:
            return False

        clause_markers = [
            "CERTIFICATION", "REPRESENTATION", "PROVISION", "CLAUSE", "FAR ",
            "DFARS", "STANDARD FORM", "CHECKLIST", "MADURO REGIME",
            "ARMS CONTROL", "COMMERCIAL DERIVATIVE MILITARY ARTICLE",
        ]
        return any(m in text for m in clause_markers)

    def _filter_noise_clins(self, clins: List[Dict]) -> List[Dict]:
        """Remove obvious clause/form noise rows before final fill."""
        filtered: List[Dict] = []
        dropped = 0
        for c in clins:
            if not isinstance(c, dict):
                continue
            if self._is_cdrl_item(c) or self._is_clause_or_form_noise(c):
                dropped += 1
                continue
            filtered.append(c)
        if dropped:
            logger.info("Filtered %s noisy CLIN rows before final fill.", dropped)
        return filtered

    def _extract_clins_batch_chunked(self, documents: List[Tuple[str, str]], combined_text: str) -> Tuple[List[Dict], List[Dict]]:
        """Large-data path: chunk extraction, merge/dedupe, final small reconcile pass."""
        logger.info(
            "Large batch detected (%s chars > %s). Using chunked extraction path.",
            len(combined_text), self.LARGE_BATCH_THRESHOLD_CHARS
        )
        chunked_docs: List[Tuple[str, str]] = []
        for doc_name, doc_text in documents:
            if not doc_text or not doc_text.strip():
                continue
            chunks = self._split_text_into_chunks(
                doc_text,
                target_chars=self.CHUNK_TARGET_CHARS,
                overlap_chars=self.CHUNK_OVERLAP_CHARS,
            )
            for idx, ctext in enumerate(chunks, start=1):
                chunked_docs.append((f"{doc_name} [chunk {idx}/{len(chunks)}]", ctext))

        all_clins: List[Dict] = []
        all_deadlines: List[Dict] = []
        for cname, ctext in chunked_docs:
            clins_chunk, deadlines_chunk = self.extract_clins(
                ctext,
                file_path=cname,
                run_missing_fields_second_pass=False,
            )
            all_clins.extend(clins_chunk or [])
            all_deadlines.extend(deadlines_chunk or [])

        merged_clins = self._merge_and_dedupe_clins(all_clins)
        merged_clins = self._filter_noise_clins(merged_clins)
        merged_deadlines = self._merge_and_dedupe_deadlines(all_deadlines)
        reconciled_clins = self._reconcile_merged_clins_llm(merged_clins)
        reconciled_clins = self._filter_noise_clins(reconciled_clins)
        final_clins = reconciled_clins

        # Final second pass only once, after merge + reconcile, using full combined context.
        if final_clins:
            missing_fields_count, total_fields_count = self._count_missing_fields(final_clins)
            if missing_fields_count > 0 and total_fields_count > 0:
                missing_percentage = (missing_fields_count / total_fields_count) * 100
                logger.info(
                    "Final merged CLINs still have %s missing fields (%.1f%%). Running one final missing-fields pass.",
                    missing_fields_count,
                    missing_percentage,
                )
                final_clins = self._fill_missing_fields(final_clins, combined_text)
            else:
                logger.info("Final merged CLINs have no missing fields; skipping final missing-fields pass.")

        logger.info(
            "Chunked extraction complete: chunks=%s raw_clins=%s merged_clins=%s deadlines=%s",
            len(chunked_docs), len(all_clins), len(final_clins), len(merged_deadlines)
        )
        return final_clins, merged_deadlines

    def extract_clins_batch(self, documents: List[Tuple[str, str]]) -> Tuple[List[Dict], List[Dict]]:
        """Extract CLINs from multiple documents - try all at once, else per document"""
        if not self.llm and not self.fallback_llm:
            logger.warning("No LLM available")
            return ([], [])
        
        if not documents:
            return ([], [])
        
        # Build full combined text first so small requests keep full context.
        if not documents:
            return ([], [])
        combined_text = "\n\n".join([f"=== DOCUMENT: {n} ===\n{t}" for n, t in documents if t and t.strip()])
        if not combined_text:
            return ([], [])
        if len(combined_text) > self.LARGE_BATCH_THRESHOLD_CHARS:
            return self._extract_clins_batch_chunked(documents, combined_text)

        # Non-large path: preserve full context for quality (no Claude truncation).
        # Keep Groq budgeted as fallback safety.
        combined_text_len = len(combined_text)
        claude_docs_text = combined_text
        groq_docs_text, _ = self._build_docs_text_for_budget(
            documents=documents,
            max_total_chars=22000,
            prepend_schedule_max_chars=12000,
        )

        def _build_prompt(docs_text: str) -> str:
            return f"""You are a government contracting analyst. Analyze these solicitation documents and extract ALL Contract Line Item Numbers (CLINs) and their complete details.

Each document is separated by "=== DOCUMENT: [name] ===".

CRITICAL: Extract EVERY CLIN found across ALL documents. Search SYSTEMATICALLY through EACH document. Look for:
- Tables with headers containing "CLIN", "Line Item", "Item Number", "Schedule Item", "Item No", "ITEM NUMBER", "B.3 PRICE/COST SCHEDULE"
- Sections titled "Schedule of Supplies/Services", "Pricing Schedule", "CLIN Schedule", "SECTION B", "Schedule"
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
{docs_text}"""
        
        # Log combined text info
        logger.info(f"Combining {len(documents)} documents into single request")
        logger.info(f"Total combined text length: {combined_text_len} characters")
        logger.info(f"Claude docs text length after budget: {len(claude_docs_text)} characters")
        logger.info(f"Groq docs text length after budget: {len(groq_docs_text)} characters")
        for doc_name, _ in documents:
            logger.info(f"  - {doc_name}")
        
        # Try Claude first with all documents combined
        logger.info("Sending ALL documents combined in ONE request to Claude for CLIN and deadline extraction...")
        all_clins, all_deadlines = self._extract_with_llm(_build_prompt(claude_docs_text), use_claude=True)
        
        # If failed, try Groq
        if not all_clins and self.fallback_llm:
            logger.info("Claude batch failed, trying Groq with budgeted prompt...")
            all_clins, all_deadlines = self._extract_with_llm(_build_prompt(groq_docs_text), use_claude=False)
        
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