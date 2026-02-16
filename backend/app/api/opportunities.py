"""
Opportunities API endpoints
"""
import re
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Body
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional
from pathlib import Path
import json
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
from ..models.user_email_connection import UserEmailConnection
from ..models.draft_quote_email import DraftQuoteEmail
from ..schemas.opportunity import OpportunityCreate, OpportunityResponse, OpportunityDetailResponse, OpportunityList
from ..schemas.document import DocumentResponse
from ..schemas.draft_quote_email import DraftQuoteEmailList, DraftQuoteEmailResponse
from sqlalchemy.orm import joinedload
from ..services.tasks import scrape_sam_gov_opportunity, log_document_update
from ..services.lookup_links import get_clin_lookup_links
from ..services.calendar_sync import sync_deadlines_to_calendar, delete_calendar_events_for_deadlines
from ..services.quote_email_drafts import generate_drafts_for_opportunity
from ..services.form_filler_service import (
    build_opportunity_form_data,
    fill_pdf_form,
    get_form_fields_for_pdf,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


def _delivery_timeline_string_from_clins(opportunity) -> Optional[str]:
    """Build a single delivery-timeline string from opportunity CLINs for calendar event descriptions."""
    if not getattr(opportunity, "clins", None):
        return None
    parts = []
    seen = set()
    for c in opportunity.clins:
        add = getattr(c, "additional_data", None) or {}
        timeline = add.get("delivery_timeline") or getattr(c, "timeline", None)
        if timeline and isinstance(timeline, str) and timeline.strip():
            t = timeline.strip()
            if t not in seen:
                seen.add(t)
                parts.append(t)
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    return " | ".join(parts) if len(parts) == 2 else "\n".join(parts)


def _aggregate_delivery_requirements_from_clins(opportunity) -> Optional[dict]:
    """Build delivery_requirements dict from CLIN additional_data and timeline for the opportunity detail response.
    Frontend expects delivery_address (with street_address or full text), special_instructions (list), delivery_timeline.
    """
    if not opportunity.clins:
        return None
    delivery_address_texts = []
    special_instructions = []
    delivery_timelines = []
    for c in opportunity.clins:
        add = c.additional_data or {}
        addr = add.get("delivery_address")
        if addr and isinstance(addr, str) and addr.strip():
            delivery_address_texts.append(addr.strip())
        spec = add.get("special_delivery_instructions")
        if spec and isinstance(spec, str) and spec.strip():
            special_instructions.append(spec.strip())
        timeline = add.get("delivery_timeline") or getattr(c, "timeline", None)
        if timeline and isinstance(timeline, str) and timeline.strip():
            delivery_timelines.append(timeline.strip())
    if not delivery_address_texts and not special_instructions and not delivery_timelines:
        return None
    out = {}
    if delivery_address_texts:
        # Use first address as primary; UI can show street_address as full text when no parsed parts
        out["delivery_address"] = {"street_address": delivery_address_texts[0]}
        if len(delivery_address_texts) > 1:
            out["delivery_address"]["additional_addresses"] = delivery_address_texts[1:]
    if special_instructions:
        out["special_instructions"] = special_instructions
    if delivery_timelines:
        out["delivery_timeline"] = delivery_timelines[0] if len(delivery_timelines) == 1 else " | ".join(delivery_timelines)
    return out if out else None


@router.post("", response_model=OpportunityResponse, status_code=status.HTTP_201_CREATED)
async def create_opportunity(
    sam_gov_url: str = Form(..., description="SAM.gov opportunity URL"),
    files: Optional[List[UploadFile]] = File(None, description="Optional additional documents"),
    enable_document_analysis: Optional[str] = Form("false", description="Enable document analysis (true/false)"),
    enable_clin_extraction: Optional[str] = Form("false", description="Enable CLIN extraction (true/false)"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Create a new opportunity from SAM.gov URL with optional file uploads.
    Same URL can exist for different users (no cross-account conflict). If this user already has this URL,
    returns the existing opportunity (200) so the client can open it.
    """
    # Normalize URL for comparison (strip trailing slash and whitespace)
    url_normalized = (sam_gov_url or "").strip().rstrip("/")
    if not url_normalized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SAM.gov URL is required"
        )

    # Only check for this user: same URL for another user is allowed (per-user opportunity)
    existing = db.query(Opportunity).filter(
        Opportunity.user_id == current_user.id,
        Opportunity.sam_gov_url.in_([url_normalized, url_normalized + "/"])
    ).first()

    if existing:
        # Same user re-submitted: return existing opportunity so frontend can navigate to it
        logger.info("Opportunity already exists for user %s, returning existing id=%s", current_user.id, existing.id)
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=OpportunityResponse.model_validate(existing).model_dump(mode="json")
        )

    # Create new opportunity (store normalized URL for consistent duplicate detection)
    new_opportunity = Opportunity(
        user_id=current_user.id,
        sam_gov_url=url_normalized,
        status="pending",
        enable_document_analysis=enable_document_analysis.lower() if enable_document_analysis else "false",
        enable_clin_extraction=enable_clin_extraction.lower() if enable_clin_extraction else "false"
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
    getattr(scrape_sam_gov_opportunity, "delay")(new_opportunity.id)
    
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


def _normalize_clin_for_response(clin):
    """Ensure manufacturer_research and dealer_research are lists for API (DB may return JSON string or object)."""
    mfr = getattr(clin, "manufacturer_research", None)
    if isinstance(mfr, str):
        try:
            mfr = json.loads(mfr) if mfr.strip() else None
        except Exception:
            mfr = None
    if mfr is not None and not isinstance(mfr, dict) and not isinstance(mfr, list):
        mfr = None
    # Always return manufacturer_research as a list for frontend (legacy single dict -> [dict])
    if isinstance(mfr, dict):
        mfr = [mfr]
    if mfr is None:
        mfr = []
    dr = getattr(clin, "dealer_research", None)
    if isinstance(dr, str):
        try:
            dr = json.loads(dr) if dr.strip() else []
        except Exception:
            dr = []
    if dr is not None and not isinstance(dr, list):
        dr = []
    return {
        "manufacturer_research": mfr,
        "dealer_research": dr or [],
    }


@router.get("/{opportunity_id}", response_model=OpportunityDetailResponse)
async def get_opportunity(
    opportunity_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get a specific opportunity by ID with documents, deadlines, and CLINs (including Tavily dealer/manufacturer research)."""
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
    # Ensure CLINs include Tavily research (manufacturer_research, dealer_research) as dict/list for frontend
    from ..schemas.clin import CLINResponse
    clins_out = []
    for c in opportunity.clins:
        extra = _normalize_clin_for_response(c)
        clins_out.append(CLINResponse(
            id=c.id,
            clin_number=c.clin_number,
            clin_name=c.clin_name,
            base_item_number=c.base_item_number,
            product_name=c.product_name,
            product_description=c.product_description,
            manufacturer_name=c.manufacturer_name,
            part_number=c.part_number,
            model_number=getattr(c, "model_number", None),
            quantity=c.quantity,
            unit_of_measure=c.unit_of_measure,
            contract_type=getattr(c, "contract_type", None),
            extended_price=getattr(c, "extended_price", None),
            service_description=c.service_description,
            scope_of_work=c.scope_of_work,
            timeline=c.timeline,
            service_requirements=c.service_requirements,
            additional_data=c.additional_data,
            manufacturer_research=extra["manufacturer_research"],
            dealer_research=extra["dealer_research"],
            created_at=c.created_at,
            updated_at=c.updated_at,
        ))
    resp = OpportunityDetailResponse.model_validate(opportunity)
    resp.clins = clins_out
    # Populate delivery_requirements from CLINs when not set (aggregate from CLIN additional_data)
    dr = _aggregate_delivery_requirements_from_clins(opportunity)
    if dr:
        base_codes = dict(resp.classification_codes or {})
        base_codes["delivery_requirements"] = dr
        resp.classification_codes = base_codes
    return resp


@router.post("/{opportunity_id}/sync-calendar")
async def sync_opportunity_calendar(
    opportunity_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Create calendar events for all opportunity deadlines in the user's connected calendar (Google or Outlook). Events are persisted so they are not duplicated. Includes delivery timeline from CLINs in event description when available."""
    opportunity = db.query(Opportunity).options(
        joinedload(Opportunity.deadlines),
        joinedload(Opportunity.clins),
    ).filter(
        Opportunity.id == opportunity_id,
        Opportunity.user_id == current_user.id,
    ).first()
    if not opportunity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")
    conn = db.query(UserEmailConnection).filter(UserEmailConnection.user_id == current_user.id).first()
    if not conn:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Connect your email/calendar (Gmail or Outlook) first to add deadlines to your calendar.",
        )
    deadlines = [d for d in opportunity.deadlines]
    if not deadlines:
        return {"created": 0, "message": "No deadlines to sync."}
    opportunity_title = getattr(opportunity, "title", None)
    delivery_timeline = _delivery_timeline_string_from_clins(opportunity)
    try:
        created = sync_deadlines_to_calendar(
            conn,
            deadlines,
            opportunity_title=opportunity_title,
            delivery_timeline=delivery_timeline,
        )
        db.commit()
        logger.info("Add to calendar: opportunity_id=%s created=%s total_deadlines=%s", opportunity_id, created, len(deadlines))
        return {"created": created, "total_deadlines": len(deadlines)}
    except Exception as e:
        logger.exception("Add to calendar failed: opportunity_id=%s error=%s", opportunity_id, e)
        err_str = str(e).lower() if e else ""
        detail = "Calendar sync failed. "
        if "RefreshError" in type(e).__name__ or "refresh" in err_str:
            detail += "Your calendar connection needs to be refreshed. Please disconnect and reconnect your Google account in Settings."
        elif "credentials" in err_str:
            detail += "Please disconnect and reconnect your email/calendar account in Settings."
        elif any(x in err_str for x in ("unable to find the server", "getaddrinfo failed", "name or service not known", "timed out", "timeout", "connection", "network is unreachable", "nodename nor servname")):
            detail += "This often happens with slow or unstable internet. Please check your connection and try again in a moment."
        else:
            detail += err_str if err_str else "Please try again or reconnect your email/calendar in Settings."
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


# ----- Quote email drafts (persisted in DB; generate saves, send/discard delete) -----


@router.get("/{opportunity_id}/quote-email-drafts", response_model=DraftQuoteEmailList)
async def list_quote_email_drafts(
    opportunity_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """List draft quote emails for this opportunity (from DB). View does not generate."""
    opportunity = db.query(Opportunity).filter(
        Opportunity.id == opportunity_id,
        Opportunity.user_id == current_user.id,
    ).first()
    if not opportunity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")
    drafts = db.query(DraftQuoteEmail).filter(DraftQuoteEmail.opportunity_id == opportunity_id).order_by(DraftQuoteEmail.id).all()
    return DraftQuoteEmailList(drafts=[DraftQuoteEmailResponse.model_validate(d) for d in drafts])


@router.post("/{opportunity_id}/quote-email-drafts/generate", response_model=DraftQuoteEmailList)
async def generate_quote_email_drafts(
    opportunity_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Generate draft quote emails from CLINs (manufacturers/dealers with contact emails) and save to DB. Replaces existing drafts."""
    opportunity = db.query(Opportunity).options(joinedload(Opportunity.clins)).filter(
        Opportunity.id == opportunity_id,
        Opportunity.user_id == current_user.id,
    ).first()
    if not opportunity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")
    generate_drafts_for_opportunity(db, opportunity_id, opportunity=opportunity)
    drafts = db.query(DraftQuoteEmail).filter(DraftQuoteEmail.opportunity_id == opportunity_id).order_by(DraftQuoteEmail.id).all()
    return DraftQuoteEmailList(drafts=[DraftQuoteEmailResponse.model_validate(d) for d in drafts])


@router.delete("/{opportunity_id}/quote-email-drafts/{draft_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_quote_email_draft(
    opportunity_id: int,
    draft_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Delete one draft (after send or discard)."""
    opportunity = db.query(Opportunity).filter(
        Opportunity.id == opportunity_id,
        Opportunity.user_id == current_user.id,
    ).first()
    if not opportunity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")
    draft = db.query(DraftQuoteEmail).filter(
        DraftQuoteEmail.id == draft_id,
        DraftQuoteEmail.opportunity_id == opportunity_id,
    ).first()
    if not draft:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")
    db.delete(draft)
    db.commit()
    return None


@router.patch("/{opportunity_id}/quote-email-drafts/{draft_id}", response_model=DraftQuoteEmailResponse)
async def update_quote_email_draft(
    opportunity_id: int,
    draft_id: int,
    body: dict = Body(...),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Update draft to, to_name, subject, body (when user edits)."""
    opportunity = db.query(Opportunity).filter(
        Opportunity.id == opportunity_id,
        Opportunity.user_id == current_user.id,
    ).first()
    if not opportunity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")
    draft = db.query(DraftQuoteEmail).filter(
        DraftQuoteEmail.id == draft_id,
        DraftQuoteEmail.opportunity_id == opportunity_id,
    ).first()
    if not draft:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")
    for key in ("to", "to_name", "subject", "body"):
        if key in body and body[key] is not None:
            setattr(draft, key, body[key] if key != "body" else str(body[key]))
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return DraftQuoteEmailResponse.model_validate(draft)


def _is_valid_email(s: Optional[str]) -> bool:
    """Return True if s looks like a valid email (no URLs/obfuscation)."""
    if not s or not isinstance(s, str):
        return False
    s = s.strip()
    if len(s) < 6 or len(s) > 254 or " " in s or "@" not in s:
        return False
    if "/cdn-cgi/" in s or s.startswith("/") or "http" in s.lower() or "mailto:" in s.lower():
        return False
    if not re.match(r"^[^@]+@[^@]+\.[^@]+$", s):
        return False
    return True


class UpdateDealerEmailBody(BaseModel):
    dealer_index: int
    sales_contact_email: str


@router.patch("/{opportunity_id}/clins/{clin_id}/dealer-email", status_code=status.HTTP_200_OK)
async def update_dealer_email(
    opportunity_id: int,
    clin_id: int,
    body: UpdateDealerEmailBody = Body(...),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Update a dealer's sales_contact_email for a CLIN. User can add an email they found themselves; persisted to DB."""
    opportunity = db.query(Opportunity).filter(
        Opportunity.id == opportunity_id,
        Opportunity.user_id == current_user.id
    ).first()
    if not opportunity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")
    clin = db.query(CLIN).filter(
        CLIN.id == clin_id,
        CLIN.opportunity_id == opportunity_id
    ).first()
    if not clin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CLIN not found")
    email = (body.sales_contact_email or "").strip()
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="sales_contact_email is required")
    if not _is_valid_email(email):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid email format")
    dealers = clin.dealer_research
    if isinstance(dealers, str):
        try:
            dealers = json.loads(dealers) if dealers.strip() else []
        except Exception:
            dealers = []
    if not isinstance(dealers, list):
        dealers = []
    idx = body.dealer_index
    if idx < 0 or idx >= len(dealers):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid dealer_index")
    item = dealers[idx]
    if not isinstance(item, dict):
        item = {}
    dealers = list(dealers)
    dealers[idx] = {**item, "sales_contact_email": email}
    setattr(clin, "dealer_research", dealers)
    db.add(clin)
    db.commit()
    db.refresh(clin)
    return {"ok": True, "dealer_index": idx, "sales_contact_email": email}


@router.delete("/{opportunity_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_opportunity(
    opportunity_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Delete an opportunity and all related data: removes synced calendar events from user's Google/Outlook, deletes all document files and opportunity directories from disk, then deletes the opportunity and related DB records (documents, deadlines, CLINs) via CASCADE."""
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

    # Remove calendar events from user's Google/Outlook calendar (if any were synced)
    conn = db.query(UserEmailConnection).filter(UserEmailConnection.user_id == current_user.id).first()
    if conn and any(d.calendar_event_id for d in deadlines):
        try:
            removed = delete_calendar_events_for_deadlines(conn, deadlines)
            logger.info(f"Removed {removed} calendar event(s) from user calendar")
        except Exception as e:
            logger.warning("Calendar event removal failed (continuing with delete): %s", e)
    
    # Delete individual files from disk
    deleted_files = []
    failed_files = []
    for doc in documents:
        try:
            # Resolve file path
            file_path = Path(str(doc.file_path))
            
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


def _parse_positive_int(value: str, name: str) -> int:
    """Coerce path param to positive int; raise HTTP 400 with clear message if invalid."""
    try:
        n = int(float(value))
        if n < 1:
            raise ValueError(f"{name} must be a positive integer")
        return n
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {name}; must be a positive integer",
        )


@router.get("/{opportunity_id}/documents/{document_id}/view")
async def view_document(
    opportunity_id: str,
    document_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """View/download a document from an opportunity"""
    oid = _parse_positive_int(opportunity_id, "opportunity_id")
    did = _parse_positive_int(document_id, "document_id")
    # Verify opportunity belongs to user
    opportunity = db.query(Opportunity).filter(
        Opportunity.id == oid,
        Opportunity.user_id == current_user.id
    ).first()
    
    if not opportunity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Opportunity not found"
        )
    
    # Get document
    document = db.query(Document).filter(
        Document.id == did,
        Document.opportunity_id == oid
    ).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    # If document has a public URL (S3), redirect to it
    file_url = getattr(document, "file_url", None)
    if file_url:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=str(file_url))
    
    # For local files, serve the file (same path resolution as overwrite_document)
    doc_file_path_str = str(getattr(document, "file_path", "") or "")
    file_path = _resolve_document_file_path(document, doc_file_path_str, oid)
    logger.info("view_document: opp_id=%s doc_id=%s db_path=%r resolved=%s exists=%s", oid, did, doc_file_path_str, file_path, file_path.exists() and file_path.is_file())
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document file not found at path: {doc_file_path_str}"
        )

    # Determine media type (use plain str for type checker)
    doc_mime = getattr(document, "mime_type", None)
    doc_ftype = getattr(document, "file_type", None)
    media_type = str(doc_mime) if doc_mime else "application/octet-stream"
    if doc_ftype == "pdf":
        media_type = "application/pdf"
    elif doc_ftype == "word":
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif doc_ftype == "excel":
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    doc_name = getattr(document, "original_file_name", None) or getattr(document, "file_name", None) or ""
    return FileResponse(
        path=str(file_path),
        filename=str(doc_name),
        media_type=media_type,
        headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"},
    )


@router.get("/{opportunity_id}/form-data")
async def get_opportunity_form_data(
    opportunity_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Get flat key-value form data for this opportunity (for prefill in editor)."""
    oid = _parse_positive_int(opportunity_id, "opportunity_id")
    opportunity = db.query(Opportunity).filter(
        Opportunity.id == oid,
        Opportunity.user_id == current_user.id,
    ).first()
    if not opportunity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")
    deadlines = db.query(Deadline).filter(Deadline.opportunity_id == oid).order_by(Deadline.due_date).all()
    data = build_opportunity_form_data(opportunity, deadlines=deadlines)
    return data


class FormFieldsResponse(BaseModel):
    """Response for GET form-fields."""
    fields: List[dict]
    source: str  # docai_form_parser | acroform | ocr | none


class FillFormBody(BaseModel):
    """Body for POST fill-form."""
    fields: Optional[dict] = None  # { "contractor_name": "Acme", ... }
    use_opportunity_data: Optional[bool] = False  # if True, fill from opportunity + deadlines
    save_as_new: Optional[bool] = False  # if True, create new document; else overwrite


@router.get("/{opportunity_id}/documents/{document_id}/form-fields", response_model=FormFieldsResponse)
async def get_document_form_fields(
    opportunity_id: str,
    document_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Get form field names and metadata for a PDF document (for editor or autofill)."""
    oid = _parse_positive_int(opportunity_id, "opportunity_id")
    did = _parse_positive_int(document_id, "document_id")
    logger.info(
        "form_fields_request opportunity_id=%s document_id=%s user_id=%s",
        oid, did, current_user.id,
    )
    opportunity = db.query(Opportunity).filter(
        Opportunity.id == oid,
        Opportunity.user_id == current_user.id,
    ).first()
    if not opportunity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")
    document = db.query(Document).filter(
        Document.id == did,
        Document.opportunity_id == oid,
    ).first()
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    if str(getattr(document, "file_type", "")).lower() not in ("pdf", "documenttype.pdf"):
        return FormFieldsResponse(fields=[], source="none")
    doc_file_path_str = str(getattr(document, "file_path", "") or "")
    if not doc_file_path_str:
        return FormFieldsResponse(fields=[], source="none")
    file_path = _resolve_document_file_path(document, doc_file_path_str, oid)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document file not found")
    try:
        fields_dict, source = get_form_fields_for_pdf(str(file_path))
        fields_list = []
        for name, info in fields_dict.items():
            fields_list.append({
                "name": name,
                "type": info.get("type", "text"),
                "value": info.get("value"),
                "mapping_key": info.get("mapping_key"),
            })
        logger.info(
            "form_fields_success opportunity_id=%s document_id=%s field_count=%s source=%s",
            oid, did, len(fields_list), source,
        )
        return FormFieldsResponse(fields=fields_list, source=source)
    except Exception as e:
        logger.exception("get_form_fields failed: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to extract form fields")


@router.post("/{opportunity_id}/documents/{document_id}/fill-form")
async def fill_document_form(
    opportunity_id: str,
    document_id: str,
    body: FillFormBody = Body(...),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Fill PDF form with provided fields or opportunity data; overwrite document or save as new."""
    oid = _parse_positive_int(opportunity_id, "opportunity_id")
    did = _parse_positive_int(document_id, "document_id")
    logger.info(
        "fill_form_request opportunity_id=%s document_id=%s user_id=%s use_opportunity_data=%s save_as_new=%s",
        oid, did, current_user.id, body.use_opportunity_data, body.save_as_new,
    )
    opportunity = db.query(Opportunity).filter(
        Opportunity.id == oid,
        Opportunity.user_id == current_user.id,
    ).first()
    if not opportunity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")
    document = db.query(Document).filter(
        Document.id == did,
        Document.opportunity_id == oid,
    ).first()
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    if getattr(document, "file_url", None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot fill form on document stored externally (S3)",
        )
    doc_file_path_str = str(getattr(document, "file_path", "") or "")
    if not doc_file_path_str:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Document has no file path")
    file_path = _resolve_document_file_path(document, doc_file_path_str, oid)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document file not found")
    if str(getattr(document, "file_type", "")).lower() not in ("pdf", "documenttype.pdf"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only PDF documents can be filled")

    if body.use_opportunity_data:
        deadlines = db.query(Deadline).filter(Deadline.opportunity_id == oid).order_by(Deadline.due_date).all()
        data = build_opportunity_form_data(opportunity, deadlines=deadlines)
    else:
        data = body.fields or {}
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No field data provided")

    import tempfile
    result_path = None
    if body.save_as_new:
        out_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        out_path = out_file.name
        out_file.close()
    else:
        out_path = str(file_path)

    try:
        result_path = fill_pdf_form(str(file_path), data, output_path=out_path)
        if not result_path:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Form fill failed (no AcroForm or fillable regions)")
        if body.save_as_new:
            base_name = getattr(document, "original_file_name", None) or getattr(document, "file_name", None) or "document"
            safe = re.sub(r"[^\w\-\.]", "_", base_name)
            new_name = f"Filled_{safe}" if not safe.lower().startswith("filled_") else safe
            new_path = file_path.parent / new_name
            Path(result_path).rename(new_path)
            result_path = None
            rel_path = str(new_path.relative_to(settings.PROJECT_ROOT)) if settings.PROJECT_ROOT in new_path.parents else str(new_path)
            new_doc = Document(
                opportunity_id=oid,
                file_name=new_name,
                original_file_name=new_name,
                file_path=rel_path,
                file_size=new_path.stat().st_size,
                file_type=DocumentType.PDF,
                mime_type="application/pdf",
                source=DocumentSource.FORM_FILLED,
                storage_type="local",
            )
            db.add(new_doc)
            db.commit()
            db.refresh(new_doc)
            logger.info(
                "fill_form_success opportunity_id=%s document_id=%s save_as_new=True new_document_id=%s",
                oid, did, new_doc.id,
            )
            try:
                log_document_update.delay(  # type: ignore[union-attr]
                    action="form_fill",
                    opportunity_id=oid,
                    document_id=did,
                    user_id=current_user.id,
                    save_as_new=True,
                    new_document_id=new_doc.id,
                )
            except Exception:
                pass
            return DocumentResponse.model_validate(new_doc)
        db.commit()
        db.refresh(document)
        logger.info(
            "fill_form_success opportunity_id=%s document_id=%s save_as_new=False",
            oid, did,
        )
        try:
            log_document_update.delay(  # type: ignore[union-attr]
                action="form_fill",
                opportunity_id=oid,
                document_id=did,
                user_id=current_user.id,
                save_as_new=False,
            )
        except Exception:
            pass
        return DocumentResponse.model_validate(document)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("fill_form failed: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Form fill failed")
    finally:
        if result_path and Path(result_path).exists():
            try:
                Path(result_path).unlink(missing_ok=True)
            except Exception:
                pass


def _resolve_document_file_path(document, doc_file_path_str: str, opportunity_id: int) -> Path:
    """Resolve document file_path to absolute Path. Used by view_document and overwrite_document so they serve/write the same file."""
    file_path = Path(doc_file_path_str)
    if file_path.is_absolute():
        return file_path
    doc_name = getattr(document, "file_name", None) or file_path.name
    candidates = [
        settings.PROJECT_ROOT / file_path,
        Path.cwd() / file_path,
    ]
    if hasattr(settings, "STORAGE_BASE_PATH"):
        storage_base = Path(settings.STORAGE_BASE_PATH)
        if not storage_base.is_absolute():
            storage_base = settings.PROJECT_ROOT / storage_base
        candidates.append(storage_base / str(opportunity_id) / doc_name)
        candidates.append(storage_base / file_path)
    relative_path = doc_file_path_str.lstrip("/").lstrip("\\")
    candidates.append(settings.DATA_DIR / relative_path)
    if hasattr(settings, "DOCUMENTS_DIR"):
        candidates.append(settings.DOCUMENTS_DIR / str(opportunity_id) / doc_name)
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return candidates[0]


@router.put("/{opportunity_id}/documents/{document_id}")
async def overwrite_document(
    opportunity_id: str,
    document_id: str,
    file: Optional[UploadFile] = File(None, description="Replacement file (PDF or Word). Overwrites existing document."),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Overwrite an existing opportunity document with new file content (e.g. after in-app edit). Saves to same path in data."""
    oid = _parse_positive_int(opportunity_id, "opportunity_id")
    did = _parse_positive_int(document_id, "document_id")
    if not file or not getattr(file, "filename", None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Replacement file is required. Upload a PDF or Word file.",
        )
    opportunity = db.query(Opportunity).filter(
        Opportunity.id == oid,
        Opportunity.user_id == current_user.id
    ).first()
    if not opportunity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")
    document = db.query(Document).filter(
        Document.id == did,
        Document.opportunity_id == oid
    ).first()
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    if getattr(document, "file_url", None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot overwrite document stored externally (S3)"
        )
    doc_file_path_str = str(getattr(document, "file_path", "") or "")
    if not doc_file_path_str:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Document has no file path")
    file_path = _resolve_document_file_path(document, doc_file_path_str, oid)
    logger.info("overwrite_document: opp_id=%s doc_id=%s db_path=%r resolved=%s exists=%s", oid, did, doc_file_path_str, file_path, file_path.exists())
    # If file doesn't exist yet (e.g. path from scraping but never downloaded), create parent dirs and write
    if not file_path.exists():
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.error(f"Error creating parent dir for overwrite: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Could not create document directory",
            ) from e
    elif not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Document path exists but is not a file: {doc_file_path_str}",
        )
    # Allow PDF or Word replacement; optionally keep same type
    filename = file.filename or ""
    ext = Path(filename).suffix.lower()
    if ext not in (".pdf", ".doc", ".docx"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Replacement file must be PDF or Word (.pdf, .doc, .docx)"
        )
    try:
        content = await file.read()
    except Exception as e:
        logger.error(f"Error reading upload for overwrite: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to read uploaded file")
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty. Save the PDF again.",
        )
    try:
        file_path.write_bytes(content)
    except Exception as e:
        logger.error(f"Error writing document overwrite: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save file")
    file_size = len(content)
    mime_type, _ = mimetypes.guess_type(filename)
    if ext == ".pdf":
        doc_type = DocumentType.PDF
        if not mime_type:
            mime_type = "application/pdf"
    elif ext in (".doc", ".docx"):
        doc_type = DocumentType.WORD
        if not mime_type:
            mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    else:
        doc_type = getattr(document, "file_type", DocumentType.OTHER)
    document.file_size = file_size  # type: ignore[assignment]
    document.mime_type = mime_type or "application/octet-stream"  # type: ignore[assignment]
    document.file_type = doc_type  # type: ignore[assignment]
    db.commit()
    db.refresh(document)
    logger.info(
        "document_edit_success opportunity_id=%s document_id=%s user_id=%s file=%s size=%s",
        oid, did, current_user.id, filename, file_size,
    )
    try:
        log_document_update.delay(  # type: ignore[union-attr]
            action="document_edit",
            opportunity_id=oid,
            document_id=did,
            user_id=current_user.id,
            extra={"filename": filename, "file_size": file_size},
        )
    except Exception:
        pass
    return DocumentResponse.model_validate(document)


@router.get("/{opportunity_id}/clins/{clin_id}/lookup-links")
async def get_clin_lookup_links_endpoint(
    opportunity_id: int,
    clin_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get external lookup URLs for a CLIN (NSN Lookup, CAGE, Digi-Key, SAM.gov). Links open in browser."""
    opportunity = db.query(Opportunity).filter(
        Opportunity.id == opportunity_id,
        Opportunity.user_id == current_user.id
    ).first()
    if not opportunity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")
    clin = db.query(CLIN).filter(
        CLIN.id == clin_id,
        CLIN.opportunity_id == opportunity_id
    ).first()
    if not clin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CLIN not found")
    clin_dict = {
        "part_number": clin.part_number,
        "base_item_number": clin.base_item_number,
        "manufacturer_name": clin.manufacturer_name,
        "product_name": clin.product_name,
        "product_description": clin.product_description,
        "additional_data": clin.additional_data,
    }
    links = get_clin_lookup_links(clin_dict)
    return {"links": links}
