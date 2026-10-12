# shellcheck shell=bash
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# scripts/lib/deployment_identity.sh — deployment identity for the MAIW
# reference deployment (v2.0.1 round 2, NEW-P1-02 §17/§18/§19).
#
# start_reference_deployment.sh writes an instance-state file
#     $MAIW_RUNTIME_STATE_DIR/maiw-api.instance   (default $MAIW_PERSISTENCE_ROOT/runtime)
# with: instance_id, pid, host, port, project_root, app, started_at.
# The API process is launched with MAIW_INSTANCE_ID=<instance_id> and reports
# it on GET /api/v1/live.
#
# status / smoke / stop / restart act ONLY on a target that this file
# identifies and that passes every check below.  There is no fallback to a
# default port (e.g. localhost:8001) and no kill-by-port: if identity cannot be
# established the scripts report "NOT RUNNING / CANNOT VERIFY" and touch
# nothing.
#
# maiw_verify_instance [--no-live]
#   0   verified: sets MAIW_TARGET_PID, MAIW_TARGET_PORT, MAIW_TARGET_HOST,
#       MAIW_TARGET_BASE_URL, MAIW_TARGET_INSTANCE_ID
#   10  no instance-state file
#   11  recorded PID is not running (stale state)
#   12  recorded PID is a different process (cmdline / cwd / instance env)
#   13  the API port does not answer as this instance (/api/v1/live)
#   14  malformed instance-state file
# MAIW_VERIFY_REASON holds a one-line explanation.

maiw_runtime_dir() {
    if [[ -n "${MAIW_RUNTIME_STATE_DIR:-}" ]]; then
        printf '%s\n' "$MAIW_RUNTIME_STATE_DIR"
    else
        printf '%s/runtime\n' "${MAIW_PERSISTENCE_ROOT:?MAIW_PERSISTENCE_ROOT not set}"
    fi
}

maiw_instance_file() {
    printf '%s/maiw-api.instance\n' "$(maiw_runtime_dir)"
}

# maiw_write_instance ID PID HOST PORT PROJECT_ROOT — atomic, mode 600.
maiw_write_instance() {
    local file tmp
    file="$(maiw_instance_file)"
    tmp="${file}.tmp.$$"
    (
        umask 077
        {
            printf 'instance_id=%s\n' "$1"
            printf 'pid=%s\n' "$2"
            printf 'host=%s\n' "$3"
            printf 'port=%s\n' "$4"
            printf 'project_root=%s\n' "$5"
            printf 'app=maiw_api.app:app\n'
            printf 'started_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        } > "$tmp"
    )
    mv -f "$tmp" "$file"
    # legacy pidfile (read by nothing that kills; kept for operators' tooling)
    printf '%s\n' "$2" > "$(maiw_runtime_dir)/maiw-api.pid"
}

maiw_clear_instance() {
    rm -f "$(maiw_instance_file)" "$(maiw_runtime_dir)/maiw-api.pid"
}

# maiw_read_instance — parse the state file (never `source`d).
maiw_read_instance() {
    local file key val
    file="$(maiw_instance_file)"
    MAIW_I_INSTANCE_ID="" MAIW_I_PID="" MAIW_I_HOST="" MAIW_I_PORT="" MAIW_I_ROOT="" MAIW_I_APP=""
    [[ -f "$file" ]] || return 10
    while IFS='=' read -r key val; do
        case "$key" in
            instance_id) MAIW_I_INSTANCE_ID="$val" ;;
            pid) MAIW_I_PID="$val" ;;
            host) MAIW_I_HOST="$val" ;;
            port) MAIW_I_PORT="$val" ;;
            project_root) MAIW_I_ROOT="$val" ;;
            app) MAIW_I_APP="$val" ;;
        esac
    done < "$file"
    if [[ ! "$MAIW_I_PID" =~ ^[0-9]+$ || ! "$MAIW_I_PORT" =~ ^[0-9]+$ \
          || ! "$MAIW_I_INSTANCE_ID" =~ ^[A-Za-z0-9-]{16,}$ || -z "$MAIW_I_ROOT" ]]; then
        return 14
    fi
    return 0
}

# maiw_pid_is_instance PID PORT ROOT INSTANCE_ID — /proc identity of the process.
maiw_pid_is_instance() {
    local pid="$1" port="$2" root="$3" iid="$4" cmd cwd
    [[ -r "/proc/$pid/cmdline" ]] || return 1
    cmd="$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null)"
    [[ "$cmd" == *uvicorn* && "$cmd" == *"maiw_api.app:app"* && "$cmd" == *"--port $port"* ]] || return 1
    cwd="$(readlink "/proc/$pid/cwd" 2>/dev/null || true)"
    [[ "$cwd" == "$root" ]] || return 1
    tr '\0' '\n' < "/proc/$pid/environ" 2>/dev/null | grep -qx "MAIW_INSTANCE_ID=$iid" || return 1
    return 0
}

# maiw_live_instance_id URL — instance_id reported by GET URL/api/v1/live.
# A single bounded GET: the only interaction with an unverified listener.
maiw_live_instance_id() {
    local body
    body="$(curl -s --max-time 5 "$1/api/v1/live" 2>/dev/null || true)"
    [[ -n "$body" ]] || return 1
    printf '%s' "$body" | "${MAIW_PYTHON:-python3}" -c \
        'import sys,json; print(json.load(sys.stdin).get("instance_id") or "")' 2>/dev/null
}

maiw_verify_instance() {
    local want_live=1 rc
    [[ "${1:-}" == "--no-live" ]] && want_live=0
    MAIW_VERIFY_REASON=""
    MAIW_TARGET_PID="" MAIW_TARGET_PORT="" MAIW_TARGET_HOST="" MAIW_TARGET_BASE_URL="" MAIW_TARGET_INSTANCE_ID=""
    maiw_read_instance
    rc=$?
    if [[ $rc -eq 10 ]]; then
        MAIW_VERIFY_REASON="no deployment state at $(maiw_instance_file)"
        return 10
    elif [[ $rc -ne 0 ]]; then
        MAIW_VERIFY_REASON="malformed deployment state at $(maiw_instance_file)"
        return 14
    fi
    if ! kill -0 "$MAIW_I_PID" 2>/dev/null; then
        MAIW_VERIFY_REASON="recorded PID $MAIW_I_PID is not running (stale deployment state)"
        return 11
    fi
    if ! maiw_pid_is_instance "$MAIW_I_PID" "$MAIW_I_PORT" "$MAIW_I_ROOT" "$MAIW_I_INSTANCE_ID"; then
        MAIW_VERIFY_REASON="PID $MAIW_I_PID is not this MAIW instance (cmdline/cwd/instance id do not match)"
        return 12
    fi
    MAIW_TARGET_PID="$MAIW_I_PID"
    MAIW_TARGET_PORT="$MAIW_I_PORT"
    MAIW_TARGET_HOST="$MAIW_I_HOST"
    MAIW_TARGET_BASE_URL="http://127.0.0.1:${MAIW_I_PORT}"
    MAIW_TARGET_INSTANCE_ID="$MAIW_I_INSTANCE_ID"
    if [[ $want_live -eq 1 ]]; then
        local seen
        seen="$(maiw_live_instance_id "$MAIW_TARGET_BASE_URL" || true)"
        if [[ "$seen" != "$MAIW_I_INSTANCE_ID" ]]; then
            MAIW_VERIFY_REASON="port $MAIW_I_PORT does not answer as instance ${MAIW_I_INSTANCE_ID:0:8}… (/api/v1/live)"
            MAIW_TARGET_BASE_URL=""
            return 13
        fi
    fi
    return 0
}

maiw_new_instance_id() {
    if [[ -r /proc/sys/kernel/random/uuid ]]; then
        cat /proc/sys/kernel/random/uuid
    else
        "${MAIW_PYTHON:-python3}" -c 'import uuid; print(uuid.uuid4())'
    fi
}
