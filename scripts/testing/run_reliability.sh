#!/usr/bin/env bash
# Run the MAIW Phase 10E reliability test suite (no running services required).
#
# Usage:
#   ./scripts/testing/run_reliability.sh [extra pytest args]
#
# Example:
#   ./scripts/testing/run_reliability.sh -v -k "F06"

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${REPO_ROOT}"

exec python -m pytest tests/unit/reliability/ "$@"
