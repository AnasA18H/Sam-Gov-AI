"""add_extracted_rfp_info_to_opportunities

Revision ID: j2k3l4m5n6o7
Revises: i0j1k2l3m4n5
Create Date: 2026-02-20

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "j2k3l4m5n6o7"
down_revision = "i0j1k2l3m4n5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "opportunities",
        sa.Column("extracted_rfp_info", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("opportunities", "extracted_rfp_info")
