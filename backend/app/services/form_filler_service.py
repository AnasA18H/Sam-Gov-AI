"""
Form filler service: build opportunity form data and run GenericPDFFormFiller.
Used by API to get form fields and fill forms (overwrite or save as new document).
"""
import logging
from typing import Any, Dict, List, Optional, Tuple

from ..models.deadline import Deadline
from ..models.opportunity import Opportunity
from .generic_pdf_form_filler import GenericPDFFormFiller

logger = logging.getLogger(__name__)


def build_opportunity_form_data(
    opportunity: Opportunity,
    deadlines: Optional[List[Deadline]] = None,
    include_clin_totals: bool = True,
) -> Dict[str, Any]:
    """
    Build a flat dict of form field values from opportunity (and optional deadlines)
    for use with GenericPDFFormFiller. Keys match form_field_mappings.DATA_KEY_TO_FORM_LABELS.
    """
    data: Dict[str, Any] = {}

    # Solicitation / contract identifiers
    sam_id = getattr(opportunity, "sam_gov_id", None) or getattr(opportunity, "id", "")
    data["solicitation_number"] = str(sam_id) if sam_id else ""
    data["contract_number"] = data["solicitation_number"]

    # Opportunity title / agency
    title = getattr(opportunity, "title", None) or ""
    agency = getattr(opportunity, "agency", None) or ""
    if agency and title:
        data["contracting_officer"] = agency  # fallback; may be overwritten by contacts

    # Primary deadline -> offer due date/time
    if deadlines:
        for d in deadlines:
            if getattr(d, "is_primary", False) or (getattr(d, "deadline_type", "") or "").lower() in (
                "submission",
                "offers_due",
                "proposal",
            ):
                due = getattr(d, "due_date", None)
                if due:
                    try:
                        data["offer_due_date"] = due.strftime("%m-%d-%Y") if hasattr(due, "strftime") else str(due)[:10]
                    except Exception:
                        data["offer_due_date"] = str(due)[:10]
                data["offer_due_time"] = getattr(d, "due_time", None) or ""
                data["signature_date"] = data.get("offer_due_date", "")
                break
        if "offer_due_date" not in data and deadlines:
            d = deadlines[0]
            due = getattr(d, "due_date", None)
            if due:
                try:
                    data["offer_due_date"] = due.strftime("%m-%d-%Y") if hasattr(due, "strftime") else str(due)[:10]
                except Exception:
                    data["offer_due_date"] = str(due)[:10]
            data["offer_due_time"] = getattr(d, "due_time", None) or ""

    # Delivery: from first CLIN's additional_data or timeline
    clins = getattr(opportunity, "clins", None) or []
    if clins and include_clin_totals:
        add = getattr(clins[0], "additional_data", None) or {}
        if isinstance(add, dict):
            data["delivery_address"] = add.get("delivery_address") or add.get("delivery_timeline") or ""
            if not data.get("delivery_date") and add.get("delivery_timeline"):
                data["delivery_date"] = add.get("delivery_timeline")

    # Placeholder contractor fields (user or profile can fill later)
    data.setdefault("contractor_name", "")
    data.setdefault("contractor_address", "")
    data.setdefault("contractor_phone", "")
    data.setdefault("contractor_email", "")
    data.setdefault("signature_name", "")
    data.setdefault("signature_title", "")
    data.setdefault("signature_date", data.get("offer_due_date", ""))
    data.setdefault("tax_id", "")
    data.setdefault("uei_number", "")
    data.setdefault("total_amount", "")
    data.setdefault("payment_terms", "Net 30")

    return {k: v for k, v in data.items() if v is not None and str(v).strip() != ""}


def get_form_fields_for_pdf(pdf_path: str) -> Tuple[Dict[str, Any], str]:
    """
    Return (form_fields dict, extraction_source) for the given PDF path.
    """
    logger.info("get_form_fields_for_pdf path=%s", pdf_path)
    filler = GenericPDFFormFiller()
    filler.detect_form_type(pdf_path)
    fields = filler.extract_form_fields(pdf_path)
    source = getattr(filler, "extraction_source", None) or "none"
    logger.info("get_form_fields_for_pdf result field_count=%s source=%s", len(fields), source)
    return fields, source


def fill_pdf_form(
    pdf_path: str,
    data: Dict[str, Any],
    output_path: Optional[str] = None,
) -> Optional[str]:
    """
    Fill the PDF form with data; write to output_path if given, else a temp path.
    Returns path to filled PDF or None on failure.
    """
    logger.info(
        "fill_pdf_form start path=%s data_keys=%s output_path=%s",
        pdf_path, len(data), output_path,
    )
    filler = GenericPDFFormFiller()
    filler.detect_form_type(pdf_path)
    filler.extract_form_fields(pdf_path)
    result = filler.fill_form(pdf_path, data, output_path=output_path)
    if result:
        logger.info("fill_pdf_form success path=%s output=%s", pdf_path, result)
    else:
        logger.warning("fill_pdf_form failed path=%s", pdf_path)
    return result
