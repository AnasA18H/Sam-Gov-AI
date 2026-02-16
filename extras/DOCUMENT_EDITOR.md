# Document Editor (in-app)

The document editor is a modal opened from the opportunity detail page (Edit button on an attachment). It supports **PDF** (form fields + add text) and **Word** (replace file).

## PDF flow

1. **Open:** User clicks Edit on a PDF attachment. Modal opens and shows "Loading document…".
2. **Load:** Frontend requests the full PDF via `GET /opportunities/{id}/documents/{docId}/view` (arraybuffer). It then uses **pdf-lib** in the browser to load the PDF and read AcroForm fields (name, type, current value). Form field list and values are stored in state; a preview URL is created from the bytes for PDF.js to render pages.
3. **Display:** User sees a PDF page preview (left) and a "Form fields" panel (right) with one input per field. Server form-fields (for "Fill from opportunity" mapping) are fetched in the background so the editor is interactive as soon as the PDF is parsed.
4. **Edit:** User can change form values and/or add text boxes (click on preview to place, then type). Changes are in memory only until Save.
5. **Save:** User clicks Save. Frontend uses pdf-lib to write current form values and any added text onto a copy of the PDF, then uploads the result via `PUT /opportunities/{id}/documents/{docId}` (overwrite). Optionally "Save as new document" uses the fill-form API to create a new attachment from the current form values.

## Word flow

User uploads a replacement Word/PDF file; Save overwrites the document via the same PUT endpoint.

## Backend

- **View:** `GET /opportunities/{id}/documents/{docId}/view` streams the file from disk (or S3) for the frontend to download.
- **Overwrite:** `PUT /opportunities/{id}/documents/{docId}` accepts a multipart file and overwrites the stored file and metadata.
