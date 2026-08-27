#!/usr/bin/env bash
# Run the MAIW CORE CI test suite (no running services required).
#
# Usage:
#   ./scripts/testing/run_core_ci.sh [extra pytest args]
#
# Example:
#   ./scripts/testing/run_core_ci.sh -x -v

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${REPO_ROOT}"

exec python -m pytest tests/unit/ tests/contract/ tests/mcp/ \
    --ignore=tests/unit/test_all_agents.py \
    --ignore=tests/unit/test_basic.py \
    --ignore=tests/unit/test_nvidia_llm.py \
    --ignore=tests/unit/test_caching_demo.py \
    --ignore=tests/unit/test_response_quality_demo.py \
    --ignore=tests/unit/test_mcp_integrated_planner_graph.py \
    --ignore=tests/unit/test_chunking_demo.py \
    --ignore=tests/unit/test_db_connection.py \
    --ignore=tests/unit/test_enhanced_retrieval.py \
    --ignore=tests/unit/test_evidence_scoring_demo.py \
    --ignore=tests/unit/test_mcp_system.py \
    --ignore=tests/unit/test_guardrails.py \
    --ignore=tests/unit/test_guardrails_sdk.py \
    --ignore=tests/unit/test_mcp_planner_integration.py \
    --ignore=tests/unit/test_nvidia_integration.py \
    --ignore=tests/unit/test_document_action_tools.py \
    --ignore=tests/unit/test_document_pipeline.py \
    --ignore=tests/unit/test_embedding.py \
    --ignore=tests/unit/test_reasoning_evaluation.py \
    --ignore=tests/unit/test_prompt_injection_protection.py \
    --ignore=tests/unit/test_prompt_injection_simple.py \
    "$@"
