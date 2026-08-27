#!/usr/bin/env bash
# Install all MAIW workspace packages in editable mode.
#
# Usage:
#   source env/bin/activate   # activate the virtual environment first
#   ./scripts/install_packages.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

if [ ! -f "env/bin/activate" ]; then
    echo "[!!] Virtual environment not found. Create it first:"
    echo "     python3 -m venv env && source env/bin/activate"
    exit 1
fi

echo "Installing Python dependencies..."
pip install -r requirements.txt

echo ""
echo "Installing MAIW workspace packages (editable)..."
pip install -e packages/maiw-models \
            -e packages/maiw-mcp \
            -e packages/maiw-state \
            -e packages/maiw-skills \
            -e packages/maiw-decision \
            -e packages/maiw-execution \
            -e packages/maiw-agents \
            -e apps/api

echo ""
echo "Done. Run ./scripts/check_demo_environment.sh to verify."
