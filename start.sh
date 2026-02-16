#!/bin/bash

###############################################################################
# Sam Gov AI - Application Startup Script
# This script starts all required services for the application
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

# Configuration
BACKEND_PORT=8000
FRONTEND_PORT=5173
BACKEND_URL="http://localhost:${BACKEND_PORT}"
FRONTEND_URL="http://localhost:${FRONTEND_PORT}"

# PID files for cleanup
BACKEND_PID_FILE="${SCRIPT_DIR}/.backend.pid"
FRONTEND_PID_FILE="${SCRIPT_DIR}/.frontend.pid"
CELERY_PID_FILE="${SCRIPT_DIR}/.celery.pid"
DB_VIEWER_PID_FILE="${SCRIPT_DIR}/.dbviewer.pid"
DB_VIEWER_PORT="${DB_VIEWER_PORT:-5050}"

###############################################################################
# Helper Functions
###############################################################################

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

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

# Cleanup function
cleanup() {
    print_header "Shutting Down Services"
    
    # Kill backend
    if [ -f "$BACKEND_PID_FILE" ]; then
        BACKEND_PID=$(cat "$BACKEND_PID_FILE")
        if kill -0 "$BACKEND_PID" 2>/dev/null; then
            print_info "Stopping backend server (PID: $BACKEND_PID)..."
            kill "$BACKEND_PID" 2>/dev/null || true
            rm -f "$BACKEND_PID_FILE"
        fi
    fi
    
    # Kill frontend
    if [ -f "$FRONTEND_PID_FILE" ]; then
        FRONTEND_PID=$(cat "$FRONTEND_PID_FILE")
        if kill -0 "$FRONTEND_PID" 2>/dev/null; then
            print_info "Stopping frontend server (PID: $FRONTEND_PID)..."
            kill "$FRONTEND_PID" 2>/dev/null || true
            rm -f "$FRONTEND_PID_FILE"
        fi
    fi
    
    # Kill Celery worker
    if [ -f "$CELERY_PID_FILE" ]; then
        CELERY_PID=$(cat "$CELERY_PID_FILE")
        if kill -0 "$CELERY_PID" 2>/dev/null; then
            print_info "Stopping Celery worker (PID: $CELERY_PID)..."
            kill "$CELERY_PID" 2>/dev/null || true
            rm -f "$CELERY_PID_FILE"
        fi
    fi

    # Kill DB viewer
    if [ -f "$DB_VIEWER_PID_FILE" ]; then
        DBVIEWER_PID=$(cat "$DB_VIEWER_PID_FILE")
        if kill -0 "$DBVIEWER_PID" 2>/dev/null; then
            print_info "Stopping DB viewer (PID: $DBVIEWER_PID)..."
            kill "$DBVIEWER_PID" 2>/dev/null || true
            rm -f "$DB_VIEWER_PID_FILE"
        fi
    fi
    
    # Kill any remaining processes (match start.sh process invocations)
    pkill -f "uvicorn.*backend.app.main" 2>/dev/null || true
    pkill -f "vite" 2>/dev/null || true
    pkill -f "celery.*backend.app.core.celery_app" 2>/dev/null || true
    pkill -f "dev-db-viewer/server.py" 2>/dev/null || true
    
    print_success "All services stopped"
    exit 0
}

# Trap SIGINT and SIGTERM
trap cleanup SIGINT SIGTERM

###############################################################################
# Pre-flight Checks
###############################################################################

print_header "Pre-flight Checks"

# Resolve venv path (venv or .venv)
VENV_DIR="${SCRIPT_DIR}/venv"
if [ -d "$VENV_DIR" ]; then
    :
elif [ -d "${SCRIPT_DIR}/.venv" ]; then
    VENV_DIR="${SCRIPT_DIR}/.venv"
else
    print_error "Python virtual environment not found!"
    print_info "Please run: python3 -m venv venv"
    exit 1
fi

# Check if requirements are installed
if [ ! -f "$VENV_DIR/bin/python" ]; then
    print_error "Python executable not found in venv!"
    exit 1
fi

# Load venv and check key packages
source "$VENV_DIR/bin/activate"
if ! python -c "import fastapi" 2>/dev/null; then
    print_warning "FastAPI not found in venv - installing requirements..."
    pip install -q -r requirements.txt || print_error "Failed to install requirements"
fi
print_success "Virtual environment loaded: $VIRTUAL_ENV"
# Keep venv active for the rest of the script (backend, Celery, migrations use it)

# Check if .env exists
if [ ! -f ".env" ]; then
    print_error ".env file not found!"
    print_info "Create .env in the project root (see extras/PASTE_INTO_ENV.txt and extras/SMTP_SETUP.md)"
    exit 1
fi

print_success "Virtual environment found: $VENV_DIR"
print_success ".env file found"

# Check PostgreSQL
if command -v psql &> /dev/null; then
    print_success "PostgreSQL client found"
else
    print_warning "PostgreSQL client not found (database operations may fail)"
fi

# Check Redis
if command -v redis-cli &> /dev/null; then
    if redis-cli ping &> /dev/null; then
        print_success "Redis is running"
    else
        print_warning "Redis is not running - starting Redis service..."
        sudo systemctl start redis-server 2>/dev/null || \
        sudo service redis-server start 2>/dev/null || \
        print_warning "Could not start Redis automatically. Please start it manually."
    fi
else
    print_warning "Redis client not found"
fi

# Check Node.js
if command -v node &> /dev/null; then
    NODE_VERSION=$(node --version)
    print_success "Node.js found: $NODE_VERSION"
    
    # Check if node_modules exists in frontend
    if [ ! -d "frontend/node_modules" ]; then
        print_warning "Frontend dependencies not installed"
        print_info "Installing frontend dependencies..."
        cd frontend
        npm install
        cd ..
        print_success "Frontend dependencies installed"
    else
        print_success "Frontend dependencies found"
    fi
else
    print_error "Node.js not found! Please install Node.js"
    exit 1
fi

###############################################################################
# Database Setup
###############################################################################

print_header "Database Setup"

# Ensure venv is active (already activated in pre-flight)
source "$VENV_DIR/bin/activate"

# Check database connection
print_info "Checking database connection..."
if python -c "from backend.app.core.database import engine; engine.connect(); print('OK')" 2>/dev/null; then
    print_success "Database connection successful"
else
    print_warning "Database connection failed - migrations may fail"
fi

# Ensure data directories exist (backend documents, Tavily results, logs)
print_info "Ensuring data directories exist..."
mkdir -p backend/data/documents
mkdir -p data/documents
mkdir -p data/uploads
mkdir -p data/debug_extracts
mkdir -p data/tavily_results
mkdir -p logs
print_success "Data directories ready"

# Run migrations
print_info "Running database migrations..."
alembic upgrade head || print_warning "Migrations may have failed"
print_success "Database migrations completed"

###############################################################################
# Start Backend Server
###############################################################################

print_header "Starting Backend Server"

# Check if backend is already running
if curl -s "$BACKEND_URL/health" &> /dev/null; then
    print_warning "Backend server is already running on port $BACKEND_PORT"
    print_info "Skipping backend startup"
else
    print_info "Starting FastAPI backend server (using venv)..."
    
    # Create logs directory if it doesn't exist
    mkdir -p logs
    
    # Start backend in background with venv Python so deps are correct
    source "$VENV_DIR/bin/activate"
    nohup "$VENV_DIR/bin/uvicorn" backend.app.main:app \
        --host 0.0.0.0 \
        --port "$BACKEND_PORT" \
        --reload \
        > logs/backend.log 2>&1 &
    
    BACKEND_PID=$!
    echo "$BACKEND_PID" > "$BACKEND_PID_FILE"
    
    # Wait for backend to start (with --reload, worker can take a few seconds)
    print_info "Waiting for backend to start..."
    sleep 4
    BACKEND_READY=0
    for i in 1 2 3 4 5 6; do
        if curl -s -o /dev/null -w "%{http_code}" "$BACKEND_URL/health" | grep -q 200; then
            BACKEND_READY=1
            break
        fi
        [ $i -lt 6 ] && sleep 2
    done
    
    if kill -0 "$BACKEND_PID" 2>/dev/null; then
        if [ "$BACKEND_READY" -eq 1 ]; then
            print_success "Backend server started (PID: $BACKEND_PID)"
            print_info "Backend URL: $BACKEND_URL"
            print_info "API Docs: $BACKEND_URL/docs"
        else
            print_warning "Backend process running but health check did not pass yet"
            print_info "Server may still be starting (--reload). Check logs/backend.log and try: curl $BACKEND_URL/health"
        fi
    else
        print_error "Backend server failed to start"
        print_info "Check logs/backend.log for details"
        rm -f "$BACKEND_PID_FILE"
    fi
fi

###############################################################################
# Start Celery Worker
###############################################################################

print_header "Starting Celery Worker"

# Stop any existing Celery worker so we start fresh (ensures new log file and unbuffered logging)
if [ -f "$CELERY_PID_FILE" ]; then
    CELERY_PID=$(cat "$CELERY_PID_FILE")
    if kill -0 "$CELERY_PID" 2>/dev/null; then
        print_info "Stopping existing Celery worker (PID: $CELERY_PID)..."
        kill "$CELERY_PID" 2>/dev/null || true
        sleep 2
    fi
    rm -f "$CELERY_PID_FILE"
fi
pkill -f "celery.*worker.*backend.app.core.celery_app" 2>/dev/null || true
sleep 1

print_info "Starting Celery worker for background tasks (using venv)..."

# Unbuffered output so logs appear immediately in logs/celery.log
export PYTHONUNBUFFERED=1

# Start Celery worker in background using venv binary
mkdir -p logs
nohup "$VENV_DIR/bin/celery" -A backend.app.core.celery_app worker \
    --loglevel=info \
    --logfile="$SCRIPT_DIR/logs/celery.log" \
    > logs/celery.log 2>&1 &

CELERY_PID=$!
echo "$CELERY_PID" > "$CELERY_PID_FILE"

# Wait for Celery to start
print_info "Waiting for Celery worker to start..."
sleep 2

# Check if Celery started successfully
if kill -0 "$CELERY_PID" 2>/dev/null; then
    print_success "Celery worker started (PID: $CELERY_PID)"
    print_info "Celery log: logs/celery.log"
else
    print_warning "Celery worker may have failed to start"
    print_info "Check logs/celery.log for details"
    rm -f "$CELERY_PID_FILE"
fi

###############################################################################
# Start Frontend Server
###############################################################################

print_header "Starting Frontend Server"

# Check if frontend is already running
if curl -s "$FRONTEND_URL" &> /dev/null 2>&1; then
    print_warning "Frontend server is already running on port $FRONTEND_PORT"
    print_info "Skipping frontend startup"
else
    print_info "Starting frontend dev server (Vite)..."
    
    cd frontend
    
    # Start frontend in background
    nohup npm run dev > "$SCRIPT_DIR/logs/frontend.log" 2>&1 &
    
    FRONTEND_PID=$!
    echo "$FRONTEND_PID" > "$FRONTEND_PID_FILE"
    
    cd ..
    
    # Wait for frontend to start
    print_info "Waiting for frontend to start..."
    sleep 5
    
    # Check if frontend started successfully
    if kill -0 "$FRONTEND_PID" 2>/dev/null; then
        print_success "Frontend server started (PID: $FRONTEND_PID)"
        print_info "Frontend URL: $FRONTEND_URL"
    else
        print_warning "Frontend process may have failed"
        print_info "Check logs/frontend.log for details"
    fi
fi

###############################################################################
# Start Dev DB Viewer (optional)
###############################################################################

print_header "Dev DB Viewer"

if [ -d "$SCRIPT_DIR/dev-db-viewer" ] && [ -f "$SCRIPT_DIR/dev-db-viewer/server.py" ]; then
    if curl -s "http://127.0.0.1:${DB_VIEWER_PORT}" &>/dev/null; then
        print_warning "DB viewer already running on port $DB_VIEWER_PORT"
        print_info "Skipping DB viewer startup"
    else
        print_info "Starting DB viewer on port $DB_VIEWER_PORT (using project venv)..."
        mkdir -p logs
        nohup env DB_VIEWER_PORT="$DB_VIEWER_PORT" "$VENV_DIR/bin/python" "$SCRIPT_DIR/dev-db-viewer/server.py" >> "$SCRIPT_DIR/logs/db-viewer.log" 2>&1 &
        DBVIEWER_PID=$!
        echo "$DBVIEWER_PID" > "$DB_VIEWER_PID_FILE"
        sleep 1
        if kill -0 "$DBVIEWER_PID" 2>/dev/null; then
            print_success "DB viewer started (PID: $DBVIEWER_PID)"
            print_info "DB viewer: http://127.0.0.1:${DB_VIEWER_PORT}"
        else
            print_warning "DB viewer may have failed to start"
            print_info "Check logs/db-viewer.log (ensure DATABASE_URL in .env is correct)"
            rm -f "$DB_VIEWER_PID_FILE"
        fi
    fi
else
    print_info "Dev DB viewer not found (optional); skip or add dev-db-viewer/ to enable"
fi

###############################################################################
# Final Status
###############################################################################

print_header "Application Started"

echo -e "${GREEN}✓${NC} Backend:  ${BLUE}$BACKEND_URL${NC}"
echo -e "${GREEN}✓${NC} Frontend: ${BLUE}$FRONTEND_URL${NC}"
echo -e "${GREEN}✓${NC} Celery:   ${BLUE}Background worker running${NC}"
if [ -f "$DB_VIEWER_PID_FILE" ] && kill -0 "$(cat "$DB_VIEWER_PID_FILE")" 2>/dev/null; then
echo -e "${GREEN}✓${NC} DB Viewer: ${BLUE}http://127.0.0.1:${DB_VIEWER_PORT}${NC}"
fi
echo ""
echo -e "${YELLOW}Useful Links:${NC}"
echo "  • Frontend:        $FRONTEND_URL"
echo "  • Backend API:     $BACKEND_URL"
echo "  • API Docs:        $BACKEND_URL/docs"
echo "  • ReDoc:           $BACKEND_URL/redoc"
echo "  • Health Check:    $BACKEND_URL/health"
[ -f "$DB_VIEWER_PID_FILE" ] && kill -0 "$(cat "$DB_VIEWER_PID_FILE")" 2>/dev/null && echo "  • DB Viewer:       http://127.0.0.1:${DB_VIEWER_PORT}"
echo ""
echo -e "${YELLOW}Logs:${NC}"
echo "  • Backend:   tail -f logs/backend.log"
echo "  • Frontend:  tail -f logs/frontend.log"
echo "  • Celery:    tail -f logs/celery.log"
[ -d "$SCRIPT_DIR/dev-db-viewer" ] && echo "  • DB Viewer:  tail -f logs/db-viewer.log"
echo ""
echo -e "${YELLOW}To stop all services:${NC}"
echo "  Press Ctrl+C or run: ./stop.sh"
echo ""
echo -e "${YELLOW}Note:${NC}"
echo "  • Document Analysis is disabled by default"
echo "  • Enable it via the toggle buttons in the UI"
echo "  • CLIN Extraction requires Document Analysis to be enabled"
echo ""
echo -e "${GREEN}Application is ready! Press Ctrl+C to stop all services.${NC}"
echo ""

# Keep script running and wait for interrupt
while true; do
    sleep 1
done
