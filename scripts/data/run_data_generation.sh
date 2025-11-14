#!/bin/bash

# Synthetic Data Generation Script for Warehouse Operational Assistant
# This script generates comprehensive synthetic data across all databases

set -e

echo "🚀 Starting Warehouse Operational Assistant Synthetic Data Generation"
echo "=================================================================="

# Check if we're in the right directory
if [ ! -f "generate_synthetic_data.py" ]; then
    echo "❌ Error: Please run this script from the scripts/ directory"
    exit 1
fi

# Check if virtual environment exists
if [ ! -d "../.venv" ]; then
    echo "❌ Error: Virtual environment not found. Please run from project root:"
    echo "   python -m venv .venv"
    echo "   source .venv/bin/activate"
    echo "   pip install -r requirements.txt"
    exit 1
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source ../.venv/bin/activate

# Install additional requirements for data generation
echo "📦 Installing synthetic data generation requirements..."
pip install -r requirements_synthetic_data.txt

# Check if databases are running
echo "🔍 Checking database connections..."

# Check PostgreSQL
if ! pg_isready -h localhost -p 5435 -U warehouse_user > /dev/null 2>&1; then
    echo "❌ Error: PostgreSQL not running on port 5435"
    echo "   Please start PostgreSQL: docker-compose up -d postgres"
    exit 1
fi

# Check Redis
if ! redis-cli -h localhost -p 6379 ping > /dev/null 2>&1; then
    echo "❌ Error: Redis not running on port 6379"
    echo "   Please start Redis: docker-compose up -d redis"
    exit 1
fi

# Check Milvus (optional)
if ! nc -z localhost 19530 > /dev/null 2>&1; then
    echo "⚠️  Warning: Milvus not running on port 19530"
    echo "   Vector data generation will be skipped"
fi

echo "✅ Database connections verified"

# Run the synthetic data generator
echo "🎯 Starting synthetic data generation..."
python generate_synthetic_data.py

echo ""
echo "🎉 Synthetic data generation completed successfully!"
echo ""
echo "📊 Generated Data Summary:"
echo "   • 50 users across all roles (admin, manager, supervisor, operator, viewer)"
echo "   • 1,000 inventory items with realistic locations and quantities"
echo "   • 500 tasks with various statuses and realistic payloads"
echo "   • 100 safety incidents with different severities and types"
echo "   • 30 days of equipment telemetry data (50 pieces of equipment)"
echo "   • 200 audit log entries for user actions"
echo "   • 1,000 vector embeddings for knowledge base (if Milvus available)"
echo "   • Redis cache data for sessions and metrics"
echo ""
echo "🚀 Your warehouse is now ready for an impressive demo!"
echo ""
echo "💡 Next steps:"
echo "   1. Start the API server: cd .. && source .venv/bin/activate && python -m chain_server.app"
echo "   2. Start the frontend: cd src/src/ui/web && npm start"
echo "   3. Visit http://localhost:3001 to see your populated warehouse!"
