"""
Main API router that combines all route modules
"""
from fastapi import APIRouter
from .auth import router as auth_router
from .opportunities import router as opportunities_router
from ..core.config import settings

api_router = APIRouter(prefix=settings.API_V1_PREFIX)

# Include all route modules
api_router.include_router(auth_router)
api_router.include_router(opportunities_router)
