"""
Celery background tasks
"""
from ..core.celery_app import celery_app
from ..core.database import SessionLocal
from ..core.config import settings
from ..models.opportunity import Opportunity
from ..models.document import Document, DocumentType, DocumentSource
from ..models.deadline import Deadline
from .sam_gov_scraper import SAMGovScraper
from .document_downloader import DocumentDownloader
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
                if not opportunity.sam_gov_id:
                    opportunity.sam_gov_id = metadata['notice_id']
            
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
            
            # Update status to completed
            opportunity.status = "completed"
            db.commit()
            
            logger.info(f"Successfully scraped opportunity {opportunity_id}")
            
            # Trigger document analysis
            analyze_documents.delay(opportunity_id)
            
            return {
                "status": "success",
                "opportunity_id": opportunity_id,
                "attachments_downloaded": len(attachments)
            }
        
    except Exception as e:
        logger.error(f"Error scraping opportunity {opportunity_id}: {str(e)}", exc_info=True)
        if opportunity:
            opportunity.status = "failed"
            opportunity.error_message = str(e)
            db.commit()
        return {"status": "error", "message": str(e)}
    finally:
        db.close()


@celery_app.task(name="analyze_documents")
def analyze_documents(opportunity_id: int):
    """
    Background task to analyze downloaded documents
    This will extract CLINs, classify solicitation type, etc.
    
    Args:
        opportunity_id: ID of the opportunity to analyze
    """
    db = SessionLocal()
    try:
        opportunity = db.query(Opportunity).filter(Opportunity.id == opportunity_id).first()
        if not opportunity:
            logger.error(f"Opportunity {opportunity_id} not found")
            return {"status": "error", "message": "Opportunity not found"}
        
        # Get all documents for this opportunity
        documents = db.query(Document).filter(Document.opportunity_id == opportunity_id).all()
        
        if not documents:
            logger.warning(f"No documents found for opportunity {opportunity_id}")
            return {"status": "success", "message": "No documents to analyze"}
        
        logger.info(f"Starting document analysis for opportunity {opportunity_id} ({len(documents)} documents)")
        
        # TODO: Implement document analysis
        # 1. Extract text from PDFs/Word docs
        # 2. Classify solicitation type (product/service/hybrid)
        # 3. Extract CLINs from documents
        # 4. Extract additional deadlines
        # 5. Store extracted data in database
        
        # Placeholder - analysis will be implemented in next phase
        logger.info(f"Document analysis placeholder for opportunity {opportunity_id}")
        
        return {
            "status": "success",
            "opportunity_id": opportunity_id,
            "documents_analyzed": len(documents)
        }
        
    except Exception as e:
        logger.error(f"Error analyzing documents for opportunity {opportunity_id}: {str(e)}", exc_info=True)
        return {"status": "error", "message": str(e)}
    finally:
        db.close()
