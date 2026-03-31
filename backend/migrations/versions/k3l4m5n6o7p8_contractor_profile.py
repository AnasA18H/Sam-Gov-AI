"""contractor_profile

Revision ID: k3l4m5n6o7p8
Revises: j2k3l4m5n6o7
Create Date: 2026-02-20

"""
from alembic import op
import sqlalchemy as sa


revision = "k3l4m5n6o7p8"
down_revision = "j2k3l4m5n6o7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contractor_profiles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("company_name", sa.String(500), nullable=True),
        sa.Column("company_address", sa.Text(), nullable=True),
        sa.Column("uei", sa.String(50), nullable=True),
        sa.Column("cage", sa.String(20), nullable=True),
        sa.Column("tin", sa.String(50), nullable=True),
        sa.Column("contract_officer_name", sa.String(255), nullable=True),
        sa.Column("digital_signature", sa.Text(), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_unique_constraint("uq_contractor_profiles_user_id", "contractor_profiles", ["user_id"])


def downgrade() -> None:
    op.drop_table("contractor_profiles")
