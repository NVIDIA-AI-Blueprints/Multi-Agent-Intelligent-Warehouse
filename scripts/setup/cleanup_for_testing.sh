#!/bin/bash
# Cleanup script to reset the environment for fresh notebook testing
# This will remove the virtual environment and stop services

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "🧹 Cleanup Script for Fresh Testing"
echo "============================================================"
echo ""
echo "This script will:"
echo "  1. Stop frontend (npm start)"
echo "  2. Stop backend (if running)"
echo "  3. Delete virtual environment (env/)"
echo "  4. Clean Python cache files"
echo "  5. Optionally stop Docker containers"
echo "  6. Optionally remove Jupyter kernel"
echo ""

read -p "Continue with cleanup? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 1
fi

cd "$PROJECT_ROOT"

# 1. Stop frontend
echo ""
echo "1️⃣  Stopping frontend..."
FRONTEND_PID=$(ps aux | grep -E "npm start" | grep -v grep | awk '{print $2}' | head -1)
if [ ! -z "$FRONTEND_PID" ]; then
    echo "   Found frontend process (PID: $FRONTEND_PID), stopping..."
    kill $FRONTEND_PID 2>/dev/null || true
    sleep 2
    # Force kill if still running
    kill -9 $FRONTEND_PID 2>/dev/null || true
    echo "   ✅ Frontend stopped"
else
    echo "   ℹ️  No frontend process found"
fi

# 2. Stop backend
echo ""
echo "2️⃣  Stopping backend..."
BACKEND_PID=$(ps aux | grep -E "uvicorn.*app:app|python.*app.py" | grep -v grep | grep "$PROJECT_ROOT" | awk '{print $2}' | head -1)
if [ ! -z "$BACKEND_PID" ]; then
    echo "   Found backend process (PID: $BACKEND_PID), stopping..."
    kill $BACKEND_PID 2>/dev/null || true
    sleep 2
    # Force kill if still running
    kill -9 $BACKEND_PID 2>/dev/null || true
    echo "   ✅ Backend stopped"
else
    echo "   ℹ️  No backend process found"
fi

# 3. Delete virtual environment
echo ""
echo "3️⃣  Removing virtual environment..."
if [ -d "env" ]; then
    echo "   Deleting env/ directory..."
    rm -rf env
    echo "   ✅ Virtual environment removed"
else
    echo "   ℹ️  No virtual environment found"
fi

# 4. Clean Python cache
echo ""
echo "4️⃣  Cleaning Python cache files..."
find . -type d -name "__pycache__" -exec rm -r {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true
find . -type f -name "*.pyo" -delete 2>/dev/null || true
find . -type d -name "*.egg-info" -exec rm -r {} + 2>/dev/null || true
echo "   ✅ Python cache cleaned"

# 5. Optional: Stop Docker containers
echo ""
read -p "5️⃣  Stop Docker infrastructure containers? (TimescaleDB, Redis, Milvus, Kafka) (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "   Stopping Docker containers..."
    cd "$PROJECT_ROOT"
    if command -v docker-compose &> /dev/null; then
        docker-compose -f deploy/compose/docker-compose.yaml down 2>/dev/null || true
    elif command -v docker &> /dev/null && docker compose version &> /dev/null; then
        docker compose -f deploy/compose/docker-compose.yaml down 2>/dev/null || true
    fi
    echo "   ✅ Docker containers stopped"
else
    echo "   ℹ️  Keeping Docker containers running"
fi

# 6. Optional: Remove Jupyter kernel
echo ""
read -p "6️⃣  Remove Jupyter kernel 'warehouse-assistant'? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "   Removing kernel..."
    jupyter kernelspec remove warehouse-assistant -f 2>/dev/null || true
    echo "   ✅ Kernel removed"
else
    echo "   ℹ️  Keeping kernel (you can re-register it in Step 3)"
fi

echo ""
echo "============================================================"
echo "✅ Cleanup complete!"
echo ""
echo "📋 Next steps:"
echo "   1. Open the notebook: jupyter notebook notebooks/setup/complete_setup_guide.ipynb"
echo "   2. Start from Step 1 and work through each step"
echo "   3. The notebook will create a fresh virtual environment in Step 3"
echo ""
echo "💡 Note: Your .env file and source code are preserved"
echo ""

