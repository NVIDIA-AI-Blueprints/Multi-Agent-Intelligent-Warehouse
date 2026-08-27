#!/usr/bin/env bash
# Start the MAIW API in Synthetic Demo Mode.
#
# Usage:
#   ./scripts/start_demo_mode.sh          # runs on port 8001
#   DEMO_PORT=8003 ./scripts/start_demo_mode.sh  # runs on alternate port
#
# MCP servers are NOT required — demo mode uses SimulationProviders internally.
#
# To stop: Ctrl-C
#
# To start the frontend (in a separate terminal):
#   cd src/ui/web && npm start
#   Open http://localhost:3001 → COMMAND tab

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${REPO_ROOT}/env/bin/python"
DEMO_PORT="${DEMO_PORT:-8001}"

# ── Preflight ────────────────────────────────────────────────────────────────

if [ ! -x "${VENV}" ]; then
    echo ""
    echo "[!!] Virtual environment not found at env/"
    echo "     Run: python3 -m venv env && source env/bin/activate"
    echo "          pip install -r requirements.txt"
    echo "          pip install -e packages/maiw-models packages/maiw-mcp packages/maiw-state"
    echo "          pip install -e packages/maiw-skills packages/maiw-decision packages/maiw-execution"
    echo "          pip install -e packages/maiw-agents apps/api"
    echo ""
    exit 1
fi

if ! "${VENV}" -c "import maiw_api" &>/dev/null; then
    echo ""
    echo "[!!] maiw_api package not importable from env/"
    echo "     Run: source env/bin/activate && pip install -e apps/api"
    echo ""
    exit 1
fi

# Check port
if lsof -Pi ":${DEMO_PORT}" -sTCP:LISTEN -t &>/dev/null; then
    echo ""
    echo "[!!] Port ${DEMO_PORT} is already in use."
    echo "     Stop the existing process or set: DEMO_PORT=8003 ./scripts/start_demo_mode.sh"
    echo ""
    exit 1
fi

# ── Load .env if present ─────────────────────────────────────────────────────

ENV_FILE="${REPO_ROOT}/.env"
if [ -f "${ENV_FILE}" ]; then
    set -a; source "${ENV_FILE}"; set +a
fi

# ── Readiness summary ────────────────────────────────────────────────────────

echo ""
echo "MAIW Synthetic Demo Mode"
echo "─────────────────────────────────────────────────────"
echo "  API port    : ${DEMO_PORT}"
echo "  MCP servers : not required (SimulationProviders active)"
echo ""

if [ -z "${NVIDIA_API_KEY:-}" ]; then
    echo "  [--] NVIDIA_API_KEY not set — NIM calls will fail"
    echo "       Set it in .env or export NVIDIA_API_KEY=nvapi-..."
elif [[ "${NVIDIA_API_KEY}" == nvapi-* ]]; then
    echo "  [OK] NVIDIA_API_KEY set (nvapi-...)"
else
    echo "  [--] NVIDIA_API_KEY set but format looks unexpected"
fi

echo ""
echo "  Scenarios available:"
echo "    healthy_baseline              — all systems nominal"
echo "    equipment_failure             — forklift offline, wave at risk"
echo "    labor_constraint_wave_risk    — understaffed shift, wave priority conflict  ← recommended first"
echo "    stale_state                   — agent reasons on outdated snapshot"
echo "    state_drift                   — warehouse state changes between propose and execute"
echo ""
echo "  Next steps:"
echo "    1. In a separate terminal: cd src/ui/web && npm start"
echo "    2. Open http://localhost:3001 → COMMAND tab"
echo "    3. Select 'labor_constraint_wave_risk' and click START"
echo "─────────────────────────────────────────────────────"
echo ""

# ── Start API ────────────────────────────────────────────────────────────────

cd "${REPO_ROOT}"
MAIW_DEMO_MODE=true exec "${VENV}" -m uvicorn maiw_api.app:app \
    --host 0.0.0.0 \
    --port "${DEMO_PORT}"
