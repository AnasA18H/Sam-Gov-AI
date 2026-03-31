"""
Tavily web search: find manufacturer and dealers per CLIN (runs after CLIN extraction).
Extracts: manufacturer official website + sales contact email; up to 8 dealers with name, URL, email, pricing.

Missing emails are filled once per opportunity: copy across CLINs by site key (hostname, no path; www stripped),
then merged Tavily snippets, then one HTTP fetch per unique site (https://{host}/), then one batched LLM pass
over merged snippets for stragglers. All Tavily params and query generation are config-driven or LLM-generated.
"""
import copy
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from pydantic import SecretStr

from ..core.config import settings

logger = logging.getLogger(__name__)

# Legacy: previously when CLINs > this, we grouped by manufacturer and ran Tavily once per group,
# then copied the same manufacturer_research and dealer_research to all CLINs in the group.
# That incorrectly assigned dealers found for one product to other products (same manufacturer).
# We now always run Tavily once per CLIN so each CLIN gets dealers actually found for that product.
# Set to a high value to effectively disable grouping (no copying of dealers).
TAVILY_GROUP_CLINS_THRESHOLD = 999
# Reuse Tavily result by unique (manufacturer, product): one run per product, same result for same product.
TAVILY_REUSE_BY_PRODUCT = True
TAVILY_PARALLEL_MAX_WORKERS = 4

try:
    from langchain_anthropic import ChatAnthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ChatAnthropic = None  # type: ignore[misc, assignment]
    ANTHROPIC_AVAILABLE = False
try:
    from langchain_groq import ChatGroq
    GROQ_AVAILABLE = True
except ImportError:
    ChatGroq = None  # type: ignore[misc, assignment]
    GROQ_AVAILABLE = False


def _get_tavily_params() -> Dict[str, Any]:
    """Tavily API params from settings (generic; no hardcoding)."""
    params: Dict[str, Any] = {
        "search_depth": getattr(settings, "TAVILY_SEARCH_DEPTH", "advanced"),
        "max_results": getattr(settings, "TAVILY_MAX_RESULTS", 12),
        "include_answer": getattr(settings, "TAVILY_INCLUDE_ANSWER", True),
    }
    domains = getattr(settings, "TAVILY_INCLUDE_DOMAINS", "") or ""
    if domains.strip():
        params["include_domains"] = [d.strip() for d in domains.split(",") if d.strip()]
    time_range = getattr(settings, "TAVILY_TIME_RANGE", "") or ""
    if time_range.strip():
        params["time_range"] = time_range.strip()
    return params


def _generate_search_queries_for_clin(clin: Dict[str, Any]) -> List[str]:
    """
    Generate Tavily search queries from CLIN in a generic way: use LLM to produce a list of queries
    aimed at finding manufacturer website, sales contact email, and authorized dealers with contact info.
    Fallback: build a minimal list from non-empty CLIN fields (no fixed phrase templates).
    """
    max_queries = getattr(settings, "TAVILY_MAX_QUERIES_PER_CLIN", 8)
    parts = [
        (clin.get("manufacturer_name") or "").strip(),
        (clin.get("product_name") or "").strip(),
        (clin.get("part_number") or "").strip(),
        (clin.get("product_description") or "").strip()[:80],
    ]
    context = " ".join(p for p in parts if p).strip()
    if not context:
        return []

    result: List[str] = []
    llm = None
    if ANTHROPIC_AVAILABLE and ChatAnthropic is not None and getattr(settings, "ANTHROPIC_API_KEY", None):
        try:
            llm = ChatAnthropic(  # type: ignore[call-arg, argument]
                model=getattr(settings, "ANTHROPIC_MODEL", "claude-3-sonnet-20240229"),  # type: ignore[misc]
                temperature=0,
                api_key=SecretStr(settings.ANTHROPIC_API_KEY),
                timeout=60,
            )
        except Exception as e:
            logger.debug("Tavily query gen: Claude init failed: %s", e)
    if not llm and GROQ_AVAILABLE and ChatGroq is not None and getattr(settings, "GROQ_API_KEY", None):
        try:
            llm = ChatGroq(  # type: ignore[call-arg]
                model=getattr(settings, "GROQ_MODEL", "llama-3.3-70b-versatile"),
                temperature=0,
                api_key=SecretStr(settings.GROQ_API_KEY),
            )
        except Exception as e:
            logger.debug("Tavily query gen: Groq init failed: %s", e)

    if llm:
        prompt = f"""You are generating web search queries to find: (1) the manufacturer's official website and sales/contact email, (2) authorized dealers or distributors with company name, website, and contact email for quote requests.

CLIN context (use only the non-empty fields):
- manufacturer_name: {clin.get('manufacturer_name') or ''}
- product_name: {clin.get('product_name') or ''}
- part_number: {clin.get('part_number') or ''}
- product_description: (first 80 chars) {context[:80]}

Output a JSON array of 4 to {max_queries} search query strings, each a single line suitable for a web search. Vary phrasing (e.g. "contact email", "sales", "quote", "authorized dealers", "distributors", "where to buy"). No explanation, only the JSON array."""
        try:
            response = llm.invoke(prompt)
            raw = response.content if hasattr(response, "content") else str(response)
            if isinstance(raw, list):
                text_parts = [
                    block.get("text", "") if isinstance(block, dict) else str(block)
                    for block in raw
                ]
                text = "".join(text_parts).strip()
            else:
                text = str(raw).strip()
            if text:
                if text.startswith("```"):
                    text = re.sub(r"^```(?:json)?\s*", "", text)
                    text = re.sub(r"\s*```\s*$", "", text)
                arr = json.loads(text)
                if isinstance(arr, list):
                    result = [str(q).strip() for q in arr if q and str(q).strip()][:max_queries]
        except (json.JSONDecodeError, Exception) as e:
            logger.debug("Tavily query gen LLM fallback: %s", e)

    if not result:
        # Fallback: generic queries from context (no fixed templates)
        if context:
            result.append(context)
        if len(context) > 20 and f"{context} contact email sales quote" not in result:
            result.append(f"{context} contact email sales quote")
        if len(result) < 3 and (clin.get("manufacturer_name") or clin.get("product_name")):
            extra = f"{clin.get('manufacturer_name') or ''} {clin.get('product_name') or ''} authorized dealers distributors".strip()
            if extra and extra not in result:
                result.append(extra)
        result = list(dict.fromkeys(result))[:max_queries]
    return result


def _search_with_tavily_client(api_key: str, query: str) -> Dict[str, Any]:
    """Run one Tavily search via TavilyClient. All params from settings."""
    from tavily import TavilyClient

    params = _get_tavily_params()
    client = TavilyClient(api_key=api_key)
    kwargs = {
        "search_depth": params.get("search_depth", "advanced"),
        "max_results": params.get("max_results", 12),
        "include_answer": params.get("include_answer", True),
    }
    if params.get("include_domains"):
        kwargs["include_domains"] = params["include_domains"]
    if params.get("time_range"):
        kwargs["time_range"] = params["time_range"]
    try:
        response = client.search(query, **kwargs)
    except TypeError:
        kwargs["query"] = query
        response = client.search(**kwargs)
    out: Dict[str, Any] = {"query": query, "results": [], "answer": None}
    if isinstance(response, dict):
        out["results"] = response.get("results", [])
        out["answer"] = response.get("answer")
    else:
        results = getattr(response, "results", None) or []
        if results:
            out["results"] = [
                {
                    "title": getattr(r, "title", None) or (r.get("title") if isinstance(r, dict) else None),
                    "url": getattr(r, "url", None) or (r.get("url") if isinstance(r, dict) else None),
                    "content": getattr(r, "content", None) or (r.get("content") if isinstance(r, dict) else None),
                    "score": getattr(r, "score", None) or (r.get("score") if isinstance(r, dict) else None),
                }
                for r in results
            ]
        answer = getattr(response, "answer", None)
        if answer:
            out["answer"] = answer
    return out


def run_tavily_for_clin(api_key: str, clin: Dict[str, Any]) -> Dict[str, Any]:
    """Run Tavily search(es) for one CLIN; return combined result dict (clin, queries, searches)."""
    queries = _generate_search_queries_for_clin(clin)
    if not queries:
        return {
            "clin": {k: v for k, v in clin.items() if v is not None},
            "queries": [],
            "searches": [],
            "summary": "No search queries (missing product/manufacturer)",
        }
    searches: List[Dict[str, Any]] = []
    for q in queries:
        one = _search_with_tavily_client(api_key, q)
        searches.append(one)
    params = _get_tavily_params()
    return {
        "clin": {k: v for k, v in clin.items() if v is not None},
        "queries": queries,
        "searches": searches,
        "search_depth": params.get("search_depth", "advanced"),
        "max_results": params.get("max_results", 12),
        "include_answer": params.get("include_answer", True),
    }


def _is_valid_email(s: Optional[str]) -> bool:
    """Return True only if s looks like a real email (not a URL, not Cloudflare obfuscation)."""
    if not s or not isinstance(s, str):
        return False
    s = s.strip()
    if len(s) < 6 or len(s) > 254:
        return False
    if "@" not in s or " " in s:
        return False
    # Reject obfuscation/URLs
    if "/cdn-cgi/" in s or s.startswith("/") or "http" in s.lower() or "mailto:" in s.lower():
        return False
    # Basic format: local@domain
    parts = s.split("@")
    if len(parts) != 2 or not parts[0] or not parts[1] or "." not in parts[1]:
        return False
    return True


def _normalize_email(s: Optional[str]) -> Optional[str]:
    """Return the string if it's a valid email, else None."""
    if not s or not isinstance(s, str):
        return None
    s = (s.strip() or "").strip()
    return s if _is_valid_email(s) else None


# Regex to find email addresses in text (whole-page or snippet)
_EMAIL_PATTERN = re.compile(
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
)

# Domains/local parts we treat as placeholders (not real contact emails)
_EMAIL_BLACKLIST_LOCAL = frozenset(
    {"example", "test", "user", "email", "admin", "webmaster", "postmaster", "noreply", "no-reply", "donotreply", "do-not-reply", "null", "undefined"}
)
_EMAIL_BLACKLIST_DOMAIN = frozenset(
    {"example.com", "example.org", "test.com", "domain.com", "email.com", "sentry.io", "wixpress.com"}
)


def _extract_emails_from_text(text: str) -> List[str]:
    """Extract all email-like strings from text; return deduplicated list (may include some noise)."""
    if not text or not isinstance(text, str):
        return []
    found = set()
    for m in _EMAIL_PATTERN.finditer(text):
        email = m.group(0).strip()
        if len(email) < 6 or len(email) > 254:
            continue
        if "/cdn-cgi/" in email or "http" in email.lower() or "mailto:" in email.lower():
            continue
        if "@" not in email or email.count("@") != 1:
            continue
        local, domain = email.split("@", 1)
        if not local or not domain or "." not in domain:
            continue
        domain_lower = domain.lower()
        local_lower = local.lower()
        if local_lower in _EMAIL_BLACKLIST_LOCAL or domain_lower in _EMAIL_BLACKLIST_DOMAIN:
            continue
        if domain_lower.endswith(".png") or domain_lower.endswith(".jpg") or domain_lower.endswith(".gif"):
            continue
        found.add(email)
    return list(found)


def _pick_best_contact_email(emails: List[str], domain_hint: Optional[str] = None) -> Optional[str]:
    """Choose the best contact email from a list (prefer sales/contact/info, then domain match)."""
    if not emails:
        return None
    domain_hint_lower = (domain_hint or "").lower()
    preferred_local = ("sales", "contact", "info", "quotes", "inquiry", "enquir")
    best = None
    best_score = -1
    for e in emails:
        local = (e.split("@")[0] or "").lower()
        dom = (e.split("@")[-1] or "").lower() if "@" in e else ""
        score = 0
        if domain_hint_lower and domain_hint_lower in dom:
            score += 10
        for p in preferred_local:
            if p in local or local.startswith(p + ".") or local.startswith(p + "_"):
                score += 5
                break
        if local in ("info", "sales", "contact"):
            score += 3
        if score > best_score:
            best_score = score
            best = e
    return best or emails[0]


def _domain_from_url(url: Optional[str]) -> Optional[str]:
    """Extract hostname (domain) from URL for matching."""
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    for p in ("https://", "http://"):
        if url.lower().startswith(p):
            url = url[len(p):]
            break
    if "/" in url:
        url = url.split("/")[0]
    return url.lower() if url else None


def _site_key(url: Optional[str]) -> Optional[str]:
    """
    Normalize a website URL to a single key for deduplication: hostname only (no path),
    with leading www. stripped so https://www.abc.com/sales and https://abc.com/about match.
    """
    host = _domain_from_url(url)
    if not host:
        return None
    if host.startswith("www."):
        host = host[4:]
    return host.lower()


def _is_same_or_subdomain(result_domain: str, target_domain: str) -> bool:
    """True if result_domain equals target_domain or is its subdomain."""
    rd = (result_domain or "").lower().strip()
    td = (target_domain or "").lower().strip()
    if not rd or not td:
        return False
    return rd == td or rd.endswith("." + td)


def _is_aggregator_domain(domain: Optional[str]) -> bool:
    """Known directory/email-harvest domains that should not be treated as official manufacturer websites."""
    if not domain:
        return False
    d = domain.lower()
    blocked = (
        "rocketreach.co",
        "zoominfo.com",
        "contactout.com",
        "hunter.io",
        "theorg.com",
        "signalhire.com",
        "lusha.com",
        "apollo.io",
    )
    return any(d == b or d.endswith("." + b) for b in blocked)


def _looks_like_dealer_listing(url: str, title: str, content: str) -> bool:
    """Heuristic: page likely contains authorized dealer/distributor listings."""
    text = f"{url} {title} {content}".lower()
    keys = (
        "dealer",
        "distributor",
        "where to buy",
        "locator",
        "regional contact",
        "sales contact",
        "authorized",
        "channel partner",
        "reseller",
    )
    return any(k in text for k in keys)


def _email_domain(email: Optional[str]) -> str:
    if not email or "@" not in email:
        return ""
    return email.split("@", 1)[1].strip().lower()


def _is_bad_dealer_source(url: str, title: str, content: str) -> bool:
    """
    Exclude obvious non-dealer sources (news/media/wiki/pdfs/owner portals/attachments pages).
    """
    text = f"{url} {title} {content}".lower()
    bad_markers = (
        "wikipedia.org",
        "/wiki/",
        "[pdf]",
        ".pdf",
        "press",
        "media",
        "newsroom",
        "owner portal",
        "owner site",
        "attachment b",
        "attachment ",
        "blog",
        "linkedin.com",
        "facebook.com",
        "x.com/",
        "twitter.com/",
        "youtube.com/",
        "instagram.com/",
    )
    return any(m in text for m in bad_markers)


def _dealer_candidate_score(c: Dict[str, Any], mfr_domain: str = "") -> int:
    """
    Score candidate legitimacy for dealer/distributor row quality.
    Higher = better. Negative means likely noise.
    """
    url = (c.get("url") or "").lower()
    title = (c.get("title") or "").lower()
    content = (c.get("content") or "").lower()
    email = (c.get("email") or "").strip().lower()
    c_domain = (_domain_from_url(c.get("url")) or "").lower()
    email_dom = _email_domain(email)

    score = 0
    text = f"{url} {title} {content}"
    if any(k in text for k in ("dealer", "distributor", "authorized", "where to buy", "reseller", "quote", "sales")):
        score += 6
    if _looks_like_dealer_listing(url, title, content):
        score += 4
    if email:
        score += 5
    if email and email_dom:
        if c_domain and (email_dom == c_domain or email_dom.endswith("." + c_domain) or c_domain.endswith("." + email_dom)):
            score += 4
        elif mfr_domain and (email_dom == mfr_domain or email_dom.endswith("." + mfr_domain)):
            # Manufacturer direct-sales mail (allowed, but lower than dealer-domain match)
            score += 1
        else:
            score -= 4
    if _is_bad_dealer_source(url, title, content):
        score -= 10
    if c.get("is_aggregator"):
        score -= 8
    return score


def _normalize_company_name(name: Optional[str]) -> str:
    """Normalize company/page title into a comparable key for dedup."""
    if not name:
        return ""
    s = name.lower().strip()
    s = re.sub(r"\s*\|.*$", "", s)  # Drop " | Site" suffixes
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    # Remove common page words that create duplicates of same company
    s = re.sub(r"\b(contact|contacts|about|careers|locations|service|parts|distributor|locator|sales)\b", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _extract_emails_from_tavily_content(tavily_result: Dict[str, Any], website_url: Optional[str]) -> Optional[str]:
    """Scan all Tavily result snippets for URLs matching website_url's domain; extract emails and return best."""
    if not website_url:
        return None
    target_domain = _domain_from_url(website_url)
    if not target_domain:
        return None
    combined = []
    for search in tavily_result.get("searches") or []:
        for r in search.get("results") or []:
            url = (r.get("url") or "").strip()
            result_domain = _domain_from_url(url)
            if result_domain and _is_same_or_subdomain(result_domain, target_domain):
                content = (r.get("content") or "").strip()
                if content:
                    combined.append(content)
    if not combined:
        return None
    text = "\n".join(combined)
    emails = _extract_emails_from_text(text)
    return _pick_best_contact_email(emails, target_domain) if emails else None


# Browser-like User-Agent to reduce blocks and 403s
_FETCH_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Shorter timeouts for faster failure (sites that block or are slow)
_FETCH_TIMEOUT_BASE = 6
_FETCH_TIMEOUT_PATH = 5

# Only the most likely contact paths (trying many paths is slow and often 403)
_CONTACT_PATHS = ("/contact", "/contact-us", "/contact.html")


def _fetch_page_text_internal(
    url: str, timeout_sec: int = _FETCH_TIMEOUT_BASE, log_prefix: str = "", retry_on_error: bool = True
) -> Tuple[Optional[str], Optional[int]]:
    """
    Fetch URL and return (plain_text, None) on success, (None, status_code) on HTTP error, (None, None) on other failure.
    Used to skip remaining path tries when host returns 403.
    """
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError:
        logger.warning("[Tavily fill] %sNavigation failed (missing requests or bs4): skipping fetch", log_prefix)
        return (None, None)
    if not url.startswith(("http://", "https://")):
        url = "https://" + url.lstrip("/")

    def _do_fetch() -> Tuple[Optional[str], Optional[int]]:
        try:
            r = requests.get(
                url,
                timeout=timeout_sec,
                headers={
                    "User-Agent": _FETCH_USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "en-US,en;q=0.9",
                },
                allow_redirects=True,
            )
            if r.status_code == 404:
                logger.debug("[Tavily fill] %sPath not found (404) url=%s", log_prefix, url[:80])
                return (None, 404)
            if r.status_code == 403:
                logger.info("[Tavily fill] %sNavigation 403 Forbidden url=%s", log_prefix, url[:80])
                return (None, 403)
            r.raise_for_status()
            html = r.text
            soup = BeautifulSoup(html, "html.parser")
            mailto_emails: List[str] = []
            for a in soup.find_all("a", href=True):
                href = (str(a.get("href", "")) or "").strip()
                if href.lower().startswith("mailto:"):
                    raw = href[7:].split("?")[0].strip()
                    if raw and "@" in raw and _normalize_email(raw):
                        mailto_emails.append(raw)
            for tag in soup(["script", "style"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
            if mailto_emails:
                text = (text or "") + "\n" + "\n".join(mailto_emails)
            return (text or None, None)
        except requests.exceptions.HTTPError as e:
            if e.response is not None:
                code = e.response.status_code
                if code == 403:
                    logger.info("[Tavily fill] %sNavigation 403 Forbidden url=%s", log_prefix, url[:80])
                    return (None, 403)
                if code == 404:
                    return (None, 404)
                return (None, code)
            return (None, None)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            logger.info("[Tavily fill] %sNavigation timeout/connection url=%s reason=%s", log_prefix, url[:80], e)
            return (None, None)

    try:
        text, status = _do_fetch()
        if text is not None:
            return (text, None)
        if status == 403:
            return (None, 403)
        if status is not None:
            return (None, status)
    except Exception as e:
        if retry_on_error and ("500" in str(e) or "timed out" in str(e).lower() or "Timeout" in str(e)):
            import time
            time.sleep(1)
            try:
                return _do_fetch()
            except Exception:
                pass
        logger.info("[Tavily fill] %sNavigation FAILED url=%s reason=%s", log_prefix, url[:80], e)
    return (None, None)


def _fetch_page_text(url: str, timeout_sec: int = _FETCH_TIMEOUT_BASE, log_prefix: str = "", retry_on_error: bool = True) -> Optional[str]:
    """Fetch URL and return plain text. Returns None on failure (backward-compat wrapper)."""
    text, _ = _fetch_page_text_internal(url, timeout_sec, log_prefix, retry_on_error)
    return text


def _extract_emails_from_page(url: str, timeout_sec: int = _FETCH_TIMEOUT_BASE, log_prefix: str = "") -> List[str]:
    """Fetch URL and up to 3 contact paths; return all found emails. Stops path tries if host returns 403."""
    base = url.rstrip("/")
    path_timeout = _FETCH_TIMEOUT_PATH
    # Try base URL first
    text, status = _fetch_page_text_internal(url, timeout_sec, log_prefix=log_prefix)
    if status == 403:
        # Host blocks requests; skip trying paths (they will 403 too)
        logger.info("[Tavily fill] %sNavigation FAILED (no emails extracted) url=%s", log_prefix, url[:80])
        return []
    if text:
        emails = _extract_emails_from_text(text)
        if emails:
            logger.info("[Tavily fill] %sNavigation PASSED url=%s emails_found=%s", log_prefix, url[:80], len(emails))
            return emails
    for path in _CONTACT_PATHS:
        u = base + path
        text, status = _fetch_page_text_internal(u, timeout_sec=path_timeout, log_prefix=log_prefix)
        if status == 403:
            break
        if text:
            emails = _extract_emails_from_text(text)
            if emails:
                logger.info("[Tavily fill] %sNavigation PASSED url=%s emails_found=%s", log_prefix, u[:80], len(emails))
                return emails
    logger.info("[Tavily fill] %sNavigation FAILED (no emails extracted) url=%s", log_prefix, url[:80])
    return []


def _merge_tavily_searches_from_all_data(all_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Concatenate all Tavily search payloads so snippet-based email extraction sees every CLIN's results."""
    merged: List[Dict[str, Any]] = []
    for d in all_data:
        merged.extend(d.get("searches") or [])
    return merged


def _normalize_mfr_research_payload(raw: Any) -> List[Dict[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, dict):
        return [raw]
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    return []


def _normalize_dealer_research_payload(raw: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    return [x for x in raw if isinstance(x, dict)]


def _build_research_stub_from_clin_payload(clin: Dict[str, Any]) -> Dict[str, Any]:
    """Minimal Tavily-shaped dict from DB/payload (no searches) for skip-Tavily decisions and propagation."""
    return {
        "clin": clin,
        "manufacturer_research": _normalize_mfr_research_payload(clin.get("manufacturer_research")),
        "dealer_research": _normalize_dealer_research_payload(clin.get("dealer_research")),
    }


def _missing_email_rate_for_stub(stub: Dict[str, Any]) -> Optional[float]:
    """
    After cross-CLIN propagation: fraction of website rows (mfr + dealer with URL) that still lack email.
    Returns None if there are no website rows (Tavily needed to discover structure).
    """
    total = 0
    missing = 0
    mfr_list = stub.get("manufacturer_research")
    if isinstance(mfr_list, dict):
        mfr_list = [mfr_list]
    elif not isinstance(mfr_list, list):
        mfr_list = []
    for m in mfr_list:
        if not isinstance(m, dict):
            continue
        if not _site_key(m.get("official_website")):
            continue
        total += 1
        if not _normalize_email(m.get("sales_contact_email")):
            missing += 1
    for dealer in stub.get("dealer_research") or []:
        if not isinstance(dealer, dict):
            continue
        if not _site_key(dealer.get("website_url")):
            continue
        total += 1
        if not _normalize_email(dealer.get("sales_contact_email")):
            missing += 1
    if total == 0:
        return None
    return missing / total


def _propagate_cross_clin_emails_by_domain(all_data: List[Dict[str, Any]]) -> None:
    """If any row has an email for site key S, copy it to other rows in the opportunity that share S but lack email."""
    domain_to_emails: Dict[str, List[str]] = defaultdict(list)
    for d in all_data:
        mfr_list = d.get("manufacturer_research")
        if isinstance(mfr_list, dict):
            mfr_list = [mfr_list]
        elif not isinstance(mfr_list, list):
            mfr_list = []
        for m in mfr_list:
            if not isinstance(m, dict):
                continue
            em = _normalize_email(m.get("sales_contact_email"))
            sk = _site_key(m.get("official_website"))
            if sk and em:
                domain_to_emails[sk].append(em)
        for dealer in d.get("dealer_research") or []:
            if not isinstance(dealer, dict):
                continue
            em = _normalize_email(dealer.get("sales_contact_email"))
            sk = _site_key(dealer.get("website_url"))
            if sk and em:
                domain_to_emails[sk].append(em)

    domain_best: Dict[str, str] = {}
    for sk, emails in domain_to_emails.items():
        uniq = list(dict.fromkeys(emails))
        best = _pick_best_contact_email(uniq, sk)
        if best:
            domain_best[sk] = best

    for d in all_data:
        clin_id = (d.get("clin") or {}).get("id", "?")
        mfr_list = d.get("manufacturer_research")
        if isinstance(mfr_list, dict):
            mfr_iter = [mfr_list]
        elif isinstance(mfr_list, list):
            mfr_iter = mfr_list
        else:
            mfr_iter = []
        for m in mfr_iter:
            if not isinstance(m, dict) or m.get("sales_contact_email"):
                continue
            sk = _site_key(m.get("official_website"))
            if sk and sk in domain_best:
                m["sales_contact_email"] = domain_best[sk]
                logger.info(
                    "[Tavily fill] CLIN %s: manufacturer cross-CLIN copy (site=%s) -> %s",
                    clin_id, sk, domain_best[sk][:50],
                )
        for dealer in d.get("dealer_research") or []:
            if not isinstance(dealer, dict) or dealer.get("sales_contact_email"):
                continue
            sk = _site_key(dealer.get("website_url"))
            if sk and sk in domain_best:
                dealer["sales_contact_email"] = domain_best[sk]
                logger.info(
                    "[Tavily fill] CLIN %s: dealer '%s' cross-CLIN copy (site=%s) -> %s",
                    clin_id, (dealer.get("company_name") or "dealer")[:40], sk, domain_best[sk][:50],
                )


def _collect_site_keys_needing_email(all_data: List[Dict[str, Any]]) -> Dict[str, str]:
    """site_key -> representative URL (any row) for logging and Tavily domain match."""
    need: Dict[str, str] = {}
    for d in all_data:
        mfr_list = d.get("manufacturer_research")
        if isinstance(mfr_list, dict):
            mfr_list = [mfr_list]
        elif not isinstance(mfr_list, list):
            mfr_list = []
        for m in mfr_list:
            if not isinstance(m, dict) or m.get("sales_contact_email"):
                continue
            url = (m.get("official_website") or "").strip()
            sk = _site_key(url)
            if sk and url:
                if not url.startswith(("http://", "https://")):
                    url = "https://" + url.lstrip("/")
                need[sk] = url
        for dealer in d.get("dealer_research") or []:
            if not isinstance(dealer, dict) or dealer.get("sales_contact_email"):
                continue
            url = (dealer.get("website_url") or "").strip()
            sk = _site_key(url)
            if sk and url:
                if not url.startswith(("http://", "https://")):
                    url = "https://" + url.lstrip("/")
                need[sk] = url
    return need


def _apply_email_to_site_key(all_data: List[Dict[str, Any]], site_key: str, email: str) -> None:
    em = _normalize_email(email)
    if not em:
        return
    for d in all_data:
        mfr_list = d.get("manufacturer_research")
        if isinstance(mfr_list, dict):
            mfr_list = [mfr_list]
        elif not isinstance(mfr_list, list):
            mfr_list = []
        for m in mfr_list:
            if not isinstance(m, dict) or m.get("sales_contact_email"):
                continue
            if _site_key(m.get("official_website")) == site_key:
                m["sales_contact_email"] = em
        for dealer in d.get("dealer_research") or []:
            if not isinstance(dealer, dict) or dealer.get("sales_contact_email"):
                continue
            if _site_key(dealer.get("website_url")) == site_key:
                dealer["sales_contact_email"] = em


def _build_merged_tavily_context_for_opportunity(all_data: List[Dict[str, Any]]) -> str:
    parts: List[str] = []
    for d in all_data:
        clin = d.get("clin") or {}
        cid = clin.get("id", "?")
        parts.append(f"=== Tavily block (lead CLIN id={cid}) ===\n")
        parts.append(_build_tavily_context_for_llm(d))
    return "\n".join(parts)


def _chunk_aggregate_parse_batches(
    items: List[Dict[str, Any]], merged_context: str, max_chars: int
) -> List[Tuple[List[Dict[str, Any]], str]]:
    """Split items into batches that fit with context (context truncated once, repeated per batch)."""
    ctx_budget = max(8000, int(max_chars * 0.62))
    ctx = merged_context
    if len(ctx) > ctx_budget:
        ctx = ctx[:ctx_budget] + "\n...[truncated]...\n"
    overhead = 2500
    item_budget = max_chars - len(ctx) - overhead
    if item_budget < 500:
        item_budget = max_chars // 4
    batches: List[Tuple[List[Dict[str, Any]], str]] = []
    current: List[Dict[str, Any]] = []
    cur_sz = 0
    for it in items:
        js = len(json.dumps(it, default=str))
        if current and cur_sz + js > item_budget:
            batches.append((current, ctx))
            current = []
            cur_sz = 0
        current.append(it)
        cur_sz += js
    if current:
        batches.append((current, ctx))
    return batches


def _llm_map_item_ids_to_emails(batch_items: List[Dict[str, Any]], context: str, batch_idx: int) -> Dict[str, Optional[str]]:
    """Return { item_id: email or None } from one LLM call."""
    llm = None
    if ANTHROPIC_AVAILABLE and ChatAnthropic is not None and getattr(settings, "ANTHROPIC_API_KEY", None):
        try:
            llm = ChatAnthropic(  # type: ignore[call-arg, argument]
                model=getattr(settings, "ANTHROPIC_MODEL", "claude-3-sonnet-20240229"),  # type: ignore[misc]
                temperature=0,
                api_key=SecretStr(settings.ANTHROPIC_API_KEY),
                timeout=120,
            )
        except Exception as e:
            logger.debug("Tavily aggregate parse: Claude init failed: %s", e)
    if not llm and GROQ_AVAILABLE and ChatGroq is not None and getattr(settings, "GROQ_API_KEY", None):
        try:
            llm = ChatGroq(  # type: ignore[call-arg]
                model=getattr(settings, "GROQ_MODEL", "llama-3.3-70b-versatile"),
                temperature=0,
                api_key=SecretStr(settings.GROQ_API_KEY),
            )
        except Exception as e:
            logger.debug("Tavily aggregate parse: Groq init failed: %s", e)
    if not llm:
        return {}

    prompt = f"""From the web search snippets below, find the best sales or contact email for quote requests for each item.
Match email to the company/website when possible (same domain as website_url preferred). If no plausible email exists in the text, use null.

Items (JSON):
{json.dumps(batch_items, indent=1)}

Web search context:
---
{context}
---

Output ONLY a valid JSON object mapping each item "id" to one email string or null, e.g. {{"mfr_0_0":"sales@example.com","dealer_0_1":null}}
No markdown, no explanation."""
    try:
        response = llm.invoke(prompt)
        raw = response.content if hasattr(response, "content") else str(response)
        if isinstance(raw, list):
            text = "".join(
                (block.get("text", "") if isinstance(block, dict) else str(block))
                for block in raw
            )
        else:
            text = str(raw) if raw else ""
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```\s*$", "", text)
        out = json.loads(text)
        if not isinstance(out, dict):
            return {}
        return {str(k): (v if v is None or isinstance(v, str) else None) for k, v in out.items()}
    except Exception as e:
        logger.warning("Tavily aggregate parse batch %s failed: %s", batch_idx, e)
        return {}


def _apply_parsed_email_by_item_id(all_data: List[Dict[str, Any]], item_id: str, email: str) -> None:
    parts = item_id.split("_", 2)
    if len(parts) < 3:
        return
    kind, di_s, idx_s = parts[0], parts[1], parts[2]
    try:
        di = int(di_s)
        idx = int(idx_s)
    except ValueError:
        return
    if di < 0 or di >= len(all_data):
        return
    d = all_data[di]
    clin_id = (d.get("clin") or {}).get("id", "?")
    if kind == "mfr":
        ml = d.get("manufacturer_research")
        if isinstance(ml, dict):
            ml = [ml]
        elif not isinstance(ml, list):
            return
        if 0 <= idx < len(ml) and isinstance(ml[idx], dict) and not ml[idx].get("sales_contact_email"):
            ml[idx]["sales_contact_email"] = email
            logger.info(
                "[Tavily fill] CLIN %s: aggregate AI parse filled manufacturer -> %s (id=%s)",
                clin_id, email[:50], item_id,
            )
    elif kind == "dealer":
        dl = d.get("dealer_research") or []
        if 0 <= idx < len(dl) and isinstance(dl[idx], dict) and not dl[idx].get("sales_contact_email"):
            dl[idx]["sales_contact_email"] = email
            logger.info(
                "[Tavily fill] CLIN %s: aggregate AI parse filled dealer -> %s (id=%s)",
                clin_id, email[:50], item_id,
            )


def _ai_batch_parse_missing_emails_opportunity(all_data: List[Dict[str, Any]]) -> None:
    """Single (or batched) LLM pass over merged Tavily text for rows still missing email after snippet+fetch."""
    items: List[Dict[str, Any]] = []
    for di, d in enumerate(all_data):
        clin_id = (d.get("clin") or {}).get("id", "?")
        mfr_list = d.get("manufacturer_research")
        if isinstance(mfr_list, dict):
            mfr_list = [mfr_list]
        elif not isinstance(mfr_list, list):
            mfr_list = []
        for mi, m in enumerate(mfr_list):
            if not isinstance(m, dict) or m.get("sales_contact_email"):
                continue
            if not (m.get("official_website") or "").strip():
                continue
            items.append({
                "id": f"mfr_{di}_{mi}",
                "kind": "manufacturer",
                "clin_id": clin_id,
                "name": (str(m.get("name") or ""))[:120],
                "website_url": m.get("official_website"),
            })
        for ei, dealer in enumerate(d.get("dealer_research") or []):
            if not isinstance(dealer, dict) or dealer.get("sales_contact_email"):
                continue
            if not (dealer.get("website_url") or "").strip():
                continue
            items.append({
                "id": f"dealer_{di}_{ei}",
                "kind": "dealer",
                "clin_id": clin_id,
                "name": (str(dealer.get("company_name") or ""))[:120],
                "website_url": dealer.get("website_url"),
            })
    if not items:
        return

    merged_context = _build_merged_tavily_context_for_opportunity(all_data)
    max_chars = getattr(settings, "TAVILY_AGGREGATE_AI_MAX_CHARS", 45000)
    batches = _chunk_aggregate_parse_batches(items, merged_context, max_chars)
    logger.info(
        "[Tavily fill] opportunity: aggregate AI email parse batches=%s items=%s",
        len(batches), len(items),
    )
    for bi, (batch_items, ctx_slice) in enumerate(batches):
        result_map = _llm_map_item_ids_to_emails(batch_items, ctx_slice, bi)
        for it in batch_items:
            iid = it.get("id")
            if not iid:
                continue
            raw = result_map.get(str(iid))
            em = _normalize_email(raw) if raw else None
            if em:
                _apply_parsed_email_by_item_id(all_data, str(iid), em)


def _fill_missing_emails_opportunity_level(all_data: List[Dict[str, Any]]) -> None:
    """
    Per unique site key (hostname, no path; www stripped): fill missing emails once, then copy to all CLIN rows.
    Phase 1: merged Tavily snippets across the opportunity. Phase 2: one HTTP fetch per site to https://{site}/ (+ contact paths).
    """
    if not all_data:
        return

    _propagate_cross_clin_emails_by_domain(all_data)

    merged_tavily = {"searches": _merge_tavily_searches_from_all_data(all_data)}
    domains_need = _collect_site_keys_needing_email(all_data)
    logger.info("[Tavily fill] opportunity: phase 1 (Tavily snippets) unique sites=%s", len(domains_need))

    for site_key, rep_url in domains_need.items():
        email = _extract_emails_from_tavily_content(merged_tavily, rep_url)
        ne = _normalize_email(email) if email else None
        if ne:
            _apply_email_to_site_key(all_data, site_key, ne)
            logger.info("[Tavily fill] opportunity: site=%s email from content PASSED -> %s", site_key, ne[:50])
        else:
            logger.info("[Tavily fill] opportunity: site=%s email from content FAILED (no match in snippets)", site_key)

    domains_need = _collect_site_keys_needing_email(all_data)
    logger.info("[Tavily fill] opportunity: phase 2 (fetch) unique sites=%s", len(domains_need))
    if not domains_need:
        logger.info("[Tavily fill] opportunity: finding missing emails complete")
        return

    max_workers = min(3, len(domains_need))
    max_workers = getattr(settings, "TAVILY_FILL_FETCH_MAX_WORKERS", max_workers) or 1

    def _fetch_one_site(site_key: str) -> Tuple[str, Optional[str]]:
        base_url = f"https://{site_key}/"
        log_prefix = f"site {site_key} "
        emails = _extract_emails_from_page(base_url, log_prefix=log_prefix)
        email = _pick_best_contact_email(emails, site_key)
        return (site_key, _normalize_email(email) if email else None)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_fetch_one_site, sk): sk for sk in domains_need.keys()}
        for future in as_completed(futures):
            try:
                site_key, email = future.result()
                if email:
                    _apply_email_to_site_key(all_data, site_key, email)
                    logger.info("[Tavily fill] opportunity: site=%s email from fetch PASSED -> %s", site_key, email[:50])
                else:
                    logger.info(
                        "[Tavily fill] opportunity: site=%s email from fetch FAILED (navigation returned no usable email)",
                        site_key,
                    )
            except Exception as e:
                logger.warning("[Tavily fill] opportunity: fetch failed: %s", e)

    logger.info("[Tavily fill] opportunity: finding missing emails complete")


def _fill_missing_emails(tavily_data: Dict[str, Any]) -> None:
    """Backward-compatible: one CLIN/group payload as a single-element opportunity run."""
    _fill_missing_emails_opportunity_level([tavily_data])


def _extract_manufacturer_and_dealers_from_tavily_regex(tavily_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract manufacturer and dealers from Tavily results using regex/patterns only (no LLM).
    Each search result becomes a candidate: title/domain -> company name, url -> website, emails from content.
    Manufacturer: CLIN manufacturer_name + result that best matches (url/title); dealers: all results with emails preferred.
    """
    empty = {"manufacturer_research": [], "dealer_research": []}
    clin_info = tavily_result.get("clin") or {}
    mfr_name = (clin_info.get("manufacturer_name") or "").strip()
    searches = tavily_result.get("searches") or []
    if not searches:
        return empty

    # Collect all results with (url, title, content)
    candidates: List[Dict[str, Any]] = []
    seen_urls: set = set()
    for search in searches:
        for r in search.get("results") or []:
            url = (r.get("url") or "").strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            title = (r.get("title") or "").strip()
            content = (r.get("content") or "").strip()
            emails = _extract_emails_from_text(content) if content else []
            best_email = _pick_best_contact_email(emails, _domain_from_url(url)) if emails else None
            domain = _domain_from_url(url) or ""
            company_name = title if title and len(title) < 120 else (domain or "Unknown")
            candidates.append({
                "url": url,
                "title": title,
                "domain": domain,
                "content": content,
                "email": best_email,
                "emails": emails,
                "is_aggregator": _is_aggregator_domain(domain),
            })

    # Manufacturer: prefer non-aggregator official-looking domains that match manufacturer name.
    manufacturer_research: List[Dict[str, Any]] = []
    mfr_lower = mfr_name.lower() if mfr_name else ""
    mfr_tokens = [t for t in re.findall(r"[a-z0-9]+", mfr_lower) if len(t) >= 3]
    mfr_candidate = None
    best_score = -10_000
    for c in candidates:
        url_l = (c.get("url") or "").lower()
        title_l = (c.get("title") or "").lower()
        domain_l = (c.get("domain") or "").lower()
        score = 0
        if c.get("is_aggregator"):
            score -= 200
        if mfr_lower and (mfr_lower in url_l or mfr_lower in title_l):
            score += 120
        if mfr_tokens and any(tok in domain_l for tok in mfr_tokens):
            score += 60
        if "/contact" in url_l or "/about" in url_l:
            score += 10
        if score > best_score:
            best_score = score
            mfr_candidate = c
    if not mfr_candidate and candidates:
        # Fallback to first non-aggregator candidate, then first.
        mfr_candidate = next((c for c in candidates if not c.get("is_aggregator")), candidates[0])
    if mfr_candidate:
        manufacturer_research.append({
            "name": mfr_name or None,
            "official_website": mfr_candidate["url"] if mfr_candidate["url"].startswith(("http://", "https://")) else "https://" + mfr_candidate["url"].lstrip("/"),
            "sales_contact_email": _normalize_email(mfr_candidate.get("email")),
        })

    # Dealers: strict filtering for legit dealer/distributor pages with quote-usable emails.
    dealer_research: List[Dict[str, Any]] = []
    mfr_url = (mfr_candidate or {}).get("url", "")
    mfr_domain = _domain_from_url(mfr_url) or ""
    with_email = [c for c in candidates if c.get("email")]
    # Contact email is required for quote outreach; only include candidates with email.
    ordered_candidates = sorted(
        with_email,
        key=lambda c: _dealer_candidate_score(c, mfr_domain=mfr_domain),
        reverse=True,
    )
    for c in ordered_candidates:
        if len(dealer_research) >= 8:
            break
        c_domain = _domain_from_url(c.get("url")) or ""
        c_is_mfr_domain = bool(mfr_domain and _is_same_or_subdomain(c_domain, mfr_domain))
        c_is_listing = _looks_like_dealer_listing(c.get("url") or "", c.get("title") or "", c.get("content") or "")
        score = _dealer_candidate_score(c, mfr_domain=mfr_domain)
        if score < 3:
            continue
        if _is_bad_dealer_source(c.get("url") or "", c.get("title") or "", c.get("content") or ""):
            continue
        if c.get("is_aggregator"):
            # Skip directories/email-harvest pages as dealers.
            continue
        if c["url"] == mfr_url and len(manufacturer_research) > 0:
            # Include manufacturer as dealer if they sell direct (same entry with email)
            if c.get("email") and _normalize_email(c.get("email")):
                dealer_research.append({
                    "company_name": mfr_name or c.get("title") or c.get("domain") or "Manufacturer",
                    "website_url": c["url"] if c["url"].startswith(("http://", "https://")) else "https://" + c["url"].lstrip("/"),
                    "sales_contact_email": _normalize_email(c["email"]),
                    "retail_pricing": None,
                })
            continue
        if c_is_mfr_domain and not c_is_listing:
            # Manufacturer pages like product lines/careers/contact are not dealer companies.
            continue
        normalized_email = _normalize_email(c.get("email"))
        if not normalized_email:
            continue
        dealer_research.append({
            "company_name": c.get("title") or c.get("domain") or "Unknown",
            "website_url": c["url"] if c["url"].startswith(("http://", "https://")) else "https://" + c["url"].lstrip("/"),
            "sales_contact_email": normalized_email,
            "retail_pricing": None,
        })

    # Deduplicate dealer rows by contact email only (requested behavior).
    # If email is missing, fallback to URL so we do not collapse unrelated no-email rows.
    deduped_dealers: List[Dict[str, Any]] = []
    seen: set = set()
    for d in dealer_research:
        email = (d.get("sales_contact_email") or "").strip().lower()
        website = (d.get("website_url") or "").strip().lower()
        key = ("email", email) if email else ("url", website)
        if key in seen:
            continue
        seen.add(key)
        deduped_dealers.append(d)

    return {"manufacturer_research": manufacturer_research, "dealer_research": deduped_dealers}


def _build_tavily_context_for_llm(tavily_result: Dict[str, Any]) -> str:
    """Build a concise text context from Tavily searches for the LLM."""
    parts: List[str] = []
    for i, search in enumerate(tavily_result.get("searches") or []):
        q = search.get("query") or ""
        answer = search.get("answer") or ""
        results = search.get("results") or []
        parts.append(f"Query {i + 1}: {q}")
        if answer:
            parts.append(f"Answer: {answer}")
        for r in results[:6]:
            title = (r.get("title") or "").strip()
            url = (r.get("url") or "").strip()
            content = (r.get("content") or "").strip()[:800]
            if title or url or content:
                parts.append(f"  - {title or 'No title'} | {url}")
                if content:
                    parts.append(f"    {content}")
    return "\n".join(parts)


def _extract_manufacturer_and_dealers_from_tavily(tavily_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Use LLM to extract from Tavily raw results:
    - manufacturer_research: list of { name, official_website, sales_contact_email } (one per manufacturer)
    - dealer_research: list of { company_name, website_url, sales_contact_email, retail_pricing }; manufacturers that are also dealers are included here too
    Returns { "manufacturer_research": [...] or {...}, "dealer_research": [...] }. Single-object manufacturer format is supported for backward compat.
    """
    empty = {
        "manufacturer_research": [],
        "dealer_research": [],
    }
    clin_info = tavily_result.get("clin") or {}
    mfr = (clin_info.get("manufacturer_name") or "").strip()
    product = (clin_info.get("product_name") or "").strip()
    context = _build_tavily_context_for_llm(tavily_result)
    if not context.strip():
        return empty

    prompt = f"""You are extracting structured research from web search results for a government contract line item (CLIN). The goal is to find ALL manufacturers and authorized dealers with website and contact email for quote requests. Contact email is REQUIRED for quote requests—extract it whenever it appears.

CLIN context: manufacturer="{mfr}", product="{product}"
(The manufacturer field may list multiple companies, e.g. "Company A / Company B" or "Company A - CAGE X / Company B - CAGE Y". Extract research for EACH.)

Web search results (queries, answers, and result snippets). Each result has "Title | URL" then snippet text:
---
{context}
---

RULES:
1) manufacturer_research: MUST be an ARRAY of objects, one per manufacturer. For EACH manufacturer named in the CLIN (or found in results):
   - name: company name (e.g. "BAE Systems", "North Atlantic Industries Inc.").
   - official_website: that manufacturer's official site URL from the results, or null.
   - sales_contact_email: real email for quote/contact (e.g. sales@company.com). REQUIRED when found. Null only if not in results. No URLs or /cdn-cgi/ links.

2) dealer_research (authorized dealers/distributors for quote requests). For EACH dealer OR distributor:
   - company_name: string.
   - website_url: REQUIRED when possible. Use the result URL that clearly belongs to that company.
   - sales_contact_email: contact/sales email for quote requests. REQUIRED when found. Extract from snippet (e.g. "email: x@y.com", "contact@", "sales@"). Null only if not found.
   - retail_pricing: string or null if visible.
   - If a manufacturer also acts as a distributor or dealer (sells direct), INCLUDE them in dealer_research as well with their website and sales_contact_email.

Prioritize entries where sales_contact_email is found. Include up to 8 dealers. Always set website_url from the result URL when the result is about that company.
Output ONLY a single valid JSON object (no markdown, no explanation):
{{"manufacturer_research": [{{"name": "...", "official_website": "...", "sales_contact_email": "..."}}, ...], "dealer_research": [{{"company_name": "...", "website_url": "...", "sales_contact_email": "...", "retail_pricing": "..."}}, ...]}}
"""

    llm = None
    if ANTHROPIC_AVAILABLE and ChatAnthropic is not None and getattr(settings, "ANTHROPIC_API_KEY", None):
        try:
            llm = ChatAnthropic(  # type: ignore[call-arg, argument]
                model=getattr(settings, "ANTHROPIC_MODEL", "claude-3-sonnet-20240229"),  # type: ignore[misc]
                temperature=0,
                api_key=SecretStr(settings.ANTHROPIC_API_KEY),
                timeout=None,
            )
        except Exception as e:
            logger.debug("Tavily extract: Claude init failed: %s", e)
    if not llm and GROQ_AVAILABLE and ChatGroq is not None and getattr(settings, "GROQ_API_KEY", None):
        try:
            llm = ChatGroq(  # type: ignore[call-arg]
                model=getattr(settings, "GROQ_MODEL", "llama-3.3-70b-versatile"),
                temperature=0,
                api_key=SecretStr(settings.GROQ_API_KEY),
            )
        except Exception as e:
            logger.debug("Tavily extract: Groq init failed: %s", e)
    if not llm:
        logger.warning("Tavily extract: no LLM available (Anthropic/Groq); skipping structured extraction")
        return empty

    text = ""
    try:
        response = llm.invoke(prompt)
        raw = response.content if hasattr(response, "content") else str(response)
        if isinstance(raw, list):
            text = "".join(
                (block.get("text", "") if isinstance(block, dict) else str(block))
                for block in raw
            )
        else:
            text = str(raw) if raw else ""
        if not text:
            return empty
        # Strip markdown code block if present
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```\s*$", "", text)
        out = json.loads(text)
        m = out.get("manufacturer_research")
        d = out.get("dealer_research")
        if not isinstance(d, list):
            d = []

        def _normalize_url(u: Optional[str]) -> Optional[str]:
            if not u or not isinstance(u, str):
                return None
            u = u.strip() or None
            if not u:
                return None
            if not u.startswith(("http://", "https://")):
                return "https://" + u.lstrip("/")
            return u

        # Normalize manufacturer_research: accept array (new) or single object (legacy)
        manufacturers: List[Dict[str, Any]] = []
        if isinstance(m, list):
            for item in m:
                if not isinstance(item, dict):
                    continue
                name = (str(item.get("name") or "").strip()) or None
                official_website = (item.get("official_website") or "").strip() or None
                if official_website and not official_website.startswith(("http://", "https://")):
                    official_website = "https://" + official_website.lstrip("/")
                manufacturers.append({
                    "name": name,
                    "official_website": official_website or None,
                    "sales_contact_email": _normalize_email((str(item.get("sales_contact_email") or "").strip()) or None),
                })
        elif isinstance(m, dict):
            # Legacy single-object format
            official_website = (m.get("official_website") or "").strip() or None
            if official_website and not official_website.startswith(("http://", "https://")):
                official_website = "https://" + official_website.lstrip("/")
            manufacturers = [{
                "name": None,
                "official_website": official_website or None,
                "sales_contact_email": _normalize_email((str(m.get("sales_contact_email") or "").strip()) or None),
            }]

        # Cap dealers at 8 and ensure each has required keys; validate emails
        dealers = []
        for i, item in enumerate(d[:8]):
            if not isinstance(item, dict):
                continue
            raw_email = (str(item.get("sales_contact_email") or "").strip()) or None
            dealers.append({
                "company_name": (str(item.get("company_name") or "").strip()) or None,
                "website_url": _normalize_url(str(item.get("website_url") or "").strip() or None),
                "sales_contact_email": _normalize_email(raw_email),
                "retail_pricing": (str(item.get("retail_pricing") or "").strip()) or None,
            })

        return {
            "manufacturer_research": manufacturers if manufacturers else [],  # Store as list; frontend/API accept dict or list
            "dealer_research": dealers,
        }
    except json.JSONDecodeError as e:
        logger.warning("Tavily extract: JSON parse error: %s", e)
        if text:
            logger.debug("Tavily extract: raw LLM snippet: %.500s", text)
        return empty
    except Exception as e:
        logger.exception("Tavily extract failed: %s", e)
        return empty


def _post_filter_research(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Final quality filter for extracted research (AI or regex):
    - dealers must have valid email
    - drop obvious bad sources (wiki/pdf/social/news/owner portal)
    - dedupe by email (fallback url when email missing)
    """
    manufacturers = data.get("manufacturer_research") or []
    dealers = data.get("dealer_research") or []

    if isinstance(manufacturers, dict):
        manufacturers = [manufacturers]
    if not isinstance(manufacturers, list):
        manufacturers = []
    if not isinstance(dealers, list):
        dealers = []

    cleaned_mfr: List[Dict[str, Any]] = []
    for m in manufacturers:
        if not isinstance(m, dict):
            continue
        cleaned_mfr.append({
            "name": (m.get("name") or None),
            "official_website": m.get("official_website"),
            "sales_contact_email": _normalize_email(m.get("sales_contact_email")),
        })

    cleaned_dealers: List[Dict[str, Any]] = []
    seen = set()
    for d in dealers:
        if not isinstance(d, dict):
            continue
        email = _normalize_email(d.get("sales_contact_email"))
        website = (d.get("website_url") or "").strip()
        company = (d.get("company_name") or "").strip()
        if not email:
            continue
        if _is_bad_dealer_source(website, company, ""):
            continue
        key = ("email", email.lower()) if email else ("url", website.lower())
        if key in seen:
            continue
        seen.add(key)
        cleaned_dealers.append({
            "company_name": company or None,
            "website_url": website or None,
            "sales_contact_email": email,
            "retail_pricing": d.get("retail_pricing"),
        })

    return {
        "manufacturer_research": cleaned_mfr,
        "dealer_research": cleaned_dealers,
    }


def _group_clins_by_manufacturer(clins: List[Dict[str, Any]]) -> List[Tuple[str, List[Dict[str, Any]]]]:
    """
    Group CLINs by normalized manufacturer name. Kept for reference only; no longer used to batch
    Tavily runs (we run once per CLIN so dealers are never copied across CLINs).
    Returns list of (group_key, clins_in_group).
    """
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for c in clins:
        mfr = (c.get("manufacturer_name") or "").strip()
        key = mfr.lower() if mfr else "__unknown__"
        groups.setdefault(key, []).append(c)
    return list(groups.items())


def _group_clins_by_manufacturer_and_product(clins: List[Dict[str, Any]]) -> List[Tuple[str, List[Dict[str, Any]]]]:
    """Group CLINs by (manufacturer_name, product_key) so one Tavily run per unique product; dealers stay product-specific."""
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for c in clins:
        mfr = (c.get("manufacturer_name") or "").strip().lower() or "__unknown__"
        product_key = (c.get("product_name") or c.get("part_number") or "").strip().lower() or f"clin_{c.get('id', id(c))}"
        key = (mfr, product_key)
        key_str = f"{mfr}|{product_key}"
        groups.setdefault(key_str, []).append(c)
    return list(groups.items())


def _run_tavily_for_one_clin_no_persist(api_key: str, clin: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    """
    Run Tavily for a single CLIN: search, AI extract (primary), regex fallback. No email fill or post-filter here;
    those run once per opportunity in run_tavily_for_opportunity. No file I/O.
    Returns (success, data) so caller can persist for one or many CLINs.
    """
    clin_id = clin.get("id")
    try:
        data = run_tavily_for_clin(api_key, clin)
        if data.get("searches"):
            logger.info("[Tavily] CLIN %s: AI extraction from Tavily results (searches=%s)", clin_id, len(data.get("searches") or []))
            extracted = _extract_manufacturer_and_dealers_from_tavily(data)

            # Fallback to regex parser only when AI extraction returns effectively empty output.
            ai_mfr = extracted.get("manufacturer_research") or []
            ai_dealers = extracted.get("dealer_research") or []
            if (not ai_mfr) and (not ai_dealers):
                logger.info("[Tavily] CLIN %s: AI extraction empty; using regex fallback", clin_id)
                extracted = _extract_manufacturer_and_dealers_from_tavily_regex(data)

            data["manufacturer_research"] = extracted.get("manufacturer_research") or []
            data["dealer_research"] = extracted.get("dealer_research") or []
        else:
            data["manufacturer_research"] = []
            data["dealer_research"] = []
        mfr_list = data.get("manufacturer_research") or []
        dealers = data.get("dealer_research") or []
        mfr_count = len(mfr_list) if isinstance(mfr_list, list) else (1 if mfr_list else 0)
        has_mfr_contact = bool(
            (isinstance(mfr_list, list) and any((m.get("official_website") or m.get("sales_contact_email")) for m in mfr_list if isinstance(m, dict)))
            or (isinstance(mfr_list, dict) and (mfr_list.get("official_website") or mfr_list.get("sales_contact_email")))
        )
        logger.info("[Tavily] CLIN %s: extracted manufacturers=%s has_contact=%s dealers_count=%s",
            clin_id, mfr_count, has_mfr_contact, len(dealers))
        return True, data
    except Exception as e:
        logger.exception("[Tavily] CLIN %s failed: %s", clin_id, e)
        return False, {"manufacturer_research": [], "dealer_research": [], "clin": clin}


def _persist_tavily_result_for_clin(
    clin: Dict[str, Any],
    data: Dict[str, Any],
    run_dir: Path,
    updates: List[Dict[str, Any]],
) -> None:
    """Write one JSON per CLIN and append one update. data can be shared; we set data['clin'] for this CLIN."""
    clin_id = clin.get("id")
    out_data = {**data, "clin": clin}
    out_path = run_dir / f"clin_{clin_id}.json"
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(out_data, f, indent=2, default=str)
        updates.append({
            "clin_id": clin_id,
            "manufacturer_research": out_data.get("manufacturer_research") or [],
            "dealer_research": out_data.get("dealer_research") or [],
        })
    except Exception as e:
        logger.exception("[Tavily] persist CLIN %s failed: %s", clin_id, e)
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump({"clin_id": clin_id, "error": str(e), "clin": clin}, f, indent=2, default=str)
        except Exception:
            pass


def _run_tavily_for_one_clin_and_persist(
    api_key: str,
    clin: Dict[str, Any],
    run_dir: Path,
    updates: List[Dict[str, Any]],
) -> Tuple[bool, Optional[Any], Optional[Any]]:
    """
    Run Tavily for a single CLIN (search, regex extract, fill emails), save JSON, append to updates.
    Returns (success, manufacturer_research, dealer_research).
    """
    ok, data = _run_tavily_for_one_clin_no_persist(api_key, clin)
    if not ok:
        clin_id = clin.get("id")
        try:
            err_path = run_dir / f"clin_{clin_id}.json"
            with open(err_path, "w", encoding="utf-8") as f:
                json.dump({"clin_id": clin_id, "error": "Tavily run failed", "clin": clin}, f, indent=2, default=str)
        except Exception:
            pass
        return False, None, None
    _fill_missing_emails_opportunity_level([data])
    _ai_batch_parse_missing_emails_opportunity([data])
    filtered = _post_filter_research(data)
    data["manufacturer_research"] = filtered.get("manufacturer_research") or []
    data["dealer_research"] = filtered.get("dealer_research") or []
    _persist_tavily_result_for_clin(clin, data, run_dir, updates)
    return True, data.get("manufacturer_research"), data.get("dealer_research")


def _write_group_tavily_errors(run_dir: Path, clins_in_group: List[Dict[str, Any]], err_msg: str = "Tavily run failed") -> None:
    for clin in clins_in_group:
        clin_id = clin.get("id")
        try:
            err_path = run_dir / f"clin_{clin_id}.json"
            with open(err_path, "w", encoding="utf-8") as f:
                json.dump({"clin_id": clin_id, "error": err_msg, "clin": clin}, f, indent=2, default=str)
        except Exception:
            pass


def _run_one_tavily_group_extract_only(
    api_key: str,
    clins_in_group: List[Dict[str, Any]],
) -> Tuple[str, List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Tavily + structured extract for the group's lead CLIN only. Returns:
    ("ok", group_clins, data) or ("fail", group_clins, None).
    """
    if not clins_in_group:
        return ("fail", clins_in_group, None)
    lead = clins_in_group[0]
    ok, data = _run_tavily_for_one_clin_no_persist(api_key, lead)
    if not ok:
        return ("fail", clins_in_group, None)
    return ("ok", clins_in_group, data)


def _data_dict_for_skip_tavily_search(lead_clin: Dict[str, Any], stub_after_propagation: Dict[str, Any]) -> Dict[str, Any]:
    """Shape like run_tavily_for_clin output but with no Tavily API calls (empty searches)."""
    params = _get_tavily_params()
    data = copy.deepcopy(stub_after_propagation)
    data["clin"] = lead_clin
    data["queries"] = []
    data["searches"] = []
    data["search_depth"] = params.get("search_depth", "advanced")
    data["max_results"] = params.get("max_results", 12)
    data["include_answer"] = params.get("include_answer", True)
    data.setdefault("summary", "Tavily search skipped (cached research + cross-CLIN email rate threshold)")
    return data


def _finalize_and_persist_opportunity_groups(
    successful_pairs: List[Tuple[List[Dict[str, Any]], Dict[str, Any]]],
    run_dir: Path,
    updates: List[Dict[str, Any]],
) -> None:
    """Cross-CLIN email fill, aggregate AI parse, post-filter, then persist each CLIN JSON."""
    all_data = [data for _gc, data in successful_pairs]
    if all_data:
        _fill_missing_emails_opportunity_level(all_data)
        _ai_batch_parse_missing_emails_opportunity(all_data)
        for d in all_data:
            filtered = _post_filter_research(d)
            d["manufacturer_research"] = filtered.get("manufacturer_research") or []
            d["dealer_research"] = filtered.get("dealer_research") or []
    for group_clins, data in successful_pairs:
        for clin in group_clins:
            _persist_tavily_result_for_clin(clin, data, run_dir, updates)


def run_tavily_for_opportunity(
    opportunity_id: int,
    clins: List[Dict[str, Any]],
    output_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Run Tavily per unique (manufacturer, product); parallel groups run search + extract first.
    If stored research exists, cross-CLIN copy runs first; when fewer than TAVILY_SKIP_IF_MISSING_RATE_BELOW
    of website rows still lack email, Tavily search is skipped for that group (fill/AI still run opportunity-wide).
    Then one opportunity-wide pass: cross-CLIN copy by site key, one Tavily-snippet + one fetch per unique
    hostname, aggregate AI email parse, post-filter, then persist one JSON per CLIN.

    Returns summary: { "opportunity_id", "clins_processed", "clins_failed", "output_dir", "updates" }.
    """
    logger.info("[Tavily] run_tavily_for_opportunity start opportunity_id=%s clins_count=%s", opportunity_id, len(clins))
    api_key = getattr(settings, "TAVILY_API_KEY", None) or ""
    if not api_key:
        logger.warning("[Tavily] TAVILY_API_KEY not set; skipping Tavily dealer search for opportunity %s", opportunity_id)
        return {
            "opportunity_id": opportunity_id,
            "skipped": True,
            "reason": "TAVILY_API_KEY not set",
            "clins_processed": 0,
            "clins_failed": 0,
            "updates": [],
        }
    out_dir = output_dir or (settings.DATA_DIR / "tavily_results")
    run_dir = out_dir / f"opportunity_{opportunity_id}"
    run_dir.mkdir(parents=True, exist_ok=True)

    if getattr(settings, "TAVILY_REUSE_BY_PRODUCT", TAVILY_REUSE_BY_PRODUCT):
        groups = _group_clins_by_manufacturer_and_product(clins)
        logger.info("[Tavily] output_dir=%s reuse_by_product=True groups=%s", run_dir, len(groups))
    else:
        groups = [(f"clin_{c.get('id', i)}", [c]) for i, c in enumerate(clins)]
        logger.info("[Tavily] output_dir=%s one run per CLIN", run_dir)

    # Stubs from DB/payload manufacturer_research + dealer_research; cross-CLIN copy before deciding to skip Tavily.
    stubs: List[Dict[str, Any]] = [_build_research_stub_from_clin_payload(c) for c in clins]
    _propagate_cross_clin_emails_by_domain(stubs)
    stub_by_clin_id: Dict[Any, Dict[str, Any]] = {s["clin"]["id"]: s for s in stubs}
    skip_threshold = float(getattr(settings, "TAVILY_SKIP_IF_MISSING_RATE_BELOW", 0.30) or 0.0)

    updates: List[Dict[str, Any]] = []
    successful_pairs: List[Tuple[List[Dict[str, Any]], Dict[str, Any]]] = []
    tavily_groups: List[Tuple[str, List[Dict[str, Any]]]] = []

    for _key, group_clins in groups:
        lead = group_clins[0]
        stub = stub_by_clin_id.get(lead.get("id"))
        rate: Optional[float] = None
        if stub is not None:
            rate = _missing_email_rate_for_stub(stub)
        skip_tavily = skip_threshold > 0 and rate is not None and rate < skip_threshold
        if skip_tavily:
            assert stub is not None and rate is not None
            data = _data_dict_for_skip_tavily_search(lead, stub)
            successful_pairs.append((group_clins, data))
            logger.info(
                "[Tavily] CLIN %s: skip Tavily search (missing email rate %.1f%% < %.0f%% after cross-CLIN)",
                lead.get("id"),
                rate * 100.0,
                skip_threshold * 100.0,
            )
        else:
            tavily_groups.append((_key, group_clins))

    max_workers = getattr(settings, "TAVILY_PARALLEL_MAX_WORKERS", TAVILY_PARALLEL_MAX_WORKERS) or 1
    if max_workers <= 1:
        for _key, group_clins in tavily_groups:
            status, gclins, data = _run_one_tavily_group_extract_only(api_key, group_clins)
            if status != "ok" or data is None:
                _write_group_tavily_errors(run_dir, group_clins)
            else:
                successful_pairs.append((gclins, data))
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_run_one_tavily_group_extract_only, api_key, group_clins): (_key, group_clins)
                for _key, group_clins in tavily_groups
            }
            for fut in as_completed(futures):
                _key, group_clins = futures[fut]
                try:
                    status, gclins, data = fut.result()
                    if status != "ok" or data is None:
                        _write_group_tavily_errors(run_dir, group_clins)
                    else:
                        successful_pairs.append((gclins, data))
                except Exception as e:
                    logger.exception("[Tavily] group %s failed: %s", _key, e)
                    for clin in group_clins:
                        clin_id = clin.get("id")
                        try:
                            err_path = run_dir / f"clin_{clin_id}.json"
                            with open(err_path, "w", encoding="utf-8") as f:
                                json.dump({"clin_id": clin_id, "error": str(e), "clin": clin}, f, indent=2, default=str)
                        except Exception:
                            pass

    if successful_pairs:
        _finalize_and_persist_opportunity_groups(successful_pairs, run_dir, updates)

    processed = len(updates)
    failed = len(clins) - processed
    logger.info("[Tavily] run_tavily_for_opportunity done opportunity_id=%s processed=%s failed=%s updates_count=%s",
        opportunity_id, processed, failed, len(updates))
    return {
        "opportunity_id": opportunity_id,
        "clins_processed": processed,
        "clins_failed": failed,
        "output_dir": str(run_dir),
        "updates": updates,
    }
