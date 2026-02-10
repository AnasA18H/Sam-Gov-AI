"""
Alembic environment configuration.
Uses settings.DATABASE_URL for both offline and online so migrations always hit the same DB as the app.
"""
from logging.config import fileConfig
from sqlalchemy import create_engine, pool
from alembic import context
import os
import sys

# Add backend directory to path
backend_dir = os.path.dirname(os.path.dirname(__file__))
project_root = os.path.dirname(backend_dir)
sys.path.insert(0, project_root)
sys.path.insert(0, backend_dir)

# Import models and config
from backend.app.core.config import settings
from backend.app.core.database import Base
from backend.app.models import *  # noqa: F401 - Import all models for metadata

# this is the Alembic Config object
config = context.config

# Use app DB URL everywhere (ignore alembic.ini sqlalchemy.url)
url = settings.DATABASE_URL
config.set_main_option("sqlalchemy.url", url)

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode. Use same DATABASE_URL as the app."""
    connectable = create_engine(url, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
