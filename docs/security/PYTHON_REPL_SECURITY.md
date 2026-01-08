# Python REPL Security Guidelines

## Overview

This document provides security guidelines for handling Python REPL (Read-Eval-Print Loop) and code execution capabilities in the Warehouse Operational Assistant system.

## Security Risks

### CVE-2024-38459: Unauthorized Python REPL Access

**Vulnerability**: LangChain Experimental provides Python REPL access without an opt-in step, allowing unauthorized code execution.

**Impact**: 
- **Critical (RCE)**: Remote Code Execution
- Attackers can execute arbitrary Python code
- Code runs with application permissions
- Can access environment variables, files, network, databases
- Full system compromise possible

**Related CVEs**:
- CVE-2024-38459: Unauthorized Python REPL access (incomplete fix for CVE-2024-27444)
- CVE-2024-46946: Code execution via `sympy.sympify` in LLMSymbolicMathChain
- CVE-2024-21513: Code execution via VectorSQLDatabaseChain
- CVE-2023-44467: Arbitrary code execution via PALChain

## Current Status

✅ **This codebase does NOT use `langchain-experimental`**

- Only `langchain-core>=1.2.6` is installed (patched for template injection and CVE-2025-68664)
- No Python REPL or PALChain components are used
- MCP tool discovery system includes security checks to block code execution tools

## Security Controls

### 1. Dependency Blocklist

Blocked packages are automatically detected and prevented:

```bash
# Check for blocked dependencies
python scripts/security/dependency_blocklist.py

# Check installed packages
python scripts/security/dependency_blocklist.py --check-installed
```

**Blocked Packages**:
- `langchain-experimental` (all versions < 0.0.61)
- `langchain_experimental` (alternative package name)
- Any package with code execution capabilities

### 2. MCP Tool Security Checks

The MCP tool discovery system automatically blocks dangerous tools:

**Blocked Tool Patterns**:
- `python.*repl`, `python.*exec`, `python.*eval`
- `pal.*chain`, `palchain`
- `code.*exec`, `execute.*code`, `run.*code`
- `shell.*exec`, `bash.*exec`, `command.*exec`
- `__import__`, `subprocess`, `os.system`

**Blocked Tool Names**:
- `python_repl`, `python_repl_tool`
- `python_exec`, `python_eval`
- `pal_chain`, `palchain`
- `code_executor`, `code_runner`
- `shell_executor`, `command_executor`

**Blocked Capabilities**:
- `code_execution`, `python_execution`
- `code_evaluation`, `shell_execution`
- `repl_access`, `python_repl`

### 3. Security Validation

All tools are validated before registration:

```python
from src.api.services.mcp.security import validate_tool_security, is_tool_blocked

# Check if tool is blocked
is_blocked, reason = is_tool_blocked(
    tool_name="python_repl",
    tool_description="Execute Python code",
    tool_capabilities=["code_execution"],
)

# Validate tool security (raises SecurityViolationError if blocked)
validate_tool_security(
    tool_name="python_repl",
    tool_description="Execute Python code",
)
```

## If Python REPL is Required (Future)

### ⚠️ **DO NOT USE IN PRODUCTION WITHOUT STRICT CONTROLS**

If you absolutely need Python REPL functionality:

### 1. Upgrade to Secure Version

```bash
# Minimum secure version
pip install "langchain-experimental>=0.0.61"
```

### 2. Explicit Opt-In

```python
import os

# Require explicit opt-in via environment variable
ENABLE_PYTHON_REPL = os.getenv("ENABLE_PYTHON_REPL", "false").lower() == "true"

if not ENABLE_PYTHON_REPL:
    raise SecurityError("Python REPL is disabled in production")

# Only then import and use
from langchain_experimental import PythonREPL
```

### 3. Sandbox Execution

**Option A: RestrictedPython**

```python
from RestrictedPython import compile_restricted, safe_globals
from RestrictedPython.Guards import safe_builtins

# Create restricted execution environment
restricted_globals = {
    **safe_globals,
    "__builtins__": safe_builtins,
    # Add only necessary builtins
}

# Compile and execute in restricted environment
code = compile_restricted(user_code, "<string>", "exec")
exec(code, restricted_globals)
```

**Option B: Docker Container**

```python
import docker

client = docker.from_env()

# Execute code in isolated container
container = client.containers.run(
    "python:3.11-slim",
    command=f"python -c '{sanitized_code}'",
    remove=True,
    network_disabled=True,  # No network access
    mem_limit="128m",       # Memory limit
    cpu_period=100000,
    cpu_quota=50000,        # CPU limit
    read_only=True,         # Read-only filesystem
)
```

**Option C: Restricted Subprocess**

```python
import subprocess
import tempfile
import os

# Create temporary file with code
with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
    f.write(sanitized_code)
    temp_file = f.name

try:
    # Execute in restricted subprocess
    result = subprocess.run(
        ["python", "-u", temp_file],
        capture_output=True,
        timeout=5,  # Timeout
        cwd="/tmp",  # Restricted directory
        env={},      # No environment variables
    )
finally:
    os.unlink(temp_file)  # Cleanup
```

### 4. Input Validation

```python
import re
from typing import List

# Blocked keywords and patterns
BLOCKED_KEYWORDS = [
    "import", "__import__", "eval", "exec", "compile",
    "open", "file", "input", "raw_input",
    "subprocess", "os.system", "os.popen",
    "__builtins__", "__globals__", "__locals__",
]

BLOCKED_PATTERNS = [
    r"__.*__",  # Magic methods
    r"\.system\(", r"\.popen\(",  # System calls
    r"subprocess\.",
    r"import\s+os", r"import\s+sys",
]

def validate_python_code(code: str) -> bool:
    """Validate Python code for dangerous patterns."""
    code_lower = code.lower()
    
    # Check for blocked keywords
    for keyword in BLOCKED_KEYWORDS:
        if keyword in code_lower:
            return False
    
    # Check for blocked patterns
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, code):
            return False
    
    return True
```

### 5. Security Configuration

```python
# config/security.py
class SecurityConfig:
    """Security configuration for code execution."""
    
    # Python REPL settings
    ENABLE_PYTHON_REPL: bool = False  # Default: disabled
    PYTHON_REPL_TIMEOUT: int = 5  # seconds
    PYTHON_REPL_MEMORY_LIMIT: str = "128m"
    PYTHON_REPL_CPU_LIMIT: float = 0.5
    
    # Allowed imports (whitelist)
    ALLOWED_IMPORTS: List[str] = [
        "math",
        "datetime",
        "json",
        # Add only necessary modules
    ]
    
    # Blocked imports (blacklist)
    BLOCKED_IMPORTS: List[str] = [
        "os", "sys", "subprocess",
        "importlib", "__builtin__",
        "eval", "exec", "compile",
    ]
    
    # Execution environment
    USE_SANDBOX: bool = True
    SANDBOX_TYPE: str = "docker"  # or "restricted_python"
```

### 6. Audit Logging

```python
import logging
from datetime import datetime

logger = logging.getLogger("security")

def log_code_execution(
    code: str,
    user: str,
    result: str,
    execution_time: float,
    success: bool,
):
    """Log all code execution attempts for audit."""
    logger.warning(
        f"CODE_EXECUTION: user={user}, "
        f"code_length={len(code)}, "
        f"execution_time={execution_time:.2f}s, "
        f"success={success}, "
        f"timestamp={datetime.utcnow().isoformat()}"
    )
    
    # Store in audit database
    audit_db.log_execution({
        "user": user,
        "code_hash": hash(code),  # Don't store actual code
        "result": result[:1000],  # Limit result size
        "execution_time": execution_time,
        "success": success,
        "timestamp": datetime.utcnow(),
    })
```

## Best Practices

### ✅ DO

- **Always use explicit opt-in** for code execution features
- **Sandbox all code execution** in isolated environments
- **Validate and sanitize all inputs** before execution
- **Implement timeouts** to prevent resource exhaustion
- **Log all execution attempts** for audit purposes
- **Use whitelists** for allowed operations
- **Limit resource usage** (CPU, memory, disk)
- **Run with minimal permissions** (principle of least privilege)
- **Monitor for suspicious patterns** in code execution

### ❌ DON'T

- **Never enable Python REPL by default** in production
- **Never execute code with full application permissions**
- **Never trust user input** without validation
- **Never allow network access** from code execution
- **Never allow file system access** beyond necessary directories
- **Never allow imports** of dangerous modules (os, sys, subprocess)
- **Never skip audit logging** for code execution
- **Never use eval() or exec()** on untrusted input

## Monitoring and Alerting

Set up monitoring for:

1. **Code execution attempts**: Alert on any attempt to use Python REPL
2. **Blocked tool registrations**: Monitor security violations
3. **Suspicious patterns**: Detect potential injection attempts
4. **Resource usage**: Alert on excessive CPU/memory usage
5. **Execution failures**: Monitor for exploitation attempts

## Incident Response

If unauthorized code execution is detected:

1. **Immediately disable** the affected service
2. **Review audit logs** to identify the attack vector
3. **Assess impact**: Check for data access, system changes
4. **Rotate credentials**: Change all API keys, tokens, passwords
5. **Patch vulnerabilities**: Update to secure versions
6. **Review security controls**: Strengthen defenses
7. **Document incident**: Create post-mortem report

## References

- [CVE-2024-38459](https://nvd.nist.gov/vuln/detail/CVE-2024-38459)
- [CVE-2024-46946](https://nvd.nist.gov/vuln/detail/CVE-2024-46946)
- [CVE-2024-21513](https://nvd.nist.gov/vuln/detail/CVE-2024-21513)
- [CVE-2023-44467](https://nvd.nist.gov/vuln/detail/CVE-2023-44467)
- [LangChain Security Documentation](https://python.langchain.com/docs/security/)
- [OWASP Code Injection](https://owasp.org/www-community/attacks/Code_Injection)

## Contact

For security concerns, contact the security team or refer to `SECURITY.md`.

