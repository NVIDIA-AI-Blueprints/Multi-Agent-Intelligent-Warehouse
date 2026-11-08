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

# Check for poppler-utils (required for PDF document processing)
echo ""
echo "🔍 Checking for system dependencies..."
if ! command -v pdfinfo &> /dev/null; then
    echo "⚠️  poppler-utils is not installed (required for PDF document processing)"
    
    # Detect OS and provide installation instructions
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        # Linux - check if we can use apt-get
        if command -v apt-get &> /dev/null; then
            echo "💡 To install poppler-utils, run: sudo apt-get install poppler-utils"
            read -p "❓ Would you like to install poppler-utils now? (requires sudo) [y/N]: " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                echo "📦 Installing poppler-utils..."
                sudo apt-get update && sudo apt-get install -y poppler-utils
                echo "✅ poppler-utils installed"
            else
                echo "⚠️  Skipping poppler-utils installation. You can install it later with: sudo apt-get install poppler-utils"
            fi
        elif command -v yum &> /dev/null; then
            echo "💡 To install poppler-utils, run: sudo yum install poppler-utils"
        elif command -v dnf &> /dev/null; then
            echo "💡 To install poppler-utils, run: sudo dnf install poppler-utils"
        else
            echo "💡 Please install poppler-utils using your system's package manager"
        fi
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        if command -v brew &> /dev/null; then
            echo "💡 To install poppler, run: brew install poppler"
            read -p "❓ Would you like to install poppler now? [y/N]: " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                echo "📦 Installing poppler..."
                brew install poppler
                echo "✅ poppler installed"
            else
                echo "⚠️  Skipping poppler installation. You can install it later with: brew install poppler"
            fi
        else
            echo "💡 Please install Homebrew first, then run: brew install poppler"
        fi
    else
        echo "💡 Please install poppler-utils using your system's package manager"
        echo "   Ubuntu/Debian: sudo apt-get install poppler-utils"
        echo "   macOS: brew install poppler"
        echo "   Windows: Download from http://blog.alivate.com.au/poppler-windows/"
    fi
else
    echo "✅ poppler-utils is installed ($(pdfinfo --version 2>/dev/null | head -n1 || echo 'version unknown'))"
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
echo "   4. Start the server: ./scripts/start_server.sh"
echo ""

