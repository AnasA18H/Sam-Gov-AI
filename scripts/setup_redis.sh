#!/bin/bash
# Redis setup script
# Run this script to set up Redis for development

set -e

echo "=========================================="
echo "Redis Setup"
echo "=========================================="

# Check if Redis is installed
if ! command -v redis-server &> /dev/null; then
    echo "Redis is not installed. Installing..."
    sudo apt update
    sudo apt install -y redis-server
    echo "✓ Redis installed"
else
    echo "✓ Redis is already installed"
fi

# Start Redis service
echo "Starting Redis service..."
sudo systemctl start redis-server
sudo systemctl enable redis-server
echo "✓ Redis service started"

# Test Redis connection
echo "Testing Redis connection..."
if redis-cli ping | grep -q PONG; then
    echo "✓ Redis is running and responding"
else
    echo "✗ Redis is not responding"
    exit 1
fi

# Update .env file
ENV_FILE=".env"
if [ -f "$ENV_FILE" ]; then
    echo "Updating .env file with Redis URL..."
    sed -i "s|REDIS_URL=.*|REDIS_URL=redis://localhost:6379/0|" "$ENV_FILE"
    sed -i "s|REDIS_CELERY_URL=.*|REDIS_CELERY_URL=redis://localhost:6379/1|" "$ENV_FILE"
    echo "✓ .env file updated"
fi

echo ""
echo "=========================================="
echo "Redis Setup Complete!"
echo "=========================================="
echo ""
echo "Redis is running on: redis://localhost:6379"
echo ""
echo "Test connection:"
echo "  redis-cli ping"
echo ""
