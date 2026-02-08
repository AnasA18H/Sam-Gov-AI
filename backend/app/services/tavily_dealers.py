"""
Tavily web search: find manufacturer and dealers per CLIN (runs after CLIN extraction).
Uses tavily-python with search_depth=advanced, max_results=10, include_answer=True.
"""
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.config import settings

logger = logging.getLogger(__name__)

TAVILY_SEARCH_DEPTH = "advanced"
TAVILY_MAX_RESULTS = 10
TAVILY_INCLUDE_ANSWER = True


def build_search_queries_for_clin(clin: Dict[str, Any]) -> List[str]:
    """Build Tavily search queries: 1 manufacturer-focused, rest dealer-focused (target 8+ dealers)."""
    mfr = (clin.get("manufacturer_name") or "").strip()
    product = (clin.get("product_name") or "").strip()
    part = (clin.get("part_number") or "").strip()
    queries: List[str] = []
    if mfr or product:
        q = f"{mfr} {product} official manufacturer website contact support".strip()
        if q and q not in queries:
            queries.append(q)
    for template in [
        f"{product} {part} authorized dealers list where to buy",
        f"{mfr} {product} authorized dealers distributors USA",
        f"{product} dealers near me buy",
        f"{mfr} {product} dealers retailers",
    ]:
        q = template.strip()
        if q and q not in queries and (mfr or product or part):
            queries.append(q)
    return queries[:5]


def _search_with_tavily_client(api_key: str, query: str) -> Dict[str, Any]:
    """Run one Tavily search via TavilyClient."""
    from tavily import TavilyClient

    client = TavilyClient(api_key=api_key)
    try:
        response = client.search(
            query,
            search_depth=TAVILY_SEARCH_DEPTH,
            max_results=TAVILY_MAX_RESULTS,
            include_answer=TAVILY_INCLUDE_ANSWER,
        )
    except TypeError:
        response = client.search(
            query=query,
            search_depth=TAVILY_SEARCH_DEPTH,
            max_results=TAVILY_MAX_RESULTS,
            include_answer=TAVILY_INCLUDE_ANSWER,
        )
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
    queries = build_search_queries_for_clin(clin)
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
    return {
        "clin": {k: v for k, v in clin.items() if v is not None},
        "queries": queries,
        "searches": searches,
        "search_depth": TAVILY_SEARCH_DEPTH,
        "max_results": TAVILY_MAX_RESULTS,
        "include_answer": TAVILY_INCLUDE_ANSWER,
    }


def run_tavily_for_opportunity(
    opportunity_id: int,
    clins: List[Dict[str, Any]],
    output_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Run Tavily for each CLIN and save one JSON per CLIN under output_dir/opportunity_{id}/clin_{id}.json.
    Returns summary: { "opportunity_id", "clins_processed", "clins_failed", "output_dir" }.
    """
    api_key = getattr(settings, "TAVILY_API_KEY", None) or ""
    if not api_key:
        logger.warning("TAVILY_API_KEY not set; skipping Tavily dealer search for opportunity %s", opportunity_id)
        return {
            "opportunity_id": opportunity_id,
            "skipped": True,
            "reason": "TAVILY_API_KEY not set",
            "clins_processed": 0,
            "clins_failed": 0,
        }
    out_dir = output_dir or (settings.DATA_DIR / "tavily_results")
    run_dir = out_dir / f"opportunity_{opportunity_id}"
    run_dir.mkdir(parents=True, exist_ok=True)
    processed = 0
    failed = 0
    for i, clin in enumerate(clins):
        clin_id = clin.get("id", i + 1)
        try:
            data = run_tavily_for_clin(api_key, clin)
            out_path = run_dir / f"clin_{clin_id}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
            processed += 1
            logger.info("Tavily results saved for opportunity %s CLIN %s -> %s", opportunity_id, clin_id, out_path.name)
        except Exception as e:
            failed += 1
            logger.exception("Tavily search failed for opportunity %s CLIN %s: %s", opportunity_id, clin_id, e)
            try:
                err_path = run_dir / f"clin_{clin_id}.json"
                with open(err_path, "w", encoding="utf-8") as f:
                    json.dump({"clin_id": clin_id, "error": str(e), "clin": clin}, f, indent=2, default=str)
            except Exception:
                pass
    return {
        "opportunity_id": opportunity_id,
        "clins_processed": processed,
        "clins_failed": failed,
        "output_dir": str(run_dir),
    }
