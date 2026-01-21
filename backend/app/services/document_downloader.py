"""
Document downloader service
Handles downloading and storing SAM.gov attachments
"""
import logging
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
    
    def _download_with_playwright(self, url: str, opportunity_id: int, filename: str, opp_dir: Path) -> Optional[Dict]:
        """
        Download using Playwright with smart case detection
        Tries in order: Case 1 (direct PDF) -> Case 2 (find PDF link) -> Case 3 (extract text as last resort)
        """
        try:
            logger.info(f"Navigating to {url} to detect download type")
            self.page.goto(url, wait_until='load', timeout=60000)
            self.page.wait_for_timeout(2000)  # Wait for page to fully load
            
            # CASE 1: Try direct PDF download (PDF viewer or direct PDF URL)
            result = self._try_case1_direct_pdf(url, filename, opp_dir)
            if result:
                logger.info(f"✅ Case 1 succeeded: Direct PDF download")
                return result
            
            logger.info(f"Case 1 failed, trying Case 2: Find PDF link on page")
            
            # CASE 2: Look for PDF download links on the page
            result = self._try_case2_find_pdf_link(url, filename, opp_dir)
            if result:
                logger.info(f"✅ Case 2 succeeded: Found and downloaded PDF from page")
                return result
            
            logger.info(f"Case 2 failed, trying Case 3: Extract text content (last resort)")
            
            # CASE 3: Extract text content and save as TXT (LAST RESORT)
            result = self._try_case3_extract_text(url, filename, opp_dir)
            if result:
                logger.info(f"✅ Case 3 succeeded: Extracted and saved text content")
                return result
            
            logger.warning(f"All three cases failed for {url}")
            return None
                
        except Exception as e:
            logger.error(f"Error in Playwright download: {str(e)}", exc_info=True)
            return None
    
    def _try_case1_direct_pdf(self, url: str, filename: str, opp_dir: Path) -> Optional[Dict]:
        """Case 1: Try direct PDF download (PDF viewer or direct PDF URL)"""
        try:
            # Check if URL directly serves a PDF
            if url.lower().endswith('.pdf'):
                logger.info(f"Case 1: URL appears to be direct PDF, attempting download")
                try:
                    with self.page.expect_download(timeout=10000) as download_info:
                        self.page.goto(url, wait_until='load', timeout=60000)
                    
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
                            with self.page.expect_download(timeout=10000) as download_info:
                                self.page.goto(pdf_src, wait_until='load', timeout=60000)
                            
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
    
    def _try_case2_find_pdf_link(self, url: str, filename: str, opp_dir: Path) -> Optional[Dict]:
        """Case 2: Look for PDF download links on the page"""
        try:
            pdf_links = self._find_pdf_download_links()
            if not pdf_links:
                logger.info(f"Case 2: No PDF links found on page")
                return None
            
            logger.info(f"Case 2: Found {len(pdf_links)} PDF download link(s) on page")
            for pdf_link in pdf_links:
                try:
                    pdf_url = pdf_link.get('url')
                    pdf_name = pdf_link.get('name', filename)
                    if not pdf_name.endswith('.pdf'):
                        pdf_name += '.pdf'
                    
                    logger.info(f"Case 2: Attempting to download PDF from link: {pdf_url}")
                    
                    # Try clicking the link element first (more reliable)
                    link_element = pdf_link.get('element')
                    if link_element:
                        try:
                            with self.page.expect_download(timeout=30000) as download_info:
                                link_element.click()
                            download = download_info.value
                            file_path = opp_dir / self._sanitize_filename(pdf_name)
                            download.save_as(str(file_path))
                            file_size = file_path.stat().st_size
                            
                            if file_size > 0 and self._is_valid_pdf(file_path):
                                logger.info(f"Case 2: Successfully downloaded PDF via click: {pdf_name} ({file_size} bytes)")
                                return self._create_file_info(file_path, url, file_size)
                        except Exception as e:
                            logger.info(f"Case 2: Click failed, trying direct navigation: {e}")
                    
                    # Fallback: Navigate directly to PDF URL
                    try:
                        # Resolve relative URLs
                        if not pdf_url.startswith('http'):
                            pdf_url = urljoin(self.page.url, pdf_url)
                        
                        with self.page.expect_download(timeout=30000) as download_info:
                            self.page.goto(pdf_url, wait_until='load', timeout=60000)
                        
                        download = download_info.value
                        file_path = opp_dir / self._sanitize_filename(pdf_name)
                        download.save_as(str(file_path))
                        file_size = file_path.stat().st_size
                        
                        if file_size > 0 and self._is_valid_pdf(file_path):
                            logger.info(f"Case 2: Successfully downloaded PDF via navigation: {pdf_name} ({file_size} bytes)")
                            return self._create_file_info(file_path, url, file_size)
                    except Exception as e:
                        logger.warning(f"Case 2: Direct navigation also failed: {e}")
                        continue
                except Exception as e:
                    logger.warning(f"Case 2: Failed to download PDF from link: {e}")
                    continue
            
            return None
            
        except Exception as e:
            logger.warning(f"Case 2: Error finding PDF links: {e}")
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
            # Look for links with .pdf in href or text
            pdf_selectors = [
                'a[href$=".pdf"]',
                'a[href*=".pdf"]',
                'a:has-text(".pdf")',
                'a[href*="download"]',
                'a[href*="Download"]',
                'a[href*="file"]',
            ]
            
            for selector in pdf_selectors:
                try:
                    links = self.page.query_selector_all(selector)
                    for link in links:
                        href = link.get_attribute('href')
                        text = link.inner_text().strip()
                        
                        if href and ('.pdf' in href.lower() or 'download' in href.lower() or 'file' in href.lower()):
                            # Resolve relative URLs
                            if not href.startswith('http'):
                                from urllib.parse import urljoin
                                href = urljoin(self.page.url, href)
                            
                            pdf_links.append({
                                'url': href,
                                'name': text or Path(href).name,
                                'element': link
                            })
                except:
                    continue
            
            # Also try JavaScript evaluation to find PDF links
            try:
                js_links = self.page.evaluate('''() => {
                    const links = Array.from(document.querySelectorAll('a'));
                    const pdfLinks = [];
                    links.forEach(link => {
                        const href = link.getAttribute('href') || '';
                        const text = link.innerText?.trim() || '';
                        if (href.includes('.pdf') || href.includes('download') || text.includes('.pdf')) {
                            pdfLinks.push({
                                href: href,
                                text: text,
                                fullUrl: link.href
                            });
                        }
                    });
                    return pdfLinks;
                }''')
                
                for js_link in js_links:
                    if js_link.get('fullUrl') and js_link['fullUrl'] not in [l['url'] for l in pdf_links]:
                        pdf_links.append({
                            'url': js_link['fullUrl'],
                            'name': js_link.get('text') or Path(js_link['fullUrl']).name,
                            'element': None
                        })
            except:
                pass
            
            # Remove duplicates
            seen_urls = set()
            unique_links = []
            for link in pdf_links:
                if link['url'] not in seen_urls:
                    seen_urls.add(link['url'])
                    unique_links.append(link)
            
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
