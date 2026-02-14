"""user_email_connections token columns to TEXT

Microsoft OAuth tokens can exceed VARCHAR(2048). Use TEXT for refresh_token and access_token.

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-02-11

"""
from alembic import op
import sqlalchemy as sa


revision = 'f7a8b9c0d1e2'
down_revision = 'e6f7a8b9c0d1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        'user_email_connections',
        'refresh_token',
        existing_type=sa.String(2048),
        type_=sa.Text(),
        existing_nullable=False,
    )
    op.alter_column(
        'user_email_connections',
        'access_token',
        existing_type=sa.String(2048),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        'user_email_connections',
        'refresh_token',
        existing_type=sa.Text(),
        type_=sa.String(2048),
        existing_nullable=False,
    )
    op.alter_column(
        'user_email_connections',
        'access_token',
        existing_type=sa.Text(),
        type_=sa.String(2048),
        existing_nullable=True,
    )
