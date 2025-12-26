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
import email.header
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime

# Full license texts
MIT_LICENSE_TEXT = """MIT License

Permission is hereby granted, free of charge, to any person obtaining a copy of this software 
and associated documentation files (the "Software"), to deal in the Software without restriction, 
including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, 
and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, 
subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or 
substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING 
BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. 
IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, 
WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE 
OR THE USE OR OTHER DEALINGS IN THE SOFTWARE."""

APACHE_LICENSE_TEXT = """Apache License
Version 2.0, January 2004
http://www.apache.org/licenses/

TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION

1. Definitions.

   "License" shall mean the terms and conditions for use, reproduction, and distribution as defined in this document.
   "Licensor" shall mean the copyright owner or entity authorized by the copyright owner that is granting the License.
   "Legal Entity" shall mean the union of the acting entity and all other entities that control, are controlled by, or are under common control with that entity.
   "You" (or "Your") shall mean an individual or Legal Entity exercising permissions granted by this License.
   "Source" form shall mean the preferred form for making modifications, including but not limited to software source code, documentation source, and configuration files.
   "Object" form shall mean any form resulting from mechanical transformation or translation of a Source form, including but not limited to compiled object code, generated documentation, and conversions to other media types.
   "Work" shall mean the work of authorship, whether in Source or Object form, made available under the License, as indicated by a copyright notice that is included in or attached to the work.
   "Derivative Works" shall mean any work, whether in Source or Object form, that is based on (or derived from) the Work and for which the modifications represent, as a whole, an original work of authorship.
   "Contribution" shall mean any work of authorship, including the original version of the Work and any modifications or additions to that Work or Derivative Works thereof, that is intentionally submitted to Licensor for inclusion in the Work.
   "Contributor" shall mean Licensor and any individual or Legal Entity on behalf of whom a Contribution has been received by Licensor and subsequently incorporated within the Work.

2. Grant of Copyright License.

   Subject to the terms and conditions of this License, each Contributor hereby grants to You a perpetual, worldwide, non-exclusive, 
   no-charge, royalty-free, irrevocable copyright license to reproduce, prepare Derivative Works of, 
   publicly display, publicly perform, sublicense, and distribute the Work and such Derivative Works.

3. Grant of Patent License.

   Subject to the terms and conditions of this License, each Contributor hereby grants to You a perpetual, worldwide, non-exclusive, 
   no-charge, royalty-free, irrevocable (except as stated in this section) patent license to make, have made, use, offer to sell, 
   sell, import, and otherwise transfer the Work, where such license applies only to those patent claims licensable by such Contributor 
   that are necessarily infringed by their Contribution(s) alone or by combination of their Contribution(s) with the Work.

4. Redistribution.

   You may reproduce and distribute copies of the Work or Derivative Works thereof in any medium, with or without modifications, 
   and in Source or Object form, provided that You meet the following conditions:
     (a) You must give any other recipients of the Work or Derivative Works a copy of this License; and
     (b) You must cause any modified files to carry prominent notices stating that You changed the files; and
     (c) You must retain, in the Source form of any Derivative Works that You distribute, all copyright, patent, trademark, 
         and attribution notices from the Source form of the Work; and
     (d) If the Work includes a "NOTICE" text file as part of its distribution, then any Derivative Works that You distribute 
         must include a readable copy of the attribution notices contained within such NOTICE file.

5. Submission of Contributions.

   Unless You explicitly state otherwise, any Contribution submitted for inclusion in the Work shall be under the terms and conditions of this License.

6. Trademarks.

   This License does not grant permission to use the trade names, trademarks, service marks, or product names of the Licensor.

7. Disclaimer of Warranty.

   The Work is provided on an "AS IS" basis, without warranties or conditions of any kind, either express or implied.

8. Limitation of Liability.

   In no event shall any Contributor be liable for any damages arising from the use of the Work.

END OF TERMS AND CONDITIONS"""

BSD_3_CLAUSE_TEXT = """BSD 3-Clause License

Copyright <YEAR> <COPYRIGHT HOLDER>

Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE."""

BSD_2_CLAUSE_TEXT = """BSD 2-Clause License

Copyright <YEAR> <COPYRIGHT HOLDER>

Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDER AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE."""


def normalize_license(license_str: str) -> Tuple[str, str]:
    """
    Normalize license string to standard name and return full text.
    
    Args:
        license_str: Raw license string from package metadata
        
    Returns:
        Tuple of (normalized_license_name, full_license_text)
    """
    license_str = str(license_str).strip()
    
    if not license_str or license_str == 'N/A' or license_str == 'UNKNOWN':
        return 'Unknown License', ''
    
    # Normalize to standard license names
    license_upper = license_str.upper()
    
    if 'MIT' in license_upper:
        return 'MIT License', MIT_LICENSE_TEXT
    elif 'APACHE' in license_upper and '2.0' in license_upper:
        return 'Apache License, Version 2.0', APACHE_LICENSE_TEXT
    elif 'BSD' in license_upper:
        if '3-CLAUSE' in license_upper or '3 CLAUSE' in license_upper:
            return 'BSD 3-Clause License', BSD_3_CLAUSE_TEXT
        elif '2-CLAUSE' in license_upper or '2 CLAUSE' in license_upper:
            return 'BSD 2-Clause License', BSD_2_CLAUSE_TEXT
        else:
            return 'BSD License', BSD_3_CLAUSE_TEXT  # Default to 3-clause
    elif 'GPL' in license_upper:
        if 'LGPL' in license_upper or 'LESSER' in license_upper:
            return 'LGPL License', ''  # Would need full text
        else:
            return 'GPL License', ''  # Would need full text
    elif 'PSF' in license_upper or 'PYTHON' in license_upper:
        return 'Python Software Foundation License', ''
    else:
        return license_str, ''  # Return as-is for custom licenses


def get_pypi_copyright(package_name: str, version: str) -> Tuple[str, str]:
    """
    Get copyright information from PyPI API.
    
    Args:
        package_name: Package name
        version: Package version
        
    Returns:
        Tuple of (copyright_year, copyright_holder)
    """
    try:
        url = f"https://pypi.org/pypi/{package_name}/{version}/json"
        with urllib.request.urlopen(url, timeout=5) as response:
            data = json.loads(response.read())
            info = data.get('info', {})
            
            # Get author information
            author = info.get('author', '')
            author_email = info.get('author_email', '')
            
            # Decode RFC 2047 encoded strings
            if author and '=?' in author:
                try:
                    decoded_parts = email.header.decode_header(author)
                    decoded_author = ''
                    for part in decoded_parts:
                        if isinstance(part[0], bytes):
                            encoding = part[1] or 'utf-8'
                            decoded_author += part[0].decode(encoding)
                        else:
                            decoded_author += part[0]
                    author = decoded_author.strip()
                except Exception:
                    pass
            
            # Extract copyright holder (author name without email)
            copyright_holder = author
            if author and '<' in author:
                copyright_holder = author.split('<')[0].strip()
            elif author_email and not author:
                # Use email if no author name
                copyright_holder = author_email.split('@')[0].replace('.', ' ').title()
            
            # Get copyright year from release date
            releases = data.get('releases', {})
            release_info = releases.get(version, [])
            copyright_year = None
            
            if release_info and len(release_info) > 0:
                upload_time = release_info[0].get('upload_time', '')
                if upload_time:
                    try:
                        # Parse ISO format date
                        dt = datetime.fromisoformat(upload_time.replace('Z', '+00:00'))
                        copyright_year = str(dt.year)
                    except:
                        pass
            
            # If no release date, try to get from first release
            if not copyright_year:
                all_releases = list(releases.keys())
                if all_releases:
                    # Get earliest release
                    first_release = releases.get(all_releases[0], [])
                    if first_release:
                        upload_time = first_release[0].get('upload_time', '')
                        if upload_time:
                            try:
                                dt = datetime.fromisoformat(upload_time.replace('Z', '+00:00'))
                                copyright_year = str(dt.year)
                            except:
                                pass
            
            # Default to current year if no date found
            if not copyright_year:
                copyright_year = datetime.now().strftime('%Y')
            
            # Clean up copyright holder
            if copyright_holder:
                copyright_holder = copyright_holder.strip()
                # Remove common prefixes
                copyright_holder = re.sub(r'^Copyright\s*\(c\)\s*\d{4}\s*', '', copyright_holder, flags=re.IGNORECASE)
                copyright_holder = copyright_holder.strip()
                # Remove incomplete entries (single words, email fragments, etc.)
                if len(copyright_holder) < 3 or copyright_holder.lower() in ['hello', 'n/a', 'unknown', 'none']:
                    copyright_holder = None
                # Remove email fragments
                if '<' in copyright_holder and '>' not in copyright_holder:
                    copyright_holder = copyright_holder.split('<')[0].strip()
            
            # If still no good copyright holder, try maintainers or project name
            if not copyright_holder or copyright_holder == 'N/A':
                maintainers = info.get('maintainer', '')
                if maintainers:
                    if '<' in maintainers:
                        maintainers = maintainers.split('<')[0].strip()
                    copyright_holder = maintainers.strip()
                else:
                    # Use project name as fallback
                    project_name = info.get('name', package_name)
                    if project_name:
                        copyright_holder = f"{project_name} Contributors"
            
            return copyright_year, copyright_holder or 'N/A'
            
    except Exception as e:
        # Return defaults on error
        return datetime.now().strftime('%Y'), 'N/A'


def get_npm_copyright(package_name: str, version: str) -> Tuple[str, str]:
    """
    Get copyright information from npm API.
    
    Args:
        package_name: Package name
        version: Package version
        
    Returns:
        Tuple of (copyright_year, copyright_holder)
    """
    try:
        package_url_name = package_name.replace('/', '%2F')
        url = f"https://registry.npmjs.org/{package_url_name}"
        
        with urllib.request.urlopen(url, timeout=5) as response:
            data = json.loads(response.read())
            
            version_data = data.get('versions', {}).get(version, {})
            
            # Get author information
            author = version_data.get('author', {})
            if isinstance(author, dict):
                author_name = author.get('name', '')
            elif isinstance(author, str):
                author_name = author
            else:
                author_name = ''
            
            # Get time from version data
            time_data = data.get('time', {})
            copyright_year = None
            
            if version in time_data:
                try:
                    dt = datetime.fromisoformat(time_data[version].replace('Z', '+00:00'))
                    copyright_year = str(dt.year)
                except:
                    pass
            
            # Try to get from first release
            if not copyright_year and time_data:
                first_time = list(time_data.values())[0] if time_data else None
                if first_time:
                    try:
                        dt = datetime.fromisoformat(first_time.replace('Z', '+00:00'))
                        copyright_year = str(dt.year)
                    except:
                        pass
            
            # Default to current year
            if not copyright_year:
                copyright_year = datetime.now().strftime('%Y')
            
            # Clean up author name
            copyright_holder = author_name.strip() if author_name else None
            if copyright_holder and '<' in copyright_holder:
                copyright_holder = copyright_holder.split('<')[0].strip()
            
            # If no author, try maintainers or project name
            if not copyright_holder or len(copyright_holder) < 3:
                maintainers = data.get('maintainers', [])
                if maintainers and len(maintainers) > 0:
                    maintainer = maintainers[0]
                    if isinstance(maintainer, dict):
                        copyright_holder = maintainer.get('name', '')
                    elif isinstance(maintainer, str):
                        copyright_holder = maintainer
                
                if not copyright_holder or len(copyright_holder) < 3:
                    # Use package name as fallback
                    package_display_name = package_name.replace('@', '').replace('/', ' ').title()
                    copyright_holder = f"{package_display_name} Contributors"
            
            return copyright_year, copyright_holder or 'N/A'
        
    except Exception as e:
        return datetime.now().strftime('%Y'), 'N/A'

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

