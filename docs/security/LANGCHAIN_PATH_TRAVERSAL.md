# LangChain Path Traversal Security (CVE-2024-28088)

## Overview

This document provides security guidelines for handling LangChain Hub path loading to prevent directory traversal attacks.

## Vulnerability Details

### CVE-2024-28088 / GHSA-h59x-p739-982c

**Vulnerability**: Directory traversal in `load_chain`, `load_prompt`, and `load_agent` functions when an attacker controls the path parameter.

**Affected Versions**:
- `langchain <= 0.1.10`
- `langchain-core < 0.1.29`

**Patched Versions**:
- `langchain >= 0.1.11`
- `langchain-core >= 0.1.29`

**Impact**:
- **High**: Disclosure of API keys for LLM services
- **Critical**: Remote Code Execution (RCE)
- Bypasses intended behavior of loading only from `hwchase17/langchain-hub` GitHub repository

**Attack Vector**:
```python
# Vulnerable code
load_chain("lc://chains/../../something")  # Directory traversal
load_chain(user_input)  # If user_input contains ../ sequences
```

## Current Status

✅ **This codebase is NOT affected**

- **Current version**: `langchain-core==0.3.80` (well above patched version 0.1.29+)
- **No usage**: The codebase does NOT use `load_chain`, `load_prompt`, or `load_agent` functions
- **No LangChain Hub**: The codebase does NOT load chains from LangChain Hub (`lc://` paths)
- **Safe usage**: Only uses `langchain_core.messages` and `langchain_core.tools` which are safe

## Security Controls

### 1. Path Validation

The security module includes path validation utilities:

```python
from src.api.services.mcp.security import validate_chain_path, safe_load_chain_path

# Validate a path
is_valid, reason = validate_chain_path("lc://chains/my_chain", allow_lc_hub=True)
if not is_valid:
    raise SecurityError(f"Invalid path: {reason}")

# Use allowlist mapping (recommended)
ALLOWED_CHAINS = {
    "summarize": "lc://chains/summarize",
    "qa": "lc://chains/qa",
}

safe_path = safe_load_chain_path("summarize", ALLOWED_CHAINS)
```

### 2. Blocked Patterns

The following patterns are automatically blocked:
- `../` - Directory traversal (Unix/Linux)
- `..\\` - Directory traversal (Windows)
- `..` - Any parent directory reference
- `/` - Absolute paths (Unix)
- `C:` - Absolute paths (Windows drive letters)
- `\\` - UNC paths (Windows network)

### 3. Defense-in-Depth

Even with patched versions, implement additional protections:

**A. Use Allowlist Mapping**

```python
# ❌ DON'T: Direct user input
chain = load_chain(user_input)  # Vulnerable to path traversal

# ✅ DO: Use allowlist
ALLOWED_CHAINS = {
    "summarize": "lc://chains/summarize",
    "qa": "lc://chains/qa",
    "chat": "lc://chains/chat",
}

def safe_load_chain(user_chain_name: str):
    if user_chain_name not in ALLOWED_CHAINS:
        raise ValueError(f"Chain '{user_chain_name}' not allowed")
    
    hub_path = ALLOWED_CHAINS[user_chain_name]
    
    # Additional validation
    from src.api.services.mcp.security import validate_chain_path
    is_valid, reason = validate_chain_path(hub_path, allow_lc_hub=True)
    if not is_valid:
        raise SecurityError(f"Invalid path: {reason}")
    
    return load_chain(hub_path)
```

**B. Reject Traversal Tokens**

```python
def validate_chain_path(path: str) -> bool:
    """Validate chain path before loading."""
    # Check for traversal patterns
    if ".." in path:
        raise ValueError("Directory traversal detected")
    
    if path.startswith(("/", "\\")):
        raise ValueError("Absolute paths not allowed")
    
    # Only allow lc:// hub paths
    if not path.startswith("lc://"):
        raise ValueError("Only lc:// hub paths allowed")
    
    return True
```

**C. Pin Hub Assets**

If loading from LangChain Hub in production:

```python
# Pin to specific commit/ref to prevent loading attacker-modified configs
chain = load_chain(
    "lc://chains/my_chain",
    hub_ref="abc123def456"  # Specific commit hash
)
```

**D. Treat Loaded Configs as Untrusted**

Remember: Chain configs can include:
- Tool definitions
- Prompt templates
- Model settings
- API keys (if stored in config)

Prefer:
- Internal "known good" registry
- Signed artifacts
- Bundling chains with your app

## If LangChain Hub Loading is Required (Future)

### ⚠️ **DO NOT USE WITHOUT STRICT CONTROLS**

If you need to load chains from LangChain Hub:

### 1. Upgrade to Secure Version

```bash
# Minimum secure versions
pip install "langchain>=0.1.11" "langchain-core>=0.1.29"
```

### 2. Use Allowlist Mapping

```python
# Define allowed chains
ALLOWED_CHAINS = {
    "summarize": "lc://chains/summarize",
    "qa": "lc://chains/qa",
}

# Use allowlist function
from src.api.services.mcp.security import safe_load_chain_path

def load_user_chain(chain_name: str):
    """Safely load a chain using allowlist."""
    hub_path = safe_load_chain_path(chain_name, ALLOWED_CHAINS)
    return load_chain(hub_path)
```

### 3. Validate All Paths

```python
from src.api.services.mcp.security import validate_chain_path

def load_chain_safely(path: str):
    """Load chain with path validation."""
    is_valid, reason = validate_chain_path(path, allow_lc_hub=True)
    if not is_valid:
        raise SecurityViolationError(f"Invalid path: {reason}")
    
    return load_chain(path)
```

### 4. Audit Logging

```python
import logging
from datetime import datetime

logger = logging.getLogger("security")

def log_chain_load(chain_name: str, hub_path: str, user: str):
    """Log all chain loading attempts for audit."""
    logger.warning(
        f"CHAIN_LOAD: user={user}, "
        f"chain_name={chain_name}, "
        f"hub_path={hub_path}, "
        f"timestamp={datetime.utcnow().isoformat()}"
    )
```

## Best Practices

### ✅ DO

- **Always use allowlist mapping** for user-provided chain names
- **Validate all paths** before passing to `load_chain`
- **Pin hub assets** to specific commits/refs in production
- **Treat loaded configs as untrusted** and validate them
- **Log all chain loading** attempts for audit
- **Use internal registries** instead of external hubs when possible
- **Bundle chains with your app** for production deployments

### ❌ DON'T

- **Never pass raw user input** directly to `load_chain`
- **Never trust paths** from external sources
- **Never skip path validation** even with patched versions
- **Never load chains dynamically** based on user input without allowlist
- **Never store chain paths in user-editable databases** without validation
- **Never allow LLMs to dynamically decide** which `lc://` path to load
- **Never skip audit logging** for chain loading

## Exploitation Scenarios

### Scenario 1: Direct User Input

```python
# ❌ VULNERABLE
user_chain = request.json["chain_name"]  # User input: "lc://chains/../../secrets"
chain = load_chain(user_chain)  # Loads from wrong location
```

### Scenario 2: Database-Stored Paths

```python
# ❌ VULNERABLE
chain_path = db.get_chain_path(user_id)  # User can edit: "../malicious"
chain = load_chain(chain_path)
```

### Scenario 3: LLM-Generated Paths

```python
# ❌ VULNERABLE
llm_response = llm.generate("Which chain should I load?")
chain_path = extract_path(llm_response)  # LLM suggests: "lc://chains/../../evil"
chain = load_chain(chain_path)
```

### ✅ Secure Implementation

```python
# ✅ SECURE
ALLOWED_CHAINS = {
    "summarize": "lc://chains/summarize",
    "qa": "lc://chains/qa",
}

user_chain = request.json["chain_name"]
if user_chain not in ALLOWED_CHAINS:
    raise ValueError("Chain not allowed")

hub_path = ALLOWED_CHAINS[user_chain]
chain = load_chain(hub_path)
```

## Monitoring and Alerting

Set up monitoring for:

1. **Chain loading attempts**: Alert on any `load_chain` calls
2. **Path validation failures**: Monitor for traversal attempts
3. **Suspicious patterns**: Detect `../` sequences in paths
4. **Unusual chain names**: Alert on chains not in allowlist
5. **Failed validations**: Monitor security violations

## Incident Response

If path traversal is detected:

1. **Immediately disable** chain loading functionality
2. **Review audit logs** to identify attack vector
3. **Assess impact**: Check for API key exposure, config access
4. **Rotate credentials**: Change all API keys, tokens
5. **Patch immediately**: Upgrade to secure versions
6. **Review security controls**: Strengthen path validation
7. **Document incident**: Create post-mortem report

## References

- [CVE-2024-28088](https://nvd.nist.gov/vuln/detail/CVE-2024-28088)
- [GHSA-h59x-p739-982c](https://github.com/advisories/GHSA-h59x-p739-982c)
- [OWASP Path Traversal](https://owasp.org/www-community/attacks/Path_Traversal)
- [LangChain Security Documentation](https://python.langchain.com/docs/security/)

## Contact

For security concerns, contact the security team or refer to `SECURITY.md`.

