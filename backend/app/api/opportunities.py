"""
Opportunities API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List
from pathlib import Path
import os
from ..core.database import get_db
from ..core.dependencies import get_current_active_user
from ..models.user import User
from ..models.opportunity import Opportunity
from ..models.document import Document
from ..schemas.opportunity import OpportunityCreate, OpportunityResponse, OpportunityDetailResponse, OpportunityList
from sqlalchemy.orm import joinedload
from ..services.tasks import scrape_sam_gov_opportunity

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


@router.post("", response_model=OpportunityResponse, status_code=status.HTTP_201_CREATED)
async def create_opportunity(
    opportunity_data: OpportunityCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Create a new opportunity from SAM.gov URL"""
    # Check if opportunity already exists
    existing = db.query(Opportunity).filter(
        Opportunity.sam_gov_url == str(opportunity_data.sam_gov_url)
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Opportunity with this URL already exists"
        )
    
    # Create new opportunity
    new_opportunity = Opportunity(
        user_id=current_user.id,
        sam_gov_url=str(opportunity_data.sam_gov_url),
        status="pending"
    )
    
    db.add(new_opportunity)
    db.commit()
    db.refresh(new_opportunity)
    
    # Trigger background task to scrape SAM.gov and analyze documents
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
    """Get a specific opportunity by ID with documents and deadlines"""
    opportunity = db.query(Opportunity).options(
        joinedload(Opportunity.documents),
        joinedload(Opportunity.deadlines)
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
    """Delete an opportunity and all related data (documents, deadlines, CLINs)"""
    opportunity = db.query(Opportunity).filter(
        Opportunity.id == opportunity_id,
        Opportunity.user_id == current_user.id
    ).first()
    
    if not opportunity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Opportunity not found"
        )
    
    # Delete opportunity (cascade will handle related records)
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
