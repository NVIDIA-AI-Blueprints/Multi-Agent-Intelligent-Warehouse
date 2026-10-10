#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# scripts/setup/reference_db.sh — the reference deployment's Postgres/TimescaleDB
# (v2.0.1 round 2, NEW-P1-02 §20).
#
#   bash scripts/setup/reference_db.sh up       start + load schema + verify
#   bash scripts/setup/reference_db.sh status   health check (SELECT 1 + schema)
#   bash scripts/setup/reference_db.sh down     remove THIS container (only if
#                                               it carries this script's label)
#
# Configuration (from .env via scripts/lib/load_env.sh — the same values the
# app's data path uses):
#   MAIW_DB_CONTAINER   docker container name (REQUIRED; unique per host)
#   PGHOST / PGPORT     where the app connects (PGHOST must be local: 127.0.0.1)
#   POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB
#   MAIW_DB_IMAGE       default timescale/timescaledb:2.15.2-pg16
#
# Schema: data/postgres/*.sql are mounted as /docker-entrypoint-initdb.d and
# applied by the image on first start of an empty data directory.
#
# Safety: never touches a container it did not create (label
# maiw.reference-db=<container name>), and refuses to bind a port that is
# already in use.
# ---------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd -P)"
# shellcheck source=../lib/load_env.sh
source "$PROJECT_ROOT/scripts/lib/load_env.sh"
maiw_load_env "$PROJECT_ROOT"
maiw_require_vars MAIW_DB_CONTAINER PGPORT POSTGRES_PASSWORD

ACTION="${1:-status}"
IMAGE="${MAIW_DB_IMAGE:-timescale/timescaledb:2.15.2-pg16}"
PGHOST="${PGHOST:-127.0.0.1}"
DB_USER="${POSTGRES_USER:-warehouse}"
DB_NAME="${POSTGRES_DB:-warehouse}"
LABEL="maiw.reference-db=${MAIW_DB_CONTAINER}"

_ours() {
    docker inspect -f '{{ index .Config.Labels "maiw.reference-db" }}' "$MAIW_DB_CONTAINER" 2>/dev/null \
        | grep -qx "$MAIW_DB_CONTAINER"
}

_verify() {
    docker exec "$MAIW_DB_CONTAINER" pg_isready -U "$DB_USER" -d "$DB_NAME" >/dev/null 2>&1 || return 1
    local has
    has=$(PGPASSWORD="$POSTGRES_PASSWORD" docker exec -e PGPASSWORD "$MAIW_DB_CONTAINER" \
        psql -U "$DB_USER" -d "$DB_NAME" -tAc "select to_regclass('public.equipment_assets') is not null" 2>/dev/null || true)
    [[ "$has" == "t" ]]
}

case "$ACTION" in
    up)
        if docker inspect "$MAIW_DB_CONTAINER" >/dev/null 2>&1; then
            if ! _ours; then
                echo "ERROR: container '$MAIW_DB_CONTAINER' exists and was not created by this script — refusing." >&2
                exit 1
            fi
            docker start "$MAIW_DB_CONTAINER" >/dev/null
            echo "Reference DB container '$MAIW_DB_CONTAINER' started (existing)."
        else
            case "$PGHOST" in
                127.0.0.1|localhost) ;;
                *) echo "ERROR: PGHOST=$PGHOST is not local; this script only provisions a local DB." >&2; exit 1 ;;
            esac
            if (exec 3<>"/dev/tcp/127.0.0.1/$PGPORT") 2>/dev/null; then
                echo "ERROR: 127.0.0.1:$PGPORT is already in use — choose a free PGPORT in .env." >&2
                exit 1
            fi
            docker run -d --name "$MAIW_DB_CONTAINER" --label "$LABEL" \
                -e POSTGRES_USER="$DB_USER" -e POSTGRES_PASSWORD -e POSTGRES_DB="$DB_NAME" \
                -p "127.0.0.1:${PGPORT}:5432" \
                -v "$PROJECT_ROOT/data/postgres:/docker-entrypoint-initdb.d:ro" \
                "$IMAGE" >/dev/null
            echo "Reference DB container '$MAIW_DB_CONTAINER' created on 127.0.0.1:$PGPORT ($IMAGE)."
        fi
        echo "Waiting for the database and schema (up to 120s)..."
        for _ in $(seq 1 60); do
            if _verify; then
                echo "Reference DB READY: 127.0.0.1:$PGPORT/$DB_NAME (SELECT 1 ok, schema loaded)"
                exit 0
            fi
            sleep 2
        done
        echo "ERROR: database not ready / schema not loaded within 120s (docker logs $MAIW_DB_CONTAINER)" >&2
        exit 1
        ;;
    status)
        if _verify; then
            echo "Reference DB READY: $MAIW_DB_CONTAINER 127.0.0.1:$PGPORT/$DB_NAME"
            exit 0
        fi
        echo "Reference DB NOT READY: $MAIW_DB_CONTAINER" >&2
        exit 1
        ;;
    down)
        if ! docker inspect "$MAIW_DB_CONTAINER" >/dev/null 2>&1; then
            echo "No container '$MAIW_DB_CONTAINER'."
            exit 0
        fi
        if ! _ours; then
            echo "ERROR: container '$MAIW_DB_CONTAINER' was not created by this script — refusing to remove it." >&2
            exit 1
        fi
        docker rm -f "$MAIW_DB_CONTAINER" >/dev/null
        echo "Reference DB container '$MAIW_DB_CONTAINER' removed."
        ;;
    *)
        echo "usage: $0 up|status|down" >&2
        exit 2
        ;;
esac
