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
from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..core.config import settings
from ..models.user import User
from ..models.opportunity import Opportunity
from ..models.document import Document, DocumentType, DocumentSource
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
    
    # Get all documents before deletion to delete files from disk
    documents = db.query(Document).filter(Document.opportunity_id == opportunity_id).all()
    
    # Delete individual files from disk
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
                file_path.unlink()
                logger.info(f"Deleted file: {file_path}")
            elif file_path.exists() and file_path.is_dir():
                # If it's a directory, remove it recursively
                shutil.rmtree(file_path)
                logger.info(f"Deleted directory: {file_path}")
        except Exception as e:
            logger.warning(f"Error deleting file {doc.file_path}: {str(e)}")
            # Continue deleting other files even if one fails
    
    # Delete opportunity directories (documents and uploads) - this will catch any remaining files
    try:
        # Delete documents directory
        documents_dir = settings.DOCUMENTS_DIR / str(opportunity_id)
        if documents_dir.exists() and documents_dir.is_dir():
            shutil.rmtree(documents_dir)
            logger.info(f"Deleted documents directory: {documents_dir}")
        
        # Delete uploads directory
        uploads_dir = settings.UPLOADS_DIR / str(opportunity_id)
        if uploads_dir.exists() and uploads_dir.is_dir():
            shutil.rmtree(uploads_dir)
            logger.info(f"Deleted uploads directory: {uploads_dir}")
    except Exception as e:
        logger.warning(f"Error deleting opportunity directories: {str(e)}")
    
    # Delete the opportunity (CASCADE will delete related database records)
    db.delete(opportunity)
    db.commit()
    
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
