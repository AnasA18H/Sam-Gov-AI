"""add digital_signature_2 and digital_signature_3 to contractor_profile (max 3 signatures)

Revision ID: m5n6o7p8q9r0
Revises: l4m5n6o7p8q9
Create Date: 2026-02-26

"""
from alembic import op
import sqlalchemy as sa


revision = "m5n6o7p8q9r0"
down_revision = "l4m5n6o7p8q9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("contractor_profiles", sa.Column("digital_signature_2", sa.Text(), nullable=True))
    op.add_column("contractor_profiles", sa.Column("digital_signature_3", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("contractor_profiles", "digital_signature_3")
    op.drop_column("contractor_profiles", "digital_signature_2")
