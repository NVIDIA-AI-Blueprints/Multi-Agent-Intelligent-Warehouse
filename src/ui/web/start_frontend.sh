#!/bin/bash

# Warehouse Operational Assistant - Frontend Startup Script

echo "🚀 Starting Warehouse Operational Assistant Frontend..."
echo "📡 Frontend will be available at: http://localhost:3001"
echo "🔗 Backend API should be running at: http://localhost:8002"
echo ""

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo "❌ Node.js is not installed. Please install Node.js 16+ and try again."
    exit 1
fi

# Check if npm is installed
if ! command -v npm &> /dev/null; then
    echo "❌ npm is not installed. Please install npm and try again."
    exit 1
fi

# Check if we're in the right directory
if [ ! -f "package.json" ]; then
    echo "❌ package.json not found. Please run this script from the src/src/ui/web directory."
    exit 1
fi

# Install dependencies if node_modules doesn't exist
if [ ! -d "node_modules" ]; then
    echo "📦 Installing dependencies..."
    npm install
    if [ $? -ne 0 ]; then
        echo "❌ Failed to install dependencies. Please check your internet connection and try again."
        exit 1
    fi
fi

# Check if backend is running
echo "🔍 Checking backend API status..."
if curl -s http://localhost:8002/api/v1/health > /dev/null; then
    echo "✅ Backend API is running"
else
    echo "⚠️  Backend API is not running. Please start the backend first:"
    echo "   cd /path/to/warehouse-operational-assistant"
    echo "   ./RUN_LOCAL.sh"
    echo ""
    echo "   The frontend will still start, but API calls will fail."
fi

echo ""
echo "🎨 Starting React development server..."
echo "Press Ctrl+C to stop the server"
echo ""

# Start the React development server
npm start
