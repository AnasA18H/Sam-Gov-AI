# Sam Gov AI - Government Contract Analysis Platform

AI-powered web application for analyzing US Government contract solicitations from SAM.gov and streamlining the bid preparation process.

## Project Status: Phase 1 - Foundation & Core Scraping

### ✅ Completed Components

#### Backend Infrastructure
- ✅ **Environment Configuration**: `.env` support with comprehensive settings
- ✅ **Database Models**: Complete SQLAlchemy models for:
  - Users (authentication)
  - Sessions (JWT token management)
  - Opportunities (SAM.gov solicitations)
  - CLINs (Contract Line Items)
  - Documents (PDF/Word attachments)
  - Deadlines (submission due dates)
- ✅ **Database Configuration**: PostgreSQL setup with SQLAlchemy
- ✅ **Alembic Migrations**: Database migration system configured
- ✅ **Authentication System**: 
  - User registration and login
  - JWT token generation (access + refresh)
  - Protected route dependencies
  - Session management
- ✅ **API Endpoints**:
  - `/api/v1/auth/register` - User registration
  - `/api/v1/auth/login` - User login
  - `/api/v1/auth/me` - Get current user
  - `/api/v1/auth/logout` - Logout
  - `/api/v1/opportunities` - Create/list opportunities

#### Project Structure
```
sam-project/
├── backend/
│   ├── app/
│   │   ├── api/          # API route handlers
│   │   ├── core/         # Configuration, database, security
│   │   ├── models/       # SQLAlchemy database models
│   │   ├── schemas/      # Pydantic request/response schemas
│   │   ├── services/     # Business logic (to be implemented)
│   │   ├── utils/        # Utility functions (to be implemented)
│   │   └── main.py       # FastAPI application
│   └── migrations/       # Alembic database migrations
├── frontend/             # React application (to be implemented)
├── requirements.txt      # Python dependencies
└── .env.example         # Environment variables template
```

### 🚧 Next Steps (Phase 1 Continuation)

1. **Database Setup**
   - Install and configure PostgreSQL
   - Run Alembic migrations to create tables
   - Set up Redis for caching

2. **SAM.gov Scraping** (Week 2)
   - URL parser and validator
   - Playwright scraper for SAM.gov pages
   - Attachment downloader
   - Document storage (local or S3)

3. **Document Classification** (Week 2-3)
   - spaCy NLP model setup
   - Classification logic (product/service/both)
   - Confidence scoring

4. **Data Extraction** (Week 3)
   - Deadline extraction from documents
   - CLIN extraction (product/service details)
   - Delivery requirements parsing

5. **Frontend Development** (Week 3)
   - React setup with Vite
   - Login/Signup pages
   - Analysis input page (SAM.gov URL + file upload)
   - Results display page

## Setup Instructions

### Prerequisites
- Python 3.12+
- Node.js 18+
- PostgreSQL (to be installed)
- Redis (to be installed)

### Backend Setup

1. **Activate virtual environment**
   ```bash
   source venv/bin/activate
   ```

2. **Install dependencies** (already done)
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your database credentials
   ```

4. **Set up PostgreSQL**
   ```bash
   # Install PostgreSQL (Ubuntu/Debian)
   sudo apt install postgresql postgresql-contrib
   
   # Create database
   sudo -u postgres createdb samgov_db
   sudo -u postgres createuser samgov_user
   ```

5. **Run database migrations**
   ```bash
   cd backend
   alembic upgrade head
   ```

6. **Start the server**
   ```bash
   # From project root
   uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
   # Or use the compatibility entry point
   python app.py
   ```

### Frontend Setup (To be implemented)

```bash
cd frontend
npm install
npm run dev
```

## API Documentation

Once the server is running, visit:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Technology Stack

- **Backend**: FastAPI, SQLAlchemy, Alembic, Pydantic
- **Authentication**: JWT (python-jose), bcrypt (passlib)
- **Database**: PostgreSQL
- **Cache**: Redis
- **Web Scraping**: Playwright (to be implemented)
- **NLP/AI**: spaCy, scikit-learn, transformers (to be implemented)
- **Frontend**: React, Vite, TailwindCSS (to be implemented)

## Development Notes

- The project uses FastAPI (not Node.js/Express as mentioned in some docs)
- All database models are defined and ready for migration
- Authentication system is fully implemented
- SAM.gov scraping and document analysis are next priorities

## License

[To be determined]
