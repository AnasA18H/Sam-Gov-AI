"""
SAM.gov Web Scraper using Playwright
Extracts metadata and downloads attachments from SAM.gov opportunity pages
"""
from playwright.sync_api import sync_playwright, Page, Browser
from typing import Dict, List, Optional, Tuple
import re
import logging
from datetime import datetime
from pathlib import Path
import os
from urllib.parse import urljoin, urlparse, quote

from ..utils.sam_gov import validate_sam_gov_url, extract_opportunity_id
from ..core.config import settings

logger = logging.getLogger(__name__)


class SAMGovScraper:
    """Scraper for SAM.gov opportunity pages"""
    
    def __init__(self, base_url: str = None):
        self.base_url = base_url or settings.SAM_GOV_BASE_URL
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.playwright = None
    
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
    
    def scrape_opportunity(self, url: str) -> Dict:
        """
        Scrape a SAM.gov opportunity page and extract all data
        
        Returns:
            dict: {
                'metadata': {...},
                'attachments': [...],
                'success': bool
            }
        """
        # Validate URL
        is_valid, error = validate_sam_gov_url(url)
        if not is_valid:
            return {'success': False, 'error': error}
        
        try:
            logger.info(f"Navigating to {url}")
            # Use 'load' instead of 'networkidle' - more reliable for sites with continuous requests
            self.page.goto(url, wait_until='load', timeout=90000)
            
            # Wait for page to load (Angular app may need time)
            try:
                self.page.wait_for_selector('app-root', timeout=30000)
            except Exception as e:
                logger.warning(f"app-root selector not found, continuing anyway: {e}")
            
            # Give Angular time to initialize
            self.page.wait_for_timeout(2000)
            
            # Extract all data
            metadata = self._extract_metadata()
            attachments = self._extract_attachments()
            
            # Extract page text content for LLM analysis
            page_text = self._extract_page_text()
            
            return {
                'success': True,
                'metadata': metadata,
                'attachments': attachments,
                'opportunity_id': extract_opportunity_id(url),
                'page_text': page_text
            }
            
        except Exception as e:
            logger.error(f"Error scraping {url}: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def _extract_metadata(self) -> Dict:
        """Extract metadata from the SAM.gov page"""
        metadata = {}
        
        try:
            # Extract Notice ID (appears in multiple places)
            notice_id = self._extract_notice_id()
            metadata['notice_id'] = notice_id
            logger.info(f"Extracted notice_id: {notice_id}")
            
            # Extract Title
            title = self._extract_title()
            metadata['title'] = title
            logger.info(f"Extracted title: {title[:50] if title else None}")
            
            # Extract Date Offers Due (CRITICAL)
            deadline = self._extract_deadline()
            metadata['date_offers_due'] = deadline.get('date') if deadline else None
            metadata['date_offers_due_time'] = deadline.get('time') if deadline else None
            metadata['date_offers_due_timezone'] = deadline.get('timezone') if deadline else None
            logger.info(f"Extracted deadline: {deadline}")
            
            # Extract Agency Information
            agency = self._extract_agency()
            metadata['agency'] = agency.get('department') if agency else None
            metadata['sub_tier'] = agency.get('sub_tier') if agency else None
            metadata['office'] = agency.get('office') if agency else None
            logger.info(f"Extracted agency: {agency}")
            
            # Extract Classification
            classification = self._extract_classification()
            metadata['set_aside'] = classification.get('set_aside') if classification else None
            metadata['naics_code'] = classification.get('naics_code') if classification else None
            metadata['psc_code'] = classification.get('psc_code') if classification else None
            
            # Extract Description
            description = self._extract_description()
            metadata['description'] = description
            logger.info(f"Extracted description: {len(description) if description else 0} chars")
            
            # Extract Published Date
            published_date = self._extract_published_date()
            metadata['published_date'] = published_date
            
            # Extract Status
            status = self._extract_status()
            metadata['status'] = status
            
            # Extract Contact Information
            contacts = self._extract_contacts()
            metadata['primary_contact'] = contacts.get('primary') if contacts else None
            metadata['alternative_contact'] = contacts.get('alternative') if contacts else None
            metadata['contracting_office_address'] = contacts.get('contracting_office_address') if contacts else None
            logger.info(f"Extracted contacts: primary={metadata.get('primary_contact') is not None}, alternative={metadata.get('alternative_contact') is not None}")
            
            logger.info(f"Metadata extraction complete. Keys: {list(metadata.keys())}, Non-null values: {sum(1 for v in metadata.values() if v)}")
            
        except Exception as e:
            logger.error(f"Error extracting metadata: {str(e)}", exc_info=True)
        
        return metadata
    
    def _extract_notice_id(self) -> Optional[str]:
        """Extract Notice ID from the page"""
        try:
            # Try multiple selectors based on HTML structure
            selectors = [
                '#notice-id',
                '[id*="notice"]',
                'h5:has-text("2031ZA26")',  # Pattern match
                '.sds-field__value:has-text("2031ZA26")'
            ]
            
            for selector in selectors:
                try:
                    element = self.page.query_selector(selector)
                    if element:
                        text = element.inner_text().strip()
                        # Extract notice ID pattern (alphanumeric, usually 15 chars)
                        match = re.search(r'([A-Z0-9]{10,20})', text)
                        if match:
                            return match.group(1)
                except:
                    continue
            
            # Fallback: search in page content
            content = self.page.content()
            match = re.search(r'Notice ID[\s\S]{0,200}?([A-Z0-9]{10,20})', content, re.IGNORECASE)
            if match:
                return match.group(1)
            
        except Exception as e:
            logger.warning(f"Could not extract Notice ID: {str(e)}")
        
        return None
    
    def _extract_title(self) -> Optional[str]:
        """Extract opportunity title"""
        try:
            # Title appears in card-title class
            selectors = [
                '.card-title',
                'h1.card-title',
                'h1[class*="title"]',
                '.contract-title'
            ]
            
            for selector in selectors:
                try:
                    element = self.page.query_selector(selector)
                    if element:
                        text = element.inner_text().strip()
                        if text and len(text) > 5:  # Reasonable title length
                            return text
                except:
                    continue
        except Exception as e:
            logger.warning(f"Could not extract title: {str(e)}")
        
        return None
    
    def _extract_deadline(self) -> Optional[Dict]:
        """
        Extract Date Offers Due - CRITICAL priority
        Returns: {'date': 'YYYY-MM-DD', 'time': 'HH:MM', 'timezone': 'EST'}
        """
        try:
            # Look for "Date Offers Due" field
            selectors = [
                '[id*="date-offers"]',
                '[id*="date_offers"]',
                '[aria-describedby*="date-offers"]',
                '.sds-field__value:has-text("PM")',
                '.sds-field__value:has-text("AM")'
            ]
            
            for selector in selectors:
                try:
                    # Find field label first
                    field = self.page.query_selector('[id="date-offers-date"]')
                    if field:
                        # Get value element
                        value_element = self.page.query_selector('[aria-describedby="date-offers-date"]')
                        if value_element:
                            text = value_element.inner_text().strip()
                            # Parse: "Feb 02, 2026 2:00 PM EST"
                            parsed = self._parse_deadline_text(text)
                            if parsed:
                                return parsed
                except:
                    continue
            
            # Fallback: regex search in page content
            content = self.page.content()
            # Pattern: Date Offers Due followed by date
            pattern = r'Date Offers Due[\s\S]{0,300}?(\w+\s+\d{1,2},\s+\d{4}\s+\d{1,2}:\d{2}\s+(?:AM|PM)\s+\w+)'
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                return self._parse_deadline_text(match.group(1))
            
        except Exception as e:
            logger.warning(f"Could not extract deadline: {str(e)}")
        
        return None
    
    def _parse_deadline_text(self, text: str) -> Optional[Dict]:
        """Parse deadline text like 'Feb 02, 2026 2:00 PM EST'"""
        try:
            # Pattern: "Feb 02, 2026 2:00 PM EST"
            pattern = r'(\w+)\s+(\d{1,2}),\s+(\d{4})\s+(\d{1,2}):(\d{2})\s+(AM|PM)\s+(\w+)'
            match = re.search(pattern, text)
            
            if match:
                month_str, day, year, hour, minute, am_pm, timezone = match.groups()
                
                # Convert month name to number
                months = {
                    'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
                    'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
                    'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
                }
                month = months.get(month_str[:3])
                
                if month:
                    # Convert 12-hour to 24-hour
                    hour_int = int(hour)
                    if am_pm.upper() == 'PM' and hour_int != 12:
                        hour_int += 12
                    elif am_pm.upper() == 'AM' and hour_int == 12:
                        hour_int = 0
                    
                    return {
                        'date': f"{year}-{month}-{day.zfill(2)}",
                        'time': f"{hour_int:02d}:{minute}",
                        'timezone': timezone
                    }
        except Exception as e:
            logger.warning(f"Could not parse deadline text '{text}': {str(e)}")
        
        return None
    
    def _extract_agency(self) -> Optional[Dict]:
        """Extract agency information"""
        try:
            agency_info = {}
            
            # Department/Ind. Agency
            dept = self.page.query_selector('[id="dept-agency"]')
            if dept:
                dept_value = self.page.query_selector('[aria-describedby="dept-agency"]')
                if dept_value:
                    agency_info['department'] = dept_value.inner_text().strip()
            
            # Sub-tier
            sub_tier = self.page.query_selector('[id="sub-tier"]')
            if sub_tier:
                sub_tier_value = self.page.query_selector('[aria-describedby="sub-tier"]')
                if sub_tier_value:
                    agency_info['sub_tier'] = sub_tier_value.inner_text().strip()
            
            # Office
            office = self.page.query_selector('[id="office"]')
            if office:
                office_value = self.page.query_selector('[aria-describedby="office"]')
                if office_value:
                    agency_info['office'] = office_value.inner_text().strip()
            
            return agency_info if agency_info else None
            
        except Exception as e:
            logger.warning(f"Could not extract agency: {str(e)}")
        
        return None
    
    def _extract_classification(self) -> Optional[Dict]:
        """Extract classification codes (NAICS, PSC, Set-Aside)"""
        try:
            classification = {}
            
            # Set Aside
            set_aside = self.page.query_selector('[id="set-aside"]')
            if set_aside:
                set_aside_value = self.page.query_selector('[aria-describedby="set-aside"]')
                if set_aside_value:
                    classification['set_aside'] = set_aside_value.inner_text().strip()
            
            # NAICS Code
            naics = self.page.query_selector('[id="naics"]')
            if naics:
                naics_value = self.page.query_selector('[aria-describedby="naics"]')
                if naics_value:
                    text = naics_value.inner_text().strip()
                    # Extract code like "332999 - Description"
                    match = re.search(r'(\d{6})', text)
                    if match:
                        classification['naics_code'] = match.group(1)
            
            # PSC Code
            psc = self.page.query_selector('[id="psc"]')
            if psc:
                psc_value = self.page.query_selector('[aria-describedby="psc"]')
                if psc_value:
                    text = psc_value.inner_text().strip()
                    # Extract code like "9999 - Description"
                    match = re.search(r'(\d{4})', text)
                    if match:
                        classification['psc_code'] = match.group(1)
            
            return classification if classification else None
            
        except Exception as e:
            logger.warning(f"Could not extract classification: {str(e)}")
        
        return None
    
    def _extract_description(self) -> Optional[str]:
        """Extract opportunity description"""
        try:
            desc_section = self.page.query_selector('[id="desc"]')
            if desc_section:
                desc_value = self.page.query_selector('[aria-describedby="desc"]')
                if desc_value:
                    return desc_value.inner_text().strip()
            
            # Fallback: look for description class
            desc = self.page.query_selector('.description, [class*="description"]')
            if desc:
                return desc.inner_text().strip()
                
        except Exception as e:
            logger.warning(f"Could not extract description: {str(e)}")
        
        return None
    
    def _extract_published_date(self) -> Optional[str]:
        """Extract published date"""
        try:
            published = self.page.query_selector('[id="published-date"]')
            if published:
                published_value = self.page.query_selector('[aria-describedby="published-date"]')
                if published_value:
                    return published_value.inner_text().strip()
        except Exception as e:
            logger.warning(f"Could not extract published date: {str(e)}")
        
        return None
    
    def _extract_status(self) -> Optional[str]:
        """Extract opportunity status"""
        try:
            status_tag = self.page.query_selector('.sds-tag--status, [class*="status"]')
            if status_tag:
                return status_tag.inner_text().strip()
        except Exception as e:
            logger.warning(f"Could not extract status: {str(e)}")
        
        return None
    
    def _extract_contacts(self) -> Optional[Dict]:
        """Extract contact information - for future phases"""
        try:
            contacts = {}
            
            # Primary Point of Contact
            try:
                primary_poc_label = self.page.query_selector('[id="primary-poc"]')
                if primary_poc_label:
                    # Find the contact card near the label
                    # The structure is: label -> contact card with name, email, phone
                    parent = primary_poc_label.evaluate_handle('el => el.closest(".grid-row, .section-content")')
                    
                    # Find name (usually in .contact-title-2 or h5)
                    name_element = self.page.query_selector('[id="primary-poc"]').evaluate_handle('''
                        (label) => {
                            const container = label.closest('.grid-row, .section-content');
                            if (container) {
                                const nameEl = container.querySelector('.contact-title-2, h5');
                                return nameEl ? nameEl.innerText.trim() : null;
                            }
                            return null;
                        }
                    ''')
                    
                    # Try direct selector for name
                    name_selectors = [
                        '.contact-title-2',
                        'h5.contact-title-2',
                        '[aria-describedby="primary-poc"] .contact-title-2',
                        '[aria-describedby="primary-poc"] h5'
                    ]
                    
                    name = None
                    for selector in name_selectors:
                        try:
                            name_el = self.page.query_selector(f'[id="primary-poc"] ~ * {selector}, [aria-describedby="primary-poc"] {selector}')
                            if not name_el:
                                # Try finding in same section
                                poc_section = self.page.query_selector('[id="primary-poc"]')
                                if poc_section:
                                    parent = poc_section.evaluate_handle('el => el.closest("div")')
                                    name_el = self.page.query_selector(selector)
                            if name_el:
                                name = name_el.inner_text().strip()
                                if name and name != '(blank)':
                                    break
                        except:
                            continue
                    
                    # Find email
                    email_selectors = [
                        '[aria-describedby="email"]',
                        '.sds-field__value:has-text("@")',
                    ]
                    
                    email = None
                    # Look for email near primary-poc
                    try:
                        # Try to find email in the same section as primary-poc
                        primary_section = self.page.query_selector('[id="primary-poc"]')
                        if primary_section:
                            # Find all email elements and match by context
                            all_email_elements = self.page.query_selector_all('[aria-describedby="email"]')
                            if all_email_elements:
                                # Usually the first email element after primary-poc is the primary contact's email
                                for email_el in all_email_elements:
                                    email_text = email_el.inner_text().strip()
                                    if '@' in email_text and email_text != '(blank)':
                                        email = email_text
                                        break
                    except Exception as e:
                        logger.warning(f"Could not extract primary email: {e}")
                    
                    # Find phone
                    phone_selectors = [
                        '[aria-describedby="phone"]',
                    ]
                    
                    phone = None
                    try:
                        all_phone_elements = self.page.query_selector_all('[aria-describedby="phone"]')
                        if all_phone_elements:
                            # Usually the first phone element after primary-poc is the primary contact's phone
                            for phone_el in all_phone_elements:
                                phone_text = phone_el.inner_text().strip()
                                if phone_text and phone_text != '(blank)':
                                    phone = phone_text
                                    break
                    except Exception as e:
                        logger.warning(f"Could not extract primary phone: {e}")
                    
                    if name or email or phone:
                        contacts['primary'] = {
                            'name': name if name and name != '(blank)' else None,
                            'email': email if email and email != '(blank)' else None,
                            'phone': phone if phone and phone != '(blank)' else None
                        }
            except Exception as e:
                logger.warning(f"Could not extract primary contact: {e}")
            
            # Alternative Point of Contact
            try:
                alt_poc_label = self.page.query_selector('[id="alt-poc"]')
                if alt_poc_label:
                    # Similar extraction for alternative contact
                    alt_name = None
                    alt_email = None
                    alt_phone = None
                    
                    # Find name
                    alt_name_el = self.page.query_selector('[aria-describedby="alt-poc"] .contact-title-2, [aria-describedby="alt-poc"] h5')
                    if alt_name_el:
                        alt_name = alt_name_el.inner_text().strip()
                        if alt_name == '(blank)':
                            alt_name = None
                    
                    # Find email and phone (usually after primary contact fields)
                    all_email_elements = self.page.query_selector_all('[aria-describedby="email"]')
                    all_phone_elements = self.page.query_selector_all('[aria-describedby="phone"]')
                    
                    # Usually the second set of email/phone is alternative contact
                    if len(all_email_elements) > 1:
                        alt_email_text = all_email_elements[1].inner_text().strip()
                        if '@' in alt_email_text and alt_email_text != '(blank)':
                            alt_email = alt_email_text
                    
                    if len(all_phone_elements) > 1:
                        alt_phone_text = all_phone_elements[1].inner_text().strip()
                        if alt_phone_text and alt_phone_text != '(blank)':
                            alt_phone = alt_phone_text
                    
                    if alt_name or alt_email or alt_phone:
                        contacts['alternative'] = {
                            'name': alt_name if alt_name and alt_name != '(blank)' else None,
                            'email': alt_email if alt_email and alt_email != '(blank)' else None,
                            'phone': alt_phone if alt_phone and alt_phone != '(blank)' else None
                        }
            except Exception as e:
                logger.warning(f"Could not extract alternative contact: {e}")
            
            # Contracting Office Address
            try:
                office_address_label = self.page.query_selector('[id="contract-office"]')
                if office_address_label:
                    # Extract address lines (usually multiple lines)
                    address_lines = []
                    address_elements = self.page.query_selector_all('[aria-describedby="contract-office"] h6, [aria-describedby="contract-office"] .value-new-line')
                    
                    for addr_el in address_elements:
                        addr_text = addr_el.inner_text().strip()
                        if addr_text and addr_text != '(blank)' and '(No Street Address' not in addr_text:
                            address_lines.append(addr_text)
                    
                    if address_lines:
                        contacts['contracting_office_address'] = '\n'.join(address_lines)
            except Exception as e:
                logger.warning(f"Could not extract contracting office address: {e}")
            
            return contacts if contacts else None
            
        except Exception as e:
            logger.warning(f"Could not extract contacts: {str(e)}", exc_info=True)
        
        return None
    
    def _extract_page_text(self) -> Optional[str]:
        """
        Extract COMPLETE raw text content from the SAM.gov page for LLM analysis.
        This is separate from metadata extraction - extracts ALL visible text from the page.
        """
        try:
            # Get complete raw text from the entire page body
            # This extracts ALL visible text including headers, descriptions, deadlines, etc.
            try:
                # Get all text from body element - this includes everything visible on the page
                body = self.page.query_selector('body')
                if body:
                    # Use inner_text() to get all visible text content
                    # This includes all text from all elements: headers, paragraphs, tables, lists, etc.
                    complete_text = body.inner_text()
                    
                    if complete_text and len(complete_text.strip()) > 50:
                        logger.info(f"Extracted {len(complete_text)} characters of complete raw text from SAM.gov page")
                        return complete_text
                    else:
                        logger.warning(f"Extracted text too short ({len(complete_text) if complete_text else 0} chars)")
                else:
                    logger.warning("Could not find body element on SAM.gov page")
            except Exception as body_error:
                logger.warning(f"Error extracting text from body: {str(body_error)}")
            
            # Fallback: try to get page content using page.content() and extract text
            try:
                # Get HTML content and extract text from it
                html_content = self.page.content()
                # Try BeautifulSoup if available for better text extraction
                try:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(html_content, 'html.parser')
                    # Remove script and style elements
                    for script in soup(["script", "style"]):
                        script.decompose()
                    text = soup.get_text()
                    # Clean up whitespace
                    lines = (line.strip() for line in text.splitlines())
                    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                    text = '\n'.join(chunk for chunk in chunks if chunk)
                    
                    if text and len(text.strip()) > 50:
                        logger.info(f"Extracted {len(text)} characters from SAM.gov page using BeautifulSoup fallback")
                        return text
                except ImportError:
                    # BeautifulSoup not available - use simple regex to extract text from HTML
                    import re
                    # Remove script and style tags
                    text = re.sub(r'<script[^>]*>.*?</script>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
                    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
                    # Extract text content between tags
                    text = re.sub(r'<[^>]+>', '\n', text)
                    # Clean up whitespace
                    lines = (line.strip() for line in text.splitlines())
                    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                    text = '\n'.join(chunk for chunk in chunks if chunk)
                    
                    if text and len(text.strip()) > 50:
                        logger.info(f"Extracted {len(text)} characters from SAM.gov page using regex fallback")
                        return text
            except Exception as html_error:
                logger.warning(f"Error extracting text from HTML: {str(html_error)}")
            
            logger.warning("Could not extract text from SAM.gov page using any method")
            return None
                
        except Exception as e:
            logger.warning(f"Error extracting page text: {str(e)}")
            return None
    
    def _extract_attachments(self) -> List[Dict]:
        """
        Extract attachment links - PRIMARY DATA SOURCE
        Returns list of attachment dictionaries
        Note: SAM.gov uses Angular, so links may not have href initially
        """
        attachments = []
        
        try:
            logger.info(f"DEBUG: Starting attachment extraction")
            
            # Wait for Angular to fully render the attachments table
            try:
                self.page.wait_for_selector('#tblDesc', timeout=15000)
                # Wait for Angular to populate the table
                self.page.wait_for_timeout(3000)  # Give Angular 3 seconds to render
                logger.info(f"DEBUG: Attachments table found after waiting")
            except Exception as e:
                logger.warning(f"DEBUG: Table not found after wait: {e}")
            
            # Find attachments table using exact ID from HTML
            table = self.page.query_selector('#tblDesc')
            
            if not table:
                # Try alternative selectors
                table = self.page.query_selector('table[aria-describedby="att-table"]')
            
            if table:
                logger.info(f"DEBUG: Found attachments table")
                
                # Get all rows in tbody (skip header)
                rows = table.query_selector_all('tbody tr')
                logger.info(f"DEBUG: Found {len(rows)} tbody rows")
                
                # If no tbody rows, try all rows and skip header
                if not rows:
                    all_rows = table.query_selector_all('tr')
                    logger.info(f"DEBUG: No tbody rows, found {len(all_rows)} total rows")
                    if all_rows:
                        # Skip header row if it has th elements
                        first_row = all_rows[0]
                        if first_row.query_selector_all('th'):
                            rows = all_rows[1:]
                            logger.info(f"DEBUG: Skipped header row, {len(rows)} data rows remaining")
                        else:
                            rows = all_rows
                
                logger.info(f"DEBUG: Processing {len(rows)} attachment rows")
                
                for idx, row in enumerate(rows):
                    try:
                        attachment = {}
                        
                        # Get all cells in the row
                        cells = row.query_selector_all('td')
                        if not cells:
                            logger.warning(f"DEBUG: Row {idx + 1} has no cells, skipping")
                            continue
                        
                        logger.info(f"DEBUG: Row {idx + 1} has {len(cells)} cells")
                        
                        # First cell contains the file link (may be nested in divs)
                        first_cell = cells[0]
                        first_cell_text = first_cell.inner_text().strip()
                        
                        logger.info(f"DEBUG: Row {idx + 1} first cell text: '{first_cell_text[:50]}...'")
                        
                        # Check if it's a deleted file
                        if '(deleted)' in first_cell_text.lower():
                            logger.info(f"DEBUG: Row {idx + 1} is deleted file, skipping")
                            continue
                        
                        # Look for file-link class anchor (may be nested)
                        link_element = None
                        
                        # Try multiple ways to find the link
                        # Method 1: Direct query in first cell
                        link_element = first_cell.query_selector('a.file-link')
                        if not link_element:
                            # Method 2: Any link in first cell
                            link_element = first_cell.query_selector('a')
                        
                        if link_element:
                            # Get filename from link text
                            attachment['name'] = link_element.inner_text().strip()
                            logger.info(f"DEBUG: Row {idx + 1} found link with name: '{attachment['name']}'")
                        else:
                            # No link element, but first cell text might be filename
                            if '.' in first_cell_text and any(ext in first_cell_text.lower() for ext in ['.pdf', '.doc', '.docx', '.xls', '.xlsx']):
                                attachment['name'] = first_cell_text.replace('(deleted)', '').strip()
                                logger.warning(f"DEBUG: Row {idx + 1} found filename in text but no link: '{attachment['name']}'")
                            else:
                                logger.warning(f"DEBUG: Row {idx + 1} first cell doesn't look like a filename: '{first_cell_text}'")
                                continue
                        
                        # Try to get href from link (may not exist for Angular links)
                        href = None
                        if link_element:
                            href = link_element.get_attribute('href')
                            logger.info(f"DEBUG: Row {idx + 1} link href: '{href}'")
                        
                        # If no href, try to get from Angular's JavaScript state or construct URL
                        if not href or href == '#' or href == '':
                            # Try to get download URL via JavaScript evaluation
                            # SAM.gov likely stores attachment URLs in Angular component state
                            try:
                                # Evaluate JavaScript to get download URLs from Angular state
                                # We'll try to access the Angular component's data
                                js_result = self.page.evaluate('''() => {
                                    // Try to find file links and get their actual hrefs after Angular renders
                                    const links = document.querySelectorAll('a.file-link');
                                    const results = [];
                                    links.forEach((link, index) => {
                                        const href = link.getAttribute('href');
                                        const name = link.innerText.trim();
                                        results.push({index, name, href: href || null});
                                    });
                                    return results;
                                }''')
                                
                                logger.info(f"DEBUG: JavaScript evaluation found {len(js_result)} links")
                                
                                # Match this row's link by index or name
                                if js_result and idx < len(js_result):
                                    js_link = js_result[idx]
                                    if js_link and js_link.get('href'):
                                        href = js_link['href']
                                        logger.info(f"DEBUG: Row {idx + 1} got href from JS: '{href}'")
                                
                            except Exception as e:
                                logger.warning(f"DEBUG: Could not evaluate JavaScript for download URLs: {e}")
                            
                            # If still no href, construct download URL based on pattern
                            if not href or href == '#' or href == '':
                                import re
                                # Extract opportunity ID from current page URL
                                # Pattern: /workspace/contract/opp/{id}/view
                                opp_id_match = re.search(r'/opp/([^/]+)', self.page.url)
                                if opp_id_match:
                                    opp_id = opp_id_match.group(1)
                                    filename = attachment.get('name', '').strip()
                                    
                                    # SAM.gov download URL pattern (verify this works)
                                    # Common patterns:
                                    # /workspace/contract/opp/{id}/attachment/download/{filename}
                                    # /workspace/contract/opp/{id}/download/{filename}
                                    # /workspace/contract/opp/{id}/file/{filename}
                                    
                                    # URL-encode the filename (spaces and special chars)
                                    encoded_filename = quote(filename, safe='')
                                    
                                    # Try most common pattern first
                                    href = f"{self.base_url}/workspace/contract/opp/{opp_id}/attachment/download/{encoded_filename}"
                                    logger.warning(f"DEBUG: Row {idx + 1} constructed URL with encoded filename: '{href}'")
                        
                        attachment['url'] = href
                        
                        # Resolve relative URLs
                        if attachment['url'] and not attachment['url'].startswith('http'):
                            attachment['url'] = urljoin(self.base_url, attachment['url'])
                        
                        # Extract file size from second column (index 1)
                        if len(cells) > 1:
                            size_cell = cells[1]
                            size_text = size_cell.inner_text().strip()
                            if size_text and ('kb' in size_text.lower() or 'mb' in size_text.lower() or 'gb' in size_text.lower()):
                                attachment['size'] = size_text
                                logger.info(f"DEBUG: Row {idx + 1} file size: '{size_text}'")
                        
                        # Extract access level from third column (index 2)
                        if len(cells) > 2:
                            access_cell = cells[2]
                            access_text = access_cell.inner_text().strip()
                            if access_text and ('public' in access_text.lower() or 'private' in access_text.lower()):
                                attachment['access'] = access_text
                        
                        # Extract updated date from last column
                        if cells and len(cells) > 3:
                            last_cell = cells[-1]
                            date_text = last_cell.inner_text().strip()
                            if date_text:
                                attachment['updated_date'] = date_text
                        
                        # Determine file type from name
                        if attachment.get('name'):
                            name_lower = attachment['name'].lower()
                            if name_lower.endswith('.pdf'):
                                attachment['type'] = 'pdf'
                            elif name_lower.endswith(('.doc', '.docx')):
                                attachment['type'] = 'word'
                            elif name_lower.endswith(('.xls', '.xlsx')):
                                attachment['type'] = 'excel'
                            else:
                                attachment['type'] = 'unknown'
                        
                        # Only add if we have a name and URL
                        name = attachment.get('name', '').strip()
                        url = attachment.get('url', '').strip()
                        
                        if name and url and url != '#' and url != '':
                            # Skip deleted files
                            if 'deleted' not in name.lower():
                                attachments.append(attachment)
                                logger.info(f"DEBUG: ✅ Added attachment {len(attachments)}: name='{name}', url='{url[:80]}...'")
                            else:
                                logger.info(f"DEBUG: Skipped deleted file: '{name}'")
                        else:
                            logger.warning(f"DEBUG: Row {idx + 1} missing name or URL: name='{name}', url='{url}'")
                    
                    except Exception as e:
                        logger.error(f"Error parsing attachment row {idx + 1}: {str(e)}", exc_info=True)
                        continue
            
            # Fallback: search for file links directly if table parsing failed
            if not attachments:
                logger.info(f"DEBUG: No attachments from table, trying fallback: searching all file links")
                file_links = self.page.query_selector_all('a.file-link')
                logger.info(f"DEBUG: Fallback found {len(file_links)} file links")
                
                for link in file_links:
                    try:
                        name = link.inner_text().strip()
                        href = link.get_attribute('href')
                        
                        if name and '(deleted)' not in name.lower():
                            if not href or href == '#' or href == '':
                                # Construct URL with URL-encoded filename
                                import re
                                opp_id_match = re.search(r'/opp/([^/]+)', self.page.url)
                                if opp_id_match:
                                    opp_id = opp_id_match.group(1)
                                    encoded_name = quote(name, safe='')
                                    href = f"{self.base_url}/workspace/contract/opp/{opp_id}/attachment/download/{encoded_name}"
                                
                            if href and href != '#' and href != '':
                                attachments.append({
                                    'name': name,
                                    'url': urljoin(self.base_url, href) if not href.startswith('http') else href,
                                    'type': 'unknown'
                                })
                                logger.info(f"DEBUG: Fallback added attachment: '{name}'")
                    except Exception as e:
                        logger.warning(f"Error in fallback link extraction: {e}")
                        continue
        
        except Exception as e:
            logger.error(f"Error extracting attachments: {str(e)}", exc_info=True)
        
        logger.info(f"DEBUG: ✅ Extracted {len(attachments)} attachments total")
        if attachments:
            for idx, att in enumerate(attachments):
                logger.info(f"DEBUG: Attachment {idx + 1}: name='{att.get('name')}', url='{att.get('url', '')[:80]}...', type='{att.get('type')}'")
        else:
            logger.warning(f"DEBUG: ❌ No attachments extracted - table={table is not None}")
            # Log page HTML snippet for debugging
            try:
                table_html = self.page.query_selector('#tblDesc')
                if table_html:
                    html_preview = table_html.inner_html()[:500]
                    logger.info(f"DEBUG: Table HTML preview: {html_preview}...")
            except:
                pass
        
        return attachments
    
    def download_attachment(self, url: str, save_path: Path) -> bool:
        """
        Download a single attachment file
        
        Args:
            url: URL of the file to download
            save_path: Path where file should be saved
            
        Returns:
            bool: True if successful
        """
        try:
            # Create directory if it doesn't exist
            save_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Download file - use 'load' instead of 'networkidle' for better reliability
            with self.page.expect_download() as download_info:
                self.page.goto(url, wait_until='load', timeout=60000)
            
            download = download_info.value
            download.save_as(str(save_path))
            
            logger.info(f"Downloaded {url} to {save_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error downloading {url}: {str(e)}")
            return False
