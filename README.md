# 🚀 SAM.gov AI - Government Contract Analysis Platform

<div align="center">

![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)
![React](https://img.shields.io/badge/React-18+-61dafb.svg)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-14+-336791.svg)
![License](https://img.shields.io/badge/License-Proprietary-red.svg)

**AI-powered web application for automating US Government contract solicitation analysis from SAM.gov**

[Features](#-features) • [Installation](#-installation) • [Quick Start](#-quick-start) • [API Documentation](#-api-documentation) • [Tech Stack](#-tech-stack)

</div>

---

## 📋 Table of Contents

- [Overview](#-overview)
- [Features](#-features)
- [Tech Stack](#-tech-stack)
- [Installation](#-installation)
- [Quick Start](#-quick-start)
- [Project Structure](#-project-structure)
- [API Documentation](#-api-documentation)
- [Development](#-development)
- [Deployment](#-deployment)
- [Status](#-project-status)

---

## 🎯 Overview

**SAM.gov AI** is an intelligent web application that automates the analysis of US Government contract solicitations from [SAM.gov](https://sam.gov). The platform streamlines the bid preparation process by automatically extracting critical information from solicitation documents, classifying opportunities, and providing actionable insights.

### Key Capabilities

- 🔍 **Automated Scraping**: Extracts data directly from SAM.gov opportunity pages
- 📄 **Document Processing**: Analyzes PDF, Word, and Excel attachments
- 🤖 **AI Classification**: Automatically classifies solicitations as product/service/hybrid
- ⏰ **Deadline Tracking**: Extracts and tracks submission deadlines with timezone support
- 📊 **CLIN Extraction**: Parses Contract Line Item Numbers with full details
- 👥 **Contact Information**: Captures primary and alternative contacts automatically

---

## ✨ Features

### ✅ Phase 1 - Completed

- 🔐 **User Authentication**
  - Secure registration and login with JWT tokens
  - Session management and protected routes
  - Password hashing with bcrypt

- 🌐 **SAM.gov Integration**
  - URL validation and opportunity ID extraction
  - Playwright-based web scraping
  - Automated attachment downloads (PDF, Word, Excel)
  - Contact information extraction

- 📦 **Document Management**
  - Local file storage with organized structure
  - Document metadata tracking (size, type, URLs)
  - Secure document viewing/downloading
  - Support for ZIP file extraction from "Download All" button

- 🎨 **Modern Frontend**
  - React 18 with Vite
  - TailwindCSS for styling
  - Responsive design
  - Real-time status updates

- 🔄 **Background Processing**
  - Celery task queue for async operations
  - Redis message broker
  - Real-time progress tracking

### 🚧 In Progress / Planned

- 📝 **Document Analysis** (Phase 1 - Week 2-3)
  - Text extraction from PDFs/Word/Excel
  - AI-powered classification (product/service/hybrid)
  - CLIN extraction from documents
  - Additional deadline extraction

- 🔍 **Research Automation** (Phase 2)
  - Manufacturer website research
  - Sales contact discovery
  - Dealer/distributor information
  - Pricing data collection

- 📧 **Email Integration** (Phase 2)
  - Gmail and Outlook integration
  - Automated quote inquiry email generation
  - Template editing and review

- 📅 **Calendar Integration** (Phase 2)
  - Google Calendar, iCal, Outlook
  - Automatic deadline event creation
  - Reminder notifications

- 📄 **Form Automation** (Phase 3)
  - PDF form autofill (e.g., SF1449)
  - Adobe Acrobat equivalent functionality

---

## 🛠 Tech Stack

### Backend
- **Framework**: [FastAPI](https://fastapi.tiangolo.com/) - Modern, fast web framework
- **Database**: [PostgreSQL](https://www.postgresql.org/) - Relational database
- **ORM**: [SQLAlchemy](https://www.sqlalchemy.org/) - Database toolkit and ORM
- **Migrations**: [Alembic](https://alembic.sqlalchemy.org/) - Database migration tool
- **Authentication**: JWT (python-jose) + bcrypt
- **Task Queue**: [Celery](https://docs.celeryq.dev/) - Distributed task queue
- **Cache**: [Redis](https://redis.io/) - In-memory data store

### Web Scraping & Processing
- **Browser Automation**: [Playwright](https://playwright.dev/) - Reliable web scraping
- **PDF Processing**: [pdfplumber](https://github.com/jsvine/pdfplumber) - PDF text extraction
- **Word Processing**: [python-docx](https://python-docx.readthedocs.io/) - Word document parsing
- **Excel Processing**: [openpyxl](https://openpyxl.readthedocs.io/) - Excel file handling

### AI & NLP
- **NLP**: [spaCy](https://spacy.io/) - Natural language processing
- **ML**: [scikit-learn](https://scikit-learn.org/) - Machine learning library
- **Transformers**: [Hugging Face Transformers](https://huggingface.co/docs/transformers) - Pre-trained models
- **Deep Learning**: [PyTorch](https://pytorch.org/) - Neural network framework

### Frontend
- **Framework**: [React](https://react.dev/) - UI library
- **Build Tool**: [Vite](https://vitejs.dev/) - Fast frontend build tool
- **Styling**: [TailwindCSS](https://tailwindcss.com/) - Utility-first CSS framework
- **Routing**: [React Router](https://reactrouter.com/) - Client-side routing
- **HTTP Client**: [Axios](https://axios-http.com/) - API requests

### DevOps & Deployment
- **Containerization**: [Docker](https://www.docker.com/) - Application containers
- **Orchestration**: [Docker Compose](https://docs.docker.com/compose/) - Multi-container apps
- **Web Server**: [Nginx](https://nginx.org/) - Reverse proxy and static serving
- **Deployment**: [Digital Ocean App Platform](https://www.digitalocean.com/products/app-platform)

---

## 📦 Installation

### Prerequisites

Ensure you have the following installed:

- **Python** 3.12 or higher
- **Node.js** 18.x or higher
- **PostgreSQL** 14+ (or use managed database)
- **Redis** 6+ (or use managed Redis)
- **Git** for version control

### Step 1: Clone the Repository

```bash
git clone <repository-url>
cd sam-project
```

### Step 2: Backend Setup

```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install Python dependencies
pip install -r requirements.txt

# Install Playwright browsers (for web scraping)
playwright install chromium
```

### Step 3: Database Setup

```bash
# Run the database setup script
./scripts/setup_database.sh

# Or manually:
# Install PostgreSQL, create database and user
# Update .env file with DATABASE_URL
```

### Step 4: Environment Configuration

```bash
# Copy example environment file (if needed)
cp .env.example .env

# Edit .env with your configuration
nano .env  # or use your preferred editor
```

**Required Environment Variables:**
```env
DATABASE_URL=postgresql://user:password@localhost:5432/samgov_db
REDIS_URL=redis://localhost:6379/0
JWT_SECRET_KEY=your-secret-key-here
SECRET_KEY=your-app-secret-key
```

### Step 5: Database Migrations

```bash
# Run Alembic migrations
./scripts/run_migrations.sh

# Or manually:
alembic upgrade head
```

### Step 6: Frontend Setup

```bash
cd frontend
npm install
cd ..
```

---

## 🚀 Quick Start

### Option 1: Use the Start Script (Recommended)

```bash
# Start all services (backend, frontend, Celery worker)
./start.sh
```

The script will:
- ✅ Check prerequisites
- ✅ Verify database connection
- ✅ Run migrations
- ✅ Start backend server (port 8000)
- ✅ Start frontend dev server (port 5173)
- ✅ Start Celery worker

### Option 2: Manual Start

```bash
# Terminal 1: Start Backend
source venv/bin/activate
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2: Start Celery Worker
source venv/bin/activate
celery -A backend.app.core.celery_app worker --loglevel=info

# Terminal 3: Start Frontend
cd frontend
npm run dev
```

### Access the Application

- **Frontend**: http://localhost:5173
- **Backend API**: http://localhost:8000
- **API Docs (Swagger)**: http://localhost:8000/docs
- **API Docs (ReDoc)**: http://localhost:8000/redoc

### Stop All Services

```bash
./stop.sh
```

---

## 📁 Project Structure

```
sam-project/
├── backend/
│   ├── app/
│   │   ├── api/              # API route handlers
│   │   │   ├── auth.py       # Authentication endpoints
│   │   │   ├── opportunities.py  # Opportunity management
│   │   │   └── router.py     # Main API router
│   │   ├── core/             # Core configuration
│   │   │   ├── config.py     # Settings and environment
│   │   │   ├── database.py   # Database connection
│   │   │   ├── security.py   # JWT and password hashing
│   │   │   ├── dependencies.py  # FastAPI dependencies
│   │   │   └── celery_app.py # Celery configuration
│   │   ├── models/           # SQLAlchemy database models
│   │   │   ├── user.py
│   │   │   ├── opportunity.py
│   │   │   ├── document.py
│   │   │   ├── clin.py
│   │   │   ├── deadline.py
│   │   │   └── session.py
│   │   ├── schemas/          # Pydantic request/response schemas
│   │   ├── services/         # Business logic
│   │   │   ├── tasks.py      # Celery background tasks
│   │   │   ├── sam_gov_scraper.py  # SAM.gov scraper
│   │   │   └── document_downloader.py  # Document downloader
│   │   ├── utils/            # Utility functions
│   │   │   └── sam_gov.py    # SAM.gov URL validation
│   │   └── main.py           # FastAPI application entry
│   ├── migrations/           # Alembic database migrations
│   └── data/                 # Local file storage
│       ├── documents/        # Downloaded documents
│       └── uploads/          # User uploaded files
├── frontend/
│   ├── src/
│   │   ├── components/       # React components
│   │   ├── contexts/         # React contexts (Auth)
│   │   ├── pages/            # Page components
│   │   │   ├── Login.jsx
│   │   │   ├── Signup.jsx
│   │   │   ├── Dashboard.jsx
│   │   │   ├── Analyze.jsx
│   │   │   └── OpportunityDetail.jsx
│   │   ├── utils/            # Utility functions
│   │   │   └── api.js        # API client
│   │   └── styles/           # CSS files
│   └── public/               # Static assets
├── scripts/                  # Setup and utility scripts
│   ├── setup_database.sh
│   ├── run_migrations.sh
│   └── set_db_password.sh
├── logs/                     # Application logs
├── requirements.txt          # Python dependencies
├── start.sh                  # Start all services
├── stop.sh                   # Stop all services
└── .env                      # Environment variables (not in git)
```

---

## 📚 API Documentation

### Interactive API Docs

Once the backend is running, access the interactive API documentation:

- **Swagger UI**: http://localhost:8000/docs
  - Interactive API explorer with "Try it out" functionality
  - Full request/response schemas
  - Authentication testing

- **ReDoc**: http://localhost:8000/redoc
  - Beautiful, responsive documentation
  - Clean, readable format

### Main Endpoints

#### Authentication
```
POST   /api/v1/auth/register    # User registration
POST   /api/v1/auth/login       # User login (returns JWT)
GET    /api/v1/auth/me          # Get current user (protected)
POST   /api/v1/auth/logout      # Logout (protected)
```

#### Opportunities
```
GET    /api/v1/opportunities                    # List all opportunities (protected)
POST   /api/v1/opportunities                    # Create new opportunity (protected)
GET    /api/v1/opportunities/{id}               # Get opportunity details (protected)
DELETE /api/v1/opportunities/{id}               # Delete opportunity (protected)
GET    /api/v1/opportunities/{id}/documents/{doc_id}/view  # View document (protected)
```

### Example: Creating an Opportunity

```bash
# 1. Login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "yourpassword"}'

# Response: {"access_token": "eyJ...", "token_type": "bearer"}

# 2. Create Opportunity (use token from step 1)
curl -X POST http://localhost:8000/api/v1/opportunities \
  -H "Authorization: Bearer eyJ..." \
  -H "Content-Type: application/json" \
  -d '{"sam_gov_url": "https://sam.gov/workspace/contract/opp/.../view"}'
```

---

## 💻 Development

### Running Tests

```bash
# Backend tests (when implemented)
pytest backend/tests/

# Frontend tests (when implemented)
cd frontend
npm test
```

### Code Style

```bash
# Python formatting with black (if configured)
black backend/

# Python linting with flake8 (if configured)
flake8 backend/
```

### Database Migrations

```bash
# Create a new migration
alembic revision --autogenerate -m "Description of changes"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1
```

### Debugging

- **Backend logs**: Check `logs/backend.log`
- **Celery logs**: Check `logs/celery.log`
- **Frontend logs**: Check `logs/frontend.log`

---

## 🚢 Deployment

### Digital Ocean App Platform

See [DEPLOYMENT.md](./DEPLOYMENT.md) for detailed deployment instructions.

**Quick Deploy:**

1. Push code to your Git repository
2. Connect repository to Digital Ocean App Platform
3. Configure environment variables in App Platform dashboard
4. Deploy!

### Docker Deployment

```bash
# Build and run with Docker Compose
docker-compose up -d

# Or build individual services
docker build -f Dockerfile.backend -t samgov-backend .
docker build -f Dockerfile.frontend -t samgov-frontend .
```

---

## 📊 Project Status

### Phase 1: Foundation & Core Scraping (In Progress)

| Feature | Status |
|---------|--------|
| User Authentication | ✅ Complete |
| SAM.gov Scraping | ✅ Complete |
| Document Downloads | ✅ Complete |
| Contact Info Extraction | ✅ Complete |
| Frontend UI | ✅ Complete |
| Document Analysis | 🚧 In Progress |
| CLIN Extraction | ⏳ Planned |
| Deadline Extraction (from docs) | ⏳ Planned |

### Phase 2: Research & Automation (Planned)

- Manufacturer research
- Email integration
- Calendar integration

### Phase 3: Advanced Features (Planned)

- Form automation
- Quote generation
- Reporting dashboard

---

## 🤝 Contributing

This is a private project. For internal contributors:

1. Create a feature branch from `main`
2. Make your changes
3. Test thoroughly
4. Submit a pull request

---

## 📝 License

Proprietary - All rights reserved

---

## 📞 Support

For issues, questions, or feature requests, please contact the development team.

---

<div align="center">

**Built with ❤️ for Government Contractors**

[Back to Top](#-samgov-ai---government-contract-analysis-platform)

</div>
