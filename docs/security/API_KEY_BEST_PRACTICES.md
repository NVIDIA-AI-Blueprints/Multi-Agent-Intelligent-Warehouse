# API Key Security Best Practices

## ⚠️ Critical Security Principle

**NEVER hardcode API keys, secrets, passwords, or tokens in source code.**

## Why This Matters

### Security Risks of Hardcoded Secrets

1. **Version Control Exposure**
   - Secrets committed to Git are permanently in history
   - Even if removed later, they remain in commit history
   - Anyone with repository access can see them
   - Public repositories expose secrets to the entire internet

2. **Code Sharing**
   - Hardcoded secrets are visible to all developers
   - Cannot be easily rotated without code changes
   - Secrets may be accidentally shared in screenshots, logs, or documentation

3. **Deployment Issues**
   - Same secrets used across all environments
   - Cannot use different keys for dev/staging/production
   - Difficult to manage and rotate keys

4. **Compliance Violations**
   - Violates security standards (OWASP, PCI-DSS, SOC 2)
   - Can lead to data breaches and legal issues
   - Fails security audits

## ✅ Current Implementation (Correct)

Our codebase correctly follows best practices:

```python
# ✅ CORRECT: Reading from environment variables
llm_api_key: str = os.getenv("NVIDIA_API_KEY", "")
embedding_api_key: str = os.getenv("EMBEDDING_API_KEY") or os.getenv("NVIDIA_API_KEY", "")
```

### What This Does Right

1. **No Hardcoded Secrets**: All API keys come from environment variables
2. **Flexible Configuration**: Different keys for different environments
3. **Secure Storage**: Keys stored in `.env` file (not committed to Git)
4. **Fallback Support**: Can use same key or different keys per service

## ❌ What NOT to Do

```python
# ❌ BAD: Hardcoded API key
llm_api_key: str = "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"

# ❌ BAD: Hardcoded in string
api_key = "brev_api_-2x95MrBJwU5BeKlHNkaFX62wiHX"

# ❌ BAD: In comments (still visible in code)
# API_KEY = "secret-key-here"
```

## ✅ Best Practices Checklist

### 1. Use Environment Variables

```python
# ✅ Good
api_key = os.getenv("API_KEY", "")
```

### 2. Provide Clear Defaults (Empty String, Not Real Keys)

```python
# ✅ Good: Empty string default
api_key = os.getenv("API_KEY", "")

# ❌ Bad: Real key as default
api_key = os.getenv("API_KEY", "real-secret-key-here")
```

### 3. Validate at Runtime

```python
# ✅ Good: Validate and warn
if not api_key:
    logger.warning("API_KEY not set. Service will not work.")
    raise ValueError("API_KEY environment variable is required")
```

### 4. Never Log Secrets

```python
# ✅ Good: Log that key is set, not the actual key
logger.info(f"API key configured: {bool(api_key)}")

# ❌ Bad: Logging the actual key
logger.info(f"API key: {api_key}")  # NEVER DO THIS
```

### 5. Use .env Files (Not Committed)

```bash
# .env file (in .gitignore)
NVIDIA_API_KEY=your-actual-key-here
EMBEDDING_API_KEY=your-actual-key-here
```

### 6. Provide .env.example (Committed)

```bash
# .env.example (committed to Git)
NVIDIA_API_KEY=your-nvidia-api-key-here
EMBEDDING_API_KEY=your-embedding-api-key-here
```

## Current Code Review

### ✅ Correct Implementation in `nim_client.py`

```python
@dataclass
class NIMConfig:
    """NVIDIA NIM configuration."""
    
    # ✅ Correct: Reading from environment variable
    llm_api_key: str = os.getenv("NVIDIA_API_KEY", "")
    
    # ✅ Correct: Reading from environment variable with fallback
    embedding_api_key: str = os.getenv("EMBEDDING_API_KEY") or os.getenv("NVIDIA_API_KEY", "")
    
    # ✅ Correct: Model identifier (not a secret, safe to have default)
    llm_model: str = os.getenv("LLM_MODEL", "nvcf:nvidia/llama-3.3-nemotron-super-49b-v1:dep-...")
    
    # ✅ Correct: Configuration values (not secrets)
    timeout: int = int(os.getenv("LLM_CLIENT_TIMEOUT", "120"))
```

### ✅ Validation in Code

```python
def _validate_config(self) -> None:
    """Validate NIM configuration and log warnings for common issues."""
    # ✅ Good: Validates without exposing the key
    if not self.config.llm_api_key or not self.config.llm_api_key.strip():
        logger.warning(
            "NVIDIA_API_KEY is not set or is empty. LLM requests will fail with authentication errors."
        )
    
    # ✅ Good: Logs configuration status without exposing secrets
    logger.info(
        f"api_key_set={bool(self.config.llm_api_key and self.config.llm_api_key.strip())}, "
        # Note: Does NOT log the actual key value
    )
```

## Environment Variable Setup

### Development

1. **Copy example file:**
   ```bash
   cp .env.example .env
   ```

2. **Edit .env file:**
   ```bash
   nano .env  # or your preferred editor
   ```

3. **Add your keys:**
   ```bash
   NVIDIA_API_KEY=your-actual-key-here
   EMBEDDING_API_KEY=your-actual-key-here
   ```

4. **Verify .env is in .gitignore:**
   ```bash
   # .gitignore should contain:
   .env
   .env.local
   .env.*.local
   ```

### Production

1. **Use secrets management:**
   - AWS Secrets Manager
   - HashiCorp Vault
   - Kubernetes Secrets
   - Environment variables in deployment platform

2. **Never commit .env files:**
   ```bash
   # Verify .env is ignored
   git check-ignore .env
   ```

3. **Rotate keys regularly:**
   - Change keys periodically
   - Revoke old keys
   - Update environment variables

## Security Checklist

- [x] All API keys read from environment variables
- [x] No hardcoded secrets in source code
- [x] .env file in .gitignore
- [x] .env.example provided (without real keys)
- [x] Validation and error messages for missing keys
- [x] Secrets never logged
- [x] Different keys for different environments
- [x] Documentation explains how to set keys

## Additional Security Measures

### 1. Key Rotation

```bash
# Rotate keys periodically
# 1. Generate new key
# 2. Update .env file
# 3. Restart services
# 4. Revoke old key
```

### 2. Least Privilege

- Use different keys for different services
- Limit key permissions
- Use service-specific keys when possible

### 3. Monitoring

- Monitor for unauthorized key usage
- Set up alerts for key exposure
- Log access attempts (without logging keys)

### 4. Code Reviews

- Always review code for hardcoded secrets
- Use tools like `git-secrets` or `truffleHog`
- Check commit history before merging

## Tools for Secret Detection

```bash
# Install git-secrets
git secrets --install

# Scan for secrets
truffleHog git file://. --json

# Check for exposed keys
gitleaks detect --source . --verbose
```

## Summary

✅ **Our codebase follows security best practices:**
- All API keys read from environment variables
- No hardcoded secrets
- Proper validation and error handling
- Secrets never logged

✅ **Configuration is secure:**
- Keys stored in .env (not committed)
- .env.example provided for reference
- Clear documentation for setup

⚠️ **Always remember:**
- Never commit .env files
- Never hardcode secrets
- Never log secrets
- Rotate keys regularly
- Use different keys per environment

