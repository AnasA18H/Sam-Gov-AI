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
        name = parsed.get("name")
        if isinstance(name, str):
            name = name.strip() or None
        else:
            name = None
        return [{
            "name": name,
            "official_website": parsed.get("official_website"),
            "sales_contact_email": parsed.get("sales_contact_email"),
        }]
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


def _product_spec_section(clin: CLIN, contact_type: str) -> str:
    """HTML fragment for one CLIN's product specs (no greeting/closing)."""
    is_mfr = contact_type == "manufacturer"
    product_name = getattr(clin, "product_name", None) or getattr(clin, "clin_name", None) or "product"
    manufacturer_name = getattr(clin, "manufacturer_name", None) or "manufacturer"
    part_number = getattr(clin, "part_number", None) or getattr(clin, "base_item_number", None)
    quantity = None
    if clin.quantity is not None:
        quantity = f"{clin.quantity} {clin.unit_of_measure or 'units'}"
    add = getattr(clin, "additional_data", None) or {}
    if not isinstance(add, dict):
        add = {}
    nsn = add.get("nsn") or None
    _p_section = '<p style="margin: 1.25em 0 0.5em 0;">'
    html = f'{_p_section}<strong>Product Specifications:</strong><br/>'
    html += f"• Product Name: {_html_escape(product_name)}<br/>"
    if manufacturer_name and not is_mfr:
        html += f"• Manufacturer: {_html_escape(manufacturer_name)}<br/>"
    if part_number not in (None, ""):
        html += f"• Part Number: {_html_escape(part_number)}<br/>"
    if getattr(clin, "model_number", None):
        html += f"• Model Number: {_html_escape(str(clin.model_number))}<br/>"
    if nsn:
        html += f"• NSN: {_html_escape(nsn)}<br/>"
    if quantity:
        html += f"• Quantity: {_html_escape(quantity)}<br/>"
    product_description = getattr(clin, "product_description", None)
    if product_description not in (None, ""):
        html += f"• Description: {_html_escape(product_description)}<br/>"
    html += "</p>"
    return html


def _template(opp: Opportunity, clin: CLIN, contact: dict, contact_type: str) -> tuple[str, str]:
    """Single-CLIN email: subject and full HTML body."""
    add = clin.additional_data or {}
    delivery_address_raw = add.get("delivery_address")
    delivery_timeline_raw = add.get("delivery_timeline") or getattr(clin, "timeline", None)
    delivery_address = _sanitize_for_commercial_email(str(delivery_address_raw)) if delivery_address_raw else None
    delivery_timeline_raw_sanitized = _sanitize_for_commercial_email(str(delivery_timeline_raw)) if delivery_timeline_raw else None
    delivery_timeline = _normalize_delivery_timeline(delivery_timeline_raw_sanitized)
    product_name = getattr(clin, "product_name", None) or getattr(clin, "clin_name", None) or "product"
    part_number = getattr(clin, "part_number", None) or getattr(clin, "base_item_number", None)
    quantity = f"{clin.quantity} {clin.unit_of_measure or 'units'}" if clin.quantity is not None else None

    subject = f"Quote Request: {product_name}"
    if part_number not in (None, ""):
        subject += f" (Part #{part_number})"
    if quantity:
        subject += f" — Qty {quantity.split()[0]}"

    _p = '<p style="margin: 0 0 0.75em 0;">'
    _p_section = '<p style="margin: 1.25em 0 0.5em 0;">'
    to_name = (contact.get("company_name") or contact.get("name") or "").strip()
    greeting = f"Hello, {_html_escape(to_name)}," if to_name else "Hello,"
    opening = "We're currently working on a project and would like to request a quote for the following:"
    body = f"{_p}{greeting}</p>{_p}{opening}</p>"
    body += _product_spec_section(clin, contact_type)
    if delivery_address:
        body += f'{_p_section}<strong>Delivery Address:</strong><br/>{_html_escape(delivery_address)}</p>'
    if delivery_timeline:
        body += f'{_p_section}<strong>Required Delivery Timeline:</strong><br/>{_html_escape(delivery_timeline)}</p>'
    body += f'{_p_section}<strong>We would also appreciate:</strong><br/>'
    body += "• Product datasheets/specification sheets<br/>• Net payment terms</p>"
    body += f'{_p}We\'re currently evaluating competitive quotes from multiple suppliers and would appreciate your best pricing. Please provide your quote at your earliest convenience so we can move forward with our selection process.</p>'
    body += f'{_p}<em>Thank you for your time and consideration.</em></p>{_p}Best regards</p>'
    return subject, body


def _template_combined(
    opp: Opportunity,
    items: List[tuple],  # [(clin, contact), ...]
    contact_type: str,
    to_name: str,
) -> tuple[str, str]:
    """One email covering multiple CLINs for the same recipient. items = [(clin, contact), ...]."""
    if not items:
        return "Quote Request", ""
    if len(items) == 1:
        return _template(opp, items[0][0], items[0][1], contact_type)

    _p = '<p style="margin: 0 0 0.75em 0;">'
    _p_section = '<p style="margin: 1.25em 0 0.5em 0;">'
    greeting = f"Hello, {_html_escape(to_name)}," if to_name else "Hello,"
    opening = "We're currently working on a project and would like to request quotes for the following line items:"
    body = f"{_p}{greeting}</p>{_p}{opening}</p>"

    delivery_address_used = None
    delivery_timeline_used = None

    for idx, (clin, contact) in enumerate(items, 1):
        clin_num = getattr(clin, "clin_number", None) or str(idx)
        body += f'{_p_section}<strong>— Line item {idx} (CLIN {_html_escape(str(clin_num))}):</strong></p>'
        body += _product_spec_section(clin, contact_type)
        add = clin.additional_data or {}
        if not delivery_address_used and add.get("delivery_address"):
            delivery_address_used = _sanitize_for_commercial_email(str(add.get("delivery_address")))
        if not delivery_timeline_used:
            tl = add.get("delivery_timeline") or getattr(clin, "timeline", None)
            if tl:
                delivery_timeline_used = _normalize_delivery_timeline(_sanitize_for_commercial_email(str(tl)))

    if delivery_address_used:
        body += f'{_p_section}<strong>Delivery Address:</strong><br/>{_html_escape(delivery_address_used)}</p>'
    if delivery_timeline_used:
        body += f'{_p_section}<strong>Required Delivery Timeline:</strong><br/>{_html_escape(delivery_timeline_used)}</p>'
    body += f'{_p_section}<strong>We would also appreciate:</strong><br/>'
    body += "• Product datasheets/specification sheets<br/>• Net payment terms</p>"
    body += f'{_p}We\'re currently evaluating competitive quotes from multiple suppliers and would appreciate your best pricing. Please provide your quote(s) at your earliest convenience so we can move forward with our selection process.</p>'
    body += f'{_p}<em>Thank you for your time and consideration.</em></p>{_p}Best regards</p>'

    n = len(items)
    subject = f"Quote Request: Multiple line items ({n} items)"
    return subject, body


def generate_drafts_for_opportunity(db: Session, opportunity_id: int, opportunity: Optional[Opportunity] = None) -> List[DraftQuoteEmail]:
    """Build draft quote emails from CLINs and persist; replaces existing drafts for this opportunity.
    Groups by recipient email: one combined email per dealer/manufacturer covering all their CLINs."""
    from sqlalchemy.orm import joinedload
    from collections import defaultdict

    if opportunity is None:
        opportunity = db.query(Opportunity).filter(Opportunity.id == opportunity_id).options(
            joinedload(Opportunity.clins)
        ).first()
    if not opportunity or not opportunity.clins:
        return []

    # Collect (contact_type, normalized_email, to_name, clin, contact) then group by (contact_type, email)
    groups = defaultdict(list)  # (contact_type, email_lower) -> [(clin, contact, to_name), ...]

    for clin in opportunity.clins:
        mfr_list = _normalize_manufacturer_list(clin)
        for mfr in mfr_list:
            email = (mfr.get("sales_contact_email") or "").strip()
            if not email:
                continue
            key = ("manufacturer", email.lower())
            to_name = mfr.get("name") or clin.manufacturer_name or "Manufacturer"
            groups[key].append((clin, mfr, to_name))

        dealer_list = _normalize_dealer_list(clin)
        for dealer in dealer_list:
            email = (dealer.get("sales_contact_email") or "").strip()
            if not email:
                continue
            key = ("dealer", email.lower())
            to_name = dealer.get("company_name") or "Dealer"
            groups[key].append((clin, dealer, to_name))

    # Delete existing drafts for this opportunity
    db.query(DraftQuoteEmail).filter(DraftQuoteEmail.opportunity_id == opportunity_id).delete()

    created = []
    for (contact_type, email_lower), group in groups.items():
        # Dedupe by clin id so same dealer on same CLIN once (e.g. multiple entries in dealer_research)
        seen_clin_ids = set()
        unique_items = []
        canonical_to_name = None
        for clin, contact, to_name in group:
            if clin.id in seen_clin_ids:
                continue
            seen_clin_ids.add(clin.id)
            unique_items.append((clin, contact))
            if canonical_to_name is None:
                canonical_to_name = to_name
        if not unique_items:
            continue

        # Use original email (first occurrence) for To
        first_contact = unique_items[0][1]
        to_email = first_contact.get("sales_contact_email") or email_lower
        to_name = canonical_to_name or ("Manufacturer" if contact_type == "manufacturer" else "Dealer")

        subject, body = _template_combined(opportunity, unique_items, contact_type, to_name)
        first_clin = unique_items[0][0]
        clin_numbers_full = ", ".join(str(getattr(c, "clin_number", None) or str(i)) for i, (c, _) in enumerate(unique_items, 1))
        clin_numbers = clin_numbers_full[:50] if len(clin_numbers_full) > 50 else clin_numbers_full  # DB column is String(50)

        draft = DraftQuoteEmail(
            opportunity_id=opportunity_id,
            to=to_email,
            to_name=to_name,
            subject=subject,
            body=body,
            contact_type=contact_type,
            clin_id=first_clin.id,
            clin_number=clin_numbers,
        )
        db.add(draft)
        created.append(draft)

    db.commit()
    for d in created:
        db.refresh(d)
    return created
