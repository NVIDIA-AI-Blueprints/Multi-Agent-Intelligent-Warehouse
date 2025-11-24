# Axios SSRF Protection

## Overview

This document describes the security measures implemented to protect against Server-Side Request Forgery (SSRF) attacks in Axios HTTP client usage.

## Vulnerability: CVE-2025-27152

**CVE**: CVE-2025-27152  
**Advisory**: [GHSA-4w2v-q235-vp99](https://github.com/axios/axios/security/advisories/GHSA-4w2v-q235-vp99)

### Description

Axios is vulnerable to SSRF attacks when:
1. A `baseURL` is configured in `axios.create()`
2. User-controlled input is passed as the request URL
3. The user input contains an absolute URL (e.g., `http://evil.com/api`)

In vulnerable versions, Axios would treat absolute URLs as "already full" and send the request to the attacker's host, bypassing the `baseURL` restriction.

### Affected Versions

- Axios < 1.8.2: Vulnerable in all adapters
- Axios 1.8.2: Fixed for `http` adapter only
- Axios 1.8.3+: Fixed for all adapters (`http`, `xhr`, `fetch`)

**Note**: Even in patched versions (1.8.3+), the `allowAbsoluteUrls` option defaults to `true`, making the application vulnerable unless explicitly disabled.

## Protection Measures

### 1. Upgrade Axios

**Status**: ✅ Implemented

Upgraded Axios from `^1.6.0` to `^1.8.3` in `src/ui/web/package.json`.

```json
{
  "dependencies": {
    "axios": "^1.8.3"
  }
}
```

### 2. Disable Absolute URLs

**Status**: ✅ Implemented

Set `allowAbsoluteUrls: false` in all `axios.create()` configurations:

```typescript
// src/ui/web/src/services/api.ts
const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60000,
  headers: {
    'Content-Type': 'application/json',
  },
  // Security: Prevent SSRF attacks by disallowing absolute URLs
  allowAbsoluteUrls: false,
});
```

This prevents Axios from processing absolute URLs even if they are passed as request paths.

### 3. Path Parameter Validation

**Status**: ✅ Implemented

Added `validatePathParam()` helper function to sanitize user-controlled path parameters:

```typescript
function validatePathParam(param: string, paramName: string = 'parameter'): string {
  // Reject absolute URLs
  if (param.startsWith('http://') || param.startsWith('https://') || param.startsWith('//')) {
    throw new Error(`Invalid ${paramName}: absolute URLs are not allowed`);
  }
  
  // Reject path traversal sequences
  if (param.includes('../') || param.includes('..\\')) {
    throw new Error(`Invalid ${paramName}: path traversal sequences are not allowed`);
  }
  
  // Reject control characters
  if (/[\x00-\x1F\x7F-\x9F\n\r]/.test(param)) {
    throw new Error(`Invalid ${paramName}: control characters are not allowed`);
  }
  
  return param.trim().replace(/^\/+|\/+$/g, '');
}
```

**Applied to**:
- `equipmentAPI.getAsset(asset_id)`
- `equipmentAPI.getAssetStatus(asset_id)`
- `equipmentAPI.getTelemetry(asset_id, ...)`
- `inventoryAPI.getItem(sku)`
- `inventoryAPI.updateItem(sku, ...)`
- `inventoryAPI.deleteItem(sku)`
- `documentAPI.getDocumentStatus(documentId)`
- `documentAPI.getDocumentResults(documentId)`
- `documentAPI.approveDocument(documentId, ...)`
- `documentAPI.rejectDocument(documentId, ...)`
- `InventoryAPI.getItemBySku(sku)`
- `InventoryAPI.updateItem(sku, ...)`

### 4. Relative URLs Only

**Status**: ✅ Implemented

All API base URLs are enforced to be relative paths:

```typescript
// Force relative path - never use absolute URLs
let API_BASE_URL = process.env.REACT_APP_API_URL || '/api/v1';

if (API_BASE_URL.startsWith('http://') || API_BASE_URL.startsWith('https://')) {
  console.warn('API_BASE_URL should be relative for proxy to work. Using /api/v1 instead.');
  API_BASE_URL = '/api/v1';
}
```

## Best Practices

### ✅ DO

1. **Always use `allowAbsoluteUrls: false`** when creating Axios instances with `baseURL`
2. **Validate all user-controlled path parameters** before using them in URLs
3. **Use relative URLs** for `baseURL` configuration
4. **Sanitize query parameters** using `URLSearchParams` or `encodeURIComponent()`
5. **Keep Axios updated** to the latest patched version

### ❌ DON'T

1. **Don't pass user input directly** as request URLs without validation
2. **Don't use absolute URLs** in `baseURL` configuration
3. **Don't disable `allowAbsoluteUrls`** unless absolutely necessary
4. **Don't trust environment variables** for base URLs without validation
5. **Don't bypass validation** even if you think the input is "safe"

## Testing

### Manual Testing

1. **Test absolute URL rejection**:
   ```typescript
   // Should throw error
   try {
     await equipmentAPI.getAsset('http://evil.com/api');
   } catch (error) {
     console.log('✅ Absolute URL rejected:', error.message);
   }
   ```

2. **Test path traversal rejection**:
   ```typescript
   // Should throw error
   try {
     await inventoryAPI.getItem('../../../etc/passwd');
   } catch (error) {
     console.log('✅ Path traversal rejected:', error.message);
   }
   ```

3. **Test normal operation**:
   ```typescript
   // Should work normally
   const asset = await equipmentAPI.getAsset('FL-01');
   console.log('✅ Normal operation works');
   ```

### Automated Testing

Add unit tests for `validatePathParam()`:

```typescript
describe('validatePathParam', () => {
  it('should reject absolute URLs', () => {
    expect(() => validatePathParam('http://evil.com')).toThrow();
    expect(() => validatePathParam('https://evil.com')).toThrow();
    expect(() => validatePathParam('//evil.com')).toThrow();
  });
  
  it('should reject path traversal', () => {
    expect(() => validatePathParam('../etc/passwd')).toThrow();
    expect(() => validatePathParam('..\\windows\\system32')).toThrow();
  });
  
  it('should accept valid parameters', () => {
    expect(validatePathParam('FL-01')).toBe('FL-01');
    expect(validatePathParam('SKU-12345')).toBe('SKU-12345');
  });
});
```

## Monitoring

Monitor for:
- Errors from `validatePathParam()` (potential attack attempts)
- Axios errors related to URL parsing
- Unusual network requests from the frontend
- Failed API calls with suspicious path parameters

## References

- [CVE-2025-27152](https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2025-27152)
- [Axios Security Advisory](https://github.com/axios/axios/security/advisories/GHSA-4w2v-q235-vp99)
- [Axios SSRF Fix Commit](https://github.com/axios/axios/commit/fb8eec214ce7744b5ca787f2c3b8339b2f54b00f)
- [OWASP SSRF Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html)

## Changelog

- **2025-01-XX**: Initial implementation
  - Upgraded Axios to 1.8.3
  - Added `allowAbsoluteUrls: false` to all Axios instances
  - Implemented `validatePathParam()` helper
  - Applied validation to all user-controlled path parameters

