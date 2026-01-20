"""
Celery background tasks
"""
from pathlib import Path
from ..core.celery_app import celery_app
from ..core.database import SessionLocal
from ..core.config import settings
from ..models.opportunity import Opportunity
from ..models.document import Document, DocumentType, DocumentSource
from ..models.deadline import Deadline
from .sam_gov_scraper import SAMGovScraper
from .document_downloader import DocumentDownloader
from .document_extractor import DocumentExtractor
from datetime import datetime
from dateutil import parser as dateutil_parser
import logging

logger = logging.getLogger(__name__)


@celery_app.task(name="scrape_sam_gov_opportunity")
def scrape_sam_gov_opportunity(opportunity_id: int):
    """
    Background task to scrape SAM.gov opportunity and download attachments
    
    Args:
        opportunity_id: ID of the opportunity to scrape
    """
    db = SessionLocal()
    opportunity = None
    
    try:
        opportunity = db.query(Opportunity).filter(Opportunity.id == opportunity_id).first()
        if not opportunity:
            logger.error(f"Opportunity {opportunity_id} not found")
            return {"status": "error", "message": "Opportunity not found"}
        
        # Update status to processing
        opportunity.status = "processing"
        db.commit()
        
        logger.info(f"Starting scrape for opportunity {opportunity_id}: {opportunity.sam_gov_url}")
        
        # Scrape the SAM.gov page
        with SAMGovScraper() as scraper:
            result = scraper.scrape_opportunity(opportunity.sam_gov_url)
            
            if not result.get('success'):
                error_msg = result.get('error', 'Unknown error')
                logger.error(f"Scraping failed: {error_msg}")
                opportunity.status = "failed"
                opportunity.error_message = error_msg
                db.commit()
                return {"status": "error", "message": error_msg}
            
            metadata = result.get('metadata', {})
            attachments = result.get('attachments', [])
            
            logger.info(f"DEBUG: Scraping result - success: {result.get('success')}, metadata keys: {list(metadata.keys())}, attachments count: {len(attachments)}")
            if attachments:
                logger.info(f"DEBUG: Attachments found: {[att.get('name', att.get('url', 'unknown')) for att in attachments]}")
            else:
                logger.warning(f"DEBUG: No attachments found in scraping result!")
            
            # Update opportunity with metadata
            if metadata.get('title'):
                opportunity.title = metadata['title']
            
            if metadata.get('notice_id'):
                opportunity.notice_id = metadata['notice_id']
                # Also update sam_gov_id if not set (for backward compatibility)
                # But check if it already exists for another opportunity to avoid unique constraint violation
                if not opportunity.sam_gov_id:
                    notice_id = metadata['notice_id']
                    # Check if another opportunity already has this sam_gov_id
                    existing_opp = db.query(Opportunity).filter(
                        Opportunity.sam_gov_id == notice_id,
                        Opportunity.id != opportunity.id
                    ).first()
                    if not existing_opp:
                        opportunity.sam_gov_id = notice_id
                    else:
                        logger.warning(f"sam_gov_id '{notice_id}' already exists for opportunity {existing_opp.id}, skipping update for opportunity {opportunity_id}")
            
            if metadata.get('description'):
                opportunity.description = metadata['description']
            
            if metadata.get('agency'):
                opportunity.agency = metadata['agency']
            
            if metadata.get('status'):
                opportunity.status = metadata['status'].lower()
            
            # Store contact information
            if metadata.get('primary_contact'):
                opportunity.primary_contact = metadata['primary_contact']
            
            if metadata.get('alternative_contact'):
                opportunity.alternative_contact = metadata['alternative_contact']
            
            if metadata.get('contracting_office_address'):
                opportunity.contracting_office_address = metadata['contracting_office_address']
            
            # Store deadline if found (CRITICAL)
            if metadata.get('date_offers_due'):
                try:
                    # Parse deadline date
                    deadline_date_str = metadata['date_offers_due']
                    deadline_time_str = metadata.get('date_offers_due_time', '00:00')
                    timezone_str = metadata.get('date_offers_due_timezone', 'UTC')
                    
                    # Combine date and time
                    if isinstance(deadline_date_str, str):
                        # Try to parse ISO format
                        try:
                            deadline_dt = datetime.fromisoformat(deadline_date_str)
                        except:
                            # Try parsing with dateutil
                            deadline_dt = dateutil_parser.parse(deadline_date_str)
                    else:
                        deadline_dt = deadline_date_str
                    
                    deadline = Deadline(
                        opportunity_id=opportunity.id,
                        deadline_type="offers_due",
                        due_date=deadline_dt,
                        due_time=deadline_time_str,
                        timezone=timezone_str,
                        is_primary=True
                    )
                    db.add(deadline)
                except Exception as e:
                    logger.warning(f"Could not parse deadline: {str(e)}")
            
            # Download attachments (PRIMARY DATA SOURCE)
            logger.info(f"DEBUG: Starting attachment download - count: {len(attachments) if attachments else 0}")
            if attachments:
                logger.info(f"DEBUG: Storage base path: {settings.STORAGE_BASE_PATH}")
                # Pass the Playwright page to downloader for authenticated downloads
                downloader = DocumentDownloader(page=scraper.page)
                logger.info(f"DEBUG: DocumentDownloader initialized with path: {downloader.storage_base_path}")
                
                downloaded_files = downloader.download_attachments(attachments, opportunity.id, opportunity.sam_gov_url)
                logger.info(f"DEBUG: Downloaded files count: {len(downloaded_files) if downloaded_files else 0}")
                
                if downloaded_files:
                    logger.info(f"DEBUG: Downloaded files: {[f.get('name', 'unknown') for f in downloaded_files]}")
                else:
                    logger.warning(f"DEBUG: No files were successfully downloaded!")
                
                # Store document records in database
                for file_info in downloaded_files:
                    # Map file type string to DocumentType enum
                    file_type_str = file_info.get('type', 'unknown').lower()
                    if file_type_str == 'pdf':
                        doc_type = DocumentType.PDF
                    elif file_type_str in ['word', 'doc', 'docx']:
                        doc_type = DocumentType.WORD
                    elif file_type_str in ['excel', 'xls', 'xlsx']:
                        doc_type = DocumentType.EXCEL
                    else:
                        doc_type = DocumentType.OTHER
                    
                    doc = Document(
                        opportunity_id=opportunity.id,
                        file_name=file_info['name'],
                        file_path=file_info['path'],
                        file_size=file_info.get('size', 0),
                        file_type=doc_type,
                        source=DocumentSource.SAM_GOV,
                        source_url=file_info.get('url'),
                        storage_type="local"
                    )
                    db.add(doc)
                    logger.info(f"DEBUG: Added document to DB: {doc.file_name} (path: {doc.file_path})")
                
                db.commit()
                logger.info(f"DEBUG: Committed {len(downloaded_files)} documents to database")
            else:
                logger.warning(f"DEBUG: No attachments to download - attachments list was empty or None!")
            
            # Set status to completed after scraping finishes
            opportunity.status = "completed"
            db.commit()
            
            logger.info(f"Successfully scraped opportunity {opportunity_id}")
            
            return {
                "status": "success",
                "opportunity_id": opportunity_id,
                "attachments_downloaded": len(attachments)
            }
        
    except Exception as e:
        logger.error(f"Error scraping opportunity {opportunity_id}: {str(e)}", exc_info=True)
        if opportunity:
            try:
                db.rollback()  # Rollback any pending transaction
                opportunity.status = "failed"
                opportunity.error_message = str(e)
                db.commit()
            except Exception as commit_error:
                logger.error(f"Error updating opportunity status after failure: {str(commit_error)}")
                db.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        db.close()


@celery_app.task(name="extract_documents")
def extract_documents(opportunity_id: int):
    """
    Background task to extract text from all documents for an opportunity
    
    Args:
        opportunity_id: ID of the opportunity to extract documents for
    """
    db = SessionLocal()
    opportunity = None
    
    try:
        opportunity = db.query(Opportunity).filter(Opportunity.id == opportunity_id).first()
        if not opportunity:
            logger.error(f"Opportunity {opportunity_id} not found")
            return {"status": "error", "message": "Opportunity not found"}
        
        # Get all documents for this opportunity
        documents = db.query(Document).filter(Document.opportunity_id == opportunity_id).all()
        
        if not documents:
            logger.warning(f"No documents found for opportunity {opportunity_id}")
            return {"status": "success", "message": "No documents to extract", "extracted_count": 0}
        
        logger.info(f"Starting text extraction for opportunity {opportunity_id} ({len(documents)} documents)")
        
        # Initialize document extractor
        extractor = DocumentExtractor()
        
        extracted_count = 0
        failed_count = 0
        
        # Extract text from each document
        for doc in documents:
            try:
                # Resolve file path
                file_path = Path(doc.file_path)
                
                # Handle relative paths
                if not file_path.is_absolute():
                    project_root = settings.PROJECT_ROOT
                    abs_path = project_root / file_path
                    if not abs_path.exists() and hasattr(settings, 'STORAGE_BASE_PATH'):
                        storage_base = Path(settings.STORAGE_BASE_PATH)
                        if storage_base.is_absolute():
                            abs_path = storage_base.parent / file_path.lstrip('/') if 'backend/data' in str(file_path) else storage_base / file_path.lstrip('/')
                        else:
                            abs_path = project_root / storage_base.parent / file_path.lstrip('/') if 'backend/data' in str(file_path) else project_root / storage_base / file_path.lstrip('/')
                    file_path = abs_path if abs_path.exists() else file_path
                
                if not Path(file_path).exists():
                    logger.warning(f"Document file not found: {doc.file_path} (doc ID: {doc.id})")
                    failed_count += 1
                    continue
                
                # Extract text using the robust extractor
                logger.info(f"Extracting text from document {doc.id}: {doc.file_name}")
                result = extractor.extract_text_robustly(
                    file_path=str(file_path),
                    opportunity_id=opportunity_id,
                    document_id=doc.id
                )
                
                if result['text'] and result['quality_score'] > 0:
                    extracted_count += 1
                    logger.info(f"Successfully extracted text from {doc.file_name} (quality: {result['quality_score']:.2f}, length: {len(result['text'])})")
                else:
                    failed_count += 1
                    logger.warning(f"Extraction failed or returned empty text for {doc.file_name}")
                
            except Exception as e:
                logger.error(f"Error extracting text from document {doc.id} ({doc.file_name}): {str(e)}", exc_info=True)
                failed_count += 1
                continue
        
        logger.info(f"Text extraction completed for opportunity {opportunity_id}: {extracted_count} succeeded, {failed_count} failed")
        
        return {
            "status": "success",
            "opportunity_id": opportunity_id,
            "total_documents": len(documents),
            "extracted_count": extracted_count,
            "failed_count": failed_count
        }
        
    except Exception as e:
        logger.error(f"Error extracting documents for opportunity {opportunity_id}: {str(e)}", exc_info=True)
        return {"status": "error", "message": str(e)}
    finally:
        db.close()
