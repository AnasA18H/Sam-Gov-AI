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
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import SecretStr

from ..core.config import settings

logger = logging.getLogger(__name__)

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
                model=getattr(settings, "GROQ_MODEL", "llama-3.1-70b-versatile"),
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


def _fetch_page_text(url: str, timeout_sec: int = 12, log_prefix: str = "", retry_on_error: bool = True) -> Optional[str]:
    """Fetch URL and return plain text (strip HTML). Also extracts mailto: links. Returns None on failure."""
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError:
        logger.warning("[Tavily fill] %sNavigation failed (missing requests or bs4): skipping fetch", log_prefix)
        return None
    if not url.startswith(("http://", "https://")):
        url = "https://" + url.lstrip("/")

    def _do_fetch() -> Optional[str]:
        try:
            r = requests.get(
                url,
                timeout=timeout_sec,
                headers={"User-Agent": _FETCH_USER_AGENT},
                allow_redirects=True,
            )
            # Treat 404 as "page not there" - log at debug, not as hard failure
            if r.status_code == 404:
                logger.debug("[Tavily fill] %sPath not found (404) url=%s", log_prefix, url[:80])
                return None
            r.raise_for_status()
            html = r.text
            soup = BeautifulSoup(html, "html.parser")
            # Extract mailto: links before stripping (many sites only expose email in links)
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
                text = text + "\n" + "\n".join(mailto_emails)
            return text or None
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                logger.debug("[Tavily fill] %sPath not found (404) url=%s", log_prefix, url[:80])
                return None
            raise
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            logger.info("[Tavily fill] %sNavigation timeout/connection url=%s reason=%s", log_prefix, url[:80], e)
            raise

    try:
        return _do_fetch()
    except Exception as e:
        # Retry once on 500 or timeout (server may be slow or briefly down)
        if retry_on_error:
            if "500" in str(e) or "timed out" in str(e).lower() or "Timeout" in str(e):
                logger.info("[Tavily fill] %sRetrying once after error url=%s", log_prefix, url[:80])
                import time
                time.sleep(2)
                try:
                    return _do_fetch()
                except Exception:
                    pass
        logger.info("[Tavily fill] %sNavigation FAILED url=%s reason=%s", log_prefix, url[:80], e)
        return None


# Common contact-page paths (many sites use one of these)
_CONTACT_PATHS = (
    "/contact", "/contact-us", "/contact_us", "/contact.html",
    "/about", "/about-us", "/about_us", "/get-in-touch", "/en/contact",
)

def _extract_emails_from_page(url: str, timeout_sec: int = 14, log_prefix: str = "") -> List[str]:
    """Fetch URL and optional contact paths; return all found emails (from text + mailto: links)."""
    text = _fetch_page_text(url, timeout_sec, log_prefix=log_prefix)
    if text:
        emails = _extract_emails_from_text(text)
        if emails:
            logger.info("[Tavily fill] %sNavigation PASSED url=%s emails_found=%s", log_prefix, url[:80], len(emails))
            return emails
    # Try common contact paths (longer timeout for slow servers)
    base = url.rstrip("/")
    path_timeout = min(10, timeout_sec)
    for path in _CONTACT_PATHS:
        u = base + path
        t = _fetch_page_text(u, timeout_sec=path_timeout, log_prefix=log_prefix)
        if t:
            emails = _extract_emails_from_text(t)
            if emails:
                logger.info("[Tavily fill] %sNavigation PASSED url=%s emails_found=%s", log_prefix, u[:80], len(emails))
                return emails
    logger.info("[Tavily fill] %sNavigation FAILED (no emails extracted) url=%s", log_prefix, url[:80])
    return []


def _fill_missing_emails(tavily_data: Dict[str, Any]) -> None:
    """
    Fill missing sales_contact_email for manufacturers and dealers using:
    1) Emails already in Tavily result content (nav/footer in snippets).
    2) Fetch dealer/manufacturer website_url + /contact, /contact-us and scrape emails.
    Mutates tavily_data["manufacturer_research"] and tavily_data["dealer_research"] in place.
    """
    import time
    fill_delay_sec = getattr(settings, "TAVILY_FILL_EMAIL_FETCH_DELAY", 1.0)
    clin_id = (tavily_data.get("clin") or {}).get("id", "?")

    # 1) Fill from Tavily content first (no HTTP)
    logger.info("[Tavily fill] CLIN %s: finding missing emails (phase 1: Tavily content)", clin_id)
    mfr_list = tavily_data.get("manufacturer_research")
    if isinstance(mfr_list, list):
        for m in mfr_list:
            if not isinstance(m, dict):
                continue
            if m.get("sales_contact_email"):
                continue
            name = (m.get("name") or "manufacturer")[:40]
            url = m.get("official_website")
            email = _extract_emails_from_tavily_content(tavily_data, url)
            if email and _normalize_email(email):
                m["sales_contact_email"] = _normalize_email(email)
                logger.info("[Tavily fill] CLIN %s: manufacturer '%s' email from content PASSED -> %s", clin_id, name, email[:50])
            elif url:
                logger.info("[Tavily fill] CLIN %s: manufacturer '%s' email from content FAILED (no match in snippets)", clin_id, name)

    dealers = tavily_data.get("dealer_research") or []
    for d in dealers:
        if not isinstance(d, dict) or d.get("sales_contact_email"):
            continue
        name = (d.get("company_name") or "dealer")[:40]
        url = d.get("website_url")
        email = _extract_emails_from_tavily_content(tavily_data, url)
        if email and _normalize_email(email):
            d["sales_contact_email"] = _normalize_email(email)
            logger.info("[Tavily fill] CLIN %s: dealer '%s' email from content PASSED -> %s", clin_id, name, email[:50])
        elif url:
            logger.info("[Tavily fill] CLIN %s: dealer '%s' email from content FAILED (no match in snippets)", clin_id, name)

    # 2) Fetch pages for those still missing (navigation)
    logger.info("[Tavily fill] CLIN %s: finding missing emails (phase 2: fetch/navigation)", clin_id)
    if isinstance(mfr_list, list):
        for m in mfr_list:
            if not isinstance(m, dict) or m.get("sales_contact_email"):
                continue
            url = m.get("official_website")
            if not url:
                continue
            name = (m.get("name") or "manufacturer")[:40]
            time.sleep(fill_delay_sec)
            log_prefix = f"mfr '{name}' "
            emails = _extract_emails_from_page(url, log_prefix=log_prefix)
            email = _pick_best_contact_email(emails, _domain_from_url(url))
            if email and _normalize_email(email):
                m["sales_contact_email"] = _normalize_email(email)
                logger.info("[Tavily fill] CLIN %s: manufacturer '%s' email from fetch PASSED -> %s", clin_id, name, email[:50])
            else:
                logger.info("[Tavily fill] CLIN %s: manufacturer '%s' email from fetch FAILED (navigation returned no usable email)", clin_id, name)

    for d in dealers:
        if not isinstance(d, dict) or d.get("sales_contact_email"):
            continue
        url = d.get("website_url")
        if not url:
            continue
        name = (d.get("company_name") or "dealer")[:40]
        time.sleep(fill_delay_sec)
        log_prefix = f"dealer '{name}' "
        emails = _extract_emails_from_page(url, log_prefix=log_prefix)
        email = _pick_best_contact_email(emails, _domain_from_url(url))
        if email and _normalize_email(email):
            d["sales_contact_email"] = _normalize_email(email)
            logger.info("[Tavily fill] CLIN %s: dealer '%s' email from fetch PASSED -> %s", clin_id, name, email[:50])
        else:
            logger.info("[Tavily fill] CLIN %s: dealer '%s' email from fetch FAILED (navigation returned no usable email)", clin_id, name)

    logger.info("[Tavily fill] CLIN %s: finding missing emails complete", clin_id)


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
                model=getattr(settings, "GROQ_MODEL", "llama-3.1-70b-versatile"),
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


def run_tavily_for_opportunity(
    opportunity_id: int,
    clins: List[Dict[str, Any]],
    output_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Run Tavily for each CLIN and save one JSON per CLIN under output_dir/opportunity_{id}/clin_{id}.json.
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
    logger.info("[Tavily] output_dir=%s", run_dir)
    processed = 0
    failed = 0
    updates: List[Dict[str, Any]] = []  # for DB persistence: [{ "clin_id", "manufacturer_research", "dealer_research" }, ...]
    for i, clin in enumerate(clins):
        clin_id = clin.get("id", i + 1)
        logger.info("[Tavily] CLIN %s/%s id=%s product=%s", i + 1, len(clins), clin_id, (clin.get("product_name") or "")[:50])
        try:
            data = run_tavily_for_clin(api_key, clin)
            # Extract structured manufacturer + dealer research (official website, sales email, up to 8 dealers)
            if data.get("searches"):
                logger.info("[Tavily] CLIN %s: running LLM extraction (searches=%s)", clin_id, len(data.get("searches") or []))
                extracted = _extract_manufacturer_and_dealers_from_tavily(data)
                data["manufacturer_research"] = extracted.get("manufacturer_research") or []
                data["dealer_research"] = extracted.get("dealer_research") or []
                _fill_missing_emails(data)  # in-core: fill missing sales_contact_email from snippets + fetch
            else:
                data["manufacturer_research"] = []
                data["dealer_research"] = []
            mfr_list = data.get("manufacturer_research") or []
            dealers = data.get("dealer_research") or []
            mfr_count = len(mfr_list) if isinstance(mfr_list, list) else (1 if mfr_list else 0)
            has_mfr_contact = False
            if isinstance(mfr_list, list):
                has_mfr_contact = any((m.get("official_website") or m.get("sales_contact_email")) for m in mfr_list if isinstance(m, dict))
            elif isinstance(mfr_list, dict):
                has_mfr_contact = bool(mfr_list.get("official_website") or mfr_list.get("sales_contact_email"))
            logger.info("[Tavily] CLIN %s: extracted manufacturers=%s has_contact=%s dealers_count=%s",
                clin_id, mfr_count, has_mfr_contact, len(dealers))
            out_path = run_dir / f"clin_{clin_id}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
            processed += 1
            updates.append({
                "clin_id": clin_id,
                "manufacturer_research": data["manufacturer_research"],
                "dealer_research": data["dealer_research"],
            })
            logger.info("[Tavily] CLIN %s saved -> %s (updates list size=%s)", clin_id, out_path.name, len(updates))
        except Exception as e:
            failed += 1
            logger.exception("[Tavily] CLIN %s failed: %s", clin_id, e)
            try:
                err_path = run_dir / f"clin_{clin_id}.json"
                with open(err_path, "w", encoding="utf-8") as f:
                    json.dump({"clin_id": clin_id, "error": str(e), "clin": clin}, f, indent=2, default=str)
            except Exception:
                pass
    logger.info("[Tavily] run_tavily_for_opportunity done opportunity_id=%s processed=%s failed=%s updates_count=%s",
        opportunity_id, processed, failed, len(updates))
    return {
        "opportunity_id": opportunity_id,
        "clins_processed": processed,
        "clins_failed": failed,
        "output_dir": str(run_dir),
        "updates": updates,
    }
