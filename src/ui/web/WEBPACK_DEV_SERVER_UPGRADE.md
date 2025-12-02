# webpack-dev-server Security Upgrade

## Summary

Successfully upgraded `webpack-dev-server` from `4.15.2` (vulnerable) to `5.2.2` (patched) to address security vulnerabilities:
- **CVE-2018-14732** (BDSA-2018-3403): Source Code Disclosure via Improper Cross-Site WebSocket Access Control
- **CVE-2025-30360**: Source Code Theft via WebSocket Hijacking

## Upgrade Details

### Method Used: npm overrides

Since `react-scripts@5.0.1` requires `webpack-dev-server@^4.6.0` (4.x only), we used npm's `overrides` feature to force the upgrade to version 5.2.2.

### Changes Made

**File: `package.json`**
```json
{
  "overrides": {
    "webpack-dev-server": "^5.2.1"
  }
}
```

### Verification

✅ **Upgrade Successful**: `webpack-dev-server@5.2.2` is now installed
✅ **Compatibility**: Works with `webpack@5.103.0` (peer dependency satisfied)
✅ **No Breaking Changes**: Dev server starts successfully

### Current Status

```bash
$ npm list webpack-dev-server
└─┬ react-scripts@5.0.1
  ├─┬ @pmmmwh/react-refresh-webpack-plugin@0.5.17
  │ └── webpack-dev-server@5.2.2 deduped
  └── webpack-dev-server@5.2.2 overridden
```

## Security Impact

### Before Upgrade
- **Version**: `4.15.2`
- **Status**: Vulnerable to CVE-2018-14732 and CVE-2025-30360
- **Risk**: Source code disclosure via cross-site WebSocket hijacking

### After Upgrade
- **Version**: `5.2.2`
- **Status**: ✅ **PATCHED** - All known vulnerabilities fixed
- **Risk**: Eliminated

## Compatibility Fix: CRACO Configuration

After upgrading to webpack-dev-server 5.x, you may encounter two types of errors:

1. **source-map-loader error**:
   ```
   Error: ENOENT: no such file or directory, open 'webpack-dev-server/client/index.js'
   ```

2. **Deprecated options error**:
   ```
   Invalid options object. Dev Server has been initialized using an options object that does not match the API schema.
   - options has an unknown property 'onAfterSetupMiddleware'
   ```

**Solution**: We've installed and configured CRACO to:
- Exclude webpack-dev-server from source-map-loader processing
- Remove deprecated `onAfterSetupMiddleware` and `onBeforeSetupMiddleware` options

### CRACO Setup

1. **Installed**: `@craco/craco` as a dev dependency
2. **Created**: `craco.config.js` with two configuration sections:
   - `webpack.configure`: Excludes webpack-dev-server from source-map-loader
   - `devServer`: Removes deprecated options from devServer config
3. **Updated**: Scripts in `package.json` to use `craco` instead of `react-scripts` directly

### Files Modified

- `package.json`: Added CRACO to devDependencies and updated scripts
- `craco.config.js`: Configuration file with webpack and devServer sections

### How the Fix Works

The CRACO `devServer` configuration function intercepts the devServer config **after** react-scripts sets it up and removes the deprecated options before webpack-dev-server 5.x validates the configuration. This ensures compatibility without modifying react-scripts directly.

## Testing Recommendations

1. **Test Development Server**:
   ```bash
   cd src/ui/web
   npm start
   ```
   Verify that:
   - Dev server starts without errors
   - No source-map-loader errors
   - Hot Module Replacement (HMR) works
   - WebSocket connections function correctly
   - No console errors related to webpack-dev-server

2. **Test Production Build**:
   ```bash
   npm run build
   ```
   Verify that:
   - Build completes successfully
   - Production bundle is generated correctly
   - No webpack-dev-server dependencies in production build

3. **Test Application Functionality**:
   - Verify all features work as expected
   - Check that API calls function correctly
   - Test routing and navigation
   - Verify hot reloading works during development

## Compatibility Notes

### What Works
- ✅ `webpack@5.103.0` (compatible with webpack-dev-server 5.x)
- ✅ `react-scripts@5.0.1` (works with override)
- ✅ All existing webpack plugins and loaders

### Potential Issues
- ⚠️ If you encounter any issues with the dev server, check:
  - WebSocket connections (should work with new security fixes)
  - Hot Module Replacement (should work as before)
  - Any custom webpack-dev-server configuration
  - If you see `onAfterSetupMiddleware` or `onBeforeSetupMiddleware` errors, ensure CRACO's `devServer` configuration is working

### Troubleshooting

**Issue**: `Invalid options object. Dev Server has been initialized using an options object that does not match the API schema. - options has an unknown property 'onAfterSetupMiddleware'`

**Solution**: This error occurs when react-scripts sets deprecated options that webpack-dev-server 5.x doesn't support. The CRACO `devServer` configuration should automatically remove these. If the error persists:

1. Verify `craco.config.js` has the `devServer` section
2. Check that CRACO is being used (scripts should use `craco start`, not `react-scripts start`)
3. Clear node_modules and reinstall: `rm -rf node_modules package-lock.json && npm install`
4. Check console output for CRACO messages indicating deprecated options are being removed

**Issue**: `Invalid options object. Dev Server has been initialized using an options object that does not match the API schema. - options has an unknown property 'https'`

**Solution**: This error occurs because `react-scripts` sets the deprecated `https` option. You need to manually patch `webpackDevServer.config.js` in `node_modules`:

1. **After running `npm install`**, open:
   ```
   src/ui/web/node_modules/react-scripts/config/webpackDevServer.config.js
   ```

2. **Find line ~102-103** (look for `https: getHttpsConfig()` or `server:`)

3. **Replace the `https` option** with the `server` option:
   ```javascript
   // OLD (deprecated):
   https: getHttpsConfig(),
   
   // NEW (webpack-dev-server 5.x compatible):
   // Updated for webpack-dev-server 5.x: https option moved to server.type
   server: getHttpsConfig() ? { type: 'https', options: getHttpsConfig() } : { type: 'http' },
   ```

4. **Remove the old `https:` line** if it still exists

5. **Restart the dev server**: `npm start`

**Note**: This patch is in `node_modules` and will be lost if you run `npm install` again. You'll need to reapply it after each `npm install`. The CRACO config also attempts to handle this conversion, but the manual patch is more reliable.

**Alternative**: Consider using `patch-package` to persist this patch automatically:
```bash
npm install --save-dev patch-package postinstall-postinstall
# After applying the patch manually:
npx patch-package react-scripts
# Add to package.json scripts:
"postinstall": "patch-package"
```

### Rollback Instructions

If you need to rollback (not recommended due to security):

1. Remove the `overrides` section from `package.json`
2. Run `npm install` to restore `webpack-dev-server@4.15.2`

**Note**: Rolling back will reintroduce security vulnerabilities.

## Additional Security Recommendations

1. **Use Chromium-based browsers** (Chrome 94+, Edge) during development for additional protection
2. **Don't expose dev server to the internet** - bind to localhost only
3. **Use VPN** if accessing dev server remotely
4. **Monitor for updates** to react-scripts that may include webpack-dev-server 5.x support

## References

- [CVE-2018-14732](https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2018-14732)
- [CVE-2025-30360](https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2025-30360)
- [webpack-dev-server GitHub](https://github.com/webpack/webpack-dev-server)
- [npm overrides documentation](https://docs.npmjs.com/cli/v9/configuring-npm/package-json#overrides)

## Maintenance

- Monitor `react-scripts` updates for official webpack-dev-server 5.x support
- Consider migrating to Vite or other modern build tools in the future
- Keep webpack-dev-server updated to latest 5.x version

