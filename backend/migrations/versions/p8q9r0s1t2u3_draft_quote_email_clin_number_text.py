"""draft_quote_emails clin_number to Text for combined CLIN lists

Revision ID: p8q9r0s1t2u3
Revises: m6n7o8p9q0r1
Create Date: 2026-02-26

"""
from alembic import op
import sqlalchemy as sa


revision = "p8q9r0s1t2u3"
down_revision = "m6n7o8p9q0r1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "draft_quote_emails",
        "clin_number",
        existing_type=sa.String(50),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "draft_quote_emails",
        "clin_number",
        existing_type=sa.Text(),
        type_=sa.String(50),
        existing_nullable=True,
    )
