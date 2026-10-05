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
# Exit codes:
#   0  all checks pass
#   1  one or more checks failed (details printed to stderr)
#
# Steps 8, 41, 42, 45, 62, 63, 64, 65 of Phase 20C-C.
# ---------------------------------------------------------------------------
set -euo pipefail

# ── Globals ──────────────────────────────────────────────────────────────────
QUIET=${1:-""}
FAIL=0
CHECKS_PASSED=0
CHECKS_FAILED=0

# Qualified component versions (Step 3 / Step 45)
REQUIRED_NEMOCLAW_VERSION="0.0.124"
REQUIRED_OPENSHELL_VERSION="0.0.116"
REQUIRED_PYTHON_MIN="3.12"

# Approved model generation values (Step 42)
APPROVED_GENERATIONS=("nemotron-3" "nemotron-3.5")

# Persistence root (Step 29)
MAIW_PERSISTENCE_ROOT="${MAIW_PERSISTENCE_ROOT:-/var/lib/maiw}"

# Required ports (Step 64)
REQUIRED_PORTS=(8001 8020)

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
PY_VERSION=$(python3 --version 2>/dev/null | awk '{print $2}' || echo "0.0.0")
if _version_ge "$PY_VERSION" "$REQUIRED_PYTHON_MIN"; then
    _pass "Python $PY_VERSION >= $REQUIRED_PYTHON_MIN"
else
    _fail "Python version" ">= $REQUIRED_PYTHON_MIN" "$PY_VERSION" \
        "Install Python $REQUIRED_PYTHON_MIN or newer"
fi

# ── Check 3: GPU visibility ───────────────────────────────────────────────────
_header "GPU / CUDA"
if command -v nvidia-smi &>/dev/null; then
    GPU_COUNT=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | wc -l || echo 0)
    if [[ "$GPU_COUNT" -ge 1 ]]; then
        _pass "NVIDIA GPU(s) visible: $GPU_COUNT"
    else
        _fail "GPU visibility" ">= 1 NVIDIA GPU" "0 GPUs" \
            "Ensure NVIDIA GPU is installed and driver is loaded"
    fi
else
    _fail "nvidia-smi" "nvidia-smi command available" "not found" \
        "Install NVIDIA driver and CUDA toolkit"
fi

# Check NVIDIA driver version
if command -v nvidia-smi &>/dev/null; then
    DRIVER_VERSION=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -1 || echo "unknown")
    if [[ "$DRIVER_VERSION" != "unknown" ]]; then
        _pass "NVIDIA driver: $DRIVER_VERSION"
    else
        _fail "NVIDIA driver" "detectable" "$DRIVER_VERSION" \
            "Reinstall NVIDIA driver"
    fi
fi

# Check GPU architecture (must be SM_90a for H100 NVL or equivalent)
if command -v nvidia-smi &>/dev/null; then
    GPU_ARCH=$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader 2>/dev/null | head -1 || echo "unknown")
    _pass "GPU compute capability: $GPU_ARCH (reference: sm_90a for H100 NVL)"
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
if python3 -c "import nemoclaw; print(nemoclaw.__version__)" &>/dev/null 2>&1; then
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
if python3 -c "import openshell; print(openshell.__version__)" &>/dev/null 2>&1; then
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

# ── Check 7: Approved model deployment ────────────────────────────────────────
_header "Approved Model Deployment"
MODEL_ID="${LLM_MODEL:-${MAIW_NIM_MODEL:-}}"
if [[ -z "$MODEL_ID" ]]; then
    _fail "Approved model" "LLM_MODEL or MAIW_NIM_MODEL set" "not set" \
        "Set LLM_MODEL=nvidia/nemotron-3-super-120b-a12b in .env"
else
    _pass "Model configured: $MODEL_ID"
fi

# ── Check 8: Approved model generation ────────────────────────────────────────
_header "Model Generation Policy"
MODEL_GEN="${MAIW_MODEL_GENERATION:-}"
if [[ -z "$MODEL_GEN" ]]; then
    # Infer from model ID for known approved models
    case "${MODEL_ID:-}" in
        *nemotron-3-*|*nemotron-3\.*|*nemotron-3-super*|*nemotron-3-nano*|*nemotron-3-ultra*)
            INFERRED_GEN="nemotron-3" ;;
        *nemotron-3.5*)
            INFERRED_GEN="nemotron-3.5" ;;
        nvidia/llama-*|*llama-*|*qwen*|*mistral*|*gemma*)
            INFERRED_GEN="unapproved"
            _fail "Model generation" "nemotron-3 or nemotron-3.5" \
                "inferred $INFERRED_GEN from $MODEL_ID" \
                "Use an approved model: nvidia/nemotron-3-super-120b-a12b (gen=nemotron-3)"
            MODEL_GEN="$INFERRED_GEN" ;;
        *)
            INFERRED_GEN="unknown"
            _fail "Model generation" "nemotron-3 or nemotron-3.5" \
                "cannot infer from $MODEL_ID" \
                "Set MAIW_MODEL_GENERATION=nemotron-3 or nemotron-3.5 explicitly"
            MODEL_GEN="$INFERRED_GEN" ;;
    esac
    if [[ "${INFERRED_GEN:-unknown}" == "nemotron-3" ]] || [[ "${INFERRED_GEN:-unknown}" == "nemotron-3.5" ]]; then
        _pass "Model generation inferred: $INFERRED_GEN (from $MODEL_ID)"
        MODEL_GEN="$INFERRED_GEN"
    fi
else
    GEN_OK=0
    for approved in "${APPROVED_GENERATIONS[@]}"; do
        [[ "$MODEL_GEN" == "$approved" ]] && GEN_OK=1
    done
    if [[ "$GEN_OK" -eq 1 ]]; then
        _pass "Model generation: $MODEL_GEN (explicitly set)"
    else
        _fail "Model generation" "nemotron-3 or nemotron-3.5" \
            "$MODEL_GEN" \
            "Set MAIW_MODEL_GENERATION to an approved generation"
    fi
fi

# Check that Llama-family / legacy models are not configured
LLAMA_LEGACY_MODELS=(
    "nvidia/llama-3.3-nemotron-super-49b-v1.5"
    "nvidia/llama-3.1-nemotron-nano-4b-v1.1"
    "nvidia/llama-3.1-nemotron-ultra-253b-v1"
    "nvidia/llama-nemotron-nano-vl-8b-v1"
    "nvidia/llama-nemotron-embed-vl-1b-v2"
    "nvidia/llama-3.1-nemotron-nano-8b-v1"
)
MODEL_IS_LEGACY=0
for legacy in "${LLAMA_LEGACY_MODELS[@]}"; do
    if [[ "${MODEL_ID:-}" == "$legacy" ]]; then
        MODEL_IS_LEGACY=1
        break
    fi
done
if [[ "$MODEL_IS_LEGACY" -eq 1 ]]; then
    _fail "Legacy model rejected" "Approved Nemotron 3/3.5 model" \
        "$MODEL_ID (Llama-family / legacy, rejected by PolicyFilter)" \
        "Use nvidia/nemotron-3-super-120b-a12b or another approved model"
else
    _pass "Legacy model not configured"
fi

# ── Check 9: Required ports free ──────────────────────────────────────────────
_header "Port Availability"
for port in "${REQUIRED_PORTS[@]}"; do
    if ss -tlnp "sport = :$port" 2>/dev/null | grep -q ":$port" || \
       netstat -tln 2>/dev/null | grep -q ":$port "; then
        _fail "Port $port" "free" "in use" \
            "Stop the process using port $port: ss -tlnp | grep :$port"
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
        # Dir doesn't exist yet — check parent
        PARENT=$(dirname "$dir")
        if [[ -w "$PARENT" ]] || [[ -w "$(dirname "$PARENT")" ]]; then
            _pass "Persistence dir will be created: $dir"
        else
            _fail "Persistence dir parent writable" "parent writable" \
                "$(dirname "$dir") not writable" \
                "sudo mkdir -p $dir && sudo chown \$USER $dir"
        fi
    fi
done

# Disk space for persistence (Step 63)
PERSIST_PARTITION=$(df --output=avail -m "${MAIW_PERSISTENCE_ROOT}" 2>/dev/null | tail -1 | tr -d ' ' || echo 0)
if [[ -n "$PERSIST_PARTITION" ]] && [[ "$PERSIST_PARTITION" -ge "$MIN_DISK_MB_STATE" ]]; then
    _pass "Persistence disk: ${PERSIST_PARTITION}MB available (>= ${MIN_DISK_MB_STATE}MB)"
else
    _fail "Persistence disk" ">= ${MIN_DISK_MB_STATE}MB" "${PERSIST_PARTITION:-unknown}MB" \
        "Free disk space on $(df --output=target "${MAIW_PERSISTENCE_ROOT}" 2>/dev/null | tail -1)"
fi

# ── Check 11: Auth token ──────────────────────────────────────────────────────
_header "Authentication"
if [[ -n "${MAIW_INFERENCE_INTERNAL_TOKEN:-}" ]]; then
    TOKEN_LEN=${#MAIW_INFERENCE_INTERNAL_TOKEN}
    if [[ "$TOKEN_LEN" -ge 32 ]]; then
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
    _pass "MAIW_SANDBOX_MODE=required (sandbox enforced)"
else
    _fail "MAIW_SANDBOX_MODE" "required" "$SANDBOX_MODE" \
        "Set MAIW_SANDBOX_MODE=required in .env for reference deployment"
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
