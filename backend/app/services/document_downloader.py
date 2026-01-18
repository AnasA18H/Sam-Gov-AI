"""
Document downloader service
Handles downloading and storing SAM.gov attachments
"""
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import requests
from urllib.parse import urlparse
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
            
            file_path = opp_dir / filename
            
            # Use Playwright if available (for authenticated downloads), otherwise fall back to requests
            if self.page:
                logger.info(f"Downloading {url} to {file_path} using Playwright")
                try:
                    # Use Playwright's download functionality
                    with self.page.expect_download() as download_info:
                        self.page.goto(url, wait_until='load', timeout=60000)
                    
                    download = download_info.value
                    download.save_as(str(file_path))
                    file_size = file_path.stat().st_size
                    logger.info(f"Downloaded {filename} ({file_size} bytes) using Playwright")
                except Exception as e:
                    logger.warning(f"Playwright download failed, trying requests: {e}")
                    # Fall back to requests
                    response = requests.get(url, stream=True, timeout=60, headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    })
                    response.raise_for_status()
                    
                    with open(file_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    
                    file_size = file_path.stat().st_size
                    logger.info(f"Downloaded {filename} ({file_size} bytes) using requests")
            else:
                # Use requests (fallback)
                logger.info(f"Downloading {url} to {file_path} using requests")
                response = requests.get(url, stream=True, timeout=60, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                })
                response.raise_for_status()
                
                with open(file_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                file_size = file_path.stat().st_size
                logger.info(f"Downloaded {filename} ({file_size} bytes)")
            
            # Verify file is not empty and is a valid file type
            if file_size == 0:
                logger.error(f"Downloaded file is empty: {filename}")
                file_path.unlink()  # Delete empty file
                return None
            
            # Check if file is actually an error page (HTML) instead of a document
            try:
                with open(file_path, 'rb') as f:
                    first_bytes = f.read(1024)
                    if b'<html' in first_bytes.lower() or b'<!doctype' in first_bytes.lower():
                        logger.error(f"Downloaded file appears to be HTML error page: {filename}")
                        file_path.unlink()  # Delete error page
                        return None
            except:
                pass
            
            return {
                'path': str(file_path),
                'relative_path': str(file_path.relative_to(self.storage_base_path.parent)),
                'size': file_size,
                'name': filename,
                'url': url
            }
            
        except Exception as e:
            logger.error(f"Error downloading document from {url}: {str(e)}", exc_info=True)
            return None
    
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
