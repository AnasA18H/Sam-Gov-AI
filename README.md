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
| **AI Classification** | Groq-powered Llama models classify solicitations as Product/Service/Both with confidence scores |
| **CLIN Extraction** | Intelligent extraction of Contract Line Item Numbers with full product/service details |
| **Deadline Tracking** | Automated deadline extraction with timezone support from pages and documents |
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

- **Hybrid Extraction Approach**:
  - Table parsing for structured forms (SF1449, SF30) using camelot-py/pdfplumber
  - LLM-powered extraction using Groq (Llama 3.1-8B) for unstructured text (SOW, amendments)
  - Regex fallback for edge cases
- Text extraction from PDF, Word, and Excel documents
- AI-powered classification (Product/Service/Both) with confidence scoring
- CLIN extraction with product/service details, quantities, part numbers
- Deadline extraction from documents (complements page metadata)
- Optional file uploads with SAM.gov URL analysis

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
| **pdfplumber** | PDF text extraction |
| **camelot-py** | Table extraction from PDFs |
| **python-docx** | Word document parsing |
| **openpyxl** | Excel file handling |

</details>

<details>
<summary><strong>AI & Machine Learning</strong></summary>

| Technology | Purpose |
|------------|---------|
| **Groq + LangChain** | LLM-powered extraction (Llama 3.1-8B) |
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

# Groq API (Optional - for LLM extraction)
GROQ_API_KEY=your-groq-api-key
GROQ_MODEL=llama-3.1-8b-instant
```

### Step 5: Run Migrations

```bash
./scripts/run_migrations.sh
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
- ✓ Ensures data directories exist
- ✓ Verifies database connection
- ✓ Runs migrations
- ✓ Starts all required services

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
│   │   │   ├── document_downloader.py
│   │   │   └── document_analyzer.py  # Hybrid extraction
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

# 2. Create Opportunity with Files
curl -X POST http://localhost:8000/api/v1/opportunities \
  -H "Authorization: Bearer eyJ..." \
  -F "sam_gov_url=https://sam.gov/workspace/contract/opp/.../view" \
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
| Document Downloads | ✓ |
| Contact Info Extraction | ✓ |
| Document Analysis | ✓ |
| CLIN Extraction (Hybrid) | ✓ |
| Deadline Extraction | ✓ |
| File Upload | ✓ |
| Frontend UI | ✓ |

**Phase 1 is 100% complete** - All MVP requirements met!

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

1. **Input**: User provides SAM.gov URL (+ optional files)
2. **Scraping**: Playwright extracts metadata and downloads attachments
3. **Document Classification**: Documents routed by type (SF1449, SF30, SOW, etc.)
4. **Extraction**:
   - Structured forms → Table parsing (camelot/pdfplumber)
   - Unstructured text → LLM extraction (Groq + Llama)
   - Fallback → Regex extraction
5. **Classification**: AI determines Product/Service/Both
6. **Storage**: All data saved to database and displayed in UI

</details>

<details>
<summary><strong>CLIN Extraction Methods</strong></summary>

**For Structured Forms (SF1449, SF30):**
- Uses `camelot-py` or `pdfplumber` to extract tables
- Directly parses CLIN table rows and columns

**For Unstructured Documents (SOW, Amendments):**
- Uses Groq LLM (Llama 3.1-8B) with LangChain
- Pydantic schemas ensure structured output
- Extracts: CLIN numbers, descriptions, quantities, part numbers, manufacturers

**Fallback:**
- Regex-based pattern matching if other methods fail

</details>

---

## License

Proprietary - All rights reserved

---

<div align="center">

**Built for Government Contractors**

[Back to Top](#samgov-ai)

</div>