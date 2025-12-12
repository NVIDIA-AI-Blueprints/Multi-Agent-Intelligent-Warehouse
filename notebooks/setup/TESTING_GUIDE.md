# Testing Guide for Complete Setup Notebook

This guide provides comprehensive strategies for testing the `complete_setup_guide.ipynb` notebook.

## Testing Approaches

### 1. **Manual Testing (Recommended for First Pass)**

#### Step-by-Step Manual Test

1. **Start Fresh Environment**
   ```bash
   # Create a test directory
   mkdir -p /tmp/notebook_test
   cd /tmp/notebook_test
   
   # Start Jupyter
   jupyter notebook
   ```

2. **Open the Notebook**
   - Navigate to `notebooks/setup/complete_setup_guide.ipynb`
   - Open in Jupyter Notebook or JupyterLab

3. **Test Each Cell Sequentially**
   - Run cells one by one from top to bottom
   - Verify outputs match expectations
   - Check for errors or warnings
   - Document any issues

4. **Test Scenarios**
   - ✅ **Fresh Setup**: Test on a clean system
   - ✅ **Partial Setup**: Test when some components already exist
   - ✅ **Error Handling**: Test with missing dependencies
   - ✅ **Skip Steps**: Test skipping optional steps

#### What to Check

- [ ] All cells execute without errors
- [ ] Output messages are clear and helpful
- [ ] Error messages are informative
- [ ] Progress indicators work correctly
- [ ] Interactive prompts function properly
- [ ] File paths are correct
- [ ] Commands execute successfully
- [ ] Verification steps pass

---

### 2. **Automated Testing with nbconvert**

#### Basic Execution Test

```bash
# Install nbconvert if not already installed
pip install nbconvert

# Execute notebook (dry run - won't actually set up)
jupyter nbconvert --to notebook --execute \
  notebooks/setup/complete_setup_guide.ipynb \
  --output complete_setup_guide_executed.ipynb \
  --ExecutePreprocessor.timeout=600
```

#### Validation Script

Create a test script to validate notebook structure:

```python
# tests/notebooks/test_setup_notebook.py
import json
import pytest
from pathlib import Path

def test_notebook_structure():
    """Test that notebook has correct structure."""
    notebook_path = Path("notebooks/setup/complete_setup_guide.ipynb")
    
    with open(notebook_path) as f:
        nb = json.load(f)
    
    # Check cell count
    assert len(nb['cells']) > 0, "Notebook should have cells"
    
    # Check for markdown cells (documentation)
    markdown_cells = [c for c in nb['cells'] if c['cell_type'] == 'markdown']
    assert len(markdown_cells) > 0, "Notebook should have markdown cells"
    
    # Check for code cells
    code_cells = [c for c in nb['cells'] if c['cell_type'] == 'code']
    assert len(code_cells) > 0, "Notebook should have code cells"
    
    # Check for required sections
    content = ' '.join([c.get('source', '') for c in nb['cells']])
    required_sections = [
        'Prerequisites',
        'Repository Setup',
        'Environment Setup',
        'NVIDIA API Key',
        'Database Setup',
        'Verification'
    ]
    for section in required_sections:
        assert section.lower() in content.lower(), f"Missing section: {section}"
```

---

### 3. **Unit Testing Individual Functions**

Extract and test functions separately:

```python
# tests/notebooks/test_setup_functions.py
import sys
from pathlib import Path

# Add notebook directory to path
sys.path.insert(0, str(Path("notebooks/setup")))

def test_prerequisites_check():
    """Test prerequisites checking functions."""
    # Import functions from notebook (if extracted)
    # Or test them directly
    pass

def test_env_setup():
    """Test environment setup functions."""
    pass
```

---

### 4. **Integration Testing**

Test the complete flow in a controlled environment:

```bash
# Use Docker or VM for isolated testing
docker run -it --rm \
  -v $(pwd):/workspace \
  -w /workspace \
  python:3.9 \
  bash -c "pip install jupyter nbconvert && \
           jupyter nbconvert --to notebook --execute \
           notebooks/setup/complete_setup_guide.ipynb"
```

---

## Testing Checklist

### Pre-Testing Setup

- [ ] Create a clean test environment
- [ ] Backup existing setup (if testing on main system)
- [ ] Document current system state
- [ ] Prepare test API keys (if needed)

### Cell-by-Cell Testing

#### Cell 0: Introduction
- [ ] Renders correctly
- [ ] All links work
- [ ] Formatting is correct

#### Cell 1-2: Prerequisites Check
- [ ] Detects Python version correctly
- [ ] Detects Node.js version correctly
- [ ] Handles missing tools gracefully
- [ ] Version checks work correctly

#### Cell 3-5: Repository Setup
- [ ] Detects if already in repo
- [ ] Provides clear cloning instructions
- [ ] Optional auto-clone works (if enabled)

#### Cell 6-7: Environment Setup
- [ ] Creates virtual environment
- [ ] Handles existing venv correctly
- [ ] Installs dependencies successfully
- [ ] Error messages are helpful

#### Cell 8-9: API Key Setup
- [ ] Creates .env file from .env.example
- [ ] Handles existing .env correctly
- [ ] Secure input works (getpass)
- [ ] Updates API keys correctly
- [ ] Validates API key format

#### Cell 10-11: Environment Variables
- [ ] Displays current configuration
- [ ] Masks sensitive values
- [ ] Shows warnings for missing values

#### Cell 12-13: Infrastructure Services
- [ ] Checks Docker status
- [ ] Starts services correctly
- [ ] Waits for services to be ready
- [ ] Handles errors gracefully

#### Cell 14-15: Database Setup
- [ ] Runs migrations successfully
- [ ] Handles missing files gracefully
- [ ] Provides helpful error messages
- [ ] Works with Docker exec or psql

#### Cell 16-17: User Creation
- [ ] Creates default users
- [ ] Handles existing users
- [ ] Shows credentials clearly

#### Cell 18-19: Demo Data
- [ ] Generates demo data (optional)
- [ ] Handles missing scripts gracefully

#### Cell 20-21: Backend Server
- [ ] Checks port availability
- [ ] Provides start instructions
- [ ] Optional auto-start works

#### Cell 22-23: Frontend Setup
- [ ] Installs npm dependencies
- [ ] Provides start instructions
- [ ] Handles errors gracefully

#### Cell 24-25: Verification
- [ ] Checks all services
- [ ] Tests health endpoints
- [ ] Provides clear status report

#### Cell 26-27: Troubleshooting & Summary
- [ ] Documentation is clear
- [ ] Links work correctly

---

## Automated Test Script

Run this script to perform automated validation:

```bash
# Run automated notebook tests
python notebooks/setup/test_notebook.py
```

---

## Common Issues to Test

1. **Missing Dependencies**
   - Test with Python < 3.9
   - Test with Node.js < 18.17.0
   - Test with missing Docker

2. **Existing Setup**
   - Test with existing virtual environment
   - Test with existing .env file
   - Test with running services

3. **Network Issues**
   - Test with no internet connection
   - Test with slow connection
   - Test with API key errors

4. **Permission Issues**
   - Test with read-only directories
   - Test with insufficient permissions

5. **Path Issues**
   - Test from different directories
   - Test with spaces in paths
   - Test with special characters

---

## Best Practices

1. **Test in Isolation**: Use Docker or VM for testing
2. **Test Incrementally**: Test one section at a time
3. **Document Issues**: Keep a log of problems found
4. **Test Edge Cases**: Test error conditions
5. **Verify Outputs**: Check that outputs are correct
6. **Test User Experience**: Ensure instructions are clear

---

## Continuous Integration

Add to CI/CD pipeline:

```yaml
# .github/workflows/test-notebooks.yml
name: Test Notebooks

on: [push, pull_request]

jobs:
  test-notebook:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.9'
      - name: Install dependencies
        run: |
          pip install jupyter nbconvert pytest
      - name: Validate notebook structure
        run: |
          pytest tests/notebooks/test_setup_notebook.py
      - name: Execute notebook (dry run)
        run: |
          jupyter nbconvert --to notebook --execute \
            notebooks/setup/complete_setup_guide.ipynb \
            --ExecutePreprocessor.timeout=600 \
            --ExecutePreprocessor.allow_errors=True
```

---

## Quick Test Commands

```bash
# 1. Validate notebook structure
python -c "import json; nb=json.load(open('notebooks/setup/complete_setup_guide.ipynb')); print(f'Cells: {len(nb[\"cells\"])}')"

# 2. Check for syntax errors in code cells
jupyter nbconvert --to python notebooks/setup/complete_setup_guide.ipynb --stdout | python -m py_compile -

# 3. Execute notebook (with timeout)
jupyter nbconvert --to notebook --execute \
  notebooks/setup/complete_setup_guide.ipynb \
  --ExecutePreprocessor.timeout=600

# 4. Convert to HTML for review
jupyter nbconvert --to html notebooks/setup/complete_setup_guide.ipynb
```

---

## Reporting Issues

When reporting issues, include:
- Cell number and content
- Expected behavior
- Actual behavior
- Error messages
- System information (OS, Python version, etc.)
- Steps to reproduce

