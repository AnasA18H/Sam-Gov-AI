"""add_manufacturers_and_dealers_tables

Revision ID: 87c66d5342c1
Revises: 3a7d9615947f
Create Date: 2026-01-31 08:57:25.640213

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '87c66d5342c1'
down_revision = '3a7d9615947f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum types (check if they exist first)
    conn = op.get_bind()
    
    # Check and create researchstatus enum
    result = conn.execute(sa.text("SELECT 1 FROM pg_type WHERE typname = 'researchstatus'"))
    if result.fetchone() is None:
        conn.execute(sa.text("CREATE TYPE researchstatus AS ENUM ('pending', 'in_progress', 'completed', 'failed', 'not_found')"))
    
    # Check and create verificationstatus enum
    result = conn.execute(sa.text("SELECT 1 FROM pg_type WHERE typname = 'verificationstatus'"))
    if result.fetchone() is None:
        conn.execute(sa.text("CREATE TYPE verificationstatus AS ENUM ('not_verified', 'verified', 'verification_failed')"))
    
    # Reference enum types for column definitions (create_type=False means don't try to create)
    research_status_enum = postgresql.ENUM('pending', 'in_progress', 'completed', 'failed', 'not_found', name='researchstatus', create_type=False)
    verification_status_enum = postgresql.ENUM('not_verified', 'verified', 'verification_failed', name='verificationstatus', create_type=False)
    
    # Create manufacturers table
    op.create_table('manufacturers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('opportunity_id', sa.Integer(), nullable=False),
        sa.Column('clin_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('cage_code', sa.String(length=20), nullable=True),
        sa.Column('part_number', sa.String(length=255), nullable=True),
        sa.Column('nsn', sa.String(length=50), nullable=True),
        sa.Column('website', sa.String(length=512), nullable=True),
        sa.Column('contact_email', sa.String(length=255), nullable=True),
        sa.Column('contact_phone', sa.String(length=50), nullable=True),
        sa.Column('address', sa.Text(), nullable=True),
        sa.Column('company_info', sa.JSON(), nullable=True),
        sa.Column('sam_gov_status', sa.String(length=50), nullable=True),
        sa.Column('sam_gov_verified', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('sam_gov_verification_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('website_verified', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('website_verification_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('verification_status', verification_status_enum, nullable=False, server_default='not_verified'),
        sa.Column('verification_notes', sa.Text(), nullable=True),
        sa.Column('research_status', research_status_enum, nullable=False, server_default='pending'),
        sa.Column('research_started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('research_completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('research_error', sa.Text(), nullable=True),
        sa.Column('research_source', sa.String(length=100), nullable=True),
        sa.Column('additional_data', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['opportunity_id'], ['opportunities.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['clin_id'], ['clins.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_manufacturers_id'), 'manufacturers', ['id'], unique=False)
    op.create_index(op.f('ix_manufacturers_opportunity_id'), 'manufacturers', ['opportunity_id'], unique=False)
    op.create_index(op.f('ix_manufacturers_clin_id'), 'manufacturers', ['clin_id'], unique=False)
    op.create_index(op.f('ix_manufacturers_name'), 'manufacturers', ['name'], unique=False)
    op.create_index(op.f('ix_manufacturers_cage_code'), 'manufacturers', ['cage_code'], unique=False)
    
    # Create dealers table
    op.create_table('dealers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('opportunity_id', sa.Integer(), nullable=False),
        sa.Column('clin_id', sa.Integer(), nullable=True),
        sa.Column('manufacturer_id', sa.Integer(), nullable=True),
        sa.Column('company_name', sa.String(length=255), nullable=False),
        sa.Column('website', sa.String(length=512), nullable=True),
        sa.Column('contact_email', sa.String(length=255), nullable=True),
        sa.Column('contact_phone', sa.String(length=50), nullable=True),
        sa.Column('address', sa.Text(), nullable=True),
        sa.Column('company_info', sa.JSON(), nullable=True),
        sa.Column('part_number', sa.String(length=255), nullable=True),
        sa.Column('nsn', sa.String(length=50), nullable=True),
        sa.Column('product_listed', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('pricing_info', sa.Text(), nullable=True),
        sa.Column('pricing_source', sa.String(length=100), nullable=True),
        sa.Column('pricing_amount', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('currency', sa.String(length=10), nullable=False, server_default='USD'),
        sa.Column('stock_status', sa.String(length=50), nullable=True),
        sa.Column('sam_gov_status', sa.String(length=50), nullable=True),
        sa.Column('sam_gov_verified', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('sam_gov_verification_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('website_verified', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('website_verification_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('manufacturer_authorized', sa.Boolean(), nullable=True),
        sa.Column('verification_status', verification_status_enum, nullable=False, server_default='not_verified'),
        sa.Column('verification_notes', sa.Text(), nullable=True),
        sa.Column('research_status', research_status_enum, nullable=False, server_default='pending'),
        sa.Column('research_started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('research_completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('research_error', sa.Text(), nullable=True),
        sa.Column('research_source', sa.String(length=100), nullable=True),
        sa.Column('search_query', sa.String(length=500), nullable=True),
        sa.Column('rank_score', sa.Integer(), nullable=True),
        sa.Column('additional_data', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['opportunity_id'], ['opportunities.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['clin_id'], ['clins.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['manufacturer_id'], ['manufacturers.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_dealers_id'), 'dealers', ['id'], unique=False)
    op.create_index(op.f('ix_dealers_opportunity_id'), 'dealers', ['opportunity_id'], unique=False)
    op.create_index(op.f('ix_dealers_clin_id'), 'dealers', ['clin_id'], unique=False)
    op.create_index(op.f('ix_dealers_manufacturer_id'), 'dealers', ['manufacturer_id'], unique=False)
    op.create_index(op.f('ix_dealers_company_name'), 'dealers', ['company_name'], unique=False)


def downgrade() -> None:
    # Drop tables
    op.drop_index(op.f('ix_dealers_company_name'), table_name='dealers')
    op.drop_index(op.f('ix_dealers_manufacturer_id'), table_name='dealers')
    op.drop_index(op.f('ix_dealers_clin_id'), table_name='dealers')
    op.drop_index(op.f('ix_dealers_opportunity_id'), table_name='dealers')
    op.drop_index(op.f('ix_dealers_id'), table_name='dealers')
    op.drop_table('dealers')
    
    op.drop_index(op.f('ix_manufacturers_cage_code'), table_name='manufacturers')
    op.drop_index(op.f('ix_manufacturers_name'), table_name='manufacturers')
    op.drop_index(op.f('ix_manufacturers_clin_id'), table_name='manufacturers')
    op.drop_index(op.f('ix_manufacturers_opportunity_id'), table_name='manufacturers')
    op.drop_index(op.f('ix_manufacturers_id'), table_name='manufacturers')
    op.drop_table('manufacturers')
    
    # Note: We don't drop enum types here as they might be used elsewhere
    # If needed, drop manually: DROP TYPE IF EXISTS researchstatus; DROP TYPE IF EXISTS verificationstatus;
