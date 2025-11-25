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

# Check Node.js version
if ! command -v node &> /dev/null; then
    echo "❌ Node.js is not installed. Please install Node.js 20.0.0+ (or minimum 18.17.0+) first."
    echo "   Recommended: Node.js 20.x LTS"
    exit 1
fi

NODE_VERSION=$(node --version | cut -d'v' -f2)
NODE_MAJOR=$(echo "$NODE_VERSION" | cut -d'.' -f1)
NODE_MINOR=$(echo "$NODE_VERSION" | cut -d'.' -f2)
NODE_PATCH=$(echo "$NODE_VERSION" | cut -d'.' -f3)

echo "✅ Found Node.js $NODE_VERSION"

# Check if Node.js version meets requirements
# Minimum: 18.17.0, Recommended: 20.0.0+
if [ "$NODE_MAJOR" -lt 18 ]; then
    echo "❌ Node.js version $NODE_VERSION is too old. Please install Node.js 18.17.0+ (recommended: 20.x LTS)"
    exit 1
elif [ "$NODE_MAJOR" -eq 18 ]; then
    if [ "$NODE_MINOR" -lt 17 ]; then
        echo "❌ Node.js version $NODE_VERSION is too old. Please install Node.js 18.17.0+ (recommended: 20.x LTS)"
        echo "   Note: Node.js 18.0.0 - 18.16.x will fail with 'Cannot find module node:path' error"
        exit 1
    elif [ "$NODE_MINOR" -eq 17 ] && [ "$NODE_PATCH" -lt 0 ]; then
        echo "❌ Node.js version $NODE_VERSION is too old. Please install Node.js 18.17.0+ (recommended: 20.x LTS)"
        exit 1
    else
        echo "⚠️  Node.js 18.17.0+ detected. Node.js 20.x LTS is recommended for best compatibility."
    fi
elif [ "$NODE_MAJOR" -ge 20 ]; then
    echo "✅ Node.js version meets requirements (20.x LTS recommended)"
fi

# Check npm version
if ! command -v npm &> /dev/null; then
    echo "⚠️  npm is not installed. Please install npm 9.0.0+"
else
    NPM_VERSION=$(npm --version)
    echo "✅ Found npm $NPM_VERSION"
fi

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

