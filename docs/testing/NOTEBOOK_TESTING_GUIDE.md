# Notebook Testing Guide

This guide explains how to test the `complete_setup_guide.ipynb` notebook to ensure it works correctly for new users.

## Testing Approach

### Option 1: Clean Test Environment (Recommended)

Test in a completely fresh environment to simulate a new user's experience:

```bash
# 1. Create a test directory
mkdir -p ~/test-warehouse-setup
cd ~/test-warehouse-setup

# 2. Clone the repository fresh
git clone https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse.git
cd Multi-Agent-Intelligent-Warehouse

# 3. Start Jupyter from the project root
python3 -m venv test-env
source test-env/bin/activate
pip install jupyter ipykernel
python -m ipykernel install --user --name=test-warehouse
jupyter notebook notebooks/setup/complete_setup_guide.ipynb
```

**Advantages:**
- ✅ Tests the complete user journey
- ✅ Catches missing dependencies or setup issues
- ✅ Verifies all instructions are correct
- ✅ Most realistic testing scenario

**Disadvantages:**
- ⚠️ Takes longer (full setup)
- ⚠️ Requires clean Docker state

### Option 2: Quick Validation (Faster)

Test specific cells or functions without full setup:

```bash
# In your current project directory
cd /home/tarik-devh/Projects/warehouseassistant/warehouse-operational-assistant

# Start Jupyter
source env/bin/activate
jupyter notebook notebooks/setup/complete_setup_guide.ipynb
```

**Advantages:**
- ✅ Faster iteration
- ✅ Good for testing specific fixes
- ✅ Can test individual cells

**Disadvantages:**
- ⚠️ May miss environment-specific issues
- ⚠️ Existing setup might mask problems

## Testing Checklist

### Prerequisites (Step 1)
- [ ] Python version check works
- [ ] Node.js version check works
- [ ] Docker and Docker Compose detection works
- [ ] Git check works

### Repository Setup (Step 2)
- [ ] Project root detection works
- [ ] Works from any directory
- [ ] Handles missing repository gracefully

### Environment Setup (Step 3)
- [ ] Virtual environment creation works
- [ ] Dependencies install correctly
- [ ] CUDA version detection works (if GPU available)
- [ ] CUDA mismatch warnings appear correctly
- [ ] Handles existing venv gracefully

### API Key Configuration (Step 4)
- [ ] Prompts for all NVIDIA API keys
- [ ] Handles Brev API key option
- [ ] Prompts for LLM_MODEL when using Brev
- [ ] Updates .env file correctly
- [ ] Strips comments from values

### Environment Variables (Step 5)
- [ ] Checks all required variables
- [ ] Shows helpful descriptions
- [ ] Identifies missing variables

### Infrastructure Services (Step 6)
- [ ] Loads .env variables correctly
- [ ] Configures TimescaleDB port (5435)
- [ ] Cleans up old containers
- [ ] Starts all services
- [ ] Waits for TimescaleDB to be ready
- [ ] Shows service endpoints

### Database Setup (Step 7)
- [ ] Runs all migrations successfully
- [ ] Handles docker compose vs docker-compose
- [ ] Shows helpful error messages

### Create Default Users (Step 8)
- [ ] Creates admin user successfully
- [ ] Handles existing users gracefully

### Generate Demo Data (Step 9)
- [ ] Loads .env variables
- [ ] Runs quick_demo_data.py successfully
- [ ] Runs generate_historical_demand.py successfully
- [ ] Shows helpful error messages
- [ ] Passes environment to subprocess

### RAPIDS Installation (Step 10 - Optional)
- [ ] Detects CUDA version
- [ ] Installs correct RAPIDS packages (cu11/cu12)
- [ ] Handles missing GPU gracefully

### Start Backend (Step 11)
- [ ] Loads .env variables correctly
- [ ] Activates virtual environment properly
- [ ] Starts server in background
- [ ] Waits for server to be ready
- [ ] No ValueError with commented env vars
- [ ] Shows server endpoints

### Start Frontend (Step 12)
- [ ] Checks for node_modules
- [ ] Installs dependencies if needed
- [ ] Shows start instructions

### Verification (Step 13)
- [ ] Checks all services
- [ ] Tests API endpoints
- [ ] Shows status correctly

## Common Issues to Test

### 1. Missing .env File
- Test Step 6 without .env - should warn but continue
- Test Step 9 without .env - should warn about database credentials

### 2. Inline Comments in .env
```bash
# Test with .env containing:
LLM_CLIENT_TIMEOUT=120.  # Timeout in seconds
GUARDRAILS_TIMEOUT=10  # Guardrails timeout
```
- Should not cause ValueError in Step 11

### 3. Different CUDA Versions
- Test with CUDA 11.x - should install cu11 packages
- Test with CUDA 12.x - should install cu12 packages
- Test with CUDA 13.x - should install cu12 (backward compatible)

### 4. Existing Containers
- Test Step 6 with existing containers - should clean up first

### 5. Port Conflicts
- Test Step 11 with port 8001 already in use - should detect and warn

## Quick Test Script

Create a test script to automate some checks:

```bash
#!/bin/bash
# Quick notebook validation test

set -e

echo "🧪 Testing Notebook Functions"

# Test 1: Check if notebook is valid JSON
echo "1. Validating notebook JSON..."
python3 -c "import json; json.load(open('notebooks/setup/complete_setup_guide.ipynb'))"
echo "   ✅ Valid JSON"

# Test 2: Check for syntax errors in Python cells
echo "2. Checking Python syntax..."
python3 << 'PYEOF'
import json
import ast

with open('notebooks/setup/complete_setup_guide.ipynb', 'r') as f:
    nb = json.load(f)

errors = []
for i, cell in enumerate(nb['cells']):
    if cell['cell_type'] == 'code':
        source = ''.join(cell.get('source', []))
        if source.strip():
            try:
                ast.parse(source)
            except SyntaxError as e:
                errors.append(f"Cell {i}: {e}")

if errors:
    print("   ❌ Syntax errors found:")
    for err in errors:
        print(f"      {err}")
    exit(1)
else:
    print("   ✅ No syntax errors")
PYEOF

# Test 3: Check for required functions
echo "3. Checking required functions..."
python3 << 'PYEOF'
import json

with open('notebooks/setup/complete_setup_guide.ipynb', 'r') as f:
    nb = json.load(f)

source = ''.join([''.join(cell.get('source', [])) for cell in nb['cells'] if cell['cell_type'] == 'code'])

required = [
    'get_project_root',
    'start_infrastructure',
    'generate_demo_data',
    'start_backend',
    'setup_database',
    'create_default_users'
]

missing = [f for f in required if f'def {f}(' not in source]
if missing:
    print(f"   ❌ Missing functions: {missing}")
    exit(1)
else:
    print("   ✅ All required functions present")
PYEOF

echo ""
echo "✅ Basic validation complete!"
echo ""
echo "Next: Test manually in Jupyter notebook"
```

## Recommended Testing Workflow

1. **Quick Syntax Check** (30 seconds)
   ```bash
   # Run the test script above
   ./scripts/tools/test_notebook_syntax.sh  # Create this if needed
   ```

2. **Cell-by-Cell Test** (10-15 minutes)
   - Open notebook in Jupyter
   - Run each cell sequentially
   - Verify outputs match expectations
   - Check for errors or warnings

3. **Full End-to-End Test** (30-45 minutes)
   - Use Option 1 (clean environment)
   - Follow notebook from start to finish
   - Document any issues or unclear instructions

4. **Edge Case Testing** (15-20 minutes)
   - Test with missing .env
   - Test with commented env vars
   - Test with different CUDA versions
   - Test with existing containers/services

## Testing on Same Machine

**Yes, you can test on the same machine**, but:

### Best Practice:
1. **Use a separate directory** to avoid conflicts:
   ```bash
   mkdir ~/test-notebook
   cd ~/test-notebook
   git clone <repo-url>
   ```

2. **Use different ports** if services are already running:
   - Change TimescaleDB port in docker-compose.dev.yaml
   - Or stop existing services first

3. **Use a separate virtual environment**:
   ```bash
   python3 -m venv test-env
   source test-env/bin/activate
   ```

### Quick Test (Same Machine, Different Directory)

```bash
# 1. Create test directory
mkdir -p ~/test-warehouse-notebook
cd ~/test-warehouse-notebook

# 2. Clone fresh
git clone https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse.git
cd Multi-Agent-Intelligent-Warehouse

# 3. Create test venv
python3 -m venv test-venv
source test-venv/bin/activate

# 4. Install Jupyter
pip install jupyter ipykernel
python -m ipykernel install --user --name=test-warehouse

# 5. Start Jupyter
jupyter notebook notebooks/setup/complete_setup_guide.ipynb

# 6. Select kernel: test-warehouse
# 7. Run cells step by step
```

## What to Look For

### ✅ Success Indicators:
- All cells execute without errors
- Environment variables load correctly
- Services start successfully
- Database migrations complete
- Demo data generates
- Backend starts without ValueError

### ❌ Failure Indicators:
- Syntax errors in cells
- Missing environment variables
- Services fail to start
- Database connection errors
- ValueError when parsing env vars
- Missing dependencies

## Reporting Issues

When you find issues, document:
1. **Step number** (e.g., Step 9)
2. **Cell number** (if applicable)
3. **Error message** (full traceback)
4. **Environment** (OS, Python version, CUDA version if applicable)
5. **What you expected** vs **what happened**
6. **Screenshot** (if visual issue)

## Next Steps After Testing

1. Fix any issues found
2. Update documentation if instructions are unclear
3. Add error handling for edge cases
4. Improve error messages
5. Commit fixes with clear commit messages

