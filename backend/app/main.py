"""
Main FastAPI application
"""
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from .core.config import settings
from .core.database import Base, engine
from .api.router import api_router

# Send all backend.* loggers to logs/backend.log so autofill, API, etc. appear in one place
_log_dir = Path(__file__).resolve().parents[2] / "logs"
_log_dir.mkdir(parents=True, exist_ok=True)
_log_file = _log_dir / "backend.log"
_backend_logger = logging.getLogger("backend")
_backend_logger.setLevel(logging.INFO)
if not any(h.baseFilename == str(_log_file) for h in _backend_logger.handlers if getattr(h, "baseFilename", None)):
    _handler = logging.FileHandler(_log_file, encoding="utf-8")
    _handler.setLevel(logging.INFO)
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    _backend_logger.addHandler(_handler)

# Create database tables (in production, use Alembic migrations)
# Base.metadata.create_all(bind=engine)

# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-powered SAM.gov procurement analysis",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router)

# Avoid 404 when browser requests favicon (e.g. after OAuth redirect)
@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)

# Health check endpoints
@app.get("/")
async def root():
    return {
        "message": f"{settings.APP_NAME} API is running!",
        "status": "healthy",
        "version": settings.APP_VERSION,
        "tech_stack": "FastAPI, PostgreSQL, Redis, React, Docker",
        "endpoints": ["/", "/health", "/docs", "/redoc", f"{settings.API_V1_PREFIX}"]
    }

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "sam-gov-ai",
        "database": "postgresql",
        "cache": "redis"
    }
