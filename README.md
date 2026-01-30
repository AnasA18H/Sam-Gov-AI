# SAM.gov AI

<div align="center">

![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)
![React](https://img.shields.io/badge/React-18+-61dafb.svg)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-14+-336791.svg)
![Groq](https://img.shields.io/badge/Groq-Llama_3.1-8B-orange.svg)

**AI-Powered Government Contract Analysis Platform**

*Automating US Government contract solicitation analysis from SAM.gov*

[Features](#features) • [Quick Start](#quick-start) • [Documentation](#api-documentation) • [Deployment](#deployment)

</div>

---

## Overview

**SAM.gov AI** is an intelligent web application that automates the analysis of US Government contract solicitations from [SAM.gov](https://sam.gov). The platform streamlines the bid preparation process by automatically extracting critical information from solicitation documents, classifying opportunities, and providing actionable insights.

### Core Capabilities

| Capability | Description |
|------------|-------------|
| **Automated Scraping** | Extracts data directly from SAM.gov opportunity pages using Playwright |
| **Hybrid Document Analysis** | Table parsing for structured forms (SF1449, SF30) + LLM extraction for unstructured text (SOW, amendments) |
| **AI Classification** | Claude (Haiku) + Groq (Llama 3.1) powered classification of solicitations as Product/Service/Both with confidence scores |
| **CLIN Extraction** | Intelligent extraction of Contract Line Item Numbers with full product/service details, delivery requirements, and deadlines (Claude primary, Groq fallback). Combines all documents + SAM.gov page text in single LLM request |
| **Smart Text Extraction** | Google Document AI for scanned PDFs, pytesseract OCR fallback, pdfplumber for text-based PDFs |
| **Configurable Analysis** | Enable/disable document analysis and CLIN extraction via UI toggles (disabled by default for testing) |
| **Deadline Tracking** | LLM-based deadline extraction combined with CLIN extraction, with timezone support and deduplication |
| **Delivery Requirements** | Integrated extraction of delivery addresses, special delivery instructions, and delivery timelines within CLIN data |
| **Two-Pass Extraction** | Automatic second pass to fill missing fields when 20%+ of important fields are null |
| **Robust JSON Parsing** | Advanced error recovery for malformed/truncated LLM responses with multiple fallback strategies |
| **Contact Management** | Automatic extraction and display of primary/alternative contacts |

---

## Features

### Phase 1 - Complete ✓

<details>
<summary><strong>User Authentication & Security</strong></summary>

- Secure JWT-based authentication
- Password hashing with bcrypt
- Session management
- Protected routes and API endpoints

</details>

<details>
<summary><strong>SAM.gov Integration</strong></summary>

- URL validation and opportunity ID extraction
- Playwright-based web scraping
- Automated attachment downloads (PDF, Word, Excel, ZIP)
- Contact information extraction (names, emails, phone numbers)
- Contracting office address capture

</details>

<details>
<summary><strong>Advanced Document Analysis</strong></summary>

- **Unified LLM Extraction**:
  - All documents + SAM.gov page text combined into single LLM request for comprehensive analysis
  - Claude 3 Haiku (primary) + Groq Llama 3.1 (fallback) for CLIN, deadline, and delivery requirements extraction
  - Two-pass extraction: Second pass automatically fills missing fields when 20%+ are null
  - Robust JSON parsing with error recovery for malformed/truncated responses
- **Smart Text Extraction**:
  - Google Document AI for high-quality OCR on scanned PDFs
  - pytesseract OCR with image preprocessing as fallback
  - pdfplumber for text-based PDFs
  - Support for PDF, Word, Excel, PowerPoint, Images, RTF, Markdown
  - Raw text sent to LLM (no aggressive cleaning) to preserve all information
- AI-powered classification (Product/Service/Both) with confidence scoring
- **Comprehensive CLIN Extraction**:
  - Product/service details (name, description, manufacturer, part/model numbers, drawing numbers)
  - Quantities and units of measure
  - Scope of work (complete text extraction)
  - Service requirements (detailed specifications)
  - Delivery address (complete with facility name, street, city, state, ZIP)
  - Special delivery instructions (testing requirements, schedules, constraints)
  - Delivery timeline (complete phrases with dates and conditions)
- **LLM-Based Deadline Extraction**: Combined with CLIN extraction, extracts submission deadlines, question deadlines, and other critical dates with timezone support
- **SAM.gov Page Integration**: Raw page text included in analysis for opportunities with no attachments
- Optional file uploads with SAM.gov URL analysis
- **Configurable Analysis**: Enable/disable document analysis and CLIN extraction via UI (disabled by default)

</details>

<details>
<summary><strong>Modern Frontend</strong></summary>

- React 18 with Vite
- TailwindCSS for professional styling
- Responsive, mobile-friendly design
- Real-time status updates with polling
- Intuitive UI with icon-based navigation

</details>

<details>
<summary><strong>Background Processing</strong></summary>

- Celery task queue for async operations
- Redis message broker
- Real-time progress tracking
- Automatic retry on failures

</details>

<details>
<summary><strong>Data Management</strong></summary>

- Organized file storage (documents/uploads)
- Secure document viewing/downloading
- Complete data cleanup on opportunity deletion
- Debug extraction files for troubleshooting (`data/debug_extracts/`)

</details>

### Phase 2 - Planned

- Research automation (manufacturer websites, sales contacts, pricing)
- Email integration (Gmail, Outlook) with automated quote inquiries
- Calendar integration (Google Calendar, iCal, Outlook) with automatic deadline events
- Quote generation and review system

### Phase 3 - Planned

- PDF form automation (SF1449 autofill)
- Advanced reporting dashboard
- Multi-opportunity batch processing

---

## Tech Stack

<details>
<summary><strong>Backend Technologies</strong></summary>

| Technology | Purpose |
|------------|---------|
| **FastAPI** | Modern, fast web framework |
| **PostgreSQL** | Relational database |
| **SQLAlchemy** | ORM for database operations |
| **Alembic** | Database migrations |
| **Celery** | Distributed task queue |
| **Redis** | Message broker and cache |
| **Playwright** | Web scraping and automation |

</details>

<details>
<summary><strong>Document Processing</strong></summary>

| Library | Purpose |
|---------|---------|
| **pdfplumber** | PDF text extraction (text-based PDFs) |
| **PyPDF2** | PDF manipulation and splitting |
| **Google Document AI** | Cloud-based OCR for scanned PDFs |
| **pytesseract** | Local OCR with image preprocessing |
| **opencv-python** | Image preprocessing for OCR |
| **pdf2image** | PDF to image conversion for OCR |
| **python-docx** | Word document parsing |
| **python-pptx** | PowerPoint document parsing |
| **openpyxl** | Excel file handling |
| **pandas** | CSV and advanced Excel processing |

</details>

<details>
<summary><strong>AI & Machine Learning</strong></summary>

| Technology | Purpose |
|------------|---------|
| **Claude 3 Haiku (Anthropic)** | Primary LLM for CLIN extraction, deadline extraction, and classification |
| **Groq + LangChain** | Fallback LLM-powered extraction (Note: llama-3.1-70b-versatile is decommissioned, update to newer model) |
| **LangChain** | LLM orchestration framework with structured output support |
| **spaCy** | NLP for classification |
| **scikit-learn** | Machine learning algorithms |
| **Transformers** | Pre-trained NLP models |

</details>

<details>
<summary><strong>Frontend Technologies</strong></summary>

| Technology | Purpose |
|------------|---------|
| **React 18** | UI library |
| **Vite** | Build tool and dev server |
| **TailwindCSS** | Utility-first CSS framework |
| **React Router** | Client-side routing |
| **Axios** | HTTP client for API calls |

</details>

---

## Installation

### Prerequisites

```bash
# Required Software
- Python 3.12+
- Node.js 18.x+
- PostgreSQL 14+
- Redis 6+
- Git
```

### Step 1: Clone Repository

```bash
git clone <repository-url>
cd sam-project
```

### Step 2: Backend Setup

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium
```

### Step 3: Database Setup

```bash
# Automated setup (recommended)
./scripts/setup_database.sh

# Or manual setup:
# 1. Install PostgreSQL
# 2. Create database and user
# 3. Update .env with DATABASE_URL
```

### Step 4: Environment Configuration

Create `.env` file with required variables:

```env
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/samgov_db

# Redis
REDIS_URL=redis://localhost:6379/0

# JWT Authentication
JWT_SECRET_KEY=your-secret-key-here
SECRET_KEY=your-app-secret-key

# CLIN Extraction Settings
# Anthropic Claude (Primary LLM for CLIN extraction)
ANTHROPIC_API_KEY=your-anthropic-api-key
ANTHROPIC_MODEL=claude-3-haiku-20240307

# Groq (Fallback LLM for CLIN extraction)
# Note: llama-3.1-70b-versatile is decommissioned. Update to newer model (e.g., llama-3.3-70b-versatile)
GROQ_API_KEY=your-groq-api-key
GROQ_MODEL=llama-3.1-70b-versatile

# Text Extraction Settings
# Google Document AI (for high-quality OCR and text extraction from scanned PDFs)
GOOGLE_SERVICE_ACCOUNT_JSON=extras/your-service-account.json
GOOGLE_PROJECT_ID=your-project-id
GOOGLE_PROCESSOR_ID=your-processor-id
GOOGLE_LOCATION=us
GOOGLE_DOCAI_ENABLED=True
```

### Step 5: Run Migrations

```bash
# Automated (recommended)
./scripts/run_migrations.sh

# Or manually
alembic upgrade head
```

### Step 6: Frontend Setup

```bash
cd frontend
npm install
cd ..
```

---

## Quick Start

### Automated Start (Recommended)

```bash
# Start all services (backend, frontend, Celery worker)
./start.sh
```

The script automatically:
- ✓ Checks prerequisites
- ✓ Verifies Python packages are installed
- ✓ Ensures data directories exist
- ✓ Verifies database connection
- ✓ Runs migrations (with fallback to direct alembic)
- ✓ Starts all required services (backend, frontend, Celery worker)

### Manual Start

```bash
# Terminal 1: Backend
source venv/bin/activate
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2: Celery Worker
source venv/bin/activate
celery -A backend.app.core.celery_app worker --loglevel=info

# Terminal 3: Frontend
cd frontend
npm run dev
```

### Access Application

| Service | URL |
|---------|-----|
| **Frontend** | http://localhost:5173 |
| **Backend API** | http://localhost:8000 |
| **API Docs (Swagger)** | http://localhost:8000/docs |
| **API Docs (ReDoc)** | http://localhost:8000/redoc |
| **Health Check** | http://localhost:8000/health |

### Stop Services

```bash
./stop.sh
```

---

## Project Structure

```
sam-project/
├── backend/
│   ├── app/
│   │   ├── api/              # API endpoints
│   │   │   ├── auth.py       # Authentication
│   │   │   ├── opportunities.py
│   │   │   └── router.py
│   │   ├── core/             # Configuration
│   │   │   ├── config.py
│   │   │   ├── database.py
│   │   │   ├── security.py
│   │   │   └── celery_app.py
│   │   ├── models/           # Database models
│   │   ├── schemas/          # Pydantic schemas
│   │   ├── services/         # Business logic
│   │   │   ├── tasks.py
│   │   │   ├── sam_gov_scraper.py
│   │   │   ├── document_downloader.py  # Smart download with disclaimer handling
│   │   │   ├── document_analyzer.py    # Facade for text extraction and CLIN detection
│   │   │   ├── text_extractor.py      # Text extraction from all formats
│   │   │   └── clin_extractor.py      # CLIN detection (Claude + Groq)
│   │   └── utils/
│   └── migrations/           # Alembic migrations
├── frontend/
│   ├── src/
│   │   ├── pages/            # Page components
│   │   ├── components/       # Reusable components
│   │   ├── contexts/         # React contexts
│   │   └── utils/            # Utilities
│   └── public/
├── data/
│   ├── documents/            # Downloaded documents
│   ├── uploads/              # User uploads
│   └── debug_extracts/       # Debug extraction files
├── scripts/                  # Setup scripts
├── logs/                     # Application logs
├── start.sh                  # Start script
└── stop.sh                   # Stop script
```

---

## API Documentation

### Interactive Documentation

Once the backend is running:

- **Swagger UI**: http://localhost:8000/docs
  - Interactive API explorer
  - Try endpoints directly
  - Full request/response schemas

- **ReDoc**: http://localhost:8000/redoc
  - Clean, readable format
  - Searchable documentation

### Core Endpoints

#### Authentication

```
POST   /api/v1/auth/register    # User registration
POST   /api/v1/auth/login       # Login (returns JWT)
GET    /api/v1/auth/me          # Current user (protected)
POST   /api/v1/auth/logout      # Logout (protected)
```

#### Opportunities

```
GET    /api/v1/opportunities                    # List opportunities
POST   /api/v1/opportunities                    # Create opportunity (with optional file uploads)
GET    /api/v1/opportunities/{id}               # Get details with CLINs
DELETE /api/v1/opportunities/{id}               # Delete opportunity and files
GET    /api/v1/opportunities/{id}/documents/{doc_id}/view  # View document
```

### Example Usage

<details>
<summary><strong>Create Opportunity with File Upload</strong></summary>

```bash
# 1. Login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "password"}'

# Response: {"access_token": "eyJ...", "token_type": "bearer"}

# 2. Create Opportunity with Files and Analysis Options
curl -X POST http://localhost:8000/api/v1/opportunities \
  -H "Authorization: Bearer eyJ..." \
  -F "sam_gov_url=https://sam.gov/workspace/contract/opp/.../view" \
  -F "enable_document_analysis=true" \
  -F "enable_clin_extraction=true" \
  -F "files=@/path/to/document1.pdf" \
  -F "files=@/path/to/document2.docx"
```

</details>

---

## Development

### Database Migrations

```bash
# Create migration
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

### Logs

| Service | Log File |
|---------|----------|
| Backend | `logs/backend.log` |
| Celery | `logs/celery.log` |
| Frontend | `logs/frontend.log` |

### Debug Extracts

Extracted text and analysis results are saved to:

```
data/debug_extracts/opportunity_{id}/
  ├── {doc_id}_{filename}_extracted.txt
  ├── {doc_id}_{filename}_clins.txt
  └── analysis_summary.txt
```

---

## Deployment

### Digital Ocean App Platform

1. Push code to Git repository
2. Connect repository to Digital Ocean App Platform
3. Configure environment variables
4. Deploy

See `DEPLOYMENT.md` for detailed instructions.

### Docker

```bash
# Build and run
docker-compose up -d

# Or build individually
docker build -f Dockerfile.backend -t samgov-backend .
docker build -f Dockerfile.frontend -t samgov-frontend .
```

---

## Project Status

### Phase 1: Foundation & Core Scraping ✓ **COMPLETE**

| Feature | Status |
|---------|--------|
| User Authentication | ✓ |
| SAM.gov Scraping | ✓ |
| Smart Document Downloads (with disclaimer handling) | ✓ |
| Contact Info Extraction | ✓ |
| Multi-format Text Extraction (PDF, Word, Excel, PPT, Images) | ✓ |
| Google Document AI Integration | ✓ |
| OCR Support (pytesseract with preprocessing) | ✓ |
| Document Analysis (configurable) | ✓ |
| CLIN Extraction (Claude + Groq fallback) | ✓ |
| Deadline Extraction | ✓ |
| File Upload | ✓ |
| Frontend UI with Analysis Toggles | ✓ |

**Phase 1 is 100% complete** - All MVP requirements met!

### Recent Enhancements

- ✅ **Unified CLIN & Deadline Extraction**: All documents + SAM.gov page text combined in single LLM request
- ✅ **Delivery Requirements Integration**: Delivery addresses, special instructions, and timelines extracted within CLIN data
- ✅ **Two-Pass Extraction**: Automatic second pass fills missing fields when 20%+ are null
- ✅ **Robust JSON Parsing**: Advanced error recovery for malformed/truncated LLM responses with multiple fallback strategies
- ✅ **SAM.gov Page Integration**: Raw page text included in analysis, even when no attachments available
- ✅ **Configurable Analysis**: Document analysis and CLIN extraction can be enabled/disabled via UI (disabled by default for testing)
- ✅ **Smart Text Extraction**: Google Document AI for scanned PDFs, intelligent routing between text-based and scanned PDFs
- ✅ **Improved OCR**: pytesseract with advanced image preprocessing (denoising, contrast enhancement, deskewing)
- ✅ **LLM Fallback**: Claude 3 Haiku as primary, Groq Llama 3.1 as fallback for CLIN extraction
- ✅ **Disclaimer Handling**: Automatic detection and handling of disclaimer/agreement pages during document download
- ✅ **Recursive Navigation**: Smart depth tracking (max 4 levels) for multi-page document downloads
- ✅ **Enhanced Download Timeouts**: Increased timeouts (90s) and improved wait times for slow sites

### Phase 2: Research & Automation

- Manufacturer research
- Email integration
- Calendar integration

### Phase 3: Advanced Features

- Form automation
- Quote generation
- Reporting dashboard

---

## How It Works

<details>
<summary><strong>Analysis Pipeline</strong></summary>

1. **Input**: User provides SAM.gov URL (+ optional files) with analysis options
2. **Scraping**: Playwright extracts metadata and downloads attachments
   - Handles disclaimer/agreement pages automatically
   - Recursive navigation with depth tracking (max 4 levels)
   - Smart PDF detection and download
3. **Document Analysis** (if enabled):
   - **Text Extraction**: 
     - Text-based PDFs → pdfplumber
     - Scanned PDFs → Google Document AI (with pytesseract fallback)
     - Other formats → Format-specific extractors
   - **Document Classification**: Documents routed by type (SF1449, SF30, SOW, etc.)
4. **CLIN & Deadline Extraction** (if enabled):
   - **Combined Processing**: All document texts + SAM.gov page text sent to LLM in single request
   - **Primary**: Claude 3 Haiku extracts CLINs, deadlines, and delivery requirements together
   - **Fallback**: Groq Llama 3.1 if Claude fails
   - **Two-Pass System**: If 20%+ fields are missing, second pass fills missing values
   - **Robust Parsing**: Advanced JSON error recovery handles malformed/truncated responses
   - Extracts: CLIN numbers, product details, quantities, manufacturers, part numbers, scope of work, service requirements, delivery addresses, special delivery instructions, delivery timelines, deadlines
5. **Classification**: AI determines Product/Service/Both with confidence scoring
6. **Storage**: All data saved to database with proper deduplication (CLINs and deadlines)
7. **Display**: Data displayed in UI with collapsible CLIN sections and professional formatting

</details>

<details>
<summary><strong>CLIN & Deadline Extraction Process</strong></summary>

**Unified Extraction Approach:**
- All documents + SAM.gov page text are combined and sent to LLM in a single request
- Claude 3 Haiku (primary) extracts CLINs, deadlines, and delivery requirements together
- Groq Llama 3.1 (fallback) used if Claude fails
- LangChain with structured output ensures JSON format compliance

**Extracted Fields:**
- **CLIN Data**: Numbers, descriptions, quantities, units, product names, manufacturers, part/model numbers, drawing numbers, contract types
- **Scope & Requirements**: Complete scope of work text, detailed service requirements
- **Delivery Information**: Complete delivery addresses, special delivery instructions, delivery timelines
- **Deadlines**: Submission deadlines, question deadlines, with dates, times, timezones, and types

**Two-Pass System:**
- First pass extracts all available data
- If 20%+ of important fields are null, second pass specifically targets missing fields
- Ensures maximum data completeness

**Error Handling:**
- Robust JSON parsing with multiple fallback strategies
- Handles truncated/malformed JSON responses
- Extracts partial data even from incomplete responses
- Individual CLIN object extraction if outer JSON structure is broken

</details>

---

## License

Proprietary - All rights reserved

---

<div align="center">

**Built for Government Contractors**

[Back to Top](#samgov-ai)

</div>