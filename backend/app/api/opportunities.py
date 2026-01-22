"""
Opportunities API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from pathlib import Path
import os
import mimetypes
import shutil
import logging
import glob
from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..core.config import settings
from ..models.user import User
from ..models.opportunity import Opportunity
from ..models.document import Document, DocumentType, DocumentSource
from ..models.clin import CLIN
from ..models.deadline import Deadline
from ..schemas.opportunity import OpportunityCreate, OpportunityResponse, OpportunityDetailResponse, OpportunityList
from sqlalchemy.orm import joinedload
from ..services.tasks import scrape_sam_gov_opportunity

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


@router.post("", response_model=OpportunityResponse, status_code=status.HTTP_201_CREATED)
async def create_opportunity(
    sam_gov_url: str = Form(..., description="SAM.gov opportunity URL"),
    files: Optional[List[UploadFile]] = File(None, description="Optional additional documents"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Create a new opportunity from SAM.gov URL with optional file uploads"""
    # Check if opportunity already exists
    existing = db.query(Opportunity).filter(
        Opportunity.sam_gov_url == sam_gov_url
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Opportunity with this URL already exists"
        )
    
    # Create new opportunity
    new_opportunity = Opportunity(
        user_id=current_user.id,
        sam_gov_url=sam_gov_url,
        status="pending"
    )
    
    db.add(new_opportunity)
    db.commit()
    db.refresh(new_opportunity)
    
    # Save uploaded files if provided
    uploaded_files = []
    if files:
        # Create opportunity-specific upload directory
        upload_dir = settings.UPLOADS_DIR / str(new_opportunity.id)
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        for file in files:
            if file.filename:
                try:
                    # Determine file type
                    file_ext = Path(file.filename).suffix.lower()
                    if file_ext == '.pdf':
                        doc_type = DocumentType.PDF
                    elif file_ext in ['.doc', '.docx']:
                        doc_type = DocumentType.WORD
                    elif file_ext in ['.xls', '.xlsx']:
                        doc_type = DocumentType.EXCEL
                    else:
                        doc_type = DocumentType.OTHER
                    
                    # Sanitize filename
                    safe_filename = file.filename.replace('/', '_').replace('\\', '_')
                    file_path = upload_dir / safe_filename
                    
                    # Save file
                    with open(file_path, "wb") as buffer:
                        shutil.copyfileobj(file.file, buffer)
                    
                    file_size = file_path.stat().st_size
                    mime_type, _ = mimetypes.guess_type(file.filename)
                    
                    # Create document record
                    doc = Document(
                        opportunity_id=new_opportunity.id,
                        file_name=safe_filename,
                        original_file_name=file.filename,
                        file_path=str(file_path.relative_to(settings.PROJECT_ROOT)),
                        file_size=file_size,
                        file_type=doc_type,
                        mime_type=mime_type,
                        source=DocumentSource.USER_UPLOAD,
                        storage_type="local"
                    )
                    db.add(doc)
                    uploaded_files.append(doc)
                    
                except Exception as e:
                    # Log error but continue processing other files
                    logger.error(f"Error saving uploaded file {file.filename}: {str(e)}")
        
        # Commit uploaded file records
        if uploaded_files:
            db.commit()
    
    # Trigger background task to scrape SAM.gov and analyze documents (including uploaded files)
    scrape_sam_gov_opportunity.delay(new_opportunity.id)
    
    return new_opportunity


@router.get("", response_model=OpportunityList)
async def list_opportunities(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """List all opportunities for current user"""
    opportunities = db.query(Opportunity).filter(
        Opportunity.user_id == current_user.id
    ).offset(skip).limit(limit).all()
    
    total = db.query(Opportunity).filter(
        Opportunity.user_id == current_user.id
    ).count()
    
    return {
        "opportunities": opportunities,
        "total": total
    }


@router.get("/{opportunity_id}", response_model=OpportunityDetailResponse)
async def get_opportunity(
    opportunity_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get a specific opportunity by ID with documents, deadlines, and CLINs"""
    opportunity = db.query(Opportunity).options(
        joinedload(Opportunity.documents),
        joinedload(Opportunity.deadlines),
        joinedload(Opportunity.clins)
    ).filter(
        Opportunity.id == opportunity_id,
        Opportunity.user_id == current_user.id
    ).first()
    
    if not opportunity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Opportunity not found"
        )
    
    return opportunity


@router.delete("/{opportunity_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_opportunity(
    opportunity_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Delete an opportunity and all related data (documents, deadlines, CLINs) and files"""
    opportunity = db.query(Opportunity).filter(
        Opportunity.id == opportunity_id,
        Opportunity.user_id == current_user.id
    ).first()
    
    if not opportunity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Opportunity not found"
        )
    
    # Log all data that will be deleted
    logger.info(f"=" * 80)
    logger.info(f"DELETING OPPORTUNITY {opportunity_id}")
    logger.info(f"=" * 80)
    logger.info(f"Opportunity: {opportunity.title or 'Untitled'} (ID: {opportunity_id})")
    logger.info(f"Notice ID: {opportunity.notice_id or 'N/A'}")
    logger.info(f"Status: {opportunity.status}")
    
    # Get all related data before deletion
    documents = db.query(Document).filter(Document.opportunity_id == opportunity_id).all()
    clins = db.query(CLIN).filter(CLIN.opportunity_id == opportunity_id).all()
    deadlines = db.query(Deadline).filter(Deadline.opportunity_id == opportunity_id).all()
    
    # Log data counts
    logger.info(f"Related data to be deleted:")
    logger.info(f"  - Documents: {len(documents)}")
    logger.info(f"  - CLINs: {len(clins)}")
    logger.info(f"  - Deadlines: {len(deadlines)}")
    
    # Log document details
    if documents:
        logger.info(f"  Document files:")
        for doc in documents:
            logger.info(f"    - {doc.file_name} ({doc.file_type}, {doc.file_size or 'N/A'} bytes)")
    
    # Log CLIN details
    if clins:
        logger.info(f"  CLINs:")
        for clin in clins:
            logger.info(f"    - CLIN {clin.clin_number}: {clin.product_name or clin.clin_name or 'N/A'}")
    
    # Log deadline details
    if deadlines:
        logger.info(f"  Deadlines:")
        for deadline in deadlines:
            logger.info(f"    - {deadline.deadline_type}: {deadline.due_date} {deadline.due_time or ''}")
    
    logger.info(f"=" * 80)
    
    # Delete individual files from disk
    deleted_files = []
    failed_files = []
    for doc in documents:
        try:
            # Resolve file path
            file_path = Path(doc.file_path)
            
            # Handle relative paths
            if not file_path.is_absolute():
                # Try relative to project root
                abs_path = settings.PROJECT_ROOT / file_path
                if not abs_path.exists():
                    # Try relative to storage base path
                    if hasattr(settings, 'STORAGE_BASE_PATH'):
                        storage_base = Path(settings.STORAGE_BASE_PATH)
                        abs_path = storage_base.parent / file_path if 'backend/data' in str(file_path) else storage_base / file_path
                file_path = abs_path
            
            # Delete file if it exists
            if file_path.exists() and file_path.is_file():
                file_size = file_path.stat().st_size
                file_path.unlink()
                deleted_files.append(str(file_path))
                logger.info(f"✅ Deleted file: {file_path} ({file_size} bytes)")
            elif file_path.exists() and file_path.is_dir():
                # If it's a directory, remove it recursively
                shutil.rmtree(file_path)
                deleted_files.append(str(file_path))
                logger.info(f"✅ Deleted directory: {file_path}")
            else:
                logger.warning(f"⚠️  File not found: {file_path}")
        except Exception as e:
            failed_files.append((str(doc.file_path), str(e)))
            logger.warning(f"❌ Error deleting file {doc.file_path}: {str(e)}")
            # Continue deleting other files even if one fails
    
    if deleted_files:
        logger.info(f"Deleted {len(deleted_files)} file(s) from disk")
    if failed_files:
        logger.warning(f"Failed to delete {len(failed_files)} file(s)")
    
    # Delete all opportunity-related directories and their contents
    logger.info(f"Deleting opportunity directories and temp files...")
    directories_to_delete = []
    
    # Documents directory - check multiple possible locations
    if hasattr(settings, 'STORAGE_BASE_PATH'):
        # Primary location: backend/data/documents/{opportunity_id}
        storage_base = Path(settings.STORAGE_BASE_PATH)
        if not storage_base.is_absolute():
            storage_base = settings.PROJECT_ROOT / storage_base
        documents_dir = storage_base / str(opportunity_id)
        if documents_dir not in directories_to_delete:
            directories_to_delete.append(documents_dir)
    
    # Also check DOCUMENTS_DIR location (data/documents/{opportunity_id})
    documents_dir_alt = settings.DOCUMENTS_DIR / str(opportunity_id)
    if documents_dir_alt not in directories_to_delete:
        directories_to_delete.append(documents_dir_alt)
    
    # Also check backend/data/documents directly
    backend_docs_dir = settings.PROJECT_ROOT / "backend" / "data" / "documents" / str(opportunity_id)
    if backend_docs_dir not in directories_to_delete:
        directories_to_delete.append(backend_docs_dir)
        
    # Uploads directory (data/uploads/{opportunity_id})
    uploads_dir = settings.UPLOADS_DIR / str(opportunity_id)
    if uploads_dir not in directories_to_delete:
        directories_to_delete.append(uploads_dir)
    
    # Debug extracts directory (data/debug_extracts/opportunity_{opportunity_id})
    debug_dir = settings.DEBUG_EXTRACTS_DIR / f"opportunity_{opportunity_id}"
    if debug_dir not in directories_to_delete:
        directories_to_delete.append(debug_dir)
    
    # Also check for any temp files in the data directory
    data_dir = settings.DATA_DIR
    temp_patterns = [
        str(data_dir / f"temp_opportunity_{opportunity_id}*"),
        str(data_dir / f"opportunity_{opportunity_id}_*"),
    ]
    
    # Delete all directories
    deleted_dirs = []
    failed_dirs = []
    total_size_deleted = 0
    
    for directory in directories_to_delete:
        try:
            if directory.exists() and directory.is_dir():
                # Calculate directory size before deletion
                dir_size = sum(f.stat().st_size for f in directory.rglob('*') if f.is_file())
                total_size_deleted += dir_size
                
                # Count files in directory
                file_count = sum(1 for f in directory.rglob('*') if f.is_file())
                
                shutil.rmtree(directory)
                deleted_dirs.append({
                    'path': str(directory),
                    'size': dir_size,
                    'files': file_count
                })
                logger.info(f"✅ Deleted directory: {directory} ({file_count} files, {dir_size} bytes)")
            else:
                logger.debug(f"Directory does not exist: {directory}")
        except Exception as e:
            failed_dirs.append((str(directory), str(e)))
            logger.warning(f"❌ Error deleting directory {directory}: {str(e)}")
            # Continue deleting other directories even if one fails
    
    # Try to find and delete any temp files matching patterns
    temp_files_deleted = []
    for pattern in temp_patterns:
        try:
            # Convert Path to string for glob
            pattern_str = str(pattern)
            matches = glob.glob(pattern_str)
            for match in matches:
                match_path = Path(match)
                if match_path.exists():
                    if match_path.is_file():
                        size = match_path.stat().st_size
                        match_path.unlink()
                        temp_files_deleted.append({'path': str(match_path), 'size': size, 'type': 'file'})
                        logger.info(f"✅ Deleted temp file: {match_path} ({size} bytes)")
                    elif match_path.is_dir():
                        dir_size = sum(f.stat().st_size for f in match_path.rglob('*') if f.is_file())
                        file_count = sum(1 for f in match_path.rglob('*') if f.is_file())
                        shutil.rmtree(match_path)
                        temp_files_deleted.append({'path': str(match_path), 'size': dir_size, 'type': 'directory', 'files': file_count})
                        logger.info(f"✅ Deleted temp directory: {match_path} ({file_count} files, {dir_size} bytes)")
        except Exception as e:
            logger.warning(f"Error processing temp pattern {pattern}: {str(e)}")
    
    # Summary of file/directory deletion
    logger.info(f"=" * 80)
    logger.info(f"FILE DELETION SUMMARY:")
    logger.info(f"  - Individual files deleted: {len(deleted_files)}")
    logger.info(f"  - Directories deleted: {len(deleted_dirs)}")
    if deleted_dirs:
        total_dir_files = sum(d.get('files', 0) for d in deleted_dirs)
        logger.info(f"  - Files in directories: {total_dir_files}")
    if temp_files_deleted:
        logger.info(f"  - Temp files/dirs deleted: {len(temp_files_deleted)}")
    if failed_files:
        logger.warning(f"  - Failed file deletions: {len(failed_files)}")
    if failed_dirs:
        logger.warning(f"  - Failed directory deletions: {len(failed_dirs)}")
    logger.info(f"=" * 80)
    
    # Delete the opportunity from database
    # Note: CASCADE will automatically delete all related database records:
    # - Documents (via ondelete="CASCADE" in Document.opportunity_id)
    # - CLINs (via ondelete="CASCADE" in CLIN.opportunity_id)
    # - Deadlines (via ondelete="CASCADE" in Deadline.opportunity_id)
    logger.info(f"Deleting database records...")
    db.delete(opportunity)
    db.commit()
    
    logger.info(f"=" * 80)
    logger.info(f"✅ SUCCESSFULLY DELETED OPPORTUNITY {opportunity_id}")
    logger.info(f"   - Database records: 1 opportunity, {len(documents)} documents, {len(clins)} CLINs, {len(deadlines)} deadlines")
    logger.info(f"   - Files deleted: {len(deleted_files)}")
    logger.info(f"   - Directories deleted: {len(deleted_dirs)}")
    if temp_files_deleted:
        logger.info(f"   - Temp files/dirs deleted: {len(temp_files_deleted)}")
    logger.info(f"=" * 80)
    return None


@router.get("/{opportunity_id}/documents/{document_id}/view")
async def view_document(
    opportunity_id: int,
    document_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """View/download a document from an opportunity"""
    # Verify opportunity belongs to user
    opportunity = db.query(Opportunity).filter(
        Opportunity.id == opportunity_id,
        Opportunity.user_id == current_user.id
    ).first()
    
    if not opportunity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Opportunity not found"
        )
    
    # Get document
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.opportunity_id == opportunity_id
    ).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    # If document has a public URL (S3), redirect to it
    if document.file_url:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=document.file_url)
    
    # For local files, serve the file
    file_path = Path(document.file_path)
    
    # Handle relative paths (from project root or data directory)
    if not file_path.is_absolute():
        from ..core.config import settings
        # Try relative to project root first
        project_root = Path(__file__).parent.parent.parent.parent
        file_path = project_root / file_path
        
        # If still doesn't exist, try relative to DATA_DIR (which is already relative to project root)
        if not file_path.exists():
            # Remove any leading slashes and normalize
            relative_path = document.file_path.lstrip('/').lstrip('\\')
            # Try with DATA_DIR
            file_path = settings.DATA_DIR / relative_path
    
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document file not found at path: {document.file_path}"
        )
    
    # Determine media type
    media_type = document.mime_type or "application/octet-stream"
    if document.file_type == "pdf":
        media_type = "application/pdf"
    elif document.file_type == "word":
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif document.file_type == "excel":
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    
    # Return file with appropriate filename
    return FileResponse(
        path=str(file_path),
        filename=document.original_file_name or document.file_name,
        media_type=media_type
    )
