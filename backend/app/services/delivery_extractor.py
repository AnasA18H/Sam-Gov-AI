"""
Delivery Requirements Extraction Service
Extracts delivery addresses, FOB terms, timelines, and special instructions from solicitation documents.
"""
import re
import logging
from typing import Dict, List, Optional
from datetime import datetime
import dateutil.parser
from dateutil.parser import ParserError

logger = logging.getLogger(__name__)

# LLM imports (optional)
try:
    from langchain_anthropic import ChatAnthropic
    from langchain_groq import ChatGroq
    from langchain_core.pydantic_v1 import BaseModel as V1BaseModel, Field as V1Field
    from pydantic import BaseModel as PydanticBaseModel
    LANGCHAIN_AVAILABLE = True
    PYDANTIC_V1_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    PYDANTIC_V1_AVAILABLE = False
    logger.warning("LangChain or Pydantic v1 not available. LLM-based delivery extraction disabled.")

from ..core.config import settings

# Define Pydantic schemas for LLM extraction (if available)
if LANGCHAIN_AVAILABLE and PYDANTIC_V1_AVAILABLE:
    class DeliveryAddress(V1BaseModel):
        facility_name: Optional[str] = V1Field(None, description="Name of the delivery facility or location")
        street_address: Optional[str] = V1Field(None, description="Street address including street number and name")
        city: Optional[str] = V1Field(None, description="City name")
        state: Optional[str] = V1Field(None, description="State abbreviation (e.g., 'TX', 'CA')")
        zip_code: Optional[str] = V1Field(None, description="ZIP code (5 or 9 digits)")
        country: Optional[str] = V1Field("US", description="Country code (default: 'US')")
    
    class DeliveryRequirements(V1BaseModel):
        delivery_address: Optional[DeliveryAddress] = V1Field(None, description="Complete delivery address")
        fob_terms: Optional[str] = V1Field(None, description="FOB terms: 'destination' or 'origin'")
        delivery_timeline: Optional[str] = V1Field(None, description="Delivery timeline (e.g., '60 days after contract award', 'Within 30 days')")
        delivery_date: Optional[str] = V1Field(None, description="Specific delivery date if mentioned")
        special_instructions: List[str] = V1Field(default_factory=list, description="Special delivery instructions, requirements, or constraints")
        packing_requirements: Optional[str] = V1Field(None, description="Packing or shipping method requirements")
        facility_constraints: Dict = V1Field(default_factory=dict, description="Facility constraints like dock requirements, height restrictions, vehicle restrictions")

# Delivery extraction patterns
DELIVERY_ADDRESS_KEYWORDS = [
    'place of delivery', 'deliver to', 'delivery address', 'ship to',
    'delivery location', 'destination', 'receiving address', 'facility'
]

FOB_KEYWORDS = [
    'f.o.b.', 'fob', 'free on board', 'freight on board'
]

DELIVERY_TIMELINE_KEYWORDS = [
    'delivery time', 'delivery date', 'required delivery', 'preferred delivery',
    'delivery schedule', 'delivery deadline', 'within', 'days after', 'after receipt'
]

PACKING_KEYWORDS = [
    'packing', 'packaging', 'shipping method', 'delivery method', 'skids', 'pallets'
]


class DeliveryRequirementsExtractor:
    """Service for extracting delivery requirements from government contract documents"""
    
    def __init__(self):
        """Initialize the delivery requirements extractor"""
        self.llm = None  # Primary LLM (Claude)
        self.fallback_llm = None  # Fallback LLM (Groq)
        
        # Initialize primary LLM (Claude) - optional
        if LANGCHAIN_AVAILABLE and PYDANTIC_V1_AVAILABLE:
            try:
                from langchain_anthropic import ChatAnthropic
                if settings.ANTHROPIC_API_KEY:
                    self.llm = ChatAnthropic(
                        model=settings.ANTHROPIC_MODEL,
                        temperature=0,
                        api_key=settings.ANTHROPIC_API_KEY
                    )
                    logger.info(f"Claude LLM initialized for delivery extraction: {settings.ANTHROPIC_MODEL}")
            except Exception as e:
                logger.warning(f"Failed to initialize Claude LLM for delivery extraction: {str(e)}")
        
        # Initialize fallback LLM (Groq) - optional
        if LANGCHAIN_AVAILABLE and PYDANTIC_V1_AVAILABLE:
            try:
                from langchain_groq import ChatGroq
                if settings.GROQ_API_KEY:
                    self.fallback_llm = ChatGroq(
                        model=settings.GROQ_MODEL,
                        temperature=0,
                        api_key=settings.GROQ_API_KEY
                    )
                    logger.info(f"Groq LLM initialized for delivery extraction: {settings.GROQ_MODEL}")
            except Exception as e:
                logger.warning(f"Failed to initialize Groq LLM for delivery extraction: {str(e)}")
    
    def extract_delivery_requirements(self, text: str) -> Dict:
        """
        Extract delivery requirements from document text using hybrid approach:
        1. Regex patterns for structured data (addresses, FOB terms)
        2. LLM for natural language sections (SOW, special instructions)
        
        Args:
            text: Document text content
            
        Returns:
            Dictionary with delivery requirements:
            {
                'delivery_address': {
                    'facility_name': str,
                    'street_address': str,
                    'city': str,
                    'state': str,
                    'zip_code': str,
                    'country': str
                },
                'fob_terms': str,  # 'destination' or 'origin'
                'delivery_timeline': str,
                'delivery_date': datetime or None,
                'special_instructions': List[str],
                'packing_requirements': str,
                'facility_constraints': Dict
            }
        """
        if not text or not text.strip():
            return {}
        
        # Step 1: Regex extraction for structured patterns
        delivery_address = self._extract_address_regex(text)
        fob_terms = self._extract_fob_terms_regex(text)
        packing_requirements = self._extract_packing_regex(text)
        
        # Step 2: LLM extraction for natural language (if available)
        llm_results = {}
        if self.llm or self.fallback_llm:
            try:
                llm_results = self._extract_with_llm(text)
            except Exception as e:
                logger.warning(f"LLM delivery extraction failed: {str(e)}")
        
        # Step 3: Merge results (LLM takes precedence for natural language, regex for structured)
        result = {
            'delivery_address': llm_results.get('delivery_address') or delivery_address,
            'fob_terms': llm_results.get('fob_terms') or fob_terms,
            'delivery_timeline': llm_results.get('delivery_timeline'),
            'delivery_date': llm_results.get('delivery_date'),
            'special_instructions': llm_results.get('special_instructions', []),
            'packing_requirements': llm_results.get('packing_requirements') or packing_requirements,
            'facility_constraints': llm_results.get('facility_constraints', {})
        }
        
        # Clean up empty values
        result = {k: v for k, v in result.items() if v}
        
        return result
    
    def _extract_address_regex(self, text: str) -> Optional[Dict]:
        """Extract delivery address using regex patterns"""
        # Pattern 1: "Place of Delivery: Facility Name\nStreet Address | City, State ZIP"
        pattern1 = r'(?:place\s+of\s+delivery|deliver\s+to|delivery\s+address)[:\s]+([^\n]+?)\s*\n\s*([^\n|]+?)(?:\s*\|\s*)?([^,\n]+),\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)'
        match1 = re.search(pattern1, text, re.IGNORECASE | re.MULTILINE)
        if match1:
            return {
                'facility_name': match1.group(1).strip(),
                'street_address': match1.group(2).strip(),
                'city': match1.group(3).strip(),
                'state': match1.group(4).strip(),
                'zip_code': match1.group(5).strip(),
                'country': 'US'
            }
        
        # Pattern 2: Street Address, City, State ZIP (without facility name)
        pattern2 = r'(\d+\s+[A-Za-z0-9\s]+(?:Street|St|Road|Rd|Avenue|Ave|Boulevard|Blvd|Drive|Dr|Lane|Ln|Way|Court|Ct|Place|Pl)[^,\n]+),\s*([^,\n]+),\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)'
        match2 = re.search(pattern2, text, re.IGNORECASE)
        if match2:
            return {
                'facility_name': None,
                'street_address': match2.group(1).strip(),
                'city': match2.group(2).strip(),
                'state': match2.group(3).strip(),
                'zip_code': match2.group(4).strip(),
                'country': 'US'
            }
        
        return None
    
    def _extract_fob_terms_regex(self, text: str) -> Optional[str]:
        """Extract FOB terms using regex"""
        # Pattern: "F.O.B. destination" or "FOB destination"
        pattern = r'f\.?o\.?b\.?\s+(destination|origin)'
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).lower()
        return None
    
    def _extract_packing_regex(self, text: str) -> Optional[str]:
        """Extract packing requirements using regex"""
        # Look for packing-related phrases
        patterns = [
            r'packing\s+method[:\s]+([^\n\.]+)',
            r'packaging[:\s]+([^\n\.]+)',
            r'(?:skids|pallets|bulk\s+packed)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip() if match.groups() else match.group(0).strip()
        
        return None
    
    def _extract_with_llm(self, text: str) -> Dict:
        """Extract delivery requirements using LLM"""
        if not LANGCHAIN_AVAILABLE or not PYDANTIC_V1_AVAILABLE:
            return {}
        
        if not self.llm and not self.fallback_llm:
            return {}
        
        if not LANGCHAIN_AVAILABLE or not PYDANTIC_V1_AVAILABLE:
            return {}
        
        prompt = """You are a specialized data extraction assistant for government contract documents. Your task is to extract delivery requirements from solicitation documents.

## INPUT
You will receive government contract document text that may include:
- Statement of Work (SOW) sections
- Delivery or Performance sections
- Q&A documents
- Amendment documents

## TASK
Extract ALL delivery-related information including:

### 1. DELIVERY ADDRESS
Look for sections labeled:
- "Place of Delivery"
- "Deliver To"
- "Delivery Address"
- "Ship To"
- "Destination"

Extract complete address including:
- Facility name (if specified)
- Street address
- City, State, ZIP code
- Country (usually US)

### 2. FOB TERMS
Look for "F.O.B." or "FOB" followed by:
- "destination" (delivery to government location)
- "origin" (pickup from contractor)

### 3. DELIVERY TIMELINE
Extract phrases like:
- "within X days"
- "X days after contract award"
- "preferred delivery time"
- "delivery schedule"
- "staggered delivery"

### 4. SPECIAL INSTRUCTIONS
Extract:
- Testing requirements before delivery
- Staggered delivery schedules
- Delivery method requirements
- Acceptance criteria
- Any special constraints or requirements

### 5. PACKING REQUIREMENTS
Extract:
- Packing method (skids, pallets, boxes)
- Shipping method preferences
- Bulk packing instructions

### 6. FACILITY CONSTRAINTS
Extract:
- Dock requirements
- Height restrictions
- Vehicle restrictions (semi-trailer, flatbed, etc.)

## RULES
- Extract complete addresses when found
- If multiple addresses mentioned, prioritize the primary delivery address
- Extract FOB terms exactly as written (destination or origin)
- Capture delivery timelines in natural language
- List all special instructions separately
- If information is not found, leave fields as null or empty

DOCUMENT TEXT:
""" + text[:50000]  # Limit to 50k chars to avoid token limits
        
        # Try Claude first, then Groq if Claude fails
        llm_to_use = self.llm if self.llm else self.fallback_llm
        llm_name = "Claude" if self.llm else "Groq"
        
        try:
            structured_llm = llm_to_use.with_structured_output(DeliveryRequirements, method="function_calling")
            result = structured_llm.invoke(prompt)
            
            # Convert to dict format
            delivery_dict = {}
            if isinstance(result, DeliveryRequirements):
                if result.delivery_address:
                    delivery_dict['delivery_address'] = {
                        'facility_name': result.delivery_address.facility_name,
                        'street_address': result.delivery_address.street_address,
                        'city': result.delivery_address.city,
                        'state': result.delivery_address.state,
                        'zip_code': result.delivery_address.zip_code,
                        'country': result.delivery_address.country or 'US'
                    }
                delivery_dict['fob_terms'] = result.fob_terms
                delivery_dict['delivery_timeline'] = result.delivery_timeline
                if result.delivery_date:
                    try:
                        delivery_dict['delivery_date'] = dateutil.parser.parse(result.delivery_date)
                    except:
                        delivery_dict['delivery_timeline'] = result.delivery_date  # Fallback to timeline
                delivery_dict['special_instructions'] = result.special_instructions
                delivery_dict['packing_requirements'] = result.packing_requirements
                delivery_dict['facility_constraints'] = result.facility_constraints
            
            logger.info(f"{llm_name} extracted delivery requirements successfully")
            return delivery_dict
            
        except Exception as e:
            logger.warning(f"{llm_name} delivery extraction failed: {str(e)}")
            # Try fallback LLM if primary failed
            if self.llm and self.fallback_llm:
                try:
                    structured_llm = self.fallback_llm.with_structured_output(DeliveryRequirements, method="function_calling")
                    result = structured_llm.invoke(prompt)
                    # Convert same as above
                    delivery_dict = {}
                    if isinstance(result, DeliveryRequirements):
                        if result.delivery_address:
                            delivery_dict['delivery_address'] = {
                                'facility_name': result.delivery_address.facility_name,
                                'street_address': result.delivery_address.street_address,
                                'city': result.delivery_address.city,
                                'state': result.delivery_address.state,
                                'zip_code': result.delivery_address.zip_code,
                                'country': result.delivery_address.country or 'US'
                            }
                        delivery_dict['fob_terms'] = result.fob_terms
                        delivery_dict['delivery_timeline'] = result.delivery_timeline
                        delivery_dict['special_instructions'] = result.special_instructions
                        delivery_dict['packing_requirements'] = result.packing_requirements
                        delivery_dict['facility_constraints'] = result.facility_constraints
                    logger.info("Groq fallback extracted delivery requirements successfully")
                    return delivery_dict
                except Exception as fallback_error:
                    logger.warning(f"Groq fallback also failed: {str(fallback_error)}")
            
            return {}
