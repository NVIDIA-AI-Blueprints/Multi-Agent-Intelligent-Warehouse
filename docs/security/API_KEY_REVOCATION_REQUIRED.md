# ⚠️ CRITICAL: API Key Revocation Required

## Summary

On **December 25, 2025**, a security audit identified that a `.env.backup` file containing hardcoded NVIDIA NGC API keys was previously committed to git history. This file has been **permanently removed** from all git branches and history, but the exposed keys must be **immediately revoked** and regenerated.

## Exposed API Keys

The following NVIDIA NGC API keys were exposed in the `.env.backup` file and must be revoked:

1. **RAIL_API_KEY** (Line 26)
   - Key: `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`
   - Used for: NeMo Guardrails service

2. **NEMO_RETRIEVER_API_KEY** (Line 37)
   - Key: `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`
   - Used for: NeMo Retriever service

3. **NEMO_OCR_API_KEY** (Line 38)
   - Key: `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`
   - Used for: NeMo OCR service

4. **NEMO_PARSE_API_KEY** (Line 39)
   - Key: `nvapi-xB777sxDLhhDDUtNfL3rHnV_jON7VI3KccDGEp43`
   - Used for: NeMo Parse service

5. **LLAMA_NANO_VL_API_KEY** (Line 40)
   - Key: `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`
   - Used for: Llama Nano Vision-Language model

6. **LLAMA_70B_API_KEY** (Line 41)
   - Key: `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`
   - Used for: Llama 70B model

**Note:** All keys appear to be the same value, which suggests they may have been copied from a single source. If you have multiple distinct keys, ensure all are revoked.

## Actions Taken

✅ **Completed:**
- Removed `.env.backup` file from entire git history using `git filter-branch`
- Updated `.gitignore` to prevent future commits of `.env.backup` and `.env.*.backup` files
- Force-pushed cleaned history to both remote repositories (`origin` and `nvidia`)
- Verified no hardcoded keys exist in current codebase

## Required Actions

### 1. Revoke Exposed API Keys (URGENT)

**Steps to revoke NVIDIA NGC API keys:**

1. **Log in to NVIDIA NGC Portal:**
   - Visit: https://ngc.nvidia.com/
   - Sign in with your NVIDIA account

2. **Navigate to API Keys:**
   - Go to your account settings
   - Find the "API Keys" or "Keys" section

3. **Revoke the exposed keys:**
   - Locate each of the exposed keys listed above
   - Click "Revoke" or "Delete" for each key
   - Confirm the revocation

4. **Verify revocation:**
   - Ensure all exposed keys are removed from your account
   - Check that no active services are using these keys

### 2. Generate New API Keys

After revoking the exposed keys, generate new ones:

1. **Create new API keys:**
   - In the NVIDIA NGC Portal, create new API keys
   - Use descriptive names (e.g., "Warehouse Assistant - Production")

2. **Update your `.env` file:**
   ```bash
   # Update these values in your .env file
   RAIL_API_KEY=nvapi-<your-new-key>
   NEMO_RETRIEVER_API_KEY=nvapi-<your-new-key>
   NEMO_OCR_API_KEY=nvapi-<your-new-key>
   NEMO_PARSE_API_KEY=nvapi-<your-new-key>
   LLAMA_NANO_VL_API_KEY=nvapi-<your-new-key>
   LLAMA_70B_API_KEY=nvapi-<your-new-key>
   ```

3. **Restart services:**
   - Restart any running services that use these API keys
   - Verify services are working with new keys

### 3. Security Best Practices

To prevent future exposure:

- ✅ **Never commit `.env` files or backup files** to version control
- ✅ **Use `.gitignore`** to exclude sensitive files (already configured)
- ✅ **Use environment variables** instead of hardcoded values
- ✅ **Rotate API keys regularly** (quarterly recommended)
- ✅ **Use separate keys** for different environments (dev/staging/prod)
- ✅ **Monitor API key usage** in NVIDIA NGC Portal for suspicious activity

## Verification

After revoking keys, verify:

1. **Check git history:**
   ```bash
   git log --all --full-history --source -- ".env.backup"
   # Should return no results
   ```

2. **Verify .gitignore:**
   ```bash
   grep "\.env\.backup" .gitignore
   # Should show: .env.backup
   ```

3. **Test new API keys:**
   - Verify all NVIDIA services are working with new keys
   - Check application logs for authentication errors

## Timeline

- **Discovery:** December 25, 2025
- **Removal from git:** December 25, 2025
- **Revocation deadline:** **IMMEDIATELY** (within 24 hours)

## Contact

If you have questions or need assistance:
- Review NVIDIA NGC documentation: https://docs.nvidia.com/ngc/
- Contact NVIDIA support if you notice suspicious activity on your account

## References

- NVIDIA NGC Portal: https://ngc.nvidia.com/
- NVIDIA API Documentation: https://docs.nvidia.com/ngc/ngc-api/
- Project Security Guidelines: See `docs/security/` directory

---

**Status:** ⚠️ **ACTION REQUIRED** - Keys must be revoked immediately

**Last Updated:** December 25, 2025

