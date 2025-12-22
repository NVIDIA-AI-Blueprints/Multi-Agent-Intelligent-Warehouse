#!/usr/bin/env python3
"""
Audit Requirements
Checks if all packages in requirements.txt are used in the codebase,
and if all imported packages are listed in requirements.txt.
"""

import re
import ast
from pathlib import Path
from typing import Set, Dict, List
from collections import defaultdict

def parse_requirements(requirements_file: Path) -> Dict[str, str]:
    """Parse requirements.txt and return package names and versions."""
    packages = {}
    with open(requirements_file, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            # Parse package specification
            # Format: package==version, package>=version, package[extra]>=version
            match = re.match(r'^([a-zA-Z0-9_-]+(?:\[[^\]]+\])?)([<>=!]+)?([0-9.]+)?', line)
            if match:
                package_spec = match.group(1)
                # Remove extras
                package_name = re.sub(r'\[.*\]', '', package_spec).lower()
                version = match.group(3) if match.group(3) else None
                packages[package_name] = version or 'any'
    
    return packages

def extract_imports_from_file(file_path: Path) -> Set[str]:
    """Extract all import statements from a Python file."""
    imports = set()
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Parse the file
        try:
            tree = ast.parse(content, filename=str(file_path))
        except SyntaxError:
            # Skip files with syntax errors
            return imports
        
        # Walk the AST to find imports
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module_name = alias.name.split('.')[0]
                    imports.add(module_name.lower())
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    module_name = node.module.split('.')[0]
                    imports.add(module_name.lower())
    except Exception as e:
        # Skip files that can't be read or parsed
        pass
    
    return imports

def get_standard_library_modules() -> Set[str]:
    """Get a list of Python standard library modules."""
    import sys
    if sys.version_info >= (3, 10):
        import stdlib_list
        return set(stdlib_list.stdlib_list())
    else:
        # Fallback list of common stdlib modules
        return {
            'os', 'sys', 'json', 're', 'datetime', 'time', 'logging', 'pathlib',
            'typing', 'collections', 'itertools', 'functools', 'operator',
            'abc', 'dataclasses', 'enum', 'asyncio', 'threading', 'multiprocessing',
            'urllib', 'http', 'email', 'base64', 'hashlib', 'secrets', 'uuid',
            'io', 'csv', 'pickle', 'copy', 'math', 'random', 'statistics',
            'string', 'textwrap', 'unicodedata', 'codecs', 'locale',
            'traceback', 'warnings', 'contextlib', 'functools', 'inspect',
            'argparse', 'getopt', 'shutil', 'tempfile', 'glob', 'fnmatch',
            'linecache', 'pprint', 'reprlib', 'weakref', 'gc', 'sysconfig',
            'platform', 'errno', 'ctypes', 'mmap', 'select', 'socket',
            'ssl', 'socketserver', 'http', 'urllib', 'email', 'mimetypes',
            'base64', 'binascii', 'hashlib', 'hmac', 'secrets', 'uuid',
            'html', 'xml', 'sqlite3', 'dbm', 'zlib', 'gzip', 'bz2', 'lzma',
            'tarfile', 'zipfile', 'csv', 'configparser', 'netrc', 'xdrlib',
            'plistlib', 'hashlib', 'hmac', 'secrets', 'uuid', 'io', 'pickle',
            'copyreg', 'shelve', 'marshal', 'dbm', 'sqlite3', 'zlib', 'gzip',
            'bz2', 'lzma', 'zipfile', 'tarfile', 'csv', 'configparser',
            'netrc', 'xdrlib', 'plistlib', 'logging', 'getopt', 'argparse',
            'getpass', 'curses', 'platform', 'errno', 'ctypes', 'threading',
            'multiprocessing', 'concurrent', 'subprocess', 'sched', 'queue',
            'select', 'selectors', 'asyncio', 'socket', 'ssl', 'email',
            'json', 'mailcap', 'mailbox', 'mmh3', 'nntplib', 'poplib',
            'imaplib', 'smtplib', 'telnetlib', 'uuid', 'socketserver',
            'http', 'urllib', 'xmlrpc', 'ipaddress', 'audioop', 'aifc',
            'sunau', 'wave', 'chunk', 'colorsys', 'imghdr', 'sndhdr',
            'ossaudiodev', 'gettext', 'locale', 'calendar', 'cmd', 'shlex',
            'configparser', 'fileinput', 'linecache', 'netrc', 'xdrlib',
            'plistlib', 'shutil', 'tempfile', 'glob', 'fnmatch', 'linecache',
            'stat', 'filecmp', 'mmap', 'codecs', 'stringprep', 'readline',
            'rlcompleter', 'struct', 'codecs', 'encodings', 'unicodedata',
            'stringprep', 'readline', 'rlcompleter', 'difflib', 'textwrap',
            'unicodedata', 'stringprep', 'readline', 'rlcompleter', 're',
            'string', 'difflib', 'textwrap', 'unicodedata', 'stringprep',
            'readline', 'rlcompleter', 'struct', 'codecs', 'encodings',
            'unicodedata', 'stringprep', 'readline', 'rlcompleter'
        }

def scan_codebase_for_imports(root_dir: Path) -> Dict[str, List[str]]:
    """Scan the codebase for all imports."""
    imports = defaultdict(list)
    stdlib = get_standard_library_modules()
    
    for py_file in root_dir.rglob('*.py'):
        # Skip test files and virtual environments
        if 'test' in str(py_file) or 'env' in str(py_file) or '__pycache__' in str(py_file):
            continue
        
        file_imports = extract_imports_from_file(py_file)
        for imp in file_imports:
            # Skip standard library
            if imp not in stdlib:
                imports[imp].append(str(py_file.relative_to(root_dir)))
    
    return imports

def normalize_package_name(import_name: str) -> str:
    """Normalize import name to package name."""
    # Common mappings
    mappings = {
        'pil': 'pillow',
        'yaml': 'pyyaml',
        'cv2': 'opencv-python',
        'sklearn': 'scikit-learn',
        'bs4': 'beautifulsoup4',
        'dateutil': 'python-dateutil',
        'dotenv': 'python-dotenv',
        'jwt': 'pyjwt',
        'passlib': 'passlib',
        'pydantic': 'pydantic',
        'fastapi': 'fastapi',
        'uvicorn': 'uvicorn',
        'asyncpg': 'asyncpg',
        'aiohttp': 'aiohttp',
        'httpx': 'httpx',
        'redis': 'redis',
        'pymilvus': 'pymilvus',
        'numpy': 'numpy',
        'pandas': 'pandas',
        'xgboost': 'xgboost',
        'sklearn': 'scikit-learn',
        'pymodbus': 'pymodbus',
        'pyserial': 'pyserial',
        'paho': 'paho-mqtt',
        'websockets': 'websockets',
        'click': 'click',
        'loguru': 'loguru',
        'langchain': 'langchain',
        'langgraph': 'langgraph',
        'prometheus_client': 'prometheus-client',
        'psycopg': 'psycopg',
        'fitz': 'pymupdf',  # Legacy mapping - PyMuPDF replaced with pdf2image/pdfplumber
        'tiktoken': 'tiktoken',
        'faker': 'faker',
        'bcrypt': 'bcrypt',
    }
    
    return mappings.get(import_name.lower(), import_name.lower())

def main():
    """Main audit function."""
    repo_root = Path(__file__).parent.parent.parent
    
    # Parse requirements
    requirements_file = repo_root / 'requirements.txt'
    if not requirements_file.exists():
        print(f"Error: {requirements_file} not found")
        return
    
    required_packages = parse_requirements(requirements_file)
    print(f"Found {len(required_packages)} packages in requirements.txt\n")
    
    # Scan codebase for imports
    print("Scanning codebase for imports...")
    src_dir = repo_root / 'src'
    all_imports = scan_codebase_for_imports(src_dir)
    
    # Also check scripts directory
    scripts_dir = repo_root / 'scripts'
    if scripts_dir.exists():
        scripts_imports = scan_codebase_for_imports(scripts_dir)
        for imp, files in scripts_imports.items():
            all_imports[imp].extend(files)
    
    print(f"Found {len(all_imports)} unique third-party imports\n")
    
    # Check which required packages are used
    print("=" * 80)
    print("PACKAGES IN requirements.txt - USAGE ANALYSIS")
    print("=" * 80)
    
    unused_packages = []
    used_packages = []
    
    for pkg_name, version in sorted(required_packages.items()):
        # Check various possible import names
        possible_imports = [
            pkg_name,
            pkg_name.replace('-', '_'),
            pkg_name.replace('_', '-'),
        ]
        
        found = False
        for imp_name in possible_imports:
            if imp_name in all_imports:
                used_packages.append((pkg_name, version, all_imports[imp_name]))
                found = True
                break
        
        if not found:
            unused_packages.append((pkg_name, version))
    
    print(f"\n✅ USED PACKAGES ({len(used_packages)}):")
    for pkg_name, version, files in sorted(used_packages):
        file_count = len(set(files))
        print(f"  ✓ {pkg_name}=={version} (used in {file_count} file(s))")
    
    print(f"\n⚠️  POTENTIALLY UNUSED PACKAGES ({len(unused_packages)}):")
    for pkg_name, version in sorted(unused_packages):
        print(f"  ⚠ {pkg_name}=={version}")
        print(f"     Note: May be used indirectly or in configuration files")
    
    # Check which imports are not in requirements
    print("\n" + "=" * 80)
    print("IMPORTS IN CODEBASE - REQUIREMENTS ANALYSIS")
    print("=" * 80)
    
    missing_packages = []
    found_packages = []
    
    for imp_name, files in sorted(all_imports.items()):
        normalized = normalize_package_name(imp_name)
        
        # Check if it's in requirements
        if normalized in required_packages:
            found_packages.append((imp_name, normalized, files))
        else:
            # Check if it might be a standard library module we missed
            if imp_name not in get_standard_library_modules():
                missing_packages.append((imp_name, files))
    
    print(f"\n✅ IMPORTS COVERED BY requirements.txt ({len(found_packages)}):")
    for imp_name, pkg_name, files in sorted(found_packages)[:20]:  # Show first 20
        file_count = len(set(files))
        print(f"  ✓ {imp_name} -> {pkg_name} (in {file_count} file(s))")
    if len(found_packages) > 20:
        print(f"  ... and {len(found_packages) - 20} more")
    
    print(f"\n❌ POTENTIALLY MISSING PACKAGES ({len(missing_packages)}):")
    for imp_name, files in sorted(missing_packages):
        file_count = len(set(files))
        file_list = ', '.join(set(files))[:100]  # Limit file list length
        if len(', '.join(set(files))) > 100:
            file_list += '...'
        print(f"  ❌ {imp_name} (used in {file_count} file(s))")
        print(f"     Files: {file_list}")
    
    # Generate summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total packages in requirements.txt: {len(required_packages)}")
    print(f"  - Used: {len(used_packages)}")
    print(f"  - Potentially unused: {len(unused_packages)}")
    print(f"\nTotal third-party imports found: {len(all_imports)}")
    print(f"  - Covered by requirements.txt: {len(found_packages)}")
    print(f"  - Potentially missing: {len(missing_packages)}")
    
    if unused_packages:
        print(f"\n⚠️  Recommendation: Review {len(unused_packages)} potentially unused packages")
    if missing_packages:
        print(f"\n❌ Recommendation: Add {len(missing_packages)} potentially missing packages to requirements.txt")

if __name__ == '__main__':
    main()

