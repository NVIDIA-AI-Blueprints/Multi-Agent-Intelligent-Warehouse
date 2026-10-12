#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# scripts/setup/reference_sandbox.sh — the reference deployment's OpenShell
# sandbox (v2.0.1 round 2, NEW-P1-02 §21).
#
#   bash scripts/setup/reference_sandbox.sh create   render policy + create sandbox
#   bash scripts/setup/reference_sandbox.sh status   print the sandbox phase
#   bash scripts/setup/reference_sandbox.sh probe    run the in-sandbox probe
#                                                    against the canonical app
#                                                    (token on stdin, never printed)
#   bash scripts/setup/reference_sandbox.sh delete   delete it (only a sandbox
#                                                    this script created)
#
# Configuration (from .env via scripts/lib/load_env.sh):
#   MAIW_SANDBOX_NAME                    sandbox name (<= 19 characters, OpenShell limit)
#   MAIW_SANDBOX_MODEL_GATEWAY_ENDPOINT  http://<HOST_IP>:<MAIW_API_PORT>/api/v1/inference
#                                        — the host's routable IP (not localhost)
#   MAIW_API_PORT                        must equal the endpoint's port
#   MAIW_SANDBOX_FROM                    OpenShell image/community name (default: base)
#   MAIW_INFERENCE_INTERNAL_TOKEN        passed to the probe on stdin only
#
# Policy: deploy/openshell/maiw-inference-only.policy.yaml.tmpl — deny-by-
# default egress; on the MAIW API host:port only `POST /api/v1/inference` (L7
# REST rule, v2.0.1 round 3).  No credential provider is attached; the
# operator write credential is never passed to the sandbox.  The rendered policy is kept at
# $MAIW_PERSISTENCE_ROOT/runtime/sandbox-<name>.policy.yaml.
# ---------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd -P)"
# shellcheck source=../lib/load_env.sh
source "$PROJECT_ROOT/scripts/lib/load_env.sh"
# shellcheck source=../lib/deployment_identity.sh
source "$PROJECT_ROOT/scripts/lib/deployment_identity.sh"
maiw_load_env "$PROJECT_ROOT"
maiw_require_vars MAIW_SANDBOX_NAME MAIW_SANDBOX_MODEL_GATEWAY_ENDPOINT MAIW_API_PORT MAIW_PERSISTENCE_ROOT

ACTION="${1:-status}"
NAME="$MAIW_SANDBOX_NAME"
PY="${MAIW_PYTHON:-python3}"
RUNTIME_DIR="$(maiw_runtime_dir)"
MARKER="$RUNTIME_DIR/sandbox-${NAME}.created"
POLICY_OUT="$RUNTIME_DIR/sandbox-${NAME}.policy.yaml"

if [[ ${#NAME} -gt 19 || ! "$NAME" =~ ^[a-z0-9][a-z0-9-]*$ ]]; then
    echo "ERROR: MAIW_SANDBOX_NAME must be <= 19 chars of [a-z0-9-] (got '$NAME')" >&2
    exit 1
fi
command -v openshell >/dev/null || { echo "ERROR: openshell CLI not in PATH" >&2; exit 1; }

_phase() {
    openshell sandbox list -o json 2>/dev/null | "$PY" -c "
import sys, json
for s in json.load(sys.stdin):
    if s.get('name') == sys.argv[1]:
        print(s.get('phase', '')); break
" "$NAME" 2>/dev/null || true
}

# host / port from the documented endpoint variable
read -r EP_HOST EP_PORT < <("$PY" -c "
import sys
from urllib.parse import urlparse
u = urlparse(sys.argv[1]); print(u.hostname or '', u.port or '')
" "$MAIW_SANDBOX_MODEL_GATEWAY_ENDPOINT")

case "$ACTION" in
    create)
        if [[ -z "$EP_HOST" || "$EP_HOST" == "localhost" || "$EP_HOST" == 127.* || "$EP_HOST" == "HOST_IP" ]]; then
            echo "ERROR: MAIW_SANDBOX_MODEL_GATEWAY_ENDPOINT must use the host's routable IP (got '$EP_HOST')" >&2
            exit 1
        fi
        if [[ "$EP_PORT" != "$MAIW_API_PORT" ]]; then
            echo "ERROR: endpoint port $EP_PORT != MAIW_API_PORT $MAIW_API_PORT" >&2
            exit 1
        fi
        if [[ -n "$(_phase)" ]]; then
            echo "ERROR: sandbox '$NAME' already exists — choose another MAIW_SANDBOX_NAME or delete it first." >&2
            exit 1
        fi
        mkdir -p "$RUNTIME_DIR"
        sed -e "s/__MAIW_API_HOST_IP__/${EP_HOST}/" -e "s/__MAIW_API_PORT__/${EP_PORT}/" \
            "$PROJECT_ROOT/deploy/openshell/maiw-inference-only.policy.yaml.tmpl" > "$POLICY_OUT"
        # The name was verified absent above, so a sandbox with this name after
        # this point is ours: record the marker first, so a failed create can
        # still be cleaned up with `delete`.
        date -u +%Y-%m-%dT%H:%M:%SZ > "$MARKER"
        if ! openshell sandbox create --name "$NAME" --from "${MAIW_SANDBOX_FROM:-base}" \
            --policy "$POLICY_OUT" --detach --no-tty >/dev/null; then
            echo "ERROR: sandbox create failed; removing the partial sandbox '$NAME'" >&2
            [[ -n "$(_phase)" ]] && openshell sandbox delete "$NAME" >/dev/null 2>&1 || true
            rm -f "$MARKER"
            exit 1
        fi
        for _ in $(seq 1 60); do
            [[ "$(_phase)" == "Ready" ]] && break
            sleep 2
        done
        echo "Sandbox '$NAME': $(_phase) (policy: egress only POST /api/v1/inference on $EP_HOST:$EP_PORT; no providers attached)"
        [[ "$(_phase)" == "Ready" ]]
        ;;
    status)
        PHASE="$(_phase)"
        echo "Sandbox '$NAME': ${PHASE:-absent}"
        [[ "$PHASE" == "Ready" ]]
        ;;
    probe)
        maiw_require_vars MAIW_INFERENCE_INTERNAL_TOKEN
        openshell sandbox upload "$NAME" "$PROJECT_ROOT/scripts/qualification/in_sandbox_canonical_probe.py" /sandbox/ >/dev/null
        BASE="${MAIW_SANDBOX_MODEL_GATEWAY_ENDPOINT%/api/v1/inference}"
        PROBE_OUT="$RUNTIME_DIR/sandbox-${NAME}.probe.json"
        mkdir -p "$RUNTIME_DIR"
        # The probe's exit status is its verdict (inference allowed with a
        # verified approved model AND every governed write denied for every
        # credential the sandbox holds — v2.0.1 round 3, NEW3-P1-01).
        PROBE_RC=0
        printf '%s\n' "$MAIW_INFERENCE_INTERNAL_TOKEN" | \
            openshell sandbox exec -n "$NAME" --no-tty -- python3 /sandbox/in_sandbox_canonical_probe.py "$BASE" \
            > "$PROBE_OUT" || PROBE_RC=$?
        cat "$PROBE_OUT"
        # Host secrets must not be present in the sandbox: compare digests of
        # host secret values with the digests the probe reported (no value is
        # ever printed or sent into the sandbox).
        "$PY" - "$PROBE_OUT" <<'PYEOF' || PROBE_RC=1
import hashlib, json, os, sys
raw = open(sys.argv[1]).read().strip().splitlines()
probe = json.loads(raw[-1]) if raw else {}
digests = set(probe.get("env_value_digests", []))
names = set(probe.get("env_secret_names", []))
leaked = []
for var in ("MAIW_OPERATOR_WRITE_TOKEN", "NVIDIA_API_KEY", "MAIW_NIM_API_KEY",
            "POSTGRES_PASSWORD", "JWT_SECRET_KEY"):
    value = os.environ.get(var)
    if var in names or (value and hashlib.sha256(value.encode()).hexdigest()[:24] in digests):
        leaked.append(var)
denied = probe.get("operational_writes_all_denied") is True
print(f"sandbox credential isolation: host secrets present in sandbox = {leaked or 'none'}")
print(f"sandbox governed-write denial: {'all denied' if denied else 'NOT ALL DENIED'}")
sys.exit(1 if (leaked or not denied) else 0)
PYEOF
        exit "$PROBE_RC"
        ;;
    delete)
        if [[ ! -f "$MARKER" ]]; then
            echo "ERROR: '$NAME' was not created by this script for this deployment ($MARKER missing) — refusing to delete." >&2
            exit 1
        fi
        openshell sandbox delete "$NAME" >/dev/null
        rm -f "$MARKER"
        echo "Sandbox '$NAME' deleted."
        ;;
    *)
        echo "usage: $0 create|status|probe|delete" >&2
        exit 2
        ;;
esac
