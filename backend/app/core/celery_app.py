"""
Celery configuration for background tasks
"""
from celery import Celery
from .config import settings

# Create Celery app
celery_app = Celery(
    "samgov_ai",
    broker=settings.REDIS_CELERY_URL,
    backend=settings.REDIS_CELERY_URL,
    include=["backend.app.services.tasks"]
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,  # 25 minutes
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=50,
)
