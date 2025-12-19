#!/bin/bash
# Quick notebook validation test

set -e

echo "🧪 Testing Notebook Functions"
echo "=" * 60

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
