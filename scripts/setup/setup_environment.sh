#!/bin/bash
# Setup script for Warehouse Operational Assistant
# Creates virtual environment and installs dependencies

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$PROJECT_ROOT"

echo "🚀 Setting up Warehouse Operational Assistant environment..."
echo ""

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.9+ first."
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
echo "✅ Found Python $PYTHON_VERSION"

# Create virtual environment if it doesn't exist
if [ ! -d "env" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv env
    echo "✅ Virtual environment created"
else
    echo "✅ Virtual environment already exists"
fi

# Activate virtual environment
echo "🔌 Activating virtual environment..."
source env/bin/activate

# Upgrade pip
echo "⬆️  Upgrading pip..."
pip install --upgrade pip setuptools wheel

# Install dependencies
echo "📥 Installing dependencies..."
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
    echo "✅ Dependencies installed from requirements.txt"
else
    echo "⚠️  requirements.txt not found"
fi

# Install development dependencies if available
if [ -f "requirements-dev.txt" ]; then
    echo "📥 Installing development dependencies..."
    pip install -r requirements-dev.txt
    echo "✅ Development dependencies installed"
fi

echo ""
echo "✅ Environment setup complete!"
echo ""
echo "📝 Next steps:"
echo "   1. Activate the virtual environment: source env/bin/activate"
echo "   2. Set up environment variables (copy .env.example to .env and configure)"
echo "   3. Run database migrations: ./scripts/setup/run_migrations.sh"
echo "   4. Create default users: python scripts/setup/create_default_users.py"
echo "   5. Start the server: ./scripts/start_server.sh"
echo ""

