"""opportunity_unique_per_user: allow same SAM.gov URL per user (no cross-account conflict)

Revision ID: i0j1k2l3m4n5
Revises: h9c0d1e2f3a4
Create Date: 2026-02-05

"""
from alembic import op


revision = "i0j1k2l3m4n5"
down_revision = "h9c0d1e2f3a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop global unique indexes so different users can have the same SAM.gov URL
    op.drop_index("ix_opportunities_sam_gov_url", table_name="opportunities")
    op.create_index("ix_opportunities_sam_gov_url", "opportunities", ["sam_gov_url"], unique=False)

    op.drop_index("ix_opportunities_sam_gov_id", table_name="opportunities")
    op.create_index("ix_opportunities_sam_gov_id", "opportunities", ["sam_gov_id"], unique=False)

    op.drop_index("ix_opportunities_notice_id", table_name="opportunities")
    op.create_index("ix_opportunities_notice_id", "opportunities", ["notice_id"], unique=False)

    # One opportunity per URL per user
    op.create_unique_constraint(
        "uq_opportunities_user_sam_gov_url",
        "opportunities",
        ["user_id", "sam_gov_url"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_opportunities_user_sam_gov_url", "opportunities", type_="unique")

    op.drop_index("ix_opportunities_notice_id", table_name="opportunities")
    op.create_index("ix_opportunities_notice_id", "opportunities", ["notice_id"], unique=True)

    op.drop_index("ix_opportunities_sam_gov_id", table_name="opportunities")
    op.create_index("ix_opportunities_sam_gov_id", "opportunities", ["sam_gov_id"], unique=True)

    op.drop_index("ix_opportunities_sam_gov_url", table_name="opportunities")
    op.create_index("ix_opportunities_sam_gov_url", "opportunities", ["sam_gov_url"], unique=True)
