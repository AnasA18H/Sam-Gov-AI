"""draft_quote_emails table

Persist draft quote emails per opportunity. Generate saves; send/discard delete from DB.

Revision ID: h9c0d1e2f3a4
Revises: g8b9c0d1e2f3
Create Date: 2026-02-12

"""
from alembic import op
import sqlalchemy as sa


revision = 'h9c0d1e2f3a4'
down_revision = 'g8b9c0d1e2f3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'draft_quote_emails',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('opportunity_id', sa.Integer(), nullable=False),
        sa.Column('to', sa.String(255), nullable=False),
        sa.Column('to_name', sa.String(255), nullable=True),
        sa.Column('subject', sa.String(500), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('contact_type', sa.String(20), nullable=False),
        sa.Column('clin_id', sa.Integer(), nullable=True),
        sa.Column('clin_number', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['clin_id'], ['clins.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['opportunity_id'], ['opportunities.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_draft_quote_emails_opportunity_id'), 'draft_quote_emails', ['opportunity_id'], unique=False)
    op.create_index(op.f('ix_draft_quote_emails_clin_id'), 'draft_quote_emails', ['clin_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_draft_quote_emails_clin_id'), table_name='draft_quote_emails')
    op.drop_index(op.f('ix_draft_quote_emails_opportunity_id'), table_name='draft_quote_emails')
    op.drop_table('draft_quote_emails')
