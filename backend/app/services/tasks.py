"""
Celery background tasks
"""
import re
from pathlib import Path
from typing import Optional
from ..core.celery_app import celery_app
from ..core.database import SessionLocal
from ..core.config import settings
from ..models.opportunity import Opportunity
from ..models.document import Document, DocumentType, DocumentSource
from ..models.deadline import Deadline
from ..models.clin import CLIN
from ..models.manufacturer import Manufacturer, ResearchStatus
from .sam_gov_scraper import SAMGovScraper
from .document_downloader import DocumentDownloader
from .document_analyzer import DocumentAnalyzer
from .research_service import save_extracted_manufacturers, save_extracted_dealers, save_external_dealers
from .llm_external_research_service import LLMExternalResearchService
from datetime import datetime
from dateutil import parser as dateutil_parser
from sqlalchemy import func
import logging

logger = logging.getLogger(__name__)


def _truncate_string(value: Optional[str], max_length: int = 255) -> Optional[str]:
    """Truncate string to max_length if it exceeds the limit"""
    if not value:
        return None
    if len(value) <= max_length:
        return value
    # Truncate and add ellipsis
    return value[:max_length - 3] + "..."


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
            sam_gov_page_text = result.get('page_text', '')  # SAM.gov page text for LLM analysis
            
            logger.info(f"DEBUG: Scraping result - success: {result.get('success')}, metadata keys: {list(metadata.keys())}, attachments count: {len(attachments)}, page text length: {len(sam_gov_page_text)}")
            logger.info(f"DEBUG: Extracted metadata - title: {metadata.get('title', 'None')[:50] if metadata.get('title') else 'None'}, description: {len(metadata.get('description', '')) if metadata.get('description') else 0} chars, agency: {metadata.get('agency', 'None')}")
            if attachments:
                logger.info(f"DEBUG: Attachments found: {[att.get('name', att.get('url', 'unknown')) for att in attachments]}")
            else:
                logger.warning(f"DEBUG: No attachments found in scraping result!")
            
            # Update opportunity with metadata
            metadata_updated = False
            if metadata.get('title'):
                opportunity.title = metadata['title']
                metadata_updated = True
                logger.info(f"Updated opportunity title: {metadata['title'][:50]}")
            
            if metadata.get('notice_id'):
                new_notice_id = metadata['notice_id']
                # Check if this notice_id already exists for another opportunity
                existing_notice = db.query(Opportunity).filter(
                    Opportunity.notice_id == new_notice_id,
                    Opportunity.id != opportunity_id
                ).first()
                
                if existing_notice:
                    logger.warning(f"Skipping notice_id update: {new_notice_id} already exists for opportunity {existing_notice.id}")
                elif opportunity.notice_id and opportunity.notice_id != new_notice_id:
                    logger.warning(f"Opportunity {opportunity_id} already has notice_id={opportunity.notice_id}, not updating to {new_notice_id}")
                else:
                    opportunity.notice_id = new_notice_id
                    metadata_updated = True
                    logger.info(f"Updated opportunity notice_id: {new_notice_id}")
                
                # Only update sam_gov_id if not already set (for backward compatibility)
                # Don't update if it's already set to avoid unique constraint violations
                new_sam_gov_id = metadata['notice_id']
                if not opportunity.sam_gov_id:
                    # Check if this sam_gov_id already exists for another opportunity
                    existing_sam = db.query(Opportunity).filter(
                        Opportunity.sam_gov_id == new_sam_gov_id,
                        Opportunity.id != opportunity_id
                    ).first()
                    if not existing_sam:
                        opportunity.sam_gov_id = new_sam_gov_id
                        logger.info(f"Updated opportunity sam_gov_id: {new_sam_gov_id}")
                    else:
                        logger.warning(f"Skipping sam_gov_id update: {new_sam_gov_id} already exists for opportunity {existing_sam.id}")
                elif opportunity.sam_gov_id != new_sam_gov_id:
                    logger.warning(f"Opportunity {opportunity_id} already has sam_gov_id={opportunity.sam_gov_id}, not updating to {new_sam_gov_id}")
            
            if metadata.get('description'):
                opportunity.description = metadata['description']
                metadata_updated = True
                logger.info(f"Updated opportunity description ({len(metadata['description'])} chars)")
            
            if metadata.get('agency'):
                opportunity.agency = metadata['agency']
                metadata_updated = True
                logger.info(f"Updated opportunity agency: {metadata['agency']}")
            
            if metadata.get('status'):
                # Don't overwrite status if it's already "processing" - let analyze_documents set it to "completed"
                if opportunity.status != "processing":
                    opportunity.status = metadata['status'].lower()
                    metadata_updated = True
            
            # Store contact information
            if metadata.get('primary_contact'):
                opportunity.primary_contact = metadata['primary_contact']
                metadata_updated = True
                logger.info(f"Updated primary contact: {metadata['primary_contact'].get('name', 'N/A')}")
            
            if metadata.get('alternative_contact'):
                opportunity.alternative_contact = metadata['alternative_contact']
                metadata_updated = True
                logger.info(f"Updated alternative contact: {metadata['alternative_contact'].get('name', 'N/A')}")
            
            if metadata.get('contracting_office_address'):
                opportunity.contracting_office_address = metadata['contracting_office_address']
                metadata_updated = True
                logger.info(f"Updated contracting office address")
            
            # Commit metadata updates immediately so frontend can see them
            if metadata_updated:
                try:
                    db.commit()
                    db.refresh(opportunity)  # Refresh to ensure frontend gets latest data
                    logger.info(f"Committed metadata updates for opportunity {opportunity_id}")
                except Exception as e:
                    db.rollback()
                    logger.error(f"Error committing metadata updates for opportunity {opportunity_id}: {str(e)}")
                    # Re-raise to let the outer exception handler deal with it
                    raise
            
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
                    # Commit deadline immediately so frontend can see it
                    db.commit()
                    logger.info(f"Added deadline: {deadline_dt} {deadline_time_str} {timezone_str}")
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
                db.refresh(opportunity)  # Refresh to ensure frontend gets latest data
                logger.info(f"DEBUG: Committed {len(downloaded_files)} documents to database")
            else:
                logger.warning(f"DEBUG: No attachments to download - attachments list was empty or None!")
            
            # Keep status as "processing" - will be set to "completed" after analysis finishes
            # Don't set to completed here - let analyze_documents set it after analysis
            db.commit()
            
            logger.info(f"Successfully scraped opportunity {opportunity_id}")
            
            # Trigger document analysis (will set status to "completed" when done)
            # Check if analysis is enabled (stored in opportunity metadata)
            enable_document_analysis = opportunity.enable_document_analysis.lower() == "true" if opportunity.enable_document_analysis else False
            enable_clin_extraction = opportunity.enable_clin_extraction.lower() == "true" if opportunity.enable_clin_extraction else False
            analyze_documents.delay(opportunity_id, enable_document_analysis, enable_clin_extraction, sam_gov_page_text)
            
            return {
                "status": "success",
                "opportunity_id": opportunity_id,
                "attachments_downloaded": len(attachments)
            }
        
    except Exception as e:
        logger.error(f"Error scraping opportunity {opportunity_id}: {str(e)}", exc_info=True)
        try:
            db.rollback()
            if opportunity:
                opportunity.status = "failed"
                opportunity.error_message = str(e)
                db.commit()
        except Exception as rollback_error:
            logger.error(f"Error during rollback/status update: {str(rollback_error)}")
        return {"status": "error", "message": str(e)}
    finally:
        db.close()


@celery_app.task(name="analyze_documents")
def analyze_documents(opportunity_id: int, enable_document_analysis: bool = False, enable_clin_extraction: bool = False, sam_gov_page_text: str = ''):
    """
    Background task to analyze downloaded documents
    This will extract CLINs, classify solicitation type, etc.
    
    Args:
        opportunity_id: ID of the opportunity to analyze
        enable_document_analysis: Whether to run document analysis (text extraction, classification, etc.)
        enable_clin_extraction: Whether to extract CLINs from documents
        sam_gov_page_text: Text content from SAM.gov page for LLM analysis
    """
    db = SessionLocal()
    try:
        opportunity = db.query(Opportunity).filter(Opportunity.id == opportunity_id).first()
        if not opportunity:
            logger.error(f"Opportunity {opportunity_id} not found")
            return {"status": "error", "message": "Opportunity not found"}
        
        # Check if document analysis is enabled
        if not enable_document_analysis:
            logger.info(f"Document analysis is DISABLED for opportunity {opportunity_id} - skipping analysis")
            # Set status to completed since scraping is done
            opportunity.status = "completed"
            db.commit()
            db.refresh(opportunity)
            return {"status": "success", "message": "Document analysis disabled"}
        
        # Get all documents for this opportunity
        documents = db.query(Document).filter(Document.opportunity_id == opportunity_id).all()
        
        # Check if we have SAM.gov page text or documents to analyze
        has_sam_gov_text = sam_gov_page_text and sam_gov_page_text.strip()
        
        if not documents and not has_sam_gov_text:
            logger.warning(f"No documents found and no SAM.gov page text for opportunity {opportunity_id}")
            # Set status to completed since there's nothing to analyze
            opportunity.status = "completed"
            db.commit()
            db.refresh(opportunity)
            return {"status": "success", "message": "No documents or SAM.gov page text to analyze"}
        
        if not documents:
            logger.info(f"No documents found for opportunity {opportunity_id}, but SAM.gov page text is available - will analyze SAM.gov page only")
        else:
            logger.info(f"Starting document analysis for opportunity {opportunity_id} ({len(documents)} documents)")
        
        logger.info(f"Starting analysis for opportunity {opportunity_id} ({len(documents)} documents, SAM.gov page text: {'yes' if has_sam_gov_text else 'no'})")
        
        # Initialize document analyzer
        analyzer = DocumentAnalyzer()
        
        # Combine all extracted text from all documents
        all_text = []
        clins_found = []
        deadlines_found = []
        
        # 1. Extract text from all documents first (for batch processing)
        document_texts = []  # List of (doc_name, text) tuples for batch CLIN extraction
        import time
        for doc_idx, doc in enumerate(documents, 1):
            # Check file type - also check extension for OTHER types
            file_ext = Path(doc.file_name).suffix.lower()
            is_supported_type = (
                doc.file_type in [DocumentType.PDF, DocumentType.WORD, DocumentType.EXCEL] or
                file_ext in ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.txt']
            )
            
            if not is_supported_type:
                logger.debug(f"Skipping document {doc.id} - unsupported type: {doc.file_type} (extension: {file_ext})")
                continue
            
            # Skip Q&A documents and similar files for CLIN extraction
            doc_name_lower = doc.file_name.lower()
            is_qa_document = any(keyword in doc_name_lower for keyword in ['question', 'q&a', 'qa', 'inquiry', 'clarification'])
            
            logger.info(f"[{doc_idx}/{len(documents)}] Processing document: {doc.file_name}")
            
            # Add delay between documents to avoid rate limits (except for first document)
            if doc_idx > 1:
                delay = 2  # 2 seconds between documents
                logger.debug(f"Waiting {delay}s before processing next document...")
                time.sleep(delay)
            
            try:
                # Get absolute file path
                doc_file_path = Path(doc.file_path)
                if not doc_file_path.is_absolute():
                    doc_file_path = Path(settings.PROJECT_ROOT) / doc.file_path
                
                logger.info(f"Attempting to extract text from: {doc.file_path} (absolute: {doc_file_path})")
                # Commit progress periodically so frontend can see updates
                if doc_idx % 2 == 0:  # Commit every 2 documents
                    db.commit()
                    db.refresh(opportunity)
                
                text = analyzer.extract_text(doc.file_path)
                if text and text.strip():
                    all_text.append(text)
                    logger.info(f"Extracted {len(text)} characters from {doc.file_name}")
                    
                    # DEBUG: Save extracted text to file for debugging
                    try:
                        debug_dir = settings.DEBUG_EXTRACTS_DIR / f"opportunity_{opportunity_id}"
                        debug_dir.mkdir(parents=True, exist_ok=True)
                        debug_file = debug_dir / f"{doc.id}_{doc.file_name}_extracted.txt"
                        with open(debug_file, 'w', encoding='utf-8') as f:
                            f.write(f"Document: {doc.file_name}\n")
                            f.write(f"File Path: {doc.file_path}\n")
                            f.write(f"Document Type: {doc.file_type}\n")
                            f.write(f"Source: {doc.source}\n")
                            f.write(f"Size: {doc.file_size} bytes\n")
                            f.write("=" * 80 + "\n")
                            f.write("EXTRACTED TEXT:\n")
                            f.write("=" * 80 + "\n")
                            f.write(text)
                        logger.info(f"DEBUG: Saved extracted text to {debug_file}")
                    except Exception as debug_error:
                        logger.warning(f"Failed to save debug extract: {str(debug_error)}")
                    
                    # Collect documents for batch CLIN extraction (skip Q&A documents)
                    if not is_qa_document:
                        document_texts.append((doc.file_name, text))
                    
                    # Extract deadlines will be done later with LLM including SAM.gov page text
                    # Skip individual document deadline extraction
                    
                    # Delivery requirements are now extracted as part of CLIN extraction
                else:
                    logger.warning(f"No text extracted from {doc.file_name} (file exists: {doc_file_path.exists()})")
            except Exception as e:
                logger.error(f"Error extracting text from {doc.file_name}: {str(e)}", exc_info=True)
                continue
        
        # 2. Extract CLINs from all documents + SAM.gov page in batch (single LLM call)
        # Include SAM.gov page text if available
        if enable_clin_extraction:
            # Add SAM.gov page text as first document if available
            if sam_gov_page_text and sam_gov_page_text.strip():
                logger.info(f"Including SAM.gov page text ({len(sam_gov_page_text)} chars) in CLIN extraction")
                document_texts.insert(0, ("SAM.gov Opportunity Page", sam_gov_page_text))
            
            # If no documents but we have SAM.gov page text, still try CLIN extraction
            if document_texts:
                logger.info(f"Batch extracting CLINs, deadlines, manufacturers, and dealers from {len(document_texts)} sources (including SAM.gov page) in a single LLM call")
                try:
                    batch_clins, batch_deadlines, batch_manufacturers, batch_dealers = analyzer.extract_clins_batch(document_texts)
                    clins_found.extend(batch_clins)
                    deadlines_found.extend(batch_deadlines)
                    logger.info(f"Batch extraction found {len(batch_clins)} CLINs, {len(batch_deadlines)} deadlines, {len(batch_manufacturers)} manufacturers, {len(batch_dealers)} dealers")
                    
                    # Store manufacturers and dealers for later saving
                    manufacturers_found = batch_manufacturers
                    dealers_found = batch_dealers
                    
                    # DEBUG: Save batch CLIN extraction results
                    try:
                        debug_dir = settings.DEBUG_EXTRACTS_DIR / f"opportunity_{opportunity_id}"
                        debug_dir.mkdir(parents=True, exist_ok=True)
                        batch_clin_debug_file = debug_dir / "batch_clins.txt"
                        with open(batch_clin_debug_file, 'w', encoding='utf-8') as f:
                            f.write(f"Batch CLIN Extraction Results\n")
                            f.write(f"Total Documents Processed: {len(document_texts)}\n")
                            f.write(f"Total CLINs Found: {len(batch_clins)}\n")
                            f.write("=" * 80 + "\n")
                            for i, clin in enumerate(batch_clins, 1):
                                f.write(f"\nCLIN {i}:\n")
                                f.write("-" * 80 + "\n")
                                for key, value in clin.items():
                                    if value:
                                        f.write(f"{key}: {value}\n")
                        logger.info(f"DEBUG: Saved batch CLIN extraction results to {batch_clin_debug_file}")
                    except Exception as batch_debug_error:
                        logger.warning(f"Failed to save batch CLIN debug extract: {str(batch_debug_error)}")
                except Exception as batch_error:
                    logger.error(f"Batch CLIN extraction failed: {str(batch_error)}", exc_info=True)
                    # No fallback - we want all documents combined in one request
                    logger.warning("CLIN extraction failed - no fallback to individual processing")
        else:
            if not enable_clin_extraction:
                logger.info("CLIN extraction is DISABLED - skipping")
            elif not document_texts and not (sam_gov_page_text and sam_gov_page_text.strip()):
                logger.info("No document texts or SAM.gov page text available for CLIN extraction")
        
        # Deadlines are now extracted together with CLINs in the batch extraction above
        # No separate deadline extraction needed
        
        # Combine document texts for classification (if needed)
        combined_text = "\n\n".join(all_text)
        if sam_gov_page_text and sam_gov_page_text.strip():
            if combined_text:
                combined_text = f"=== SAM.gov Opportunity Page ===\n{sam_gov_page_text}\n\n{combined_text}"
            else:
                combined_text = f"=== SAM.gov Opportunity Page ===\n{sam_gov_page_text}"
        
        # 3. Classify solicitation type (product/service/hybrid)
        logger.info("Classifying solicitation type...")
        classification, confidence = analyzer.classify_solicitation_type(
            text=combined_text if combined_text else "",
            title=opportunity.title,
            description=opportunity.description
        )
        
        opportunity.solicitation_type = classification
        opportunity.classification_confidence = f"{confidence:.2f}"
        logger.info(f"Classification: {classification.value}, confidence: {confidence:.2f}")
        
        # 4. Simple deduplication: merge CLINs with same number
        deduplicated_clins = {}
        for clin_data in clins_found:
            clin_number = clin_data.get('clin_number', '')
            if not clin_number:
                continue
            
            if clin_number not in deduplicated_clins:
                deduplicated_clins[clin_number] = clin_data
            else:
                # Merge: fill in missing fields from new CLIN
                existing = deduplicated_clins[clin_number]
                for key in clin_data:
                    if not existing.get(key) and clin_data.get(key):
                        existing[key] = clin_data[key]
                    # Prefer longer text fields
                    elif key in ['product_description', 'scope_of_work', 'delivery_timeline']:
                        if clin_data.get(key) and len(clin_data[key]) > len(existing.get(key, '')):
                            existing[key] = clin_data[key]
        
        logger.info(f"Deduplicated {len(clins_found)} CLINs to {len(deduplicated_clins)} unique CLINs")
        
        # 5. Store CLINs in database
        logger.info(f"Storing {len(deduplicated_clins)} CLINs...")
        for clin_data in deduplicated_clins.values():
            # Check if CLIN already exists
            existing_clin = db.query(CLIN).filter(
                CLIN.opportunity_id == opportunity_id,
                CLIN.clin_number == clin_data['clin_number']
            ).first()
            
            # Prepare additional_data
            additional_data = {}
            if clin_data.get('drawing_number'):
                additional_data['drawing_number'] = clin_data['drawing_number']
            if clin_data.get('delivery_address'):
                additional_data['delivery_address'] = clin_data['delivery_address']
            if clin_data.get('special_delivery_instructions'):
                additional_data['special_delivery_instructions'] = clin_data['special_delivery_instructions']
            if clin_data.get('delivery_timeline'):
                additional_data['delivery_timeline'] = clin_data['delivery_timeline']
            
            if not existing_clin:
                # Create new CLIN
                clin = CLIN(
                    opportunity_id=opportunity.id,
                    clin_number=clin_data['clin_number'],
                    clin_name=clin_data.get('clin_name'),
                    base_item_number=clin_data.get('base_item_number'),
                    product_name=clin_data.get('product_name'),
                    product_description=clin_data.get('product_description'),
                    manufacturer_name=clin_data.get('manufacturer_name'),
                    part_number=clin_data.get('part_number'),
                    model_number=clin_data.get('model_number'),
                    quantity=clin_data.get('quantity'),
                    unit_of_measure=clin_data.get('unit_of_measure'),
                    contract_type=clin_data.get('contract_type'),
                    extended_price=clin_data.get('extended_price'),
                    service_description=clin_data.get('service_description'),
                    scope_of_work=clin_data.get('scope_of_work'),
                    timeline=_truncate_string(clin_data.get('delivery_timeline'), max_length=255),
                    service_requirements=clin_data.get('service_requirements'),
                    additional_data=additional_data if additional_data else None,
                )
                db.add(clin)
            else:
                # Update existing CLIN - fill missing fields, prefer longer text
                if not existing_clin.base_item_number and clin_data.get('base_item_number'):
                    existing_clin.base_item_number = clin_data['base_item_number']
                if not existing_clin.product_name and clin_data.get('product_name'):
                    existing_clin.product_name = clin_data['product_name']
                if not existing_clin.product_description and clin_data.get('product_description'):
                    existing_clin.product_description = clin_data['product_description']
                elif clin_data.get('product_description') and len(clin_data['product_description']) > len(existing_clin.product_description or ''):
                    existing_clin.product_description = clin_data['product_description']
                if not existing_clin.manufacturer_name and clin_data.get('manufacturer_name'):
                    existing_clin.manufacturer_name = clin_data['manufacturer_name']
                if not existing_clin.part_number and clin_data.get('part_number'):
                    existing_clin.part_number = clin_data['part_number']
                if not existing_clin.model_number and clin_data.get('model_number'):
                    existing_clin.model_number = clin_data['model_number']
                if not existing_clin.contract_type and clin_data.get('contract_type'):
                    existing_clin.contract_type = clin_data['contract_type']
                if not existing_clin.extended_price and clin_data.get('extended_price'):
                    existing_clin.extended_price = clin_data['extended_price']
                if not existing_clin.service_description and clin_data.get('service_description'):
                    existing_clin.service_description = clin_data['service_description']
                if not existing_clin.scope_of_work and clin_data.get('scope_of_work'):
                    existing_clin.scope_of_work = clin_data['scope_of_work']
                elif clin_data.get('scope_of_work') and len(clin_data['scope_of_work']) > len(existing_clin.scope_of_work or ''):
                    existing_clin.scope_of_work = clin_data['scope_of_work']
                if not existing_clin.service_requirements and clin_data.get('service_requirements'):
                    existing_clin.service_requirements = clin_data['service_requirements']
                
                # Update timeline
                if clin_data.get('delivery_timeline'):
                    if existing_clin.additional_data is None:
                        existing_clin.additional_data = {}
                    existing_clin.additional_data['delivery_timeline'] = clin_data['delivery_timeline']
                    if not existing_clin.timeline or len(clin_data['delivery_timeline']) > len(existing_clin.timeline or ''):
                        existing_clin.timeline = _truncate_string(clin_data['delivery_timeline'], max_length=255)
                
                # Update additional_data for drawing_number, delivery_address, special_delivery_instructions
                if clin_data.get('drawing_number'):
                    if existing_clin.additional_data is None:
                        existing_clin.additional_data = {}
                    existing_clin.additional_data['drawing_number'] = clin_data['drawing_number']
                if clin_data.get('delivery_address'):
                    if existing_clin.additional_data is None:
                        existing_clin.additional_data = {}
                    existing_clin.additional_data['delivery_address'] = clin_data['delivery_address']
                if clin_data.get('special_delivery_instructions'):
                    if existing_clin.additional_data is None:
                        existing_clin.additional_data = {}
                    existing_clin.additional_data['special_delivery_instructions'] = clin_data['special_delivery_instructions']
        
        # Commit CLINs to database
        db.commit()
        logger.info("CLINs committed to database")
        
        # 4. Save Manufacturers and Dealers FROM DOCUMENTS (extracted together with CLINs)
        logger.info("Phase 1: Saving manufacturers and dealers extracted FROM DOCUMENTS...")
        try:
            # Manufacturers and dealers were already extracted together with CLINs
            manufacturers_found = batch_manufacturers if 'batch_manufacturers' in locals() else []
            dealers_found = batch_dealers if 'batch_dealers' in locals() else []
            
            logger.info(f"Found {len(manufacturers_found)} manufacturers and {len(dealers_found)} dealers from document extraction")
            
            # Get CLINs for linking
            db_clins = db.query(CLIN).filter(CLIN.opportunity_id == opportunity_id).all()
            
            # Save manufacturers to database
            if manufacturers_found:
                saved_manufacturers = save_extracted_manufacturers(
                    db=db,
                    opportunity_id=opportunity_id,
                    manufacturers=manufacturers_found,
                    clins=db_clins
                )
                logger.info(f"Saved {len(saved_manufacturers)} manufacturers to database (from documents)")
            
            # Save dealers to database
            if dealers_found:
                saved_manufacturers_list = db.query(Manufacturer).filter(
                    Manufacturer.opportunity_id == opportunity_id
                ).all()
                saved_dealers = save_extracted_dealers(
                    db=db,
                    opportunity_id=opportunity_id,
                    dealers=dealers_found,
                    manufacturers=saved_manufacturers_list if manufacturers_found else None,
                    clins=db_clins
                )
                logger.info(f"Saved {len(saved_dealers)} dealers to database (from documents)")
            
            # Phase 2: Trigger external web research for manufacturers needing website/contact info
            manufacturers_needing_research = db.query(Manufacturer).filter(
                Manufacturer.opportunity_id == opportunity_id,
                Manufacturer.research_source == "document_extraction"
            ).all()
            
            if manufacturers_needing_research:
                logger.info(f"Phase 2: Triggering external research for {len(manufacturers_needing_research)} manufacturers")
                # Trigger external research as background task
                research_manufacturers_external.delay(opportunity_id)
            else:
                logger.info("No manufacturers found in documents - skipping external research")
        except Exception as mfg_dealer_error:
            logger.error(f"Error saving manufacturers/dealers: {str(mfg_dealer_error)}", exc_info=True)
            # Don't fail the whole task if manufacturer/dealer saving fails
        
        # 5. Deduplicate deadlines before storing
        deduplicated_deadlines = []
        seen_deadlines = set()
        
        for deadline_data in deadlines_found:
            if not deadline_data.get('due_date'):
                continue
            
            # Parse and normalize date
            due_date = deadline_data['due_date']
            if isinstance(due_date, str):
                due_date = dateutil_parser.parse(due_date)
            
            # Normalize date to date-only for comparison (ignore time component)
            if hasattr(due_date, 'date'):
                date_key = due_date.date()
            elif isinstance(due_date, datetime):
                date_key = due_date.date()
            else:
                date_key = due_date
            
            deadline_type = deadline_data.get('deadline_type', 'submission')
            due_time = deadline_data.get('due_time') or ''
            timezone = deadline_data.get('timezone') or ''
            
            # Create unique key: (date, deadline_type, due_time, timezone)
            unique_key = (date_key, deadline_type, due_time, timezone)
            
            if unique_key not in seen_deadlines:
                seen_deadlines.add(unique_key)
                deduplicated_deadlines.append(deadline_data)
            else:
                logger.debug(f"Skipping duplicate deadline: {date_key} {deadline_type} {due_time} {timezone}")
        
        logger.info(f"Deduplicated {len(deadlines_found)} deadlines to {len(deduplicated_deadlines)} unique deadlines")
        
        # 6. Store deduplicated deadlines
        logger.info(f"Storing {len(deduplicated_deadlines)} deadlines from documents...")
        for deadline_data in deduplicated_deadlines:
            # Parse date
            due_date = deadline_data['due_date']
            if isinstance(due_date, str):
                due_date = dateutil_parser.parse(due_date)
            
            # Normalize date to date-only for comparison
            if hasattr(due_date, 'date'):
                date_key = due_date.date()
            elif isinstance(due_date, datetime):
                date_key = due_date.date()
            else:
                date_key = due_date
            
            deadline_type = deadline_data.get('deadline_type', 'submission')
            due_time = deadline_data.get('due_time') or ''
            timezone = deadline_data.get('timezone') or ''
            
            # Check if similar deadline already exists in database (avoid duplicates)
            # Compare by date (date only), deadline_type, due_time, and timezone
            existing_deadline = db.query(Deadline).filter(
                Deadline.opportunity_id == opportunity_id,
                func.date(Deadline.due_date) == date_key,
                Deadline.deadline_type == deadline_type,
                Deadline.due_time == due_time,
                Deadline.timezone == timezone
            ).first()
            
            if not existing_deadline:
                deadline = Deadline(
                    opportunity_id=opportunity.id,
                    due_date=deadline_data['due_date'],
                    due_time=deadline_data.get('due_time'),
                    timezone=deadline_data.get('timezone'),
                    deadline_type=deadline_data.get('deadline_type'),
                    description=deadline_data.get('description'),
                    is_primary=deadline_data.get('is_primary', False)
                )
                db.add(deadline)
            else:
                logger.debug(f"Deadline already exists in database: {date_key} {deadline_type} {due_time} {timezone}")
        
        # Update status to completed AFTER analysis is done
        opportunity.status = "completed"
        
        # Commit all changes
        db.commit()
        
        # DEBUG: Save analysis summary to file
        try:
            debug_dir = settings.DEBUG_EXTRACTS_DIR / f"opportunity_{opportunity_id}"
            debug_dir.mkdir(parents=True, exist_ok=True)
            summary_file = debug_dir / "analysis_summary.txt"
            with open(summary_file, 'w', encoding='utf-8') as f:
                f.write(f"Opportunity Analysis Summary - ID: {opportunity_id}\n")
                f.write("=" * 80 + "\n\n")
                f.write(f"Title: {opportunity.title}\n")
                f.write(f"Notice ID: {opportunity.notice_id}\n")
                f.write(f"Status: {opportunity.status}\n")
                f.write(f"Documents Analyzed: {len(documents)}\n")
                f.write(f"Classification: {classification.value}\n")
                f.write(f"Confidence: {confidence:.2f}\n")
                f.write(f"CLINs Extracted: {len(clins_found)}\n")
                f.write(f"Deadlines Extracted: {len(deadlines_found)}\n")
                f.write("\n" + "=" * 80 + "\n")
                f.write("DOCUMENTS:\n")
                f.write("=" * 80 + "\n")
                for doc in documents:
                    f.write(f"\n- {doc.file_name} ({doc.file_type}, {doc.file_size} bytes)\n")
                f.write("\n" + "=" * 80 + "\n")
                f.write(f"ALL CLINs EXTRACTED ({len(clins_found)}):\n")
                f.write("=" * 80 + "\n")
                for i, clin in enumerate(clins_found, 1):
                    f.write(f"\nCLIN {i}:\n")
                    f.write("-" * 80 + "\n")
                    for key, value in clin.items():
                        if value:
                            f.write(f"  {key}: {value}\n")
            logger.info(f"DEBUG: Saved analysis summary to {summary_file}")
        except Exception as summary_error:
            logger.warning(f"Failed to save analysis summary: {str(summary_error)}")
        
        logger.info(f"Successfully analyzed documents for opportunity {opportunity_id}")
        logger.info(f"  - Classification: {classification.value} (confidence: {confidence:.2f})")
        logger.info(f"  - CLINs extracted: {len(clins_found)}")
        logger.info(f"  - Deadlines extracted: {len(deadlines_found)}")
        
        return {
            "status": "success",
            "opportunity_id": opportunity_id,
            "documents_analyzed": len(documents),
            "classification": classification.value,
            "confidence": confidence,
            "clins_extracted": len(clins_found),
            "deadlines_extracted": len(deadlines_found)
        }
        
    except Exception as e:
        logger.error(f"Error analyzing documents for opportunity {opportunity_id}: {str(e)}", exc_info=True)
        if opportunity:
            opportunity.status = "failed"
            opportunity.error_message = f"Document analysis failed: {str(e)}"
            db.commit()
        return {"status": "error", "message": str(e)}
    finally:
        db.close()


@celery_app.task(name="research_manufacturers_external")
def research_manufacturers_external(opportunity_id: int):
    """
    Phase 2: External research for manufacturers found in documents
    Uses LLM-guided web search to find websites, contact info, and authorized dealers
    
    Args:
        opportunity_id: ID of the opportunity
    """
    db = SessionLocal()
    try:
        opportunity = db.query(Opportunity).filter(Opportunity.id == opportunity_id).first()
        if not opportunity:
            logger.error(f"Opportunity {opportunity_id} not found")
            return {"status": "error", "message": "Opportunity not found"}
        
        # Get manufacturers that need external research (found in documents but missing website/contact)
        manufacturers = db.query(Manufacturer).filter(
            Manufacturer.opportunity_id == opportunity_id,
            Manufacturer.research_source == "document_extraction"
        ).all()
        
        if not manufacturers:
            logger.info(f"No manufacturers found for external research (opportunity {opportunity_id})")
            return {"status": "success", "message": "No manufacturers to research"}
        
        logger.info(f"Phase 2: Starting LLM-guided external research for {len(manufacturers)} manufacturers")
        
        # Load reference material for online search strategies
        reference_text = None
        try:
            reference_file = Path(settings.PROJECT_ROOT) / "extras" / "ONLINE_SEARCH_GUIDE.md"
            if reference_file.exists():
                with open(reference_file, 'r', encoding='utf-8') as f:
                    reference_text = f.read()
                logger.info(f"Loaded online search guide: {len(reference_text)} characters")
        except Exception as ref_error:
            logger.warning(f"Failed to load online search guide: {str(ref_error)}")
        
        # Get CLINs for context
        clins = db.query(CLIN).filter(CLIN.opportunity_id == opportunity_id).all()
        clin_part_map = {clin.id: clin.part_number for clin in clins if clin.part_number}
        
        import time
        with LLMExternalResearchService() as research_service:
            for mfg_idx, manufacturer in enumerate(manufacturers, 1):
                try:
                    logger.info(f"[{mfg_idx}/{len(manufacturers)}] Researching: {manufacturer.name}")
                    
                    # Update status to in_progress
                    manufacturer.research_status = ResearchStatus.IN_PROGRESS
                    manufacturer.research_started_at = datetime.utcnow()
                    db.commit()
                    
                    # Get part number from associated CLIN
                    part_number = manufacturer.part_number
                    if not part_number and manufacturer.clin_id and manufacturer.clin_id in clin_part_map:
                        part_number = clin_part_map[manufacturer.clin_id]
                    
                    # Research manufacturer website and find dealers using LLM-guided search
                    research_results = research_service.research_manufacturer_and_dealers(
                        manufacturer=manufacturer,
                        part_number=part_number,
                        nsn=manufacturer.nsn,
                        reference_text=reference_text
                    )
                    
                    # Update manufacturer with results
                    mfg_results = research_results.get('manufacturer', {})
                    if mfg_results.get('website'):
                        manufacturer.website = mfg_results['website']
                        manufacturer.website_verified = mfg_results.get('website_verified', False)
                        manufacturer.website_verification_date = datetime.utcnow()
                    
                    if mfg_results.get('contact_email'):
                        manufacturer.contact_email = mfg_results['contact_email']
                    
                    if mfg_results.get('contact_phone'):
                        manufacturer.contact_phone = mfg_results['contact_phone']
                    
                    if mfg_results.get('address'):
                        manufacturer.address = mfg_results['address']
                    
                    if mfg_results.get('sam_gov_verified'):
                        manufacturer.sam_gov_verified = True
                        manufacturer.sam_gov_verification_date = datetime.utcnow()
                    
                    # Update research status
                    manufacturer.research_status = ResearchStatus.COMPLETED
                    manufacturer.research_completed_at = datetime.utcnow()
                    manufacturer.research_source = "document_extraction,external_search"
                    
                    # Remove needs_external_research flag
                    if manufacturer.additional_data:
                        manufacturer.additional_data.pop('needs_external_research', None)
                    
                    db.commit()
                    logger.info(f"Completed manufacturer research: {manufacturer.name}")
                    logger.info(f"  Website: {bool(mfg_results.get('website'))}")
                    logger.info(f"  Email: {bool(mfg_results.get('contact_email'))}")
                    
                    # Save dealers found for this manufacturer
                    dealers_found = research_results.get('dealers', [])
                    if dealers_found:
                        logger.info(f"Found {len(dealers_found)} dealers for {manufacturer.name}")
                        from .research_service import save_external_dealers
                        saved_dealers = save_external_dealers(
                            db=db,
                            opportunity_id=opportunity_id,
                            dealers=dealers_found,
                            manufacturer=manufacturer,
                            clins=clins
                        )
                        logger.info(f"Saved {len(saved_dealers)} dealers to database")
                    
                    # Rate limiting - wait between manufacturers
                    if mfg_idx < len(manufacturers):
                        time.sleep(5)  # 5 seconds between manufacturers
                
                except Exception as mfg_error:
                    logger.error(f"Error researching manufacturer {manufacturer.name}: {str(mfg_error)}", exc_info=True)
                    manufacturer.research_status = ResearchStatus.FAILED
                    manufacturer.research_error = str(mfg_error)
                    manufacturer.research_completed_at = datetime.utcnow()
                    db.commit()
                    continue
        
        logger.info(f"Phase 2 complete: External research finished for {len(manufacturers)} manufacturers")
        
        return {
            "status": "success",
            "opportunity_id": opportunity_id,
            "manufacturers_researched": len(manufacturers)
        }
    
    except Exception as e:
        logger.error(f"Error in external research for opportunity {opportunity_id}: {str(e)}", exc_info=True)
        return {"status": "error", "message": str(e)}
    finally:
        db.close()
