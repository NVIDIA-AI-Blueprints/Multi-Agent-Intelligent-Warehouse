# Repository Restructure Proposal

This document proposes a restructuring of the warehouse-operational-assistant repository to align with the NVIDIA AI Blueprints structure pattern, as seen in the [ai-virtual-assistant](https://github.com/NVIDIA-AI-Blueprints/ai-virtual-assistant) repository.

## Current Structure Analysis

### Current Top-Level Directories:
- `chain_server/` - FastAPI application and services
- `inventory_retriever/` - Retrieval services
- `memory_retriever/` - Memory management
- `adapters/` - External system adapters (ERP, IoT, WMS, etc.)
- `ui/` - React frontend
- `scripts/` - Utility scripts
- `data/` - Database schemas
- `docs/` - Documentation
- `helm/` - Helm charts
- `monitoring/` - Monitoring configurations
- `guardrails/` - Guardrails configuration
- `tests/` - Test files
- Root: Multiple docker-compose files, Dockerfiles, requirements.txt, etc.

## Proposed Structure

```
warehouse-operational-assistant/
├── .github/                          # GitHub workflows, templates, issue templates
│   ├── workflows/
│   ├── ISSUE_TEMPLATE/
│   └── PULL_REQUEST_TEMPLATE.md
│
├── src/                              # All source code (NEW - consolidates multiple dirs)
│   ├── api/                          # FastAPI application (from chain_server/)
│   │   ├── app.py                    # Main FastAPI app
│   │   ├── routers/                  # API route handlers
│   │   └── cli/                      # CLI commands
│   │
│   ├── agents/                       # AI agents (from chain_server/agents/)
│   │   ├── document/
│   │   ├── inventory/
│   │   ├── operations/
│   │   └── safety/
│   │
│   ├── services/                     # Core services (from chain_server/services/)
│   │   ├── auth/
│   │   ├── llm/
│   │   ├── mcp/
│   │   ├── memory/
│   │   ├── guardrails/
│   │   └── ...
│   │
│   ├── graphs/                       # LangGraph workflows (from chain_server/graphs/)
│   │
│   ├── retrieval/                    # Retrieval services (from inventory_retriever/)
│   │   ├── structured/
│   │   ├── vector/
│   │   ├── caching/
│   │   └── ...
│   │
│   ├── memory/                       # Memory services (from memory_retriever/)
│   │
│   ├── adapters/                     # External system adapters (from adapters/)
│   │   ├── erp/
│   │   ├── iot/
│   │   ├── wms/
│   │   ├── rfid_barcode/
│   │   └── time_attendance/
│   │
│   └── ui/                           # Frontend (from ui/)
│       └── web/
│
├── deploy/                           # Deployment configurations (NEW - consolidates deployment files)
│   ├── compose/                      # Docker Compose files
│   │   ├── docker-compose.yaml       # Main compose file
│   │   ├── docker-compose.dev.yaml
│   │   ├── docker-compose.monitoring.yaml
│   │   ├── docker-compose.gpu.yaml
│   │   └── docker-compose.rapids.yml
│   │
│   ├── helm/                         # Helm charts (from helm/)
│   │   └── warehouse-assistant/
│   │
│   ├── kubernetes/                   # Kubernetes manifests (if any)
│   │
│   └── scripts/                      # Deployment scripts
│       ├── deploy.sh
│       └── setup_monitoring.sh
│
├── data/                             # Data files and schemas (ENHANCED)
│   ├── postgres/                     # Database schemas (existing)
│   │   ├── migrations/
│   │   └── *.sql
│   │
│   ├── sample/                       # Sample/test data files
│   │   ├── forecasts/
│   │   └── test_documents/
│   │
│   └── config/                       # Configuration files
│       └── guardrails/
│
├── docs/                             # Documentation (KEEP AS IS - already well organized)
│   ├── api/
│   ├── architecture/
│   ├── deployment/
│   ├── forecasting/
│   └── retrieval/
│
├── notebooks/                        # Jupyter notebooks (NEW - for analysis, demos)
│   ├── forecasting/
│   ├── retrieval/
│   └── demos/
│
├── scripts/                          # Utility scripts (REORGANIZED)
│   ├── setup/                        # Setup and initialization scripts
│   │   ├── dev_up.sh
│   │   ├── create_default_users.py
│   │   └── setup_monitoring.sh
│   │
│   ├── data/                         # Data generation scripts
│   │   ├── generate_historical_demand.py
│   │   ├── generate_synthetic_data.py
│   │   └── generate_all_sku_forecasts.py
│   │
│   ├── forecasting/                  # Forecasting scripts
│   │   ├── phase1_phase2_forecasting_agent.py
│   │   ├── phase3_advanced_forecasting.py
│   │   └── rapids_gpu_forecasting.py
│   │
│   ├── testing/                      # Test scripts
│   │   ├── test_chat_functionality.py
│   │   └── test_rapids_forecasting.py
│   │
│   └── tools/                        # Utility tools
│       ├── migrate.py
│       └── debug_chat_response.py
│
├── tests/                            # Test suite (KEEP AS IS)
│   ├── integration/
│   ├── performance/
│   └── unit/
│
├── monitoring/                       # Monitoring configurations (KEEP AS IS)
│   ├── prometheus/
│   ├── grafana/
│   └── alertmanager/
│
├── .github/                          # GitHub configuration (ENHANCED)
│   ├── workflows/                    # CI/CD workflows
│   ├── ISSUE_TEMPLATE/
│   └── PULL_REQUEST_TEMPLATE.md
│
├── Root Level Files (CLEANED UP):
│   ├── README.md
│   ├── CHANGELOG.md
│   ├── LICENSE
│   ├── requirements.txt
│   ├── pyproject.toml
│   ├── Dockerfile                    # Main Dockerfile
│   ├── Dockerfile.rapids             # RAPIDS-specific Dockerfile
│   ├── .dockerignore
│   ├── .gitignore
│   ├── .env.example
│   └── RUN_LOCAL.sh                  # Local development runner
│
└── Temporary/Test Files (TO BE CLEANED):
    ├── test_*.py                     # Move to tests/ or scripts/testing/
    ├── test_*.pdf/png/txt            # Move to data/sample/test_documents/
    ├── *_forecasts.json              # Move to data/sample/forecasts/
    └── *_results.json                # Move to data/sample/ or remove
```

## Key Changes

### 1. **Consolidate Source Code into `src/`**
   - Move `chain_server/` → `src/api/`
   - Move `inventory_retriever/` → `src/retrieval/`
   - Move `memory_retriever/` → `src/memory/`
   - Move `adapters/` → `src/adapters/`
   - Move `ui/` → `src/ui/`

### 2. **Create `deploy/` Directory**
   - Move all `docker-compose*.yaml` files → `deploy/compose/`
   - Move `helm/` → `deploy/helm/`
   - Move deployment scripts → `deploy/scripts/`

### 3. **Reorganize `scripts/`**
   - Group by purpose: `setup/`, `data/`, `forecasting/`, `testing/`, `tools/`

### 4. **Enhance `data/` Directory**
   - Keep `data/postgres/` for schemas
   - Add `data/sample/` for test data and forecasts
   - Add `data/config/` for configuration files

### 5. **Add `notebooks/` Directory**
   - For Jupyter notebooks (forecasting analysis, demos, etc.)

### 6. **Clean Root Directory**
   - Keep only essential files
   - Move test files to appropriate locations
   - Move forecast JSON files to `data/sample/forecasts/`

## Migration Strategy

### Phase 1: Create New Structure
1. Create new directories
2. Move files without modifying content
3. Update import paths incrementally

### Phase 2: Update Imports
1. Update Python imports in all files
2. Update Dockerfile paths
3. Update docker-compose file paths
4. Update CI/CD workflow paths

### Phase 3: Update Documentation
1. Update README.md with new structure
2. Update all documentation references
3. Update deployment guides

### Phase 4: Testing
1. Run all tests
2. Verify Docker builds
3. Verify deployment scripts
4. Verify local development setup

## Benefits

1. **Alignment with NVIDIA Blueprints**: Matches the structure of official NVIDIA AI Blueprints
2. **Better Organization**: Clear separation of concerns
3. **Easier Navigation**: Logical grouping of related files
4. **Professional Structure**: Industry-standard layout
5. **Scalability**: Easier to add new components
6. **Cleaner Root**: Only essential files at root level

## Potential Issues & Solutions

### Issue 1: Import Path Changes
**Solution**: Use relative imports and update `PYTHONPATH` in Dockerfiles and scripts

### Issue 2: Docker Compose File Paths
**Solution**: Update volume mounts and context paths in docker-compose files

### Issue 3: CI/CD Workflows
**Solution**: Update workflow file paths and build contexts

### Issue 4: Documentation References
**Solution**: Update all documentation to reflect new paths

## Files to Move

### Source Code (→ `src/`)
- `chain_server/` → `src/api/`
- `inventory_retriever/` → `src/retrieval/`
- `memory_retriever/` → `src/memory/`
- `adapters/` → `src/adapters/`
- `ui/` → `src/ui/`

### Deployment (→ `deploy/`)
- `docker-compose*.yaml` → `deploy/compose/`
- `helm/` → `deploy/helm/`
- `scripts/setup_monitoring.sh` → `deploy/scripts/`

### Data Files (→ `data/sample/`)
- `*_forecasts.json` → `data/sample/forecasts/`
- `test_*.pdf/png/txt` → `data/sample/test_documents/`
- `guardrails/` → `data/config/guardrails/`

### Scripts (→ `scripts/` subdirectories)
- Setup scripts → `scripts/setup/`
- Data generation → `scripts/data/`
- Forecasting → `scripts/forecasting/`
- Testing → `scripts/testing/`

## Next Steps

1. **Review this proposal** - Confirm structure meets requirements
2. **Create migration script** - Automated script to move files and update imports
3. **Test migration** - Run on a branch first
4. **Update documentation** - After migration is complete
5. **Merge to main** - After thorough testing

