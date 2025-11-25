#!/bin/bash
# Node.js version check script for Warehouse Operational Assistant
# Checks if Node.js version meets minimum requirements

set -e

MIN_NODE_VERSION="18.17.0"
RECOMMENDED_NODE_VERSION="20.0.0"
MIN_NPM_VERSION="9.0.0"

echo "🔍 Checking Node.js and npm versions..."
echo ""

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo "❌ Node.js is not installed."
    echo "   Please install Node.js $RECOMMENDED_NODE_VERSION+ (minimum: $MIN_NODE_VERSION)"
    echo "   Download from: https://nodejs.org/"
    echo ""
    echo "   Or use nvm (Node Version Manager):"
    echo "   curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash"
    echo "   nvm install 20"
    echo "   nvm use 20"
    exit 1
fi

# Get Node.js version
NODE_VERSION=$(node --version | cut -d'v' -f2)
NODE_MAJOR=$(echo "$NODE_VERSION" | cut -d'.' -f1)
NODE_MINOR=$(echo "$NODE_VERSION" | cut -d'.' -f2)
NODE_PATCH=$(echo "$NODE_VERSION" | cut -d'.' -f3)

echo "📦 Node.js version: $NODE_VERSION"

# Parse minimum version for comparison
MIN_MAJOR=$(echo "$MIN_NODE_VERSION" | cut -d'.' -f1)
MIN_MINOR=$(echo "$MIN_NODE_VERSION" | cut -d'.' -f2)
MIN_PATCH=$(echo "$MIN_NODE_VERSION" | cut -d'.' -f3)

# Check if version meets minimum requirements
VERSION_OK=false
if [ "$NODE_MAJOR" -gt "$MIN_MAJOR" ]; then
    VERSION_OK=true
elif [ "$NODE_MAJOR" -eq "$MIN_MAJOR" ]; then
    if [ "$NODE_MINOR" -gt "$MIN_MINOR" ]; then
        VERSION_OK=true
    elif [ "$NODE_MINOR" -eq "$MIN_MINOR" ]; then
        if [ "$NODE_PATCH" -ge "$MIN_PATCH" ]; then
            VERSION_OK=true
        fi
    fi
fi

if [ "$VERSION_OK" = false ]; then
    echo "❌ Node.js version $NODE_VERSION is too old."
    echo "   Minimum required: $MIN_NODE_VERSION"
    echo "   Recommended: $RECOMMENDED_NODE_VERSION+ (LTS)"
    echo ""
    echo "   Note: Node.js 18.0.0 - 18.16.x will fail with 'Cannot find module node:path' error"
    echo ""
    echo "   Upgrade options:"
    echo "   1. Download from: https://nodejs.org/"
    echo "   2. Use nvm: nvm install 20 && nvm use 20"
    exit 1
fi

# Check if version is recommended
if [ "$NODE_MAJOR" -lt 20 ]; then
    echo "⚠️  Node.js 18.17.0+ detected. Node.js 20.x LTS is recommended for best compatibility."
else
    echo "✅ Node.js version meets requirements (20.x LTS)"
fi

# Check npm version
if ! command -v npm &> /dev/null; then
    echo "⚠️  npm is not installed. Please install npm $MIN_NPM_VERSION+"
    exit 1
fi

NPM_VERSION=$(npm --version)
echo "📦 npm version: $NPM_VERSION"

# Check npm version meets minimum
NPM_MAJOR=$(echo "$NPM_VERSION" | cut -d'.' -f1)
MIN_NPM_MAJOR=$(echo "$MIN_NPM_VERSION" | cut -d'.' -f1)

if [ "$NPM_MAJOR" -lt "$MIN_NPM_MAJOR" ]; then
    echo "⚠️  npm version $NPM_VERSION is below recommended minimum ($MIN_NPM_VERSION)"
    echo "   Consider upgrading: npm install -g npm@latest"
else
    echo "✅ npm version meets requirements"
fi

echo ""
echo "✅ Node.js and npm version check passed!"
echo ""

# Check for .nvmrc file and suggest using it
if [ -f "src/ui/web/.nvmrc" ]; then
    NVMRC_VERSION=$(cat src/ui/web/.nvmrc)
    echo "💡 Tip: This project uses Node.js $NVMRC_VERSION (see src/ui/web/.nvmrc)"
    echo "   If using nvm, run: cd src/ui/web && nvm use"
fi

