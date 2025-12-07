# ADR-002: NVIDIA NIMs Integration

## Status

**Accepted** - 2025-09-12

## Context

The Warehouse Operational Assistant requires high-quality AI capabilities for:

- Natural language understanding and generation
- Semantic search and retrieval
- Multi-agent reasoning and decision making
- Real-time warehouse operations assistance
- Production-grade performance and reliability

We need to choose between various AI service providers and models, considering factors like:

- Model quality and capabilities
- Performance and latency
- Cost and scalability
- Integration complexity
- Vendor lock-in risks
- Production readiness

## Decision

We will integrate NVIDIA NIMs (NVIDIA Inference Microservices) as our primary AI service provider, specifically:

### Core AI Services

1. **NVIDIA NIM LLM** - Llama 3.3 Nemotron Super 49B v1.5
   - Primary language model for all AI operations
   - High-quality reasoning and generation capabilities
   - Optimized for production workloads
   - Enhanced performance with 131K context window

2. **NVIDIA NIM Embeddings** - NV-EmbedQA-E5-v5
   - 1024-dimensional embeddings for semantic search
   - Optimized for question-answering and retrieval
   - High-quality vector representations

### Integration Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Application   │    │   NVIDIA NIMs   │    │   Vector Store  │
│                 │    │                 │    │                 │
│  ┌───────────┐  │    │  ┌───────────┐  │    │  ┌───────────┐  │
│  │   Agents  │──┼────┼──│    LLM    │  │    │  │   Milvus  │  │
│  └───────────┘  │    │  │(Llama 3.3)│  │    │  └───────────┘  │
│                 │    │  └───────────┘  │    │                 │
│  ┌───────────┐  │    │  ┌───────────┐  │    │                 │
│  │ Retrieval │──┼────┼──│Embeddings │  │    │                 │
│  │  System   │  │    │  │(NV-EmbedQA)│  │    │                 │
│  └───────────┘  │    │  └───────────┘  │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### Service Configuration

- **LLM Service**: `http://localhost:8000/v1`
- **Embeddings Service**: `http://localhost:8001/v1`
- **Authentication**: API key-based
- **Timeout**: 30 seconds for LLM, 10 seconds for embeddings
- **Retry Policy**: 3 attempts with exponential backoff

## Implementation Plan

### Phase 1: Core Integration
- [x] NVIDIA NIMs service setup
- [x] LLM service integration
- [x] Embeddings service integration
- [x] Basic error handling and retry logic

### Phase 2: Advanced Features
- [x] Caching layer implementation
- [x] Performance optimization
- [x] Monitoring and metrics
- [x] Fallback mechanisms

### Phase 3: Production Deployment
- [x] Production environment setup
- [x] Load testing and optimization
- [x] Monitoring and alerting
- [x] Documentation and training

### Phase 4: Optimization
- [ ] Advanced caching strategies
- [ ] Performance tuning
- [ ] Cost optimization
- [ ] Advanced monitoring

## Monitoring and Metrics

### Key Metrics

- **LLM Metrics**:
  - Request latency (p50, p95, p99)
  - Request success rate
  - Token generation rate
  - Error rate by error type

- **Embeddings Metrics**:
  - Request latency (p50, p95, p99)
  - Request success rate
  - Embedding generation rate
  - Error rate by error type

- **Cost Metrics**:
  - API calls per hour/day
  - Token usage
  - Cost per request
  - Monthly cost trends

### Alerts

- High latency (>5 seconds for LLM, >2 seconds for embeddings)
- High error rate (>5%)
- Service unavailability
- Cost threshold exceeded
- Rate limit exceeded

## Configuration

### Environment Variables

```bash
# NVIDIA NIMs Configuration
NIM_LLM_BASE_URL=http://localhost:8000/v1
NIM_LLM_API_KEY=your-nim-llm-api-key
NIM_LLM_TIMEOUT=30
NIM_LLM_MAX_RETRIES=3

NIM_EMBEDDINGS_BASE_URL=http://localhost:8001/v1
NIM_EMBEDDINGS_API_KEY=your-nim-embeddings-api-key
NIM_EMBEDDINGS_TIMEOUT=10
NIM_EMBEDDINGS_MAX_RETRIES=3
```

### Service Configuration

```python
# LLM Service Configuration
LLM_CONFIG = {
    "base_url": "http://localhost:8000/v1",
    "api_key": "your-api-key",
    "timeout": 30,
    "max_retries": 3,
    "retry_delay": 1.0,
    "model": "llama-3.3-nemotron-super-49b-v1"
}

# Embeddings Service Configuration
EMBEDDINGS_CONFIG = {
    "base_url": "http://localhost:8001/v1",
    "api_key": "your-api-key",
    "timeout": 10,
    "max_retries": 3,
    "retry_delay": 0.5,
    "model": "nv-embedqa-e5-v5"
}
```

## Future Considerations

### Potential Enhancements

1. **Model Updates**: Upgrade to newer models as they become available
2. **Custom Models**: Fine-tune models for warehouse-specific tasks
3. **Multi-Model Support**: Support for multiple models for different use cases
4. **Advanced Caching**: Implement more sophisticated caching strategies
5. **Cost Optimization**: Implement cost optimization strategies

### Migration Strategy

If we need to migrate away from NVIDIA NIMs:

1. **Abstraction Layer**: Implement abstraction layer for AI services
2. **Multi-Provider Support**: Support multiple AI providers
3. **Gradual Migration**: Phased migration to new provider
4. **Data Preservation**: Ensure all AI-generated data is preserved

### Deprecation Strategy

If NVIDIA NIMs is deprecated:

1. **Early Warning**: Monitor for deprecation announcements
2. **Migration Plan**: Develop migration plan to alternative services
3. **Data Export**: Export all AI-generated data
4. **Service Replacement**: Replace with alternative services

## References

- [NVIDIA NIMs Documentation](https://docs.nvidia.com/nim/)
- [Llama 3.3 Nemotron Super 49B Model Card](https://huggingface.co/nvidia/Llama-3.3-Nemotron-Super-49B)
- [NV-EmbedQA-E5-v5 Model Card](https://huggingface.co/nvidia/NV-EmbedQA-E5-v5)
- [NVIDIA AI Enterprise](https://www.nvidia.com/en-us/data-center/products/ai-enterprise/)
- [Production AI Best Practices](https://docs.nvidia.com/nim/guides/production-deployment/)
