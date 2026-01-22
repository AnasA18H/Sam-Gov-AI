"""
Document downloader service
Handles downloading and storing SAM.gov attachments
"""
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import requests
from urllib.parse import urlparse, urljoin
from playwright.sync_api import Page
import zipfile
import shutil

from ..core.config import settings

logger = logging.getLogger(__name__)


class DocumentDownloader:
    """Service to download and store documents"""
    
    def __init__(self, storage_base_path: Path = None, page: Optional[Page] = None):
        """
        Initialize document downloader
        
        Args:
            storage_base_path: Base path for storing documents locally
            page: Optional Playwright page object for authenticated downloads
        """
        if storage_base_path is None:
            storage_base_path = Path(settings.STORAGE_BASE_PATH) if hasattr(settings, 'STORAGE_BASE_PATH') else Path('backend/data/documents')
        
        self.storage_base_path = Path(storage_base_path)
        self.storage_base_path.mkdir(parents=True, exist_ok=True)
        self.page = page  # Playwright page for authenticated downloads
        logger.info(f"DEBUG: DocumentDownloader initialized - storage_base_path: {self.storage_base_path} (exists: {self.storage_base_path.exists()})")
    
    def download_document(self, url: str, opportunity_id: int, filename: str = None) -> Optional[Dict]:
        """
        Download a document from URL and save it
        Handles three cases:
        1. PDF viewer - direct PDF download
        2. Webpage with download link - find and download PDF
        3. Webpage with text only - scrape and save as TXT
        
        Args:
            url: Document URL
            opportunity_id: ID of the opportunity this document belongs to
            filename: Optional filename (will extract from URL if not provided)
            
        Returns:
            dict with file info: {'path': str, 'size': int, 'name': str} or None if failed
        """
        try:
            # Generate filename if not provided
            if not filename:
                filename = Path(urlparse(url).path).name
                if not filename or filename == '/':
                    filename = f"document_{opportunity_id}_{datetime.now().timestamp()}"
            
            # Sanitize filename
            filename = self._sanitize_filename(filename)
            
            # Create opportunity-specific directory
            opp_dir = self.storage_base_path / str(opportunity_id)
            opp_dir.mkdir(parents=True, exist_ok=True)
            
            # If we have Playwright, use smart download with case detection
            if self.page:
                return self._download_with_playwright(url, opportunity_id, filename, opp_dir)
            else:
                # Fallback to simple requests download
                return self._download_with_requests(url, opportunity_id, filename, opp_dir)
            
        except Exception as e:
            logger.error(f"Error downloading document from {url}: {str(e)}", exc_info=True)
            return None
    
    def _download_with_playwright(self, url: str, opportunity_id: int, filename: str, opp_dir: Path, max_depth: int = 3, current_depth: int = 0) -> Optional[Dict]:
        """
        Download using Playwright with smart case detection
        Tries in order: Case 1 (direct PDF) -> Case 2 (find PDF link) -> Case Download Button -> Case 0 (handle agreement) -> Case 3 (extract text as last resort)
        
        Case 0 is only used when no links, download buttons, or PDFs are found - right before extracting text.
        This handles pages with disclaimers that need to be accepted before data extraction.
        
        Args:
            url: URL to download from
            opportunity_id: Opportunity ID
            filename: Target filename
            opp_dir: Output directory
            max_depth: Maximum recursion depth (default: 3)
            current_depth: Current recursion depth (default: 0)
        """
        try:
            # Prevent infinite recursion
            if current_depth >= max_depth:
                logger.warning(f"Maximum recursion depth ({max_depth}) reached for {url}")
                return None
            # CASE 1: Check if URL is a direct PDF BEFORE navigating
            # This handles PDFs that auto-download when navigated to
            if url.lower().endswith('.pdf'):
                logger.info(f"Case 1: URL is direct PDF, attempting download before navigation")
                result = self._try_case1_direct_pdf(url, filename, opp_dir)
                if result:
                    logger.info(f"✅ Case 1 succeeded: Direct PDF download")
                    return result
            
            logger.info(f"Navigating to {url} to detect download type")
            self.page.goto(url, wait_until='load', timeout=60000)
            self.page.wait_for_timeout(2000)  # Wait for page to fully load
            
            # CASE 1: Try direct PDF download (PDF viewer or direct PDF URL)
            # Only if we haven't tried it already
            if not url.lower().endswith('.pdf'):
                result = self._try_case1_direct_pdf(url, filename, opp_dir)
                if result:
                    logger.info(f"✅ Case 1 succeeded: Direct PDF download")
                    return result
            
            logger.info(f"Case 1 failed, trying Case 2: Find PDF link on page")
            
            # CASE 2: Look for PDF download links on the page
            result = self._try_case2_find_pdf_link(url, filename, opp_dir, current_depth, max_depth, opportunity_id)
            if result:
                logger.info(f"✅ Case 2 succeeded: Found and downloaded PDF from page")
                return result
            
            logger.info(f"Case 2 failed, trying Case Download Button: Check for download buttons")
            
            # CASE DOWNLOAD BUTTON: Look for download buttons on the page
            result = self._try_case_download_button(url, filename, opp_dir, current_depth, max_depth, opportunity_id)
            if result:
                logger.info(f"✅ Case Download Button succeeded: Found and clicked download button")
                return result
            
            logger.info(f"Case Download Button failed. No links or download buttons found.")
            logger.info(f"Case 0: Checking for agreement/disclaimer (only when no other options available)")
            
            # CASE 0: Handle agreement/disclaimer dialogs ONLY when no links/buttons/PDFs found
            # This is for pages with just data that might have a disclaimer blocking access
            agreement_handled = self._try_case0_handle_agreement()
            if agreement_handled:
                logger.info(f"✅ Case 0: Handled agreement/disclaimer, waiting for page to update")
                self.page.wait_for_timeout(2000)  # Wait for page to update after agreement
                
                # After handling agreement, the page might now have links/PDFs available
                # Re-check all cases again since the page content may have changed
                logger.info(f"Case 0: Re-checking for PDFs/links after agreement was accepted")
                
                # Re-check Case 1: Direct PDF download (PDF viewer might be revealed)
                result = self._try_case1_direct_pdf(url, filename, opp_dir)
                if result:
                    logger.info(f"✅ Case 1 succeeded after Case 0: Direct PDF download")
                    return result
                
                # Re-check Case 2: Look for PDF download links (might be revealed after agreement)
                result = self._try_case2_find_pdf_link(url, filename, opp_dir, current_depth, max_depth, opportunity_id)
                if result:
                    logger.info(f"✅ Case 2 succeeded after Case 0: Found and downloaded PDF from page")
                    return result
                
                # Re-check Case Download Button: Look for download buttons (might be revealed after agreement)
                result = self._try_case_download_button(url, filename, opp_dir, current_depth, max_depth, opportunity_id)
                if result:
                    logger.info(f"✅ Case Download Button succeeded after Case 0: Found and clicked download button")
                    return result
                
                logger.info(f"Case 0: After agreement, still no PDFs/links found, proceeding to text extraction")
            
            logger.info(f"Trying Case 3: Extract text content (last resort)")
            
            # CASE 3: Extract text content and save as TXT (LAST RESORT)
            result = self._try_case3_extract_text(url, filename, opp_dir)
            if result:
                logger.info(f"✅ Case 3 succeeded: Extracted and saved text content")
                return result
            
            logger.warning(f"All cases failed for {url}")
            return None
                
        except Exception as e:
            logger.error(f"Error in Playwright download: {str(e)}", exc_info=True)
            return None
    
    def _try_case0_handle_agreement(self) -> bool:
        """
        Case 0: Handle agreement/disclaimer dialogs or statements that must be accepted
        This is ONLY used when no links, download buttons, or PDFs are found on the page.
        Used right before Case 3 (text extraction) to handle disclaimers that might block data access.
        Returns True if an agreement was found and handled, False otherwise
        """
        try:
            # Wait a bit for any modals/dialogs to appear
            self.page.wait_for_timeout(1000)
            
            # Common agreement/disclaimer button texts (case-insensitive)
            agreement_texts = [
                'ok', 'agree', 'accept', 'i agree', 'i accept', 'continue', 'proceed',
                'acknowledge', 'acknowledged', 'understood', 'yes', 'confirm',
                'accept terms', 'accept and continue', 'agree and continue',
                'i understand', 'accept disclaimer', 'accept agreement'
            ]
            
            # Look for buttons with agreement text
            # Try multiple selectors to find agreement buttons
            selectors_to_try = [
                # Common button selectors
                'button',
                'input[type="button"]',
                'input[type="submit"]',
                'a.button',
                '.btn',
                '.button',
                '[role="button"]',
                # Modal/dialog specific
                '.modal button',
                '.dialog button',
                '#dialog button',
                '#modal button',
                '[class*="modal"] button',
                '[class*="dialog"] button',
                '[id*="modal"] button',
                '[id*="dialog"] button',
            ]
            
            agreement_found = False
            
            for selector in selectors_to_try:
                try:
                    # Get all buttons matching the selector
                    buttons = self.page.query_selector_all(selector)
                    
                    for button in buttons:
                        try:
                            # Get button text (multiple ways)
                            button_text = ''
                            
                            # Try inner text
                            inner_text = button.inner_text()
                            if inner_text:
                                button_text = inner_text.strip().lower()
                            
                            # Try text content if inner_text is empty
                            if not button_text:
                                text_content = button.evaluate('el => el.textContent')
                                if text_content:
                                    button_text = text_content.strip().lower()
                            
                            # Try value attribute for input buttons
                            if not button_text:
                                value = button.get_attribute('value')
                                if value:
                                    button_text = value.strip().lower()
                            
                            # Try aria-label
                            if not button_text:
                                aria_label = button.get_attribute('aria-label')
                                if aria_label:
                                    button_text = aria_label.strip().lower()
                            
                            # Check if button text matches any agreement phrase
                            for agreement_phrase in agreement_texts:
                                if agreement_phrase in button_text:
                                    logger.info(f"Case 0: Found agreement button with text: '{button_text}'")
                                    
                                    # FIRST: Check if there are checkboxes that need to be checked before clicking
                                    # Some sites require checking a checkbox before the button becomes clickable
                                    try:
                                        checkboxes = self.page.query_selector_all('input[type="checkbox"]')
                                        for checkbox in checkboxes:
                                            try:
                                                # Check if checkbox is related to agreement/terms
                                                checkbox_id = checkbox.get_attribute('id') or ''
                                                checkbox_name = checkbox.get_attribute('name') or ''
                                                checkbox_label = ''
                                                
                                                # Try to find associated label
                                                if checkbox_id:
                                                    label = self.page.query_selector(f'label[for="{checkbox_id}"]')
                                                    if label:
                                                        checkbox_label = label.inner_text().strip().lower()
                                                
                                                # Check if it's an agreement checkbox
                                                agreement_keywords = ['agree', 'accept', 'terms', 'conditions', 'disclaimer', 'acknowledge']
                                                if any(keyword in checkbox_label or keyword in checkbox_id.lower() or keyword in checkbox_name.lower() for keyword in agreement_keywords):
                                                    # Check if checkbox is not already checked
                                                    is_checked = checkbox.evaluate('el => el.checked')
                                                    if not is_checked:
                                                        checkbox.evaluate('el => el.click()')
                                                        logger.info(f"Case 0: Checked agreement checkbox")
                                                        self.page.wait_for_timeout(500)
                                            except Exception as cb_error:
                                                logger.debug(f"Case 0: Error checking checkbox: {cb_error}")
                                    except Exception as cb_error:
                                        logger.debug(f"Case 0: Error finding checkboxes: {cb_error}")
                                    
                                    # Scroll into view
                                    try:
                                        button.scroll_into_view_if_needed()
                                        self.page.wait_for_timeout(500)
                                    except:
                                        pass
                                    
                                    # Click the agreement button
                                    try:
                                        button.click(timeout=5000)
                                        logger.info(f"Case 0: Clicked agreement button: '{button_text}'")
                                        agreement_found = True
                                        
                                        # Wait for any modal/dialog to close
                                        self.page.wait_for_timeout(1500)
                                        
                                        break  # Found and clicked agreement button
                                    except Exception as click_error:
                                        logger.info(f"Case 0: Could not click button '{button_text}': {click_error}")
                                        # Try JavaScript click as fallback
                                        try:
                                            self.page.evaluate('el => el.click()', button)
                                            logger.info(f"Case 0: Clicked agreement button via JavaScript: '{button_text}'")
                                            agreement_found = True
                                            self.page.wait_for_timeout(1500)
                                            break
                                        except:
                                            pass
                                    
                                    if agreement_found:
                                        break
                            
                            if agreement_found:
                                break
                        except Exception as btn_error:
                            logger.debug(f"Case 0: Error processing button: {btn_error}")
                            continue
                    
                    if agreement_found:
                        break
                except Exception as selector_error:
                    logger.debug(f"Case 0: Error with selector '{selector}': {selector_error}")
                    continue
            
            # Also check for common modal/dialog patterns that might contain agreements
            if not agreement_found:
                try:
                    # Look for modals with agreement text
                    modal_selectors = [
                        '.modal',
                        '.dialog',
                        '[role="dialog"]',
                        '[class*="modal"]',
                        '[class*="dialog"]',
                        '[id*="modal"]',
                        '[id*="dialog"]',
                    ]
                    
                    for modal_selector in modal_selectors:
                        try:
                            modal = self.page.query_selector(modal_selector)
                            if modal and modal.is_visible():
                                modal_text = modal.inner_text().lower()
                                # Check if modal contains agreement-related text
                                if any(keyword in modal_text for keyword in ['agree', 'accept', 'terms', 'conditions', 'disclaimer', 'acknowledge']):
                                    logger.info(f"Case 0: Found agreement modal/dialog")
                                    # Try to find and click agreement button in modal using scoped selectors
                                    modal_selector_base = modal_selector
                                    button_selectors = [
                                        f'{modal_selector_base} button',
                                        f'{modal_selector_base} input[type="button"]',
                                        f'{modal_selector_base} input[type="submit"]',
                                        f'{modal_selector_base} a.button',
                                        f'{modal_selector_base} .btn',
                                    ]
                                    
                                    for btn_selector in button_selectors:
                                        try:
                                            modal_buttons = self.page.query_selector_all(btn_selector)
                                            for btn in modal_buttons:
                                                try:
                                                    btn_text = btn.inner_text().strip().lower()
                                                    if not btn_text:
                                                        btn_text = btn.get_attribute('value') or btn.get_attribute('aria-label') or ''
                                                        btn_text = btn_text.strip().lower()
                                                    
                                                    if btn_text and any(phrase in btn_text for phrase in agreement_texts):
                                                        try:
                                                            btn.scroll_into_view_if_needed()
                                                            self.page.wait_for_timeout(500)
                                                            btn.click(timeout=5000)
                                                            logger.info(f"Case 0: Clicked agreement button in modal: '{btn_text}'")
                                                            agreement_found = True
                                                            self.page.wait_for_timeout(1500)
                                                            break
                                                        except Exception as click_err:
                                                            # Try JavaScript click
                                                            try:
                                                                self.page.evaluate('el => el.click()', btn)
                                                                logger.info(f"Case 0: Clicked agreement button in modal via JS: '{btn_text}'")
                                                                agreement_found = True
                                                                self.page.wait_for_timeout(1500)
                                                                break
                                                            except:
                                                                pass
                                                except:
                                                    continue
                                            if agreement_found:
                                                break
                                        except:
                                            continue
                                if agreement_found:
                                    break
                        except:
                            continue
                except Exception as modal_error:
                    logger.debug(f"Case 0: Error checking modals: {modal_error}")
            
            if agreement_found:
                logger.info(f"✅ Case 0: Successfully handled agreement/disclaimer")
            else:
                logger.info(f"Case 0: No agreement/disclaimer found to handle")
            
            return agreement_found
            
        except Exception as e:
            logger.warning(f"Case 0: Error handling agreement: {e}")
            return False
    
    def _try_case1_direct_pdf(self, url: str, filename: str, opp_dir: Path) -> Optional[Dict]:
        """Case 1: Try direct PDF download (PDF viewer or direct PDF URL)"""
        try:
            # Check if URL directly serves a PDF
            if url.lower().endswith('.pdf'):
                logger.info(f"Case 1: URL appears to be direct PDF, attempting download")
                try:
                    # For direct PDF URLs, expect download BEFORE navigating
                    # This handles the case where navigation triggers immediate download
                    with self.page.expect_download(timeout=30000) as download_info:
                        # Use 'networkidle' or 'domcontentloaded' instead of 'load' for PDFs
                        # because PDFs trigger downloads and don't fully "load" as pages
                        try:
                            self.page.goto(url, wait_until='domcontentloaded', timeout=60000)
                        except Exception as nav_error:
                            # If navigation fails because download started, that's actually good
                            # The download_info should have the download
                            if "Download is starting" not in str(nav_error):
                                raise
                    
                    download = download_info.value
                    file_path = opp_dir / filename
                    if not file_path.suffix.lower() == '.pdf':
                        file_path = file_path.with_suffix('.pdf')
                    download.save_as(str(file_path))
                    file_size = file_path.stat().st_size
                    
                    if file_size > 0 and self._is_valid_pdf(file_path):
                        logger.info(f"Case 1: Direct PDF download - {file_path.name} ({file_size} bytes)")
                        return self._create_file_info(file_path, url, file_size)
                except Exception as e:
                    logger.info(f"Case 1: Direct PDF download failed: {e}")
                    # Try alternative method: use requests for direct PDF
                    try:
                        logger.info(f"Case 1: Trying alternative method with requests")
                        response = requests.get(url, stream=True, timeout=60, headers={
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                        })
                        response.raise_for_status()
                        
                        file_path = opp_dir / filename
                        if not file_path.suffix.lower() == '.pdf':
                            file_path = file_path.with_suffix('.pdf')
                        
                        with open(file_path, 'wb') as f:
                            for chunk in response.iter_content(chunk_size=8192):
                                f.write(chunk)
                        
                        file_size = file_path.stat().st_size
                        if file_size > 0 and self._is_valid_pdf(file_path):
                            logger.info(f"Case 1: Direct PDF download via requests - {file_path.name} ({file_size} bytes)")
                            return self._create_file_info(file_path, url, file_size)
                    except Exception as req_error:
                        logger.info(f"Case 1: Requests method also failed: {req_error}")
            
            # Also check if current page is a PDF viewer (check for PDF.js or embedded PDF)
            try:
                # Check if page has PDF viewer indicators
                pdf_viewer_indicators = [
                    'embed[type="application/pdf"]',
                    'iframe[src*=".pdf"]',
                    'object[type="application/pdf"]',
                    '#pdf-viewer',
                    '.pdf-viewer',
                ]
                
                for indicator in pdf_viewer_indicators:
                    element = self.page.query_selector(indicator)
                    if element:
                        # Try to get PDF URL from iframe/embed
                        pdf_src = element.get_attribute('src')
                        if pdf_src:
                            if not pdf_src.startswith('http'):
                                pdf_src = urljoin(self.page.url, pdf_src)
                            
                            logger.info(f"Case 1: Found PDF viewer with src: {pdf_src}")
                            with self.page.expect_download(timeout=30000) as download_info:
                                self.page.goto(pdf_src, wait_until='domcontentloaded', timeout=60000)
                            
                            download = download_info.value
                            file_path = opp_dir / filename
                            if not file_path.suffix.lower() == '.pdf':
                                file_path = file_path.with_suffix('.pdf')
                            download.save_as(str(file_path))
                            file_size = file_path.stat().st_size
                            
                            if file_size > 0 and self._is_valid_pdf(file_path):
                                logger.info(f"Case 1: Downloaded PDF from viewer - {file_path.name} ({file_size} bytes)")
                                return self._create_file_info(file_path, url, file_size)
            except Exception as e:
                logger.info(f"Case 1: PDF viewer detection failed: {e}")
            
            return None
            
        except Exception as e:
            logger.warning(f"Case 1: Error in direct PDF download: {e}")
            return None
    
    def _try_case2_find_pdf_link(self, url: str, filename: str, opp_dir: Path, current_depth: int = 0, max_depth: int = 3, opportunity_id: int = None) -> Optional[Dict]:
        """Case 2: Look for PDF download links on the page and also scrape webpage content"""
        try:
            # FIRST: Extract webpage content before navigating away
            logger.info(f"Case 2: Extracting webpage content before PDF download")
            webpage_content = None
            try:
                webpage_content = self._extract_text_from_page()
                if webpage_content and len(webpage_content.strip()) > 100:
                    logger.info(f"Case 2: Extracted {len(webpage_content)} characters from webpage")
                else:
                    logger.info(f"Case 2: Webpage content too short or empty, skipping save")
                    webpage_content = None
            except Exception as extract_error:
                logger.warning(f"Case 2: Failed to extract webpage content: {extract_error}")
                webpage_content = None
            
            pdf_links = self._find_pdf_download_links()
            if not pdf_links:
                logger.info(f"Case 2: No PDF links found on page")
                return None
            
            logger.info(f"Case 2: Found {len(pdf_links)} PDF download link(s) on page")
            for pdf_link in pdf_links:
                try:
                    pdf_url = pdf_link.get('url')
                    pdf_name = pdf_link.get('name', filename)
                    
                    # Clean up URL (remove fragments like #)
                    if pdf_url and '#' in pdf_url:
                        pdf_url = pdf_url.split('#')[0]
                    
                    # Ensure PDF extension
                    if not pdf_name.endswith('.pdf'):
                        pdf_name += '.pdf'
                    
                    logger.info(f"Case 2: Attempting to download PDF from link: {pdf_url}")
                    
                    # Try clicking the link element first (more reliable)
                    link_element = pdf_link.get('element')
                    onclick_handler = pdf_link.get('onclick', '')
                    
                    if link_element:
                        try:
                            logger.info(f"Case 2: Trying to click link element")
                            
                            # Store current URL to detect navigation
                            current_url_before = self.page.url
                            
                            # Try to catch download, but also handle navigation
                            download_started = False
                            navigation_occurred = False
                            
                            try:
                                with self.page.expect_download(timeout=5000) as download_info:
                                    # Scroll element into view first
                                    link_element.scroll_into_view_if_needed()
                                    self.page.wait_for_timeout(500)
                                    # Click the element
                                    link_element.click()
                                    # Wait a bit for download to start
                                    self.page.wait_for_timeout(2000)
                            
                                download = download_info.value
                                file_path = opp_dir / self._sanitize_filename(pdf_name)
                                download.save_as(str(file_path))
                                file_size = file_path.stat().st_size
                                
                                if file_size > 0 and self._is_valid_pdf(file_path):
                                    logger.info(f"Case 2: Successfully downloaded PDF via click: {pdf_name} ({file_size} bytes)")
                                    
                                    # Also save webpage content if we extracted it
                                    if webpage_content:
                                        self._save_webpage_content(url, filename, opp_dir, webpage_content)
                                    
                                    return self._create_file_info(file_path, url, file_size)
                                download_started = True
                            except Exception as download_error:
                                # Check if we navigated to a new page instead of downloading
                                self.page.wait_for_timeout(2000)  # Wait for navigation to complete
                                current_url_after = self.page.url
                                
                                if current_url_after != current_url_before and current_url_after != url:
                                    navigation_occurred = True
                                    logger.info(f"Case 2: Link navigated to new page: {current_url_after} (was: {current_url_before})")
                                    logger.info(f"Case 2: New page may have PDF viewer, PDF link, another page, or just data - applying all cases")
                                    
                                    # Get opportunity_id from opp_dir path or use provided
                                    opp_id = int(opp_dir.name) if opp_dir.name.isdigit() else (opportunity_id if opportunity_id else 0)
                                    
                                    # Recursively process the new page - this will apply all cases
                                    logger.info(f"Case 2: Recursively processing new page (depth: {current_depth + 1}/{max_depth})")
                                    result = self._download_with_playwright(
                                        current_url_after, 
                                        opp_id, 
                                        pdf_name, 
                                        opp_dir, 
                                        max_depth, 
                                        current_depth + 1
                                    )
                                    
                                    if result:
                                        # Also save webpage content from original page if we extracted it
                                        if webpage_content:
                                            self._save_webpage_content(url, filename, opp_dir, webpage_content)
                                        return result
                                else:
                                    logger.info(f"Case 2: Click failed ({download_error}), no navigation detected")
                            
                            if not download_started and not navigation_occurred:
                                logger.info(f"Case 2: Click did not trigger download or navigation, trying JavaScript click or direct navigation")
                        except Exception as e:
                            logger.info(f"Case 2: Click failed ({e}), trying JavaScript click or direct navigation")
                            # Try JavaScript click as fallback
                            try:
                                if onclick_handler:
                                    logger.info(f"Case 2: Trying JavaScript onclick handler")
                                    self.page.evaluate(f"() => {{ {onclick_handler} }}")
                                    self.page.wait_for_timeout(2000)
                                    # Check if download started
                                    # This is tricky - we'll try navigation method instead
                            except:
                                pass
                    
                    # Fallback: Navigate directly to PDF URL
                    try:
                        # Resolve relative URLs
                        if not pdf_url.startswith('http'):
                            pdf_url = urljoin(self.page.url, pdf_url)
                        
                        logger.info(f"Case 2: Trying direct navigation to: {pdf_url}")
                        current_url_before_nav = self.page.url
                        
                        # For PDF URLs, use domcontentloaded and expect download
                        download_started = False
                        try:
                            with self.page.expect_download(timeout=10000) as download_info:
                                try:
                                    self.page.goto(pdf_url, wait_until='domcontentloaded', timeout=60000)
                                except Exception as nav_error:
                                    # If navigation fails because download started, that's actually good
                                    if "Download is starting" not in str(nav_error):
                                        raise
                            
                            download = download_info.value
                            file_path = opp_dir / self._sanitize_filename(pdf_name)
                            download.save_as(str(file_path))
                            file_size = file_path.stat().st_size
                            
                            if file_size > 0 and self._is_valid_pdf(file_path):
                                logger.info(f"Case 2: Successfully downloaded PDF via navigation: {pdf_name} ({file_size} bytes)")
                                
                                # Also save webpage content if we extracted it
                                if webpage_content:
                                    self._save_webpage_content(url, filename, opp_dir, webpage_content)
                                
                                return self._create_file_info(file_path, url, file_size)
                            download_started = True
                        except Exception as nav_error:
                            # Check if we navigated to a new page (not a PDF)
                            self.page.wait_for_timeout(2000)
                            current_url_after_nav = self.page.url
                            
                            if current_url_after_nav != current_url_before_nav and not pdf_url.lower().endswith('.pdf'):
                                logger.info(f"Case 2: Navigation to {pdf_url} resulted in new page: {current_url_after_nav}")
                                logger.info(f"Case 2: New page may have PDF viewer, PDF link, another page, or just data - applying all cases")
                                
                                # Get opportunity_id from opp_dir path or use provided
                                opp_id = int(opp_dir.name) if opp_dir.name.isdigit() else (opportunity_id if opportunity_id else 0)
                                
                                # Recursively process the new page - this will apply all cases
                                logger.info(f"Case 2: Recursively processing new page from navigation (depth: {current_depth + 1}/{max_depth})")
                                result = self._download_with_playwright(
                                    current_url_after_nav, 
                                    opp_id, 
                                    pdf_name, 
                                    opp_dir, 
                                    max_depth, 
                                    current_depth + 1
                                )
                                
                                if result:
                                    # Also save webpage content from original page if we extracted it
                                    if webpage_content:
                                        self._save_webpage_content(url, filename, opp_dir, webpage_content)
                                    return result
                            else:
                                logger.warning(f"Case 2: Direct navigation failed: {nav_error}")
                    except Exception as e:
                        logger.warning(f"Case 2: Direct navigation also failed: {e}")
                        # Try one more time with requests as last resort
                        try:
                            logger.info(f"Case 2: Trying requests as last resort for: {pdf_url}")
                            response = requests.get(pdf_url, stream=True, timeout=60, headers={
                                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                            })
                            response.raise_for_status()
                            
                            file_path = opp_dir / self._sanitize_filename(pdf_name)
                            with open(file_path, 'wb') as f:
                                for chunk in response.iter_content(chunk_size=8192):
                                    f.write(chunk)
                            
                            file_size = file_path.stat().st_size
                            if file_size > 0 and self._is_valid_pdf(file_path):
                                logger.info(f"Case 2: Successfully downloaded PDF via requests: {pdf_name} ({file_size} bytes)")
                                
                                # Also save webpage content if we extracted it
                                if webpage_content:
                                    self._save_webpage_content(url, filename, opp_dir, webpage_content)
                                
                                return self._create_file_info(file_path, url, file_size)
                        except Exception as req_error:
                            logger.warning(f"Case 2: Requests method also failed: {req_error}")
                        continue
                except Exception as e:
                    logger.warning(f"Case 2: Failed to download PDF from link: {e}")
                    continue
            
            return None
            
        except Exception as e:
            logger.warning(f"Case 2: Error finding PDF links: {e}")
            return None
    
    def _try_case_download_button(self, url: str, filename: str, opp_dir: Path, current_depth: int = 0, max_depth: int = 3, opportunity_id: int = None) -> Optional[Dict]:
        """Case Download Button: Look for download buttons on the page"""
        try:
            logger.info(f"Case Download Button: Searching for download buttons")
            
            # Common download button texts (case-insensitive)
            download_texts = [
                'download', 'download pdf', 'download file', 'download document',
                'get pdf', 'get file', 'save pdf', 'save file',
                'download all', 'download attachments'
            ]
            
            # Look for buttons with download text
            button_selectors = [
                'button',
                'input[type="button"]',
                'input[type="submit"]',
                'a.button',
                '.btn',
                '.button',
                '[role="button"]',
                'a[download]',  # Links with download attribute
            ]
            
            for selector in button_selectors:
                try:
                    buttons = self.page.query_selector_all(selector)
                    
                    for button in buttons:
                        try:
                            # Get button text (multiple ways)
                            button_text = ''
                            
                            # Try inner text
                            inner_text = button.inner_text()
                            if inner_text:
                                button_text = inner_text.strip().lower()
                            
                            # Try text content if inner_text is empty
                            if not button_text:
                                text_content = button.evaluate('el => el.textContent')
                                if text_content:
                                    button_text = text_content.strip().lower()
                            
                            # Try value attribute for input buttons
                            if not button_text:
                                value = button.get_attribute('value')
                                if value:
                                    button_text = value.strip().lower()
                            
                            # Try aria-label
                            if not button_text:
                                aria_label = button.get_attribute('aria-label')
                                if aria_label:
                                    button_text = aria_label.strip().lower()
                            
                            # Check if button has download attribute
                            has_download_attr = button.get_attribute('download')
                            
                            # Check if button text matches any download phrase or has download attribute
                            is_download_button = has_download_attr or any(phrase in button_text for phrase in download_texts)
                            
                            if is_download_button:
                                logger.info(f"Case Download Button: Found download button with text: '{button_text}' (download attr: {has_download_attr})")
                                
                                # Store current URL to detect navigation
                                current_url_before = self.page.url
                                
                                # Scroll into view
                                try:
                                    button.scroll_into_view_if_needed()
                                    self.page.wait_for_timeout(500)
                                except:
                                    pass
                                
                                # Try clicking the download button
                                download_started = False
                                navigation_occurred = False
                                
                                try:
                                    with self.page.expect_download(timeout=10000) as download_info:
                                        button.click(timeout=5000)
                                        self.page.wait_for_timeout(2000)
                                    
                                    download = download_info.value
                                    # Get suggested filename from download or use provided filename
                                    suggested_filename = download.suggested_filename or filename
                                    if not suggested_filename.endswith('.pdf'):
                                        suggested_filename = filename if filename.endswith('.pdf') else f"{Path(filename).stem}.pdf"
                                    
                                    file_path = opp_dir / self._sanitize_filename(suggested_filename)
                                    download.save_as(str(file_path))
                                    file_size = file_path.stat().st_size
                                    
                                    if file_size > 0 and self._is_valid_pdf(file_path):
                                        logger.info(f"Case Download Button: Successfully downloaded PDF: {file_path.name} ({file_size} bytes)")
                                        return self._create_file_info(file_path, url, file_size)
                                    
                                    download_started = True
                                except Exception as click_error:
                                    # Check if we navigated to a new page instead of downloading
                                    self.page.wait_for_timeout(2000)
                                    current_url_after = self.page.url
                                    
                                    if current_url_after != current_url_before:
                                        navigation_occurred = True
                                        logger.info(f"Case Download Button: Button navigated to new page: {current_url_after}")
                                        
                                        # Recursively process the new page - this will apply all cases
                                        logger.info(f"Case Download Button: Recursively processing new page (depth: {current_depth + 1}/{max_depth})")
                                        logger.info(f"Case Download Button: New page may have PDF viewer, PDF link, another page, or just data - applying all cases")
                                        # Get opportunity_id from opp_dir path (e.g., /path/to/123 -> 123) or use provided
                                        opp_id = int(opp_dir.name) if opp_dir.name.isdigit() else (opportunity_id if opportunity_id else 0)
                                        result = self._download_with_playwright(
                                            current_url_after, 
                                            opp_id,
                                            filename, 
                                            opp_dir, 
                                            max_depth, 
                                            current_depth + 1
                                        )
                                        
                                        if result:
                                            return result
                                    else:
                                        logger.info(f"Case Download Button: Click failed: {click_error}")
                                
                                if download_started or navigation_occurred:
                                    break
                        except Exception as btn_error:
                            logger.debug(f"Case Download Button: Error processing button: {btn_error}")
                            continue
                    
                    if download_started or navigation_occurred:
                        break
                except Exception as selector_error:
                    logger.debug(f"Case Download Button: Error with selector '{selector}': {selector_error}")
                    continue
            
            logger.info(f"Case Download Button: No download buttons found or all attempts failed")
            return None
            
        except Exception as e:
            logger.warning(f"Case Download Button: Error finding download buttons: {e}")
            return None
    
    def _try_case3_extract_text(self, url: str, filename: str, opp_dir: Path) -> Optional[Dict]:
        """Case 3: Extract text content and save as TXT (LAST RESORT)"""
        try:
            logger.info(f"Case 3: Extracting text content from page (last resort)")
            text_content = self._extract_text_from_page()
            if text_content and len(text_content.strip()) > 100:  # Minimum content length
                file_path = opp_dir / filename
                if not file_path.suffix.lower() == '.txt':
                    file_path = file_path.with_suffix('.txt')
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(f"Source URL: {url}\n")
                    f.write(f"Extracted: {datetime.now().isoformat()}\n")
                    f.write("=" * 80 + "\n\n")
                    f.write(text_content)
                
                file_size = file_path.stat().st_size
                logger.info(f"Case 3: Extracted and saved text content: {file_path.name} ({file_size} bytes, {len(text_content)} chars)")
                return self._create_file_info(file_path, url, file_size)
            else:
                logger.warning(f"Case 3: Text extraction failed or content too short ({len(text_content) if text_content else 0} chars)")
                return None
                
        except Exception as e:
            logger.warning(f"Case 3: Error extracting text: {e}")
            return None
    
    def _download_with_requests(self, url: str, opportunity_id: int, filename: str, opp_dir: Path) -> Optional[Dict]:
        """Fallback download using requests"""
        try:
            file_path = opp_dir / filename
            logger.info(f"Downloading {url} to {file_path} using requests")
            
            response = requests.get(url, stream=True, timeout=60, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            response.raise_for_status()
            
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            file_size = file_path.stat().st_size
            
            # Check if HTML error page
            if file_size > 0:
                with open(file_path, 'rb') as f:
                    first_bytes = f.read(1024)
                    if b'<html' in first_bytes.lower() or b'<!doctype' in first_bytes.lower():
                        logger.error(f"Downloaded file appears to be HTML error page: {filename}")
                        file_path.unlink()
                        return None
            
            if file_size == 0:
                logger.error(f"Downloaded file is empty: {filename}")
                file_path.unlink()
                return None
            
            logger.info(f"Downloaded {filename} ({file_size} bytes) using requests")
            return self._create_file_info(file_path, url, file_size)
        
        except Exception as e:
            logger.error(f"Error in requests download: {str(e)}", exc_info=True)
            return None
    
    def _find_pdf_download_links(self) -> List[Dict]:
        """Find PDF download links on the current page"""
        pdf_links = []
        
        try:
            # First, use JavaScript to comprehensively find all PDF links
            # This handles JavaScript-based links, table links, and regular links
            try:
                js_links = self.page.evaluate('''() => {
                    const pdfLinks = [];
                    
                    // Find all links
                    const allLinks = Array.from(document.querySelectorAll('a'));
                    
                    // Also check table cells that might contain PDF links
                    const tableCells = Array.from(document.querySelectorAll('td, th'));
                    
                    allLinks.forEach(link => {
                        const href = link.getAttribute('href') || '';
                        const onclick = link.getAttribute('onclick') || '';
                        const text = link.innerText?.trim() || '';
                        const title = link.getAttribute('title') || '';
                        const fullUrl = link.href || '';
                        
                        // Check if it's a PDF link by various indicators
                        const isPdfLink = 
                            href.includes('.pdf') || 
                            fullUrl.includes('.pdf') ||
                            text.includes('.pdf') ||
                            title.includes('.pdf') ||
                            (onclick && onclick.includes('.pdf')) ||
                            (href && (href.includes('download') || href.includes('file')));
                        
                        if (isPdfLink) {
                            // Try to extract PDF filename from text or href
                            let pdfName = text || title || '';
                            if (!pdfName || !pdfName.includes('.pdf')) {
                                // Extract from href
                                const hrefMatch = (href || fullUrl).match(/([^/]+\.pdf)/i);
                                if (hrefMatch) {
                                    pdfName = hrefMatch[1];
                                }
                            }
                            
                            pdfLinks.push({
                                href: href,
                                fullUrl: fullUrl,
                                text: text,
                                title: title,
                                onclick: onclick,
                                element: link,
                                pdfName: pdfName
                            });
                        }
                    });
                    
                    // Also check table cells for PDF filenames
                    tableCells.forEach(cell => {
                        const cellText = cell.innerText?.trim() || '';
                        const pdfMatch = cellText.match(/([A-Za-z0-9_\-]+\.pdf)/i);
                        if (pdfMatch) {
                            const pdfName = pdfMatch[1];
                            // Find if there's a link in this cell or nearby
                            const linkInCell = cell.querySelector('a');
                            if (linkInCell) {
                                const href = linkInCell.getAttribute('href') || '';
                                const fullUrl = linkInCell.href || '';
                                if (!pdfLinks.some(l => l.pdfName === pdfName)) {
                                    pdfLinks.push({
                                        href: href,
                                        fullUrl: fullUrl,
                                        text: pdfName,
                                        title: '',
                                        onclick: '',
                                        element: linkInCell,
                                        pdfName: pdfName
                                    });
                                }
                            }
                        }
                    });
                    
                    return pdfLinks;
                }''')
                
                for js_link in js_links:
                    # Determine the actual PDF URL
                    pdf_url = None
                    pdf_name = js_link.get('pdfName') or js_link.get('text') or ''
                    
                    # Prefer fullUrl, then href, then construct from onclick
                    if js_link.get('fullUrl') and '.pdf' in js_link['fullUrl'].lower():
                        pdf_url = js_link['fullUrl']
                    elif js_link.get('href') and ('.pdf' in js_link['href'].lower() or js_link['href'].startswith('http')):
                        pdf_url = js_link['href']
                        if not pdf_url.startswith('http'):
                            pdf_url = urljoin(self.page.url, pdf_url)
                    elif js_link.get('onclick'):
                        # Try to extract URL from onclick handler
                        onclick = js_link['onclick']
                        url_match = re.search(r'["\']([^"\']*\.pdf[^"\']*)["\']', onclick)
                        if url_match:
                            pdf_url = url_match.group(1)
                            if not pdf_url.startswith('http'):
                                pdf_url = urljoin(self.page.url, pdf_url)
                    
                    # If we have a PDF name but no URL, try to construct it
                    if pdf_name and '.pdf' in pdf_name.lower() and not pdf_url:
                        # Try common patterns
                        base_url = self.page.url.split('?')[0].rsplit('/', 1)[0]
                        pdf_url = f"{base_url}/{pdf_name}"
                    
                    if pdf_url or pdf_name:
                        # Get the element if available
                        element_handle = None
                        if js_link.get('element'):
                            # We can't pass DOM elements through evaluate, so we need to find it again
                            try:
                                # Try to find by text or href
                                if pdf_name:
                                    element_handle = self.page.query_selector(f'a:has-text("{pdf_name}")')
                                if not element_handle and pdf_url:
                                    element_handle = self.page.query_selector(f'a[href*="{Path(pdf_url).name}"]')
                            except:
                                pass
                        
                        pdf_links.append({
                            'url': pdf_url or '',
                            'name': pdf_name,
                            'element': element_handle,
                            'onclick': js_link.get('onclick', '')
                        })
            except Exception as e:
                logger.warning(f"JavaScript PDF link finding failed: {e}")
            
            # Fallback: Look for links with .pdf in href or text using selectors
            pdf_selectors = [
                'a[href$=".pdf"]',
                'a[href*=".pdf"]',
                'a:has-text(".pdf")',
            ]
            
            for selector in pdf_selectors:
                try:
                    links = self.page.query_selector_all(selector)
                    for link in links:
                        href = link.get_attribute('href')
                        text = link.inner_text().strip()
                        
                        if href and '.pdf' in href.lower():
                            # Resolve relative URLs
                            if not href.startswith('http'):
                                href = urljoin(self.page.url, href)
                            
                            # Check if we already have this link
                            if not any(l['url'] == href for l in pdf_links):
                                pdf_links.append({
                                    'url': href,
                                    'name': text or Path(href).name,
                                    'element': link,
                                    'onclick': ''
                                })
                except:
                    continue
            
            # Remove duplicates and clean up
            seen_urls = set()
            unique_links = []
            for link in pdf_links:
                url = link.get('url', '').split('#')[0].split('?')[0]  # Remove fragments and query params for comparison
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    unique_links.append(link)
            
            logger.info(f"Found {len(unique_links)} unique PDF links")
            return unique_links
            
        except Exception as e:
            logger.warning(f"Error finding PDF links: {e}")
            return []
    
    def _extract_text_from_page(self) -> Optional[str]:
        """Extract text content from the current page, preserving structure"""
        try:
            # Try to get structured content first (tables, forms, etc.)
            structured_content = self._extract_structured_content()
            if structured_content and len(structured_content.strip()) > 100:
                return structured_content
            
            # Try to get main content area
            content_selectors = [
                'main',
                'article',
                '.content',
                '#content',
                '.main-content',
                '#main-content',
                'body',
            ]
            
            text_content = None
            for selector in content_selectors:
                try:
                    element = self.page.query_selector(selector)
                    if element:
                        text_content = element.inner_text()
                        if text_content and len(text_content.strip()) > 100:
                            break
                except:
                    continue
            
            # Fallback to body text
            if not text_content or len(text_content.strip()) < 100:
                try:
                    body = self.page.query_selector('body')
                    if body:
                        text_content = body.inner_text()
                except:
                    pass
            
            # Clean up text
            if text_content:
                # Remove excessive whitespace but preserve structure
                lines = []
                for line in text_content.split('\n'):
                    stripped = line.strip()
                    if stripped:
                        lines.append(stripped)
                    elif lines and lines[-1]:  # Preserve paragraph breaks
                        lines.append('')
                text_content = '\n'.join(lines)
            
            return text_content
            
        except Exception as e:
            logger.warning(f"Error extracting text: {e}")
            return None
    
    def _extract_structured_content(self) -> Optional[str]:
        """Extract structured content like tables, forms, and key-value pairs"""
        try:
            # Try to extract table data
            tables = self.page.query_selector_all('table')
            if tables:
                structured_text = []
                for table in tables:
                    rows = table.query_selector_all('tr')
                    for row in rows:
                        cells = row.query_selector_all('td, th')
                        if cells:
                            row_text = ' | '.join([cell.inner_text().strip() for cell in cells])
                            structured_text.append(row_text)
                if structured_text:
                    return '\n'.join(structured_text)
            
            # Try to extract form fields and labels
            labels = self.page.query_selector_all('label')
            inputs = self.page.query_selector_all('input, textarea, select')
            if labels or inputs:
                structured_text = []
                for label in labels:
                    label_text = label.inner_text().strip()
                    # Try to find associated input
                    for_input = label.get_attribute('for')
                    if for_input:
                        input_elem = self.page.query_selector(f'#{for_input}')
                        if input_elem:
                            value = input_elem.get_attribute('value') or input_elem.inner_text().strip()
                            structured_text.append(f"{label_text}: {value}")
                    else:
                        structured_text.append(label_text)
                
                if structured_text:
                    return '\n'.join(structured_text)
            
            # Try to extract div-based key-value pairs (common in SAM.gov pages)
            try:
                # Look for patterns like "Label: Value" or structured divs
                structured_divs = self.page.evaluate('''() => {
                    const divs = Array.from(document.querySelectorAll('div'));
                    const pairs = [];
                    divs.forEach(div => {
                        const text = div.innerText?.trim();
                        if (text && text.includes(':')) {
                            pairs.push(text);
                        }
                    });
                    return pairs.slice(0, 50); // Limit to avoid too much data
                }''')
                
                if structured_divs and len(structured_divs) > 5:
                    return '\n'.join(structured_divs)
            except:
                pass
            
            return None
            
        except Exception as e:
            logger.warning(f"Error extracting structured content: {e}")
            return None
    
    def _save_webpage_content(self, url: str, filename: str, opp_dir: Path, content: str) -> Optional[Path]:
        """Save webpage content as a TXT file alongside the PDF"""
        try:
            # Create filename for webpage content (e.g., "document.pdf" -> "document_page.txt")
            base_name = Path(filename).stem  # Get filename without extension
            webpage_filename = f"{base_name}_page.txt"
            file_path = opp_dir / webpage_filename
            
            # Write content with metadata header (same format as Case 3)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(f"Source URL: {url}\n")
                f.write(f"Extracted: {datetime.now().isoformat()}\n")
                f.write("=" * 80 + "\n\n")
                f.write(content)
            
            file_size = file_path.stat().st_size
            logger.info(f"Case 2: Saved webpage content: {file_path.name} ({file_size} bytes, {len(content)} chars)")
            return file_path
        except Exception as e:
            logger.warning(f"Case 2: Failed to save webpage content: {e}")
            return None
    
    def _is_valid_pdf(self, file_path: Path) -> bool:
        """Check if file is a valid PDF"""
        try:
            with open(file_path, 'rb') as f:
                first_bytes = f.read(4)
                return first_bytes == b'%PDF'
        except:
            return False
    
    def _create_file_info(self, file_path: Path, url: str, file_size: int) -> Dict:
        """Create file info dictionary"""
        return {
            'path': str(file_path),
            'relative_path': str(file_path.relative_to(self.storage_base_path.parent)),
            'size': file_size,
            'name': file_path.name,
            'url': url
        }
    
    def download_all_as_zip(self, page: Page, opportunity_id: int, opportunity_url: str = None) -> Optional[Dict]:
        """
        Download all attachments as ZIP file by clicking "Download All" button
        
        Args:
            page: Playwright page object (must be on the SAM.gov opportunity page)
            opportunity_id: ID of the opportunity
            opportunity_url: Optional URL to navigate back to if needed
            
        Returns:
            dict with zip file info or None if failed
        """
        try:
            logger.info(f"DEBUG: Attempting to download all attachments as ZIP for opportunity {opportunity_id}")
            
            # Navigate to opportunity page if URL provided and we're not already there
            if opportunity_url and opportunity_url not in page.url:
                logger.info(f"DEBUG: Navigating to opportunity page: {opportunity_url}")
                page.goto(opportunity_url, wait_until='load', timeout=60000)
                page.wait_for_timeout(2000)  # Wait for Angular
            
            # Find "Download All" button - try multiple selectors
            download_all_selectors = [
                'button:has-text("Download All")',
                'a:has-text("Download All")',
                'button[title*="Download All" i]',
                'a[title*="Download All" i]',
                'button[aria-label*="Download All" i]',
                'a[aria-label*="Download All" i]',
                '.download-all',
                '#download-all',
                'button:has-text("Download")',
                'a:has-text("Download")',
            ]
            
            download_button = None
            for selector in download_all_selectors:
                try:
                    download_button = page.query_selector(selector)
                    if download_button:
                        logger.info(f"DEBUG: Found Download All button with selector: {selector}")
                        break
                except:
                    continue
            
            # If not found, try JavaScript evaluation
            if not download_button:
                logger.info(f"DEBUG: Download All button not found with selectors, trying JavaScript evaluation")
                try:
                    button_info = page.evaluate('''() => {
                        const buttons = Array.from(document.querySelectorAll('button, a'));
                        for (const btn of buttons) {
                            const text = btn.innerText?.toLowerCase() || '';
                            const ariaLabel = btn.getAttribute('aria-label')?.toLowerCase() || '';
                            if (text.includes('download all') || ariaLabel.includes('download all')) {
                                return { found: true, text: btn.innerText, tag: btn.tagName };
                            }
                        }
                        return { found: false };
                    }''')
                    
                    if button_info.get('found'):
                        logger.info(f"DEBUG: Download All button found via JavaScript: {button_info.get('text')}")
                        # Try to find it by text
                        try:
                            download_button = page.query_selector(f'button:has-text("{button_info.get("text")}"), a:has-text("{button_info.get("text")}")')
                        except:
                            pass
                except Exception as e:
                    logger.warning(f"DEBUG: JavaScript evaluation failed: {e}")
            
            if not download_button:
                logger.error("DEBUG: Could not find Download All button")
                return None
            
            # Create opportunity directory
            opp_dir = self.storage_base_path / str(opportunity_id)
            opp_dir.mkdir(parents=True, exist_ok=True)
            
            zip_path = opp_dir / f"attachments_{opportunity_id}.zip"
            
            # Download ZIP file by clicking the button
            logger.info(f"DEBUG: Clicking Download All button to download ZIP")
            with page.expect_download(timeout=120000) as download_info:
                if download_button:
                    download_button.click()
                else:
                    # Fallback: try clicking by text
                    page.click('button:has-text("Download All"), a:has-text("Download All")', timeout=10000)
            
            download = download_info.value
            download.save_as(str(zip_path))
            
            zip_size = zip_path.stat().st_size
            logger.info(f"DEBUG: Downloaded ZIP file: {zip_path.name} ({zip_size} bytes)")
            
            # Extract ZIP file
            extracted_files = self._extract_zip(zip_path, opp_dir)
            logger.info(f"DEBUG: Extracted {len(extracted_files)} files from ZIP")
            
            # Clean up ZIP file after extraction
            zip_path.unlink()
            logger.info(f"DEBUG: Deleted ZIP file after extraction")
            
            return {
                'extracted_files': extracted_files,
                'zip_size': zip_size
            }
            
        except Exception as e:
            logger.error(f"Error downloading ZIP file: {str(e)}", exc_info=True)
            return None
    
    def _extract_zip(self, zip_path: Path, extract_to: Path) -> List[Dict]:
        """
        Extract ZIP file and return list of extracted file info
        
        Args:
            zip_path: Path to ZIP file
            extract_to: Directory to extract files to
            
        Returns:
            List of extracted file info dicts
        """
        extracted = []
        
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_to)
                
                # Get list of extracted files
                for member in zip_ref.namelist():
                    if member and not member.endswith('/'):  # Skip directories
                        extracted_path = extract_to / member
                        
                        # Handle nested paths in ZIP
                        if not extracted_path.exists():
                            # Try with relative path
                            extracted_path = extract_to / Path(member).name
                        
                        if extracted_path.exists() and extracted_path.is_file():
                            file_size = extracted_path.stat().st_size
                            
                            # Determine file type
                            file_type = 'unknown'
                            name_lower = extracted_path.name.lower()
                            if name_lower.endswith('.pdf'):
                                file_type = 'pdf'
                            elif name_lower.endswith(('.doc', '.docx')):
                                file_type = 'word'
                            elif name_lower.endswith(('.xls', '.xlsx')):
                                file_type = 'excel'
                            
                            extracted.append({
                                'path': str(extracted_path),
                                'relative_path': str(extracted_path.relative_to(self.storage_base_path.parent)),
                                'size': file_size,
                                'name': extracted_path.name,
                                'type': file_type
                            })
                            
                            logger.info(f"DEBUG: Extracted file: {extracted_path.name} ({file_size} bytes)")
        
        except Exception as e:
            logger.error(f"Error extracting ZIP file: {str(e)}", exc_info=True)
        
        return extracted
    
    def download_attachments(self, attachments: List[Dict], opportunity_id: int, opportunity_url: str = None) -> List[Dict]:
        """
        Download multiple attachments - tries ZIP download first, falls back to individual downloads
        
        Args:
            attachments: List of attachment dicts from scraper
            opportunity_id: ID of the opportunity
            
        Returns:
            List of downloaded file info dicts
        """
        logger.info(f"DEBUG: download_attachments called - attachments count: {len(attachments)}, opportunity_id: {opportunity_id}")
        
        # Try downloading as ZIP first if we have a page object
        if self.page:
            logger.info(f"DEBUG: Attempting to download all attachments as ZIP")
            zip_result = self.download_all_as_zip(self.page, opportunity_id, opportunity_url)
            
            if zip_result and zip_result.get('extracted_files'):
                extracted_files = zip_result['extracted_files']
                logger.info(f"DEBUG: Successfully downloaded ZIP and extracted {len(extracted_files)} files")
                return extracted_files
            else:
                logger.warning(f"DEBUG: ZIP download failed or returned no files, falling back to individual downloads")
        
        # Fallback to individual downloads
        logger.info(f"DEBUG: Falling back to individual file downloads")
        logger.info(f"DEBUG: Attachment list: {attachments}")
        
        downloaded = []
        
        for idx, attachment in enumerate(attachments):
            logger.info(f"DEBUG: Processing attachment {idx + 1}/{len(attachments)}: {attachment}")
            url = attachment.get('url')
            name = attachment.get('name')
            
            logger.info(f"DEBUG: Attachment details - url: {url}, name: {name}")
            
            if not url:
                logger.warning(f"DEBUG: Skipping attachment {idx + 1} - no URL found")
                continue
            
            file_info = self.download_document(url, opportunity_id, name)
            if file_info:
                file_info['type'] = attachment.get('type', 'unknown')
                file_info['access'] = attachment.get('access', 'unknown')
                downloaded.append(file_info)
                logger.info(f"DEBUG: Successfully downloaded attachment {idx + 1}: {file_info.get('name')}")
            else:
                logger.error(f"DEBUG: Failed to download attachment {idx + 1}: {name or url}")
        
        logger.info(f"DEBUG: download_attachments complete - downloaded {len(downloaded)}/{len(attachments)} files")
        return downloaded
    
    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename to be filesystem-safe"""
        # Remove path separators and dangerous characters
        filename = filename.replace('/', '_').replace('\\', '_')
        filename = ''.join(c for c in filename if c.isprintable() and c not in '<>:"|?*')
        
        # Limit length
        if len(filename) > 255:
            name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
            filename = name[:250] + ('.' + ext if ext else '')
        
        return filename
    
    def get_file_path(self, opportunity_id: int, filename: str) -> Path:
        """Get full path for a stored file"""
        return self.storage_base_path / str(opportunity_id) / filename
