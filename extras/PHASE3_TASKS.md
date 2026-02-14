# Phase 3: Document Editing and Form Autofill — Task Breakdown

## Requirements Summary

| Requirement | Description |
|-------------|-------------|
| **In-app PDF and Word editing** | Users can open, view, and edit PDF and DOCX documents within the app (no download-edit-upload round-trip). |
| **Autofill SF1449 and other government forms** | Use extracted opportunity data (contacts, deadlines, CLINs, agency, etc.) to prefill standard government forms. SF1449 is the primary form; design allows adding more forms later. |
| **Save and load documents** | Edited and autofilled documents are stored in the platform and can be reopened, re-edited, or downloaded. |

**Out of scope for this phase (per user):** Export to JSON/CSV, UI/UX polish for form editing/review — already done or not needed.

---

## External API: Adobe PDF Services (Acrobat-style)

PDF editing and form filling will use **Adobe PDF Services API** (same family as Acrobat) so we get Acrobat-quality form handling and optional editing features.

### Operations we use

| Operation | Purpose | When |
|-----------|---------|------|
| **Import PDF Form Data** (`setformdata`) | Fill PDF form fields with a JSON key-value map; returns filled PDF. | Autofill SF1449; save after user edits form fields in our UI. |
| **Export PDF** (optional) | Export PDF to Word/Excel/images if we need it later. | Optional Phase 3.1. |
| **Get PDF properties / Extract** (optional) | Get form field names and metadata. | If we need to list field names for the editor without parsing AcroForm ourselves. |

Reference: [Import PDF Form Data](https://developer.adobe.com/document-services/docs/overview/pdf-services-api/howtos/import-pdf-form-data/), [PDF Services API overview](https://developer.adobe.com/document-services/docs/overview/pdf-services-api/).

### Technical details

- **REST:** `https://pdf-services.adobe.io/operation/setformdata` (and other ops). Use via **SDK** (recommended) or direct REST.
- **Backend only:** Credentials must stay on the server (never in the frontend). Our backend receives form data from the frontend, calls Adobe, then saves the returned PDF.
- **SDKs:** Java, Python, Node.js, .NET. For this stack use **Python** SDK in the FastAPI backend.
- **Form support:** PDF 1.6+, AcroForm and static XFA. SF1449 and most government PDF forms are AcroForm.
- **Pricing:** Free tier ~500 document transactions/month; then paid. Store credentials in env (e.g. `ADOBE_CLIENT_ID`, `ADOBE_CLIENT_SECRET` or credential JSON path).

### What we need to implement

1. **Credentials:** Create an Adobe Developer project, get OAuth or service credentials, add to backend config (env vars).
2. **Backend service:** Thin wrapper that accepts (input PDF bytes or path, form_data dict), calls Adobe Import PDF Form Data, returns filled PDF bytes. Our existing endpoints (fill-form, forms/autofill) call this instead of pypdf.
3. **Form field names:** For “get form fields” we can either use Adobe extract/properties if available, or keep using pypdf/PDF.js on the backend/frontend only to read field names and current values; Adobe is used only for the actual fill.

**Word (DOCX):** No Adobe dependency. Keep using **python-docx** and in-browser DOCX editor as planned.

---

## Data Available for Autofill

From existing models:

- **Opportunity:** `title`, `notice_id`, `agency`, `sam_gov_url`, `primary_contact`, `alternative_contact`, `contracting_office_address`, `solicitation_type`, `description`, `classification_codes`
- **Deadline:** `due_date`, `due_time`, `timezone`, `deadline_type`, `description`, `location`
- **CLIN:** `clin_number`, `product_name`, `product_description`, `manufacturer_name`, `part_number`, `model_number`, `quantity`, `unit_of_measure`, `scope_of_work`, `timeline`, `additional_data` (e.g. delivery_address, delivery_timeline)
- **Document:** existing solicitation PDFs/Word files (can be used as source or template)

---

## Task Breakdown

### Block A: Save/Load and Document Storage (foundation)

*Needed so “edited” and “autofilled” files have a place to live and can be reopened.*

| ID | Task | Description | Dependencies |
|----|------|-------------|--------------|
| A1 | **Extend document model for saved/edited docs** | Add way to distinguish “original” vs “saved/edited” (e.g. `document_source` or `document_type`: original_attachment \| user_upload \| edited \| autofilled). Optional: `parent_document_id` to link edited/autofilled doc to source. | None |
| A2 | **API: Save document (create new)** | `POST /api/v1/opportunities/{id}/documents` — accept multipart file (PDF or DOCX), store under opportunity, create `Document` with source=edited or autofilled. Return document metadata. | A1 |
| A3 | **API: Overwrite document (optional)** | `PUT /api/v1/opportunities/{id}/documents/{doc_id}` — replace file content for existing document (e.g. after in-app edit). Keep same document id and metadata; update `updated_at`. | A1, A2 |
| A4 | **List and filter documents in UI** | On opportunity detail (or a “Documents” tab), list all documents including new “saved/edited” and “autofilled” docs; allow open (view/edit) and download. | A2 |

---

### Block B: In-App PDF and Word Editing

*Users can edit PDFs and Word docs inside the app and save back.*

| ID | Task | Description | Dependencies |
|----|------|-------------|--------------|
| B1 | **PDF viewer/editor in frontend** | Integrate an in-browser PDF viewer that supports at least form-field editing (AcroForm). Options: PDF.js + custom form layer, or a library that supports fill + flatten. User can open a document from the opportunity and see it in-app. | A4 (document list + open) |
| B2 | **PDF edit: form fields** | For PDFs with AcroForm fields: load field names and values, allow user to edit values in UI, then “Save” → send updated values to backend. Backend calls **Adobe PDF Services API** (Import PDF Form Data) to fill form and saves result (new Document or overwrite per A2/A3). | B1, A2 or A3 |
| B3 | **PDF edit: optional text/annotations** | If required: support adding or editing text/annotations (e.g. free text, highlights). Can be Phase 3.1 if time-boxed. | B2 |
| B4 | **Word (DOCX) viewer/editor in frontend** | Integrate an in-browser DOCX viewer/editor (e.g. docx.js, or only form-field-like placeholders). User can open a DOCX from the opportunity. | A4 |
| B5 | **DOCX edit and save** | User edits content (or form fields if DOCX has content controls). “Save” → send changed content or full file to backend. Backend uses python-docx to apply changes and save (new Document or overwrite). | B4, A2 or A3 |

---

### Block C: Form Autofill (SF1449 and Extensible)

*Use extracted data to prefill government forms; save as new documents.*

| ID | Task | Description | Dependencies |
|----|------|-------------|--------------|
| C1 | **SF1449 form template and field map** | Obtain or create an SF1449 PDF template (with AcroForm fields). Define a **field mapping**: which Opportunity/Deadline/CLIN (and user) fields map to which SF1449 field names. Document in code or config (e.g. `form_mappings/sf1449.yaml` or Python dict). | None |
| C2 | **Backend: autofill service (PDF)** | Service that takes: (opportunity_id, form_template_id e.g. "sf1449", optional document_id for template). Loads opportunity + deadlines + CLINs; builds flat key-value dict from mapping; calls **Adobe PDF Services API** (Import PDF Form Data) to fill template PDF; saves result as new Document. | C1, A2 |
| C3 | **API: Generate autofilled form** | `POST /api/v1/opportunities/{id}/forms/autofill` — body: `form_type=sf1449`, optional `template_document_id`. Backend runs autofill service, saves new Document (source=autofilled), returns document id and download URL. | C2 |
| C4 | **UI: “Autofill SF1449” action** | On opportunity detail (or Documents section): button “Autofill SF1449”. Calls autofill API; shows progress then link to open/download the new document. New doc appears in document list. | C3, A4 |
| C5 | **Extensible “other government forms”** | Design so additional forms (e.g. SF30, agency-specific) can be added: new template file + new mapping config + optional new form_type in API. Implement one more form as example, or only document the pattern. | C2, C3 |

---

### Block D: Integration and UX

*Tie editing and autofill into the existing flow.*

| ID | Task | Description | Dependencies |
|----|------|-------------|--------------|
| D1 | **Document open flow** | From opportunity detail document list: “Open” opens document in in-app viewer/editor (PDF or DOCX per type). “Download” keeps current behavior (file download). | B1, B4, A4 |
| D2 | **Save flow from editor** | In viewer/editor: “Save” persists changes (overwrite or new version per product decision). Success message and refresh document list. | B2, B5, A3 |
| D3 | **Clear labeling** | In UI, distinguish “Original attachment”, “Uploaded”, “Edited”, “Autofilled” so users know document origin. | A1, A4 |

---

## Suggested Implementation Order

1. **A1 → A2 → A4** — Storage and list (save new doc, list all docs).
2. **C1 → C2 → C3 → C4** — Autofill SF1449 (no in-app editor required to start; user can download filled PDF).
3. **B1 → B2** — PDF open + form-field edit and save.
4. **A3, D2** — Overwrite + save flow from editor.
5. **B4 → B5** — DOCX viewer and edit/save.
6. **D1, D3** — Open flow and labels.
7. **C5** — Extensible “other forms” (second form or doc only).
8. **B3** — Optional PDF text/annotations if time.

---

## Acceptance Criteria (Summary)

- User can **generate an autofilled SF1449** from an opportunity; the new PDF is saved to the opportunity and appears in the document list; user can open or download it.
- User can **open a PDF or DOCX** from the opportunity **in the app**, **edit form fields** (and optionally text for DOCX), and **save**; the saved file is stored and can be reopened or downloaded.
- **Save/load**: All documents (original, uploaded, edited, autofilled) are **listed** for the opportunity and can be **opened** (in-app) or **downloaded**.

---

## Phase 3 API Spec (Editing and Filling)

All under `GET /api/v1` (e.g. `/api/v1/opportunities`). Auth: `Authorization: Bearer <token>`. Opportunity must belong to current user.

### Existing (no change)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/{opportunity_id}` | Get opportunity with `documents`, `deadlines`, `clins` (document list is already here). |
| GET | `/{opportunity_id}/documents/{document_id}/view` | Stream/download document file (PDF, DOCX, etc.). |

---

### New endpoints

#### 1. Save new document (upload after edit or autofill)

| Method | Path | Purpose |
|--------|------|---------|
| **POST** | `/{opportunity_id}/documents` | Save a new document under the opportunity (e.g. after autofill or “Save as” from editor). |

**Request:** `multipart/form-data`

- `file` (required): PDF or DOCX file.
- `source` (optional): `edited` \| `autofilled` (default `edited`).
- `name` (optional): Display name; if omitted, use original filename.

**Response:** `201` + document object (id, file_name, file_path, file_type, source, created_at, etc.).

---

#### 2. Overwrite document (save edits)

| Method | Path | Purpose |
|--------|------|---------|
| **PUT** | `/{opportunity_id}/documents/{document_id}` | Replace file content for an existing document (e.g. save after in-app edit). Same document id; metadata (name, source) can be kept or updated. |

**Request:** `multipart/form-data`

- `file` (required): New PDF or DOCX file (full file replace).

**Response:** `200` + updated document object.

---

#### 3. Get PDF form fields (for in-app editing)

| Method | Path | Purpose |
|--------|------|---------|
| **GET** | `/{opportunity_id}/documents/{document_id}/form-fields` | Return AcroForm field names and current values for a PDF. Used by frontend to show editable form in the UI. |

**Response:** `200`

- If document is not PDF or has no form fields: `200` with empty or “not a form” indicator.
- If PDF with AcroForm: `{ "fields": [ { "name": "fieldName", "value": "current value", "type": "text" \| "checkbox" \| ... } ] }`.

**Response (non-PDF or no fields):** `200` + `{ "fields": [], "reason": "no_form" \| "not_pdf" }`.

---

#### 4. Fill PDF form and save (form-field edit save)

| Method | Path | Purpose |
|--------|------|---------|
| **POST** | `/{opportunity_id}/documents/{document_id}/fill-form` | Fill PDF form with provided values and save (overwrite this document or create new per product decision). |

**Request:** `application/json`

```json
{
  "fields": {
    "ContractNumber": "W912XX-24-R-0001",
    "OfferDueDate": "2024-03-15",
    "CompanyName": "Acme Corp"
  }
}
```

**Response:** `200` + updated document object (or new document object if “save as new”); or `400` if document is not a PDF or has no form.

---

#### 5. Generate autofilled form (SF1449 etc.)

| Method | Path | Purpose |
|--------|------|---------|
| **POST** | `/{opportunity_id}/forms/autofill` | Generate a filled government form from opportunity data and save as a new document. |

**Request:** `application/json`

```json
{
  "form_type": "sf1449",
  "template_document_id": null
}
```

- `form_type` (required): e.g. `sf1449` (later: `sf30`, etc.).
- `template_document_id` (optional): Use a specific opportunity document as the template PDF; if omitted, use built-in/default template for that form type.

**Response:** `201`

```json
{
  "document_id": 123,
  "file_name": "SF1449_filled_Opportunity_42.pdf",
  "download_url": "/api/v1/opportunities/42/documents/123/view"
}
```

On failure (e.g. no template, mapping error): `400` or `422` with error detail.

---

### Summary table

| Method | Path | Use case |
|--------|------|----------|
| POST | `/{opp_id}/documents` | Save new document (edited or autofilled). |
| PUT | `/{opp_id}/documents/{doc_id}` | Overwrite document (save full file after edit). |
| GET | `/{opp_id}/documents/{doc_id}/form-fields` | Get PDF form field names/values for editor. |
| POST | `/{opp_id}/documents/{doc_id}/fill-form` | Fill PDF form with JSON values and save. |
| POST | `/{opp_id}/forms/autofill` | Generate autofilled SF1449 (or other form) and save as new doc. |

No new APIs are required for “load” or “list”: list comes from `GET /{opportunity_id}`; load/view uses existing `GET /{opportunity_id}/documents/{document_id}/view`.

---

## Notes

- **SF1449**: Standard “Solicitation/Contract/Order for Commercial Products and Commercial Services”. Many versions exist; pick one and document which field set the mapping targets.
- **PDF form fill (backend):** Use **Adobe PDF Services API** (Acrobat-style) for filling PDF forms (Import PDF Form Data). Optional: pypdf only for *reading* form field names/values for the editor; actual fill is done via Adobe.
- **Frontend PDF:** PDF.js for viewing; form field values can be edited via PDF.js or a custom overlay, then sent to our API; backend calls Adobe to produce filled PDF.
- **DOCX (backend):** python-docx already in use for extraction; use it for creating/updating DOCX (paragraphs, tables, content controls) when saving from editor or for future form types.
