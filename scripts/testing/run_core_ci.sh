#!/usr/bin/env bash
# Run the MAIW CORE CI test suite (no running services required): the same
# two pytest invocations as the "Run Python tests" and "Run maiw-world
# package tests" steps of .github/workflows/ci-cd.yml, without coverage.
# docs/architecture/TEST_STRATEGY.md explains the scope and the exclusions;
# tests/api/test_ci_test_scope.py keeps the three in step.
#
# Usage:
#   ./scripts/testing/run_core_ci.sh [extra pytest args for the main run]
#
# Example:
#   ./scripts/testing/run_core_ci.sh -x -v

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${REPO_ROOT}"

python -m pytest tests/unit tests/contract tests/mcp tests/api packages/maiw-agents/tests \
    apps/api/tests apps/api/maiw_api/demo/tests tests/demo \
    --timeout=120 \
    --ignore=tests/unit/test_mcp_integrated_planner_graph.py \
    --ignore=tests/unit/test_mcp_system.py \
    --ignore=tests/unit/test_guardrails_sdk.py \
    --ignore=tests/unit/test_guardrails.py \
    --ignore=tests/unit/test_all_agents.py \
    --ignore=tests/unit/test_basic.py \
    --ignore=tests/unit/test_db_connection.py \
    --ignore=tests/unit/test_enhanced_retrieval.py \
    --ignore=tests/unit/test_mcp_planner_integration.py \
    --ignore=tests/unit/test_document_pipeline.py \
    --ignore=tests/unit/test_document_action_tools.py \
    --ignore=tests/unit/test_nvidia_integration.py \
    --ignore=tests/unit/test_nvidia_llm.py \
    --ignore=tests/unit/test_chunking_demo.py \
    --ignore=tests/unit/test_caching_demo.py \
    --ignore=tests/unit/test_response_quality_demo.py \
    --ignore=tests/unit/test_evidence_scoring_demo.py \
    --ignore=tests/unit/test_embedding.py \
    --ignore=tests/unit/test_reasoning_evaluation.py \
    --ignore=tests/unit/test_prompt_injection_protection.py \
    --ignore=tests/unit/test_prompt_injection_simple.py \
    "$@"

# packages/maiw-world/tests is a package named "tests"; it cannot be
# collected in the same process as the repository's tests/ package.
exec python -m pytest packages/maiw-world/tests --timeout=120
