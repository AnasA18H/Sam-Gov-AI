"""add custom_stamps to contractor_profile

Revision ID: m6n7o8p9q0r1
Revises: l4m5n6o7p8q9
Create Date: 2026-02-26

"""
from alembic import op
import sqlalchemy as sa


revision = "m6n7o8p9q0r1"
down_revision = "o7p8q9r0s1t2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("contractor_profiles", sa.Column("custom_stamps", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("contractor_profiles", "custom_stamps")
