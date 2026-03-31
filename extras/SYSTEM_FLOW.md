# SAM.gov AI – Full System Flow (Detailed)

This document describes the end-to-end flow of the entire system: authentication, opportunity creation and processing, email/calendar integration, and deletion.

---

## 1. Architecture Overview

- **Frontend:** React (Vite), React Router, Axios. Pages: Login, Signup, AuthCallback, Dashboard, Analyze, OpportunityDetail, QuoteEmailsPreview.
- **Backend:** FastAPI, PostgreSQL (SQLAlchemy), Redis. API under `/api/v1` (auth, opportunities, db_utils).
- **Workers:** Celery with Redis broker. Tasks: `scrape_sam_gov_opportunity`, `analyze_documents`, `run_tavily_dealers_for_opportunity`.
- **External:** SAM.gov (scraping), Gmail/Outlook OAuth (email + calendar), Tavily API (dealer/manufacturer search).

---

## 2. Authentication Flow

### 2.1 Email (signup + verify + login)

1. **Signup** (`POST /auth/register`): User submits email, password, optional full name. Backend creates a user with `auth_provider=email`, stores password hash, sends a verification code by email (SMTP). No JWT yet.
2. **Verify** (`POST /auth/verify-email`): User submits email + code. Backend validates code and expiry, marks user verified, creates session, returns JWT access + refresh tokens. Frontend stores tokens and calls `GET /auth/me` to set user.
3. **Login** (`POST /auth/login`): Only for `auth_provider=email` and verified users. Backend checks password, creates session, returns JWT. Frontend stores tokens and loads user.

### 2.2 Google / Microsoft sign-in (OAuth)

1. **Sign-in** (no prior auth):
   - User clicks “Sign in with Google” or “Sign in with Microsoft”.
   - Frontend redirects to `GET /auth/signin/google` or `GET /auth/signin/microsoft`.
   - Backend creates an `OAuthState` row with `user_id=0`, stores state in cookie/session, redirects browser to provider with scopes that include **email + calendar** (Gmail send + Calendar for Google; Mail.Send + Calendars.ReadWrite for Microsoft).
   - User consents at provider and is redirected to backend `GET /auth/google/callback` or `GET /auth/microsoft/callback` with `code` and `state`.
   - Backend validates state, exchanges code for tokens, fetches user profile (email, name), calls `_find_or_create_oauth_user` (creates user with `auth_provider=google` or `microsoft` if new). If token response includes a **refresh_token**, backend creates/overwrites a **UserEmailConnection** for that user (provider, refresh_token, access_token, token_expires_at, sender_email). So the user gets Gmail/Outlook + calendar without a separate “Connect” step.
   - Backend creates session and JWT, redirects to frontend with tokens in URL fragment (e.g. `/#access_token=...&refresh_token=...`). Frontend (AuthCallback) reads fragment, stores tokens, redirects to dashboard.

2. **Connect** (user already logged in):
   - User is authenticated. Frontend redirects to `GET /auth/connect-google` or `GET /auth/connect-microsoft` with `?access_token=...` (or Bearer in header). Backend resolves user from token, creates `OAuthState` with `user_id=current_user.id`, redirects to provider with same email+calendar scopes.
   - Callback: state has `user_id != 0`. Backend exchanges code, then creates/overwrites **UserEmailConnection** for that user. Redirects to frontend with `?email_connected=google` (or microsoft). No new user account; only the connection is stored.

### 2.3 Session and tokens

- JWT access token is used for API calls (`Authorization: Bearer <token>`). Refresh token is stored for future refresh (if implemented).
- Backend can store **Session** rows (user_id, token, refresh_token, is_active, expires_at) and deactivate them on logout.
- **UserEmailConnection** is separate: one row per user for “send email / calendar” (Gmail or Outlook). Used by send-email and calendar-sync.

---

## 3. Opportunity Creation and Processing Flow

### 3.1 Create opportunity (frontend → API → Celery)

1. **Analyze page** (`/analyze`): User enters a SAM.gov opportunity URL, optionally enables “Document analysis” and “CLIN extraction”, and can attach files. On submit, frontend builds `FormData` (sam_gov_url, enable_document_analysis, enable_clin_extraction, files) and sends `POST /api/v1/opportunities` with Bearer token.

2. **Backend** (`POST /opportunities`):
   - Checks no existing opportunity with same `sam_gov_url`.
   - Creates **Opportunity** (user_id, sam_gov_url, status=`pending`, enable_document_analysis, enable_clin_extraction).
   - If files are provided: creates `data/uploads/{opportunity_id}/`, saves files to disk, creates **Document** rows (opportunity_id, file_path, file_type, source=USER_UPLOAD).
   - Queues Celery task: `scrape_sam_gov_opportunity.delay(opportunity_id)`.
   - Returns the new opportunity (e.g. 201). Frontend typically redirects to `/opportunities/:id` or dashboard.

### 3.2 Scrape SAM.gov (Celery)

1. **Task** `scrape_sam_gov_opportunity(opportunity_id)`:
   - Loads opportunity, sets status to `processing`.
   - Uses **SAMGovScraper** to scrape the SAM.gov page: metadata (title, notice_id, description, agency, primary_contact, alternative_contact, contracting_office_address, date_offers_due, etc.), attachments list, and raw page text for LLM.
   - Updates opportunity with metadata. If `date_offers_due` exists, creates a **Deadline** (offers_due).
   - **DocumentDownloader**: downloads each attachment to `backend/data/documents` (or configured storage), creates **Document** rows (source=SAM_GOV_ATTACHMENT, file_path, etc.).
   - Queues next task: `analyze_documents.delay(opportunity_id, enable_document_analysis, enable_clin_extraction, sam_gov_page_text)`.
   - Does **not** set status to `completed`; analyze_documents does that after analysis.

### 3.3 Analyze documents (Celery)

1. **Task** `analyze_documents(opportunity_id, enable_document_analysis, enable_clin_extraction, sam_gov_page_text)`:
   - Loads opportunity and its documents (including user uploads and SAM.gov attachments).
   - **Text extraction:** For each supported document (PDF, Word, Excel), uses **DocumentAnalyzer** (e.g. PyMuPDF, python-docx, openpyxl) to extract text. Saves debug extracts under `data/debug_extracts/opportunity_{id}/`.
   - **CLIN + deadline extraction (if enabled):** Builds a list of (doc_name, text) including **SAM.gov page text** as first “document”. Single LLM call: `analyzer.extract_clins_batch(document_texts)` returns batch_clins and batch_deadlines. Deduplicates CLINs by clin_number (merge fields) and deadlines by (date, type, time, timezone).
   - **Classification:** Classifies solicitation type (product/service/both) from combined text + title/description; sets opportunity.solicitation_type and classification_confidence.
   - **Persistence:** Inserts/updates **CLIN** rows (opportunity_id, clin_number, product_name, manufacturer_name, part_number, delivery info in additional_data, etc.). Inserts **Deadline** rows (due_date, due_time, timezone, deadline_type, description, is_primary).
   - Sets opportunity status to **completed**, commits.
   - If CLIN extraction was enabled and CLINs exist, queues: `run_tavily_dealers_for_opportunity.delay(opportunity_id)`.

### 3.4 Tavily dealer/manufacturer search (Celery)

1. **Task** `run_tavily_dealers_for_opportunity(opportunity_id)`:
   - Loads all CLINs for the opportunity. For each CLIN, runs **Tavily** (or equivalent) web search for manufacturer info and authorized dealers/distributors.
   - **tavily_dealers.run_tavily_for_opportunity** returns updates: per CLIN, `manufacturer_research` (e.g. official_website, sales_contact_email) and `dealer_research` (list of dealers with company_name, website_url, sales_contact_email, retail_pricing).
   - Backend updates each CLIN row with `manufacturer_research` and `dealer_research` (JSON), then commits. Data is persisted so the frontend can show it without re-running search.

---

## 4. Frontend: Viewing and Interacting with an Opportunity

### 4.1 Dashboard

- **GET /api/v1/opportunities**: List opportunities for the current user (filtered by user_id). Frontend shows cards with title, status, notice_id, deadline count, etc.
- User can open an opportunity (navigate to `/opportunities/:id`), delete one (with confirmation), or go to “Analyze” to add a new one.

### 4.2 Opportunity detail page (`/opportunities/:id`)

1. **Load:** `GET /api/v1/opportunities/:id` returns full opportunity with documents, deadlines, and CLINs (including manufacturer_research and dealer_research). Frontend stores it in state.

2. **Polling while processing:** If status is `pending` or `processing`, frontend starts a poll (e.g. every 3 s). When status becomes `completed`, it stops and may do one delayed fetch to ensure CLINs/deadlines are present.

3. **Dealers/manufacturers loading:** If status is `completed`, there are CLINs, but no CLIN has manufacturer_research or dealer_research yet, frontend shows “Finding dealers and manufacturers…” and polls the same GET every 5 s (max 2 min) until at least one CLIN has research, then shows results.

4. **UI sections:** Title (teal card with optional texture), contact block, deadlines (with “Add to Calendar” if email connected), description, CLINs table (expandable rows with product details, manufacturer/dealer blocks, “Find manufacturers & dealers” lookup links). Sidebar: documents (view/download), email/calendar connection (Connect Gmail/Outlook, Disconnect), delivery requirements if present.

5. **Add to Calendar:** Button visible when user has a connected email (Gmail/Outlook). On click, frontend calls `POST /api/v1/opportunities/:id/sync-calendar`. Backend loads user’s **UserEmailConnection**, loads opportunity deadlines, and for each deadline without a stored `calendar_event_id` creates an event in Google Calendar or Microsoft Outlook via **calendar_sync** service, then saves `calendar_event_id` and `calendar_provider` on the **Deadline** row. Response returns how many events were created. Frontend refetches opportunity so “In calendar” badges appear.

6. **Generate quote emails:** If any CLIN has dealer or manufacturer contact emails, a “Generate Quote Emails” button appears in the CLINs section. It navigates to `/opportunities/:id/quote-emails`.

### 4.3 Quote emails preview (`/opportunities/:id/quote-emails`)

1. **Load:** Fetches opportunity and email connection status. From opportunity CLINs, builds a list of **draft emails**: one per dealer/manufacturer that has `sales_contact_email` (normalizing manufacturer_research and dealer_research from API).

2. **Templates:** Each draft gets a subject and body from **generateEmailTemplate**: product specs (name, manufacturer, part number, quantity), delivery address, delivery deadline, request for datasheets and Net payment terms; tone is professional, “We’re currently working on a project and would like to request a quote,” no government/solicitation references.

3. **Review:** All drafts are shown with recipient name/email, subject, and full body. User can **edit** any subject/body, **approve** (checkbox) which to send, and **discard** (remove from list). No email is sent until the user clicks send.

4. **Send:** User selects approved emails and clicks “Send X approved”. Frontend calls `POST /api/v1/auth/send-email` for each (to, subject, body). Backend uses **UserEmailConnection** and **email_sender** (Gmail API or Microsoft Graph) to send from the user’s connected account. Sent emails are removed from the list; success/error is shown.

---

## 5. Email and Calendar Backend Details

### 5.1 Sending email

- **POST /api/v1/auth/send-email**: Body: to, subject, body. Requires auth; loads **UserEmailConnection** for current user. **email_sender.send_email_as_user(conn, to, subject, body)** uses Gmail API (google-api-python-client) or Microsoft Graph (requests) with token refreshed via google-auth or msal. No per-opportunity email storage; mail is sent through the user’s account.

### 5.2 Calendar sync

- **Create events:** **calendar_sync.sync_deadlines_to_calendar(conn, deadlines, opportunity_title)** creates one event per deadline (no duplicate if deadline already has calendar_event_id). Google: Calendar API v3 `events().insert(calendarId='primary', body)`. Microsoft: `POST /me/events`. Each deadline row is updated with `calendar_event_id` and `calendar_provider`.
- **Delete events (on opportunity delete):** Before deleting the opportunity, backend loads deadlines and user’s **UserEmailConnection**, then **calendar_sync.delete_calendar_events_for_deadlines(conn, deadlines)** deletes each event by id from Google/Microsoft so the user’s calendar is cleaned up.

### 5.3 Connecting email and calendar later

If the user runs analysis **without** connecting Gmail or Outlook, nothing is lost. Email/calendar is optional and stored per user, not per opportunity.

- **When they connect later** (from Dashboard or from any opportunity's "Email and calendar" block): the backend creates/overwrites **UserEmailConnection** for that user. From then on, for **all** of that user's opportunities (existing and new):
  - **Add to Calendar** becomes available: they can open any opportunity and click "Add to Calendar"; the app creates events for that opportunity's deadlines and stores `calendar_event_id` on each deadline.
  - **Quote emails**: if CLINs have dealer/manufacturer contact emails, "Generate Quote Emails" appears; they can review and send from the connected account.
- **Existing opportunities** do not need to be re-analyzed. Deadlines and CLINs are already in the database; connecting only enables the calendar and email features for those same opportunities.
- So: connect at any time; the only requirement is that the user is logged in. No re-scrape or re-analysis is required.

---

## 6. Deleting an Opportunity

1. **Frontend:** User triggers delete (e.g. from dashboard or detail page). Frontend calls `DELETE /api/v1/opportunities/:id`.

2. **Backend** `delete_opportunity`:
   - Loads opportunity (must belong to current user), documents, CLINs, deadlines.
   - **Calendar:** Loads **UserEmailConnection** for current user. For each deadline that has `calendar_event_id`, calls Google or Microsoft API to **delete** that event; then continues (no DB delete of deadlines yet).
   - **Files:** Deletes each document’s file from disk (resolving path from PROJECT_ROOT / STORAGE_BASE_PATH). Then deletes known directories: documents dir for this opportunity_id, uploads dir, debug_extracts/opportunity_{id}, and temp patterns under data.
   - **Database:** Deletes the **Opportunity** row. CASCADE deletes related **Document**, **Deadline**, and **CLIN** rows.
   - Returns 204. Frontend navigates to dashboard or refreshes list.

So on delete: **calendar events** are removed from the user’s calendar, **all related files** (uploads, downloaded attachments, debug extracts) are removed from disk, and **all related data** (documents, deadlines, CLINs, opportunity) are removed from the database. Email is not stored per opportunity; only the calendar and file/DB cleanup are done.

---

## 7. Data Model (Summary)

- **users:** id, email, auth_provider (email | google | microsoft), password_hash, full_name, role, is_active, is_verified, verification_code, etc.
- **sessions:** user_id, token, refresh_token, is_active, expires_at (optional).
- **user_email_connections:** user_id, provider (google | microsoft), refresh_token, access_token, token_expires_at, sender_email. One row per user for sending email and calendar.
- **oauth_states:** state, user_id (0 for sign-in, else for connect), provider; short-lived for OAuth callbacks.
- **opportunities:** id, user_id, sam_gov_url, status (pending | processing | completed | failed), title, description, notice_id, agency, primary_contact, alternative_contact, contracting_office_address, solicitation_type, classification_confidence, enable_document_analysis, enable_clin_extraction, error_message, etc.
- **documents:** opportunity_id, file_path, file_name, file_type, source (USER_UPLOAD | SAM_GOV_ATTACHMENT), etc.
- **deadlines:** opportunity_id, due_date, due_time, timezone, deadline_type, description, is_primary, is_passed, **calendar_event_id**, **calendar_provider**.
- **clins:** opportunity_id, clin_number, product_name, manufacturer_name, part_number, quantity, additional_data (delivery_address, delivery_timeline, etc.), **manufacturer_research**, **dealer_research** (JSON).

---

## 8. Flow Diagram (High Level)

```
[User] --> Login/Signup (email or Google/Microsoft OAuth)
    --> Dashboard --> List opportunities
    --> Analyze --> POST /opportunities (URL + options + files)
        --> Backend creates Opportunity, queues scrape_sam_gov_opportunity
        --> Celery: scrape SAM.gov, download attachments, queue analyze_documents
        --> Celery: extract text, extract CLINs+deadlines (LLM), classify, save CLINs/deadlines, queue run_tavily_dealers_for_opportunity
        --> Celery: Tavily search per CLIN, save manufacturer_research + dealer_research
    --> Opportunity Detail: GET opportunity, poll if processing, show deadlines/CLINs/documents
        --> Add to Calendar: POST sync-calendar --> create events in Google/Outlook, persist event ids on deadlines
        --> Generate Quote Emails --> Quote Emails Preview: review/edit/approve/discard --> Send approved (POST send-email per email)
    --> Delete opportunity: DELETE /opportunities/:id
        --> Backend: delete calendar events, delete files, delete opportunity (CASCADE documents, deadlines, CLINs)
```

This is the full flow of the entire system in detail.
