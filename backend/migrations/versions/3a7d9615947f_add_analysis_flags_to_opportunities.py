"""add_analysis_flags_to_opportunities

Revision ID: 3a7d9615947f
Revises: 1733af08c87f
Create Date: 2026-01-28 16:03:48.766110

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3a7d9615947f'
down_revision = '1733af08c87f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('opportunities', sa.Column('enable_document_analysis', sa.String(length=10), nullable=False, server_default='false'))
    op.add_column('opportunities', sa.Column('enable_clin_extraction', sa.String(length=10), nullable=False, server_default='false'))


def downgrade() -> None:
    op.drop_column('opportunities', 'enable_clin_extraction')
    op.drop_column('opportunities', 'enable_document_analysis')
