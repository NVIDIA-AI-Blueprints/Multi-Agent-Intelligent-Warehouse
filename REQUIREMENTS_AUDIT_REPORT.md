# Requirements.txt Audit Report

**Generated:** 2025-01-XX  
**Purpose:** Verify that all packages in `requirements.txt` are actually used, and identify any missing dependencies.

---

## Executive Summary

- **Total packages in requirements.txt:** 33
- **Packages confirmed in use:** 18
- **Packages potentially unused (need verification):** 15
- **Missing packages identified:** 4

---

## ✅ Confirmed Used Packages (18)

These packages are actively imported and used in the codebase:

1. **aiohttp** (3.8.0) - Used in 5 files
2. **asyncpg** (0.29.0) - Used in 14 files
3. **bacpypes3** (0.0.0) - Used in 1 file
4. **click** (8.0.0) - Used in 1 file (CLI tools)
5. **fastapi** (0.119.0) - Used in 21 files (core framework)
6. **httpx** (0.27.0) - Used in 14 files
7. **langchain-core** (0.1.0) - Used in 3 files
8. **langgraph** (0.2.30) - Used in 3 files
9. **numpy** (1.24.0) - Used in 13 files
10. **pandas** (1.2.4) - Used in 7 files
11. **prometheus-client** (0.19.0) - Used in 1 file
12. **psycopg** (3.0.0) - Used in 2 files
13. **pydantic** (2.7+) - Used in 16 files (core framework)
14. **pymilvus** (2.3.0) - Used in 5 files
15. **redis** (5.0.0) - Used in 4 files
16. **tiktoken** - Used in 1 file
17. **websockets** (11.0.0) - Used in 3 files
18. **xgboost** (1.6.0) - Used in 5 files

---

## ⚠️ Potentially Unused Packages (15)

These packages are listed in `requirements.txt` but were not found via direct import scanning. However, they may be used indirectly or in specific contexts:

### Confirmed Used (via manual verification):

1. **PyJWT** (2.8.0) ✅ - Used as `jwt` in `src/api/services/auth/jwt_handler.py`
2. **passlib[bcrypt]** (1.7.4) ✅ - Used via `bcrypt` import in `src/api/services/auth/jwt_handler.py`
3. **Pillow** (10.0.0) ✅ - Used as `PIL` in 6 document processing files
4. **PyMuPDF** (1.23.0) ✅ - Used as `fitz` in PDF processing
5. **PyYAML** (6.0) ✅ - Used as `yaml` in `src/api/services/guardrails/guardrails_service.py` and `src/api/cli/migrate.py`
6. **python-dotenv** (1.0) ✅ - Used as `dotenv` in 9 files (environment variable loading)
7. **python-multipart** ✅ - Required by FastAPI for file uploads (used implicitly)
8. **email-validator** (2.0.0) ✅ - Required by Pydantic for email validation (used implicitly)
9. **uvicorn** (0.30.1) ✅ - Used to run the FastAPI server (via `scripts/start_server.sh`)

### Needs Verification:

10. **loguru** (0.7) ⚠️ - Not found in imports. May be used in logging configuration or replaced by standard `logging` module.
11. **paho-mqtt** (1.6.0) ⚠️ - Not found in imports. May be used in IoT adapters or planned for future use.
12. **pymodbus** (3.0.0) ⚠️ - Not found in imports. May be used in IoT/equipment adapters or planned for future use.
13. **pyserial** (3.5) ⚠️ - Not found in imports. May be used in RFID/barcode scanners or planned for future use.
14. **requests** (2.31.0) ⚠️ - Not found in imports. May be used in adapters or replaced by `httpx`.
15. **scikit-learn** (1.0.0) ⚠️ - Not found as `sklearn` import. May be used in forecasting or ML components.

---

## ❌ Missing Packages (4)

These packages are used in the codebase but are **NOT** listed in `requirements.txt`:

1. **bcrypt** (>=4.0.0) ❌
   - **Used in:** `src/api/services/auth/jwt_handler.py`, `scripts/data/generate_synthetic_data.py`
   - **Note:** While `passlib[bcrypt]` is listed, `bcrypt` is also directly imported. `passlib[bcrypt]` should install `bcrypt` as a dependency, but it's safer to list it explicitly if directly imported.
   - **Status:** Actually covered by `passlib[bcrypt]`, but direct import suggests explicit dependency may be preferred.

2. **faker** (>=19.0.0) ❌
   - **Used in:** `scripts/data/generate_synthetic_data.py`
   - **Note:** Listed in `scripts/requirements_synthetic_data.txt` but not in main `requirements.txt`
   - **Recommendation:** Add to `requirements.txt` if synthetic data generation is part of core functionality, or document that it's only needed for development scripts.

3. **optuna** ❌
   - **Used in:** `scripts/forecasting/phase3_advanced_forecasting.py`
   - **Note:** Used for hyperparameter optimization in advanced forecasting
   - **Recommendation:** Add to `requirements.txt` if advanced forecasting is part of core functionality, or move to optional/development requirements.

4. **psutil** ❌
   - **Used in:** `tests/performance/test_mcp_performance.py`, `tests/integration/test_mcp_load_testing.py`, `scripts/tools/benchmark_gpu_milvus.py`, `src/api/services/mcp/monitoring.py`
   - **Note:** Used for system monitoring and performance testing
   - **Recommendation:** Add to `requirements.txt` as it's used in production code (`src/api/services/mcp/monitoring.py`)

---

## 📋 Recommendations

### High Priority

1. **Add missing production dependencies:**
   ```txt
   psutil>=5.9.0  # Used in src/api/services/mcp/monitoring.py
   ```

2. **Verify and document optional dependencies:**
   - `faker` - Only needed for synthetic data generation scripts
   - `optuna` - Only needed for advanced forecasting features
   - Consider creating `requirements-dev.txt` or `requirements-optional.txt` for these

### Medium Priority

3. **Verify unused packages:**
   - Check if `loguru` is actually used or can be removed
   - Verify `paho-mqtt`, `pymodbus`, `pyserial` are needed for IoT/equipment adapters
   - Check if `requests` is still needed or can be replaced by `httpx`
   - Verify `scikit-learn` usage in forecasting/ML components

4. **Clean up duplicates:**
   - `requirements.txt` has duplicate entries:
     - `aiohttp>=3.8.0` (lines 12 and 20)
     - `httpx>=0.27` (line 4) and `httpx>=0.27.0` (line 22)
     - `websockets>=11.0.0` (lines 21 and 24)

### Low Priority

5. **Consider explicit dependencies:**
   - While `bcrypt` is covered by `passlib[bcrypt]`, explicit import suggests it may be worth listing separately
   - `python-multipart` and `email-validator` are implicit FastAPI/Pydantic dependencies but are already listed

---

## 🔍 Additional Findings

### Duplicate Entries in requirements.txt

The following packages appear multiple times:
- **Line 12 & 20:** `aiohttp>=3.8.0` (appears twice)
- **Line 4 & 22:** `httpx>=0.27` and `httpx>=0.27.0` (different version formats)
- **Line 21 & 24:** `websockets>=11.0.0` (appears twice)

**Recommendation:** Remove duplicates and consolidate to single entries with appropriate version constraints. Keep the more specific version format (e.g., `httpx>=0.27.0`).

### Version Inconsistencies

- `fastapi==0.119.0` in `requirements.txt` vs `fastapi==0.111.0` in `requirements.docker.txt`
- `redis>=5.0.0` in `requirements.txt` vs `redis>=4.0.0` in `requirements.docker.txt`

**Recommendation:** Align versions across all requirements files or document why they differ.

---

## 📝 Notes

- The audit script uses AST parsing to find imports, which may miss:
  - Dynamic imports
  - Imports in string literals
  - Imports in configuration files
  - Imports in test files (which may use different requirements)

- Some packages are used implicitly (e.g., `uvicorn` is called via command line, `python-multipart` is required by FastAPI for file uploads)

- Internal modules (e.g., `src.*`, `base`, `factory`) are correctly identified as not requiring external packages

---

## ✅ Action Items

- [ ] Add `psutil>=5.9.0` to `requirements.txt`
- [ ] Remove duplicate entries from `requirements.txt`
- [ ] Verify and document optional dependencies (`faker`, `optuna`)
- [ ] Verify usage of `loguru`, `paho-mqtt`, `pymodbus`, `pyserial`, `requests`, `scikit-learn`
- [ ] Align versions between `requirements.txt` and `requirements.docker.txt`
- [ ] Consider creating `requirements-dev.txt` for development-only dependencies

---

*This report was generated using automated analysis. Manual verification is recommended for packages marked as "needs verification".*

