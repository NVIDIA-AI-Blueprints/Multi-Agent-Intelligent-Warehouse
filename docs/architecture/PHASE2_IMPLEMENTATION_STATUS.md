# Phase 2: Performance Optimization - Implementation Status


> **Historical document**
>
> This file reflects an earlier MAIW implementation phase and may not describe the current MAIW v2 architecture. See [ARCHITECTURE.md](ARCHITECTURE.md) and the project [README](../../README.md) for the current authoritative design.

## Current Issues Found

### Issue 1: Missing Layout Detection in Router Flow
**Location**: `src/api/routers/document.py:1004-1010`
**Problem**: OCR is called without `layout_result` parameter, but `extract_text()` requires it
**Impact**: This may cause runtime errors or OCR may be using an empty dict
**Fix Required**: Add layout detection before OCR, or make layout_result optional

### Issue 2: Sequential Processing
**Location**: `src/api/routers/document.py:998-1019`
**Problem**: All stages run sequentially
**Impact**: Slower processing time
**Optimization**: Parallelize OCR + Layout Detection

## Implementation Plan

### Step 1: Fix Current Bug (CRITICAL - Must do first)
- Add LayoutDetectionService to router flow
- Ensure OCR receives proper layout_result
- Test that current flow works correctly

### Step 2: Parallel Processing (Low Risk)
- Use `asyncio.gather()` to run OCR and Layout Detection in parallel
- Both depend on preprocessing_result, but are independent
- OCR can work with minimal/empty layout initially, then enhance later

### Step 3: Caching (Medium Risk)
- Create Redis cache service
- Cache status queries (30s TTL)
- Cache embeddings (24h TTL, content-hash based)
- Cache API responses (1h TTL)

### Step 4: Frontend Optimization (Higher Risk)
- Implement SSE endpoint for real-time updates
- Replace polling with SSE connection
- Add exponential backoff fallback
- Add optimistic UI updates

## Files Created So Far

1. ✅ `docs/architecture/PHASE2_PERFORMANCE_PLAN.md` - Overall plan
2. ✅ `src/api/services/document/parallel_executor.py` - Parallel execution utilities
3. ✅ `docs/architecture/PHASE2_IMPLEMENTATION_STATUS.md` - This file

## Next Steps (Awaiting Approval)

1. **Fix Bug**: Add layout detection to router flow
2. **Implement Parallel**: Make OCR + Layout run in parallel
3. **Test**: Verify no regressions
4. **Measure**: Compare processing times

## Risk Assessment

- **Step 1 (Fix Bug)**: Low risk, fixes existing issue
- **Step 2 (Parallel)**: Low risk, independent operations
- **Step 3 (Caching)**: Medium risk, need cache invalidation
- **Step 4 (Frontend)**: Higher risk, user-facing changes

