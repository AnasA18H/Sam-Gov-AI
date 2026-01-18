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
from ..models.clin import CLIN
from .sam_gov_scraper import SAMGovScraper
from .document_downloader import DocumentDownloader
from .document_analyzer import DocumentAnalyzer
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
            
            # Keep status as "processing" - will be set to "completed" after analysis finishes
            # Don't set to completed here - let analyze_documents set it after analysis
            db.commit()
            
            logger.info(f"Successfully scraped opportunity {opportunity_id}")
            
            # Trigger document analysis (will set status to "completed" when done)
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
        
        # Initialize document analyzer
        analyzer = DocumentAnalyzer()
        
        # Combine all extracted text from all documents
        all_text = []
        clins_found = []
        deadlines_found = []
        
        # 1. Extract text from all documents
        for doc in documents:
            if doc.file_type not in [DocumentType.PDF, DocumentType.WORD, DocumentType.EXCEL]:
                logger.debug(f"Skipping document {doc.id} - unsupported type: {doc.file_type}")
                continue
            
            # Skip Q&A documents and similar files for CLIN extraction
            doc_name_lower = doc.file_name.lower()
            is_qa_document = any(keyword in doc_name_lower for keyword in ['question', 'q&a', 'qa', 'inquiry', 'clarification'])
            
            logger.info(f"Extracting text from document: {doc.file_name}")
            try:
                # Get absolute file path
                doc_file_path = Path(doc.file_path)
                if not doc_file_path.is_absolute():
                    doc_file_path = Path(settings.PROJECT_ROOT) / doc.file_path
                
                text = analyzer.extract_text(doc.file_path)
                if text:
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
                    
                    # Only extract CLINs from non-Q&A documents (solicitation, SOW, technical docs)
                    if not is_qa_document:
                        # Use hybrid extraction (table parsing + LLM + regex fallback)
                        doc_clins = analyzer.extract_clins(text, file_path=doc_file_path if doc.file_type == DocumentType.PDF else None)
                        clins_found.extend(doc_clins)
                        
                        # DEBUG: Save CLIN extraction results
                        if doc_clins:
                            try:
                                clin_debug_file = debug_dir / f"{doc.id}_{doc.file_name}_clins.txt"
                                with open(clin_debug_file, 'w', encoding='utf-8') as f:
                                    f.write(f"CLINs Extracted from: {doc.file_name}\n")
                                    f.write(f"Total CLINs: {len(doc_clins)}\n")
                                    f.write("=" * 80 + "\n")
                                    for i, clin in enumerate(doc_clins, 1):
                                        f.write(f"\nCLIN {i}:\n")
                                        f.write("-" * 80 + "\n")
                                        for key, value in clin.items():
                                            if value:
                                                f.write(f"{key}: {value}\n")
                                logger.info(f"DEBUG: Saved CLIN extraction results to {clin_debug_file}")
                            except Exception as clin_debug_error:
                                logger.warning(f"Failed to save CLIN debug extract: {str(clin_debug_error)}")
                    else:
                        logger.info(f"Skipping CLIN extraction from Q&A document: {doc.file_name}")
                    
                    # Extract deadlines from this document
                    doc_deadlines = analyzer.extract_deadlines(text)
                    deadlines_found.extend(doc_deadlines)
                else:
                    logger.warning(f"No text extracted from {doc.file_name}")
            except Exception as e:
                logger.error(f"Error extracting text from {doc.file_name}: {str(e)}", exc_info=True)
                continue
        
        combined_text = "\n\n".join(all_text)
        
        if not combined_text:
            logger.warning(f"No text extracted from any documents for opportunity {opportunity_id}")
            return {
                "status": "success",
                "opportunity_id": opportunity_id,
                "documents_analyzed": len(documents),
                "message": "No text extracted from documents"
            }
        
        # 2. Classify solicitation type (product/service/hybrid)
        logger.info("Classifying solicitation type...")
        classification, confidence = analyzer.classify_solicitation_type(
            text=combined_text,
            title=opportunity.title,
            description=opportunity.description
        )
        
        opportunity.solicitation_type = classification
        opportunity.classification_confidence = f"{confidence:.2f}"
        logger.info(f"Classification: {classification.value}, confidence: {confidence:.2f}")
        
        # 3. Store CLINs in database
        logger.info(f"Storing {len(clins_found)} CLINs...")
        for clin_data in clins_found:
            # Check if CLIN already exists for this opportunity
            existing_clin = db.query(CLIN).filter(
                CLIN.opportunity_id == opportunity_id,
                CLIN.clin_number == clin_data['clin_number']
            ).first()
            
            if not existing_clin:
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
                    timeline=clin_data.get('timeline'),
                    service_requirements=clin_data.get('service_requirements'),
                )
                db.add(clin)
            else:
                # Update existing CLIN if we have new information
                if clin_data.get('base_item_number') and not existing_clin.base_item_number:
                    existing_clin.base_item_number = clin_data['base_item_number']
                if clin_data.get('product_name') and not existing_clin.product_name:
                    existing_clin.product_name = clin_data['product_name']
                if clin_data.get('product_description') and not existing_clin.product_description:
                    existing_clin.product_description = clin_data['product_description']
                if clin_data.get('manufacturer_name') and not existing_clin.manufacturer_name:
                    existing_clin.manufacturer_name = clin_data['manufacturer_name']
                if clin_data.get('contract_type') and not existing_clin.contract_type:
                    existing_clin.contract_type = clin_data['contract_type']
                if clin_data.get('extended_price') and not existing_clin.extended_price:
                    existing_clin.extended_price = clin_data['extended_price']
        
        # 4. Store additional deadlines from documents
        logger.info(f"Storing {len(deadlines_found)} deadlines from documents...")
        for deadline_data in deadlines_found:
            # Check if similar deadline already exists (avoid duplicates)
            existing_deadline = db.query(Deadline).filter(
                Deadline.opportunity_id == opportunity_id,
                Deadline.due_date == deadline_data['due_date'],
                Deadline.deadline_type == deadline_data.get('deadline_type')
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
