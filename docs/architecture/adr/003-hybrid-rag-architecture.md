# ADR-003: Hybrid RAG Architecture

## Status

**Accepted** - 2025-09-12

## Context

The Warehouse Operational Assistant requires a robust retrieval system that can handle:

- Structured data queries (inventory, equipment, operations)
- Unstructured data search (documents, procedures, policies)
- Real-time data access with low latency
- High accuracy and relevance for warehouse operations
- Scalability for large datasets
- Integration with multiple data sources

We need to choose between various retrieval approaches:

- Pure vector search (semantic only)
- Pure SQL search (structured only)
- Hybrid approach (combining both)
- Graph-based retrieval
- Multi-modal retrieval

## Decision

We will implement a **Hybrid RAG (Retrieval-Augmented Generation) Architecture** that combines:

### Core Components

1. **Structured Retriever** (PostgreSQL/TimescaleDB)
   - SQL-based queries for structured data
   - Real-time operational data
   - Inventory, equipment, and operations data
   - High precision for exact matches

2. **Vector Retriever** (Milvus)
   - Semantic search for unstructured data
   - Document and procedure search
   - Natural language queries
   - High recall for semantic matches

3. **Hybrid Ranker** (Context Synthesis)
   - Combines results from both retrievers
   - Intelligent ranking and scoring
   - Evidence-based relevance scoring
   - Context-aware result synthesis

### Architecture Overview

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   User Query    │    │  Hybrid RAG     │    │   Data Sources  │
│                 │    │   System        │    │                 │
│  ┌───────────┐  │    │  ┌───────────┐  │    │  ┌───────────┐  │
│  │  Natural  │──┼────┼──│  Query    │  │    │  │PostgreSQL │  │
│  │ Language  │  │    │  │ Router    │  │    │  │/Timescale │  │
│  └───────────┘  │    │  └───────────┘  │    │  └───────────┘  │
│                 │    │        │        │    │                 │
│                 │    │  ┌─────┴─────┐  │    │  ┌───────────┐  │
│                 │    │  │           │  │    │  │   Milvus  │  │
│                 │    │  │  Hybrid   │  │    │  │  Vector   │  │
│                 │    │  │  Ranker   │  │    │  │   Store   │  │
│                 │    │  │           │  │    │  └───────────┘  │
│                 │    │  └─────┬─────┘  │    │                 │
│                 │    │        │        │    │  ┌───────────┐  │
│                 │    │  ┌─────┴─────┐  │    │  │ External │  │
│                 │    │  │  Context  │  │    │  │  Systems  │  │
│                 │    │  │ Synthesis │  │    │  │ (WMS,ERP) │  │
│                 │    │  └───────────┘  │    │  └───────────┘  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### Data Flow

1. **Query Processing**: Parse and understand user query
2. **Query Routing**: Determine which retrievers to use
3. **Parallel Retrieval**: Execute queries on both systems
4. **Result Ranking**: Score and rank results from both sources
5. **Context Synthesis**: Combine results into coherent context
6. **Response Generation**: Generate final response using synthesized context

## Rationale

### Why Hybrid RAG

1. **Best of Both Worlds**: Combines precision of SQL with recall of vector search
2. **Warehouse-Specific**: Optimized for warehouse operations data patterns
3. **Real-time Capability**: Handles both real-time and historical data
4. **Scalability**: Scales with both structured and unstructured data growth
5. **Accuracy**: Higher accuracy through evidence-based scoring
6. **Flexibility**: Adapts to different query types and data sources

### Alternatives Considered

1. **Pure Vector Search**:
   - Pros: Simple, good for semantic search
   - Cons: Poor for structured data, limited precision
   - Decision: Rejected due to poor structured data handling

2. **Pure SQL Search**:
   - Pros: High precision, real-time data
   - Cons: Poor for natural language, limited semantic understanding
   - Decision: Rejected due to poor natural language handling

3. **Graph-Based Retrieval**:
   - Pros: Good for relationship queries
   - Cons: Complex setup, limited for warehouse data
   - Decision: Rejected due to complexity and limited applicability

4. **Multi-Modal Retrieval**:
   - Pros: Handles multiple data types
   - Cons: Overkill for current needs, complex implementation
   - Decision: Rejected due to complexity and current needs

### Trade-offs

1. **Complexity vs. Performance**: More complex than single approach but better performance
2. **Latency vs. Accuracy**: Slightly higher latency but much better accuracy
3. **Maintenance vs. Features**: More components to maintain but better functionality

## Consequences

### Positive

- **High Accuracy**: Better results through evidence-based scoring
- **Comprehensive Coverage**: Handles both structured and unstructured data
- **Real-time Capability**: Access to real-time operational data
- **Scalability**: Scales with data growth
- **Flexibility**: Adapts to different query types

### Negative

- **Complexity**: More complex than single retrieval approach
- **Latency**: Slightly higher latency due to multiple retrievers
- **Maintenance**: More components to maintain and monitor
- **Resource Usage**: Higher resource usage due to multiple systems

### Risks

1. **System Complexity**: More complex system with more failure points
2. **Data Consistency**: Potential inconsistencies between data sources
3. **Performance Degradation**: System performance could degrade with scale
4. **Integration Issues**: Complex integration between different systems

### Mitigation Strategies

1. **Monitoring**: Comprehensive monitoring of all components
2. **Caching**: Intelligent caching to reduce latency
3. **Fallback**: Fallback mechanisms for system failures
4. **Data Validation**: Regular data consistency checks
5. **Performance Testing**: Regular performance testing and optimization

## Implementation Plan

### Phase 1: Core Retrieval Systems
- [x] PostgreSQL/TimescaleDB structured retriever
- [x] Milvus vector retriever
- [x] Basic query routing
- [x] Simple result combination

### Phase 2: Hybrid Ranking
- [x] Evidence-based scoring system
- [x] Context synthesis
- [x] Intelligent ranking algorithms
- [x] Performance optimization

### Phase 3: Advanced Features
- [x] Clarifying questions system
- [x] SQL path optimization
- [x] Advanced caching strategies
- [x] Monitoring and metrics

### Phase 4: Production Optimization
- [ ] Performance tuning
- [ ] Cost optimization
- [ ] Advanced monitoring
- [ ] Documentation and training

## Technical Implementation

### Structured Retriever

```python
class StructuredRetriever:
    def __init__(self, db_connection):
        self.db = db_connection
    
    async def search(self, query: str, filters: Dict = None) -> List[Dict]:
        # Parse query into SQL
        sql_query = self.parse_query(query, filters)
        
        # Execute query
        results = await self.db.fetch_all(sql_query)
        
        # Format results
        return self.format_results(results)
```

### Vector Retriever

```python
class VectorRetriever:
    def __init__(self, milvus_client, embeddings_service):
        self.milvus = milvus_client
        self.embeddings = embeddings_service
    
    async def search(self, query: str, top_k: int = 10) -> List[Dict]:
        # Generate embeddings
        query_embedding = await self.embeddings.embed(query)
        
        # Search vector database
        results = await self.milvus.search(
            collection_name="documents",
            query_vectors=[query_embedding],
            top_k=top_k
        )
        
        # Format results
        return self.format_results(results)
```

### Hybrid Ranker

```python
class HybridRanker:
    def __init__(self, structured_retriever, vector_retriever):
        self.structured = structured_retriever
        self.vector = vector_retriever
    
    async def search(self, query: str, filters: Dict = None) -> List[Dict]:
        # Parallel retrieval
        structured_results = await self.structured.search(query, filters)
        vector_results = await self.vector.search(query)
        
        # Combine and rank results
        combined_results = self.combine_results(
            structured_results, 
            vector_results
        )
        
        # Score and rank
        ranked_results = self.score_and_rank(combined_results, query)
        
        return ranked_results
```

## Monitoring and Metrics

### Key Metrics

- **Retrieval Performance**:
  - Query latency (p50, p95, p99)
  - Query success rate
  - Result relevance score
  - Cache hit rate

- **System Health**:
  - Database connection status
  - Vector database status
  - Memory usage
  - CPU usage

- **Quality Metrics**:
  - User satisfaction scores
  - Query success rate
  - Result accuracy
  - Response time

### Alerts

- High query latency (>2 seconds)
- Low query success rate (<95%)
- Database connection failures
- Vector database failures
- High memory usage (>80%)
- Low cache hit rate (<70%)

## Configuration

### Environment Variables

```bash
# Database Configuration
DB_HOST=localhost
DB_PORT=5435
DB_NAME=warehouse_assistant
DB_USER=warehouse_user
DB_PASSWORD=warehouse_pass

# Vector Database Configuration
MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_USER=root
MILVUS_PASSWORD=Milvus

# Retrieval Configuration
RETRIEVAL_CACHE_TTL=3600
RETRIEVAL_MAX_RESULTS=50
RETRIEVAL_TIMEOUT=30
```

### Service Configuration

```python
RETRIEVAL_CONFIG = {
    "structured": {
        "timeout": 10,
        "max_results": 100,
        "cache_ttl": 3600
    },
    "vector": {
        "timeout": 5,
        "max_results": 50,
        "similarity_threshold": 0.7
    },
    "hybrid": {
        "timeout": 30,
        "max_results": 50,
        "ranking_weights": {
            "structured": 0.6,
            "vector": 0.4
        }
    }
}
```

## Future Considerations

### Potential Enhancements

1. **Advanced Ranking**: Machine learning-based ranking
2. **Query Understanding**: Better query parsing and understanding
3. **Multi-Modal**: Support for images and other data types
4. **Real-time Updates**: Real-time index updates
5. **Personalization**: User-specific result ranking

### Migration Strategy

If we need to change the retrieval approach:

1. **Abstraction Layer**: Implement abstraction layer for retrieval
2. **Gradual Migration**: Phased migration to new approach
3. **Data Preservation**: Ensure all data is preserved
4. **Performance Comparison**: Compare performance before and after

### Deprecation Strategy

If we need to deprecate the hybrid approach:

1. **Single Approach**: Migrate to single retrieval approach
2. **Data Migration**: Migrate data to new system
3. **Performance Optimization**: Optimize single approach for best performance
4. **Gradual Transition**: Phased transition to new approach

## References

- [Hybrid Search Best Practices](https://docs.milvus.io/docs/hybrid_search.md)
- [PostgreSQL Full-Text Search](https://www.postgresql.org/docs/current/textsearch.html)
- [Vector Search Optimization](https://docs.milvus.io/docs/performance_tuning.md)
- [RAG Architecture Patterns](https://docs.llamaindex.ai/en/stable/getting_started/concepts.html)
- [Evidence-Based Retrieval](https://arxiv.org/abs/2305.14627)
