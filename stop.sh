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

# PID files and ports (must match start.sh)
BACKEND_PID_FILE="${SCRIPT_DIR}/.backend.pid"
FRONTEND_PID_FILE="${SCRIPT_DIR}/.frontend.pid"
CELERY_PID_FILE="${SCRIPT_DIR}/.celery.pid"
DB_VIEWER_PID_FILE="${SCRIPT_DIR}/.dbviewer.pid"
BACKEND_PORT=8000
FRONTEND_PORT=5173
DB_VIEWER_PORT="${DB_VIEWER_PORT:-5050}"

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

# 1) Stop all Docker services that may be using our ports (compose stack + any container on 8000/5173/5050)
if command -v docker &>/dev/null; then
    print_info "Checking for Docker Compose stack..."
    if (docker compose ps -q 2>/dev/null | grep -q .) || (docker-compose ps -q 2>/dev/null | grep -q .); then
        print_info "Stopping Docker Compose stack..."
        (docker compose down 2>/dev/null || docker-compose down 2>/dev/null) && print_success "Docker stack stopped" || true
    fi
    # Stop any Docker container publishing our dev ports (8000, 5173, 5050)
    for port in "$BACKEND_PORT" "$FRONTEND_PORT" "$DB_VIEWER_PORT"; do
        ids=$(docker ps -q 2>/dev/null | while read cid; do
            docker port "$cid" 2>/dev/null | grep -qE "0\.0\.0\.0:$port|:::$port" && echo "$cid"
        done || true)
        if [ -n "$ids" ]; then
            print_info "Stopping Docker container(s) using port $port..."
            echo "$ids" | xargs docker stop 2>/dev/null || true
        fi
    done
fi

# 2) Stop by PID files (local start.sh)
for label in "backend:$BACKEND_PID_FILE" "frontend:$FRONTEND_PID_FILE" "celery:$CELERY_PID_FILE" "db-viewer:$DB_VIEWER_PID_FILE"; do
    name="${label%%:*}"
    pf="${label#*:}"
    if [ -f "$pf" ]; then
        pid=$(cat "$pf" 2>/dev/null)
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            print_info "Stopping $name (PID: $pid)..."
            kill "$pid" 2>/dev/null || true
        fi
        rm -f "$pf"
    fi
done

# 3) Free ports (handles stale PIDs or processes not started by start.sh)
print_info "Freeing ports $BACKEND_PORT, $FRONTEND_PORT, $DB_VIEWER_PORT..."
for port in "$BACKEND_PORT" "$FRONTEND_PORT" "$DB_VIEWER_PORT"; do
    if command -v lsof &>/dev/null; then
        old=$(lsof -ti ":$port" 2>/dev/null || true)
        if [ -n "$old" ]; then
            print_info "Killing process(es) on port $port (PID: $old)"
            kill $old 2>/dev/null || true
        fi
    fi
    if command -v fuser &>/dev/null; then
        if fuser -s "${port}/tcp" 2>/dev/null; then
            print_info "Freeing port $port (fuser)"
            fuser -k "${port}/tcp" 2>/dev/null || true
        fi
    fi
done
sleep 1

# 4) pkill by pattern (match start.sh invocations)
print_info "Cleaning up process patterns..."
pkill -f "uvicorn.*backend.app.main" 2>/dev/null || true
pkill -f "uvicorn.*main:app" 2>/dev/null || true
pkill -f "vite" 2>/dev/null || true
pkill -f "celery.*backend.app.core.celery_app" 2>/dev/null || true
pkill -f "celery.*beat" 2>/dev/null || true
pkill -f "celery.*flower" 2>/dev/null || true
pkill -f "dev-db-viewer/server.py" 2>/dev/null || true

sleep 2

# 5) Force kill if still running
pkill -9 -f "uvicorn.*backend.app.main" 2>/dev/null || true
pkill -9 -f "celery.*backend.app.core.celery_app" 2>/dev/null || true

sleep 1
print_success "All services stopped"
