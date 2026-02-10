#!/bin/bash
# Clear all data from the database.
# Run from project root.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

if [ ! -d "venv" ]; then
    echo "Error: venv not found. Create it with: python3 -m venv venv"
    exit 1
fi

# Use --force to skip confirmation
if [ "$1" = "--force" ] || [ "$1" = "-f" ]; then
    exec python scripts/reset_database.py --force
else
    exec python scripts/reset_database.py
fi
