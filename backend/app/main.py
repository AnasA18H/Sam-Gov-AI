"""
Main FastAPI application
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .core.config import settings
from .core.database import Base, engine
from .api.router import api_router

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
