"""
Opportunities API endpoints
"""
import re
import time
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Body
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
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
from ..models.contractor_profile import ContractorProfile
from ..models.document import Document, DocumentType, DocumentSource
from ..models.clin import CLIN
from ..models.deadline import Deadline
from ..models.user_email_connection import UserEmailConnection
from ..models.draft_quote_email import DraftQuoteEmail
from ..schemas.opportunity import OpportunityResponse, OpportunityDetailResponse, OpportunityList
from ..schemas.document import DocumentResponse
from ..schemas.draft_quote_email import DraftQuoteEmailList, DraftQuoteEmailResponse
from sqlalchemy.orm import joinedload
from ..services.word_to_pdf import convert_word_to_pdf
from ..services.tasks import (
    scrape_sam_gov_opportunity,
    analyze_documents,
    run_tavily_dealers_for_opportunity,
    rerun_clins_only,
)
from ..services.lookup_links import get_clin_lookup_links
from ..services.calendar_sync import sync_deadlines_to_calendar, delete_calendar_events_for_deadlines
from ..services.quote_email_drafts import generate_drafts_for_opportunity
from ..services.form_autofill import get_autofill_values
from ..services.pdf_form_filler import introspect_pdf_fields
from ..services.clin_extractor import CLINExtractor
from ..services.object_storage import (
    s3_enabled,
    upload_file,
    make_object_key,
    presigned_get_url,
    delete_s3_uri,
    parse_s3_uri,
    get_s3_object_body,
)

logger = logging.getLogger(__name__)

# Reuse for autofill LLM (lazy init); primary and fallback (e.g. Claude then Groq)
_autofill_extractor = None


def _maybe_upload_to_s3(opportunity_id: int, category: str, file_path: Path, mime_type: Optional[str]) -> tuple[str, Optional[str]]:
    """Upload local file to S3-compatible storage when enabled."""
    if not s3_enabled():
        return "local", None
    try:
        key = make_object_key(opportunity_id, category, file_path.name)
        s3_uri = upload_file(file_path, key, content_type=mime_type)
        return "s3", s3_uri
    except Exception as exc:
        logger.warning("S3 upload failed for %s: %s; falling back to local storage", file_path, exc)
        return "local", None

def _get_autofill_llms():
    """Return (primary_llm, fallback_llm) for form autofill; try primary first, then fallback if it fails."""
    global _autofill_extractor
    if _autofill_extractor is None:
        _autofill_extractor = CLINExtractor()
    ext = _autofill_extractor
    primary = ext.llm or ext.fallback_llm
    fallback = ext.fallback_llm if ext.llm else None
    return (primary, fallback)


class AutofillPreviewRequest(BaseModel):
    """Request body for autofill preview: list of PDF form field names and optional types/values."""
    field_names: List[str]
    field_types: Optional[dict] = None  # field_name -> "checkbox" | "text"
    field_values: Optional[dict] = None  # field_name -> current value (from introspect); gov fields filled only if empty
    field_tooltips: Optional[dict] = None  # field_name -> tooltip (helps LLM when mapping)

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
                    elif file_ext in ['.txt', '.text']:
                        doc_type = DocumentType.TEXT
                    else:
                        doc_type = DocumentType.OTHER
                    
                    # Sanitize filename
                    safe_filename = file.filename.replace('/', '_').replace('\\', '_')
                    file_path = upload_dir / safe_filename
                    
                    # Save file
                    with open(file_path, "wb") as buffer:
                        shutil.copyfileobj(file.file, buffer)
                    
                    mime_type = None
                    # Auto-convert Word to PDF for viewing/editing in the PDF editor
                    if file_ext in ('.doc', '.docx'):
                        pdf_path = convert_word_to_pdf(file_path.resolve(), delete_original=True)
                        if pdf_path:
                            file_path = pdf_path
                            safe_filename = pdf_path.name
                            doc_type = DocumentType.PDF
                            mime_type = "application/pdf"
                    
                    file_size = file_path.stat().st_size
                    if mime_type is None:
                        mime_type, _ = mimetypes.guess_type(file.filename)
                    
                    storage_type, file_url = _maybe_upload_to_s3(
                        new_opportunity.id,
                        "uploads",
                        file_path,
                        mime_type or "application/octet-stream",
                    )
                    # Create document record
                    doc = Document(
                        opportunity_id=new_opportunity.id,
                        file_name=safe_filename,
                        original_file_name=file.filename,
                        file_path=str(file_path.resolve().relative_to(settings.PROJECT_ROOT.resolve())),
                        file_size=file_size,
                        file_type=doc_type,
                        mime_type=mime_type or "application/octet-stream",
                        source=DocumentSource.USER_UPLOAD,
                        storage_type=storage_type,
                        file_url=file_url,
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
    """List all opportunities for current user (newest first)."""
    opportunities = (
        db.query(Opportunity)
        .filter(Opportunity.user_id == current_user.id)
        .order_by(Opportunity.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    total = db.query(Opportunity).filter(Opportunity.user_id == current_user.id).count()
    
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
        # Normalize single-object legacy format to list (like manufacturer_research)
        dr = [dr] if isinstance(dr, dict) else []
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


# ----- Re-run options (partial re-run without affecting other parts) -----


@router.post("/{opportunity_id}/rerun/attachments", status_code=status.HTTP_202_ACCEPTED)
async def rerun_attachments(
    opportunity_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Re-run document processing only: re-extract text and re-classify. Does not re-extract CLINs or manufacturer/dealer research."""
    opportunity = db.query(Opportunity).filter(
        Opportunity.id == opportunity_id,
        Opportunity.user_id == current_user.id,
    ).first()
    if not opportunity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")
    getattr(analyze_documents, "delay")(opportunity_id, True, False, "")
    return {"message": "Re-run attachments (document processing) started. Refresh the page for updates."}


@router.post("/{opportunity_id}/rerun/clins", status_code=status.HTTP_202_ACCEPTED)
async def rerun_clins(
    opportunity_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Re-run CLIN (and deadline) extraction only from existing documents. Does not change classification or manufacturer/dealer research."""
    opportunity = db.query(Opportunity).filter(
        Opportunity.id == opportunity_id,
        Opportunity.user_id == current_user.id,
    ).first()
    if not opportunity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")
    getattr(rerun_clins_only, "delay")(opportunity_id)
    return {"message": "Re-run CLINs started. Refresh the page for updates."}


@router.post("/{opportunity_id}/rerun/manufacturer-dealer", status_code=status.HTTP_202_ACCEPTED)
async def rerun_manufacturer_dealer(
    opportunity_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Re-run manufacturer and dealer research (Tavily) only. Does not change documents or CLIN extraction."""
    opportunity = db.query(Opportunity).filter(
        Opportunity.id == opportunity_id,
        Opportunity.user_id == current_user.id,
    ).first()
    if not opportunity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")
    getattr(run_tavily_dealers_for_opportunity, "delay")(opportunity_id)
    return {"message": "Re-run manufacturer & dealer research started. Refresh the page for updates."}


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
    logger.info("=" * 80)
    logger.info("DELETING OPPORTUNITY %s", opportunity_id)
    logger.info("=" * 80)
    logger.info(f"Opportunity: {opportunity.title or 'Untitled'} (ID: {opportunity_id})")
    logger.info(f"Notice ID: {opportunity.notice_id or 'N/A'}")
    logger.info(f"Status: {opportunity.status}")
    
    # Get all related data before deletion
    documents = db.query(Document).filter(Document.opportunity_id == opportunity_id).all()
    clins = db.query(CLIN).filter(CLIN.opportunity_id == opportunity_id).all()
    deadlines = db.query(Deadline).filter(Deadline.opportunity_id == opportunity_id).all()
    
    # Log data counts
    logger.info("Related data to be deleted:")
    logger.info("  - Documents: %s", len(documents))
    logger.info("  - CLINs: %s", len(clins))
    logger.info("  - Deadlines: %s", len(deadlines))
    
    # Log document details
    if documents:
        logger.info("  Document files:")
        for doc in documents:
            logger.info(f"    - {doc.file_name} ({doc.file_type}, {doc.file_size or 'N/A'} bytes)")
    
    # Log CLIN details
    if clins:
        logger.info("  CLINs:")
        for clin in clins:
            logger.info(f"    - CLIN {clin.clin_number}: {clin.product_name or clin.clin_name or 'N/A'}")
    
    # Log deadline details
    if deadlines:
        logger.info("  Deadlines:")
        for deadline in deadlines:
            logger.info(f"    - {deadline.deadline_type}: {deadline.due_date} {deadline.due_time or ''}")
    
    logger.info("=" * 80)

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
            doc_file_url = str(getattr(doc, "file_url", "") or "")
            if doc_file_url.startswith("s3://"):
                try:
                    delete_s3_uri(doc_file_url)
                    logger.info("✅ Deleted object: %s", doc_file_url)
                except Exception as s3_exc:
                    logger.warning("❌ Error deleting object %s: %s", doc_file_url, s3_exc)
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
        
    # Tavily results directory (data/tavily_results/opportunity_{opportunity_id})
    if hasattr(settings, 'DATA_DIR'):
        tavily_dir = settings.DATA_DIR / "tavily_results" / f"opportunity_{opportunity_id}"
        if tavily_dir not in directories_to_delete:
            directories_to_delete.append(tavily_dir)
    
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
    logger.info("=" * 80)
    logger.info("FILE DELETION SUMMARY:")
    logger.info("  - Individual files deleted: %s", len(deleted_files))
    logger.info("  - Directories deleted: %s", len(deleted_dirs))
    if deleted_dirs:
        total_dir_files = sum(d.get('files', 0) for d in deleted_dirs)
        logger.info("  - Files in directories: %s", total_dir_files)
    if temp_files_deleted:
        logger.info("  - Temp files/dirs deleted: %s", len(temp_files_deleted))
    if failed_files:
        logger.warning("  - Failed file deletions: %s", len(failed_files))
    if failed_dirs:
        logger.warning("  - Failed directory deletions: %s", len(failed_dirs))
    logger.info("=" * 80)
    
    # Delete the opportunity from database
    # Note: CASCADE will automatically delete all related database records:
    # - Documents (via ondelete="CASCADE" in Document.opportunity_id)
    # - CLINs (via ondelete="CASCADE" in CLIN.opportunity_id)
    # - Deadlines (via ondelete="CASCADE" in Deadline.opportunity_id)
    logger.info("Deleting database records...")
    db.delete(opportunity)
    db.commit()
    
    logger.info("=" * 80)
    logger.info("✅ SUCCESSFULLY DELETED OPPORTUNITY %s", opportunity_id)
    logger.info("   - Database records: 1 opportunity, %s documents, %s CLINs, %s deadlines", len(documents), len(clins), len(deadlines))
    logger.info("   - Files deleted: %s", len(deleted_files))
    logger.info("   - Directories deleted: %s", len(deleted_dirs))
    if temp_files_deleted:
        logger.info("   - Temp files/dirs deleted: %s", len(temp_files_deleted))
    logger.info("=" * 80)
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
    
    # If document is in object storage, return a short-lived URL.
    file_url = getattr(document, "file_url", None)
    if file_url:
        if str(file_url).startswith("s3://"):
            try:
                body = get_s3_object_body(str(file_url))
                if body:
                    return StreamingResponse(
                        body,
                        media_type=media_type,
                        headers={
                            "Content-Disposition": f'inline; filename="{doc_name}"',
                            "Cache-Control": "no-store, no-cache, must-revalidate",
                            "Pragma": "no-cache"
                        }
                    )
            except Exception as e:
                logger.error("Error proxying S3 object %s: %s", file_url, e)
                raise HTTPException(status_code=500, detail="Failed to load document from storage")
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

    return FileResponse(
        path=str(file_path),
        filename=str(doc_name),
        media_type=media_type,
        headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"},
    )


@router.get("/{opportunity_id}/documents/{document_id}/editable-pdf-document")
async def get_editable_pdf_document(
    opportunity_id: str,
    document_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """For a Word document, return the PDF document that was created from it for editing (if any). 404 if none."""
    oid = _parse_positive_int(opportunity_id, "opportunity_id")
    did = _parse_positive_int(document_id, "document_id")
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
    doc_ftype = getattr(document, "file_type", None)
    if doc_ftype != "word":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only Word documents have an editable PDF counterpart.",
        )
    # PDF created from this Word doc has converted_from_document_id = this doc's id
    converted_from_id = getattr(document, "id", None)
    pdf_doc = (
        db.query(Document)
        .filter(
            Document.opportunity_id == oid,
            Document.file_type == DocumentType.PDF,
            Document.converted_from_document_id == converted_from_id,
        )
        .first()
    )
    if not pdf_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No PDF created from this Word document yet. Use Convert to PDF or open Edit to create one.",
        )
    return DocumentResponse.model_validate(pdf_doc)


@router.post("/{opportunity_id}/documents/{document_id}/create-pdf-from-word")
async def create_pdf_from_word(
    opportunity_id: str,
    document_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Convert the Word document to PDF: add as new attachment (keeping the .docx), or overwrite existing converted PDF. Returns the PDF document."""
    oid = _parse_positive_int(opportunity_id, "opportunity_id")
    did = _parse_positive_int(document_id, "document_id")
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
    doc_ftype = getattr(document, "file_type", None)
    if doc_ftype != "word":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document is not a Word file.",
        )
    doc_file_path_str = str(getattr(document, "file_path", "") or "")
    file_path = _resolve_document_file_path(document, doc_file_path_str, oid)
    
    # If not on disk, check if it's on S3 and download it temporarily
    if not file_path.exists() or not file_path.is_file():
        file_url = getattr(document, "file_url", None)
        if file_url and str(file_url).startswith("s3://"):
            try:
                body = get_s3_object_body(str(file_url))
                if body:
                    upload_dir = settings.UPLOADS_DIR / str(oid)
                    upload_dir.mkdir(parents=True, exist_ok=True)
                    safe_name = getattr(document, "original_file_name", "temp_word.docx") or "temp_word.docx"
                    safe_name = safe_name.replace("/", "_").replace("\\", "_")
                    file_path = upload_dir / safe_name
                    file_path.write_bytes(body.read())
            except Exception as e:
                logger.error("Error downloading Word document from S3 for conversion: %s", e)
                
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Word file not found on disk or storage.",
        )
    pdf_path = convert_word_to_pdf(file_path.resolve(), delete_original=False)
    if not pdf_path:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Word to PDF conversion is unavailable. Install LibreOffice on the server (e.g. apt install libreoffice-writer).",
        )
    # Check for existing PDF created from this Word doc
    existing_pdf = (
        db.query(Document)
        .filter(
            Document.opportunity_id == oid,
            Document.file_type == DocumentType.PDF,
            Document.converted_from_document_id == did,
        )
        .first()
    )
    upload_dir = settings.UPLOADS_DIR / str(oid)
    upload_dir.mkdir(parents=True, exist_ok=True)
    if existing_pdf:
        # Overwrite existing converted PDF file with new conversion
        existing_path_str = str(getattr(existing_pdf, "file_path", "") or "")
        existing_path = _resolve_document_file_path(existing_pdf, existing_path_str, oid)
        try:
            existing_path.write_bytes(pdf_path.read_bytes())
        except Exception as e:
            logger.error("create_pdf_from_word: failed to overwrite existing PDF: %s", e, exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update PDF file.")
        existing_pdf.file_size = existing_path.stat().st_size  # type: ignore[assignment]
        existing_pdf.mime_type = "application/pdf"  # type: ignore[assignment]
        if s3_enabled():
            try:
                existing_uri = str(getattr(existing_pdf, "file_url", "") or "")
                parsed = parse_s3_uri(existing_uri) if existing_uri else None
                if parsed:
                    _, key = parsed
                    existing_pdf.file_url = upload_file(existing_path, key, content_type="application/pdf")  # type: ignore[assignment]
                else:
                    key = make_object_key(oid, "uploads", existing_path.name)
                    existing_pdf.file_url = upload_file(existing_path, key, content_type="application/pdf")  # type: ignore[assignment]
                existing_pdf.storage_type = "s3"  # type: ignore[assignment]
            except Exception as exc:
                logger.warning("create_pdf_from_word: failed S3 sync for existing PDF doc_id=%s: %s", existing_pdf.id, exc)
        db.commit()
        db.refresh(existing_pdf)
        logger.info("create_pdf_from_word: re-converted Word doc_id=%s, updated PDF doc_id=%s", did, existing_pdf.id)
        return DocumentResponse.model_validate(existing_pdf)
    # Add as new document (keep the .docx)
    stem = file_path.stem
    pdf_name = f"{stem}.pdf"
    safe_name = pdf_name.replace("/", "_").replace("\\", "_")
    dest_path = upload_dir / safe_name
    dest_path.write_bytes(pdf_path.read_bytes())
    rel_path = str(dest_path.resolve().relative_to(settings.PROJECT_ROOT.resolve()))
    storage_type, file_url = _maybe_upload_to_s3(oid, "uploads", dest_path, "application/pdf")
    new_doc = Document(
        opportunity_id=oid,
        file_name=safe_name,
        original_file_name=pdf_name,
        file_path=rel_path,
        file_size=dest_path.stat().st_size,
        file_type=DocumentType.PDF,
        mime_type="application/pdf",
        source=DocumentSource.USER_UPLOAD,
        storage_type=storage_type,
        file_url=file_url,
        converted_from_document_id=did,
    )
    db.add(new_doc)
    db.commit()
    db.refresh(new_doc)
    logger.info("create_pdf_from_word: created PDF doc_id=%s from Word doc_id=%s", new_doc.id, did)
    return DocumentResponse.model_validate(new_doc)


@router.get("/{opportunity_id}/documents/{document_id}/pdf-for-editing")
async def document_pdf_for_editing(
    opportunity_id: str,
    document_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Return the document as PDF for the in-app editor. For Word: serves the stored converted PDF if one exists (no on-the-fly conversion)."""
    oid = _parse_positive_int(opportunity_id, "opportunity_id")
    did = _parse_positive_int(document_id, "document_id")
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
    doc_file_path_str = str(getattr(document, "file_path", "") or "")
    file_path = _resolve_document_file_path(document, doc_file_path_str, oid)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document file not found at path: {doc_file_path_str}",
        )
    doc_ftype = getattr(document, "file_type", None)
    if doc_ftype == "pdf":
        return FileResponse(
            path=str(file_path),
            media_type="application/pdf",
            headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"},
        )
    if doc_ftype == "word":
        # Serve the stored PDF created from this Word doc (no re-convert)
        pdf_doc = (
            db.query(Document)
            .filter(
                Document.opportunity_id == oid,
                Document.file_type == DocumentType.PDF,
                Document.converted_from_document_id == did,
            )
            .first()
        )
        if not pdf_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No PDF created from this Word document yet. Create one via Convert to PDF or open Edit.",
            )
        pdf_path_str = str(getattr(pdf_doc, "file_path", "") or "")
        pdf_path = _resolve_document_file_path(pdf_doc, pdf_path_str, oid)
        if not pdf_path.exists() or not pdf_path.is_file():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Converted PDF file not found. Use Convert to PDF to create it again.",
            )
        return FileResponse(
            path=str(pdf_path),
            media_type="application/pdf",
            headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"},
        )
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="This document type cannot be edited in the PDF editor.",
    )


# #region agent log
def _autofill_debug_log(message: str, data: dict, hypothesis_id: Optional[str] = None):
    try:
        _debug_path = Path(__file__).resolve().parents[2] / ".cursor" / "debug.log"
        payload = {"timestamp": int(time.time() * 1000), "location": "opportunities.autofill_preview", "message": message, "data": data}
        if hypothesis_id:
            payload["hypothesisId"] = hypothesis_id
        _debug_path.parent.mkdir(parents=True, exist_ok=True)
        with open(_debug_path, "a", encoding="utf-8") as _f:
            _f.write(json.dumps(payload) + "\n")
    except Exception:
        pass
# #endregion


@router.post("/{opportunity_id}/documents/{document_id}/autofill-preview")
async def autofill_preview(
    opportunity_id: str,
    document_id: str,
    body: AutofillPreviewRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Return suggested form field values only for reference fields (contractor + government). Other fields are omitted so they are not modified."""
    # #region agent log
    t0 = time.perf_counter()
    _autofill_debug_log("autofill_preview entry", {"opportunity_id": opportunity_id, "document_id": document_id}, "A")
    logger.info("autofill_preview: request start")
    # #endregion
    oid = _parse_positive_int(opportunity_id, "opportunity_id")
    _parse_positive_int(document_id, "document_id")  # validate; document may be used later for LLM context
    opportunity = (
        db.query(Opportunity)
        .options(joinedload(Opportunity.deadlines), joinedload(Opportunity.clins))
        .filter(Opportunity.id == oid, Opportunity.user_id == current_user.id)
        .first()
    )
    if not opportunity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")
    document = db.query(Document).filter(
        Document.id == int(document_id),
        Document.opportunity_id == oid,
    ).first()
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    field_names = body.field_names or []
    field_types = body.field_types or {}
    profile = db.query(ContractorProfile).filter(ContractorProfile.user_id == current_user.id).first()
    primary_llm, fallback_llm = _get_autofill_llms()
    logger.info("autofill_preview: primary_llm=%s fallback_llm=%s (primary=Claude if configured)", primary_llm is not None, fallback_llm is not None)
    # #region agent log
    t1 = time.perf_counter()
    _autofill_debug_log("autofill_preview after DB+LLM init", {"elapsed_ms": round((t1 - t0) * 1000), "field_count": len(field_names)}, "A")
    logger.info("autofill_preview: after DB+LLM init elapsed=%.0fms fields=%s", (t1 - t0) * 1000, len(field_names))
    # #endregion

    # No form fields: return profile-only suggestions (no OCR). Frontend shows "Suggested from your profile" from this or from its own profile fetch.
    if not field_names:
        from datetime import date
        today = date.today().strftime("%m/%d/%Y")
        if not profile:
            values = {k: "-" for k in ("Phone", "Email", "Company Name", "Company Address", "UEI", "CAGE", "TIN", "Contract Officer Name", "Signature")}
            values["Date"] = today
            return {"fields": values}
        values = {
            "Phone": (profile.phone or "-").strip() or "-",
            "Email": (profile.email or "-").strip() or "-",
            "Company Name": (profile.company_name or "-").strip() or "-",
            "Company Address": (profile.company_address or "-").strip() or "-",
            "UEI": (profile.uei or "-").strip() or "-",
            "CAGE": (profile.cage or "-").strip() or "-",
            "TIN": (profile.tin or "-").strip() or "-",
            "Contract Officer Name": (profile.contract_officer_name or "-").strip() or "-",
            "Signature": (profile.digital_signature or "-").strip() or "-",
            "Date": today,
        }
        return {"fields": values}

    logger.info(
        "autofill_preview: opp_id=%s doc_id=%s fields=%s profile=%s llm=%s",
        oid,
        document_id,
        len(field_names),
        profile is not None,
        primary_llm is not None,
    )
    values = get_autofill_values(
        opportunity,
        field_names,
        field_types,
        llm=primary_llm,
        fallback_llm=fallback_llm,
        current_user=current_user,
        profile=profile,
        pdf_field_values=body.field_values,
        pdf_field_tooltips=body.field_tooltips,
    )
    # #region agent log
    t2 = time.perf_counter()
    _autofill_debug_log("autofill_preview after get_autofill_values", {"elapsed_ms": round((t2 - t1) * 1000), "total_ms": round((t2 - t0) * 1000)}, "A")
    logger.info("autofill_preview: get_autofill_values took %.0fms total so far %.0fms", (t2 - t1) * 1000, (t2 - t0) * 1000)
    # #endregion
    # Return only fields we are allowed to fill (reference: contractor + government). Frontend updates
    # only these; fields not in response are left unchanged (do not overwrite with "-").
    return {"fields": values}


@router.get("/{opportunity_id}/documents/{document_id}/form-fields")
async def get_document_form_fields(
    opportunity_id: str,
    document_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Step 1 — Inspect PDF form fields. Returns AcroForm field metadata (name, type, value, tooltip, options)
    so the client can map correctly. Non-PDF or missing file returns empty list.
    """
    oid = _parse_positive_int(opportunity_id, "opportunity_id")
    did = _parse_positive_int(document_id, "document_id")
    opportunity = (
        db.query(Opportunity)
        .filter(Opportunity.id == oid, Opportunity.user_id == current_user.id)
        .first()
    )
    if not opportunity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")
    document = db.query(Document).filter(
        Document.id == did,
        Document.opportunity_id == oid,
    ).first()
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    doc_file_path_str = str(getattr(document, "file_path", "") or "")
    if not doc_file_path_str:
        return {"fields": []}
    file_path = _resolve_document_file_path(document, doc_file_path_str, oid)
    if not file_path.exists() or not file_path.is_file():
        return {"fields": []}
    if file_path.suffix.lower() != ".pdf":
        return {"fields": []}
    meta = introspect_pdf_fields(file_path)
    return {"fields": meta}


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
    if hasattr(settings, "UPLOADS_DIR"):
        candidates.append(settings.UPLOADS_DIR / str(opportunity_id) / doc_name)
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return candidates[0]


def _unique_document_filename(db: Session, opportunity_id: int, requested_name: str) -> str:
    """Return a filename that does not collide with existing document file_name for this opportunity."""
    base = Path(requested_name)
    stem = base.stem
    suffix = base.suffix.lower()
    existing = {d.file_name for d in db.query(Document).filter(Document.opportunity_id == opportunity_id).all()}
    name = base.name
    if name not in existing:
        return name
    for n in range(1, 1000):
        candidate = f"{stem} (copy){suffix}" if n == 1 else f"{stem} (copy {n}){suffix}"
        if candidate not in existing:
            return candidate
    return f"{stem}_{os.urandom(4).hex()}{suffix}"


@router.post("/{opportunity_id}/documents", response_model=DocumentResponse)
async def add_document(
    opportunity_id: str,
    file: Optional[UploadFile] = File(None, description="New document file (PDF or Word). Saved as new document."),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Add a new document to an opportunity (e.g. Save as new from editor). Does not overwrite any existing document."""
    oid = _parse_positive_int(opportunity_id, "opportunity_id")
    if not file or not getattr(file, "filename", None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is required. Upload a PDF or Word file.",
        )
    opportunity = db.query(Opportunity).filter(
        Opportunity.id == oid,
        Opportunity.user_id == current_user.id
    ).first()
    if not opportunity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")
    filename = file.filename or "document"
    ext = Path(filename).suffix.lower()
    if ext not in (".pdf", ".doc", ".docx"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be PDF or Word (.pdf, .doc, .docx)",
        )
    upload_dir = settings.UPLOADS_DIR / str(oid)
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_filename = filename.replace("/", "_").replace("\\", "_")
    safe_filename = _unique_document_filename(db, oid, safe_filename)
    file_path = upload_dir / safe_filename
    try:
        content = await file.read()
    except Exception as e:
        logger.error("Error reading upload for add_document: %s", e, exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to read uploaded file")
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")
    try:
        file_path.write_bytes(content)
        logger.info("add_document: wrote %s bytes to %s (abs path: %s)", len(content), safe_filename, file_path.resolve())
    except Exception as e:
        logger.error("Error writing new document: %s", e, exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save file")
    if not file_path.exists() or not file_path.is_file():
        logger.error("add_document: file not found on disk after write: %s", file_path)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="File was not saved to disk")
    actual_size = file_path.stat().st_size
    if actual_size != len(content):
        logger.error("add_document: size mismatch after write: expected %s got %s", len(content), actual_size)
        try:
            file_path.unlink()
        except Exception:
            pass
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="File save verification failed")
    # Auto-convert Word to PDF so the document can be viewed/edited in the PDF editor
    if ext in (".doc", ".docx"):
        pdf_path = convert_word_to_pdf(file_path.resolve(), delete_original=True)
        if pdf_path:
            file_path = pdf_path
            safe_filename = pdf_path.name
            file_size = pdf_path.stat().st_size
            doc_type = DocumentType.PDF
            mime_type = "application/pdf"
        else:
            file_size = len(content)
            doc_type = DocumentType.WORD
            mime_type = mimetypes.guess_type(filename)[0] or "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    else:
        file_size = len(content)
        mime_type, _ = mimetypes.guess_type(filename)
        if ext == ".pdf":
            doc_type = DocumentType.PDF
            if not mime_type:
                mime_type = "application/pdf"
        elif ext in (".txt", ".text"):
            doc_type = DocumentType.TEXT
            if not mime_type:
                mime_type = "text/plain"
        else:
            doc_type = DocumentType.OTHER
    rel_path = str(file_path.resolve().relative_to(settings.PROJECT_ROOT.resolve()))
    storage_type, file_url = _maybe_upload_to_s3(
        oid,
        "uploads",
        file_path,
        mime_type or "application/octet-stream",
    )
    doc = Document(
        opportunity_id=oid,
        file_name=safe_filename,
        original_file_name=filename,
        file_path=rel_path,
        file_size=file_size,
        file_type=doc_type,
        mime_type=mime_type or "application/octet-stream",
        source=DocumentSource.USER_UPLOAD,
        storage_type=storage_type,
        file_url=file_url,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    logger.info("add_document: opp_id=%s doc_id=%s file=%s", oid, doc.id, safe_filename)
    return DocumentResponse.model_validate(doc)


@router.put("/{opportunity_id}/documents/{document_id}")
async def overwrite_document(
    opportunity_id: str,
    document_id: str,
    file: Optional[UploadFile] = File(None, description="Replacement file (PDF or Word). Overwrites existing document."),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Overwrite an existing opportunity document with new file content (e.g. after in-app edit).
    Writes to a local temp path and syncs back to S3 when S3 is enabled.
    """
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
        logger.error("overwrite_document: Error reading upload: %s", e, exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to read uploaded file")
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty. Save the PDF again.",
        )

    # Determine write-path: use a local temp dir under uploads regardless of whether doc was from S3
    upload_dir = settings.UPLOADS_DIR / str(oid)
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Build a stable local filename based on the original document name
    existing_name = (
        getattr(document, "original_file_name", None)
        or getattr(document, "file_name", None)
        or f"doc_{did}"
    )
    base_stem = Path(existing_name).stem.replace("/", "_").replace("\\", "_")

    file_size = 0
    final_mime: str = "application/octet-stream"

    try:
        if ext in (".doc", ".docx"):
            # Write Word → convert to PDF → persist PDF
            temp_word = upload_dir / f"{base_stem}_replace.docx"
            temp_word.write_bytes(content)
            pdf_path = convert_word_to_pdf(temp_word.resolve(), delete_original=True)
            if pdf_path:
                final_local = upload_dir / f"{base_stem}.pdf"
                final_local.write_bytes(pdf_path.read_bytes())
                if pdf_path != final_local:
                    try: pdf_path.unlink()
                    except OSError: pass
                file_path = final_local
                final_mime = "application/pdf"
                document.file_name = final_local.name  # type: ignore[assignment]
                document.file_type = DocumentType.PDF  # type: ignore[assignment]
                document.mime_type = final_mime  # type: ignore[assignment]
            else:
                # LibreOffice unavailable – keep as Word
                file_path = upload_dir / f"{base_stem}.docx"
                file_path.write_bytes(content)
                final_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                document.file_name = file_path.name  # type: ignore[assignment]
                document.file_type = DocumentType.WORD  # type: ignore[assignment]
                document.mime_type = final_mime  # type: ignore[assignment]
        else:
            # Pure PDF upload
            file_path = upload_dir / f"{base_stem}.pdf"
            file_path.write_bytes(content)
            final_mime = "application/pdf"
            document.file_name = file_path.name  # type: ignore[assignment]
            document.file_type = DocumentType.PDF  # type: ignore[assignment]
            document.mime_type = final_mime  # type: ignore[assignment]

        file_size = file_path.stat().st_size
        document.file_size = file_size  # type: ignore[assignment]
        # Keep a local relative path as fallback
        try:
            document.file_path = str(file_path.resolve().relative_to(settings.PROJECT_ROOT.resolve()))  # type: ignore[assignment]
        except ValueError:
            document.file_path = str(file_path)  # type: ignore[assignment]

    except Exception as e:
        logger.error("overwrite_document: Error writing file: %s", e, exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save file")

    # ── S3 sync: upload the locally-written file back to object storage ──────
    if s3_enabled():
        try:
            existing_uri = str(getattr(document, "file_url", "") or "")
            parsed = parse_s3_uri(existing_uri) if existing_uri else None
            if parsed:
                # Overwrite same S3 key
                _, key = parsed
            else:
                # Determine a new key (category = "uploads")
                key = make_object_key(oid, "uploads", file_path.name)
            new_uri = upload_file(file_path, key, content_type=final_mime)
            document.file_url = new_uri  # type: ignore[assignment]
            document.storage_type = "s3"  # type: ignore[assignment]
            logger.info("overwrite_document: Synced to S3 uri=%s size=%s", new_uri, file_size)
        except Exception as exc:
            logger.warning("overwrite_document: S3 sync failed for doc_id=%s: %s — file kept locally", did, exc)

    db.commit()
    db.refresh(document)
    logger.info("overwrite_document: Success opp_id=%s doc_id=%s file_size=%s", oid, did, file_size)
    return DocumentResponse.model_validate(document)


@router.delete("/{opportunity_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    opportunity_id: str,
    document_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Delete a document from the opportunity and remove its file from disk if stored locally."""
    oid = _parse_positive_int(opportunity_id, "opportunity_id")
    did = _parse_positive_int(document_id, "document_id")
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
    doc_file_path_str = str(getattr(document, "file_path", "") or "")
    file_url = str(getattr(document, "file_url", "") or "")
    if file_url.startswith("s3://"):
        try:
            delete_s3_uri(file_url)
            logger.info("delete_document: removed object %s", file_url)
        except Exception as exc:
            logger.warning("delete_document: could not remove object %s: %s", file_url, exc)
    if doc_file_path_str and not file_url.startswith("s3://"):
        file_path = _resolve_document_file_path(document, doc_file_path_str, oid)
        if file_path.exists() and file_path.is_file():
            try:
                file_path.unlink()
                logger.info("delete_document: removed file %s", file_path)
            except Exception as e:
                logger.warning("delete_document: could not remove file %s: %s", file_path, e)
    db.delete(document)
    db.commit()
    return None


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
