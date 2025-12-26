#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Generate LICENSE-3rd-party.txt file from license audit data.

This script extracts license information from the License_Audit_Report.xlsx
and generates a comprehensive third-party license file.
"""

import json
import time
import re
import urllib.request
import urllib.error
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime

# Import shared utilities to eliminate code duplication
from .license_utils import (
    normalize_license,
    get_pypi_copyright,
    get_npm_copyright,
)

try:
    from openpyxl import load_workbook
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False
    print("Error: openpyxl not installed. Install with: pip install openpyxl")
    exit(1)


def parse_requirements_file(requirements_file: Path) -> List[Dict[str, str]]:
    """Parse requirements.txt file and extract package names and versions."""
    packages = []
    if not requirements_file.exists():
        return packages
    
    with open(requirements_file, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            # Parse package specification (e.g., "package>=1.0.0" or "package==1.0.0")
            # Remove comments
            if '#' in line:
                line = line.split('#')[0].strip()
            
            # Match package name and version constraints
            # Optimized regex to prevent catastrophic backtracking:
            # - Package name: starts with alphanumeric/underscore/hyphen, followed by alphanumeric/dot/underscore/hyphen
            # - Version: optional, starts with comparison operators, followed by any chars except newline
            # Using non-greedy quantifier and negated character class to avoid backtracking
            match = re.match(r'^([a-zA-Z0-9_-][a-zA-Z0-9._-]*?)([<>=!]+[^\n]*)?$', line)
            if match:
                package_name = match.group(1)
                # For now, we'll get the actual installed version from PyPI
                packages.append({'name': package_name, 'version': None})
    
    return packages


def parse_package_json(package_json: Path) -> List[Dict[str, str]]:
    """Parse package.json file and extract package names and versions."""
    packages = []
    if not package_json.exists():
        return packages
    
    with open(package_json, 'r') as f:
        data = json.load(f)
    
    # Get dependencies and devDependencies
    deps = {}
    deps.update(data.get('dependencies', {}))
    deps.update(data.get('devDependencies', {}))
    
    for name, version_spec in deps.items():
        # Clean version spec (remove ^, ~, etc.)
        version = None  # We'll get actual version from npm
        packages.append({'name': name, 'version': version})
    
    return packages


def extract_packages_from_audit(repo_root: Path) -> Dict[str, List[Dict[str, Any]]]:
    """Extract packages from requirements files and fetch copyright info from APIs."""
    all_packages = {}
    
    print("Extracting packages from requirements files...")
    
    # Parse Python requirements
    requirements_files = [
        repo_root / 'requirements.txt',
        repo_root / 'requirements.docker.txt',
    ]
    
    python_packages = set()
    for req_file in requirements_files:
        if req_file.exists():
            packages = parse_requirements_file(req_file)
            for pkg in packages:
                python_packages.add(pkg['name'])
    
    # Parse Node.js package.json
    package_json = repo_root / 'src' / 'ui' / 'web' / 'package.json'
    nodejs_packages = set()
    if package_json.exists():
        packages = parse_package_json(package_json)
        for pkg in packages:
            nodejs_packages.add(pkg['name'])
    
    print(f"Found {len(python_packages)} Python packages and {len(nodejs_packages)} Node.js packages")
    print("Fetching copyright information from PyPI and npm APIs...")
    
    # Fetch Python packages from PyPI
    for i, package_name in enumerate(sorted(python_packages), 1):
        print(f"[{i}/{len(python_packages)}] Fetching {package_name}...")
        try:
            # Get latest version info
            url = f"https://pypi.org/pypi/{package_name}/json"
            with urllib.request.urlopen(url, timeout=5) as response:
                data = json.loads(response.read())
                info = data.get('info', {})
                version = info.get('version', 'N/A')
                license_val = info.get('license', '')
                
                # Get copyright info
                copyright_year, copyright_holder = get_pypi_copyright(package_name, version)
                
                all_packages[package_name] = {
                    'version': version,
                    'license': license_val or 'N/A',
                    'copyright_year': copyright_year,
                    'copyright_holder': copyright_holder,
                    'source': 'pypi'
                }
        except Exception as e:
            print(f"  ⚠️  Error fetching {package_name}: {e}")
            all_packages[package_name] = {
                'version': 'N/A',
                'license': 'N/A',
                'copyright_year': datetime.now().strftime('%Y'),
                'copyright_holder': 'N/A',
                'source': 'pypi'
            }
        time.sleep(0.1)  # Rate limiting
    
    # Fetch Node.js packages from npm
    for i, package_name in enumerate(sorted(nodejs_packages), 1):
        print(f"[{i}/{len(nodejs_packages)}] Fetching {package_name}...")
        try:
            # Get latest version info
            package_url_name = package_name.replace('/', '%2F')
            url = f"https://registry.npmjs.org/{package_url_name}"
            with urllib.request.urlopen(url, timeout=5) as response:
                data = json.loads(response.read())
                latest_version = data.get('dist-tags', {}).get('latest', '')
                version_data = data.get('versions', {}).get(latest_version, {})
                license_val = version_data.get('license', '')
                if isinstance(license_val, dict):
                    license_val = license_val.get('type', '')
                
                # Get copyright info
                copyright_year, copyright_holder = get_npm_copyright(package_name, latest_version)
                
                all_packages[package_name] = {
                    'version': latest_version or 'N/A',
                    'license': license_val or 'N/A',
                    'copyright_year': copyright_year,
                    'copyright_holder': copyright_holder,
                    'source': 'npm'
                }
        except Exception as e:
            print(f"  ⚠️  Error fetching {package_name}: {e}")
            all_packages[package_name] = {
                'version': 'N/A',
                'license': 'N/A',
                'copyright_year': datetime.now().strftime('%Y'),
                'copyright_holder': 'N/A',
                'source': 'npm'
            }
        time.sleep(0.1)  # Rate limiting
    
    # Group by normalized license
    license_groups = defaultdict(list)
    
    for name, info in sorted(all_packages.items()):
        if info['license'] and info['license'] != 'N/A':
            normalized_license, _ = normalize_license(info['license'])
            license_groups[normalized_license].append({
                'name': name,
                'version': info['version'],
                'copyright_year': info['copyright_year'],
                'copyright_holder': info['copyright_holder']
            })
    
    return dict(license_groups)


def generate_license_file(repo_root: Path, output_file: Path):
    """Generate LICENSE-3rd-party.txt file."""
    print("Extracting license information from audit report...")
    license_groups = extract_packages_from_audit(repo_root)
    
    if not license_groups:
        print("Error: No packages found in license audit report")
        return False
    
    print(f"Found {sum(len(pkgs) for pkgs in license_groups.values())} packages across {len(license_groups)} license types")
    
    # Generate the license file
    output_lines = []
    
    # Header
    output_lines.append("This file contains third-party license information and copyright notices for software packages")
    output_lines.append("used in this project. The licenses below apply to one or more packages included in this project.")
    output_lines.append("")
    output_lines.append("For each license type, we list the packages that are distributed under it along with their")
    output_lines.append("respective copyright holders and include the full license text.")
    output_lines.append("")
    output_lines.append("")
    output_lines.append("IMPORTANT: This file includes both the copyright information and license details as required by")
    output_lines.append("most open-source licenses to ensure proper attribution and legal compliance.")
    output_lines.append("")
    output_lines.append("")
    output_lines.append("-" * 60)
    output_lines.append("")
    
    # Process licenses in priority order
    license_priority = [
        'MIT License',
        'Apache License, Version 2.0',
        'BSD 3-Clause License',
        'BSD 2-Clause License',
        'BSD License',
        'GPL License',
        'LGPL License',
        'Python Software Foundation License',
    ]
    
    # Add other licenses at the end
    other_licenses = [lic for lic in license_groups.keys() if lic not in license_priority]
    
    for license_name in license_priority + sorted(other_licenses):
        if license_name not in license_groups:
            continue
        
        packages = license_groups[license_name]
        normalized_license, license_text = normalize_license(license_name)
        
        output_lines.append("-" * 60)
        output_lines.append(license_name)
        output_lines.append("-" * 60)
        output_lines.append("")
        
        # Add description based on license type
        if 'MIT' in license_name:
            output_lines.append("The MIT License is a permissive free software license. Many of the packages used in this")
            output_lines.append("project are distributed under the MIT License. The full text of the MIT License is provided")
            output_lines.append("below.")
            output_lines.append("")
            output_lines.append("")
        elif 'Apache' in license_name:
            output_lines.append("The Apache License, Version 2.0 is a permissive license that also provides an express grant of patent rights.")
            output_lines.append("")
            output_lines.append("")
        elif 'BSD' in license_name:
            output_lines.append("The BSD License is a permissive license.")
            output_lines.append("")
            output_lines.append("")
        
        output_lines.append("Packages under the {} with their respective copyright holders:".format(license_name))
        output_lines.append("")
        
        # List packages
        for pkg in sorted(packages, key=lambda x: x['name'].lower()):
            name = pkg['name']
            version = pkg['version']
            copyright_year = pkg.get('copyright_year', datetime.now().strftime('%Y'))
            copyright_holder = pkg.get('copyright_holder', 'N/A')
            
            output_lines.append("  {} {}".format(name, version))
            if copyright_holder and copyright_holder != 'N/A' and copyright_holder.strip():
                output_lines.append("  Copyright (c) {} {}".format(copyright_year, copyright_holder))
            output_lines.append("")
        
        # Add full license text if available
        if license_text:
            output_lines.append("")
            output_lines.append("Full {} Text:".format(license_name))
            output_lines.append("")
            output_lines.append("-" * 50)
            output_lines.append("")
            output_lines.append(license_text)
            output_lines.append("")
            output_lines.append("-" * 50)
            output_lines.append("")
            output_lines.append("")
    
    output_lines.append("")
    output_lines.append("END OF THIRD-PARTY LICENSES")
    
    # Write to file
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(output_lines))
    
    print(f"✅ Generated LICENSE-3rd-party.txt: {output_file}")
    return True


def main():
    """Main function."""
    repo_root = Path(__file__).parent.parent.parent
    output_file = repo_root / 'LICENSE-3rd-party.txt'
    
    print("=" * 70)
    print("Generate LICENSE-3rd-party.txt")
    print("=" * 70)
    print(f"Repository: {repo_root}")
    print(f"Output: {output_file}")
    print("=" * 70)
    print()
    
    success = generate_license_file(repo_root, output_file)
    
    if success:
        print()
        print("=" * 70)
        print("✅ License file generated successfully!")
        print("=" * 70)
    else:
        print()
        print("=" * 70)
        print("❌ Failed to generate license file")
        print("=" * 70)
        exit(1)


if __name__ == "__main__":
    main()

