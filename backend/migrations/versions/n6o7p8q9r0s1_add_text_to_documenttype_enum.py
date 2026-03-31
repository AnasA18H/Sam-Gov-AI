"""add TEXT to documenttype enum

Revision ID: n6o7p8q9r0s1
Revises: m5n6o7p8q9r0
Create Date: 2026-02-26

"""
from alembic import op


revision = "n6o7p8q9r0s1"
down_revision = "m5n6o7p8q9r0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL: add new value to documenttype enum (uppercase - SQLAlchemy sends enum name for this column)
    op.execute("ALTER TYPE documenttype ADD VALUE IF NOT EXISTS 'TEXT'")


def downgrade() -> None:
    # PostgreSQL does not support removing an enum value; would require recreating the type and column
    pass
