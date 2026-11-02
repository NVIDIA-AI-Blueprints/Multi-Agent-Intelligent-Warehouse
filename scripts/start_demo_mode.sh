#!/usr/bin/env bash
# Start the MAIW API in Synthetic Demo Mode.
#
# Usage:
#   ./scripts/start_demo_mode.sh                     # 127.0.0.1:8001
#   DEMO_PORT=8003 ./scripts/start_demo_mode.sh      # alternate port
#   DEMO_HOST=0.0.0.0 ./scripts/start_demo_mode.sh   # all interfaces (see SECURITY.md)
#   DEMO_PERSISTENCE_ROOT=$HOME/.maiw-demo ./scripts/start_demo_mode.sh
#                                                    # durable procedure state
#   DEMO_PYTHON=/path/to/python ./scripts/start_demo_mode.sh
#                                                    # interpreter (default: .venv, then env)
#
# MCP servers are NOT required — demo mode uses SimulationProviders internally.
#
# .env is loaded with scripts/lib/load_env.sh (parsed, not executed; variables
# already set in the shell win).  The demo profile is then forced, so a .env
# copied from .env.example (MAIW_DEPLOYMENT_PROFILE=reference,
# MAIW_SANDBOX_MODE=required, MAIW_PERSISTENCE_ROOT=/var/lib/maiw,
# MAIW_API_HOST=0.0.0.0) still starts a READY demo API:
#   MAIW_DEMO_MODE=true  MAIW_DEPLOYMENT_PROFILE=demo  MAIW_SANDBOX_MODE=disabled
#   MAIW_READINESS_REQUIRE_DATABASE=false
#   MAIW_PERSISTENCE_MODE=memory, unless DEMO_PERSISTENCE_ROOT is set
#
# To stop: Ctrl-C
#
# To start the frontend (in a separate terminal):
#   cd src/ui/web && npm start
#   Open http://localhost:3001 → COMMAND tab

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEMO_HOST="${DEMO_HOST:-127.0.0.1}"
DEMO_PORT="${DEMO_PORT:-8001}"

if [[ -n "${DEMO_PYTHON:-}" ]]; then
    VENV="${DEMO_PYTHON}"
elif [[ -x "${REPO_ROOT}/.venv/bin/python" ]]; then
    VENV="${REPO_ROOT}/.venv/bin/python"
else
    VENV="${REPO_ROOT}/env/bin/python"
fi

# ── DataPack preflight ───────────────────────────────────────────────────────

PACK_DIR="${MAIW_WORLD_OUTPUT:-data/worlds/dc47-demo-v1}"
if [[ ! -f "${REPO_ROOT}/${PACK_DIR}/manifest.json" ]]; then
  echo ""
  echo "ERROR: Warehouse DataPack not found: ${PACK_DIR}"
  echo ""
  echo "Run setup first:"
  echo "  ./scripts/setup_demo_world.sh"
  echo ""
  exit 1
fi

# ── Preflight ────────────────────────────────────────────────────────────────

if [ ! -x "${VENV}" ]; then
    echo ""
    echo "[!!] Python interpreter not found (looked for .venv/ and env/; or set DEMO_PYTHON)"
    echo "     Run: python3 -m venv .venv && source .venv/bin/activate"
    echo "          pip install -r requirements.txt"
    echo "          pip install -e packages/maiw-contracts -e packages/maiw-mcp -e packages/maiw-state \\"
    echo "              -e packages/maiw-models -e packages/maiw-skills -e packages/maiw-decision \\"
    echo "              -e packages/maiw-execution -e packages/maiw-agents -e packages/maiw-world \\"
    echo "              -e apps/api"
    echo ""
    exit 1
fi

if ! "${VENV}" -c "import maiw_api" &>/dev/null; then
    echo ""
    echo "[!!] maiw_api package not importable from ${VENV}"
    echo "     Run: pip install -e apps/api (in that environment)"
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

# shellcheck source=lib/load_env.sh
source "${SCRIPT_DIR}/lib/load_env.sh"
maiw_load_env "${REPO_ROOT}"

# ── Force the demo profile ───────────────────────────────────────────────────

# An explicit MAIW_DEPLOYMENT_PROFILE beats MAIW_DEMO_MODE, and .env.example
# selects the reference profile with a required sandbox, so set all of them.
export MAIW_DEMO_MODE=true
export MAIW_DEPLOYMENT_PROFILE=demo
export MAIW_SANDBOX_MODE=disabled
export MAIW_READINESS_REQUIRE_DATABASE=false

# Development server: in-memory procedure state (lost on restart) unless the
# caller opts into a durable root.  MAIW_PERSISTENCE_ROOT from .env is not an
# opt-in: .env.example points it at /var/lib/maiw, the reference deployment's
# root.  The reference deployment (scripts/start_reference_deployment.sh) is
# file-backed.
unset MAIW_PROCEDURE_STATE_DIR MAIW_GOVERNANCE_STATE_DIR MAIW_EXECUTION_STATE_DIR
if [[ -n "${DEMO_PERSISTENCE_ROOT:-}" ]]; then
    export MAIW_PERSISTENCE_MODE=file
    export MAIW_PERSISTENCE_ROOT="${DEMO_PERSISTENCE_ROOT}"
    PERSISTENCE_SUMMARY="file (${MAIW_PERSISTENCE_ROOT})"
else
    export MAIW_PERSISTENCE_MODE=memory
    unset MAIW_PERSISTENCE_ROOT
    PERSISTENCE_SUMMARY="memory (lost on restart; set DEMO_PERSISTENCE_ROOT to keep it)"
fi

# ── Readiness summary ────────────────────────────────────────────────────────

echo ""
echo "MAIW Synthetic Demo Mode"
echo "─────────────────────────────────────────────────────"
echo "  API         : http://${DEMO_HOST}:${DEMO_PORT}"
echo "  Profile     : demo (sandbox disabled, no database)"
echo "  Persistence : ${PERSISTENCE_SUMMARY}"
echo "  MCP servers : not required (SimulationProviders active)"
echo ""

if [[ "${DEMO_HOST}" != "127.0.0.1" && "${DEMO_HOST}" != "localhost" && "${DEMO_HOST}" != "::1" ]]; then
    echo "  [!!] DEMO_HOST=${DEMO_HOST} exposes the API beyond this machine."
    echo "       The supported boundary is 127.0.0.1 (see SECURITY.md)."
fi

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
exec "${VENV}" -m uvicorn maiw_api.app:app \
    --host "${DEMO_HOST}" \
    --port "${DEMO_PORT}"
