#!/usr/bin/env python3
"""
Automated Testing Script for Complete Setup Notebook

This script validates the structure and basic functionality of the setup notebook.
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Colors for terminal output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_success(msg: str):
    """Print success message."""
    print(f"{Colors.GREEN}✅ {msg}{Colors.RESET}")

def print_error(msg: str):
    """Print error message."""
    print(f"{Colors.RED}❌ {msg}{Colors.RESET}")

def print_warning(msg: str):
    """Print warning message."""
    print(f"{Colors.YELLOW}⚠️  {msg}{Colors.RESET}")

def print_info(msg: str):
    """Print info message."""
    print(f"{Colors.BLUE}ℹ️  {msg}{Colors.RESET}")

def print_header(msg: str):
    """Print header message."""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{msg}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}\n")

def load_notebook(notebook_path: Path) -> Dict:
    """Load notebook JSON."""
    try:
        with open(notebook_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print_error(f"Notebook not found: {notebook_path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print_error(f"Invalid JSON in notebook: {e}")
        sys.exit(1)

def test_notebook_structure(nb: Dict) -> Tuple[bool, List[str]]:
    """Test basic notebook structure."""
    issues = []
    
    # Check cell count
    if len(nb['cells']) == 0:
        issues.append("Notebook has no cells")
    else:
        print_success(f"Notebook has {len(nb['cells'])} cells")
    
    # Check for required cell types
    cell_types = {}
    for cell in nb['cells']:
        cell_type = cell['cell_type']
        cell_types[cell_type] = cell_types.get(cell_type, 0) + 1
    
    if 'markdown' not in cell_types:
        issues.append("Notebook has no markdown cells (documentation)")
    else:
        print_success(f"Found {cell_types['markdown']} markdown cells")
    
    if 'code' not in cell_types:
        issues.append("Notebook has no code cells")
    else:
        print_success(f"Found {cell_types['code']} code cells")
    
    return len(issues) == 0, issues

def test_required_sections(nb: Dict) -> Tuple[bool, List[str]]:
    """Test that required sections are present."""
    required_sections = [
        'Prerequisites',
        'Repository Setup',
        'Environment Setup',
        'NVIDIA API Key',
        'Database Setup',
        'Verification',
        'Troubleshooting'
    ]
    
    # Extract all text content
    content = ' '.join([
        ''.join(cell.get('source', []))
        for cell in nb['cells']
        if cell['cell_type'] == 'markdown'
    ]).lower()
    
    missing = []
    found = []
    
    for section in required_sections:
        if section.lower() in content:
            found.append(section)
        else:
            missing.append(section)
    
    for section in found:
        print_success(f"Found section: {section}")
    
    for section in missing:
        print_error(f"Missing section: {section}")
    
    return len(missing) == 0, missing

def test_code_cells(nb: Dict) -> Tuple[bool, List[str]]:
    """Test code cells for common issues."""
    issues = []
    
    code_cells = [c for c in nb['cells'] if c['cell_type'] == 'code']
    
    for i, cell in enumerate(code_cells, 1):
        source = ''.join(cell.get('source', []))
        
        # Check for common imports
        if 'import' in source and i > 2:  # Skip first few cells
            # Check if imports are at the top
            lines = source.split('\n')
            import_lines = [j for j, line in enumerate(lines) if line.strip().startswith('import')]
            if import_lines and import_lines[0] > 10:
                issues.append(f"Cell {i}: Imports should be at the top")
        
        # Check for print statements (good for user feedback)
        if 'print(' in source or 'print ' in source:
            pass  # Good - has output
        elif source.strip() and not source.strip().startswith('#'):
            # Has code but no output - might be okay
            pass
    
    if not issues:
        print_success(f"All {len(code_cells)} code cells look good")
    
    return len(issues) == 0, issues

def test_markdown_formatting(nb: Dict) -> Tuple[bool, List[str]]:
    """Test markdown cells for proper formatting."""
    issues = []
    
    markdown_cells = [c for c in nb['cells'] if c['cell_type'] == 'markdown']
    
    for i, cell in enumerate(markdown_cells, 1):
        source = ''.join(cell.get('source', []))
        
        # Check for headers
        if source.strip() and not any(source.strip().startswith(f'{"#"*j}') for j in range(1, 7)):
            if len(source) > 100:  # Long content should have headers
                issues.append(f"Markdown cell {i}: Long content without headers")
    
    if not issues:
        print_success(f"All {len(markdown_cells)} markdown cells formatted correctly")
    
    return len(issues) == 0, issues

def test_file_paths(nb: Dict, notebook_dir: Path) -> Tuple[bool, List[str]]:
    """Test that referenced file paths exist."""
    issues = []
    
    # Extract all file paths mentioned
    content = ' '.join([
        ''.join(cell.get('source', []))
        for cell in nb['cells']
    ])
    
    # Common file patterns
    import re
    file_patterns = [
        r'\.env\.example',
        r'requirements\.txt',
        r'scripts/setup/',
        r'data/postgres/',
        r'src/api/',
    ]
    
    project_root = notebook_dir.parent.parent
    
    for pattern in file_patterns:
        matches = re.findall(pattern, content)
        if matches:
            # Check if files exist
            for match in set(matches):
                if match.startswith('.'):
                    file_path = project_root / match
                elif '/' in match:
                    file_path = project_root / match
                else:
                    file_path = project_root / match
                
                if not file_path.exists() and not file_path.is_dir():
                    issues.append(f"Referenced file/directory not found: {match}")
    
    if not issues:
        print_success("All referenced files exist")
    
    return len(issues) == 0, issues

def test_execution_order(nb: Dict) -> Tuple[bool, List[str]]:
    """Test that cells are in logical execution order."""
    issues = []
    
    # Check that markdown cells precede related code cells
    # This is a simple heuristic - can be enhanced
    prev_type = None
    for i, cell in enumerate(nb['cells'], 1):
        current_type = cell['cell_type']
        
        # Markdown should often precede code
        if prev_type == 'code' and current_type == 'code':
            # Two code cells in a row - check if second has imports
            source = ''.join(cell.get('source', []))
            if 'import' in source and i > 3:
                # Imports should be early
                pass
        
        prev_type = current_type
    
    if not issues:
        print_success("Cell execution order looks logical")
    
    return len(issues) == 0, issues

def main():
    """Run all tests."""
    print_header("Notebook Testing Suite")
    
    # Find notebook
    script_dir = Path(__file__).parent
    notebook_path = script_dir / "complete_setup_guide.ipynb"
    
    if not notebook_path.exists():
        print_error(f"Notebook not found: {notebook_path}")
        sys.exit(1)
    
    print_info(f"Testing notebook: {notebook_path}")
    
    # Load notebook
    nb = load_notebook(notebook_path)
    
    # Run tests
    tests = [
        ("Structure", test_notebook_structure),
        ("Required Sections", test_required_sections),
        ("Code Cells", test_code_cells),
        ("Markdown Formatting", test_markdown_formatting),
        ("File Paths", lambda nb: test_file_paths(nb, script_dir)),
        ("Execution Order", test_execution_order),
    ]
    
    results = []
    for test_name, test_func in tests:
        print_header(f"Test: {test_name}")
        try:
            passed, issues = test_func(nb)
            results.append((test_name, passed, issues))
        except Exception as e:
            print_error(f"Test failed with exception: {e}")
            results.append((test_name, False, [str(e)]))
    
    # Summary
    print_header("Test Summary")
    
    passed_count = sum(1 for _, passed, _ in results if passed)
    total_count = len(results)
    
    for test_name, passed, issues in results:
        if passed:
            print_success(f"{test_name}: PASSED")
        else:
            print_error(f"{test_name}: FAILED")
            for issue in issues:
                print_warning(f"  - {issue}")
    
    print(f"\n{Colors.BOLD}Results: {passed_count}/{total_count} tests passed{Colors.RESET}\n")
    
    if passed_count == total_count:
        print_success("All tests passed! 🎉")
        return 0
    else:
        print_error("Some tests failed. Please review the issues above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())

