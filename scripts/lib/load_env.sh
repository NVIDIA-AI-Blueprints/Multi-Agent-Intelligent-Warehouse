# shellcheck shell=bash
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# scripts/lib/load_env.sh — the ONE environment-loading mechanism for every
# MAIW reference-deployment script (preflight, start, stop, restart, status,
# smoke, qualify, reference DB / sandbox setup).  v2.0.1 round 2 (NEW-P1-02).
#
# Source it, then call maiw_load_env:
#
#     source "$SCRIPT_DIR/lib/load_env.sh"
#     maiw_load_env "$PROJECT_ROOT"
#
# Which file:
#     $MAIW_ENV_FILE if set (it must exist), otherwise $PROJECT_ROOT/.env if it
#     exists, otherwise no file (the current environment only).
#
# Precedence: a variable already exported in the calling shell wins over the
# file, so `MAIW_API_PORT=18920 bash scripts/...` overrides .env for one run.
# Every script loads the same file the same way, so preflight validates exactly
# the configuration start launches with.
#
# Parsing: KEY=VALUE lines are parsed, NOT executed (`source` would run shell
# code and treat `<`/`>` in values as redirections).  Supported forms:
#     KEY=value            (a ' #' after the value starts a comment)
#     KEY="value"  KEY='value'   (taken literally, no expansion)
#     export KEY=value
# Blank lines and lines starting with # are ignored.
#
# After loading, PYTHON_DOTENV_DISABLED=1 is exported so the Python app does not
# load a second .env of its own: this file is the single source.
#
# Nothing is ever printed except variable COUNTS and the file path.

maiw_load_env() {
    local project_root="${1:?maiw_load_env: project root required}"
    local file=""
    if [[ -n "${MAIW_ENV_FILE:-}" ]]; then
        file="$MAIW_ENV_FILE"
        if [[ ! -f "$file" ]]; then
            echo "  ERROR: MAIW_ENV_FILE=$file does not exist" >&2
            return 1
        fi
    elif [[ -f "$project_root/.env" ]]; then
        file="$project_root/.env"
    fi

    if [[ -z "$file" ]]; then
        echo "  env: no .env file (using the current environment only)"
        export PYTHON_DOTENV_DISABLED=1
        export MAIW_ENV_LOADED_FROM="(environment)"
        return 0
    fi

    local line key val lineno=0 loaded=0 kept=0 ignored=0
    while IFS= read -r line || [[ -n "$line" ]]; do
        lineno=$((lineno + 1))
        line="${line%$'\r'}"
        [[ "$line" =~ ^[[:space:]]*(#|$) ]] && continue
        if [[ ! "$line" =~ ^[[:space:]]*(export[[:space:]]+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
            ignored=$((ignored + 1))
            echo "  env: ignoring malformed line $lineno of $file" >&2
            continue
        fi
        key="${BASH_REMATCH[2]}"
        val="${BASH_REMATCH[3]}"
        # leading whitespace of the value
        val="${val#"${val%%[![:space:]]*}"}"
        if [[ "$val" =~ ^\"(.*)\"[[:space:]]*(#.*)?$ ]]; then
            val="${BASH_REMATCH[1]}"
        elif [[ "$val" =~ ^\'(.*)\'[[:space:]]*(#.*)?$ ]]; then
            val="${BASH_REMATCH[1]}"
        else
            # unquoted: strip an inline " #comment" and trailing whitespace
            if [[ "$val" =~ ^(.*[^[:space:]])?[[:space:]]+#.*$ ]]; then
                val="${BASH_REMATCH[1]}"
            elif [[ "$val" =~ ^#.*$ ]]; then
                val=""
            fi
            val="${val%"${val##*[![:space:]]}"}"
        fi
        if [[ -n "${!key+x}" ]]; then
            kept=$((kept + 1))
            continue
        fi
        export "$key=$val"
        loaded=$((loaded + 1))
    done < "$file"

    export PYTHON_DOTENV_DISABLED=1
    export MAIW_ENV_LOADED_FROM="$file"
    echo "  env: loaded $loaded variable(s) from $file ($kept already set in the shell kept, $ignored ignored)"
    return 0
}

# maiw_require_vars VAR... — fail (return 1) listing every unset/empty variable.
maiw_require_vars() {
    local missing=() var
    for var in "$@"; do
        if [[ -z "${!var:-}" ]]; then
            missing+=("$var")
        fi
    done
    if [[ ${#missing[@]} -gt 0 ]]; then
        echo "  ERROR: required variable(s) not set: ${missing[*]}" >&2
        echo "         Set them in .env (see .env.example and docs/operations/REFERENCE_DEPLOYMENT_RUNBOOK.md)." >&2
        return 1
    fi
    return 0
}
