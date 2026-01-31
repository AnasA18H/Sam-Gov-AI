"""
LLM-Guided External Research Service
Uses LLM to guide web search for manufacturers and dealers online
Finds official websites, contact emails, and authorized dealers
"""
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from playwright.sync_api import sync_playwright, Page, Browser
import re
import time
import json

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
    logging.warning("Pydantic v1 not available. LLM external research disabled.")

from ..core.config import settings
from ..models.manufacturer import Manufacturer
from ..models.dealer import Dealer

logger = logging.getLogger(__name__)


# Pydantic schemas for LLM extraction
if PYDANTIC_AVAILABLE:
    class ManufacturerResearchResult(V1BaseModel):
        """Manufacturer research result from external sources"""
        website: Optional[str] = V1Field(None, description="Official manufacturer website URL")
        contact_email: Optional[str] = V1Field(None, description="Sales team contact email (prefer sales@, contact@)")
        contact_phone: Optional[str] = V1Field(None, description="Contact phone number")
        address: Optional[str] = V1Field(None, description="Company address if found")
        sam_gov_verified: bool = V1Field(False, description="Whether verified on SAM.gov")
        website_verified: bool = V1Field(False, description="Whether website was verified")
        verification_notes: Optional[str] = V1Field(None, description="Verification notes")
    
    class DealerResearchResult(V1BaseModel):
        """Dealer/distributor research result from external sources"""
        company_name: str = V1Field(description="Full company name")
        website: str = V1Field(description="Company website URL")
        contact_email: Optional[str] = V1Field(None, description="Sales contact email (prefer sales@, contact@)")
        pricing: Optional[str] = V1Field(None, description="Current retail pricing if publicly available (e.g., '$1,250.00')")
        stock_status: Optional[str] = V1Field(None, description="Stock status if available (e.g., 'In Stock', 'Available')")
        rank_score: int = V1Field(description="Ranking score 1-8 (1 = highest priority)")
        sam_gov_verified: bool = V1Field(False, description="Whether verified on SAM.gov")
        manufacturer_authorized: Optional[bool] = V1Field(None, description="Whether authorized by manufacturer (if known)")
        verification_notes: Optional[str] = V1Field(None, description="Verification notes")
    
    class ExternalResearchResult(V1BaseModel):
        """Complete external research result"""
        manufacturer: Optional[ManufacturerResearchResult] = V1Field(None, description="Manufacturer research results")
        dealers: List[DealerResearchResult] = V1Field(default_factory=list, description="Top 8 dealers found (ranked by priority)")


class LLMExternalResearchService:
    """LLM-guided external research for manufacturers and dealers"""
    
    def __init__(self):
        self.llm = None
        self.fallback_llm = None
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.playwright = None
        
        # Initialize LLMs
        if ANTHROPIC_AVAILABLE and settings.ANTHROPIC_API_KEY:
            try:
                self.llm = ChatAnthropic(
                    model=settings.ANTHROPIC_MODEL,
                    temperature=0,
                    api_key=settings.ANTHROPIC_API_KEY
                )
                logger.info(f"Claude LLM initialized for external research: {settings.ANTHROPIC_MODEL}")
            except Exception as e:
                logger.warning(f"Failed to initialize Claude: {e}")
        
        if GROQ_AVAILABLE and settings.GROQ_API_KEY:
            try:
                self.fallback_llm = ChatGroq(
                    model=settings.GROQ_MODEL,
                    temperature=0,
                    api_key=settings.GROQ_API_KEY
                )
                logger.info(f"Groq LLM initialized for external research: {settings.GROQ_MODEL}")
            except Exception as e:
                logger.warning(f"Failed to initialize Groq: {e}")
    
    def __enter__(self):
        """Context manager entry"""
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )
        self.page = self.browser.new_page()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
    
    def research_manufacturer_and_dealers(
        self,
        manufacturer: Manufacturer,
        part_number: Optional[str] = None,
        nsn: Optional[str] = None,
        reference_text: Optional[str] = None
    ) -> Dict:
        """
        Research manufacturer website/contact and find top 8 authorized dealers
        
        Args:
            manufacturer: Manufacturer object to research
            part_number: Part number to search for dealers
            nsn: NSN code if available
            reference_text: Reference material for online search strategies
            
        Returns:
            Dict with manufacturer research and dealers list
        """
        if not self.llm and not self.fallback_llm:
            logger.warning("No LLM available for external research")
            return {"manufacturer": {}, "dealers": []}
        
        # Step 1: Use LLM to guide search strategy
        search_strategy = self._get_search_strategy(manufacturer, part_number, nsn, reference_text)
        
        # Step 2: Execute web searches based on LLM guidance
        manufacturer_results = self._research_manufacturer_website(manufacturer, search_strategy)
        dealer_results = self._research_dealers(manufacturer, part_number, nsn, search_strategy)
        
        return {
            "manufacturer": manufacturer_results,
            "dealers": dealer_results
        }
    
    def _get_search_strategy(
        self,
        manufacturer: Manufacturer,
        part_number: Optional[str],
        nsn: Optional[str],
        reference_text: Optional[str]
    ) -> Dict:
        """Use LLM to determine best search strategy based on reference guide"""
        reference_section = ""
        if reference_text:
            reference_section = f"""

REFERENCE GUIDE FOR ONLINE SEARCH:
{reference_text}

Use the strategies and methods described in the reference guide above to determine the best search approach.
"""
        
        prompt = f"""You are a research assistant helping to find manufacturer websites and authorized dealers online.
Follow the reference guide provided below for legitimate search strategies.

MANUFACTURER TO RESEARCH:
- Name: {manufacturer.name}
- CAGE Code: {manufacturer.cage_code or 'Not provided'}
- Part Number: {part_number or 'Not provided'}
- NSN: {nsn or 'Not provided'}
{reference_section}
Based on the reference guide above, provide a JSON strategy for finding:
1. Manufacturer's official website and sales contact email
2. Top 8 authorized dealers/distributors for this part

Return JSON with:
{{
  "manufacturer_search_queries": ["query1", "query2", ...],
  "dealer_search_queries": ["query1", "query2", ...],
  "manufacturer_website_expected": "expected domain or company name",
  "priority_sources": ["manufacturer_website", "dla_mil", "google_search", ...]
}}

Focus on legitimate sources and verification methods.
"""
        
        try:
            if PYDANTIC_AVAILABLE:
                # Use structured output if available
                structured_llm = self.llm.with_structured_output(
                    dict,  # Simple dict for strategy
                    method="function_calling"
                )
                strategy = structured_llm.invoke(prompt)
                return strategy
            else:
                # Fallback: parse JSON from text
                response = self.llm.invoke(prompt)
                # Extract JSON from response
                json_match = re.search(r'\{.*\}', response.content, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group())
        except Exception as e:
            logger.warning(f"Error getting search strategy from LLM: {str(e)}")
            # Return default strategy
            return {
                "manufacturer_search_queries": [
                    f"{manufacturer.name} official website",
                    f"{manufacturer.name} CAGE {manufacturer.cage_code}" if manufacturer.cage_code else None
                ],
                "dealer_search_queries": [
                    f'"{part_number}" distributor' if part_number else None,
                    f'"{part_number}" authorized dealer' if part_number else None,
                    f"NSN {nsn} supplier" if nsn else None
                ],
                "priority_sources": ["manufacturer_website", "google_search"]
            }
    
    def _research_manufacturer_website(
        self,
        manufacturer: Manufacturer,
        search_strategy: Dict
    ) -> Dict:
        """Research manufacturer website and contact info"""
        results = {
            'website': None,
            'contact_email': None,
            'contact_phone': None,
            'address': None,
            'sam_gov_verified': False,
            'website_verified': False
        }
        
        try:
            # Execute Google searches from strategy
            queries = search_strategy.get('manufacturer_search_queries', [])
            for query in queries[:3]:  # Limit to 3 queries
                if not query:
                    continue
                
                logger.info(f"Searching Google for manufacturer: {query}")
                google_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
                
                self.page.goto(google_url, wait_until='load', timeout=30000)
                time.sleep(2)
                
                # Extract first result
                try:
                    first_result = self.page.query_selector('div.g a')
                    if first_result:
                        website_url = first_result.get_attribute('href')
                        if website_url and website_url.startswith('http'):
                            results['website'] = website_url
                            logger.info(f"Found manufacturer website: {website_url}")
                            
                            # Extract contact info from website
                            contact_info = self._extract_contact_from_website(website_url)
                            results.update(contact_info)
                            results['website_verified'] = True
                            break
                except Exception as e:
                    logger.debug(f"Error extracting result: {str(e)}")
                
                time.sleep(1)  # Rate limiting
            
            # Verify on SAM.gov if CAGE code available
            if manufacturer.cage_code:
                results['sam_gov_verified'] = self._verify_sam_gov(manufacturer.name, manufacturer.cage_code)
        
        except Exception as e:
            logger.error(f"Error researching manufacturer website: {str(e)}")
        
        return results
    
    def _research_dealers(
        self,
        manufacturer: Manufacturer,
        part_number: Optional[str],
        nsn: Optional[str],
        search_strategy: Dict
    ) -> List[Dict]:
        """Research top 8 authorized dealers"""
        dealers = []
        seen_companies = set()
        
        try:
            # Priority 1: Check manufacturer website for authorized dealers list
            if manufacturer.name:
                manufacturer_dealers = self._get_dealers_from_manufacturer_website(manufacturer.name, part_number)
                for dealer in manufacturer_dealers:
                    if dealer['company_name'].lower() not in seen_companies:
                        seen_companies.add(dealer['company_name'].lower())
                        dealer['rank_score'] = len(dealers) + 1
                        dealer['manufacturer_authorized'] = True
                        dealers.append(dealer)
                        if len(dealers) >= 8:
                            return dealers
            
            # Priority 2: Google searches from strategy
            queries = search_strategy.get('dealer_search_queries', [])
            for query in queries[:5]:  # Limit to 5 queries
                if not query or len(dealers) >= 8:
                    break
                
                logger.info(f"Searching Google for dealers: {query}")
                google_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
                
                self.page.goto(google_url, wait_until='load', timeout=30000)
                time.sleep(2)
                
                # Extract result links
                result_links = self.page.query_selector_all('div.g a')
                for link in result_links[:10]:  # Check top 10 results
                    if len(dealers) >= 8:
                        break
                    
                    try:
                        url = link.get_attribute('href')
                        if not url or not url.startswith('http'):
                            continue
                        
                        link_text = link.inner_text() or ''
                        company_name = self._extract_company_name(url, link_text)
                        
                        if company_name and company_name.lower() not in seen_companies:
                            # Check if looks like a distributor
                            if self._is_likely_distributor(url, link_text, part_number):
                                dealer_info = self._extract_dealer_info(url, company_name, part_number)
                                if dealer_info:
                                    seen_companies.add(company_name.lower())
                                    dealer_info['rank_score'] = len(dealers) + 1
                                    dealers.append(dealer_info)
                    except Exception as e:
                        logger.debug(f"Error processing dealer result: {str(e)}")
                        continue
                
                time.sleep(1)  # Rate limiting
            
            # Verify dealers on SAM.gov
            for dealer in dealers:
                dealer['sam_gov_verified'] = self._verify_sam_gov(dealer['company_name'], None)
        
        except Exception as e:
            logger.error(f"Error researching dealers: {str(e)}")
        
        return dealers[:8]  # Return top 8
    
    def _get_dealers_from_manufacturer_website(
        self,
        manufacturer_name: str,
        part_number: Optional[str]
    ) -> List[Dict]:
        """Try to get authorized dealers list from manufacturer website"""
        dealers = []
        
        try:
            # Search for manufacturer website
            search_query = f"{manufacturer_name} official website"
            google_url = f"https://www.google.com/search?q={search_query.replace(' ', '+')}"
            
            self.page.goto(google_url, wait_until='load', timeout=30000)
            time.sleep(2)
            
            first_result = self.page.query_selector('div.g a')
            if first_result:
                website_url = first_result.get_attribute('href')
                if website_url and website_url.startswith('http'):
                    # Try to find "Where to Buy" or "Distributors" page
                    self.page.goto(website_url, wait_until='load', timeout=30000)
                    time.sleep(2)
                    
                    # Look for distributor/dealer links
                    dealer_links = self.page.query_selector_all(
                        'a[href*="distributor"], a[href*="dealer"], a[href*="where-to-buy"], '
                        'a[href*="buy"], a[href*="authorized"]'
                    )
                    
                    for link in dealer_links[:10]:
                        try:
                            link_text = link.inner_text()
                            if any(keyword in link_text.lower() for keyword in ['distributor', 'dealer', 'buy', 'where']):
                                # This might be a dealer list page
                                dealer_url = link.get_attribute('href')
                                if dealer_url and not dealer_url.startswith('http'):
                                    from urllib.parse import urljoin
                                    dealer_url = urljoin(website_url, dealer_url)
                                
                                # Navigate and extract dealers
                                # (Simplified - would need more sophisticated parsing)
                                # For now, return empty list - can be enhanced
                                pass
                        except:
                            continue
        except Exception as e:
            logger.debug(f"Could not get dealers from manufacturer website: {str(e)}")
        
        return dealers
    
    def _extract_contact_from_website(self, website_url: str) -> Dict:
        """Extract contact information from website"""
        results = {
            'contact_email': None,
            'contact_phone': None,
            'address': None
        }
        
        try:
            self.page.goto(website_url, wait_until='load', timeout=30000)
            time.sleep(2)
            
            page_text = self.page.content()
            
            # Extract emails
            email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
            emails = re.findall(email_pattern, page_text)
            contact_emails = [e for e in emails if not any(x in e.lower() for x in ['noreply', 'no-reply', 'privacy', 'legal', 'copyright'])]
            if contact_emails:
                sales_emails = [e for e in contact_emails if any(x in e.lower() for x in ['sales', 'contact', 'info', 'support'])]
                results['contact_email'] = sales_emails[0] if sales_emails else contact_emails[0]
            
            # Extract phone
            phone_pattern = r'(\+?1[-.\s]?)?\(?([0-9]{3})\)?[-.\s]?([0-9]{3})[-.\s]?([0-9]{4})'
            phones = re.findall(phone_pattern, page_text)
            if phones:
                phone = ''.join(phones[0][1:]) if phones[0][1:] else ''.join(phones[0])
                results['contact_phone'] = f"({phone[:3]}) {phone[3:6]}-{phone[6:]}" if len(phone) == 10 else phone
            
            # Try contact page
            try:
                contact_links = self.page.query_selector_all('a[href*="contact"], a[href*="sales"], a[href*="about"]')
                if contact_links:
                    contact_url = contact_links[0].get_attribute('href')
                    if contact_url and not contact_url.startswith('http'):
                        from urllib.parse import urljoin
                        contact_url = urljoin(website_url, contact_url)
                    
                    if contact_url:
                        self.page.goto(contact_url, wait_until='load', timeout=30000)
                        time.sleep(2)
                        contact_text = self.page.content()
                        
                        contact_emails = re.findall(email_pattern, contact_text)
                        if contact_emails and not results['contact_email']:
                            sales_emails = [e for e in contact_emails if any(x in e.lower() for x in ['sales', 'contact', 'info'])]
                            results['contact_email'] = sales_emails[0] if sales_emails else contact_emails[0]
                        
                        contact_phones = re.findall(phone_pattern, contact_text)
                        if contact_phones and not results['contact_phone']:
                            phone = ''.join(contact_phones[0][1:]) if contact_phones[0][1:] else ''.join(contact_phones[0])
                            results['contact_phone'] = f"({phone[:3]}) {phone[3:6]}-{phone[6:]}" if len(phone) == 10 else phone
            except:
                pass
        
        except Exception as e:
            logger.warning(f"Error extracting contact from {website_url}: {str(e)}")
        
        return results
    
    def _extract_dealer_info(self, url: str, company_name: str, part_number: Optional[str]) -> Optional[Dict]:
        """Extract dealer information from website"""
        try:
            self.page.goto(url, wait_until='load', timeout=30000)
            time.sleep(2)
            
            page_text = self.page.content()
            
            # Extract email
            email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
            emails = re.findall(email_pattern, page_text)
            contact_emails = [e for e in emails if not any(x in e.lower() for x in ['noreply', 'no-reply', 'privacy', 'legal'])]
            sales_email = None
            if contact_emails:
                sales_emails = [e for e in contact_emails if any(x in e.lower() for x in ['sales', 'contact', 'info'])]
                sales_email = sales_emails[0] if sales_emails else contact_emails[0]
            
            # Extract pricing (look for price patterns)
            pricing = None
            price_patterns = [
                r'\$[\d,]+\.?\d*',  # $1,250.00
                r'USD\s*[\d,]+\.?\d*',  # USD 1250.00
                r'Price[:\s]*\$?[\d,]+\.?\d*',  # Price: $1,250
            ]
            for pattern in price_patterns:
                prices = re.findall(pattern, page_text, re.IGNORECASE)
                if prices:
                    pricing = prices[0]
                    break
            
            # Check stock status
            stock_status = None
            if any(keyword in page_text.lower() for keyword in ['in stock', 'available', 'ready to ship']):
                stock_status = "In Stock"
            elif any(keyword in page_text.lower() for keyword in ['out of stock', 'unavailable']):
                stock_status = "Out of Stock"
            
            return {
                'company_name': company_name,
                'website': url,
                'contact_email': sales_email,
                'pricing': pricing,
                'stock_status': stock_status,
                'sam_gov_verified': False,
                'manufacturer_authorized': None
            }
        except Exception as e:
            logger.debug(f"Error extracting dealer info from {url}: {str(e)}")
            return None
    
    def _is_likely_distributor(self, url: str, link_text: str, part_number: Optional[str]) -> bool:
        """Check if URL/link looks like a distributor"""
        url_lower = url.lower()
        text_lower = link_text.lower()
        
        # Positive indicators
        positive_keywords = ['distributor', 'supplier', 'parts', 'aviation', 'aerospace', 'nsn', 'military', 'defense']
        
        # Negative indicators (skip these)
        negative_keywords = ['wikipedia', 'facebook', 'twitter', 'linkedin', 'youtube', 'amazon', 'ebay']
        
        if any(neg in url_lower for neg in negative_keywords):
            return False
        
        return any(pos in url_lower or pos in text_lower for pos in positive_keywords)
    
    def _extract_company_name(self, url: str, link_text: str) -> Optional[str]:
        """Extract company name from URL or link text"""
        if link_text:
            text = link_text.strip()
            text = re.sub(r'^(www\.|https?://)', '', text)
            parts = re.split(r'[|\-–—]', text)
            if parts:
                return parts[0].strip()
        
        try:
            from urllib.parse import urlparse
            domain = urlparse(url).netloc
            domain = domain.replace('www.', '')
            domain_parts = domain.split('.')[0]
            domain_parts = re.sub(r'([a-z])([A-Z])', r'\1 \2', domain_parts)
            return domain_parts.title()
        except:
            return None
    
    def _verify_sam_gov(self, company_name: str, cage_code: Optional[str] = None) -> bool:
        """Verify company on SAM.gov (simplified - would need actual SAM.gov API)"""
        # TODO: Implement actual SAM.gov API check
        # For now, return False (would need SAM.gov API integration)
        return False
