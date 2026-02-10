"""add_manufacturer_dealer_research_to_clins

Revision ID: a1b2c3d4e5f6
Revises: 3a7d9615947f
Create Date: 2026-02-09

"""
from alembic import op
import sqlalchemy as sa


revision = 'a1b2c3d4e5f6'
down_revision = '3a7d9615947f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('clins', sa.Column('manufacturer_research', sa.JSON(), nullable=True))
    op.add_column('clins', sa.Column('dealer_research', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('clins', 'dealer_research')
    op.drop_column('clins', 'manufacturer_research')
