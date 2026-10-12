#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# scripts/setup/reference_gateway.sh — the OpenShell gateway the reference
# sandbox runs under (v2.0.1 round 3; third re-audit N-9 / spec §28).
#
# The third re-audit found the runbook listed "a running OpenShell gateway" as
# a prerequisite with no step to start or verify it; after a host reboot the
# gateway was down and had to be started by hand.  This script makes that step
# explicit and reproducible.
#
#   bash scripts/setup/reference_gateway.sh start    start (managed) / verify (external)
#   bash scripts/setup/reference_gateway.sh status   verify: process (managed), version, reachable
#   bash scripts/setup/reference_gateway.sh stop     stop ONLY a gateway this script started
#
# Modes (MAIW_OPENSHELL_GATEWAY_MODE):
#   managed   (default) this deployment runs its OWN `openshell-gateway`:
#             name MAIW_OPENSHELL_GATEWAY_NAME, 127.0.0.1:MAIW_OPENSHELL_GATEWAY_PORT,
#             docker driver, its own sandbox namespace and docker network, its
#             own Ed25519 gateway-JWT and state under
#             $MAIW_PERSISTENCE_ROOT/openshell-gateway/.  Loopback only, TLS
#             off on loopback (single-node reference; see the runbook).  It
#             never touches any other gateway on the host.
#   external  use a gateway someone else runs (e.g. a NemoClaw-managed one).
#             `start` only VERIFIES it (reachable, version) and never starts,
#             stops or reconfigures it — start it with the tool that owns it.
#
# Every OpenShell CLI call in the lifecycle scripts targets the gateway named by
# OPENSHELL_GATEWAY_ENDPOINT (exported by scripts/lib/load_env.sh from .env).
# For managed mode set OPENSHELL_GATEWAY_ENDPOINT=http://127.0.0.1:<port>.
#
# Exit: 0 ok; 1 not running / not reachable / wrong version; 2 refused.
# ---------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd -P)"
# shellcheck source=../lib/load_env.sh
source "$PROJECT_ROOT/scripts/lib/load_env.sh"
maiw_load_env "$PROJECT_ROOT"
maiw_require_vars OPENSHELL_GATEWAY_ENDPOINT MAIW_PERSISTENCE_ROOT

REQUIRED_OPENSHELL_VERSION="0.0.116"
ACTION="${1:-status}"
MODE="${MAIW_OPENSHELL_GATEWAY_MODE:-managed}"
ENDPOINT="$OPENSHELL_GATEWAY_ENDPOINT"

command -v openshell >/dev/null || { echo "ERROR: openshell CLI not in PATH" >&2; exit 1; }

_cli_version() {
    openshell --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || true
}

# Reachability + identity of the gateway at $ENDPOINT (never any other).
_verify() {
    local cli_v status_out
    cli_v="$(_cli_version)"
    if [[ "$cli_v" != "$REQUIRED_OPENSHELL_VERSION" ]]; then
        echo "  FAIL  OpenShell CLI version ${cli_v:-unknown} (required $REQUIRED_OPENSHELL_VERSION)" >&2
        return 1
    fi
    if ! status_out="$(openshell --gateway-endpoint "$ENDPOINT" status 2>&1)"; then
        echo "  FAIL  OpenShell gateway at $ENDPOINT not reachable" >&2
        printf '%s\n' "$status_out" | head -5 | sed 's/^/        /' >&2
        return 1
    fi
    if ! openshell --gateway-endpoint "$ENDPOINT" sandbox list >/dev/null 2>&1; then
        echo "  FAIL  OpenShell gateway at $ENDPOINT does not answer sandbox list" >&2
        return 1
    fi
    echo "  PASS  OpenShell gateway reachable at $ENDPOINT (CLI $cli_v)"
    printf '%s\n' "$status_out" | sed 's/\x1b\[[0-9;]*m//g' | grep -iE 'version|status|server' \
        | head -4 | sed 's/^/        /' || true
    return 0
}

case "$MODE" in
    external)
        case "$ACTION" in
            start|status)
                echo "OpenShell gateway (external — not managed by MAIW): $ENDPOINT"
                if _verify; then exit 0; fi
                echo "  The gateway is not running/reachable. Start it with the tool that owns it;" >&2
                echo "  this script never starts or stops an external gateway." >&2
                exit 1
                ;;
            stop)
                echo "REFUSED: MAIW_OPENSHELL_GATEWAY_MODE=external — not stopping a gateway MAIW does not own." >&2
                exit 2
                ;;
            *) echo "usage: $0 start|status|stop" >&2; exit 2 ;;
        esac
        ;;
    managed) ;;
    *) echo "ERROR: MAIW_OPENSHELL_GATEWAY_MODE must be managed|external (got '$MODE')" >&2; exit 2 ;;
esac

# ── managed mode ──────────────────────────────────────────────────────────────
maiw_require_vars MAIW_OPENSHELL_GATEWAY_NAME MAIW_OPENSHELL_GATEWAY_PORT
NAME="$MAIW_OPENSHELL_GATEWAY_NAME"
PORT="$MAIW_OPENSHELL_GATEWAY_PORT"
if [[ ! "$NAME" =~ ^[a-z0-9][a-z0-9-]{0,39}$ ]]; then
    echo "ERROR: MAIW_OPENSHELL_GATEWAY_NAME must be [a-z0-9-], <= 40 chars (got '$NAME')" >&2
    exit 2
fi
if [[ "$ENDPOINT" != "http://127.0.0.1:$PORT" ]]; then
    echo "ERROR: managed mode requires OPENSHELL_GATEWAY_ENDPOINT=http://127.0.0.1:$PORT (got '$ENDPOINT')" >&2
    exit 2
fi
GW_DIR="$MAIW_PERSISTENCE_ROOT/openshell-gateway"
CONFIG="$GW_DIR/gateway.toml"
PIDFILE="$GW_DIR/gateway.pid"
LOGFILE="$GW_DIR/gateway.log"
MARKER="$GW_DIR/created-by-maiw"
NAMESPACE="${MAIW_OPENSHELL_GATEWAY_NAMESPACE:-$NAME}"
NETWORK="${MAIW_OPENSHELL_GATEWAY_NETWORK:-$NAME-net}"

_pid_ok() {  # our gateway process: pid file, alive, and the cmdline names our config
    [[ -f "$PIDFILE" ]] || return 1
    local pid; pid="$(cat "$PIDFILE")"
    [[ "$pid" =~ ^[0-9]+$ ]] || return 1
    kill -0 "$pid" 2>/dev/null || return 1
    tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null | grep -q -- "--config $CONFIG" || return 1
    return 0
}

_port_in_use() {
    "${MAIW_PYTHON:-python3}" - "$PORT" <<'PY'
import socket, sys
s = socket.socket(); s.settimeout(1)
sys.exit(0 if s.connect_ex(("127.0.0.1", int(sys.argv[1]))) == 0 else 1)
PY
}

case "$ACTION" in
    start)
        if _pid_ok; then
            echo "OpenShell gateway '$NAME' already running (PID $(cat "$PIDFILE"))"
            _verify
            exit $?
        fi
        if _port_in_use; then
            echo "ERROR: 127.0.0.1:$PORT is in use by another process — choose a free MAIW_OPENSHELL_GATEWAY_PORT" >&2
            exit 2
        fi
        command -v openshell-gateway >/dev/null || { echo "ERROR: openshell-gateway not in PATH" >&2; exit 1; }
        SUPERVISOR="$(command -v openshell-sandbox || true)"
        [[ -n "$SUPERVISOR" ]] || { echo "ERROR: openshell-sandbox not in PATH" >&2; exit 1; }
        GW_V="$(openshell-gateway --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || true)"
        if [[ "$GW_V" != "$REQUIRED_OPENSHELL_VERSION" ]]; then
            echo "ERROR: openshell-gateway ${GW_V:-unknown} (required $REQUIRED_OPENSHELL_VERSION)" >&2
            exit 1
        fi
        mkdir -p "$GW_DIR/jwt" "$GW_DIR/state"
        chmod 700 "$GW_DIR" "$GW_DIR/jwt" "$GW_DIR/state"
        if [[ ! -f "$GW_DIR/jwt/signing.pem" ]]; then
            ( umask 077
              openssl genpkey -algorithm ed25519 -out "$GW_DIR/jwt/signing.pem" 2>/dev/null
              openssl pkey -in "$GW_DIR/jwt/signing.pem" -pubout -out "$GW_DIR/jwt/public.pem" 2>/dev/null
              openssl rand -hex 16 > "$GW_DIR/jwt/kid" )
        fi
        cat > "$CONFIG" <<TOML
# Rendered by scripts/setup/reference_gateway.sh — MAIW-owned OpenShell gateway.
[openshell]
version = 1

[openshell.gateway]
compute_drivers = ["docker"]
disable_tls = true

[openshell.gateway.gateway_jwt]
signing_key_path = "$GW_DIR/jwt/signing.pem"
public_key_path = "$GW_DIR/jwt/public.pem"
kid_path = "$GW_DIR/jwt/kid"
gateway_id = "$NAME"
ttl_secs = 0

[openshell.gateway.auth]
allow_unauthenticated_users = true

[openshell.drivers.docker]
sandbox_namespace = "$NAMESPACE"
grpc_endpoint = "http://127.0.0.1:$PORT"
network_name = "$NETWORK"
supervisor_bin = "$SUPERVISOR"
TOML
        chmod 600 "$CONFIG"
        date -u +%Y-%m-%dT%H:%M:%SZ > "$MARKER"
        # Own state (sqlite DB, sandbox tokens) under $GW_DIR — never the
        # invoking user's ~/.local/state.
        nohup env XDG_STATE_HOME="$GW_DIR/state" openshell-gateway --config "$CONFIG" \
            --name "$NAME" --bind-address 127.0.0.1 --port "$PORT" \
            --db-url "sqlite:$GW_DIR/state/openshell.db" \
            >> "$LOGFILE" 2>&1 < /dev/null &
        echo $! > "$PIDFILE"
        for _ in $(seq 1 60); do
            if ! _pid_ok; then
                echo "ERROR: openshell-gateway exited during startup; see $LOGFILE" >&2
                tail -5 "$LOGFILE" >&2 || true
                exit 1
            fi
            if openshell --gateway-endpoint "$ENDPOINT" status >/dev/null 2>&1; then
                break
            fi
            sleep 1
        done
        echo "OpenShell gateway '$NAME' started (PID $(cat "$PIDFILE"), 127.0.0.1:$PORT, namespace $NAMESPACE, network $NETWORK)"
        _verify
        ;;
    status)
        if _pid_ok; then
            echo "OpenShell gateway '$NAME': running (PID $(cat "$PIDFILE"))"
            _verify
        else
            echo "OpenShell gateway '$NAME': NOT RUNNING — start it with: bash scripts/setup/reference_gateway.sh start" >&2
            exit 1
        fi
        ;;
    stop)
        if [[ ! -f "$MARKER" ]]; then
            echo "REFUSED: no gateway was started by this script for this deployment ($MARKER missing)." >&2
            exit 2
        fi
        if _pid_ok; then
            PID="$(cat "$PIDFILE")"
            kill -TERM "$PID"
            for _ in $(seq 1 30); do kill -0 "$PID" 2>/dev/null || break; sleep 1; done
            if kill -0 "$PID" 2>/dev/null && _pid_ok; then kill -KILL "$PID"; fi
            echo "OpenShell gateway '$NAME' stopped (PID $PID)."
        else
            echo "OpenShell gateway '$NAME': not running (nothing signalled)."
        fi
        rm -f "$PIDFILE"
        # The docker network this gateway created, only when empty.
        if docker network inspect "$NETWORK" >/dev/null 2>&1; then
            if [[ "$(docker network inspect -f '{{len .Containers}}' "$NETWORK" 2>/dev/null)" == "0" ]]; then
                docker network rm "$NETWORK" >/dev/null && echo "Docker network '$NETWORK' removed."
            else
                echo "Docker network '$NETWORK' still has containers — not removed (delete the sandbox first)." >&2
            fi
        fi
        ;;
    *)
        echo "usage: $0 start|status|stop" >&2
        exit 2
        ;;
esac
