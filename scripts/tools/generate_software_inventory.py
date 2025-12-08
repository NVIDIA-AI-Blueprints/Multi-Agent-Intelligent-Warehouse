#!/usr/bin/env python3
"""
Generate Software Inventory
Extracts package information from requirements.txt and package.json
and queries PyPI/npm registries for license and author information.
"""

import json
import re
import urllib.request
import urllib.error
import time
import email.header
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path

def get_pypi_info(package_name: str, version: Optional[str] = None) -> Dict:
    """Get package information from PyPI."""
    try:
        url = f"https://pypi.org/pypi/{package_name}/json"
        if version:
            url = f"https://pypi.org/pypi/{package_name}/{version}/json"
        
        with urllib.request.urlopen(url, timeout=5) as response:
            data = json.loads(response.read())
            info = data.get('info', {})
            
            # Extract license information
            license_info = info.get('license', '')
            if not license_info or license_info == 'UNKNOWN':
                # Try to get from classifiers
                classifiers = info.get('classifiers', [])
                for classifier in classifiers:
                    if classifier.startswith('License ::'):
                        license_info = classifier.split('::')[-1].strip()
                        break
            # Clean up license text (remove newlines and extra spaces, limit length)
            if license_info:
                license_info = ' '.join(license_info.split())
                # If license text is too long (like full license text), just use "MIT License" or first part
                if len(license_info) > 100:
                    # Try to extract just the license name
                    if 'MIT' in license_info:
                        license_info = 'MIT License'
                    elif 'Apache' in license_info:
                        license_info = 'Apache License'
                    elif 'BSD' in license_info:
                        license_info = 'BSD License'
                    else:
                        license_info = license_info[:50] + '...'
            
            # Get author information
            author = info.get('author', '')
            author_email = info.get('author_email', '')
            
            # Decode RFC 2047 encoded strings (like =?utf-8?q?...)
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
                    pass  # Keep original if decoding fails
            
            # Also decode author_email if it's encoded
            if author_email and '=?' in author_email:
                try:
                    decoded_parts = email.header.decode_header(author_email)
                    decoded_email = ''
                    for part in decoded_parts:
                        if isinstance(part[0], bytes):
                            encoding = part[1] or 'utf-8'
                            decoded_email += part[0].decode(encoding)
                        else:
                            decoded_email += part[0]
                    author_email = decoded_email.strip()
                except Exception:
                    pass  # Keep original if decoding fails
            
            if author_email:
                author = f"{author} <{author_email}>" if author else author_email
            
            # Truncate very long author lists
            if author and len(author) > 150:
                author = author[:147] + '...'
            
            # Get project URLs
            project_urls = info.get('project_urls', {})
            license_url = project_urls.get('License', '') or info.get('home_page', '')
            
            return {
                'name': info.get('name', package_name),
                'version': info.get('version', version or 'N/A'),
                'license': license_info or 'N/A',
                'license_url': license_url or f"https://pypi.org/project/{package_name}/",
                'author': author or 'N/A',
                'home_page': info.get('home_page', f"https://pypi.org/project/{package_name}/"),
                'source': 'PyPI',
                'distribution': 'pip'
            }
    except Exception as e:
        return {
            'name': package_name,
            'version': version or 'N/A',
            'license': 'N/A',
            'license_url': f"https://pypi.org/project/{package_name}/",
            'author': 'N/A',
            'home_page': f"https://pypi.org/project/{package_name}/",
            'source': 'PyPI',
            'distribution': 'pip',
            'error': str(e)
        }

def get_npm_info(package_name: str, version: Optional[str] = None) -> Dict:
    """Get package information from npm registry."""
    try:
        # Remove @scope if present for URL
        package_url_name = package_name.replace('/', '%2F')
        url = f"https://registry.npmjs.org/{package_url_name}"
        
        with urllib.request.urlopen(url, timeout=5) as response:
            data = json.loads(response.read())
            
            # Get latest version if version not specified
            if version:
                version_data = data.get('versions', {}).get(version, {})
            else:
                latest_version = data.get('dist-tags', {}).get('latest', '')
                version_data = data.get('versions', {}).get(latest_version, {})
            
            # Extract license
            license_info = version_data.get('license', '')
            if isinstance(license_info, dict):
                license_info = license_info.get('type', '')
            # Clean up license text (remove newlines and extra spaces)
            if license_info:
                license_info = ' '.join(license_info.split())
            
            # Get author
            author = version_data.get('author', {})
            if isinstance(author, dict):
                author_name = author.get('name', '')
                author_email = author.get('email', '')
                author = f"{author_name} <{author_email}>" if author_email else author_name
            elif isinstance(author, str):
                author = author
            else:
                author = 'N/A'
            
            homepage = version_data.get('homepage', '') or data.get('homepage', '')
            repository = version_data.get('repository', {})
            if isinstance(repository, dict):
                repo_url = repository.get('url', '')
                # Clean up git+https:// URLs
                if repo_url.startswith('git+'):
                    repo_url = repo_url[4:]
                if repo_url.endswith('.git'):
                    repo_url = repo_url[:-4]
            else:
                repo_url = ''
            
            # Try to construct license URL from repository
            license_url = homepage or repo_url or f"https://www.npmjs.com/package/{package_name}"
            # If we have a GitHub repo, try to link to license file
            if 'github.com' in repo_url:
                license_url = f"{repo_url}/blob/main/LICENSE" if repo_url else license_url
            
            return {
                'name': package_name,
                'version': version_data.get('version', version or 'N/A'),
                'license': license_info or 'N/A',
                'license_url': license_url,
                'author': author or 'N/A',
                'home_page': homepage or f"https://www.npmjs.com/package/{package_name}",
                'source': 'npm',
                'distribution': 'npm'
            }
    except Exception as e:
        return {
            'name': package_name,
            'version': version or 'N/A',
            'license': 'N/A',
            'license_url': f"https://www.npmjs.com/package/{package_name}",
            'author': 'N/A',
            'home_page': f"https://www.npmjs.com/package/{package_name}",
            'source': 'npm',
            'distribution': 'npm',
            'error': str(e)
        }

def parse_requirements(requirements_file: Path) -> List[Dict]:
    """Parse requirements.txt file."""
    packages = []
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
                package_name = re.sub(r'\[.*\]', '', package_spec)
                version = match.group(3) if match.group(3) else None
                
                packages.append({
                    'name': package_name,
                    'version': version,
                    'file': str(requirements_file)
                })
    
    return packages

def parse_package_json(package_json_file: Path) -> List[Dict]:
    """Parse package.json file."""
    packages = []
    with open(package_json_file, 'r') as f:
        data = json.load(f)
        
        # Get devDependencies
        dev_deps = data.get('devDependencies', {})
        for package_name, version_spec in dev_deps.items():
            # Remove ^ or ~ from version
            version = re.sub(r'[\^~]', '', version_spec) if version_spec else None
            packages.append({
                'name': package_name,
                'version': version,
                'file': str(package_json_file),
                'type': 'devDependency',
                'source': 'npm'  # Mark as npm package
            })
    
    return packages

def main():
    """Generate software inventory."""
    repo_root = Path(__file__).parent.parent.parent
    
    all_packages = []
    
    # Parse Python requirements
    requirements_files = [
        repo_root / 'requirements.txt',
        repo_root / 'requirements.docker.txt',
        repo_root / 'scripts' / 'requirements_synthetic_data.txt'
    ]
    
    for req_file in requirements_files:
        if req_file.exists():
            packages = parse_requirements(req_file)
            all_packages.extend(packages)
    
    # Parse Node.js package.json
    package_json = repo_root / 'package.json'
    if package_json.exists():
        packages = parse_package_json(package_json)
        all_packages.extend(packages)
    
    # Get information for each package
    print("Fetching package information...")
    inventory = []
    
    # Remove duplicates - keep the most specific version (exact version > minimum version)
    package_dict = {}
    for pkg in all_packages:
        name_lower = pkg['name'].lower()
        version = pkg.get('version')
        source = pkg.get('source', 'pypi')
        key = (name_lower, source)
        
        # If we haven't seen this package, or if this version is more specific (exact version vs None)
        if key not in package_dict or (version and not package_dict[key].get('version')):
            package_dict[key] = pkg
    
    unique_packages = list(package_dict.values())
    
    print(f"Processing {len(unique_packages)} unique packages (removed {len(all_packages) - len(unique_packages)} duplicates)...")
    
    for i, pkg in enumerate(unique_packages, 1):
        print(f"[{i}/{len(unique_packages)}] Fetching {pkg['name']}...")
        
        # Check if it's an npm package (starts with @ or from package.json)
        is_npm = (pkg.get('source') == 'npm' or 
                 pkg['name'].startswith('@') or 
                 'package.json' in str(pkg.get('file', '')))
        
        if is_npm:
            info = get_npm_info(pkg['name'], pkg.get('version'))
        else:
            info = get_pypi_info(pkg['name'], pkg.get('version'))
        
        info['file'] = pkg.get('file', 'N/A')
        inventory.append(info)
        
        # Rate limiting
        time.sleep(0.1)
    
    # Generate markdown table
    output_file = repo_root / 'docs' / 'SOFTWARE_INVENTORY.md'
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Get current date for "Last Updated"
    current_date = datetime.now().strftime("%Y-%m-%d")
    
    with open(output_file, 'w') as f:
        f.write("# Software Inventory\n\n")
        f.write("This document lists all third-party software packages used in this project, including their versions, licenses, authors, and sources.\n\n")
        f.write("**Generated:** Automatically from dependency files\n")
        f.write(f"**Last Updated:** {current_date}\n")
        f.write("**Generation Script:** `scripts/tools/generate_software_inventory.py`\n\n")
        f.write("## How to Regenerate\n\n")
        f.write("To regenerate this inventory with the latest package information:\n\n")
        f.write("```bash\n")
        f.write("# Activate virtual environment\n")
        f.write("source env/bin/activate\n\n")
        f.write("# Run the generation script\n")
        f.write("python scripts/tools/generate_software_inventory.py\n")
        f.write("```\n\n")
        f.write("The script automatically:\n")
        f.write("- Parses `requirements.txt`, `requirements.docker.txt`, and `scripts/requirements_synthetic_data.txt`\n")
        f.write("- Parses `package.json` for Node.js dependencies\n")
        f.write("- Queries PyPI and npm registries for package metadata\n")
        f.write("- Removes duplicates and formats the data into this table\n\n")
        f.write("## Python Packages (PyPI)\n\n")
        f.write("| Package Name | Version | License | License URL | Author | Source | Distribution Method |\n")
        f.write("|--------------|---------|---------|-------------|--------|--------|---------------------|\n")
        
        python_packages = [p for p in inventory if p.get('source') == 'PyPI']
        for pkg in sorted(python_packages, key=lambda x: x['name'].lower()):
            f.write(f"| {pkg['name']} | {pkg['version']} | {pkg['license']} | {pkg['license_url']} | {pkg['author']} | {pkg['source']} | {pkg['distribution']} |\n")
        
        f.write("\n## Node.js Packages (npm)\n\n")
        f.write("| Package Name | Version | License | License URL | Author | Source | Distribution Method |\n")
        f.write("|--------------|---------|---------|-------------|--------|--------|---------------------|\n")
        
        npm_packages = [p for p in inventory if p.get('source') == 'npm']
        for pkg in sorted(npm_packages, key=lambda x: x['name'].lower()):
            f.write(f"| {pkg['name']} | {pkg['version']} | {pkg['license']} | {pkg['license_url']} | {pkg['author']} | {pkg['source']} | {pkg['distribution']} |\n")
        
        f.write("\n## Notes\n\n")
        f.write("- **Source**: Location where the package was downloaded from (PyPI, npm)\n")
        f.write("- **Distribution Method**: Method used to install the package (pip, npm)\n")
        f.write("- **License URL**: Link to the package's license information\n")
        f.write("- Some packages may have missing information if the registry data is incomplete\n\n")
        f.write("## License Summary\n\n")
        
        # Count licenses
        license_counts = {}
        for pkg in inventory:
            license_name = pkg.get('license', 'N/A')
            license_counts[license_name] = license_counts.get(license_name, 0) + 1
        
        f.write("| License | Count |\n")
        f.write("|---------|-------|\n")
        for license_name, count in sorted(license_counts.items(), key=lambda x: -x[1]):
            f.write(f"| {license_name} | {count} |\n")
    
    print(f"\nSoftware inventory generated: {output_file}")
    print(f"Total packages: {len(inventory)}")

if __name__ == '__main__':
    main()

