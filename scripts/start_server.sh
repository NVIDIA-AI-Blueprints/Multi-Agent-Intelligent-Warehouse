#!/bin/bash
# Start script for Warehouse Operational Assistant API server
# Ensures virtual environment is activated and starts the FastAPI server

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

# Check if virtual environment exists
if [ ! -d "env" ]; then
    echo "❌ Virtual environment not found!"
    echo "   Please run: ./scripts/setup/setup_environment.sh"
    exit 1
fi

# Activate virtual environment
echo "🔌 Activating virtual environment..."
source env/bin/activate

# Check if required packages are installed
if ! python -c "import fastapi" 2>/dev/null; then
    echo "❌ FastAPI not installed!"
    echo "   Installing dependencies..."
    pip install -r requirements.txt
fi

# Set default port if not set
PORT=${PORT:-8001}

# Check if port is already in use.
#
# This previously ran `lsof -ti:$PORT | xargs kill -9` unconditionally, which
# SIGKILLs whatever owns the port -- not necessarily a previous run of this
# server. On a developer machine port 8001 is commonly held by an unrelated
# service, and that process was destroyed without warning or confirmation.
# Refuse to start instead, and tell the user how to proceed.
if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
    OWNER_PID=$(lsof -ti:$PORT | head -1)
    OWNER_CMD=$(ps -p "$OWNER_PID" -o comm= 2>/dev/null || echo "unknown")
    echo "❌ Port $PORT is already in use by PID $OWNER_PID ($OWNER_CMD)"
    echo ""
    echo "   This script will not kill it -- it may not belong to this project."
    echo "   Either:"
    echo "     • run on another port:  PORT=8011 $0"
    echo "     • or stop it yourself:  kill $OWNER_PID"
    exit 1
fi

echo "🚀 Starting Warehouse Operational Assistant API server..."
echo "   Port: $PORT"
echo "   API: http://localhost:$PORT"
echo "   Docs: http://localhost:$PORT/docs"
echo ""
echo "   Press Ctrl+C to stop the server"
echo ""

# Start the server
python -m uvicorn src.api.app:app --reload --port $PORT --host 0.0.0.0

