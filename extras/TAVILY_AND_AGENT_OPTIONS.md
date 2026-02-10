# Tavily Search & Agent Options (Current vs LangGraph)

## Current implementation

- **Tavily**: Used via `tavily-python` (`TavilyClient`). All search arguments come from **config** (no hardcoding):
  - `TAVILY_SEARCH_DEPTH` (basic | advanced)
  - `TAVILY_MAX_RESULTS`
  - `TAVILY_INCLUDE_ANSWER`
  - `TAVILY_MAX_QUERIES_PER_CLIN`
  - Optional: `TAVILY_INCLUDE_DOMAINS`, `TAVILY_TIME_RANGE`
- **Query generation**: **Generic** – an LLM generates 4–N search queries from the CLIN (manufacturer, product, part, description). No fixed phrase templates in code. Fallback: 1–3 queries built from non-empty CLIN fields only.
- **Flow**: For each CLIN → generate queries (LLM) → run one Tavily search per query → concatenate results → one LLM call to extract structured manufacturer_research + dealer_research → save and persist.
- **Extraction**: Single LLM call with a fixed output schema (manufacturer_research, dealer_research). Emails are validated and URLs normalized.

## When the current implementation is enough

- You want **predictable cost and latency**: fixed number of searches per CLIN, one extraction call.
- You don’t need **iterative search** (e.g. “found dealer X but no email → search again for X’s contact”).
- **Batch processing** (one opportunity, many CLINs) is the main use case and a linear pipeline is fine.
- You’re fine tuning behavior via **config and prompts** (Tavily params, max queries, LLM prompt for query generation and extraction) without changing code.

## When a LangGraph agent helps

- **Multi-step reasoning**: The agent can decide to run more Tavily searches based on what it already found (e.g. “I have a dealer name but no email → call Tavily again with a query for that dealer’s contact”).
- **Tool use**: Tavily is one tool; the agent can also call other tools (e.g. “get page content”, “look up CAGE code”) in one graph.
- **State machine**: Clear nodes (e.g. “generate_queries” → “search” → “extract” → “decide: need_more_searches?” → loop or “format_output”). Easier to add branches (e.g. “if no dealers found, try alternate query strategy”).
- **Observability**: LangGraph can give a visible graph of which steps ran and with what state; useful for debugging and tuning.

## Using LangChain-Tavily + LangGraph (if you add an agent later)

- **Install**: `langchain-tavily`, `langgraph` (and your LLM package, e.g. `langchain-anthropic`).
- **Tavily as a tool**: Use the Tavily integration (e.g. `TavilySearchResults` or the tool from `langchain-tavily`) so the agent can call search with **arguments** (query, and optionally search_depth, max_results, etc. from your config). Pass Tavily params from settings into the tool constructor or bind so they stay config-driven.
- **Agent**: Build a LangGraph that (1) has a node that can invoke the Tavily tool (and any other tools), (2) uses an LLM to decide the next step (e.g. “call Tavily with this query” or “extract and finish”), (3) keeps state (accumulated search results, partial manufacturer/dealer list), (4) ends when the agent decides to output the final structured result.
- **Stay generic**: Drive Tavily parameters (search_depth, max_results, include_domains, time_range, etc.) from config or env, not from hardcoded literals. Use the same output schema (manufacturer_research, dealer_research) so the rest of your app (DB, frontend) stays unchanged.

## Recommendation

- **Keep the current implementation** for production if it already gives good coverage and you don’t need iterative “search again based on results.” It’s simpler to operate and reason about.
- **Make it generic** (done): Tavily params from config; queries from LLM (with a minimal fallback). No hardcoded query templates.
- **Consider LangGraph** when you need: (1) “search again for this specific dealer’s email,” (2) multiple tools in one flow, or (3) a clear, debuggable state machine for research steps. Then integrate `langchain-tavily` as the search tool and keep all Tavily arguments config-driven.
