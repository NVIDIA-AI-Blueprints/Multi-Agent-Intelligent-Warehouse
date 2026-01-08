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
Dependency Blocklist Checker

This script checks for blocked dependencies that should not be installed
in production environments due to security vulnerabilities.

Usage:
    python scripts/security/dependency_blocklist.py
    python scripts/security/dependency_blocklist.py --check-installed
"""

import sys
import subprocess
import argparse
from typing import List, Dict, Set
from pathlib import Path


# Blocked packages and their security reasons
BLOCKED_PACKAGES: Dict[str, str] = {
    # LangChain Experimental - Contains Python REPL vulnerabilities
    "langchain-experimental": (
        "CVE-2024-38459: Unauthorized Python REPL access without opt-in. "
        "CVE-2024-46946: Code execution via sympy.sympify. "
        "CVE-2024-21513: Code execution via VectorSQLDatabaseChain. "
        "CVE-2023-44467: Arbitrary code execution via PALChain. "
        "Use langchain-core instead if needed."
    ),
    "langchain_experimental": (
        "Same as langchain-experimental (different package name format). "
        "Contains Python REPL vulnerabilities."
    ),
    # LangChain (old package) - Contains path traversal vulnerability
    "langchain": (
        "CVE-2024-28088: Directory traversal in load_chain/load_prompt/load_agent. "
        "Affected versions: langchain <= 0.1.10, langchain-core < 0.1.29. "
        "This codebase uses langchain-core>=1.2.6 (safe, includes CVE-2025-68664 fix). "
        "Blocking old langchain package to prevent accidental installation."
    ),
    # Other potentially dangerous packages
    "eval": (
        "Package name suggests code evaluation capabilities. "
        "Use with extreme caution in production."
    ),
    "exec": (
        "Package name suggests code execution capabilities. "
        "Use with extreme caution in production."
    ),
}


def check_requirements_file(requirements_path: Path) -> List[Dict[str, str]]:
    """
    Check requirements file for blocked packages.
    
    Args:
        requirements_path: Path to requirements file
        
    Returns:
        List of violations with package name and reason
    """
    violations = []
    
    if not requirements_path.exists():
        return violations
    
    with open(requirements_path, "r") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            
            # Skip comments and empty lines
            if not line or line.startswith("#"):
                continue
            
            # Extract package name (before ==, >=, <=, etc.)
            package_name = line.split("==")[0].split(">=")[0].split("<=")[0].split(">")[0].split("<")[0].split("~=")[0].split("!=")[0].strip()
            package_name = package_name.split("[")[0].strip()  # Remove extras like [dev]
            
            # Check for version constraints on langchain (old package)
            # Block langchain package if version is <= 0.1.10 (vulnerable to CVE-2024-28088)
            if package_name == "langchain":
                # Extract version if present
                version_part = None
                for op in ["==", ">=", "<=", ">", "<", "~=", "!="]:
                    if op in line:
                        version_part = line.split(op)[1].split()[0].split("#")[0].strip()
                        break
                
                if version_part:
                    # Check if version is vulnerable (<= 0.1.10)
                    try:
                        from packaging import version
                        if version.parse(version_part) <= version.parse("0.1.10"):
                            violations.append({
                                "package": package_name,
                                "reason": BLOCKED_PACKAGES.get(package_name, "Vulnerable version (CVE-2024-28088)"),
                                "file": str(requirements_path),
                                "line": line_num,
                                "line_content": line,
                                "version": version_part,
                            })
                            continue  # Skip further checks for this line
                    except Exception:
                        # If version parsing fails, warn but don't block (might be >= constraint)
                        pass
                else:
                    # No version specified - warn that it might be vulnerable
                    violations.append({
                        "package": package_name,
                        "reason": f"{BLOCKED_PACKAGES.get(package_name, 'Vulnerable version')} (no version constraint - may install vulnerable version)",
                        "file": str(requirements_path),
                        "line": line_num,
                        "line_content": line,
                    })
                    continue  # Skip further checks for this line
            
            # Check if package is blocked (exact name match)
            if package_name in BLOCKED_PACKAGES:
                violations.append({
                    "package": package_name,
                    "reason": BLOCKED_PACKAGES[package_name],
                    "file": str(requirements_path),
                    "line": line_num,
                    "line_content": line,
                })
    
    return violations


def check_installed_packages() -> List[Dict[str, str]]:
    """
    Check currently installed packages for blocked dependencies.
    
    Returns:
        List of violations with package name and reason
    """
    violations = []
    
    try:
        result = subprocess.run(
            ["pip", "list", "--format=json"],
            capture_output=True,
            text=True,
            check=True,
        )
        
        import json
        installed_packages = json.loads(result.stdout)
        
        for package in installed_packages:
            package_name = package["name"].lower()
            
            # Check exact match
            if package_name in BLOCKED_PACKAGES:
                violations.append({
                    "package": package_name,
                    "reason": BLOCKED_PACKAGES[package_name],
                    "version": package.get("version", "unknown"),
                    "source": "installed_packages",
                })
            
            # Check for blocked patterns
            for blocked_name, reason in BLOCKED_PACKAGES.items():
                if blocked_name.lower() in package_name or package_name in blocked_name.lower():
                    if package_name not in [v["package"] for v in violations]:
                        violations.append({
                            "package": package_name,
                            "reason": f"Matches blocked pattern '{blocked_name}': {reason}",
                            "version": package.get("version", "unknown"),
                            "source": "installed_packages",
                        })
    
    except subprocess.CalledProcessError as e:
        print(f"Error checking installed packages: {e}", file=sys.stderr)
        return violations
    except json.JSONDecodeError as e:
        print(f"Error parsing pip list output: {e}", file=sys.stderr)
        return violations
    
    return violations


def main():
    """Main entry point for dependency blocklist checker."""
    parser = argparse.ArgumentParser(
        description="Check for blocked dependencies in requirements files and installed packages"
    )
    parser.add_argument(
        "--check-installed",
        action="store_true",
        help="Also check currently installed packages",
    )
    parser.add_argument(
        "--requirements",
        type=str,
        default="requirements.txt",
        help="Path to requirements file (default: requirements.txt)",
    )
    parser.add_argument(
        "--exit-on-violation",
        action="store_true",
        help="Exit with non-zero code if violations are found",
    )
    
    args = parser.parse_args()
    
    # Find project root
    project_root = Path(__file__).parent.parent.parent
    requirements_path = project_root / args.requirements
    
    violations = []
    
    # Check requirements file
    print(f"Checking {requirements_path}...")
    file_violations = check_requirements_file(requirements_path)
    violations.extend(file_violations)
    
    # Check installed packages if requested
    if args.check_installed:
        print("Checking installed packages...")
        installed_violations = check_installed_packages()
        violations.extend(installed_violations)
    
    # Report violations
    if violations:
        print("\n" + "=" * 80)
        print("SECURITY VIOLATIONS DETECTED")
        print("=" * 80)
        
        for violation in violations:
            print(f"\n❌ BLOCKED PACKAGE: {violation['package']}")
            print(f"   Reason: {violation['reason']}")
            if "file" in violation:
                print(f"   File: {violation['file']}:{violation['line']}")
                print(f"   Line: {violation['line_content']}")
            if "version" in violation:
                print(f"   Installed Version: {violation['version']}")
        
        print("\n" + "=" * 80)
        print("RECOMMENDATION: Remove or replace these packages immediately.")
        print("=" * 80 + "\n")
        
        if args.exit_on_violation:
            sys.exit(1)
    else:
        print("✓ No blocked packages found.")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

