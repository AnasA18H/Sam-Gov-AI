"""
Form autofill: fill AcroForm fields with contractor profile + government data.

Strategy (order enforced):
1. Use reference (backend/data/acroform_reference.json) to match AcroForm fields -> logical keys.
2. For any still unmatched, use section-based matching (e.g. 30a, 17a, 06) from field names.
3. For AcroForm fields still unmapped: one LLM call with REFERENCE + our DATA (user + gov) + the
   unmapped AcroForm list. LLM matches our data to those fields (reference names/sections + common
   sense) and returns JSON: AcroForm field name -> value (from our data only).
4. Government fields: fill only when the current PDF value is empty (do not overwrite).

Data sent to LLM:
- User data: contractor profile (what user fills in Settings).
- Government data only: solicitation_number (notice_id), gov_contact_name (Agency/POC),
  gov_contact_phone, sol_issue_date (issue date), offer_due_date (deadline), issued_by.
  No gov_signature / gov_signed_date.
"""
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..core.config import settings

# Keep prompt under this size (chars) so fallback (e.g. Groq) does not hit 413 / token limit (~12k TPM)
AUTOFILL_PROMPT_MAX_CHARS = 22000


def _autofill_timeout_sec() -> int:
    """Timeout in seconds for each LLM call (primary and fallback). Read from settings at runtime so .env override works."""
    return int(getattr(settings, "AUTOFILL_LLM_TIMEOUT_SEC", 70))

# #region agent log
DEBUG_LOG_PATH = Path(__file__).resolve().parents[2] / ".cursor" / "debug.log"
def _debug_log(message: str, data: dict, hypothesis_id: Optional[str] = None):
    try:
        import json as _json
        payload = {"timestamp": int(time.time() * 1000), "location": "form_autofill", "message": message, "data": data}
        if hypothesis_id:
            payload["hypothesisId"] = hypothesis_id
        DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(_json.dumps(payload) + "\n")
    except Exception:
        pass
# #endregion

logger = logging.getLogger(__name__)

UNMAPPED = "-"

# Placeholder sent to LLM instead of full signature data URL (avoids sending huge base64 in prompt)
PLACEHOLDER_SIGNATURE = "(signature image)"

# Checkbox: frontend expects "No"; PDF write uses "Off"
CHECKBOX_OFF = "Off"
CHECKBOX_ON = "Yes"


def _norm(name: str) -> str:
    """Normalize field name for matching: lowercase, collapse spaces/underscores/dots."""
    if not name:
        return ""
    return re.sub(r"[\s_.\[\]-]+", "", (name or "").lower())


# Section pattern: AcroForm names often have section number + optional subsection (a/b/c), e.g. 05, 06, 07a, 17a, 30a, 30b, 31c.
# Try at start first, then anywhere (e.g. "Block17aAddress" -> "17a").
_SECTION_RE_START = re.compile(r"^(\d+[a-c]?)")
_SECTION_RE_ANY = re.compile(r"(\d+[a-c]?)")


def _extract_section(normalized_name: str) -> Optional[str]:
    """Extract section id from normalized field name (e.g. '30bsignername' -> '30b', '08offerduedate' -> '08', 'block17aaddress' -> '17a')."""
    if not normalized_name:
        return None
    m = _SECTION_RE_START.match(normalized_name)
    if m:
        return m.group(1).lower()
    m = _SECTION_RE_ANY.search(normalized_name)
    return m.group(1).lower() if m else None


def _invoke_llm_with_timeout(llm: Any, prompt: str, timeout_sec: Optional[int] = None) -> Any:
    """Run llm.invoke(prompt) in a thread with a timeout to avoid autofill hanging. Timeout read from settings at runtime."""
    if timeout_sec is None:
        timeout_sec = _autofill_timeout_sec()
    logger.info("autofill: LLM invoke timeout=%s s (from settings)", timeout_sec)
    if len(prompt) > AUTOFILL_PROMPT_MAX_CHARS:
        prompt = prompt[:AUTOFILL_PROMPT_MAX_CHARS] + "\n\n[Truncated for token limit.]"
        logger.info("autofill: prompt truncated to %s chars for token limit", AUTOFILL_PROMPT_MAX_CHARS)
    logger.info("autofill: sending to Claude/LLM prompt len=%s chars. First 2400 chars:\n%s", len(prompt), prompt[:2400])
    try:
        debug_path = DEBUG_LOG_PATH.parent / "autofill_prompt_sent.txt"
        with open(debug_path, "w", encoding="utf-8") as f:
            f.write(prompt)
        logger.info("autofill: full prompt written to %s", debug_path)
    except Exception:
        pass
    with ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(llm.invoke, prompt)
        try:
            return fut.result(timeout=timeout_sec)
        except FuturesTimeoutError:
            logger.warning("Autofill LLM call timed out after %s s (Claude is often slower than Groq for large prompts)", timeout_sec)
            raise


def _parse_llm_json_safe(raw: str) -> Optional[Dict]:
    """Parse JSON from LLM response; on failure try to salvage complete key-value pairs."""
    if not raw or not isinstance(raw, str):
        return None
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```\s*$", "", raw).strip()
    if not raw.startswith("{"):
        m = re.search(r"\{[\s\S]*\}", raw)
        if m:
            raw = m.group(0)
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError as e:
        logger.debug("LLM JSON parse failed (%s), attempting salvage", e)
    # Salvage: extract "key": "value" pairs (value may be truncated without closing quote)
    salvaged: Dict[str, str] = {}
    for m in re.finditer(r'"([^"]+)"\s*:\s*"((?:[^"\\]|\\.)*)"?', raw):
        key, value = m.group(1), m.group(2)
        if key and key.strip():
            salvaged[key.strip()] = value.strip() if value else ""
    return salvaged if salvaged else None


def _today_us() -> str:
    return datetime.now(timezone.utc).strftime("%m/%d/%Y")


# --- Reference: logical key -> known AcroForm names (no LLM) ---

def _get_reference_path() -> Path:
    base = getattr(settings, "PROJECT_ROOT", Path.cwd())
    if not isinstance(base, Path):
        base = Path(base)
    candidates = [
        base / "backend" / "data" / "acroform_reference.json",
        base / "data" / "acroform_reference.json",
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]


def _load_acroform_reference() -> Tuple[Dict[str, str], set, Dict[str, List[Tuple[str, str]]], Dict[str, List[str]]]:
    """Load reference; return (acro_to_logical, gov_keys, section_to_candidates, logical_to_acro_names).
    section_to_candidates: section_id -> [(logical_key, normalized_acro)] for section-based fallback.
    logical_to_acro_names: logical_key -> list of known AcroForm names (for LLM reference).
    """
    path = _get_reference_path()
    acro_to_logical: Dict[str, str] = {}
    gov_keys: set = set()
    section_to_candidates: Dict[str, List[Tuple[str, str]]] = {}
    logical_to_acro_names: Dict[str, List[str]] = {}
    if not path.exists():
        return acro_to_logical, gov_keys, section_to_candidates, logical_to_acro_names
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning("Failed to load acroform_reference.json: %s", e)
        return acro_to_logical, gov_keys, section_to_candidates, logical_to_acro_names
    if not isinstance(data, dict):
        return acro_to_logical, gov_keys, section_to_candidates, logical_to_acro_names
    contractor = data.get("contractor") or {}
    government = data.get("government") or {}
    gov_keys = set(government.keys())

    def add_logical(logical_key: str, names: List[str]) -> None:
        for acro in names or []:
            n = _norm(acro)
            if n:
                acro_to_logical[n] = logical_key
                sec = _extract_section(n)
                if sec:
                    section_to_candidates.setdefault(sec, []).append((logical_key, n))
                logical_to_acro_names.setdefault(logical_key, []).append(acro)

    for logical_key, names in contractor.items():
        if logical_key.startswith("_"):
            continue
        add_logical(logical_key, names)
    for logical_key, names in government.items():
        if logical_key.startswith("_"):
            continue
        add_logical(logical_key, names)
    return acro_to_logical, gov_keys, section_to_candidates, logical_to_acro_names


# --- Value getters: logical key -> value from profile, user, opportunity, rfp ---

def _str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return CHECKBOX_ON if v else CHECKBOX_OFF
    if isinstance(v, (list, tuple)):
        return "; ".join(_str(x) for x in v) if v else ""
    if isinstance(v, dict):
        parts = [f"{k}: {val}" for k, val in v.items() if val is not None and val != ""]
        return "; ".join(parts) if parts else ""
    if isinstance(v, datetime):
        return v.strftime("%m/%d/%Y") if v else ""
    s = str(v).strip()
    return s


def _get_contractor_values(profile: Optional[Any], current_user: Optional[Any]) -> Dict[str, str]:
    """Logical contractor keys -> value. Empty string when not available."""
    out: Dict[str, str] = {}
    if profile:
        out["company_name"] = _str(getattr(profile, "company_name", None))
        out["company_address"] = _str(getattr(profile, "company_address", None))
        out["uei"] = _str(getattr(profile, "uei", None))
        out["cage"] = _str(getattr(profile, "cage", None))
        out["tin"] = _str(getattr(profile, "tin", None))
        out["contract_officer_name"] = _str(getattr(profile, "contract_officer_name", None))
        out["email"] = _str(getattr(profile, "email", None))
        out["phone_number"] = _str(getattr(profile, "phone", None))
        sig = getattr(profile, "digital_signature", None)
        out["signature_of_contractor"] = _str(sig) if sig and isinstance(sig, str) and sig.strip() else ""
        out["signer_title"] = ""  # profile may not have title; optional
    else:
        for k in ("company_name", "company_address", "uei", "cage", "tin", "contract_officer_name", "email", "phone_number", "signature_of_contractor", "signer_title"):
            out[k] = ""
    out["current_date_when_signed"] = _today_us()
    if current_user and not out.get("contract_officer_name"):
        out["contract_officer_name"] = _str(getattr(current_user, "full_name", None))
    if current_user and not out.get("email"):
        out["email"] = _str(getattr(current_user, "email", None))
    return out


def _get_government_values(opportunity: Any, rfp: Optional[Dict]) -> Dict[str, str]:
    """Logical government keys from opportunity / extracted_rfp_info. issued_by = department + delivery/contracting address (SAM, RFP, or CLIN additional_data) + POC."""
    out: Dict[str, str] = {}
    cover = (rfp or {}).get("cover_page") or {}
    if isinstance(cover, dict):
        out["solicitation_number"] = _str(cover.get("solicitation_number"))
        out["sol_issue_date"] = _str(cover.get("solicitation_issue_date") or cover.get("issue_date"))
        out["offer_due_date"] = _str(cover.get("offer_due_date"))
    pc = getattr(opportunity, "primary_contact", None) if opportunity else None
    if isinstance(pc, dict):
        out["gov_contact_name"] = _str(pc.get("name"))
        out["gov_contact_phone"] = _str(pc.get("phone") or pc.get("email"))
    if opportunity:
        out["solicitation_number"] = out.get("solicitation_number") or _str(getattr(opportunity, "notice_id", None))
        ac = getattr(opportunity, "alternative_contact", None)
        if isinstance(ac, dict) and not out.get("gov_contact_name"):
            out["gov_contact_name"] = _str(ac.get("name"))
            out["gov_contact_phone"] = out.get("gov_contact_phone") or _str(ac.get("phone") or ac.get("email"))
        deadlines = list(getattr(opportunity, "deadlines", None) or [])
        if deadlines and hasattr(deadlines[0], "due_date"):
            deadlines = sorted(deadlines, key=lambda d: getattr(d, "due_date") or datetime.min)
            d0 = deadlines[0]
            out["offer_due_date"] = out.get("offer_due_date") or _str(getattr(d0, "due_date", None))
            out["offer_due_date_local_time"] = _str(getattr(d0, "due_time", None))
        # issued_by = department + delivery/contracting office address + POC name/contact
        dept = _str(cover.get("issuing_office") or cover.get("issuing_agency") if isinstance(cover, dict) else None) or _str(getattr(opportunity, "agency", None))
        addr = _str(getattr(opportunity, "contracting_office_address", None)).strip()
        if not addr and rfp and isinstance(rfp, dict):
            ds = rfp.get("delivery_schedule")
            if isinstance(ds, dict):
                addr = _str(ds.get("ship_to_address")).strip()
            if not addr and isinstance(cover, dict):
                addr = _str(cover.get("delivery_address") or cover.get("contracting_office_address") or cover.get("place_of_delivery")).strip()
        # Delivery address is often in CLIN additional_data (extracted from solicitation)
        if not addr:
            clins = list(getattr(opportunity, "clins", None) or [])
            for clin in clins:
                ad = getattr(clin, "additional_data", None) if hasattr(clin, "additional_data") else None
                if isinstance(ad, dict):
                    addr = _str(ad.get("delivery_address")).strip()
                    if addr:
                        break
        poc_name = out.get("gov_contact_name", "").strip()
        poc_contact = out.get("gov_contact_phone", "").strip()
        issued_parts = [p for p in [dept, addr] if p]
        if poc_name or poc_contact:
            issued_parts.append((poc_name + (" " + poc_contact if poc_contact else "")).strip())
        out["issued_by"] = "\n".join(issued_parts) if issued_parts else ""
        # issued_by_code = government/issuing office CAGE (NOT contractor CAGE). From RFP cover if present.
        out["issued_by_code"] = ""
        if isinstance(cover, dict):
            out["issued_by_code"] = _str(
                cover.get("issuing_office_cage") or cover.get("gov_cage") or cover.get("issued_by_code")
            ).strip()
    for k in ("issued_by", "issued_by_code", "contracting_officer", "gov_signed_date", "gov_signature"):
        out[k] = out.get(k) or ""
    return out


# --- Map PDF field names -> logical key (reference first, then section fallback, then LLM for missing) ---

def _section_match_score(field_norm: str, ref_acro_norm: str) -> int:
    """Score how well field name matches reference acro name (higher = better). Prefer substring containment then length overlap."""
    if not field_norm or not ref_acro_norm:
        return 0
    # Prefer ref contained in field (e.g. field "30bsignername" vs ref "30bsignername") or vice versa
    if ref_acro_norm in field_norm or field_norm in ref_acro_norm:
        return max(len(ref_acro_norm), len(field_norm))
    # Count matching character runs / overlap
    overlap = 0
    for i in range(min(len(field_norm), len(ref_acro_norm))):
        if field_norm[i] == ref_acro_norm[i]:
            overlap += 1
        else:
            break
    return overlap


def _map_fields_with_reference(
    field_names: List[str],
    acro_to_logical: Dict[str, str],
    section_to_candidates: Optional[Dict[str, List[Tuple[str, str]]]] = None,
) -> Tuple[Dict[str, str], int, int]:
    """Map each PDF field name -> logical_key using reference (exact match, then section-based fallback).
    Returns (field_to_logical, reference_exact_count, section_fallback_count)."""
    result: Dict[str, str] = {}
    ref_count = 0
    section_count = 0
    section_to_candidates = section_to_candidates or {}
    for name in field_names:
        if not name:
            continue
        n = _norm(name)
        logical = acro_to_logical.get(n)
        if logical:
            result[name] = logical
            ref_count += 1
            continue
        # Section fallback: extract section (e.g. 30b, 17a, 08) and match when names differ slightly
        sec = _extract_section(n)
        if not sec or sec not in section_to_candidates:
            continue
        candidates = section_to_candidates[sec]
        if len(candidates) == 1:
            result[name] = candidates[0][0]
            section_count += 1
            logger.debug("Autofill section fallback: %r -> %s (section %s)", name, candidates[0][0], sec)
        else:
            best_logical = None
            best_score = -1
            for logical_key, ref_acro_norm in candidates:
                score = _section_match_score(n, ref_acro_norm)
                if score > best_score:
                    best_score = score
                    best_logical = logical_key
            if best_logical and best_score > 0:
                result[name] = best_logical
                section_count += 1
                logger.debug("Autofill section fallback (multi): %r -> %s (section %s, score %s)", name, best_logical, sec, best_score)
    return result, ref_count, section_count


def _read_reference_md_for_llm() -> str:
    """Load ExamplePDF/README.md as reference text for LLM."""
    base = getattr(settings, "PROJECT_ROOT", Path.cwd())
    if not isinstance(base, Path):
        base = Path(base)
    for candidate in [base / "ExamplePDF" / "README.md", base / "backend" / ".." / "ExamplePDF" / "README.md"]:
        if candidate.exists():
            try:
                return candidate.read_text(encoding="utf-8")
            except Exception as e:
                logger.debug("Could not read reference README: %s", e)
    return ""


def _format_reference_mapping_for_llm(logical_to_acro_names: Dict[str, List[str]], gov_keys: set) -> str:
    """Format logical key -> known AcroForm names for the LLM prompt. Section = leading digits + a/b/c (e.g. 05, 17a, 30b)."""
    lines = [
        "REFERENCE MAPPING (match AcroForm field names to these logical keys; section = leading digits + optional a/b/c):",
        "",
    ]
    for logical in sorted(logical_to_acro_names.keys()):
        names = logical_to_acro_names[logical]
        kind = "government" if logical in gov_keys else "contractor"
        lines.append(f"- {logical} ({kind}) -> known AcroForm names: {', '.join(names)}")
    lines.append("")
    lines.append("Use this mapping first: compare each AcroForm field name to the known names and sections above. Then use section numbers (05, 06, 07a, 08, 09, 17a, 30a, 30b, 30c, 31b, etc.) and common sense to match when names differ slightly.")
    return "\n".join(lines)


# Logical key labels for LLM (same order as our value dicts)
CONTRACTOR_LABELS = [
    "Company name", "Company address", "UEI", "CAGE", "TIN",
    "Contract officer name", "Email", "Phone number",
    "Signature of contractor", "current date when signed signature field",
]
CONTRACTOR_KEYS = [
    "company_name", "company_address", "uei", "cage", "tin",
    "contract_officer_name", "email", "phone_number",
    "signature_of_contractor", "current_date_when_signed",
]
GOV_LABELS = [
    "solicitation number", "government contact name", "government contact phone",
    "solicitation issue date", "offer due date", "offer due date local time",
    "issued by", "issued by code (gov CAGE)", "contracting officer name", "government signed date",
]
GOV_KEYS = [
    "solicitation_number", "gov_contact_name", "gov_contact_phone",
    "sol_issue_date", "offer_due_date", "offer_due_date_local_time",
    "issued_by", "issued_by_code", "contracting_officer", "gov_signed_date",
]
# Government keys we send to LLM (exclude signature/signed date/contracting officer)
GOV_KEYS_FOR_LLM = [
    "solicitation_number", "gov_contact_name", "gov_contact_phone",
    "sol_issue_date", "offer_due_date", "offer_due_date_local_time", "issued_by", "issued_by_code",
]
# Generic key meanings only; actual values for this solicitation are in the DATA section below.
GOV_SEMANTICS_FOR_LLM = """
Government keys (actual values for this solicitation are in GOVERNMENT DATA below):
- solicitation_number: Notice ID from SAM.gov
- gov_contact_name: Point of contact name from SAM.gov (e.g. Kwamaine Clark)
- gov_contact_phone: Contact number or email of that POC
- sol_issue_date: Date the solicitation was issued (not the deadline)
- offer_due_date: Deadline from extracted deadlines
- offer_due_date_local_time: Local time for that deadline if available
- issued_by: Combined block = (1) Issuing department e.g. DEPT OF DEFENSE, DEPT OF THE ARMY + (2) Contracting/delivery office address + (3) POC name and contact. Use the full issued_by value when filling Block 9 / 09issuedby.
- issued_by_code: Government/issuing office CAGE code for Block 9 (09issuedbycode). This is the AGENCY's CAGE, NOT the contractor's. Do NOT use the contractor CAGE (profile.cage / 17acontractorcode) here. Use only if provided in GOVERNMENT DATA.
"""


def _is_signature_data_url(v: str) -> bool:
    """True if value looks like a signature image (data URL or very long blob). Used to avoid sending base64 to LLM."""
    if not v or not isinstance(v, str):
        return False
    s = v.strip()
    return s.lower().startswith("data:") or len(s) > 500


def _build_data_section_for_llm(contractor_values: Dict[str, str], government_values: Dict[str, str]) -> str:
    """Build DATA section: user (contractor) data + this solicitation's government data (actual values, not examples).
    Signature image (data URL) is replaced with a short placeholder so we don't send huge base64 to the LLM."""
    lines = ["USER DATA (from profile / settings form):"]
    for k, v in contractor_values.items():
        if v and str(v).strip() and str(v).strip() != UNMAPPED:
            if k == "signature_of_contractor" and _is_signature_data_url(v):
                lines.append(f"  {k}: {PLACEHOLDER_SIGNATURE}")
            else:
                lines.append(f"  {k}: {v}")
    lines.append("GOVERNMENT DATA (this solicitation — use these values when filling):")
    gov_lines = []
    for k in GOV_KEYS_FOR_LLM:
        v = government_values.get(k, "")
        if v and str(v).strip():
            gov_lines.append(f"  {k}: {v}")
    if gov_lines:
        lines.extend(gov_lines)
    else:
        lines.append("  (No government data extracted for this solicitation.)")
    return "\n".join(lines)


def _ask_llm_match_data_to_fields(
    llm: Any,
    field_names: List[str],
    field_types: Optional[Dict[str, str]],
    field_tooltips: Optional[Dict[str, str]],
    reference_text: str,
    reference_mapping_str: str,
    contractor_values: Dict[str, str],
    government_values: Dict[str, str],
) -> Dict[str, str]:
    """
    Single LLM task: we send our DATA (user + gov) and the list of AcroForm fields. LLM matches
    our data to those fields using the REFERENCE MAPPING (logical key -> known AcroForm names),
    section numbers, and common sense.
    Returns JSON { "exact AcroForm field name": "value from our DATA" }. Only matched fields.
    """
    if not llm or not field_names:
        return {}
    field_list_parts = []
    for name in field_names:
        if not name:
            continue
        t = (field_types or {}).get(name, "text")
        tu = (field_tooltips or {}).get(name, "")
        field_list_parts.append(f"  - {name} (type: {t})" + (f" (tooltip: {tu})" if tu else ""))
    field_list = "\n".join(field_list_parts)
    if len(field_list) > 6000:
        field_list = field_list[:6000] + "\n... (more fields omitted)"
    data_section = _build_data_section_for_llm(contractor_values, government_values)
    if len(data_section) > 1200:
        data_section = data_section[:1200] + "\n... (data truncated)"
    ref_cap = min(3000, max(0, AUTOFILL_PROMPT_MAX_CHARS - len(field_list) - len(data_section) - len(reference_mapping_str) - 600))
    reference_snippet = reference_text[:ref_cap] if ref_cap else reference_text[:2000]

    prompt = f"""You are a government form assistant. Match OUR DATA to the given PDF AcroForm fields.

HOW TO MATCH (use all three):
1. REFERENCE MAPPING below: each logical key (e.g. company_name, solicitation_number) maps to known AcroForm names. Compare each AcroForm field name from the list to these known names; if it matches or is very similar, use the value from OUR DATA for that logical key.
2. SECTION: AcroForm names often include a section (leading digits + optional a/b/c), e.g. 05, 06, 07a, 08, 09, 17a, 30a, 30b, 30c, 31b. Use section to infer meaning when the name is close (e.g. block 30b = signer name/title, block 17a = contractor address/phone, block 05 = solicitation number, block 08 = offer due date).
3. COMMON SENSE: company name/address/CAGE/phone go in contractor blocks; solicitation number, due date, issued by, gov contact go in government blocks. Match by meaning when names differ.

{reference_mapping_str}

ADDITIONAL REFERENCE (form descriptions, if available):
{reference_snippet}

{GOV_SEMANTICS_FOR_LLM}

OUR DATA (use ONLY these values when filling; keys = logical keys from the reference above):
{data_section}

ACROFORM FIELDS TO MATCH (from the PDF; output exact field names as keys):
{field_list}

TASK: For each AcroForm field that corresponds to a logical key in the REFERENCE MAPPING (by name, section, or common sense), output that AcroForm field name and the value from OUR DATA for that key. Return valid JSON only: keys = exact AcroForm field names from the list above, values = string from OUR DATA. For signature use "(signature image)". Omit fields you cannot match. Dates: MM/DD/YYYY. Checkboxes: "Yes" or "No". Output only the JSON object, no markdown."""

    try:
        timeout_sec = _autofill_timeout_sec()
        response = _invoke_llm_with_timeout(llm, prompt, timeout_sec)
        raw = response.content if hasattr(response, "content") else str(response)
        if isinstance(raw, list):
            raw = "".join(
                (b.get("text") or b.get("content") or "") if isinstance(b, dict) else str(b)
                for b in raw
            ).strip()
        else:
            raw = (raw if isinstance(raw, str) else str(raw)).strip()
        if not raw:
            return {}
        data = _parse_llm_json_safe(raw)
        if not isinstance(data, dict):
            return {}
        result: Dict[str, str] = {}
        known_names = set(field_names)
        for k, v in data.items():
            if k not in known_names or v is None:
                continue
            s = _str(v).strip()
            if s and s != UNMAPPED:
                result[k] = s
        return result
    except (FuturesTimeoutError, Exception) as e:
        logger.warning("LLM match-data-to-fields failed: %s", e)
        return {}


# --- Build fill_data: field_name -> value (gov only if empty) ---

def _build_fill_data(
    field_names: List[str],
    field_to_logical: Dict[str, str],
    contractor_values: Dict[str, str],
    government_values: Dict[str, str],
    gov_keys: set,
    pdf_field_values: Optional[Dict[str, Any]],
    field_types: Optional[Dict[str, str]],
) -> Dict[str, str]:
    """
    For each field_name that is mapped to a logical_key (in reference), set value.
    - Government keys: only set if pdf_field_values is None or current value is empty.
    - Contractor keys: always set (overwrite) with our value or "".
    - Fields not in reference (no logical): do not add to result (do not modify).
    """
    result: Dict[str, str] = {}
    for name in field_names:
        if not name:
            continue
        logical = field_to_logical.get(name)
        if not logical:
            # Not in reference: do not add — caller must not modify these fields
            continue
        if logical in gov_keys:
            current = None
            if pdf_field_values and name in pdf_field_values:
                v = pdf_field_values[name]
                current = (v if isinstance(v, str) else str(v)).strip() if v is not None else ""
            if current:
                result[name] = current
                continue
        all_vals = {**contractor_values, **government_values}
        value = all_vals.get(logical, "")
        # Contractor (and gov when empty): use "" when empty, never UNMAPPED, so we never overwrite with "-"
        if field_types and field_types.get(name) == "checkbox":
            value = CHECKBOX_ON if value and value not in (UNMAPPED, "No", "false", "0", "") else CHECKBOX_OFF
        result[name] = value
    return result


# Special: 17acontractoraddress (and similar) often hold "Company name + Address". Always use combined.
def _apply_combined_address(fill_data: Dict[str, str], field_to_logical: Dict[str, str], contractor_values: Dict[str, str]) -> None:
    for field_name, logical in field_to_logical.items():
        if logical != "company_address" and logical != "company_name":
            continue
        name_val = contractor_values.get("company_name", "")
        addr_val = contractor_values.get("company_address", "")
        combined = (name_val + "\n" + addr_val).strip() if name_val else addr_val
        if combined:
            fill_data[field_name] = combined
        elif field_name in fill_data and fill_data[field_name] in (UNMAPPED, ""):
            fill_data[field_name] = addr_val or ""


def get_autofill_values(
    opportunity: Any,
    field_names: List[str],
    field_types: Optional[Dict[str, str]] = None,
    llm: Optional[Any] = None,
    fallback_llm: Optional[Any] = None,
    current_user: Optional[Any] = None,
    profile: Optional[Any] = None,
    pdf_field_values: Optional[Dict[str, Any]] = None,
    pdf_field_tooltips: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """
    Map form fields to values using reference-based mapping; use LLM only for missing mappings.

    Returns only fields that appear in acroform_reference.json (contractor or government). Fields
    not in the reference are never returned, so they are never modified. Contractor fields are
    always overwritten (with our value or ""); government fields only when the PDF value is empty.

    - pdf_field_values: optional current value per field (from introspect). Gov fields are filled only if current is empty.
    - pdf_field_tooltips: optional tooltip per field (helps LLM when used).
    """
    # #region agent log
    t0 = time.perf_counter()
    _debug_log("get_autofill_values entry", {"field_count": len(field_names), "has_llm": llm is not None, "has_fallback": fallback_llm is not None}, "B")
    # #endregion
    rfp = getattr(opportunity, "extracted_rfp_info", None)
    if isinstance(rfp, str):
        try:
            rfp = json.loads(rfp) if rfp else None
        except Exception:
            rfp = None

    ref_path = _get_reference_path()
    acro_to_logical, gov_keys, section_to_candidates, logical_to_acro_names = _load_acroform_reference()
    logger.info(
        "autofill: reference path=%s exists=%s keys_loaded=%s",
        ref_path, ref_path.exists(), len(acro_to_logical),
    )
    if field_names:
        sample = field_names[:10]
        logger.info("autofill: PDF field name sample (first 10): %s", sample)
    if len(acro_to_logical) == 0 and field_names:
        logger.warning(
            "autofill: no reference keys loaded (wrong path or empty JSON). PDF has %s fields; add names to backend/data/acroform_reference.json to match.",
            len(field_names),
        )
    contractor_values = _get_contractor_values(profile, current_user)
    government_values = _get_government_values(opportunity, rfp)

    # 1) Map PDF field name -> logical key using reference (exact then section fallback)
    field_to_logical, ref_count, section_count = _map_fields_with_reference(field_names, acro_to_logical, section_to_candidates)
    # #region agent log
    t1 = time.perf_counter()
    _debug_log("after reference+map", {"elapsed_ms": round((t1 - t0) * 1000), "ref": ref_count, "section": section_count, "mapped": len(field_to_logical)}, "B")
    logger.info(
        "autofill: reference+section done in %.0fms — reference_exact=%s section_fallback=%s total_mapped=%s",
        (t1 - t0) * 1000, ref_count, section_count, len(field_to_logical),
    )
    if ref_count == 0 and section_count == 0 and field_names:
        logger.warning("autofill: no reference match for any PDF field; LLM will be used for all unmapped fields if available.")
    # #endregion

    # 2) Build fill_data from reference + section mapping
    fill_data = _build_fill_data(
        field_names,
        field_to_logical,
        contractor_values,
        government_values,
        gov_keys,
        pdf_field_values,
        field_types,
    )
    _apply_combined_address(fill_data, field_to_logical, contractor_values)

    result = dict(fill_data)
    # Do not add UNMAPPED for fields not in reference — only return reference fields so non-reference are never modified.

    if field_types:
        for name in list(result):
            if field_types.get(name) == "checkbox" and result.get(name) == CHECKBOX_OFF:
                result[name] = "No"

    # 3) For AcroForm fields still unmapped: one LLM call. Send any field that has no value yet, so LLM can
    # suggest matches when PDF uses different names than the reference. Exclude only: gov fields we already
    # filled (in reference and already have value in PDF).
    def _should_send_to_llm(
        n: str,
        ftl: Dict[str, str],
        gk: set,
        res: Dict[str, str],
        pdf_vals: Optional[Dict[str, Any]],
    ) -> bool:
        if not n:
            return False
        if (res.get(n) or "").strip() not in ("", UNMAPPED):
            return False
        # If we know this is a gov field and PDF already has a value, don't send (we won't overwrite).
        if n in ftl and ftl[n] in gk and pdf_vals and n in pdf_vals:
            cur = pdf_vals[n]
            cur_str = (cur if isinstance(cur, str) else str(cur)).strip() if cur is not None else ""
            if cur_str:
                return False
        return True

    unmapped_field_names = [
        n for n in field_names
        if _should_send_to_llm(n, field_to_logical, gov_keys, result, pdf_field_values)
    ]
    llm_filled_count = 0
    if unmapped_field_names and (llm or fallback_llm):
        # #region agent log
        _debug_log("LLM match-data-to-fields start", {"unmapped_count": len(unmapped_field_names)}, "C")
        logger.info("autofill: LLM match-data-to-fields start unmapped=%s", len(unmapped_field_names))
        # #endregion
        t2 = time.perf_counter()
        reference_text = _read_reference_md_for_llm()
        reference_mapping_str = _format_reference_mapping_for_llm(logical_to_acro_names, gov_keys)
        llm_fill: Dict[str, str] = {}
        for label, candidate_llm in [("primary", llm), ("fallback", fallback_llm)]:
            if not candidate_llm:
                continue
            timeout_sec = _autofill_timeout_sec()
            logger.info("autofill: trying %s LLM for match-data-to-fields (timeout=%ss)", label, timeout_sec)
            llm_fill = _ask_llm_match_data_to_fields(
                candidate_llm,
                unmapped_field_names,
                field_types,
                pdf_field_tooltips,
                reference_text,
                reference_mapping_str,
                contractor_values,
                government_values,
            )
            if llm_fill:
                for name, value in llm_fill.items():
                    if not name or not value:
                        continue
                    current = (result.get(name) or "").strip()
                    if current not in ("", UNMAPPED):
                        continue
                    # LLM returns placeholder for signature; use real signature from profile
                    if _str(value).strip() == PLACEHOLDER_SIGNATURE:
                        value = contractor_values.get("signature_of_contractor", "") or ""
                    if value:
                        result[name] = value
                        llm_filled_count += 1
                logger.info("autofill: %s LLM succeeded, matched %s fields", label, len(llm_fill))
                break
            logger.info("autofill: %s LLM returned no matches (timeout or error), will try fallback if available", label)
        # #region agent log
        t3 = time.perf_counter()
        _debug_log("LLM match-data-to-fields done", {"elapsed_ms": round((t3 - t2) * 1000)}, "C")
        logger.info("autofill: LLM match-data-to-fields done elapsed=%.0fms", (t3 - t2) * 1000)
        # #endregion

    # #region agent log
    t_end = time.perf_counter()
    filled_total = ref_count + section_count + llm_filled_count
    unmapped_total = len([n for n in field_names if n and (result.get(n) or "").strip() in ("", UNMAPPED)])
    _debug_log("get_autofill_values exit", {"total_elapsed_ms": round((t_end - t0) * 1000)}, "E")
    logger.info("autofill: get_autofill_values total elapsed=%.0fms", (t_end - t0) * 1000)
    logger.info(
        "autofill: FILL SUMMARY — reference=%s section=%s llm=%s total_filled=%s unmapped=%s",
        ref_count, section_count, llm_filled_count, filled_total, unmapped_total,
    )
    # #endregion
    return result
