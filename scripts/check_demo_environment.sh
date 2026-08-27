#!/usr/bin/env bash
# Preflight check for MAIW demo mode.
#
# Usage:
#   ./scripts/check_demo_environment.sh
#
# Exits 0 if all checks pass. Exits 1 if any required check fails.
# Warnings (non-blocking) are shown but do not cause a non-zero exit.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${REPO_ROOT}/env"
PASS=0
FAIL=1
WARN=2

_pass() { echo "  [OK]  $1"; }
_fail() { echo "  [!!]  $1"; FAILED=1; }
_warn() { echo "  [--]  $1"; }

FAILED=0

echo ""
echo "MAIW Demo Environment Preflight"
echo "================================"
echo ""

# ── Python ──────────────────────────────────────────────────────────────────
echo "Python"

if ! command -v python3 &>/dev/null; then
    _fail "python3 not found — install Python 3.11+"
else
    PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
    PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
    if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 11 ]; }; then
        _fail "Python $PY_VER found — Python 3.11+ required"
    else
        _pass "Python $PY_VER"
    fi
fi

# ── Virtual environment ──────────────────────────────────────────────────────
echo ""
echo "Virtual environment"

if [ ! -d "${VENV}" ]; then
    _fail "Virtual environment not found at env/"
    _fail "  Run: python3 -m venv env && source env/bin/activate && pip install -r requirements.txt"
else
    _pass "env/ exists"
fi

VENV_PYTHON="${VENV}/bin/python"
if [ ! -x "${VENV_PYTHON}" ]; then
    _fail "env/bin/python not executable — venv may be corrupted"
fi

# ── Workspace packages ───────────────────────────────────────────────────────
echo ""
echo "Workspace packages"

PACKAGES=(
    "maiw_models"
    "maiw_mcp"
    "maiw_state"
    "maiw_skills"
    "maiw_decision"
    "maiw_execution"
    "maiw_agents"
    "maiw_api"
)

if [ -x "${VENV_PYTHON}" ]; then
    for pkg in "${PACKAGES[@]}"; do
        if "${VENV_PYTHON}" -c "import ${pkg}" &>/dev/null; then
            _pass "${pkg}"
        else
            _fail "${pkg} not importable — run: pip install -e packages/${pkg//_/-} (or pip install -r requirements.txt)"
            # maiw_api lives in apps/api
            if [ "${pkg}" = "maiw_api" ]; then
                _fail "  For maiw_api: pip install -e apps/api"
            fi
        fi
    done
fi

# ── NVIDIA API key ───────────────────────────────────────────────────────────
echo ""
echo "Environment variables"

ENV_FILE="${REPO_ROOT}/.env"
if [ -f "${ENV_FILE}" ]; then
    # shellcheck disable=SC1090
    set -a; source "${ENV_FILE}"; set +a
fi

if [ -z "${NVIDIA_API_KEY:-}" ]; then
    _fail "NVIDIA_API_KEY is not set — get a key at https://build.nvidia.com/"
elif [[ "${NVIDIA_API_KEY}" == nvapi-* ]]; then
    _pass "NVIDIA_API_KEY set (nvapi-...)"
else
    _warn "NVIDIA_API_KEY is set but does not start with 'nvapi-' — verify it is a valid NVIDIA API key"
fi

if [ -z "${MAIW_DEMO_MODE:-}" ] || [ "${MAIW_DEMO_MODE}" != "true" ]; then
    _warn "MAIW_DEMO_MODE is not 'true' — start_demo_mode.sh sets this automatically"
else
    _pass "MAIW_DEMO_MODE=true"
fi

# ── Node / npm ───────────────────────────────────────────────────────────────
echo ""
echo "Node.js"

if ! command -v node &>/dev/null; then
    _fail "node not found — install Node.js 18.17+ (20.x LTS recommended)"
else
    NODE_VER=$(node --version | sed 's/v//')
    NODE_MAJOR=$(echo "$NODE_VER" | cut -d. -f1)
    if [ "$NODE_MAJOR" -lt 18 ]; then
        _fail "Node.js $NODE_VER — 18.17+ required"
    else
        _pass "Node.js $NODE_VER"
    fi
fi

UI_MODULES="${REPO_ROOT}/src/ui/web/node_modules"
if [ ! -d "${UI_MODULES}" ]; then
    _warn "src/ui/web/node_modules not found — run: cd src/ui/web && npm install"
else
    _pass "src/ui/web/node_modules present"
fi

# ── Port availability ────────────────────────────────────────────────────────
echo ""
echo "Ports"

for port in 8001 3001; do
    if lsof -Pi ":${port}" -sTCP:LISTEN -t &>/dev/null; then
        _warn "Port ${port} is already in use — check for a running API or frontend"
    else
        _pass "Port ${port} free"
    fi
done

# ── Result ───────────────────────────────────────────────────────────────────
echo ""
echo "================================"
if [ "${FAILED}" -eq 0 ]; then
    echo "  All checks passed."
    echo ""
    echo "  To start the demo:"
    echo "    ./scripts/start_demo_mode.sh"
    echo "    cd src/ui/web && npm start"
    echo "    Open http://localhost:3001 → COMMAND tab"
    echo ""
    exit 0
else
    echo "  One or more required checks failed (see [!!] above)."
    echo "  Fix these before starting the demo."
    echo ""
    exit 1
fi
