# MAIW Legacy File Audit
**Phase:** 19C.2 — Repository Truth & Legacy Cleanup  
**Date:** 2026-09-19  
**Branch:** `feat/phase-19c2-legacy-audit`  
**Auditor:** Claude Sonnet 4.6 (automated + engineering review)

---

## Executive Summary

Audited 100+ files across `docs/`, `notebooks/`, `scripts/`, and `src/`. Found 26 files requiring
historical labelling, 2 requiring targeted content updates, and 0 safe deletions. No secrets
exposure found. No current (authoritative) doc contradicts MAIW v2 architecture post-cleanup.

Key findings:
- **25 docs** had historical banners added (migration plans, gap analyses, old MCP implementation
  docs, phase-specific milestone docs, forecasting phase completions).
- **1 doc** (`MCP_V2_ARCHITECTURE.md`) received a targeted update note instead of a full
  historical banner because the README links to it as a primary reference and its MCP SDK
  architecture remains current; only the `ActionProposal` package location was stale.
- **`PACKAGE_OWNERSHIP.md`** got both a historical banner and an inline correction clarifying
  that `ActionProposal` moved from `maiw-mcp/contracts/` to `maiw-decision` (WS1).
- **`COMMAND_CENTER_V2.md`** had two stale "Phase 10" references cleaned up.
- The `src/` tree (218 Python files) is **actively imported** by `apps/api/maiw_api/` — it is
  not dead legacy code.
- `notebooks/setup/complete_setup_guide.ipynb` already had a legacy banner from Phase 19C.1 work.

---

## Audit Method

1. Inventoried all files in `docs/`, `notebooks/`, `scripts/`, root markdown files.
2. Ran all required grep patterns from the audit spec across non-generated files.
3. Read headers and key sections of all `docs/architecture/` files (70+ files).
4. Checked production imports from `src/` to verify it is not dead code.
5. Verified package locations for `ActionProposal` vs. PACKAGE_OWNERSHIP.md claims.
6. Applied historical banners using consistent template with correct relative links.

---

## Classification Definitions

| Code | Meaning |
|------|---------|
| CURRENT | Still correct and authoritative — no change required |
| UPDATE | Still useful but stale terminology or paths — updated in this audit |
| HISTORICAL | Valuable engineering record but not authoritative today — historical banner added |
| DELETE | Obsolete, duplicated, misleading — deleted |
| UNKNOWN | Cannot determine without deeper investigation |

---

## Classification Table

| File | Classification | Issue | Action |
|------|----------------|-------|--------|
| docs/architecture/ARCHITECTURE.md | CURRENT | Authoritative MAIW v2 doc | No change |
| docs/architecture/AGENT_RUNTIME.md | CURRENT | Authoritative MAIW v2 doc | No change |
| docs/architecture/GOVERNANCE.md | CURRENT | Authoritative MAIW v2 doc | No change |
| docs/architecture/MODEL_GATEWAY.md | CURRENT | Authoritative, includes 19C.1 rewrite | No change |
| docs/architecture/WAREHOUSE_WORLD.md | CURRENT | Authoritative MAIW v2 doc | No change |
| docs/architecture/DECISION_ENGINE.md | CURRENT | Accurate description of DecisionEngine | No change |
| docs/architecture/WAREHOUSE_STATE.md | CURRENT | Accurate WarehouseStateProvider docs | No change |
| docs/architecture/TEST_STRATEGY.md | CURRENT | Accurate CORE CI command | No change |
| docs/architecture/CAPABILITY_MATRIX.md | CURRENT | Phase 8 label but capabilities still accurate | No change |
| docs/architecture/DEPENDENCY_BOUNDARIES.md | CURRENT | MCP SDK version boundary record | No change |
| docs/architecture/RUNTIME_EXECUTION_FLOW.md | CURRENT | Phase 6B label but STATE→REASON→PROPOSE→DECIDE→EXECUTE→MCP flow is still current | No change |
| docs/architecture/COMMAND_CENTER_V2.md | UPDATE | Two stale "Phase 10" references | Cleaned inline references |
| docs/architecture/guardrails-implementation.md | CURRENT | Historical banner already added in 19C.1 | No change |
| docs/architecture/MCP_V2_ARCHITECTURE.md | UPDATE | Stale ActionProposal package location and test count | Added update note; removed historical banner (README links here as primary MCP ref) |
| docs/architecture/PACKAGE_OWNERSHIP.md | HISTORICAL + UPDATE | Phase 8; ActionProposal package location wrong (maiw-mcp vs maiw-decision) | Historical banner + inline correction |
| docs/architecture/MIGRATION_PLAN.md | HISTORICAL | Phases 0-12 modernization plan, pre-v2 | Historical banner |
| docs/architecture/MODERNIZATION_GAP_ANALYSIS.md | HISTORICAL | Pre-v2 gap analysis at commit e33ed69 | Historical banner |
| docs/architecture/CURRENT_ARCHITECTURE.md | HISTORICAL | Architecture snapshot at commit e33ed69 | Historical banner |
| docs/architecture/MCP_CUSTOM_IMPLEMENTATION.md | HISTORICAL | Incorrectly claims "no official MCP package" — pre-SDK | Historical banner |
| docs/architecture/MCP_CURRENT_IMPLEMENTATION.md | HISTORICAL | Pre-SDK audit (Phase 2 pre-work) | Historical banner |
| docs/architecture/MCP_V2_MIGRATION_PLAN.md | HISTORICAL | Migration plan to SDK v2, now complete; has stale `maiw_mcp.contracts` import | Historical banner |
| docs/architecture/mcp-migration-guide.md | HISTORICAL | Pre-SDK migration guide | Historical banner |
| docs/architecture/mcp-deployment-guide.md | HISTORICAL | Pre-SDK deployment guide | Historical banner |
| docs/architecture/mcp-api-reference.md | HISTORICAL | Pre-SDK API reference | Historical banner |
| docs/architecture/mcp-integration.md | HISTORICAL | Pre-SDK integration doc | Historical banner |
| docs/architecture/mcp-rollback-strategy.md | HISTORICAL | Pre-SDK rollback strategy | Historical banner |
| docs/architecture/mcp-gpu-acceleration-guide.md | HISTORICAL | GPU/cuVS guide from early phase | Historical banner |
| docs/architecture/MODEL_MIGRATION_PLAN.md | HISTORICAL | Model migration planning (Llama→Nemotron) from pre-v2 | Historical banner |
| docs/architecture/API_MIGRATION_PLAN.md | HISTORICAL | Phase 9B API migration plan | Historical banner |
| docs/architecture/PHASE2_IMPLEMENTATION_STATUS.md | HISTORICAL | Phase 2 document pipeline status | Historical banner |
| docs/architecture/PHASE2_PERFORMANCE_PLAN.md | HISTORICAL | Phase 2 performance optimization plan | Historical banner |
| docs/architecture/REASONING_ENGINE_OVERVIEW.md | HISTORICAL | Pre-v2 reasoning engine docs (src/api/services/reasoning/); DeepAgents SDK is the v2 direction per Phase 19A | Historical banner |
| docs/architecture/diagrams/warehouse-operational-assistant.md | HISTORICAL | Phase 1-3 Mermaid diagram with stale architecture | Historical banner |
| docs/architecture/diagrams/warehouse-assistant-architecture.png | HISTORICAL | Visual diagram from earlier phase; canonical is maiw-runtime-pipeline.png | No action needed (binary PNG; referenced only from historical docs) |
| docs/architecture/diagrams/maiw-runtime-pipeline.png | CURRENT | Canonical architecture diagram (added in 19C.4) | No change |
| docs/architecture/adr/001-database-migration-system.md | CURRENT | ADR still valid | No change |
| docs/architecture/adr/002-nvidia-nims-integration.md | CURRENT | ADR still valid | No change |
| docs/architecture/adr/003-hybrid-rag-architecture.md | HISTORICAL | Phase 3 references but accepted ADR; not misleading | No change (ADR status preserved) |
| docs/architecture/CHANGELOG_AUTOMATION.md | CURRENT | Still describes semantic-release setup | No change |
| docs/architecture/database-migrations.md | CURRENT | Describes migration system still in use | No change |
| docs/forecasting/PHASE1_PHASE2_COMPLETE.md | HISTORICAL | Phase 1&2 RAPIDS forecasting milestone | Historical banner |
| docs/forecasting/PHASE3_4_5_COMPLETE.md | HISTORICAL | Phase 3-5 RAPIDS milestone; had "Ready for Production" claim | Historical banner |
| docs/forecasting/RAPIDS_IMPLEMENTATION_PLAN.md | HISTORICAL | Planning doc for RAPIDS integration | Historical banner |
| docs/forecasting/RAPIDS_SETUP.md | CURRENT | GPU setup guide still relevant for RAPIDS | No change |
| docs/forecasting/README.md | CURRENT | Forecasting feature overview | No change |
| docs/forecasting/REORDER_RECOMMENDATION_EXPLAINER.md | CURRENT | Explains reorder recommendation logic | No change |
| docs/developer/GETTING_STARTED.md | CURRENT | "pre-Phase 14 setup path" note is helpful context, not misleading | No change |
| docs/developer/ADDING_A_CAPABILITY.md | CURRENT | Describes current MCP tool + Skill pattern | No change |
| docs/developer/ADDING_AN_AGENT_OR_SKILL.md | CURRENT | Describes current agent structure | No change |
| docs/developer/ADDING_A_PROVIDER.md | CURRENT | Provider extension guide | No change |
| docs/developer/ADDING_A_SCENARIO.md | CURRENT | Scenario extension guide | No change |
| docs/developer/EVALUATION.md | CURRENT | Counterfactual + reliability evaluation docs | No change |
| docs/developer/MODEL_DEPLOYMENT.md | CURRENT | Model deployment modes | No change |
| docs/developer/MODEL_GATEWAY_EVALUATION.md | CURRENT | Model Lab evaluation docs (Phase 18F) | No change |
| docs/developer/PHASE_15_COPILOT_ARCHITECTURE.md | CURRENT | Authoritative Copilot architecture (supersedes COPILOT_INTEGRATION) | No change |
| docs/developer/PHASE_15_COPILOT_INTEGRATION.md | HISTORICAL | Phase 14G stub — superseded by PHASE_15_COPILOT_ARCHITECTURE.md | Historical banner |
| docs/developer/WAREHOUSE_WORLD_EXPLORER.md | CURRENT | Phase 17 World Explorer developer reference | No change |
| docs/developer/WAREHOUSE_WORLD_MODEL.md | CURRENT | Warehouse World developer reference | No change |
| docs/demo/DEMO_ACCEPTANCE.md | CURRENT | Current demo acceptance criteria | No change |
| docs/demo/DEMO_RUNBOOK.md | CURRENT | Current demo runbook | No change |
| docs/demo/PHASE_14G_UI_WORKFLOW.md | HISTORICAL | Phase 14G-specific demo workflow | Historical banner |
| docs/audits/MAIW_V2_PRE_NEMOCLAW_BACKLOG.md | CURRENT | Intentional audit artifact | No change |
| docs/audits/MAIW_V2_PRE_NEMOCLAW_RELEASE_AUDIT.md | CURRENT | Intentional audit artifact | No change |
| docs/audits/PHASE_18H_AGENT_GOVERNANCE_BASELINE.md | CURRENT | Intentional audit artifact | No change |
| docs/audits/PHASE_19A_11_OWNERSHIP_MATRIX.md | CURRENT | Intentional audit artifact | No change |
| docs/audits/PHASE_19A_DEEP_AGENTS_COMPATIBILITY.md | CURRENT | Intentional audit artifact | No change |
| docs/audits/PHASE_19A_DEEP_AGENTS_POC.md | CURRENT | Intentional audit artifact | No change |
| docs/api/README.md | CURRENT | API overview — still accurate | No change |
| docs/deployment/README.md | CURRENT | Redirect to DEPLOYMENT.md | No change |
| docs/GLOSSARY.md | CURRENT | Canonical terminology | No change |
| docs/SOFTWARE_INVENTORY.md | UNKNOWN | Last updated 2025-12-20; may be stale but auto-generated; note it separately | See Remaining section |
| docs/REPOSITORY_HEALTH_REPORT.md | HISTORICAL | Snapshot from 2026-01-20 | No change (not linked from onboarding paths) |
| docs/secrets.md | CURRENT | Dev credentials with production warnings — no actual secrets | No change |
| docs/iot-integration.md | CURRENT | IoT integration guide | No change |
| docs/wms-integration.md | CURRENT | WMS integration guide | No change |
| docs/dependabot-configuration.md | CURRENT | Dependabot config explanation | No change |
| docs/configuration/LLM_PARAMETERS.md | CURRENT | LLM parameter reference | No change |
| docs/security/*.md | CURRENT | Security advisories and mitigations | No change |
| docs/retrieval/*.md | CURRENT | Retrieval architecture docs | No change |
| notebooks/MAIW_v2_Getting_Started.ipynb | CURRENT | Canonical onboarding notebook | No change |
| notebooks/setup/complete_setup_guide.ipynb | HISTORICAL | Legacy path; already has banner from 19C.1 | No change (already done) |
| notebooks/setup/maiw_v2_setup.ipynb | CURRENT | v2 setup notebook — current canonical | No change |
| notebooks/setup/TESTING_GUIDE.md | CURRENT | Testing guide for setup notebook | No change |
| notebooks/setup/VENV_BEST_PRACTICES.md | CURRENT | Venv guidance | No change |
| README.md | CURRENT | Rewritten in Phase 19C | No change |
| DEPLOYMENT.md | CURRENT | Updated in Phase 19C.1 | No change |
| CONTRIBUTING.md | CURRENT | Contribution guide | No change |
| SECURITY.md | CURRENT | Security policy | No change |
| CHANGELOG.md | CURRENT | Auto-generated | No change |
| src/ (218 Python files) | CURRENT | Actively imported by apps/api/maiw_api/ — not dead legacy code | No change |
| scripts/ | CURRENT | Utility scripts; not architecture docs | No change |

---

## Current Files

All files marked CURRENT above. Primary authoritative sources:
- `docs/architecture/ARCHITECTURE.md` — full architecture
- `docs/architecture/AGENT_RUNTIME.md` — agent runtime
- `docs/architecture/GOVERNANCE.md` — authority boundary
- `docs/architecture/MODEL_GATEWAY.md` — model access
- `docs/architecture/WAREHOUSE_WORLD.md` — warehouse world
- `docs/architecture/DECISION_ENGINE.md` — decision engine
- `README.md` — onboarding entry point
- `DEPLOYMENT.md` — deployment guide
- `notebooks/MAIW_v2_Getting_Started.ipynb` — canonical onboarding notebook

---

## Updated Files

| File | What Changed |
|------|-------------|
| `docs/architecture/COMMAND_CENTER_V2.md` | Removed stale "Phase 10" from comment; rewrote "Phase 10 deferred" to "deferred to a future release" |
| `docs/architecture/MCP_V2_ARCHITECTURE.md` | Replaced historical banner with targeted update note about ActionProposal move (WS1) and stale test count |
| `docs/architecture/PACKAGE_OWNERSHIP.md` | Added historical banner + inline correction: ActionProposal ~~maiw-mcp/contracts/~~ → maiw-decision (WS1) |

---

## Historical Files (banners added)

25 files received the standard historical banner:

**Architecture migration / planning docs:**
- `docs/architecture/MIGRATION_PLAN.md`
- `docs/architecture/MODERNIZATION_GAP_ANALYSIS.md`
- `docs/architecture/CURRENT_ARCHITECTURE.md`
- `docs/architecture/PACKAGE_OWNERSHIP.md` (also updated, see above)
- `docs/architecture/MODEL_MIGRATION_PLAN.md`
- `docs/architecture/API_MIGRATION_PLAN.md`
- `docs/architecture/PHASE2_IMPLEMENTATION_STATUS.md`
- `docs/architecture/PHASE2_PERFORMANCE_PLAN.md`
- `docs/architecture/REASONING_ENGINE_OVERVIEW.md`

**Pre-SDK MCP docs (6 files replaced by official maiw-mcp package):**
- `docs/architecture/MCP_CUSTOM_IMPLEMENTATION.md`
- `docs/architecture/MCP_CURRENT_IMPLEMENTATION.md`
- `docs/architecture/MCP_V2_MIGRATION_PLAN.md`
- `docs/architecture/mcp-migration-guide.md`
- `docs/architecture/mcp-deployment-guide.md`
- `docs/architecture/mcp-api-reference.md`
- `docs/architecture/mcp-integration.md`
- `docs/architecture/mcp-rollback-strategy.md`
- `docs/architecture/mcp-gpu-acceleration-guide.md`

**Diagrams:**
- `docs/architecture/diagrams/warehouse-operational-assistant.md`

**Forecasting milestone docs:**
- `docs/forecasting/PHASE1_PHASE2_COMPLETE.md`
- `docs/forecasting/PHASE3_4_5_COMPLETE.md`
- `docs/forecasting/RAPIDS_IMPLEMENTATION_PLAN.md`

**Phase-specific docs:**
- `docs/developer/PHASE_15_COPILOT_INTEGRATION.md` (superseded by PHASE_15_COPILOT_ARCHITECTURE.md)
- `docs/demo/PHASE_14G_UI_WORKFLOW.md`

---

## Deleted Files

None. All files with historical value have been preserved with banners.

---

## Legacy Code Findings

**`src/` tree (218 Python files)** — ACTIVE, not dead.

`apps/api/maiw_api/app.py` imports directly from `src/api/routers/*` for many router modules:
`auth`, `inventory`, `wms`, `iot`, `erp`, `scanning`, `attendance`, `reasoning`, `migration`,
`document`, `advanced_forecasting`, `training`, `chat`. Also imports from
`src/api/middleware/security_headers` and `src/api/services/monitoring/metrics`.

`apps/api/maiw_api/routers/health.py` imports `src/api/services/version`.
`apps/api/maiw_api/routers/equipment.py` imports `src/retrieval/structured/SQLRetriever`.

The `src/` tree is a **runtime dependency** of the current application. It should not be
deleted or restructured without a dedicated migration. The `PACKAGE_OWNERSHIP.md`'s intention
to move `ModelGateway` from `src/api/services/model_gateway/` to `packages/maiw-models/` has
NOT yet been completed — that code still lives in `src/`.

---

## Old Diagram Findings

| Diagram | Classification | Notes |
|---------|---------------|-------|
| `docs/architecture/diagrams/maiw-runtime-pipeline.png` | CURRENT | Added in 19C.4; canonical runtime diagram |
| `docs/architecture/diagrams/warehouse-assistant-architecture.png` | HISTORICAL | Earlier phase diagram; no references from current docs |
| `docs/architecture/diagrams/warehouse-operational-assistant.md` | HISTORICAL | Mermaid diagram with Phase 1-3 content; banner added |

---

## Old Notebooks

| Notebook | Classification | Notes |
|---------|---------------|-------|
| `notebooks/MAIW_v2_Getting_Started.ipynb` | CURRENT | Canonical onboarding |
| `notebooks/setup/maiw_v2_setup.ipynb` | CURRENT | v2 setup path |
| `notebooks/setup/complete_setup_guide.ipynb` | HISTORICAL | Pre-Phase 14 setup (PostgreSQL, Redis, Milvus, Kafka); banner added in 19C.1 |

---

## Old Config/Prompts

No agent prompt config files found that are clearly stale. All agent config is in current
`packages/maiw-agents/` structure.

---

## Security Findings

None. `docs/secrets.md` documents only development defaults with clear production warnings.
No actual credentials, tokens, or private keys found in any audited file. No disabled TLS
examples found.

---

## Remaining Intentional Historical References

The following stale terms appear **only** in intentionally historical files and are acceptable:

| Term | File | Status |
|------|------|--------|
| `Phase 3` | `docs/architecture/mcp-rollback-strategy.md` | Now has historical banner |
| `Phase 3` | `docs/forecasting/PHASE3_4_5_COMPLETE.md` | Now has historical banner |
| `Phase 14`, `Phase 15` | `docs/demo/PHASE_14G_UI_WORKFLOW.md` | Now has historical banner |
| `Phase 15` | `docs/developer/PHASE_15_COPILOT_INTEGRATION.md` | Now has historical banner |
| `Modernization` | `docs/architecture/MODERNIZATION_GAP_ANALYSIS.md` | Now has historical banner |
| `Modernization Migration Plan` | `docs/architecture/MIGRATION_PLAN.md` | Now has historical banner |
| `Ready for Production` | `docs/forecasting/PHASE3_4_5_COMPLETE.md` | Now has historical banner |
| `ActionProposal.*maiw-mcp` | `docs/architecture/MCP_V2_MIGRATION_PLAN.md` | Now has historical banner |
| `maiw_mcp.contracts` | `docs/architecture/MCP_V2_MIGRATION_PLAN.md` | Now has historical banner |
| `Chat Path (Phase 6)` | `docs/architecture/RUNTIME_EXECUTION_FLOW.md` | CURRENT doc; "Phase 6" is historical context label, not misleading |
| `DELETED (Phase 3)` | `docs/architecture/RUNTIME_EXECUTION_FLOW.md` | CURRENT doc; deletion record, accurate |

---

## Source-of-Truth Map

| Topic | Authoritative Document |
|-------|----------------------|
| Full architecture | `docs/architecture/ARCHITECTURE.md` |
| Agent runtime | `docs/architecture/AGENT_RUNTIME.md` |
| Governance + authority boundary | `docs/architecture/GOVERNANCE.md` |
| MCP interoperability | `docs/architecture/MCP_V2_ARCHITECTURE.md` (with update note) |
| ModelGateway | `docs/architecture/MODEL_GATEWAY.md` |
| Warehouse World | `docs/architecture/WAREHOUSE_WORLD.md` |
| Terminology | `docs/GLOSSARY.md` |
| Onboarding | `notebooks/MAIW_v2_Getting_Started.ipynb` |
| Deployment | `DEPLOYMENT.md` |
| ActionProposal package | `packages/maiw-decision/maiw_decision/proposal.py` |

---

## Validation

### Grep results for reserved stale terms in current (non-audit) docs

Run post-cleanup:

| Term | Hits in current docs | Status |
|------|---------------------|--------|
| `maiw-mcp/contracts` | 0 in current docs | CLEAN |
| `ActionProposal.*maiw-mcp` | 0 in current docs | CLEAN |
| `Model Adaptive Router` | 0 | CLEAN |
| `Warehouse State Provider` | 0 | CLEAN |
| `MCP Thin Protocol` | 0 | CLEAN |
| `MCP is the write plane` | 0 | CLEAN |
| `Closed-Loop Learning` | 0 | CLEAN |
| `simulated Deep Agents` | 0 | CLEAN |
| `Ready for Production` | docs/forecasting/PHASE3_4_5_COMPLETE.md | INTENTIONAL (historical banner present) |
| `Modernization Status` | 0 | CLEAN |

---

## Tests

This audit is docs-only. No code, configuration, or test files were modified. CORE CI suite
is unaffected. No test run required.

---

## Commits

- `19C.2.1` — 25 historical banners + 3 targeted doc updates
- `19C.2.2` — Audit artifact (`MAIW_LEGACY_FILE_AUDIT.md`)
