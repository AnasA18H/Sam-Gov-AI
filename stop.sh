#!/bin/bash

###############################################################################
# Sam Gov AI - Application Stop Script
# This script stops all running services
###############################################################################

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# PID files
BACKEND_PID_FILE="${SCRIPT_DIR}/.backend.pid"
FRONTEND_PID_FILE="${SCRIPT_DIR}/.frontend.pid"
CELERY_PID_FILE="${SCRIPT_DIR}/.celery.pid"

print_header() {
    echo ""
    echo -e "${BLUE}=================================================================${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}=================================================================${NC}"
    echo ""
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

print_header "Stopping Application Services"

# Stop backend
if [ -f "$BACKEND_PID_FILE" ]; then
    BACKEND_PID=$(cat "$BACKEND_PID_FILE")
    if kill -0 "$BACKEND_PID" 2>/dev/null; then
        print_info "Stopping backend server (PID: $BACKEND_PID)..."
        kill "$BACKEND_PID" 2>/dev/null || true
        rm -f "$BACKEND_PID_FILE"
        print_success "Backend server stopped"
    else
        rm -f "$BACKEND_PID_FILE"
    fi
fi

# Stop frontend
if [ -f "$FRONTEND_PID_FILE" ]; then
    FRONTEND_PID=$(cat "$FRONTEND_PID_FILE")
    if kill -0 "$FRONTEND_PID" 2>/dev/null; then
        print_info "Stopping frontend server (PID: $FRONTEND_PID)..."
        kill "$FRONTEND_PID" 2>/dev/null || true
        rm -f "$FRONTEND_PID_FILE"
        print_success "Frontend server stopped"
    else
        rm -f "$FRONTEND_PID_FILE"
    fi
fi

# Stop Celery worker
if [ -f "$CELERY_PID_FILE" ]; then
    CELERY_PID=$(cat "$CELERY_PID_FILE")
    if kill -0 "$CELERY_PID" 2>/dev/null; then
        print_info "Stopping Celery worker (PID: $CELERY_PID)..."
        kill "$CELERY_PID" 2>/dev/null || true
        rm -f "$CELERY_PID_FILE"
        print_success "Celery worker stopped"
    else
        rm -f "$CELERY_PID_FILE"
    fi
fi

# Kill any remaining processes
print_info "Cleaning up remaining processes..."
pkill -f "uvicorn.*backend.app.main" 2>/dev/null || true
pkill -f "vite" 2>/dev/null || true
pkill -f "celery.*worker" 2>/dev/null || true

print_success "All services stopped"
