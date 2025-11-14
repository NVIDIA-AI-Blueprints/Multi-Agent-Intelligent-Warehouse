#!/bin/bash
set -euo pipefail

# Warehouse Operational Assistant - Local API Runner
# Automatically finds a free port and starts the FastAPI application

echo "Starting Warehouse Operational Assistant API..."

# Check if virtual environment exists (try both .venv and env)
if [ -d "env" ]; then
    VENV_DIR="env"
elif [ -d ".venv" ]; then
    VENV_DIR=".venv"
else
    echo "Error: Virtual environment not found."
    echo "Please create a virtual environment first:"
    echo "  python3 -m venv env"
    echo "  source env/bin/activate  # Linux/macOS"
    echo "  # or: env\\Scripts\\activate  # Windows"
    echo "  pip install -r requirements.txt"
    exit 1
fi

# Activate virtual environment
source $VENV_DIR/bin/activate

# Use port 8002 for consistency
PORT=${PORT:-8002}

echo " Starting API on port $PORT"
echo " API will be available at: http://localhost:$PORT"
echo " API documentation: http://localhost:$PORT/docs"
echo " OpenAPI schema: http://localhost:$PORT/openapi.json"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

# Start the FastAPI application
uvicorn src.api.app:app --host 0.0.0.0 --port $PORT --reload