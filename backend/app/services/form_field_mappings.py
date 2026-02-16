"""
Canonical data-to-form field mapping for robust form filling.

Maps our domain data keys (solicitation_number, contractor_name, etc.) to the
labels and entity types that Google Document AI Form Parser or AcroForm fields
may use. This gives consistent, predictable filling for SF1449 and similar forms.
"""

from typing import Dict, List, Optional

# Canonical keys we use when passing data to the form filler (e.g. from opportunity/CLIN data).
# Each key maps to a list of possible form field identifiers:
# - Form Parser entity types (e.g. "company_name", "address", "date_time")
# - Common SF1449 / government form labels (substrings, normalized)
# - AcroForm field name fragments
DATA_KEY_TO_FORM_LABELS: Dict[str, List[str]] = {
    # Cover / header
    "solicitation_number": [
        "solicitation", "sol_no", "solicitation_no", "solicitation_number",
        "solicitationno", "rfp_number", "rfp_no", "solicitation_num",
    ],
    "contract_number": [
        "contract", "contract_no", "contract_number", "contractno",
        "contract_num", "cn", "ref_number",
    ],
    "offer_due_date": [
        "offer_due", "due_date", "offer_due_date", "date", "closing_date",
        "response_due", "submission_deadline", "date_time",
    ],
    "offer_due_time": [
        "due_time", "time", "offer_due_time", "closing_time", "receipt_time",
    ],
    # Contractor / vendor
    "contractor_name": [
        "company", "company_name", "contractor", "contractor_name",
        "vendor", "vendor_name", "organization", "name", "companyname",
    ],
    "contractor_address": [
        "address", "contractor_address", "vendor_address", "street",
        "remittance_address", "company_address", "business_address",
    ],
    "contractor_phone": [
        "phone", "telephone", "contractor_phone", "vendor_phone",
        "phone_number", "tel", "contact_phone",
    ],
    "contractor_email": [
        "email", "contractor_email", "vendor_email", "e_mail", "email_address",
    ],
    "tax_id": [
        "tax_id", "ein", "tin", "federal_tax_id", "tax_identification",
    ],
    "uei_number": [
        "uei", "uei_number", "unique_entity_id", "sam_uei",
    ],
    # Signature block
    "signature_name": [
        "signature", "signatory", "signature_name", "name", "authorized_name",
    ],
    "signature_title": [
        "title", "signature_title", "position", "authorized_title",
    ],
    "signature_date": [
        "date", "signature_date", "date_signed", "date_of_signature",
    ],
    # Contracting officer / government
    "contracting_officer": [
        "contracting_officer", "co_name", "ko", "government_contact",
    ],
    # Amounts and delivery
    "total_amount": [
        "amount", "total", "total_amount", "total_price", "price", "sum",
    ],
    "delivery_date": [
        "delivery", "delivery_date", "period_of_performance", "pop",
        "completion_date", "date_time",
    ],
    "delivery_address": [
        "ship_to", "delivery_address", "ship_to_address", "destination",
        "place_of_delivery", "address",
    ],
    "payment_terms": [
        "payment_terms", "terms", "net_30", "payment",
    ],
}

# Form Parser entity types (Document AI) that we map to our data keys.
# Used when Form Parser returns entity.type (e.g. "company_name", "address").
FORM_PARSER_TYPE_TO_DATA_KEY: Dict[str, str] = {
    "company_name": "contractor_name",
    "address": "contractor_address",
    "date_time": "signature_date",
    "phone_number": "contractor_phone",
    "email": "contractor_email",
    "person_name": "signature_name",
    "organization_name": "contractor_name",
}


def get_data_key_for_form_field(
    form_field_name: str,
    form_field_type: Optional[str] = None,
) -> Optional[str]:
    """
    Return the canonical data key that should fill this form field, or None.

    Args:
        form_field_name: Field name or label from AcroForm / OCR.
        form_field_type: Optional entity type from Document AI Form Parser (e.g. "company_name").

    Returns:
        Our data key (e.g. "contractor_name") or None if no mapping.
    """
    if form_field_type and form_field_type in FORM_PARSER_TYPE_TO_DATA_KEY:
        return FORM_PARSER_TYPE_TO_DATA_KEY[form_field_type]

    name_norm = "".join(c for c in form_field_name.lower() if c.isalnum())
    if not name_norm:
        return None

    for data_key, labels in DATA_KEY_TO_FORM_LABELS.items():
        for label in labels:
            label_norm = "".join(c for c in label.lower() if c.isalnum())
            if label_norm and (label_norm in name_norm or name_norm in label_norm):
                return data_key
    return None
