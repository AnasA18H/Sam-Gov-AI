"""
Generate draft quote emails from opportunity CLINs (manufacturers/dealers with contact emails).
Persisted as DraftQuoteEmail; generate saves to DB, send/discard delete from DB.

Tone: commercial inquiry only — no reference to government contracts or solicitations.
Opening: "Hello, We're currently working on a project and would like to request a quote"
"""
import re
from typing import List, Any, Optional
from ..models.opportunity import Opportunity
from ..models.clin import CLIN
from ..models.draft_quote_email import DraftQuoteEmail
from sqlalchemy.orm import Session


def _sanitize_for_commercial_email(text: str) -> str:
    """Rewrite government/procurement phrasing so the email reads as a standard commercial inquiry."""
    if not text or not text.strip():
        return text
    s = text
    # Long phrases first, then single terms (contract/procurement → commercial)
    s = re.sub(r"\bafter\s+receipt\s+of\s+contract\s+award\b", "after order confirmation", s, flags=re.IGNORECASE)
    s = re.sub(r"\breceipt\s+of\s+contract\s+award\b", "order confirmation", s, flags=re.IGNORECASE)
    s = re.sub(r"\bcontract\s+award\b", "order confirmation", s, flags=re.IGNORECASE)
    s = re.sub(r"\bagreed\s+upon\s+by\s+contractor\s+and\s+COR\b", "agreed upon with our team", s, flags=re.IGNORECASE)
    s = re.sub(r"\bcontractor\s+and\s+COR\b", "vendor and our team", s, flags=re.IGNORECASE)
    s = re.sub(r"\bthe\s+contractor\b", "the vendor", s, flags=re.IGNORECASE)
    s = re.sub(r"\bcontractor\b", "vendor", s, flags=re.IGNORECASE)
    s = re.sub(r"\bCOR\b", "our project lead", s)  # Contracting Officer's Representative
    s = re.sub(r"\bsolicitation\b", "request", s, flags=re.IGNORECASE)
    return s.strip()


def _normalize_manufacturer_list(clin: CLIN) -> List[dict]:
    m = clin.manufacturer_research
    if m is None:
        return []
    parsed = m
    if isinstance(m, str):
        try:
            import json
            parsed = json.loads(m)
        except Exception:
            return []
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        return [{"name": None, "official_website": parsed.get("official_website"), "sales_contact_email": parsed.get("sales_contact_email")}]
    return []


def _normalize_dealer_list(clin: CLIN) -> List[dict]:
    d = clin.dealer_research
    if d is None:
        return []
    if isinstance(d, list):
        return d
    if isinstance(d, str):
        try:
            import json
            a = json.loads(d)
            return a if isinstance(a, list) else []
        except Exception:
            return []
    return []


def _html_escape(s: str) -> str:
    """Escape for safe HTML content."""
    if not s:
        return ""
    s = str(s)
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _normalize_delivery_timeline(timeline_str: Optional[str]) -> Optional[str]:
    """Convert delivery timeline jargon to readable commercial language."""
    if not timeline_str:
        return None
    s = str(timeline_str).strip()
    if not s:
        return None
    # Convert "X DAYS ADO" to "X days after order" or similar
    s = re.sub(r"(\d+)\s*DAYS?\s*ADO", r"\1 days after order", s, flags=re.IGNORECASE)
    s = re.sub(r"(\d+)\s*DAYS?\s*ARO", r"\1 days after receipt of order", s, flags=re.IGNORECASE)
    return s


def _template(opp: Opportunity, clin: CLIN, contact: dict, contact_type: str) -> tuple[str, str]:
    is_mfr = contact_type == "manufacturer"
    product_name = getattr(clin, "product_name", None) or getattr(clin, "clin_name", None) or "product"
    manufacturer_name = getattr(clin, "manufacturer_name", None) or "manufacturer"
    part_number = getattr(clin, "part_number", None) or getattr(clin, "base_item_number", None)
    quantity = None
    if clin.quantity is not None:
        quantity = f"{clin.quantity} {clin.unit_of_measure or 'units'}"
    add = clin.additional_data or {}
    delivery_address_raw = add.get("delivery_address")
    delivery_timeline_raw = add.get("delivery_timeline") or getattr(clin, "timeline", None)
    delivery_address = _sanitize_for_commercial_email(str(delivery_address_raw)) if delivery_address_raw else None
    delivery_timeline_raw_sanitized = _sanitize_for_commercial_email(str(delivery_timeline_raw)) if delivery_timeline_raw else None
    delivery_timeline = _normalize_delivery_timeline(delivery_timeline_raw_sanitized)
    nsn = add.get("nsn") or None

    # Subject: include quantity if available for better visibility
    subject = f"Quote Request: {product_name}"
    if part_number not in (None, ""):
        subject += f" (Part #{part_number})"
    if quantity:
        subject += f" — Qty {quantity.split()[0]}"

    # Build HTML body with bold section headers and clear spacing (inline styles for email clients)
    _p = '<p style="margin: 0 0 0.75em 0;">'
    _p_section = '<p style="margin: 1.25em 0 0.5em 0;">'  # extra space before section
    to_name = (contact.get("company_name") or contact.get("name") or "").strip()
    greeting = f"Hello, {_html_escape(to_name)}," if to_name else "Hello,"
    opening = "We're currently working on a project and would like to request a quote for the following:"
    body = f"{_p}{greeting}</p>{_p}{opening}</p>"
    body += f'{_p_section}<strong>Product Specifications:</strong><br/>'
    body += f"• Product Name: {_html_escape(product_name)}<br/>"
    if manufacturer_name and not is_mfr:
        body += f"• Manufacturer: {_html_escape(manufacturer_name)}<br/>"
    if part_number not in (None, ""):
        body += f"• Part Number: {_html_escape(part_number)}<br/>"
    if getattr(clin, "model_number", None):
        body += f"• Model Number: {_html_escape(clin.model_number)}<br/>"
    if nsn:
        body += f"• NSN: {_html_escape(nsn)}<br/>"
    if quantity:
        body += f"• Quantity: {_html_escape(quantity)}<br/>"
    product_description = getattr(clin, "product_description", None)
    if product_description not in (None, ""):
        body += f"• Description: {_html_escape(product_description)}<br/>"
    body += "</p>"
    if delivery_address:
        body += f'{_p_section}<strong>Delivery Address:</strong><br/>{_html_escape(delivery_address)}</p>'
    if delivery_timeline:
        body += f'{_p_section}<strong>Required Delivery Timeline:</strong><br/>{_html_escape(delivery_timeline)}</p>'
    body += f'{_p_section}<strong>We would also appreciate:</strong><br/>'
    body += "• Product datasheets/specification sheets<br/>• Net payment terms</p>"
    body += f'{_p}We\'re currently evaluating competitive quotes from multiple suppliers and would appreciate your best pricing. Please provide your quote at your earliest convenience so we can move forward with our selection process.</p>'
    body += f'{_p}<em>Thank you for your time and consideration.</em></p>{_p}Best regards</p>'
    return subject, body


def generate_drafts_for_opportunity(db: Session, opportunity_id: int, opportunity: Optional[Opportunity] = None) -> List[DraftQuoteEmail]:
    """Build draft quote emails from CLINs and persist; replaces existing drafts for this opportunity."""
    from sqlalchemy.orm import joinedload
    if opportunity is None:
        opportunity = db.query(Opportunity).filter(Opportunity.id == opportunity_id).options(
            joinedload(Opportunity.clins)
        ).first()
    if not opportunity or not opportunity.clins:
        return []

    # Delete existing drafts for this opportunity
    db.query(DraftQuoteEmail).filter(DraftQuoteEmail.opportunity_id == opportunity_id).delete()

    created = []
    for clin in opportunity.clins:
        mfr_list = _normalize_manufacturer_list(clin)
        for mfr in mfr_list:
            if not mfr.get("sales_contact_email"):
                continue
            subject, body = _template(opportunity, clin, mfr, "manufacturer")
            to_name = mfr.get("name") or clin.manufacturer_name or "Manufacturer"
            draft = DraftQuoteEmail(
                opportunity_id=opportunity_id,
                to=mfr["sales_contact_email"],
                to_name=to_name,
                subject=subject,
                body=body,
                contact_type="manufacturer",
                clin_id=clin.id,
                clin_number=clin.clin_number,
            )
            db.add(draft)
            created.append(draft)

        dealer_list = _normalize_dealer_list(clin)
        for dealer in dealer_list:
            if not dealer.get("sales_contact_email"):
                continue
            subject, body = _template(opportunity, clin, dealer, "dealer")
            to_name = dealer.get("company_name") or "Dealer"
            draft = DraftQuoteEmail(
                opportunity_id=opportunity_id,
                to=dealer["sales_contact_email"],
                to_name=to_name,
                subject=subject,
                body=body,
                contact_type="dealer",
                clin_id=clin.id,
                clin_number=clin.clin_number,
            )
            db.add(draft)
            created.append(draft)

    db.commit()
    for d in created:
        db.refresh(d)
    return created
