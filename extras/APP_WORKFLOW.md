# Application Workflow

## Overview
Automated government contract solicitation analysis system that extracts critical procurement information from SAM.gov opportunities.

---

## Main Workflow

### 1. **User Input** (`/analyze` page)
- User enters SAM.gov solicitation URL (required)
- Optionally uploads additional PDF/Word documents
- Toggles analysis features:
  - ✅ Document Analysis (text extraction)
  - ✅ CLIN Extraction (AI-powered)

### 2. **Scraping Phase** (`scrape_sam_gov_opportunity` task)
- **Scrapes SAM.gov page** using Playwright:
  - Extracts: Title, Description, Agency, Contact Info, Deadlines
  - Downloads all attached documents (PDFs, Word, Excel, etc.)
  - Handles disclaimer/agreement pages automatically
- **Stores metadata** in database:
  - Opportunity record
  - Primary deadline (from SAM.gov page)
  - Document records

### 3. **Document Analysis Phase** (`analyze_documents` task)
**Only runs if "Document Analysis" is enabled**

#### 3.1 Text Extraction
- **Smart PDF routing**:
  - Text-based PDFs → `pdfplumber` (fast, local)
  - Scanned PDFs → Google Document AI → `pytesseract` fallback
- **Multi-format support**: PDF, Word, Excel, PowerPoint, Images, Text
- Extracted text saved to debug directory

#### 3.2 CLIN Extraction (`CLINExtractor`)
**Only runs if "CLIN Extraction" is enabled**

- **Batch processing**: Sends all documents to LLM in one call
- **LLM extraction** (Claude primary, Groq fallback):
  - Extracts CLIN numbers, descriptions, quantities
  - **Enhanced fields**: Manufacturer, Part/Model numbers, Drawing references
  - Scope of work, delivery timelines
- **Stores CLINs** in database with all extracted fields

#### 3.3 Deadline Extraction (`DocumentAnalyzer`)
- **Regex + LLM hybrid**:
  - Extracts submission deadlines from documents
  - Parses dates, times, timezones
  - Tracks deadline types (submission, questions, delivery)
- **Stores deadlines** in database

#### 3.4 Delivery Requirements Extraction (`DeliveryRequirementsExtractor`)
- **Hybrid extraction**:
  - Regex for structured data (addresses, FOB terms)
  - LLM for natural language (SOW sections, special instructions)
- **Extracts**:
  - Complete delivery addresses
  - FOB terms (destination/origin)
  - Delivery timelines
  - Packing requirements
  - Facility constraints
- **Stores** in `opportunity.classification_codes['delivery_requirements']`

### 4. **Results Display** (`/opportunity/:id` page)
- **Progress tracking**: Real-time updates via `analysis_stage` field
- **Displays**:
  - Scraped metadata (title, description, deadlines, contacts)
  - Downloaded documents list
  - Extracted CLINs with all details
  - Delivery requirements
  - Analysis summary

---

## Key Features

### Smart Document Download
- Handles direct PDF links
- Finds PDF links on pages
- **Disclaimer handling**: Automatically clicks "OK"/"Agree" buttons
- Recursive navigation (max depth: 4)
- Returns `None` for login pages

### Intelligent Text Extraction
- **PDF type detection**: Text-based vs. scanned
- **Google Document AI** for high-quality OCR
- **Fallback chain**: Document AI → pytesseract → pdfplumber
- **Multi-format**: PDF, Word, Excel, PowerPoint, Images, RTF, Markdown

### AI-Powered CLIN Extraction
- **Claude 3 Haiku** (primary) with **Groq Llama 3.1** (fallback)
- **Batch processing**: All documents in one LLM call
- **Enhanced extraction**: Manufacturer, part numbers, drawings, scope of work
- **Structured output**: Pydantic schemas ensure consistent data

### Delivery Requirements
- **Complete addresses**: Facility name, street, city, state, ZIP
- **FOB terms**: Destination vs. origin
- **Timelines**: "60 days after contract award", "Within 30 days"
- **Special instructions**: Testing, staggered delivery, packing methods

---

## Data Flow

```
User Input (URL + Files)
    ↓
SAM.gov Scraping
    ↓
Document Download
    ↓
Text Extraction (if enabled)
    ↓
CLIN Extraction (if enabled)
    ↓
Deadline Extraction
    ↓
Delivery Requirements Extraction
    ↓
Database Storage
    ↓
Frontend Display
```

---

## Technology Stack

- **Backend**: FastAPI, Celery, PostgreSQL
- **Scraping**: Playwright
- **Text Extraction**: pdfplumber, Google Document AI, pytesseract
- **AI/LLM**: Claude 3 Haiku (Anthropic), Groq Llama 3.1
- **Frontend**: React, Tailwind CSS
- **Task Queue**: Redis, Celery

---

## Status Tracking

Opportunity statuses:
- `pending` → Initial creation
- `processing` → Scraping/analysis in progress
- `completed` → Analysis finished
- `failed` → Error occurred

Analysis stages (`analysis_stage` field):
- "Scraping SAM.gov Data"
- "Downloading Documents"
- "Extracting Text from Documents"
- "Analyzing CLINs with AI"
- "Analysis Complete"
