#!/usr/bin/env bash
# Start the MAIW API in Synthetic Demo Mode.
#
# Usage:
#   ./scripts/start_demo_mode.sh          # runs on port 8001 (stops the normal API)
#   DEMO_PORT=8003 ./scripts/start_demo_mode.sh  # runs on alternate port
#
# The UI connects to port 8001 by default.  If you start on an alternate port,
# set REACT_APP_API_URL=http://localhost:8003 when starting the frontend.
#
# To stop: Ctrl-C, or `kill $(cat /tmp/maiw-demo.pid)`

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${REPO_ROOT}/env/bin/python"
DEMO_PORT="${DEMO_PORT:-8001}"

echo "MAIW Synthetic Demo Mode"
echo "  API port : ${DEMO_PORT}"
echo "  Scenarios: healthy_baseline, equipment_failure, labor_constraint_wave_risk,"
echo "             stale_state, state_drift"
echo ""
echo "  Open http://localhost:3001 → COMMAND tab to see the Demo Control Bar."
echo "  Select a scenario and click START."
echo ""

cd "${REPO_ROOT}"
MAIW_DEMO_MODE=true exec "${VENV}" -m uvicorn maiw_api.app:app \
    --host 0.0.0.0 \
    --port "${DEMO_PORT}"
