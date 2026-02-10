# Tavily Results Flow and Review

## Flow (end-to-end)

1. **Trigger**  
   After CLIN extraction completes (`analyze_documents` task), the app queues `run_tavily_dealers_for_opportunity` with the opportunity id.

2. **Celery task** (`tasks.run_tavily_dealers_for_opportunity`)  
   - Loads CLINs from DB for that opportunity.  
   - Builds a list of dicts: `id`, `clin_number`, `product_name`, `product_description`, `manufacturer_name`, `part_number`, `model_number`.  
   - Calls `run_tavily_for_opportunity(opportunity_id, clins_list)`.

3. **Tavily search** (`tavily_dealers.run_tavily_for_opportunity`)  
   - For each CLIN, `build_search_queries_for_clin()` builds up to 8 queries (manufacturer/product + “sales contact email”, “authorized dealers”, etc.).  
   - Each query is sent to Tavily API (`search_depth=advanced`, `max_results=12`, `include_answer=True`).  
   - Raw result per CLIN: `{ "clin", "queries", "searches" }` (each search has `query`, `results[]`, `answer`).

4. **LLM extraction** (`_extract_manufacturer_and_dealers_from_tavily`)  
   - Builds a text context from all searches (query + answer + top 6 result snippets per search).  
   - Sends to Claude (Anthropic) or Groq with a structured prompt.  
   - Asks for:  
     - **manufacturer_research**: `official_website`, `sales_contact_email`  
     - **dealer_research**: up to 8 dealers with `company_name`, `website_url`, `sales_contact_email`, `retail_pricing`.  
   - Parses JSON from the reply; validates/normalizes emails; caps dealers at 8.

5. **Save to disk**  
   - Full payload (raw Tavily + `manufacturer_research` + `dealer_research`) is written to:  
     `data/tavily_results/opportunity_{id}/clin_{clin_id}.json`.

6. **Persist to DB**  
   - Task updates each CLIN row: `manufacturer_research`, `dealer_research` (JSON columns).  
   - Commits once after all CLINs for that opportunity.

7. **Logs**  
   - `[Tavily] run_tavily_for_opportunity start/done`, per-CLIN progress, `[Tavily] CLIN id: running LLM extraction`, `extracted mfr_website=... mfr_email=... dealers_count=...`, `saved -> clin_*.json`, `[Tavily task] updated CLIN id=...`, `committed: persisted ... for N CLINs`.

---

## Example: `data/tavily_results/opportunity_236/clin_331.json`

- **CLIN**: Bureau of Engraving and Printing, “SOI Stack & Rack Carts”.  
- **Queries**: 7 (e.g. “Bureau of Engraving and Printing SOI Stack & Rack Carts sales contact email quote request government”, “authorized dealers distributors contact email quote USA”, etc.).  
- **Searches**: Rich results (snippets + Tavily “answer”).  
- **Final extracted**  
  - **manufacturer_research**:  
    - `official_website`: `"www.bep.gov"`  
    - `sales_contact_email`: `"moneyfactory.sales@bep.gov"`  
  - **dealer_research**:  
    - One dealer: “Allied Materials and Equipment Company Inc.” with `website_url`, `sales_contact_email`, `retail_pricing` all `null`.

---

## Issues identified

### 1. **“Manufacturer” is actually the government buyer (critical)**

- CLIN has `manufacturer_name: "Bureau of Engraving and Printing"`.  
- BEP is the **agency (buyer)**, not the manufacturer of the carts.  
- So:  
  - All Tavily queries are about “Bureau of Engraving and Printing” and return BEP/solicitation contact (e.g. ariel.dillon@bep.gov, moneyfactory.sales@bep.gov).  
  - The AI correctly extracted from snippets but labeled the **buyer’s** site and email as “manufacturer” research.  
- **Effect**: Wrong semantic meaning; user gets government contact, not cart manufacturer/dealer contacts.  
- **Recommendation**:  
  - Either detect known government agencies (e.g. “Bureau of Engraving”, “GSA”, “DOD”) and treat as “buyer/agency” not “manufacturer”, or  
  - Add a flag/source in the UI so “manufacturer” research can be clearly “agency contact” when the “manufacturer” field is the buying office.

### 2. **`official_website` stored without scheme**

- Value is `"www.bep.gov"` instead of `"https://www.bep.gov"`.  
- **Effect**: Links may not be clickable or may be treated as relative.  
- **Fix**: Normalize URLs to `https://` when the value is a bare hostname (e.g. `www.bep.gov` → `https://www.bep.gov`). Implemented in code.

### 3. **Dealer with no contact info**

- Allied Materials and Equipment Company Inc. appears in a sole-source notice (SAM.gov) but the snippets don’t contain their website or email; LLM correctly returned `null`.  
- **Effect**: One dealer row with no actionable contact.  
- **Recommendation**: Accept as limitation of search results; optional future improvement: extra Tavily query per dealer name to find company website/contact.

### 4. **Flow and persistence**

- Flow is correct: Tavily → JSON file (full payload) → LLM extraction → same file updated → DB UPDATE on `clins.manufacturer_research` and `clins.dealer_research`.  
- Logs in `logs/celery.log` match this (task received, CLINs loaded, Tavily run, LLM extraction, file saved, UPDATE, COMMIT).  
- No issues found in the flow itself.

### 5. **Error handling**

- Missing `TAVILY_API_KEY`: task returns early with `skipped: True`; no crash.  
- LLM/JSON failure: warning logged; empty `manufacturer_research` / `dealer_research` returned; file still has raw Tavily data.  
- Optional improvement: on JSON parse failure, log a short snippet of the raw LLM response (e.g. first 500 chars) to debug bad formats. Implemented in code.

---

## Summary

- **Flow**: Tavily results → saved to `data/tavily_results/...` → LLM extraction → same JSON updated → DB CLIN rows updated. Logging and persistence are correct.  
- **Main issue**: When “manufacturer” is really the government buyer (e.g. BEP), the system returns buyer contact as “manufacturer” research; logic or UX should distinguish buyer vs actual product manufacturer.  
- **Small fixes applied**: (1) Normalize `official_website` to `https://` when it’s a bare hostname. (2) On LLM JSON parse failure, log a snippet of the raw response for debugging.
