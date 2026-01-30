# Application Workflow - Concise Overview

## High-Level Flow

```
User Input (SAM.gov URL) 
  ↓
Scrape SAM.gov Page
  ↓
Download Documents (Smart Downloader)
  ↓
Extract Text from Documents
  ↓
Analyze & Extract Data (CLINs, Deadlines, Delivery Requirements)
  ↓
Store Results in Database
```

---

## Detailed Workflow

### 1. **User Submission** (`/api/opportunities`)
- User provides SAM.gov URL
- Optional: Upload additional PDFs
- Flags: Enable document analysis, enable CLIN extraction
- Creates `Opportunity` record → triggers `scrape_sam_gov_opportunity` task

### 2. **Scraping SAM.gov** (`scrape_sam_gov_opportunity`)
- **SAMGovScraper** extracts:
  - Title, description, agency
  - Notice ID, contact info
  - Deadline (date_offers_due)
  - Attachment URLs
- Updates `Opportunity` metadata
- Stores `Deadline` record

### 3. **Document Download** (`DocumentDownloader`)
Smart downloader handles 4 cases with recursive depth tracking (max depth: 4):

#### **Case 1: Direct PDF Download**
- PDF viewer detected → direct download
- Uses Playwright `expect_download()` with `domcontentloaded`

#### **Case 2: Find PDF Link** (Lines 911-914)
```python
# For PDF URLs, use domcontentloaded and expect download
with self.page.expect_download(timeout=30000) as download_info:
    self.page.goto(pdf_url, wait_until='domcontentloaded', timeout=60000)
```
- Finds PDF link on webpage
- Navigates to PDF URL
- If not direct PDF → recursively applies all cases (depth +1)

#### **Case Disclaimer: Handle Agreement Pages**
- Detects disclaimer/consent banners (DoD, etc.)
- Clicks "OK"/"Agree" buttons
- Navigates to new page → recursively applies all cases

#### **Case 3: Extract Text**
- If no PDF found → scrape webpage text
- Save as `.txt` file

**Files saved to:** `backend/data/documents/{opportunity_id}/`

### 4. **Document Analysis** (`analyze_documents`)
Triggered after scraping completes (if `enable_document_analysis=true`):

#### **4.1 Text Extraction** (`TextExtractor`)
- **Smart PDF Routing:**
  - Text-based PDFs → `pdfplumber`
  - Scanned PDFs → Google Document AI (fallback: `pytesseract` OCR)
- **Other Formats:**
  - Word → `python-docx`
  - Excel → `pandas`
  - Images → OCR with preprocessing
  - PowerPoint → `python-pptx`

#### **4.2 CLIN Extraction** (`CLINExtractor`) - if enabled
- **LLM-based extraction** (Claude primary, Groq fallback)
- Extracts:
  - CLIN number, description, quantity, unit
  - **Enhanced:** Manufacturer, part/model numbers, drawing references
  - **Enhanced:** Scope of work, delivery timeline
- **Batch processing:** All documents in single LLM call

#### **4.3 Deadline Extraction** (`DocumentAnalyzer`)
- Regex patterns + date parsing
- Extracts submission deadlines, question deadlines
- Handles timezone (EST, CST, PST, etc.)

#### **4.4 Delivery Requirements** (`DeliveryRequirementsExtractor`)
- **Hybrid approach:**
  - Regex for structured data (addresses, FOB terms)
  - LLM for natural language (SOW sections)
- Extracts:
  - Complete delivery address
  - FOB terms (destination/origin)
  - Delivery timeline
  - Special instructions
  - Packing requirements

#### **4.5 Classification**
- Classifies solicitation type: Product / Service / Both
- Uses keyword matching + spaCy (if available)

### 5. **Data Storage**
- **CLINs** → `clins` table
- **Deadlines** → `deadlines` table
- **Delivery Requirements** → `opportunities.classification_codes['delivery_requirements']`
- **Documents** → `documents` table
- **Status** → `opportunity.status = "completed"`

---

## Key Features

### Smart Document Downloader
- **Recursive navigation** with depth tracking (max 4 levels)
- Handles PDF viewers, download links, disclaimer pages
- Fallback to text extraction if PDF unavailable

### Enhanced CLIN Extraction
- Extracts manufacturer, part numbers, drawing references
- Captures scope of work and delivery timelines
- Batch processing for efficiency

### Delivery Requirements
- Complete address extraction
- FOB terms detection
- Special instructions capture

### Progress Tracking
- Real-time status updates via `opportunity.analysis_stage`
- Frontend displays progress: Scraping → Downloading → Extracting → Analyzing → Complete

---

## Technology Stack

- **Web Scraping:** Playwright
- **Text Extraction:** pdfplumber, Google Document AI, pytesseract
- **AI/LLM:** Claude 3 Haiku (primary), Groq Llama 3.1 (fallback)
- **Database:** PostgreSQL (SQLAlchemy)
- **Task Queue:** Celery + Redis
- **Backend:** FastAPI
- **Frontend:** React

---

## Example Flow

1. User submits: `https://sam.gov/opp/2031ZA26Q00029`
2. Scraper extracts: Title, description, 5 attachment URLs
3. Downloader processes each URL:
   - Case 1: Direct PDF → Download
   - Case 2: PDF link → Navigate → Download (lines 911-914)
   - Case Disclaimer: Agreement page → Click OK → Navigate → Download
4. Text extractor processes: 5 PDFs → Extracted text
5. CLIN extractor: Batch processes all documents → Finds 1 CLIN (0001: Stack and Rack Carts, 250 Each)
6. Delivery extractor: Finds delivery address (Fort Worth, TX), FOB destination
7. Results stored in database
8. Frontend displays: Opportunity details, documents, CLINs, deadlines
