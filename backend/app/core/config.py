"""
Application configuration settings
"""
from pydantic_settings import BaseSettings
from typing import List
import os
from pathlib import Path


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # Application (all secrets read from .env; no defaults in code)
    APP_NAME: str = "Gov OPs AI"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = os.getenv("DEBUG", "True").lower() == "true"
    SECRET_KEY: str = ""  # Set in .env
    API_V1_PREFIX: str = "/api/v1"
    
    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # Database
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/samgov_db"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_CELERY_URL: str = "redis://localhost:6379/1"
    
    # JWT (set JWT_SECRET_KEY in .env)
    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"
    FRONTEND_URL: str = "http://localhost:5173"  # Redirect after OAuth connect-email
    
    # File Storage
    STORAGE_TYPE: str = "local"  # local or s3
    STORAGE_BASE_PATH: str = "backend/data/documents"  # Base path for local storage
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"
    S3_BUCKET_NAME: str = "samgov-documents"
    AWS_S3_ENDPOINT_URL: str = ""
    AWS_S3_PUBLIC_BASE_URL: str = ""
    
    # SAM.gov
    SAM_GOV_BASE_URL: str = "https://sam.gov"
    
    # Email
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    
    # Google OAuth
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = ""
    
    # Microsoft OAuth
    MICROSOFT_CLIENT_ID: str = ""
    MICROSOFT_CLIENT_SECRET: str = ""
    MICROSOFT_TENANT_ID: str = ""  # Directory (tenant) ID from Azure; use "common" for multi-tenant
    MICROSOFT_REDIRECT_URI: str = ""
    
    # Monitoring
    SENTRY_DSN: str = ""
    
    # Anthropic / LLM – set in .env
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-3-5-sonnet-20241022"
    # Groq / LLM fallback – set in .env
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"  # was llama-3.1-70b-versatile (decommissioned)
    # Autofill LLM call timeout (seconds). Override in .env if primary (Claude) keeps timing out (e.g. AUTOFILL_LLM_TIMEOUT_SEC=90).
    AUTOFILL_LLM_TIMEOUT_SEC: int = 70
    # Gemini – set in .env
    GEMINI_API_KEY: str = ""
    # Tavily (dealer/manufacturer search) – set in .env
    TAVILY_API_KEY: str = ""
    TAVILY_SEARCH_DEPTH: str = "advanced"
    TAVILY_MAX_RESULTS: int = 12
    TAVILY_INCLUDE_ANSWER: bool = True
    TAVILY_MAX_QUERIES_PER_CLIN: int = 8
    TAVILY_INCLUDE_DOMAINS: str = ""
    TAVILY_TIME_RANGE: str = ""
    TAVILY_REUSE_BY_PRODUCT: bool = True  # one Tavily run per unique (manufacturer, product)
    TAVILY_PARALLEL_MAX_WORKERS: int = 4  # 1 = sequential
    # Google Document AI – set paths/ids in .env
    GOOGLE_SERVICE_ACCOUNT_JSON: str = ""
    GOOGLE_PROJECT_ID: str = ""
    GOOGLE_PROCESSOR_ID: str = ""
    GOOGLE_LOCATION: str = "us"
    GOOGLE_DOCAI_ENABLED: bool = True

    # Project paths
    PROJECT_ROOT: Path = Path(__file__).parent.parent.parent.parent  # Go up 4 levels from backend/app/core/config.py
    DATA_DIR: Path = PROJECT_ROOT / "data"
    UPLOADS_DIR: Path = DATA_DIR / "uploads"
    DOCUMENTS_DIR: Path = DATA_DIR / "documents"
    DEBUG_EXTRACTS_DIR: Path = DATA_DIR / "debug_extracts"  # For debugging: saved extracted text
    
    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins string into list"""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"  # Ignore extra env vars (e.g. from rolled-back features)


# Create settings instance
settings = Settings()

# Ensure data directories exist
settings.DATA_DIR.mkdir(exist_ok=True)
settings.UPLOADS_DIR.mkdir(exist_ok=True)
settings.DOCUMENTS_DIR.mkdir(exist_ok=True)
settings.DEBUG_EXTRACTS_DIR.mkdir(exist_ok=True)