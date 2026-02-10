"""auth_provider and email verification

Revision ID: e6f7a8b9c0d1
Revises: d4e5f6a7b8c9
Create Date: 2026-02-10

- Add auth_provider: 'email' | 'google' | 'microsoft' (one account per method per email).
- Add verification_code, verification_code_expires_at for email verification.
- Unique constraint (email, auth_provider) instead of unique email.
"""
from alembic import op
import sqlalchemy as sa


revision = 'e6f7a8b9c0d1'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add auth_provider with default 'email' for existing rows
    op.add_column('users', sa.Column('auth_provider', sa.String(20), nullable=True))
    op.execute("UPDATE users SET auth_provider = 'email' WHERE auth_provider IS NULL")
    op.alter_column('users', 'auth_provider', nullable=False)

    op.add_column('users', sa.Column('verification_code', sa.String(10), nullable=True))
    op.add_column('users', sa.Column('verification_code_expires_at', sa.DateTime(timezone=True), nullable=True))

    # Drop old unique index on email, add unique (email, auth_provider)
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.create_index('ix_users_email_auth_provider', 'users', ['email', 'auth_provider'], unique=True)
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_index('ix_users_email_auth_provider', table_name='users')
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)

    op.drop_column('users', 'verification_code_expires_at')
    op.drop_column('users', 'verification_code')
    op.drop_column('users', 'auth_provider')
