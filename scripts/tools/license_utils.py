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
Shared License Utilities

Common functions for license auditing and generation scripts.
Extracted to eliminate code duplication.
"""

import json
import subprocess
import urllib.request
import urllib.error
import email.header
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
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


def run_command(cmd: List[str], cwd: Optional[Path] = None, check: bool = False) -> Tuple[bool, str, str]:
    """
    Run a shell command and return success, stdout, stderr.
    
    Args:
        cmd: Command to run as list of strings
        cwd: Working directory (optional)
        check: If True, raise exception on non-zero exit code
        
    Returns:
        Tuple of (success, stdout, stderr)
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd,
            check=check
        )
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)


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

