"""
Application configuration settings
"""
from pydantic_settings import BaseSettings
from typing import List
import os
from pathlib import Path


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # Application
    APP_NAME: str = "Sam Gov AI"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = os.getenv("DEBUG", "True").lower() == "true"
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-this-secret-key-in-production")
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
    
    # JWT
    JWT_SECRET_KEY: str = "change-this-jwt-secret-key"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"
    
    # File Storage
    STORAGE_TYPE: str = "local"  # local or s3
    STORAGE_BASE_PATH: str = "backend/data/documents"  # Base path for local storage
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"
    S3_BUCKET_NAME: str = "samgov-documents"
    
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
    MICROSOFT_REDIRECT_URI: str = ""
    
    # Monitoring
    SENTRY_DSN: str = ""
    
    # Anthropic / LLM (using Claude models)
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", """")
    ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-3-haiku-20240307")  # Claude 3 Haiku model
    
    # Groq / LLM Fallback (using Groq models)
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.1-70b-versatile")  # Groq model for fallback
    
    # Google Document AI
    GOOGLE_SERVICE_ACCOUNT_JSON: str = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")  # Path to service account JSON file (default: extras/resolute-planet-485419-f8-f543cf0a64b5.json)
    GOOGLE_PROJECT_ID: str = os.getenv("GOOGLE_PROJECT_ID", "740282826965")
    GOOGLE_PROCESSOR_ID: str = os.getenv("GOOGLE_PROCESSOR_ID", "5292c35158dea675")  # Document OCR Processor
    GOOGLE_LOCATION: str = os.getenv("GOOGLE_LOCATION", "us")
    GOOGLE_DOCAI_ENABLED: bool = os.getenv("GOOGLE_DOCAI_ENABLED", "True").lower() == "true"  # Enable/disable Document AI
    
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


# Create settings instance
settings = Settings()

# Ensure data directories exist
settings.DATA_DIR.mkdir(exist_ok=True)
settings.UPLOADS_DIR.mkdir(exist_ok=True)
settings.DOCUMENTS_DIR.mkdir(exist_ok=True)
settings.DEBUG_EXTRACTS_DIR.mkdir(exist_ok=True)