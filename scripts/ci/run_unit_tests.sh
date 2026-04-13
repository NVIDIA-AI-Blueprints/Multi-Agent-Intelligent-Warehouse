#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Run unit tests suitable for CI (no live DB, no live NVIDIA API, no stale planner mocks).
# Install first: pip install -r requirements-test.txt
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-test}"
export POSTGRES_USER="${POSTGRES_USER:-warehouse}"
export POSTGRES_DB="${POSTGRES_DB:-warehouse}"
export DB_HOST="${DB_HOST:-localhost}"
export DB_PORT="${DB_PORT:-5435}"
export NVIDIA_API_KEY="${NVIDIA_API_KEY:-test-ci-key}"

# Excluded modules: live APIs/LLM, DB, stale mocks, or >120s without services.
exec python -m pytest tests/unit \
  --timeout=120 \
  --ignore=tests/unit/test_mcp_integrated_planner_graph.py \
  --ignore=tests/unit/test_migration_system.py \
  --ignore=tests/unit/test_db_connection.py \
  --ignore=tests/unit/test_document_pipeline.py \
  --ignore=tests/unit/test_nvidia_integration.py \
  --ignore=tests/unit/test_nvidia_llm.py \
  --ignore=tests/unit/test_embedding.py \
  --ignore=tests/unit/test_mcp_system.py \
  --ignore=tests/unit/test_enhanced_retrieval.py \
  --ignore=tests/unit/test_all_agents.py \
  "$@"
