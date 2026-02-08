"""
Build external lookup URLs for CLINs: NSN, CAGE, part number, Digi-Key, SAM.gov.
Uses the multi-source strategy: military/NSN sites + commercial (Digi-Key) + SAM.gov.
All links open in the user's browser; no scraping or API calls to third parties here.
"""
import re
from typing import List, Dict, Any, Optional
from urllib.parse import quote_plus

# Base URLs (no trailing slash)
# Primary: NSN-Now (part #); fallback: NSN Lookup
NSN_NOW_SEARCH = "https://www.nsn-now.com/search/search.aspx"
NSN_LOOKUP_SEARCH = "https://www.nsnlookup.com/search"
GOV_CAGE_SEARCH = "https://govcagecodes.com/"
CAGE_DLA_MIL = "https://cage.dla.mil/Search"
DIGIKEY_SEARCH = "https://www.digikey.com/en/products"
ISO_GROUP_NSN = "https://www.iso-group.com/nsn-search/"
SAM_ENTITY_SEARCH = "https://sam.gov/search/"


def _extract_cage_codes(text: Optional[str]) -> List[str]:
    """Extract 5-character CAGE codes from text (e.g. manufacturer_name or description)."""
    if not text:
        return []
    # CAGE is 5 alphanumeric; often appears after "CAGE", "-", or in "0VGU1 5388-F12 12436"
    pattern = r"(?:CAGE|code)\s*[:\s]*([0-9A-Z]{5})\b|\b([0-9A-Z]{5})\b(?=\s|,|$|/)"
    matches = re.findall(pattern, text, re.IGNORECASE)
    codes = []
    for m in matches:
        code = (m[0] or m[1] or "").strip().upper()
        if code and len(code) == 5 and code not in codes:
            codes.append(code)
    # Also catch standalone 5-char alphanumeric that look like CAGE (e.g. 0VGU1, 12436)
    for part in re.split(r"[\s,;/]+", text):
        part = part.strip().upper()
        if len(part) == 5 and re.match(r"^[0-9A-Z]{5}$", part) and part not in codes:
            codes.append(part)
    return codes[:5]  # cap at 5 to avoid noise


def _part_number_for_search(part_number: Optional[str]) -> Optional[str]:
    """Use first plausible part number segment (skip CAGE-only)."""
    if not part_number or not part_number.strip():
        return None
    # If mixed "0VGU1 5388-F12 6012315-001", prefer segments that look like part numbers (digits, hyphen)
    parts = re.split(r"\s+", part_number.strip())
    for p in parts:
        p = p.strip()
        if not p or len(p) < 3:
            continue
        # Skip 5-char CAGE-only
        if len(p) == 5 and re.match(r"^[0-9A-Z]{5}$", p):
            continue
        return p
    return part_number.strip() if part_number else None


def get_clin_lookup_links(clin: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Given a CLIN (dict with part_number, base_item_number, manufacturer_name, product_name, additional_data),
    return a list of { "source", "label", "url" } for external lookups.
    """
    links: List[Dict[str, str]] = []
    base_item = (clin.get("base_item_number") or "").strip()
    part_number = (clin.get("part_number") or "").strip()
    manufacturer = (clin.get("manufacturer_name") or "").strip()
    product_name = (clin.get("product_name") or "").strip()
    additional = clin.get("additional_data") or {}
    drawing = (additional.get("drawing_number") if isinstance(additional, dict) else None) or ""
    desc = (clin.get("product_description") or "").strip()

    # NSN / part # (military): NSN-Now primary, NSN Lookup fallback
    nsn_query = base_item or part_number or product_name or ""
    if nsn_query:
        q = nsn_query.replace(" ", "+")[:80]
        links.append({
            "source": "nsnnow",
            "label": "NSN-Now (part #)",
            "url": f"{NSN_NOW_SEARCH}?q={quote_plus(q)}",
        })
        links.append({
            "source": "nsnlookup",
            "label": "NSN Lookup (fallback)",
            "url": f"{NSN_LOOKUP_SEARCH}?q={quote_plus(q)}",
        })
        links.append({
            "source": "isogroup",
            "label": "ISO Group NSN Search",
            "url": f"{ISO_GROUP_NSN}?q={quote_plus(q)}",
        })

    # CAGE lookups (any CAGE we can find)
    cage_codes = _extract_cage_codes(manufacturer) or _extract_cage_codes(desc)
    for code in cage_codes[:2]:  # max 2 CAGE links
        links.append({
            "source": "govcage",
            "label": f"CAGE {code} (GovCAGECodes)",
            "url": f"{GOV_CAGE_SEARCH}?cage={quote_plus(code)}",
        })
        links.append({
            "source": "cagedla",
            "label": f"CAGE {code} (DLA Official)",
            "url": f"{CAGE_DLA_MIL}?q={quote_plus(code)}",
        })
    if not cage_codes and (manufacturer or product_name):
        search_term = (manufacturer or product_name or "").strip()[:60]
        if search_term:
            links.append({
                "source": "govcage",
                "label": "CAGE / Company (GovCAGECodes)",
                "url": f"{GOV_CAGE_SEARCH}?q={quote_plus(search_term)}",
            })

    # Digi-Key (commercial part number)
    part_for_digi = _part_number_for_search(part_number) or (part_number[:60] if part_number else None)
    if part_for_digi:
        links.append({
            "source": "digikey",
            "label": "Digi-Key (part number)",
            "url": f"{DIGIKEY_SEARCH}?keywords={quote_plus(part_for_digi)}",
        })

    # SAM.gov entity search (manufacturer or CAGE)
    sam_query = manufacturer or " ".join(cage_codes) or product_name or ""
    if sam_query:
        sam_q = sam_query.strip()[:80]
        links.append({
            "source": "samgov",
            "label": "SAM.gov Entity Search",
            "url": f"{SAM_ENTITY_SEARCH}?query={quote_plus(sam_q)}",
        })

    # Deduplicate by URL
    seen = set()
    unique = []
    for link in links:
        u = link.get("url") or ""
        if u and u not in seen:
            seen.add(u)
            unique.append(link)
    return unique
