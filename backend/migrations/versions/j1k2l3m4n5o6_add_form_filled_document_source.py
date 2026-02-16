"""Add FORM_FILLED to DocumentSource

Revision ID: j1k2l3m4n5o6
Revises: i0j1k2l3m4n5
Create Date: 2026-02-16

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "j1k2l3m4n5o6"
down_revision = "i0j1k2l3m4n5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL: add new value to documentsource enum.
    op.execute("ALTER TYPE documentsource ADD VALUE 'FORM_FILLED'")


def downgrade() -> None:
    # PostgreSQL does not support removing an enum value simply.
    # Existing rows with source='form_filled' would need to be updated first.
    pass
