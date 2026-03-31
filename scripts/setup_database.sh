#!/bin/bash
# Database setup script for PostgreSQL
# Run this script to set up the database for development

set -e

echo "=========================================="
echo "PostgreSQL Database Setup"
echo "=========================================="

# Check if PostgreSQL is installed
if ! command -v psql &> /dev/null; then
    echo "PostgreSQL is not installed. Installing..."
    sudo apt update
    sudo apt install -y postgresql postgresql-contrib
    echo "✓ PostgreSQL installed"
else
    echo "✓ PostgreSQL is already installed"
fi

# Start PostgreSQL service
echo "Starting PostgreSQL service..."
sudo systemctl start postgresql
sudo systemctl enable postgresql
echo "✓ PostgreSQL service started"

# Database configuration
DB_NAME="samgov_db"
DB_USER="samgov_user"
DB_PASSWORD="samgov_password_$(date +%s | sha256sum | base64 | head -c 16)"

echo ""
echo "Creating database and user..."
echo "Database: $DB_NAME"
echo "User: $DB_USER"

# Create database and user
sudo -u postgres psql <<EOF
-- Create user
CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';

-- Create database
CREATE DATABASE $DB_NAME OWNER $DB_USER;

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;

-- Connect to database and grant schema privileges
\c $DB_NAME
GRANT ALL ON SCHEMA public TO $DB_USER;
EOF

echo "✓ Database and user created"

# Update .env file
ENV_FILE=".env"
if [ -f "$ENV_FILE" ]; then
    echo ""
    echo "Updating .env file with database credentials..."
    # Backup existing .env
    cp "$ENV_FILE" "${ENV_FILE}.backup"
    
    # Update DATABASE_URL
    sed -i "s|DATABASE_URL=.*|DATABASE_URL=postgresql://$DB_USER:$DB_PASSWORD@localhost:5432/$DB_NAME|" "$ENV_FILE"
    echo "✓ .env file updated"
else
    echo ""
    echo "Creating .env file..."
    if [ -f ".env.example" ]; then
        cp .env.example "$ENV_FILE"
        echo "✓ Copied from .env.example"
    else
        # Create .env file with default values
        cat > "$ENV_FILE" <<ENVEOF
# Application
APP_NAME=Sam Gov AI
APP_VERSION=1.0.0
DEBUG=True
SECRET_KEY=$(openssl rand -hex 32)
API_V1_PREFIX=/api/v1

# Server
HOST=0.0.0.0
PORT=8000

# Database - PostgreSQL
DATABASE_URL=postgresql://$DB_USER:$DB_PASSWORD@localhost:5432/$DB_NAME
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20

# Redis
REDIS_URL=redis://localhost:6379/0
REDIS_CELERY_URL=redis://localhost:6379/1

# JWT Authentication
JWT_SECRET_KEY=$(openssl rand -hex 32)
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# CORS
CORS_ORIGINS=http://localhost:3000,http://localhost:5173

# File Storage
STORAGE_TYPE=local

# SAM.gov
SAM_GOV_BASE_URL=https://sam.gov
ENVEOF
        echo "✓ Created new .env file with defaults"
    fi
    # Update DATABASE_URL if it wasn't set correctly
    sed -i "s|DATABASE_URL=.*|DATABASE_URL=postgresql://$DB_USER:$DB_PASSWORD@localhost:5432/$DB_NAME|" "$ENV_FILE"
    echo "✓ Database URL configured"
fi

echo ""
echo "=========================================="
echo "Database Setup Complete!"
echo "=========================================="
echo ""
echo "Database credentials:"
echo "  Database: $DB_NAME"
echo "  User: $DB_USER"
echo "  Password: $DB_PASSWORD"
echo ""
echo "Connection string:"
echo "  postgresql://$DB_USER:$DB_PASSWORD@localhost:5432/$DB_NAME"
echo ""
echo "Next steps:"
echo "  1. Run migrations: cd backend && alembic upgrade head"
echo "  2. Verify tables: psql -U $DB_USER -d $DB_NAME -c '\dt'"
echo ""
