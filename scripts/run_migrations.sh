#!/bin/bash
# Run database migrations
# This script runs Alembic migrations to create/update database tables

set -e

echo "=========================================="
echo "Running Database Migrations"
echo "=========================================="

# Activate virtual environment
if [ -d "venv" ]; then
    source venv/bin/activate
    echo "✓ Virtual environment activated"
else
    echo "✗ Virtual environment not found"
    exit 1
fi

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "✗ .env file not found. Please run setup_database.sh first"
    exit 1
fi

# Check if database is accessible
echo "Checking database connection..."
python -c "from backend.app.core.config import settings; from backend.app.core.database import engine; engine.connect(); print('✓ Database connection successful')" || {
    echo "✗ Database connection failed. Please check your .env file"
    exit 1
}

# Run migrations
echo ""
echo "Running Alembic migrations..."
# Run from project root (alembic.ini is in root)
alembic upgrade head

echo ""
echo "=========================================="
echo "Migrations Complete!"
echo "=========================================="
echo ""
echo "Database tables created/updated successfully"
echo ""
echo "Verify tables:"
echo "  psql -U samgov_user -d samgov_db -c '\dt'"
echo ""
