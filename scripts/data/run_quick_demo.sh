#!/bin/bash

# Quick Demo Data Generation Script
# Generates a smaller set of realistic demo data for quick testing

set -e

echo "🚀 Quick Demo Data Generation for Warehouse Operational Assistant"
echo "==============================================================="

# Check if we're in the right directory
if [ ! -f "quick_demo_data.py" ]; then
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

# Install additional requirements
echo "📦 Installing requirements..."
pip install bcrypt psycopg[binary]

# Check if PostgreSQL is running
echo "🔍 Checking PostgreSQL connection..."
if ! pg_isready -h localhost -p 5435 -U warehouse_user > /dev/null 2>&1; then
    echo "❌ Error: PostgreSQL not running on port 5435"
    echo "   Please start PostgreSQL: docker-compose up -d postgres"
    exit 1
fi

echo "✅ PostgreSQL connection verified"

# Run the quick demo data generator
echo "🎯 Starting quick demo data generation..."
python quick_demo_data.py

echo ""
echo "🎉 Quick demo data generation completed successfully!"
echo ""
echo "📊 Generated Demo Data:"
echo "   • 12 users across all roles"
echo "   • 25 inventory items (including low stock alerts)"
echo "   • 8 tasks with various statuses"
echo "   • 8 safety incidents with different severities"
echo "   • 7 days of equipment telemetry data"
echo "   • 50 audit log entries"
echo ""
echo "🚀 Your warehouse is ready for a quick demo!"
echo ""
echo "💡 Next steps:"
echo "   1. Start the API server: cd .. && source .venv/bin/activate && python -m chain_server.app"
echo "   2. Start the frontend: cd src/src/ui/web && npm start"
echo "   3. Visit http://localhost:3001 to see your populated warehouse!"
