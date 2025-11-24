# Fixing WebSocket and Source Map Errors

## Problem
You're seeing these errors in Firefox:
- `Firefox can't establish a connection to the server at ws://localhost:3001/ws`
- `Source map error: Error: NetworkError when attempting to fetch resource`

## Root Cause
These errors typically occur when:
1. You're accessing a **production build** (`npm run build`) instead of the **dev server** (`npm start`)
2. The dev server isn't running
3. Browser cache is serving old files

## Solution

### Option 1: Use the Development Server (Recommended)

1. **Stop any running processes:**
   ```bash
   # Kill any process on port 3001
   lsof -ti:3001 | xargs kill -9 2>/dev/null || true
   ```

2. **Clear caches:**
   ```bash
   cd src/ui/web
   rm -rf node_modules/.cache .eslintcache build
   ```

3. **Start the dev server:**
   ```bash
   npm start
   ```

4. **Access the app at:**
   - http://localhost:3001 (not the build folder!)

### Option 2: Disable Source Maps (If using production build)

If you must use the production build, you can disable source maps:

1. **Update `.env.local`:**
   ```bash
   GENERATE_SOURCEMAP=false
   ```

2. **Rebuild:**
   ```bash
   npm run build
   ```

### Option 3: Fix WebSocket Configuration

The `.env.local` file is already configured with:
```
WDS_SOCKET_HOST=localhost
WDS_SOCKET_PORT=3001
WDS_SOCKET_PATH=/ws
```

If you're behind a proxy or using a different setup, you may need to adjust these values.

## Verification

After starting the dev server, you should see:
- ✅ Webpack compilation successful
- ✅ No WebSocket connection errors in the browser console
- ✅ Hot Module Replacement (HMR) working (changes reflect immediately)

## Notes

- **Source map errors are usually harmless** - they only affect debugging experience
- **WebSocket errors prevent hot reloading** - the app will still work but won't auto-refresh on code changes
- Always use `npm start` for development, not the production build

