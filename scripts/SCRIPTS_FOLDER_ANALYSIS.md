# Scripts Folder Analysis & Cleanup Report

**Generated:** 2025-01-XX  
**Status:** ✅ **CLEANUP COMPLETE**

---

## Summary

**Total Files Analyzed:** 30+ files  
**Issues Found:** 8 duplicates/overlaps, 3 outdated files, 2 organization issues  
**Actions Taken:** ✅ All cleanup completed

---

## 1. Duplicate Files (Remove or Consolidate)

### High Priority - Remove Duplicates

#### 1.1 Server Startup Scripts
- **`RUN_LOCAL.sh`** (root directory) - Uses port 8002
- **`scripts/start_server.sh`** - Uses port 8001 (standard)
- **Status:** `RUN_LOCAL.sh` is outdated, should be removed
- **Action:** Delete `RUN_LOCAL.sh`, use `scripts/start_server.sh` everywhere
- **References:** README.md, DEPLOYMENT.md already use `scripts/start_server.sh`

#### 1.2 Admin Password Scripts
- **`scripts/setup/fix_admin_password.py`** - Uses passlib (deprecated)
- **`scripts/setup/update_admin_password.py`** - Uses passlib (deprecated)
- **`scripts/setup/create_default_users.py`** - Uses bcrypt directly (current)
- **Status:** `fix_admin_password.py` and `update_admin_password.py` are outdated
- **Action:** Remove both, use `create_default_users.py` which is up-to-date
- **Note:** `create_default_users.py` already handles password creation/updates

#### 1.3 Forecasting Scripts
- **`scripts/forecasting/rapids_forecasting_agent.py`** - Older version?
- **`scripts/forecasting/rapids_gpu_forecasting.py`** - Current version
- **Status:** Need to verify if `rapids_forecasting_agent.py` is still used
- **Action:** Check imports/references, remove if unused

#### 1.4 Migration Scripts
- **`scripts/tools/migrate.py`** - Full migration CLI tool
- **`scripts/tools/simple_migrate.py`** - Simple migration script
- **Status:** Both exist, need to determine which is used
- **Action:** Check which is referenced in docs, consolidate if needed
- **Note:** Actual migrations are in `data/postgres/migrations/`

---

## 2. Outdated Files (Should be Removed)

### 2.1 Generated JSON Files (Already in .gitignore)
- **`scripts/phase1_phase2_forecasts.json`** - Generated file
- **`scripts/phase3_advanced_forecasts.json`** - Generated file
- **Status:** Already in .gitignore, should be removed from repo
- **Action:** Delete these files (they're generated at runtime)

### 2.2 Old Server Script
- **`RUN_LOCAL.sh`** (root) - Uses outdated port 8002
- **Status:** Superseded by `scripts/start_server.sh`
- **Action:** Delete

---

## 3. Organization Issues (Move Files)

### 3.1 SQL File Location
- **`scripts/create_model_tracking_tables.sql`**
- **Referenced as:** `scripts/setup/create_model_tracking_tables.sql` in docs
- **Status:** File is in wrong location
- **Action:** Move to `scripts/setup/create_model_tracking_tables.sql`
- **References to update:**
  - README.md
  - DEPLOYMENT.md
  - docs/deployment/README.md
  - src/ui/web/src/pages/Documentation.tsx

### 3.2 Migration Scripts Location
- **`scripts/tools/migrate.py`** and **`scripts/tools/simple_migrate.py`**
- **Status:** Migration scripts in tools folder, but migrations are in `data/postgres/migrations/`
- **Action:** Consider moving to `scripts/setup/` or keeping in `tools/` if they're utility scripts
- **Recommendation:** Keep in `tools/` if they're CLI utilities, move to `setup/` if they're setup scripts

---

## 4. Folder Structure Analysis

### Current Structure
```
scripts/
├── __pycache__/              # Python cache (should be in .gitignore)
├── create_model_tracking_tables.sql  # Should be in setup/
├── phase1_phase2_forecasts.json      # Should be deleted (generated)
├── phase3_advanced_forecasts.json    # Should be deleted (generated)
├── requirements_synthetic_data.txt   # OK
├── README.md                         # OK
├── start_server.sh                   # OK
├── data/                             # OK
│   ├── generate_*.py
│   └── run_*.sh
├── forecasting/                      # OK
│   ├── phase1_phase2_forecasting_agent.py
│   ├── phase3_advanced_forecasting.py
│   ├── rapids_forecasting_agent.py   # Check if duplicate
│   └── rapids_gpu_forecasting.py
├── setup/                            # OK (mostly)
│   ├── create_default_users.py       # OK (current)
│   ├── fix_admin_password.py         # Should be removed
│   ├── update_admin_password.py      # Should be removed
│   └── *.sh scripts
├── testing/                          # OK
│   └── test_*.py
└── tools/                            # OK (mostly)
    ├── migrate.py                    # Check usage
    └── simple_migrate.py             # Check usage
```

### Recommended Structure
```
scripts/
├── README.md
├── start_server.sh
├── requirements_synthetic_data.txt
├── data/
│   ├── generate_*.py
│   └── run_*.sh
├── forecasting/
│   ├── phase1_phase2_forecasting_agent.py
│   ├── phase3_advanced_forecasting.py
│   └── rapids_gpu_forecasting.py  # Keep only this one
├── setup/
│   ├── create_default_users.py
│   ├── create_model_tracking_tables.sql  # Moved here
│   └── *.sh scripts
├── testing/
│   └── test_*.py
└── tools/
    ├── migrate.py  # Keep if used, remove if not
    └── other utility scripts
```

---

## 5. Overlaps with Other Folders

### 5.1 Deployment Scripts
- **`scripts/setup/dev_up.sh`** - Development infrastructure setup
- **`deploy/scripts/setup_monitoring.sh`** - Monitoring setup
- **Status:** No overlap, different purposes
- **Action:** Keep both

### 5.2 Migration Files
- **`scripts/tools/migrate.py`** - Migration CLI tool
- **`data/postgres/migrations/`** - Migration SQL files
- **Status:** Different purposes (CLI tool vs SQL files)
- **Action:** Keep both, but verify migrate.py is used

### 5.3 Test Files
- **`scripts/testing/test_*.py`** - Script-based tests
- **`tests/`** - Formal test suite
- **Status:** Different purposes (ad-hoc tests vs formal suite)
- **Action:** Keep both, but consider moving to tests/ if they're formal tests

---

## 6. Action Plan

### Immediate Actions (High Priority)

1. **Delete duplicate/outdated files:**
   ```bash
   rm RUN_LOCAL.sh
   rm scripts/phase1_phase2_forecasts.json
   rm scripts/phase3_advanced_forecasts.json
   rm scripts/setup/fix_admin_password.py
   rm scripts/setup/update_admin_password.py
   ```

2. **Move SQL file:**
   ```bash
   mv scripts/create_model_tracking_tables.sql scripts/setup/
   ```

3. **Check and remove duplicate forecasting script:**
   ```bash
   # Check if rapids_forecasting_agent.py is referenced
   grep -r "rapids_forecasting_agent" .
   # If not referenced, remove it
   rm scripts/forecasting/rapids_forecasting_agent.py
   ```

4. **Update references:**
   - Update all references to `scripts/create_model_tracking_tables.sql` to `scripts/setup/create_model_tracking_tables.sql`

### Review Before Removing (Medium Priority)

1. **Migration scripts:**
   - Check if `scripts/tools/migrate.py` is used
   - Check if `scripts/tools/simple_migrate.py` is used
   - Remove if unused, or consolidate if both are needed

2. **Forecasting scripts:**
   - Verify `rapids_forecasting_agent.py` is not used
   - Remove if duplicate

### Future Improvements (Low Priority)

1. **Consider moving test scripts:**
   - Move `scripts/testing/` to `tests/scripts/` if they're formal tests
   - Keep in scripts/ if they're ad-hoc/demo scripts

2. **Documentation:**
   - Update scripts/README.md with current structure
   - Document which scripts are for setup vs runtime

---

## 7. Verification Checklist

After cleanup, verify:

- [ ] All references to removed files are updated
- [ ] All references to moved files are updated
- [ ] No broken imports or script calls
- [ ] Documentation is updated
- [ ] .gitignore excludes generated files
- [ ] Folder structure is logical and consistent

---

## 8. Files to Keep (Confirmed)

### Setup Scripts
- ✅ `scripts/setup/setup_environment.sh`
- ✅ `scripts/setup/dev_up.sh`
- ✅ `scripts/setup/create_default_users.py`
- ✅ `scripts/setup/install_rapids.sh`
- ✅ `scripts/setup/setup_rapids_*.sh`

### Data Generation
- ✅ `scripts/data/generate_*.py`
- ✅ `scripts/data/run_*.sh`

### Forecasting
- ✅ `scripts/forecasting/phase1_phase2_forecasting_agent.py`
- ✅ `scripts/forecasting/phase3_advanced_forecasting.py`
- ✅ `scripts/forecasting/rapids_gpu_forecasting.py`

### Testing
- ✅ `scripts/testing/test_*.py`

### Tools
- ✅ `scripts/tools/*.py` (after review)

### Main Scripts
- ✅ `scripts/start_server.sh`
- ✅ `scripts/README.md`

---

## Summary of Changes

**Files Deleted:** 7 files
- ✅ RUN_LOCAL.sh
- ✅ scripts/phase1_phase2_forecasts.json
- ✅ scripts/phase3_advanced_forecasts.json
- ✅ scripts/setup/fix_admin_password.py
- ✅ scripts/setup/update_admin_password.py
- ✅ scripts/tools/migrate.py
- ✅ scripts/tools/simple_migrate.py

**Files Kept (Still Referenced):**
- ⚠️ scripts/forecasting/rapids_forecasting_agent.py - Still referenced in some docs. Consider updating references to use rapids_gpu_forecasting.py
- ✅ Dockerfile.rapids - Updated to use rapids_gpu_forecasting.py

**Files Moved:** 1 file
- ✅ scripts/create_model_tracking_tables.sql → scripts/setup/

**Files Reviewed and Removed:** 2 files
- ✅ scripts/tools/migrate.py - Duplicate of src/api/cli/migrate.py, removed
- ✅ scripts/tools/simple_migrate.py - Not referenced, removed

**Documentation Status:**
- ✅ README.md - Already references correct paths
- ✅ DEPLOYMENT.md - Already references correct paths
- ✅ docs/deployment/README.md - Already references correct paths
- ✅ src/ui/web/src/pages/Documentation.tsx - Already references correct paths
- ✅ tests/FORECASTING_SUMMARY_CARDS_ASSESSMENT.md - Updated

**Note:** All documentation already uses `scripts/setup/create_model_tracking_tables.sql` path, so no updates needed.

