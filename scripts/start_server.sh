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

# Check if port is already in use
if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "⚠️  Port $PORT is already in use"
    echo "   Stopping existing process..."
    lsof -ti:$PORT | xargs kill -9 2>/dev/null || true
    sleep 2
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

