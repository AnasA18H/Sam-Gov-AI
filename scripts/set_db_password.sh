#!/bin/bash
# Set database password to match .env file
# This script updates the PostgreSQL user password to match what's in .env

set -e

ENV_FILE=".env"
DB_USER="samgov_user"

if [ ! -f "$ENV_FILE" ]; then
    echo "✗ .env file not found"
    exit 1
fi

# Extract password from DATABASE_URL in .env
DATABASE_URL=$(grep "^DATABASE_URL=" "$ENV_FILE" | cut -d'=' -f2-)
if [ -z "$DATABASE_URL" ]; then
    echo "✗ DATABASE_URL not found in .env"
    exit 1
fi

# Parse password from connection string (format: postgresql://user:password@host:port/db)
PASSWORD=$(echo "$DATABASE_URL" | sed -n 's|.*://[^:]*:\([^@]*\)@.*|\1|p')

if [ -z "$PASSWORD" ]; then
    echo "✗ Could not extract password from DATABASE_URL"
    echo "  Current DATABASE_URL: $DATABASE_URL"
    exit 1
fi

echo "Setting database password for user: $DB_USER"
echo "Password will be set to match .env file"

# Update password in PostgreSQL
sudo -u postgres psql <<EOF
ALTER USER $DB_USER WITH PASSWORD '$PASSWORD';
EOF

echo "✓ Database password updated successfully"
echo ""
echo "You can now test the connection:"
echo "  psql -U $DB_USER -d samgov_db -h localhost"
