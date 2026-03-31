"""add converted_from_document_id to documents

Revision ID: o7p8q9r0s1t2
Revises: n6o7p8q9r0s1
Create Date: 2026-02-26

"""
from alembic import op
import sqlalchemy as sa


revision = "o7p8q9r0s1t2"
down_revision = "n6o7p8q9r0s1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("converted_from_document_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_documents_converted_from_document_id",
        "documents",
        "documents",
        ["converted_from_document_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_documents_converted_from_document_id",
        "documents",
        ["converted_from_document_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_documents_converted_from_document_id", table_name="documents")
    op.drop_constraint("fk_documents_converted_from_document_id", "documents", type_="foreignkey")
    op.drop_column("documents", "converted_from_document_id")
