# Phase 11 §1 — Developer Journey Audit

**Date:** 2026-08-27  
**Auditor:** Phase 11 automated audit  
**Branch baseline:** `feat/phase-11-devex-demo-validation` (from `nvidia/main` at `95bf0fa`)  
**Audit scope:** Clone → configure → install → start backend → start MCP servers → start frontend → enable demo mode → run Scenario 001 → run reliability tests

---

## Friction Table

| # | Step | Current behavior | Friction | Hidden assumption | Improvement |
|---|------|-----------------|----------|-------------------|-------------|
| 1 | **Clone** | `git clone https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse.git` | README links to correct repo. No mention of Git LFS, depth, or submodules. | Assumes developer knows whether assets require LFS. | State explicitly that LFS is not required. |
| 2 | **Configure: copy .env** | `cp .env.example .env` — documented in README | `.env.example` has NO `MAIW_DEMO_MODE` variable. Developer who wants demo mode has no indication this flag exists. | That the developer will read `scripts/start_demo_mode.sh` to discover the flag. | Add `MAIW_DEMO_MODE=false` to `.env.example` under a `# DEMO MODE` section. |
| 3 | **Configure: frontend env** | No `.env` file exists in `src/ui/web/`. Frontend reads `REACT_APP_*` from shell or a `.env` file in that directory. | `REACT_APP_FAULT_INJECTION_ENABLED`, `REACT_APP_API_URL`, `REACT_APP_WAREHOUSE_ID` are all undocumented. The fault injection panel is silently hidden unless `REACT_APP_FAULT_INJECTION_ENABLED=true` is set, with no explanation anywhere. | Developer reads CommandCenter.tsx source to find these variables. | Create `src/ui/web/.env.example` with all three REACT_APP vars documented. |
| 4 | **Install Python: workspace packages** | README lists 7 separate `pip install -e packages/...` commands | A developer who misses any one of these will get cryptic `ModuleNotFoundError` at runtime. `setup_environment.sh` installs `requirements.txt` only — does NOT install workspace packages. `uv sync` shown as alternative but workspace support depends on pyproject.toml config. | Developer reads all 7 lines and runs them in order. | Provide a one-liner: `pip install -r requirements.txt $(find packages -maxdepth 1 -mindepth 1 -type d \| sed 's/^/-e /')` or a `scripts/install_packages.sh`. |
| 5 | **Install Node** | `cd src/ui/web && npm install` — documented in README | Directory path is buried in a mid-document section. `start_frontend.sh` has wrong path hint in its error message (`src/src/ui/web`). | Developer finds the UI directory without guidance. | Make `npm install` step explicit in Quick Start with the full path. |
| 6 | **Start backend (demo)** | `./scripts/start_demo_mode.sh` | Script works correctly. BUT it references `kill $(cat /tmp/maiw-demo.pid)` in its header comment — this file is never actually written. Developer who tries to use that kill command gets an error. | Developer uses Ctrl-C. | Either write the PID file or remove the incorrect comment. |
| 7 | **Start backend (demo)** | `start_demo_mode.sh` prints port and scenario list | No preflight check: does not verify Python venv exists, doesn't check NVIDIA_API_KEY is set, doesn't confirm required packages are installed. | venv already set up with all packages installed. | Add a `scripts/check_demo_environment.sh` preflight that verifies these and prints a clean readiness summary. |
| 8 | **Start MCP servers** | Documented in `## MCP Servers` section | The "Quick Start" section and "Running MAIW" section say nothing about whether MCP servers are needed for demo mode. They aren't — demo mode uses `SimulationProviders` — but this is never stated. Developer may spend time trying to start 4 MCP servers before the demo will work. | Developer knows demo mode bypasses MCP. | Add a note in `start_demo_mode.sh` and Quick Start: "MCP servers are NOT required for demo mode." |
| 9 | **Start frontend** | `cd src/ui/web && npm start` (starts on port 3001) | `start_frontend.sh` prints "Backend API should be running at: http://localhost:8002" — but the proxy (`setupProxy.js`) targets port 8001. This mismatch will confuse anyone who reads the script output. | Developer checks `setupProxy.js` directly. | Fix `start_frontend.sh` port hint to say 8001. |
| 10 | **Enable demo mode: backend** | Set `MAIW_DEMO_MODE=true` before uvicorn, or use `start_demo_mode.sh` | This env var is not in `.env.example`. README's "Running MAIW" section never mentions it. The only documentation is inside `start_demo_mode.sh`'s comments. | Developer discovers the script independently. | Document `MAIW_DEMO_MODE` in `.env.example` and Quick Start. |
| 11 | **Enable demo mode: fault injection** | Set `REACT_APP_FAULT_INJECTION_ENABLED=true` in environment before `npm start` | Completely undocumented. Not in `.env.example`, not in README, not in any guide. Panel is silently hidden. | Developer reads source code. | Add to `src/ui/web/.env.example` and document in demo runbook. |
| 12 | **Select first scenario** | Demo Control Bar: select scenario, click START | No guidance on which scenario to use first. Five scenarios available. The recommended entry point (`labor_constraint_wave_risk`) is the most instructive but not identified as "recommended first". | Developer guesses or reads phase docs. | Mark `labor_constraint_wave_risk` as the recommended first scenario in UI and runbook. |
| 13 | **Run reliability tests** | Long pytest command with 15 `--ignore` flags | Complex command is hard to remember, easy to run incorrectly. No single script wraps "run CORE CI". Baseline count mentioned in README is `528 passed` (Phase 9A) but actual baseline is now higher (Phase 10E: 528 CORE + 388 reliability). | Developer copies the full pytest command from README. | Create `scripts/testing/run_core_ci.sh` and `scripts/testing/run_reliability.sh` wrappers. |
| 14 | **Understand the pipeline** | README has Architecture section with table | No architecture map showing how packages relate + which files to edit for which concern. Developer wanting to add a scenario must discover that scenarios live in `apps/api/maiw_api/routers/demo.py` and simulation in `apps/api/maiw_api/simulation/`. | Developer reads the code. | Add `docs/developer/GETTING_STARTED.md` with a codebase map. |
| 15 | **Extend: add a scenario** | No documentation | No guide exists for adding a new scenario, domain capability, provider, agent, or skill. | Developer infers from existing code. | Create `docs/developer/ADDING_A_SCENARIO.md` through `ADDING_AN_AGENT_OR_SKILL.md`. |

---

## Summary: Highest-Impact Frictions

In priority order (most blockers first):

1. **`MAIW_DEMO_MODE` missing from `.env.example`** — developer cannot discover demo mode without script-diving
2. **`REACT_APP_FAULT_INJECTION_ENABLED` entirely undocumented** — fault injection panel permanently invisible
3. **No `scripts/check_demo_environment.sh`** — first run silently fails if packages not installed
4. **`start_frontend.sh` wrong port hint (8002 vs 8001)** — generates visible confusion
5. **Stale `/tmp/maiw-demo.pid` comment** — kill command doesn't work
6. **MCP servers NOT required for demo** — never stated, wastes developer time
7. **No single-command Python workspace install** — 7-step manual process, easy to miss one
8. **No developer extension guides** — `docs/developer/` directory doesn't exist
9. **No demo runbook** — `docs/demo/` directory doesn't exist
10. **`labor_constraint_wave_risk` not identified as the recommended first scenario**

---

## What was NOT broken

- `start_demo_mode.sh` correctly sets `MAIW_DEMO_MODE=true` and starts on port 8001
- Frontend proxy correctly targets port 8001 (`setupProxy.js`)
- Frontend starts on port 3001 and UI discovers demo mode from the API (no frontend env var needed for demo mode itself)
- README Prerequisites list Python 3.11+, PostgreSQL, NVIDIA API key — all correct
- Docker Compose path correctly copies `.env.example` to `deploy/compose/.env`
- CORE CI test command is correct (just long)
