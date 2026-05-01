"""
Tavily web search: find manufacturer and dealers per CLIN (runs after CLIN extraction).
Extracts: manufacturer official website + sales contact email; up to 8 dealers with name, URL, email, pricing.
Missing emails are filled in-core: first from Tavily snippet content, then by fetching dealer/manufacturer
website_url (and /contact, /contact-us) and scraping with email regex. All Tavily params and query
generation are config-driven or LLM-generated (no hardcoded query templates).
"""
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
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
            if result_domain and target_domain in result_domain:
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


def _fill_missing_emails_phase1(tavily_data: Dict[str, Any]) -> None:
    """
    Fill missing sales_contact_email for manufacturers and dealers using ONLY Tavily snippets.
    This is fast and should be done before any cross-CLIN optimization.
    """
    clin_id = (tavily_data.get("clin") or {}).get("id", "?")
    mfr_list = tavily_data.get("manufacturer_research")
    if isinstance(mfr_list, list):
        for m in mfr_list:
            if not isinstance(m, dict) or m.get("sales_contact_email"):
                continue
            url = m.get("official_website")
            email = _extract_emails_from_tavily_content(tavily_data, url)
            if email and _normalize_email(email):
                m["sales_contact_email"] = _normalize_email(email)
                logger.info("[Tavily fill] CLIN %s: manufacturer email from content PASSED -> %s", clin_id, email[:50])

    dealers = tavily_data.get("dealer_research") or []
    for d in dealers:
        if not isinstance(d, dict) or d.get("sales_contact_email"):
            continue
        url = d.get("website_url")
        email = _extract_emails_from_tavily_content(tavily_data, url)
        if email and _normalize_email(email):
            d["sales_contact_email"] = _normalize_email(email)
            logger.info("[Tavily fill] CLIN %s: dealer email from content PASSED -> %s", clin_id, email[:50])


def _batch_extract_emails_llm(domain_texts: Dict[str, str]) -> Dict[str, str]:
    """
    Use LLM to extract the best contact emails from multiple website text contents in a single call.
    domain_texts: { domain: concatenated_page_text }
    Returns: { domain: best_email or "" }
    """
    if not domain_texts:
        return {}

    llm = None
    if ANTHROPIC_AVAILABLE and ChatAnthropic is not None and getattr(settings, "ANTHROPIC_API_KEY", None):
        try:
            llm = ChatAnthropic(
                model=getattr(settings, "ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
                temperature=0,
                api_key=SecretStr(settings.ANTHROPIC_API_KEY),
                timeout=90,
            )
        except Exception:
            pass
    if not llm and GROQ_AVAILABLE and ChatGroq is not None and getattr(settings, "GROQ_API_KEY", None):
        try:
            llm = ChatGroq(
                model=getattr(settings, "GROQ_MODEL", "llama-3.3-70b-versatile"),
                temperature=0,
                api_key=SecretStr(settings.GROQ_API_KEY),
            )
        except Exception:
            pass
    if not llm:
        # Fallback to regex if no LLM
        results = {}
        for domain, text in domain_texts.items():
            emails = _extract_emails_from_text(text)
            results[domain] = _pick_best_contact_email(emails, domain) or ""
        return results

    # Prepare prompt for batch extraction
    context_parts = []
    for domain, text in domain_texts.items():
        context_parts.append(f"--- WEBSITE: {domain} ---\n{text[:4000]}")
    
    prompt = f"""You are extracting sales/contact emails from website text for multiple companies.
For each website, find the best email for quote requests or general contact (e.g. sales@, contact@, info@).
Avoid personal emails or irrelevant addresses.

Websites and text content:
{"\n\n".join(context_parts)}

Output ONLY a valid JSON object where keys are the domain names and values are the best email found (or empty string if none):
{{ "example.com": "sales@example.com", "other.net": "" }}
"""
    try:
        response = llm.invoke(prompt)
        raw = response.content if hasattr(response, "content") else str(response)
        # Handle list of content blocks
        if isinstance(raw, list):
            raw = "".join((b.get("text", "") if isinstance(b, dict) else str(b)) for b in raw)
        
        # Robust JSON extraction
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if json_match:
            results = json.loads(json_match.group(0))
            if isinstance(results, dict):
                # Ensure all requested domains are in the result
                final_results = {}
                for domain in domain_texts.keys():
                    final_results[domain] = _normalize_email(results.get(domain)) or ""
                return final_results
    except Exception as e:
        logger.warning("[Tavily fill] Batch LLM extraction failed: %s", e)

    # Fallback to regex
    results = {}
    for domain, text in domain_texts.items():
        emails = _extract_emails_from_text(text)
        results[domain] = _pick_best_contact_email(emails, domain) or ""
    return results


def _optimize_opportunity_emails(run_dir: Path, updates: List[Dict[str, Any]]) -> None:
    """
    Cross-CLIN email optimization:
    0) Domain normalization.
    1) Cross-check across CLINs (share emails for same domain).
    2) Threshold check (skip navigation if < 30% missing).
    3) Batch navigation (parallel fetch) + Batch LLM extraction.
    4) Overwrite JSON files on disk and update memory 'updates'.
    """
    if not updates:
        return

    # Map to track domain -> best email found so far
    domain_to_email: Dict[str, str] = {}
    
    def _collect_emails(data_list: List[Dict[str, Any]]):
        for item in data_list:
            if not isinstance(item, dict): continue
            mfrs = item.get("manufacturer_research") or []
            dealers = item.get("dealer_research") or []
            for m in mfrs:
                if not isinstance(m, dict): continue
                domain = _domain_from_url(m.get("official_website"))
                email = _normalize_email(m.get("sales_contact_email"))
                if domain and email and not domain_to_email.get(domain):
                    domain_to_email[domain] = email
            for d in dealers:
                if not isinstance(d, dict): continue
                domain = _domain_from_url(d.get("website_url"))
                email = _normalize_email(d.get("sales_contact_email"))
                if domain and email and not domain_to_email.get(domain):
                    domain_to_email[domain] = email

    # Initial collection of emails found via snippets
    _collect_emails(updates)
    
    # 1) Cross-check & Thresholding
    clin_data_list = []
    missing_domains: set = set()
    
    for upd in updates:
        clin_id = upd.get("clin_id")
        json_path = run_dir / f"clin_{clin_id}.json"
        if not json_path.exists():
            continue
            
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                full_data = json.load(f)
        except Exception:
            continue
            
        # Fill missing from our current map
        mfrs = full_data.get("manufacturer_research") or []
        dealers = full_data.get("dealer_research") or []
        
        for m in mfrs:
            domain = _domain_from_url(m.get("official_website"))
            if domain and not m.get("sales_contact_email") and domain_to_email.get(domain):
                m["sales_contact_email"] = domain_to_email[domain]
        for d in dealers:
            domain = _domain_from_url(d.get("website_url"))
            if domain and not d.get("sales_contact_email") and domain_to_email.get(domain):
                d["sales_contact_email"] = domain_to_email[domain]

        # Calculate threshold
        total_items = len(mfrs) + len(dealers)
        missing_count = 0
        for m in mfrs:
            if not m.get("sales_contact_email"): missing_count += 1
        for d in dealers:
            if not d.get("sales_contact_email"): missing_count += 1
            
        missing_ratio = (missing_count / total_items) if total_items > 0 else 0
        
        # If > 30% missing, we mark its missing domains for navigation
        if missing_ratio > 0.3:
            logger.info("[Tavily fill] CLIN %s missing %.1f%% emails (>30%%) -> queueing navigation", clin_id, missing_ratio*100)
            for m in mfrs:
                domain = _domain_from_url(m.get("official_website"))
                if domain and not m.get("sales_contact_email"): missing_domains.add((domain, m.get("official_website")))
            for d in dealers:
                domain = _domain_from_url(d.get("website_url"))
                if domain and not d.get("sales_contact_email"): missing_domains.add((domain, d.get("website_url")))
        else:
            logger.info("[Tavily fill] CLIN %s missing %.1f%% emails (<=30%%) -> skipping navigation", clin_id, missing_ratio*100)

        clin_data_list.append((upd, full_data, json_path))

    # 2) Navigation for missing domains
    if missing_domains:
        logger.info("[Tavily fill] Batch navigation for %s unique domains", len(missing_domains))
        domain_texts: Dict[str, str] = {}
        
        def _fetch_domain(item):
            dom, url = item
            # Try base + contact paths
            emails = _extract_emails_from_page(url, log_prefix=f"domain '{dom}' ")
            # We also collect page text for LLM fallback/validation if no emails found via regex
            text = _fetch_page_text(url) or ""
            return dom, emails, text

        max_workers = getattr(settings, "TAVILY_FILL_FETCH_MAX_WORKERS", 3)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(_fetch_domain, item) for item in missing_domains]
            for fut in as_completed(futures):
                dom, emails, text = fut.result()
                best = _pick_best_contact_email(emails, dom)
                if best:
                    domain_to_email[dom] = best
                elif text.strip():
                    domain_texts[dom] = text

        # 3) Batch LLM extraction for those still missing
        if domain_texts:
            logger.info("[Tavily fill] Batch LLM extraction for %s domains", len(domain_texts))
            llm_emails = _batch_extract_emails_llm(domain_texts)
            for dom, email in llm_emails.items():
                if email:
                    domain_to_email[dom] = email

    # 4) Final update & Persistence
    for upd, full_data, json_path in clin_data_list:
        mfrs = full_data.get("manufacturer_research") or []
        dealers = full_data.get("dealer_research") or []
        
        for m in mfrs:
            domain = _domain_from_url(m.get("official_website"))
            if domain and not m.get("sales_contact_email") and domain_to_email.get(domain):
                m["sales_contact_email"] = domain_to_email[domain]
        for d in dealers:
            domain = _domain_from_url(d.get("website_url"))
            if domain and not d.get("sales_contact_email") and domain_to_email.get(domain):
                d["sales_contact_email"] = domain_to_email[domain]
        
        # Save back to disk
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(full_data, f, indent=2, default=str)
        except Exception:
            pass
            
        # Update memory 'upd' so return result is correct
        upd["manufacturer_research"] = mfrs
        upd["dealer_research"] = dealers


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
            })

    # Manufacturer: first result that matches CLIN manufacturer name (in url or title), or first result
    manufacturer_research: List[Dict[str, Any]] = []
    mfr_lower = mfr_name.lower() if mfr_name else ""
    mfr_candidate = None
    for c in candidates:
        if mfr_lower and (mfr_lower in (c.get("url") or "").lower() or mfr_lower in (c.get("title") or "").lower()):
            mfr_candidate = c
            break
    if not mfr_candidate and candidates:
        mfr_candidate = candidates[0]
    if mfr_candidate:
        manufacturer_research.append({
            "name": mfr_name or None,
            "official_website": mfr_candidate["url"] if mfr_candidate["url"].startswith(("http://", "https://")) else "https://" + mfr_candidate["url"].lstrip("/"),
            "sales_contact_email": _normalize_email(mfr_candidate.get("email")),
        })

    # Dealers: prefer candidates with email; cap 8; skip duplicate of manufacturer URL
    dealer_research: List[Dict[str, Any]] = []
    mfr_url = (mfr_candidate or {}).get("url", "")
    with_email = [c for c in candidates if c.get("email")]
    without_email = [c for c in candidates if not c.get("email")]
    ordered_candidates = with_email + without_email
    for c in ordered_candidates:
        if len(dealer_research) >= 8:
            break
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
        dealer_research.append({
            "company_name": c.get("title") or c.get("domain") or "Unknown",
            "website_url": c["url"] if c["url"].startswith(("http://", "https://")) else "https://" + c["url"].lstrip("/"),
            "sales_contact_email": _normalize_email(c.get("email")),
            "retail_pricing": None,
        })

    return {"manufacturer_research": manufacturer_research, "dealer_research": dealer_research}


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
    Run Tavily for a single CLIN: search, extract (AI primary, regex fallback), fill emails. No file I/O.
    Returns (success, data) so caller can persist for one or many CLINs.
    """
    clin_id = clin.get("id")
    try:
        data = run_tavily_for_clin(api_key, clin)
        if data.get("searches"):
            # Try AI extraction first
            logger.info("[Tavily] CLIN %s: AI extraction from Tavily results (searches=%s)", clin_id, len(data.get("searches") or []))
            extracted = _extract_manufacturer_and_dealers_from_tavily(data)
            
            # Fallback to regex if AI returned nothing (and regex is available)
            if not extracted.get("manufacturer_research") and not extracted.get("dealer_research"):
                logger.info("[Tavily] CLIN %s: AI extraction returned no results; falling back to regex", clin_id)
                extracted = _extract_manufacturer_and_dealers_from_tavily_regex(data)
            
            data["manufacturer_research"] = extracted.get("manufacturer_research") or []
            data["dealer_research"] = extracted.get("dealer_research") or []
            _fill_missing_emails_phase1(data)
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
    _persist_tavily_result_for_clin(clin, data, run_dir, updates)
    return True, data.get("manufacturer_research"), data.get("dealer_research")


def _run_one_tavily_group(
    api_key: str,
    run_dir: Path,
    clins_in_group: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Run Tavily once for the first CLIN in the group (lead), then persist the same result for every CLIN in the group.
    Returns list of update dicts (one per CLIN).
    """
    group_updates: List[Dict[str, Any]] = []
    if not clins_in_group:
        return group_updates
    lead = clins_in_group[0]
    ok, data = _run_tavily_for_one_clin_no_persist(api_key, lead)
    if not ok:
        for clin in clins_in_group:
            clin_id = clin.get("id")
            try:
                err_path = run_dir / f"clin_{clin_id}.json"
                with open(err_path, "w", encoding="utf-8") as f:
                    json.dump({"clin_id": clin_id, "error": "Tavily run failed", "clin": clin}, f, indent=2, default=str)
            except Exception:
                pass
        return group_updates
    for clin in clins_in_group:
        _persist_tavily_result_for_clin(clin, data, run_dir, group_updates)
    return group_updates


def run_tavily_for_opportunity(
    opportunity_id: int,
    clins: List[Dict[str, Any]],
    output_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Run Tavily per unique (manufacturer, product) and save one JSON per CLIN. Same product reuses one run;
    dealers stay product-specific. Runs groups in parallel. Extraction is AI-based (Claude/Groq) with regex fallback.

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

    updates: List[Dict[str, Any]] = []
    max_workers = getattr(settings, "TAVILY_PARALLEL_MAX_WORKERS", TAVILY_PARALLEL_MAX_WORKERS) or 1
    if max_workers <= 1:
        for _key, group_clins in groups:
            updates.extend(_run_one_tavily_group(api_key, run_dir, group_clins))
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_run_one_tavily_group, api_key, run_dir, group_clins): (_key, group_clins)
                for _key, group_clins in groups
            }
            for fut in as_completed(futures):
                try:
                    group_updates = fut.result()
                    updates.extend(group_updates)
                except Exception as e:
                    _key, group_clins = futures[fut]
                    logger.exception("[Tavily] group %s failed: %s", _key, e)
                    for clin in group_clins:
                        clin_id = clin.get("id")
                        try:
                            err_path = run_dir / f"clin_{clin_id}.json"
                            with open(err_path, "w", encoding="utf-8") as f:
                                json.dump({"clin_id": clin_id, "error": str(e), "clin": clin}, f, indent=2, default=str)
                        except Exception:
                            pass

    if updates:
        _optimize_opportunity_emails(run_dir, updates)

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
