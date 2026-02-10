"""
Tavily web search: find manufacturer and dealers per CLIN (runs after CLIN extraction).
Extracts: manufacturer official website + sales contact email; up to 8 dealers with name, URL, email, pricing.
All Tavily params and query generation are config-driven or LLM-generated (no hardcoded query templates).
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
            llm = ChatAnthropic(
                model_name=getattr(settings, "ANTHROPIC_MODEL", "claude-3-sonnet-20240229"),
                temperature=0,
                api_key=SecretStr(settings.ANTHROPIC_API_KEY),
                timeout=60,
                stop=None,
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
    - Manufacturer: official_website, sales_contact_email
    - Up to 8 dealers: company_name, website_url, sales_contact_email, retail_pricing (if available)
    Returns { "manufacturer_research": {...}, "dealer_research": [...] } or empty on failure.
    """
    empty = {
        "manufacturer_research": {"official_website": None, "sales_contact_email": None},
        "dealer_research": [],
    }
    clin_info = tavily_result.get("clin") or {}
    mfr = (clin_info.get("manufacturer_name") or "").strip()
    product = (clin_info.get("product_name") or "").strip()
    context = _build_tavily_context_for_llm(tavily_result)
    if not context.strip():
        return empty

    prompt = f"""You are extracting structured research from web search results for a government contract line item (CLIN). The goal is to find manufacturer and authorized dealers with website and contact email for quote requests and outreach.

CLIN context: manufacturer="{mfr}", product="{product}"

Web search results (queries, answers, and result snippets). Each result has "Title | URL" then snippet text:
---
{context}
---

RULES:
1) manufacturer_research:
   - official_website: manufacturer's official site URL from the results, or null.
   - sales_contact_email: one real email (e.g. sales@company.com) for quote/contact; null if not found. No URLs or /cdn-cgi/ links.

2) dealer_research (authorized dealers/distributors for quote requests). For EACH dealer:
   - company_name: string (dealer/distributor name).
   - website_url: REQUIRED when possible. Use the result URL (the "| https://..." part) that clearly belongs to that dealer—i.e. the link of the page where that dealer is mentioned. If the snippet is about "Allied Materials" and the result URL is https://alliedmaterials.com/..., set website_url to that URL. Only use null if no result URL clearly refers to that company.
   - sales_contact_email: dealer's contact/sales email for quote requests (e.g. sales@dealer.com). Extract from snippet (e.g. "email: x@y.com", "contact@", "sales@"). Null if only a contact form or no email found.
   - retail_pricing: string or null if visible (e.g. "$X.XX" or "from $Y").

Prioritize dealers where you have both website_url and sales_contact_email. Include up to 8 dealers clearly identified in the results. Always set website_url from the result URL when the result is about that dealer.
Output ONLY a single valid JSON object (no markdown, no explanation):
{{"manufacturer_research": {{"official_website": "...", "sales_contact_email": "..."}}, "dealer_research": [{{"company_name": "...", "website_url": "...", "sales_contact_email": "...", "retail_pricing": "..."}}, ...]}}
"""

    llm = None
    if ANTHROPIC_AVAILABLE and ChatAnthropic is not None and getattr(settings, "ANTHROPIC_API_KEY", None):
        try:
            llm = ChatAnthropic(
                model_name=getattr(settings, "ANTHROPIC_MODEL", "claude-3-sonnet-20240229"),
                temperature=0,
                api_key=SecretStr(settings.ANTHROPIC_API_KEY),
                timeout=None,
                stop=None,
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
        if not isinstance(m, dict):
            m = empty["manufacturer_research"]
        if not isinstance(d, list):
            d = []
        # Cap dealers at 8 and ensure each has required keys; validate emails
        dealers = []
        def _normalize_url(u: Optional[str]) -> Optional[str]:
            if not u or not isinstance(u, str):
                return None
            u = u.strip() or None
            if not u:
                return None
            if not u.startswith(("http://", "https://")):
                return "https://" + u.lstrip("/")
            return u

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
        mfr_email = (str(m.get("sales_contact_email") or "").strip()) or None
        official_website = (m.get("official_website") or "").strip() or None
        if official_website and not official_website.startswith(("http://", "https://")):
            official_website = "https://" + official_website.lstrip("/")
        return {
            "manufacturer_research": {
                "official_website": official_website,
                "sales_contact_email": _normalize_email(mfr_email),
            },
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
                data["manufacturer_research"] = extracted.get("manufacturer_research") or {"official_website": None, "sales_contact_email": None}
                data["dealer_research"] = extracted.get("dealer_research") or []
            else:
                data["manufacturer_research"] = {"official_website": None, "sales_contact_email": None}
                data["dealer_research"] = []
            mfr = data.get("manufacturer_research") or {}
            dealers = data.get("dealer_research") or []
            logger.info("[Tavily] CLIN %s: extracted mfr_website=%s mfr_email=%s dealers_count=%s",
                clin_id, bool(mfr.get("official_website")), bool(mfr.get("sales_contact_email")), len(dealers))
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
