"""deadline calendar_event_id and calendar_provider

Persist calendar event ids so we don't duplicate events when syncing deadlines to Google/Outlook.

Revision ID: g8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-02-11

"""
from alembic import op
import sqlalchemy as sa


revision = 'g8b9c0d1e2f3'
down_revision = 'f7a8b9c0d1e2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('deadlines', sa.Column('calendar_event_id', sa.String(255), nullable=True))
    op.add_column('deadlines', sa.Column('calendar_provider', sa.String(20), nullable=True))
    op.create_index(op.f('ix_deadlines_calendar_event_id'), 'deadlines', ['calendar_event_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_deadlines_calendar_event_id'), table_name='deadlines')
    op.drop_column('deadlines', 'calendar_provider')
    op.drop_column('deadlines', 'calendar_event_id')
