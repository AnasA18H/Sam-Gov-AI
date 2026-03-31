"""add phone to contractor_profile

Revision ID: l4m5n6o7p8q9
Revises: k3l4m5n6o7p8
Create Date: 2026-02-20

"""
from alembic import op
import sqlalchemy as sa


revision = "l4m5n6o7p8q9"
down_revision = "k3l4m5n6o7p8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("contractor_profiles", sa.Column("phone", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("contractor_profiles", "phone")
