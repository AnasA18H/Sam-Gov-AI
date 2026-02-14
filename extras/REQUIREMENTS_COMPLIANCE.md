# Requirements Compliance Checklist

This document maps the application against the provided requirements. **Done** = implemented; **Gap** = missing or partial; **Note** = clarification.

---

## 1. Application Startup Workflow (CRITICAL)

| Requirement | Status | Notes |
|-------------|--------|--------|
| When app is launched, **immediately** present user with primary input (SAM.gov URL) | **Gap** | App default route is `/` → redirect to **Dashboard**. The SAM.gov URL input is on **Analyze** (`/analyze`). User must click "Analyze" from Dashboard to reach it. **Suggestion:** Consider making `/analyze` the default post-login route so the first screen is URL + optional upload + Begin Analysis. |
| **Primary input:** SAM.gov solicitation URL (required) | **Done** | Analyze page: required URL field, validated for `sam.gov`. |
| **Secondary optional:** “Upload additional PDF documents related to this solicitation” | **Done** | Analyze page: optional file upload; accepts PDF, DOC, DOCX, XLS, XLSX. |
| **Begin Analysis** button; flow: URL → (optional uploads) → Analyze → extraction/research/processing | **Done** | Single “Begin Analysis” submit; creates opportunity, starts scraping + analysis (and optional document analysis/CLIN extraction). |

---

## 2. Document Input Methods

| Requirement | Status | Notes |
|-------------|--------|--------|
| **SAM.gov (primary):** Accept SAM.gov opportunity URL, analyze page, **automatically download all attached documents** | **Done** | Scraper fetches page, extracts attachments, DocumentDownloader downloads and stores them. |
| **Optional supplemental upload:** Accept additional solicitation documents (PDF/Word) | **Done** | Analyze form: multipart upload of files; backend stores as documents for the opportunity. |

---

## 3. Solicitation Type Classification (REQUIRED)

| Requirement | Status | Notes |
|-------------|--------|--------|
| Automatically classify as: **Product** / **Service** / **Both** | **Done** | `DocumentAnalyzer.classify_solicitation_type()`; enum `PRODUCT`, `SERVICE`, `BOTH`, `UNKNOWN`. |
| **Display classification prominently** in analysis results | **Done** | Opportunity detail: `solicitation_type` shown next to Description (e.g. “product” badge). Could be made more prominent (e.g. in summary card at top). |

---

## 4. Deadline Extraction

| Requirement | Status | Notes |
|-------------|--------|--------|
| Capture **submission due date and time** | **Done** | Deadlines from scraping metadata + batch LLM extraction; stored with `due_date`, `due_time`. |
| **Include timezone** if specified | **Done** | `Deadline.timezone` stored and displayed (e.g. EST). |
| Extract **all** deadlines (e.g. questions due, quotes due) | **Done** | Prompts ask for all deadlines; types: `questions_due`, `offers_due`, `submission`, `other`; dedup and normalization in place. |

---

## 5. Product/Service Details (CLIN Analysis)

| Requirement | Status | Notes |
|-------------|--------|--------|
| Product name and description | **Done** | CLIN: `product_name`, `product_description` (and `clin_name`). |
| Manufacturer name | **Done** | CLIN: `manufacturer_name`. |
| Part/model number | **Done** | CLIN: `part_number`, `model_number`. |
| Quantity required | **Done** | CLIN: `quantity`, `unit_of_measure`. |
| For services: **scope of work, timeline, service requirements** | **Done** | CLIN: `scope_of_work`, `timeline` (and delivery_timeline in additional_data), `service_requirements`. |

---

## 6. Delivery Requirements

| Requirement | Status | Notes |
|-------------|--------|--------|
| Complete delivery address | **Done** | Extracted per CLIN (`additional_data.delivery_address`) and shown on CLIN cards; also used in quote email body. |
| Special delivery instructions | **Done** | Per CLIN: `additional_data.special_delivery_instructions`. |
| Required delivery date | **Done** | Per CLIN: `additional_data.delivery_timeline` and `timeline`. |
| Opportunity-level “Delivery Requirements” section in UI | **Partial** | Frontend has a block for `classification_codes.delivery_requirements` (address, FOB, timeline, etc.). That JSON is not currently populated by the scraper or document analyzer; delivery data is at CLIN level. |

---

## 7. Manufacturer Research (Automated)

| Requirement | Status | Notes |
|-------------|--------|--------|
| Find manufacturer’s **official website** | **Done** | Tavily-based research; `manufacturer_research`: `official_website`. |
| Locate and extract **sales team contact email** | **Done** | `manufacturer_research`: `sales_contact_email`. |

---

## 8. Dealer/Distributor Research (Automated)

| Requirement | Status | Notes |
|-------------|--------|--------|
| Identify **top 8** authorized dealers/distributors/service providers | **Done** | Tavily prompt: “Include up to 8 dealers.” |
| Company name | **Done** | `dealer_research`: `company_name`. |
| Website URL | **Done** | `dealer_research`: `website_url`. |
| Sales contact email | **Done** | `dealer_research`: `sales_contact_email`. |
| Current retail pricing (if publicly available) | **Done** | `dealer_research`: `retail_pricing`. |

---

## 9. Email Template Generation with Review

| Requirement | Status | Notes |
|-------------|--------|--------|
| Auto-generate professional quote inquiry emails with: product specs (name, manufacturer, part number, quantity) | **Done** | `quote_email_drafts._template()` builds subject/body with these fields. |
| Delivery address for shipping calculations | **Done** | Included in body from CLIN `additional_data.delivery_address`. |
| Required delivery deadline | **Done** | From `delivery_timeline` / `timeline`. |
| Request for product datasheets/spec sheets | **Done** | Body: “Product datasheets/specification sheets”. |
| Request for **Net payment terms** | **Done** | Body: “Net payment terms”. |
| **Tone:** Opening “Hello, We’re currently working on a project and would like to request a quote” | **Done** | Body starts with “We're currently working on a project and would like to request a quote for the following:”. |
| Strategic language (evaluating multiple competitive quotes) | **Done** | “Please provide your competitive quote… We are evaluating multiple options…”. |
| Professional, relaxed, assertive; **never reference government contracts or solicitations** | **Done** | Template has no government/solicitation wording; commercial inquiry only. |
| **Review process:** Present ALL generated emails before sending | **Done** | Quote Emails Preview page lists all drafts. |
| Display: recipient name and email, subject, full body | **Done** | Each draft shows to/name, subject, body (expandable). |
| **Edit capability** for each email | **Done** | Inline edit for to, to name, subject, body; “Done” saves via API. |
| User can **approve** individual emails / **select which to send** (checkboxes) | **Done** | Checkboxes per email; only selected are sent. |
| **Send all approved in batch** | **Done** | “Send selected” sends selected drafts via Gmail/Outlook, then deletes those drafts. |
| **NO emails sent without explicit user approval** | **Done** | Sending only via user action on Quote Emails Preview after review; no auto-send. |

---

## 10. Email Integration (REQUIRED)

| Requirement | Status | Notes |
|-------------|--------|--------|
| **Gmail** (full OAuth) | **Done** | Sign-in and Connect; Gmail send scope; send via Gmail API. |
| **Microsoft Outlook** (full OAuth) | **Done** | Sign-in and Connect; Mail.Send scope; send via Microsoft Graph. |
| Purpose: send quote inquiry emails from user’s account **after** user review and approval | **Done** | Sending only after user selects and confirms on Quote Emails Preview. |

---

## 11. Calendar Integration (REQUIRED)

| Requirement | Status | Notes |
|-------------|--------|--------|
| **Google Calendar** | **Done** | OAuth includes calendar scope; events created on user’s primary calendar. |
| **Microsoft Outlook Calendar** | **Done** | Graph Calendars.ReadWrite; events created in user’s Outlook calendar. |
| **Apple iCal / iCloud Calendar / iPhone Calendar** | **Gap** | No native Apple Calendar OAuth or API integration. Users can use Google or Outlook on their devices (e.g. Outlook/Google on iPhone) so deadlines still appear there; direct iCal/iCloud/iPhone-only integration is not implemented. |
| Purpose: automatically create calendar events for **extracted solicitation due dates/deadlines** | **Done** | “Add to Calendar” syncs opportunity deadlines to connected Google or Outlook calendar; event IDs stored to avoid duplicates. |

---

## Summary

- **Fully met:** Application workflow (except default landing), document inputs, classification, deadlines, CLIN and delivery data, manufacturer/dealer research (incl. top 8), email template content and tone, full review/edit/approve/send flow, Gmail/Outlook email and calendar.
- **Gaps / improvements:**
  1. **Initial screen:** Requirement says the app must “immediately” show SAM.gov URL input; currently the default is Dashboard. Making **Analyze** the default (or first post-login) screen would align with that.
  2. **Apple/iCal/iCloud/iPhone Calendar:** Only Google and Outlook are integrated; no direct Apple Calendar API.
  3. **Classification prominence:** Solicitation type is shown; could be moved to a more prominent place (e.g. summary card at top of opportunity detail).
  4. **Opportunity-level delivery_requirements:** UI block exists; data is not filled from scraper/analyzer (delivery is per CLIN). Optional enhancement: aggregate or copy from CLINs into `classification_codes.delivery_requirements` if desired.
