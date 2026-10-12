#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# preflight_reference_deployment.sh — pre-start validation for MAIW v2 reference deployment
#
# Validates that every hard prerequisite for the qualified single-node reference
# deployment is met BEFORE any service starts. Returns non-zero on the first
# category of failure encountered.
#
# Usage:
#   bash scripts/preflight_reference_deployment.sh [--quiet]
#
# v2.0.1 round 2: the environment is loaded FIRST by scripts/lib/load_env.sh —
# the same loader start/stop/restart/status/smoke use — so preflight validates
# exactly the configuration start launches with.  The model check runs the
# SAME ModelRegistry + DeploymentResolver the gateway runs before dispatch
# (scripts/lib/check_model_config.py) on the NEMOTRON_<ROLE>_MODEL bindings the
# runtime actually dispatches.
#
# Exit codes:
#   0  all checks pass
#   1  one or more checks failed (details printed to stderr)
#
# Steps 8, 41, 42, 45, 62, 63, 64, 65 of Phase 20C-C.
# ---------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
# shellcheck source=lib/load_env.sh
source "$SCRIPT_DIR/lib/load_env.sh"
# shellcheck source=lib/deployment_identity.sh
source "$SCRIPT_DIR/lib/deployment_identity.sh"
maiw_load_env "$PROJECT_ROOT"

# ── Globals ──────────────────────────────────────────────────────────────────
QUIET=${1:-""}
FAIL=0
CHECKS_PASSED=0
CHECKS_FAILED=0

# Qualified component versions (Step 3 / Step 45)
REQUIRED_NEMOCLAW_VERSION="0.0.124"
REQUIRED_OPENSHELL_VERSION="0.0.116"
REQUIRED_PYTHON_MIN="3.12"

# Persistence root (Step 29) and API port (Step 64) — explicit, no defaults:
# a default port is how lifecycle scripts end up talking to someone else's
# server on a shared host.
MAIW_PERSISTENCE_ROOT="${MAIW_PERSISTENCE_ROOT:-}"
REQUIRED_PORTS=("${MAIW_API_PORT:-}")
MAIW_PYTHON="${MAIW_PYTHON:-}"

# Disk thresholds in MB (Step 63)
MIN_DISK_MB_STATE=1024
MIN_DISK_MB_LOG=512

# ── Helpers ───────────────────────────────────────────────────────────────────
_pass() {
    CHECKS_PASSED=$((CHECKS_PASSED + 1))
    [[ "$QUIET" != "--quiet" ]] && echo "  PASS  $1"
}

_fail() {
    CHECKS_FAILED=$((CHECKS_FAILED + 1))
    FAIL=1
    echo "  FAIL  $1" >&2
    echo "        Expected: $2" >&2
    echo "        Actual:   $3" >&2
    if [[ -n "${4:-}" ]]; then
        echo "        Next:     $4" >&2
    fi
}

_header() {
    [[ "$QUIET" != "--quiet" ]] && echo ""
    [[ "$QUIET" != "--quiet" ]] && echo "=== $1 ==="
}

_version_ge() {
    # Returns 0 (true) if $1 >= $2 (dot-separated version strings)
    local IFS=.
    local a=($1) b=($2)
    for ((i=0; i<${#b[@]}; i++)); do
        local av=${a[i]:-0} bv=${b[i]:-0}
        if ((av > bv)); then return 0; fi
        if ((av < bv)); then return 1; fi
    done
    return 0
}

# ── Check 0: Required configuration present ──────────────────────────────────
_header "Configuration (${MAIW_ENV_LOADED_FROM:-environment})"
for var in MAIW_PERSISTENCE_ROOT MAIW_API_PORT MAIW_PYTHON MAIW_DEPLOYMENT_PROFILE; do
    if [[ -n "${!var:-}" ]]; then
        _pass "$var set"
    else
        _fail "$var" "set (in .env)" "not set" "See .env.example § MAIW v2 REFERENCE DEPLOYMENT"
    fi
done
if [[ -z "$MAIW_PERSISTENCE_ROOT" || -z "${MAIW_API_PORT:-}" || -z "$MAIW_PYTHON" ]]; then
    echo "" >&2
    echo "PREFLIGHT FAILED — required configuration missing (no defaults are assumed)." >&2
    exit 1
fi
case "${MAIW_DEPLOYMENT_PROFILE:-}" in
    reference|reference_governed) _pass "Deployment profile: $MAIW_DEPLOYMENT_PROFILE" ;;
    *) _fail "MAIW_DEPLOYMENT_PROFILE" "reference | reference_governed" "${MAIW_DEPLOYMENT_PROFILE:-unset}" \
        "demo is not a reference deployment profile" ;;
esac

# ── Check 1: Supported OS ─────────────────────────────────────────────────────
_header "OS / Platform"
OS_ID=$(grep -oP '(?<=^ID=).+' /etc/os-release 2>/dev/null | tr -d '"' || echo "unknown")
OS_VER=$(grep -oP '(?<=^VERSION_ID=).+' /etc/os-release 2>/dev/null | tr -d '"' || echo "unknown")
if [[ "$OS_ID" == "ubuntu" ]] || [[ "$OS_ID" == "debian" ]] || [[ "$OS_ID" == "rhel" ]] || [[ "$OS_ID" == "centos" ]]; then
    _pass "Supported OS: $OS_ID $OS_VER"
else
    _fail "Supported OS" "ubuntu|debian|rhel|centos" "$OS_ID $OS_VER" \
        "Run on a supported Linux distribution"
fi

# ── Check 2: Python version ────────────────────────────────────────────────────
_header "Python"
PY_VERSION=$("$MAIW_PYTHON" --version 2>/dev/null | awk '{print $2}' || echo "0.0.0")
if _version_ge "${PY_VERSION:-0.0.0}" "$REQUIRED_PYTHON_MIN"; then
    _pass "Python $PY_VERSION >= $REQUIRED_PYTHON_MIN ($MAIW_PYTHON)"
else
    _fail "Python version" ">= $REQUIRED_PYTHON_MIN" "${PY_VERSION:-none} ($MAIW_PYTHON)" \
        "Install Python $REQUIRED_PYTHON_MIN or newer and set MAIW_PYTHON"
fi
API_INIT=$("$MAIW_PYTHON" -c 'import maiw_api, os; print(os.path.realpath(maiw_api.__file__))' 2>/dev/null || echo "")
if [[ "$API_INIT" == "$PROJECT_ROOT/"* ]]; then
    _pass "MAIW_PYTHON imports maiw_api from this checkout"
else
    _fail "maiw_api import" "maiw_api under $PROJECT_ROOT" "${API_INIT:-not importable}" \
        "Install the packages into MAIW_PYTHON's venv (runbook § Install)"
fi

# ── Check 3: GPU visibility ───────────────────────────────────────────────────
_header "GPU / CUDA"
# v2.0.1 round 2: nvidia-smi's exit status decides — on an NVML error it
# prints the error text to stdout, which was previously counted as a GPU.
if command -v nvidia-smi &>/dev/null; then
    if GPU_OUT=$(nvidia-smi --query-gpu=name,driver_version,compute_cap --format=csv,noheader 2>&1); then
        GPU_COUNT=$(printf '%s\n' "$GPU_OUT" | grep -c . || true)
        DRIVER_VERSION=$(printf '%s\n' "$GPU_OUT" | head -1 | awk -F', ' '{print $2}')
        GPU_ARCH=$(printf '%s\n' "$GPU_OUT" | head -1 | awk -F', ' '{print $3}')
        _pass "NVIDIA GPU(s) visible: $GPU_COUNT"
        _pass "NVIDIA driver: $DRIVER_VERSION"
        _pass "GPU compute capability: $GPU_ARCH (reference: sm_90a for H100 NVL)"
    else
        _fail "GPU visibility / NVIDIA driver" "nvidia-smi succeeds with >= 1 GPU" \
            "$(printf '%s' "$GPU_OUT" | head -1)" \
            "Fix the NVIDIA driver installation (host state; not changed by MAIW)"
    fi
else
    _fail "nvidia-smi" "nvidia-smi command available" "not found" \
        "Install NVIDIA driver and CUDA toolkit"
fi

# ── Check 4: Container runtime ────────────────────────────────────────────────
_header "Container Runtime"
if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
    DOCKER_VERSION=$(docker version --format '{{.Server.Version}}' 2>/dev/null || echo "unknown")
    _pass "Docker available: $DOCKER_VERSION"
elif command -v podman &>/dev/null; then
    PODMAN_VERSION=$(podman version --format '{{.Version}}' 2>/dev/null || echo "unknown")
    _pass "Podman available: $PODMAN_VERSION"
else
    _fail "Container runtime" "docker or podman" "not found" \
        "Install Docker (https://docs.docker.com/engine/install/) or Podman"
fi

# ── Check 5: NemoClaw version ─────────────────────────────────────────────────
_header "NemoClaw / OpenShell Versions"
if command -v nemoclaw &>/dev/null; then
    NEMOCLAW_VERSION=$(nemoclaw --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || echo "unknown")
    if [[ "$NEMOCLAW_VERSION" == "$REQUIRED_NEMOCLAW_VERSION" ]]; then
        _pass "NemoClaw CLI version: $NEMOCLAW_VERSION"
    else
        _fail "NemoClaw version" "$REQUIRED_NEMOCLAW_VERSION" "${NEMOCLAW_VERSION:-unknown} (nemoclaw --version)" \
            "Install NemoClaw $REQUIRED_NEMOCLAW_VERSION"
    fi
elif python3 -c "import nemoclaw; print(nemoclaw.__version__)" &>/dev/null 2>&1; then
    NEMOCLAW_VERSION=$(python3 -c "import nemoclaw; print(nemoclaw.__version__)" 2>/dev/null || echo "unknown")
    if [[ "$NEMOCLAW_VERSION" == "$REQUIRED_NEMOCLAW_VERSION" ]]; then
        _pass "NemoClaw version: $NEMOCLAW_VERSION"
    else
        _fail "NemoClaw version" "$REQUIRED_NEMOCLAW_VERSION" "$NEMOCLAW_VERSION" \
            "Install NemoClaw==$REQUIRED_NEMOCLAW_VERSION: pip install nemoclaw==$REQUIRED_NEMOCLAW_VERSION"
    fi
elif [[ -n "${MAIW_NEMOCLAW_VERSION:-}" ]]; then
    if [[ "$MAIW_NEMOCLAW_VERSION" == "$REQUIRED_NEMOCLAW_VERSION" ]]; then
        _pass "NemoClaw version (env): $MAIW_NEMOCLAW_VERSION"
    else
        _fail "NemoClaw version" "$REQUIRED_NEMOCLAW_VERSION" "$MAIW_NEMOCLAW_VERSION (MAIW_NEMOCLAW_VERSION env)" \
            "Set MAIW_NEMOCLAW_VERSION=$REQUIRED_NEMOCLAW_VERSION or install nemoclaw==$REQUIRED_NEMOCLAW_VERSION"
    fi
else
    _fail "NemoClaw" "importable or MAIW_NEMOCLAW_VERSION set" "not found" \
        "Install NemoClaw $REQUIRED_NEMOCLAW_VERSION: pip install nemoclaw==$REQUIRED_NEMOCLAW_VERSION"
fi

# ── Check 6: OpenShell version ────────────────────────────────────────────────
if command -v openshell &>/dev/null; then
    OPENSHELL_VERSION=$(openshell --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || echo "unknown")
    if [[ "$OPENSHELL_VERSION" == "$REQUIRED_OPENSHELL_VERSION" ]]; then
        _pass "OpenShell CLI version: $OPENSHELL_VERSION"
    else
        _fail "OpenShell version" "$REQUIRED_OPENSHELL_VERSION" "${OPENSHELL_VERSION:-unknown} (openshell --version)" \
            "Install OpenShell $REQUIRED_OPENSHELL_VERSION"
    fi
elif python3 -c "import openshell; print(openshell.__version__)" &>/dev/null 2>&1; then
    OPENSHELL_VERSION=$(python3 -c "import openshell; print(openshell.__version__)" 2>/dev/null || echo "unknown")
    if [[ "$OPENSHELL_VERSION" == "$REQUIRED_OPENSHELL_VERSION" ]]; then
        _pass "OpenShell version: $OPENSHELL_VERSION"
    else
        _fail "OpenShell version" "$REQUIRED_OPENSHELL_VERSION" "$OPENSHELL_VERSION" \
            "Install OpenShell==$REQUIRED_OPENSHELL_VERSION: pip install openshell==$REQUIRED_OPENSHELL_VERSION"
    fi
elif [[ -n "${MAIW_OPENSHELL_VERSION:-}" ]]; then
    if [[ "$MAIW_OPENSHELL_VERSION" == "$REQUIRED_OPENSHELL_VERSION" ]]; then
        _pass "OpenShell version (env): $MAIW_OPENSHELL_VERSION"
    else
        _fail "OpenShell version" "$REQUIRED_OPENSHELL_VERSION" "$MAIW_OPENSHELL_VERSION (MAIW_OPENSHELL_VERSION env)" \
            "Set MAIW_OPENSHELL_VERSION=$REQUIRED_OPENSHELL_VERSION or install openshell==$REQUIRED_OPENSHELL_VERSION"
    fi
else
    _fail "OpenShell" "importable or MAIW_OPENSHELL_VERSION set" "not found" \
        "Install OpenShell $REQUIRED_OPENSHELL_VERSION: pip install openshell==$REQUIRED_OPENSHELL_VERSION"
fi

# ── Check 7: Physical model bindings (v2.0.1 round 2) ────────────────────────
# Runs the SAME ModelRegistry + DeploymentResolver the gateway uses before
# dispatch, on the NEMOTRON_<ROLE>_MODEL / _ENABLED values the runtime reads.
# LLM_MODEL / MAIW_NIM_MODEL are not dispatched by ModelGateway; if set they
# must still name an approved model.
_header "Approved Physical Model Bindings"
MODEL_REPORT=$("$MAIW_PYTHON" "$SCRIPT_DIR/lib/check_model_config.py" --provider-probe 2>&1) && MODEL_RC=0 || MODEL_RC=$?
while IFS= read -r line; do
    case "$line" in
        PASS*) _pass "${line#PASS  }" ;;
        FAIL*) _fail "${line#FAIL  }" "approved physical deployment (maiw_models.deployment.APPROVED_DEPLOYMENTS)" \
                   "not approved" "Set NEMOTRON_<ROLE>_MODEL to the approved ID for that role, or disable the role" ;;
        *) if [[ "$QUIET" != "--quiet" && -n "$line" ]]; then echo "  $line"; fi ;;
    esac
done <<< "$MODEL_REPORT"
if [[ "$MODEL_RC" -ne 0 ]] && ! grep -q '^FAIL' <<< "$MODEL_REPORT"; then
    _fail "Model configuration check" "exit 0" "exit $MODEL_RC" "Run: $MAIW_PYTHON scripts/lib/check_model_config.py"
fi
if [[ "${NVIDIA_API_KEY:-}" == "your-nvidia-api-key-here" && -z "${MAIW_NIM_API_KEY:-}" ]]; then
    _fail "NVIDIA_API_KEY" "a real key (hosted provider)" "the .env.example placeholder" "Set NVIDIA_API_KEY in .env"
fi

# ── Check 9: Required ports free ──────────────────────────────────────────────
_header "Port Availability"
for port in "${REQUIRED_PORTS[@]}"; do
    if ss -tlnp "sport = :$port" 2>/dev/null | grep -q ":$port" || \
       netstat -tln 2>/dev/null | grep -q ":$port "; then
        # Restart preflights while THIS deployment's verified instance still
        # holds the port (it is stopped only after preflight passes).
        if maiw_verify_instance --no-live && [[ "$MAIW_TARGET_PORT" == "$port" ]]; then
            _pass "Port $port held by this deployment's verified instance (PID $MAIW_TARGET_PID)"
        else
            _fail "Port $port" "free" "in use by another process" \
                "Choose a free MAIW_API_PORT (lifecycle scripts never kill by port)"
        fi
    else
        _pass "Port $port is free"
    fi
done

# ── Check 10: Persistence dirs writable ───────────────────────────────────────
_header "Persistence Directories"
PERSIST_DIRS=(
    "${MAIW_PERSISTENCE_ROOT}/procedures"
    "${MAIW_PERSISTENCE_ROOT}/governance"
    "${MAIW_PERSISTENCE_ROOT}/runtime"
)
for dir in "${PERSIST_DIRS[@]}"; do
    if [[ -d "$dir" ]]; then
        if [[ -w "$dir" ]]; then
            _pass "Persistence dir writable: $dir"
        else
            _fail "Persistence dir writable" "writable" "$dir is not writable" \
                "chown the directory to the MAIW service user: sudo chown \$USER $dir"
        fi
    else
        # Dir doesn't exist yet — `mkdir -p` succeeds iff the nearest EXISTING
        # ancestor is writable (any number of missing levels).
        ANCESTOR=$(dirname "$dir")
        while [[ ! -e "$ANCESTOR" && "$ANCESTOR" != "/" ]]; do
            ANCESTOR=$(dirname "$ANCESTOR")
        done
        if [[ -d "$ANCESTOR" && -w "$ANCESTOR" ]]; then
            _pass "Persistence dir will be created: $dir"
        else
            _fail "Persistence dir creatable" "nearest existing ancestor writable" \
                "$ANCESTOR not writable" \
                "sudo mkdir -p $dir && sudo chown \$USER $dir (or choose a writable MAIW_PERSISTENCE_ROOT)"
        fi
    fi
done

# Disk space for persistence (Step 63). Measured on the nearest existing
# ancestor: on a fresh host the root does not exist yet and `df` on a missing
# path reported 0MB (false failure, found during v2.0.1 live qualification).
PERSIST_PROBE="${MAIW_PERSISTENCE_ROOT}"
while [[ ! -e "$PERSIST_PROBE" && "$PERSIST_PROBE" != "/" ]]; do
    PERSIST_PROBE="$(dirname "$PERSIST_PROBE")"
done
PERSIST_PARTITION=$(df --output=avail -m "${PERSIST_PROBE}" 2>/dev/null | tail -1 | tr -d ' ' || echo 0)
if [[ -n "$PERSIST_PARTITION" ]] && [[ "$PERSIST_PARTITION" -ge "$MIN_DISK_MB_STATE" ]]; then
    _pass "Persistence disk: ${PERSIST_PARTITION}MB available (>= ${MIN_DISK_MB_STATE}MB)"
else
    _fail "Persistence disk" ">= ${MIN_DISK_MB_STATE}MB" "${PERSIST_PARTITION:-unknown}MB" \
        "Free disk space on $(df --output=target "${PERSIST_PROBE}" 2>/dev/null | tail -1)"
fi

# ── Check 11: Auth token ──────────────────────────────────────────────────────
_header "Authentication"
if [[ -n "${MAIW_INFERENCE_INTERNAL_TOKEN:-}" ]]; then
    TOKEN_LEN=${#MAIW_INFERENCE_INTERNAL_TOKEN}
    if [[ "$MAIW_INFERENCE_INTERNAL_TOKEN" == "your-strong-random-token-min-32-chars" ]]; then
        _fail "MAIW_INFERENCE_INTERNAL_TOKEN" "a fresh random token" "the .env.example placeholder" \
            "Generate one: python3 -c \"import secrets; print(secrets.token_hex(32))\""
    elif [[ "$TOKEN_LEN" -ge 32 ]]; then
        _pass "MAIW_INFERENCE_INTERNAL_TOKEN set (length >= 32)"
    else
        _fail "MAIW_INFERENCE_INTERNAL_TOKEN length" ">= 32 chars" \
            "${TOKEN_LEN} chars" \
            "Generate a stronger token: python3 -c \"import secrets; print(secrets.token_hex(32))\""
    fi
else
    _fail "MAIW_INFERENCE_INTERNAL_TOKEN" "set and non-empty" "not set" \
        "Set MAIW_INFERENCE_INTERNAL_TOKEN in .env — generate with: python3 -c \"import secrets; print(secrets.token_hex(32))\""
fi

# ── Check 11b: Operational write credential (v2.0.1 round 3, NEW3-P1-01) ─────
# Governed operational writes require a SEPARATE operator credential
# (X-Maiw-Operator-Token).  The same check the app runs (maiw_api.write_auth):
# set, not the placeholder, >= 32 chars, and NOT equal to the sandbox inference
# token.  Required when the profile offers governed writes.
WRITE_AUTH=$("$MAIW_PYTHON" -c '
from maiw_api.write_auth import operator_write_auth_status
s = operator_write_auth_status()
print("OK" if s.configured else "NO " + (s.reason or "not configured"))
' 2>/dev/null || echo "NO maiw_api.write_auth not importable")
if [[ "${MAIW_DEPLOYMENT_PROFILE:-}" == "reference_governed" ]]; then
    if [[ "$WRITE_AUTH" == "OK" ]]; then
        _pass "MAIW_OPERATOR_WRITE_TOKEN set (>= 32 chars, distinct from the inference token)"
    else
        _fail "MAIW_OPERATOR_WRITE_TOKEN" "a fresh random operator write token, distinct from MAIW_INFERENCE_INTERNAL_TOKEN" \
            "${WRITE_AUTH#NO }" \
            "Generate one: python3 -c \"import secrets; print(secrets.token_hex(32))\" (never give it to the sandbox)"
    fi
elif [[ -n "${MAIW_OPERATOR_WRITE_TOKEN:-}" && "$WRITE_AUTH" != "OK" ]]; then
    _fail "MAIW_OPERATOR_WRITE_TOKEN" "unset, or a valid operator write token" "${WRITE_AUTH#NO }" \
        "Remove it (profile ${MAIW_DEPLOYMENT_PROFILE:-reference} offers no governed writes) or fix it"
else
    _pass "Operator write credential not required (profile ${MAIW_DEPLOYMENT_PROFILE:-reference}: governed writes not offered)"
fi
DEMO_FLAG="${MAIW_DEMO_MODE:-false}"
if [[ "${DEMO_FLAG,,}" == "true" || "$DEMO_FLAG" == "1" || "${DEMO_FLAG,,}" == "yes" ]]; then
    _fail "MAIW_DEMO_MODE" "unset/false (reference deployment)" "$DEMO_FLAG" \
        "Demo/simulation mode is not a reference deployment; remove MAIW_DEMO_MODE"
else
    _pass "MAIW_DEMO_MODE is not enabled (good)"
fi

# ── Check 12: Dev unauthenticated override NOT active ─────────────────────────
ALLOW_UNAUTH="${MAIW_INFERENCE_ALLOW_UNAUTHENTICATED:-false}"
if [[ "${ALLOW_UNAUTH,,}" == "true" ]] || [[ "$ALLOW_UNAUTH" == "1" ]] || [[ "${ALLOW_UNAUTH,,}" == "yes" ]]; then
    _fail "MAIW_INFERENCE_ALLOW_UNAUTHENTICATED" "false (reference deployment)" \
        "$ALLOW_UNAUTH" \
        "Remove MAIW_INFERENCE_ALLOW_UNAUTHENTICATED or set it to false"
else
    _pass "MAIW_INFERENCE_ALLOW_UNAUTHENTICATED is not enabled (good)"
fi

# ── Check 13: Sandbox REQUIRED mode enabled ───────────────────────────────────
_header "Sandbox Policy"
SANDBOX_MODE="${MAIW_SANDBOX_MODE:-disabled}"
if [[ "$SANDBOX_MODE" == "required" ]]; then
    _pass "MAIW_SANDBOX_MODE=required (sandbox enforced; participates in readiness)"
    # v2.0.1 round 3: the gateway is an explicit, verified step (it was an
    # undocumented prerequisite).  Targets OPENSHELL_GATEWAY_ENDPOINT only.
    if [[ -z "${OPENSHELL_GATEWAY_ENDPOINT:-}" ]]; then
        _fail "OPENSHELL_GATEWAY_ENDPOINT" "set (the gateway this deployment uses)" "not set" \
            "Set it in .env and run: bash scripts/setup/reference_gateway.sh start"
    elif command -v openshell &>/dev/null && openshell --gateway-endpoint "$OPENSHELL_GATEWAY_ENDPOINT" status >/dev/null 2>&1; then
        _pass "OpenShell gateway reachable at $OPENSHELL_GATEWAY_ENDPOINT"
    else
        _fail "OpenShell gateway" "reachable at $OPENSHELL_GATEWAY_ENDPOINT" "not reachable" \
            "bash scripts/setup/reference_gateway.sh start (runbook § OpenShell gateway)"
    fi
    if [[ -z "${MAIW_SANDBOX_NAME:-}" ]]; then
        _fail "MAIW_SANDBOX_NAME" "name of the reference sandbox" "not set" \
            "Create it: bash scripts/setup/reference_sandbox.sh create (runbook § Sandbox)"
    elif ! command -v openshell &>/dev/null; then
        _fail "OpenShell CLI" "in PATH" "not found" "Install OpenShell $REQUIRED_OPENSHELL_VERSION"
    else
        SBX_PHASE=$(openshell sandbox list -o json 2>/dev/null | "$MAIW_PYTHON" -c "
import sys, json
name = sys.argv[1]
for s in json.load(sys.stdin):
    if s.get('name') == name:
        print(s.get('phase', '')); break
" "$MAIW_SANDBOX_NAME" 2>/dev/null || echo "")
        if [[ "$SBX_PHASE" == "Ready" ]]; then
            _pass "OpenShell sandbox '$MAIW_SANDBOX_NAME' Ready"
        else
            _fail "OpenShell sandbox '$MAIW_SANDBOX_NAME'" "phase Ready" "${SBX_PHASE:-absent}" \
                "bash scripts/setup/reference_sandbox.sh create"
        fi
    fi
else
    _fail "MAIW_SANDBOX_MODE" "required" "$SANDBOX_MODE" \
        "Set MAIW_SANDBOX_MODE=required in .env for reference deployment"
fi

# ── Check 14: Database (data path: PGHOST/PGPORT/POSTGRES_*) ──────────────────
_header "Database"
DB_REPORT=$("$MAIW_PYTHON" - <<'PYEOF' 2>&1
import asyncio, os, sys
host = os.getenv("PGHOST", "localhost"); port = int(os.getenv("PGPORT", "5435"))
db = os.getenv("POSTGRES_DB", "warehouse")
url = os.getenv("DATABASE_URL")
if url:
    from urllib.parse import urlparse
    u = urlparse(url)
    norm = lambda h: "127.0.0.1" if (h or "").lower() in ("localhost", "::1", "") else h
    if (norm(u.hostname), u.port or 5432, (u.path or "/").lstrip("/")) != (norm(host), port, db):
        print(f"FAIL DATABASE_URL targets a different database than PGHOST/PGPORT/POSTGRES_DB ({host}:{port}/{db})")
        sys.exit(1)
async def main():
    import asyncpg
    conn = await asyncpg.connect(host=host, port=port, database=db,
        user=os.getenv("POSTGRES_USER", "warehouse"),
        password=os.getenv("POSTGRES_PASSWORD", ""), timeout=5)
    try:
        await conn.execute("SELECT 1")
        has = await conn.fetchval("select to_regclass('public.equipment_assets') is not null")
    finally:
        await conn.close()
    print(f"PASS {host}:{port}/{db} SELECT 1 ok; schema {'loaded' if has else 'MISSING'}")
    sys.exit(0 if has else 1)
try:
    asyncio.run(main())
except SystemExit:
    raise
except Exception as exc:
    print(f"FAIL {host}:{port}/{db} unreachable: {type(exc).__name__}")
    sys.exit(1)
PYEOF
) && DB_RC=0 || DB_RC=$?
if [[ "$DB_RC" -eq 0 ]]; then
    _pass "Database: ${DB_REPORT#PASS }"
else
    _fail "Database" "reachable with schema loaded" "${DB_REPORT#FAIL }" \
        "bash scripts/setup/reference_db.sh up (runbook § Database)"
fi

# ── Check 15: MCP write domains (reference_governed only) ─────────────────────
_header "MCP Domains"
if [[ "${MAIW_DEPLOYMENT_PROFILE:-}" == "reference_governed" ]]; then
    REQ_DOMAINS="${MAIW_REQUIRED_MCP_DOMAINS:-equipment,labor,wave}"
    for domain in ${REQ_DOMAINS//,/ }; do
        var="MAIW_MCP_SERVER_${domain^^}_URL"
        url="${!var:-}"
        if [[ -z "$url" ]]; then
            _fail "MCP domain $domain" "$var set (required for governed writes)" "not set" \
                "Configure the $domain MCP server (runbook § MCP)"
            continue
        fi
        if "$MAIW_PYTHON" -c "
import socket, sys
from urllib.parse import urlparse
u = urlparse(sys.argv[1])
socket.create_connection((u.hostname, u.port or (443 if u.scheme == 'https' else 80)), timeout=2).close()
" "$url" 2>/dev/null; then
            _pass "MCP domain $domain reachable ($var)"
        else
            _fail "MCP domain $domain" "reachable" "$var not reachable" "Start the $domain MCP server"
        fi
    done
else
    _pass "Profile ${MAIW_DEPLOYMENT_PROFILE:-reference}: governed MCP writes not offered; MCP domains optional"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "Preflight summary: $CHECKS_PASSED passed, $CHECKS_FAILED failed"
echo ""

if [[ "$FAIL" -ne 0 ]]; then
    echo "PREFLIGHT FAILED — resolve the errors above before starting." >&2
    echo "See docs/operations/REFERENCE_DEPLOYMENT_RUNBOOK.md for guidance." >&2
    exit 1
fi

echo "PREFLIGHT PASSED — safe to start reference deployment."
exit 0
