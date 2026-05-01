"""
Celery configuration for background tasks
"""
import logging
from celery import Celery
from celery.signals import worker_process_init
from .config import settings

# Configure SSL if rediss is used (required for DigitalOcean Managed Redis)
broker_use_ssl = None
if settings.REDIS_CELERY_URL.startswith("rediss://"):
    broker_use_ssl = {"ssl_cert_reqs": "none"}  # DO managed redis uses SSL but cert reqs can be relaxed

# Create Celery app
celery_app = Celery(
    "samgov_ai",
    broker=settings.REDIS_CELERY_URL,
    backend=settings.REDIS_CELERY_URL,
    include=["backend.app.services.tasks"],
)

if broker_use_ssl:
    celery_app.conf.update(
        broker_use_ssl=broker_use_ssl,
        redis_backend_use_ssl=broker_use_ssl,
    )

# Ensure task module is imported so all tasks (e.g. rerun_clins_only) are registered
import importlib
importlib.import_module("backend.app.services.tasks")

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


@worker_process_init.connect
def _configure_log_flushing(**kwargs):
    """Make all root logger handlers flush after each emit so logs appear immediately in log files."""
    root = logging.getLogger()
    for h in root.handlers:
        stream = getattr(h, "stream", None)
        if stream is not None:
            orig_emit = h.emit
            def flush_emit(record, _h=h, _orig=orig_emit):
                _orig(record)
                try:
                    _h.flush()
                except Exception:
                    pass
            h.emit = flush_emit
