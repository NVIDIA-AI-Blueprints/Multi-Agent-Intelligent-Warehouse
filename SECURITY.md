# Security

NVIDIA is dedicated to the security and trust of our software products and services, including all source code repositories managed through our organization.

If you need to report a security issue, please use the appropriate contact points outlined below. Please do not report security vulnerabilities through GitHub.

## Reporting Potential Security Vulnerability in an NVIDIA Product

To report a potential security vulnerability in any NVIDIA product:

- **Web**: [Security Vulnerability Submission Form](https://app.intigriti.com/programs/nvidia/nvidiavdp/detail)
- **E-Mail**: psirt@nvidia.com
  - We encourage you to use the following PGP key for secure email communication: [NVIDIA public PGP Key for communication](https://www.nvidia.com/en-us/security/pgp-key/)
  - Please include the following information:
    - Product/Driver name and version/branch that contains the vulnerability
    - Type of vulnerability (code execution, denial of service, buffer overflow, etc.)
    - Instructions to reproduce the vulnerability
    - Proof-of-concept or exploit code
    - Potential impact of the vulnerability, including how an attacker could exploit the vulnerability

While NVIDIA currently does not have a bug bounty program, we do offer acknowledgement when an externally reported security issue is addressed under our coordinated vulnerability disclosure policy. Please visit our Product Security Incident Response Team (PSIRT) policies page for more information.

## NVIDIA Product Security

For all security-related concerns, please visit NVIDIA's Product Security portal at https://www.nvidia.com/en-us/security

## Project Security Documentation

This project includes additional security documentation:

- **[Python REPL Security Guidelines](docs/security/PYTHON_REPL_SECURITY.md)**: Guidelines for handling Python REPL and code execution capabilities, including protection against CVE-2024-38459 and related vulnerabilities.

- **[LangChain Path Traversal Security](docs/security/LANGCHAIN_PATH_TRAVERSAL.md)**: Guidelines for preventing directory traversal attacks in LangChain Hub path loading, including protection against CVE-2024-28088.

- **[Axios SSRF Protection](docs/security/AXIOS_SSRF_PROTECTION.md)**: Guidelines for preventing Server-Side Request Forgery (SSRF) attacks in Axios HTTP client usage, including protection against CVE-2025-27152.

## Security Tools

### Dependency Blocklist Checker

Check for blocked dependencies that should not be installed:

```bash
# Check requirements.txt
python scripts/security/dependency_blocklist.py

# Check installed packages
python scripts/security/dependency_blocklist.py --check-installed

# Exit on violation (for CI/CD)
python scripts/security/dependency_blocklist.py --exit-on-violation
```

This tool automatically detects and blocks:
- `langchain-experimental` (Python REPL vulnerabilities)
- Other packages with code execution capabilities

