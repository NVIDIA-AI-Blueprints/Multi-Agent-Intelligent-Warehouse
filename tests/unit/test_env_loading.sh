#!/bin/bash
# Test script to verify .env variable loading in dev_up.sh

set -e

echo "🧪 Testing .env variable loading..."
echo "=================================="

# Test 1: Check if .env file exists
echo ""
echo "Test 1: Checking .env file existence"
if [ -f .env ]; then
    echo "✅ .env file exists"
else
    echo "❌ .env file not found"
    exit 1
fi

# Test 2: Simulate the variable loading logic from dev_up.sh
echo ""
echo "Test 2: Simulating variable loading (set -a)"
echo "---------------------------------------------"

# Clear any existing variables
unset POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB PGPORT 2>/dev/null || true

# Load environment variables from .env file (same logic as dev_up.sh)
if [ -f .env ]; then
    echo "Loading environment variables from .env file..."
    set -a
    source .env
    set +a
    echo "✅ Environment variables loaded"
else
    echo "⚠️  Warning: .env file not found. Using default values."
fi

# Test 3: Verify variables are loaded and exported
echo ""
echo "Test 3: Verifying variables are loaded and exported"
echo "----------------------------------------------------"

VARS_TO_CHECK=("POSTGRES_USER" "POSTGRES_PASSWORD" "POSTGRES_DB" "PGPORT")
ALL_LOADED=true

for var in "${VARS_TO_CHECK[@]}"; do
    if [ -z "${!var:-}" ]; then
        echo "❌ $var is not set"
        ALL_LOADED=false
    else
        # Mask password for display
        if [ "$var" = "POSTGRES_PASSWORD" ]; then
            echo "✅ $var is set (value: ****)"
        else
            echo "✅ $var is set (value: ${!var})"
        fi
    fi
done

# Test 4: Check if variables are exported (available to subprocesses)
echo ""
echo "Test 4: Verifying variables are exported (available to subprocesses)"
echo "---------------------------------------------------------------------"

for var in "${VARS_TO_CHECK[@]}"; do
    if env | grep -q "^${var}="; then
        if [ "$var" = "POSTGRES_PASSWORD" ]; then
            echo "✅ $var is exported (value: ****)"
        else
            echo "✅ $var is exported (value: ${!var})"
        fi
    else
        echo "❌ $var is not exported"
        ALL_LOADED=false
    fi
done

# Test 5: Simulate what Docker Compose would see
echo ""
echo "Test 5: Simulating Docker Compose variable substitution"
echo "--------------------------------------------------------"

# Create a test docker-compose snippet
cat > /tmp/test-compose.yaml << 'EOF'
version: "3.9"
services:
  test:
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
EOF

# Use envsubst to simulate Docker Compose variable substitution
if command -v envsubst >/dev/null 2>&1; then
    echo "Testing variable substitution with envsubst:"
    envsubst < /tmp/test-compose.yaml | grep -A 3 "environment:" || true
    echo "✅ Variable substitution test completed"
else
    echo "⚠️  envsubst not available, skipping substitution test"
fi

# Cleanup
rm -f /tmp/test-compose.yaml

# Final result
echo ""
echo "=================================="
if [ "$ALL_LOADED" = true ]; then
    echo "🎉 All tests passed! .env variables are loading correctly."
    exit 0
else
    echo "❌ Some tests failed. Please check the output above."
    exit 1
fi

