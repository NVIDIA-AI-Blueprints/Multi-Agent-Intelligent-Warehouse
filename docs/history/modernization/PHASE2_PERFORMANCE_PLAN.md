# Phase 2: Performance Optimization Plan


> **Historical document**
>
> This file reflects an earlier MAIW implementation phase and may not describe the current MAIW v2 architecture. See [ARCHITECTURE.md](ARCHITECTURE.md) and the project [README](../../README.md) for the current authoritative design.

## Overview
This document outlines the performance optimizations for the document processing pipeline, focusing on parallel processing, caching, and frontend real-time updates.

## Current State Analysis

### Sequential Processing
- **Current Flow**: Preprocessing → Layout Detection → OCR → LLM → Validation → Routing
- **Bottlenecks**: 
  - Layout detection runs after preprocessing completes
  - OCR waits for layout detection
  - All stages run sequentially
  - Frontend polls every 2 seconds

### Caching
- **Current State**: 
  - Redis available for job queue
  - No caching for API responses
  - No caching for embeddings
  - No caching for status queries

### Frontend Polling
- **Current State**:
  - Uses `setTimeout` with 2-second intervals
  - No exponential backoff
  - No WebSocket/SSE support
  - No optimistic updates

## Optimization Plan

### 1. Parallel Processing

#### 1.1 Parallelize Independent Stages
**Target**: OCR + Layout Detection can run in parallel after preprocessing

**Current Flow**:
```
Preprocessing → Layout Detection → OCR → LLM
```

**Optimized Flow**:
```
Preprocessing → [Layout Detection || OCR] → LLM
```

**Implementation**:
- Use `asyncio.gather()` to run layout detection and OCR in parallel
- Both depend on preprocessing_result, but are independent of each other
- OCR can start with basic preprocessing data, layout can enhance it later

**Files to Modify**:
- `src/api/routers/document.py` - `process_document_background()`
- Consider creating a parallel execution helper

#### 1.2 Batch API Calls
**Target**: Batch multiple document embeddings or similar operations

**Opportunities**:
- Multiple page embeddings in a single batch
- Multiple document validations (if processing multiple docs)
- Status queries for multiple documents

**Implementation**:
- Create batch processing utilities
- Use `asyncio.gather()` for concurrent API calls
- Implement batching logic in embedding service

**Files to Modify**:
- `src/api/agents/document/processing/embedding_indexing.py`
- Create `src/api/services/document/batch_processor.py`

### 2. Caching

#### 2.1 Redis Cache Service
**Target**: Cache API responses, embeddings, and status queries

**Implementation**:
- Create `src/api/services/document/cache_service.py`
- Cache key structure: `doc_cache:{cache_type}:{identifier}`
- TTL: 1 hour for API responses, 24 hours for embeddings
- Cache invalidation on document updates

**Cache Types**:
1. **API Response Cache**: Cache LLM API responses for similar documents
2. **Embedding Cache**: Cache embeddings for duplicate content (hash-based)
3. **Status Cache**: Cache document status queries (30 seconds TTL)

**Files to Create**:
- `src/api/services/document/cache_service.py`

**Files to Modify**:
- `src/api/agents/document/action_tools.py` - Add cache for status queries
- `src/api/agents/document/processing/embedding_indexing.py` - Cache embeddings
- `src/api/agents/document/validation/large_llm_judge.py` - Cache judge responses

#### 2.2 Embedding Deduplication
**Target**: Avoid re-computing embeddings for identical content

**Implementation**:
- Hash document content (text + structure)
- Check cache before computing embeddings
- Use content hash as cache key

**Files to Modify**:
- `src/api/agents/document/processing/embedding_indexing.py`

### 3. Frontend Optimization

#### 3.1 WebSocket/SSE Implementation
**Target**: Real-time status updates instead of polling

**Backend Implementation**:
- Create WebSocket endpoint: `/api/v1/document/ws/{document_id}`
- Or use Server-Sent Events (SSE): `/api/v1/document/stream/{document_id}`
- Broadcast status updates when stages complete

**Frontend Implementation**:
- Replace polling with WebSocket/SSE connection
- Handle reconnection logic
- Fallback to polling if WebSocket unavailable

**Files to Create**:
- `src/api/routers/document_ws.py` - WebSocket router
- Or modify `src/api/routers/document.py` to add SSE endpoint

**Files to Modify**:
- `src/ui/web/src/pages/DocumentExtraction.tsx` - Replace polling with WebSocket/SSE

#### 3.2 Exponential Backoff for Polling
**Target**: Reduce server load when WebSocket unavailable

**Implementation**:
- Start with 1 second interval
- Double interval on each poll (max 30 seconds)
- Reset to 1 second on status change
- Use exponential backoff utility

**Files to Modify**:
- `src/ui/web/src/pages/DocumentExtraction.tsx` - `monitorDocumentProcessing()`

#### 3.3 Optimistic UI Updates
**Target**: Immediate UI feedback before server confirmation

**Implementation**:
- Update UI immediately on user actions
- Show loading states optimistically
- Revert on error
- Use React state for optimistic updates

**Files to Modify**:
- `src/ui/web/src/pages/DocumentExtraction.tsx` - Add optimistic state updates

## Implementation Order

### Phase 2.1: Parallel Processing (Low Risk)
1. ✅ Analyze current sequential execution
2. Implement parallel OCR + Layout Detection
3. Test with single document
4. Measure performance improvement

### Phase 2.2: Caching (Medium Risk)
1. Create Redis cache service
2. Implement status query caching
3. Implement embedding caching
4. Test cache hit rates

### Phase 2.3: Frontend Optimization (Higher Risk)
1. Implement SSE endpoint (simpler than WebSocket)
2. Add exponential backoff fallback
3. Replace polling with SSE
4. Add optimistic UI updates
5. Test reconnection logic

## Testing Strategy

### Unit Tests
- Test parallel execution logic
- Test cache hit/miss scenarios
- Test exponential backoff calculation

### Integration Tests
- Test parallel processing with real documents
- Test cache invalidation
- Test WebSocket/SSE reconnection

### Performance Tests
- Measure processing time before/after parallelization
- Measure cache hit rates
- Measure frontend polling reduction

## Risk Assessment

### Low Risk
- Parallel OCR + Layout Detection (independent operations)
- Status query caching (read-only, easy to invalidate)

### Medium Risk
- Embedding caching (need to ensure content hash is correct)
- API response caching (need to handle cache invalidation)

### Higher Risk
- WebSocket/SSE implementation (new infrastructure)
- Frontend polling replacement (user-facing changes)

## Success Metrics

### Performance
- **Target**: 30-40% reduction in processing time for parallel stages
- **Target**: 50%+ cache hit rate for status queries
- **Target**: 80%+ cache hit rate for duplicate embeddings

### Frontend
- **Target**: Eliminate 90%+ of polling requests
- **Target**: < 1 second latency for status updates
- **Target**: Smooth UI updates without flickering

## Rollback Plan

Each optimization is independent and can be rolled back:
1. Parallel processing: Revert to sequential execution
2. Caching: Disable cache service, fallback to direct queries
3. WebSocket/SSE: Revert to polling, keep exponential backoff

## Notes

- All changes must be backward compatible
- Maintain fallback mechanisms for all new features
- Add feature flags for gradual rollout
- Monitor performance metrics after deployment

