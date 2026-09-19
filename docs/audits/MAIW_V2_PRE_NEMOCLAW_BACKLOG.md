# MAIW v2 — Pre-NemoClaw Deferred Backlog

**Created:** 2026-09-19 (Phase 19B stabilization)
**Status:** Intentional deferrals — NOT bugs, NOT blockers

This document captures items that were identified during the 19B audit
but explicitly deferred because they are either:
- Out of scope for a stabilization phase
- NemoClaw candidates
- Future optimization work
- Legacy code that is isolated from the v2 critical path

---

## NemoClaw Candidates (Phase 19C+)

| ID | Item |
|----|------|
| NC-001 | Add NemoClaw runtime sandbox boundary around AgentRuntime execution |
| NC-002 | OpenShell isolation for MCP server processes |
| NC-003 | Runtime capability allowlist enforced at OS/container level |
| NC-004 | Cross-runtime execution tracing for NemoClaw boundary events |

---

## Legacy Code Cleanup (Future)

| ID | Item | Notes |
|----|------|-------|
| LC-001 | `src/api/graphs/mcp_integrated_planner_graph.py` — pre-v2 planner | Still mounted via `chat_router` in v2 app; requires careful decoupling |
| LC-002 | `src/api/agents/document/action_tools.py` — bare `except:` clause at line 1993 | Pre-v2 document agent code |
| LC-003 | `src/api/agents/document/models/document_models.py` — Pydantic V1 `@validator` | Pre-v2 document models |
| LC-004 | `test_chunking_demo.py`, `test_db_connection.py`, `test_enhanced_retrieval.py`, `test_evidence_scoring_demo.py` — fail to collect due to asyncpg | Pre-v2 test files; full removal requires confirming no overlap with v2 paths |
| LC-005 | `test_mcp_system.py` — fails to collect (nemoguardrails + asyncpg chain) | Pre-v2 MCP system test |

---

## Future Documentation

| ID | Item |
|----|------|
| FD-001 | `docs/developer/SOP_DEVELOPMENT.md` — step-by-step guide for writing a new SOP |
| FD-002 | `docs/developer/PHASE_15_COPILOT_ARCHITECTURE.md` — rename to remove phase reference |
| FD-003 | `docs/developer/PHASE_15_COPILOT_INTEGRATION.md` — rename to remove phase reference |
| FD-004 | Architecture diagram in README — update to reflect Deep Agents Runtime |

---

## Future Performance Optimization

| ID | Item |
|----|------|
| FP-001 | `OperationalContextSnapshot` — consider lazy loading for large graphs |
| FP-002 | Copilot context assembly — profile and optimize for >1000-entity DataPacks |
| FP-003 | Model Lab artifact loading — add disk caching to avoid repeated JSON parse |

---

## Future Security Hardening

| ID | Item |
|----|------|
| FS-001 | Add bearer token auth to production API endpoints (currently unauthenticated) |
| FS-002 | Rate limiting on Copilot `/turn` endpoint |
| FS-003 | Audit log for all governance approval decisions |

---

## Future Test Improvements

| ID | Item |
|----|------|
| FT-001 | Integration tests for full Copilot ASK → ANALYZE → ACT → Govern → Observe flow |
| FT-002 | End-to-end test for DeepAgentsRuntime with real deepagents graph invocation |
| FT-003 | Property-based tests for DataPack determinism across seeds |
| FT-004 | Load tests for concurrent Copilot turns |

---

## Future UI/UX

| ID | Item |
|----|------|
| FU-001 | Operator reliability dashboard improvements |
| FU-002 | WORLD graph visualization — dynamic layout for large graphs |
| FU-003 | Model Lab — side-by-side model comparison view |

---

## Research / Investigation

| ID | Item |
|----|------|
| FR-001 | Evaluate whether `mcp` official Python SDK can replace MAIW custom MCP client |
| FR-002 | Adaptive routing in ModelGateway (post-NemoClaw) |
| FR-003 | Persistent agent state store (replace in-memory AgentTaskState) |

---

*Last updated: MAIW v2 pre-NemoClaw baseline (Phase 19B)*
