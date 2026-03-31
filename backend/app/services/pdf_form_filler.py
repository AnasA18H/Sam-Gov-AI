"""
PDF form fill using pypdf/PyPDF2: introspect fields, map via field_map.json, fill from DB.
- Step 1: Inspect form fields (get_fields() with /FT, /V, /TU, /Opt).
- Step 2: Pull data from DB (opportunity, profile, user) and resolve data_key -> value.
- Step 3: Validate (only fill known fields), fill and write (update_page_form_field_values).
Checkboxes: use "Yes" / "Off" per PDF spec. Empty -> "" (not None).
"""
import io
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..core.config import settings

logger = logging.getLogger(__name__)

# PyPDF2 is already in requirements
try:
    from PyPDF2 import PdfReader, PdfWriter
except ImportError:
    PdfReader = None  # type: ignore
    PdfWriter = None  # type: ignore

# Default for unmapped or blank
UNMAPPED = "-"

# Checkbox values for AcroForm: /Yes and /Off
CHECKBOX_ON = "Yes"
CHECKBOX_OFF = "Off"


def _normalize_field_name(name: str) -> str:
    """Normalize for lookup in default map: lowercase, collapse spaces/underscores/dots."""
    if not name:
        return ""
    return re.sub(r"[\s_.\[\]-]+", "", (name or "").lower())


def _today_us() -> str:
    return datetime.now(timezone.utc).strftime("%m/%d/%Y")


def _get_field_map_path() -> Path:
    """Path to field_map.json (project data dir)."""
    base = getattr(settings, "PROJECT_ROOT", Path.cwd())
    if not isinstance(base, Path):
        base = Path(base)
    candidates = [
        base / "backend" / "data" / "field_map.json",
        base / "data" / "field_map.json",
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]


def load_field_map(form_type: str = "default") -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    Load field_map.json. Returns (exact_map, default_map).
    - exact_map: form-specific (e.g. sf1449) PDF field name -> data_key (exact match).
    - default_map: normalized field name -> data_key (for fallback).
    """
    path = _get_field_map_path()
    exact_map: Dict[str, str] = {}
    default_map: Dict[str, str] = {}
    if not path.exists():
        logger.warning("field_map.json not found at %s", path)
        return exact_map, default_map
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning("Failed to load field_map.json: %s", e)
        return exact_map, default_map
    if not isinstance(data, dict):
        return exact_map, default_map
    # Form-specific (exact keys)
    if form_type and form_type in data and isinstance(data[form_type], dict):
        for k, v in data[form_type].items():
            if k.startswith("_"):
                continue
            exact_map[k] = (v or "").strip()
    # Default (normalized keys)
    if "default" in data and isinstance(data["default"], dict):
        for k, v in data["default"].items():
            if k.startswith("_"):
                continue
            n = _normalize_field_name(k)
            if n:
                default_map[n] = (v or "").strip()
    return exact_map, default_map


def resolve_data_key(
    data_key: str,
    opportunity: Any,
    profile: Optional[Any] = None,
    current_user: Optional[Any] = None,
    rfp: Optional[Dict] = None,
) -> str:
    """
    Resolve a data_key (e.g. profile.company_name, opportunity.notice_id) to a string value.
    Returns "" for empty/None; callers can replace with UNMAPPED for display.
    """
    if not data_key:
        return ""
    key = data_key.strip().lower()
    if key == "date.today_us":
        return _today_us()
    if key.startswith("profile."):
        attr = key.replace("profile.", "").strip()
        if not profile:
            return ""
        v = getattr(profile, attr, None)
        if v is None:
            return ""
        if isinstance(v, bool):
            return CHECKBOX_ON if v else CHECKBOX_OFF
        return str(v).strip()
    if key.startswith("opportunity."):
        attr = key.replace("opportunity.", "").strip()
        if not opportunity:
            return ""
        if attr == "primary_contact_name":
            pc = getattr(opportunity, "primary_contact", None)
            if isinstance(pc, dict):
                return (pc.get("name") or "").strip()
            return ""
        if attr == "primary_contact_phone":
            pc = getattr(opportunity, "primary_contact", None)
            if isinstance(pc, dict):
                return (pc.get("phone") or "").strip()
            return ""
        if attr == "primary_contact_email":
            pc = getattr(opportunity, "primary_contact", None)
            if isinstance(pc, dict):
                return (pc.get("email") or "").strip()
            return ""
        v = getattr(opportunity, attr, None)
        if v is None:
            return ""
        return str(v).strip()
    if key.startswith("user."):
        attr = key.replace("user.", "").strip()
        if not current_user:
            return ""
        v = getattr(current_user, attr, None)
        if v is None:
            return ""
        return str(v).strip()
    if key.startswith("rfp.") and rfp:
        attr = key.replace("rfp.", "").strip()
        v = (rfp.get(attr) if isinstance(rfp, dict) else None) or ""
        return str(v).strip() if v else ""
    return ""


def get_data_key_for_field(
    pdf_field_name: str,
    exact_map: Dict[str, str],
    default_map: Dict[str, str],
) -> Optional[str]:
    """Return data_key for this PDF field, or None if unmapped. Tries exact, then normalized, then substring in normalized name."""
    data_key = exact_map.get(pdf_field_name)
    if data_key is not None:
        return data_key if data_key else None
    n = _normalize_field_name(pdf_field_name)
    data_key = default_map.get(n)
    if data_key is not None:
        return data_key if data_key else None
    # Substring: e.g. "companyname" in "page10companyname0"; prefer longest match
    best_key, best_val = None, None
    for key, val in default_map.items():
        if key and val and key in n and (best_key is None or len(key) > len(best_key)):
            best_key, best_val = key, val
    return best_val if best_val else None


def introspect_pdf_fields(pdf_path_or_bytes: Any) -> List[Dict[str, Any]]:
    """
    Step 1: Inspect form fields. Returns list of {name, type, value, tooltip, options, max_length}.
    type: /Tx = text, /Btn = button (checkbox/radio), /Ch = choice (dropdown).
    """
    if PdfReader is None:
        logger.warning("PyPDF2 not available for PDF introspection")
        return []
    try:
        if isinstance(pdf_path_or_bytes, (str, Path)):
            reader = PdfReader(str(pdf_path_or_bytes))
        else:
            reader = PdfReader(io.BytesIO(pdf_path_or_bytes))
    except Exception as e:
        logger.warning("Failed to open PDF for introspection: %s", e)
        return []
    fields = reader.get_fields()
    if not fields:
        logger.info("PDF has no AcroForm fields (may be XFA or flat)")
        return []
    out = []
    for name, field in fields.items():
        if field is None:
            continue
        def _plain(v):
            if v is None:
                return None
            if isinstance(v, (list, tuple)):
                return [_plain(x) for x in v]
            return str(v) if hasattr(v, "__str__") and not isinstance(v, (str, int, float, bool)) else v
        info = {
            "name": name,
            "type": _plain(field.get("/FT")),
            "value": _plain(field.get("/V")),
            "tooltip": _plain(field.get("/TU")),
            "options": _plain(field.get("/Opt")),
            "max_length": _plain(field.get("/MaxLen")),
        }
        out.append(info)
    return out


def build_fill_data(
    field_names: List[str],
    field_types: Optional[Dict[str, str]] = None,
    form_type: str = "default",
    opportunity: Optional[Any] = None,
    profile: Optional[Any] = None,
    current_user: Optional[Any] = None,
    rfp: Optional[Dict] = None,
    known_pdf_fields: Optional[set] = None,
    fail_unknown: bool = False,
) -> Tuple[Dict[str, str], List[str]]:
    """
    Build fill_data dict: PDF field name -> value (string). Uses field_map + resolve_data_key.
    - known_pdf_fields: if set, only include keys that are in this set (validate).
    - fail_unknown: if True, raise ValueError when a requested field is not in known_pdf_fields.
    Returns (fill_data, errors).
    """
    exact_map, default_map = load_field_map(form_type)
    fill_data: Dict[str, str] = {}
    errors: List[str] = []
    field_types = field_types or {}

    for pdf_field in field_names:
        if not pdf_field:
            continue
        if known_pdf_fields is not None and pdf_field not in known_pdf_fields:
            if fail_unknown:
                errors.append(f"UNKNOWN FIELD: {pdf_field}")
            continue
        data_key = get_data_key_for_field(pdf_field, exact_map, default_map)
        if data_key is None:
            fill_data[pdf_field] = UNMAPPED
            continue
        value = resolve_data_key(data_key, opportunity or (), profile, current_user, rfp)
        if value == "":
            value = UNMAPPED
        if field_types.get(pdf_field) == "checkbox":
            fill_data[pdf_field] = CHECKBOX_ON if value and value not in (UNMAPPED, "No", "false", "0", "") else CHECKBOX_OFF
        else:
            fill_data[pdf_field] = value

    if fail_unknown and errors:
        raise ValueError(f"Mapping errors: {errors}")
    return fill_data, errors


def fill_pdf(
    pdf_path_or_bytes: Any,
    fill_data: Dict[str, str],
    flatten: bool = False,
) -> bytes:
    """
    Step 3: Fill PDF form and return bytes. Validates that fill_data keys exist in PDF.
    Checkbox values must be "Yes" or "Off". Text fields get string; use "" for blank.
    """
    if PdfReader is None or PdfWriter is None:
        raise RuntimeError("PyPDF2 is required for PDF form fill")
    if isinstance(pdf_path_or_bytes, (str, Path)):
        reader = PdfReader(str(pdf_path_or_bytes))
    else:
        reader = PdfReader(io.BytesIO(pdf_path_or_bytes))
    fields_obj = reader.get_fields()
    known = set((fields_obj or {}).keys())
    for k in fill_data:
        if k not in known:
            logger.warning("fill_pdf: skipping unknown field %s", k)
    # Only pass known fields to avoid PyPDF2 errors
    safe_fill = {k: (v if v is not None else "") for k, v in fill_data.items() if k in known}

    writer = PdfWriter()
    writer.append(reader)
    try:
        writer.clone_reader_document_root(reader)
    except Exception as e:
        logger.debug("clone_reader_document_root: %s", e)
    for page in writer.pages:
        writer.update_page_form_field_values(page, safe_fill)
    if flatten:
        for page in writer.pages:
            flatten_fn = getattr(page, "flatten", None)
            if callable(flatten_fn):
                try:
                    flatten_fn()
                except Exception as e:
                    logger.warning("flatten page failed: %s", e)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()
