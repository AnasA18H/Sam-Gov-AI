#!/bin/bash

###############################################################################
# Sam Gov AI - Application Stop Script
# Stops services started by start.sh (PID files) or by docker-compose
###############################################################################

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# PID files (must match start.sh)
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

# 1) Stop Docker Compose stack if it was used
if command -v docker &>/dev/null; then
    print_info "Checking for Docker Compose stack..."
    if (docker compose ps -q 2>/dev/null | grep -q .) || (docker-compose ps -q 2>/dev/null | grep -q .); then
        print_info "Stopping Docker Compose stack..."
        (docker compose down 2>/dev/null || docker-compose down 2>/dev/null) && print_success "Docker stack stopped" || true
    fi
fi

# 2) Stop by PID files (local start.sh)
STOPPED=""

if [ -f "$BACKEND_PID_FILE" ]; then
    BACKEND_PID=$(cat "$BACKEND_PID_FILE")
    if kill -0 "$BACKEND_PID" 2>/dev/null; then
        print_info "Stopping backend server (PID: $BACKEND_PID)..."
        kill "$BACKEND_PID" 2>/dev/null || true
        STOPPED="${STOPPED} backend"
    fi
    rm -f "$BACKEND_PID_FILE"
fi

if [ -f "$FRONTEND_PID_FILE" ]; then
    FRONTEND_PID=$(cat "$FRONTEND_PID_FILE")
    if kill -0 "$FRONTEND_PID" 2>/dev/null; then
        print_info "Stopping frontend server (PID: $FRONTEND_PID)..."
        kill "$FRONTEND_PID" 2>/dev/null || true
        STOPPED="${STOPPED} frontend"
    fi
    rm -f "$FRONTEND_PID_FILE"
fi

if [ -f "$CELERY_PID_FILE" ]; then
    CELERY_PID=$(cat "$CELERY_PID_FILE")
    if kill -0 "$CELERY_PID" 2>/dev/null; then
        print_info "Stopping Celery worker (PID: $CELERY_PID)..."
        kill "$CELERY_PID" 2>/dev/null || true
        STOPPED="${STOPPED} celery"
    fi
    rm -f "$CELERY_PID_FILE"
fi

# 3) Clean up any remaining processes (match start.sh)
print_info "Cleaning up remaining processes..."
pkill -f "uvicorn.*backend.app.main" 2>/dev/null || true
pkill -f "vite" 2>/dev/null || true
pkill -f "celery.*backend.app.core.celery_app" 2>/dev/null || true
pkill -f "celery.*beat" 2>/dev/null || true
pkill -f "celery.*flower" 2>/dev/null || true

sleep 1

# Force kill if still running
pkill -9 -f "uvicorn.*backend.app.main" 2>/dev/null || true
pkill -9 -f "celery.*backend.app.core.celery_app" 2>/dev/null || true

[ -n "$STOPPED" ] && print_success "Stopped:$STOPPED"
print_success "All services stopped"
