# How to Fix Axios Webpack Errors

## Problem
Axios 1.13+ tries to bundle Node.js modules in browser builds, causing webpack errors.

## Solution Steps

1. **STOP the dev server completely** (Ctrl+C in the terminal where it's running)

2. **Clear webpack cache and node_modules cache:**
   ```bash
   cd src/ui/web
   rm -rf node_modules/.cache
   rm -rf .cache
   ```

3. **Verify CRACO is being used:**
   Check that `package.json` scripts use `craco`:
   ```bash
   grep "start" package.json
   ```
   Should show: `"start": "PORT=3001 craco start"`

4. **Restart the dev server:**
   ```bash
   npm start
   ```

5. **Look for this message in the console:**
   ```
   ✅ CRACO webpack config applied - Axios browser mode forced
   ```
   If you see this, CRACO is working.

6. **If errors persist:**
   - Check that you're using `npm start` (not `react-scripts start`)
   - Verify CRACO is installed: `npm list @craco/craco`
   - Check `craco.config.js` exists in `src/ui/web/`

## Alternative: If CRACO still doesn't work

If the above doesn't work, you may need to:
1. Delete `node_modules` and reinstall:
   ```bash
   rm -rf node_modules package-lock.json
   npm install
   npm start
   ```

2. Or check if there's a webpack cache that needs clearing:
   ```bash
   rm -rf node_modules/.cache .cache build
   npm start
   ```
