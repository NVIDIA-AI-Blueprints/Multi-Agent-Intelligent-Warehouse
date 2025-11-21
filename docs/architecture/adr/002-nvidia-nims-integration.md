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

1. **NVIDIA NIM LLM** - Llama 3.1 70B
   - Primary language model for all AI operations
   - High-quality reasoning and generation capabilities
   - Optimized for production workloads

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
│  └───────────┘  │    │  │ (Llama 3.1)│  │    │  └───────────┘  │
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

## Rationale

### Why NVIDIA NIMs

1. **Production-Grade Performance**: Optimized for production workloads with high throughput and low latency
2. **Model Quality**: Llama 3.1 70B provides excellent reasoning and generation capabilities
3. **Embedding Quality**: NV-EmbedQA-E5-v5 provides high-quality 1024-dimensional embeddings
4. **NVIDIA Ecosystem**: Seamless integration with NVIDIA hardware and software stack
5. **Cost Efficiency**: Competitive pricing for enterprise workloads
6. **Reliability**: Enterprise-grade reliability and support

### Alternatives Considered

1. **OpenAI API**:
   - Pros: Mature, widely used, high-quality models
   - Cons: Vendor lock-in, cost concerns, rate limits
   - Decision: Rejected due to vendor lock-in and cost concerns

2. **Anthropic Claude**:
   - Pros: High-quality reasoning, safety features
   - Cons: Limited availability, vendor lock-in
   - Decision: Rejected due to limited availability and vendor lock-in

3. **Self-hosted Models**:
   - Pros: No vendor lock-in, cost control
   - Cons: Infrastructure complexity, maintenance overhead
   - Decision: Rejected due to complexity and maintenance overhead

4. **Hugging Face Transformers**:
   - Pros: Open source, no vendor lock-in
   - Cons: Performance concerns, infrastructure requirements
   - Decision: Rejected due to performance and infrastructure concerns

5. **Google Vertex AI**:
   - Pros: Google ecosystem, good models
   - Cons: Vendor lock-in, complex pricing
   - Decision: Rejected due to vendor lock-in and pricing complexity

### Trade-offs

1. **Vendor Lock-in vs. Performance**: NVIDIA NIMs provides excellent performance but creates vendor dependency
2. **Cost vs. Quality**: Higher cost than self-hosted solutions but better quality and reliability
3. **Complexity vs. Features**: More complex than simple API calls but provides enterprise features

## Consequences

### Positive

- **High-Quality AI**: Excellent reasoning and generation capabilities
- **Production Performance**: Optimized for production workloads
- **Reliable Service**: Enterprise-grade reliability and support
- **Cost Efficiency**: Competitive pricing for enterprise use
- **Easy Integration**: Simple API-based integration

### Negative

- **Vendor Lock-in**: Dependency on NVIDIA services
- **Cost**: Ongoing service costs
- **Network Dependency**: Requires stable network connectivity
- **API Rate Limits**: Potential rate limiting for high-volume usage

### Risks

1. **Service Outages**: NVIDIA NIMs service could experience outages
2. **Cost Escalation**: Usage costs could increase significantly
3. **API Changes**: NVIDIA could change API or deprecate services
4. **Performance Degradation**: Service performance could degrade

### Mitigation Strategies

1. **Fallback Options**: Implement fallback to alternative services
2. **Caching**: Implement intelligent caching to reduce API calls
3. **Rate Limiting**: Implement client-side rate limiting
4. **Monitoring**: Comprehensive monitoring and alerting
5. **Contract Negotiation**: Negotiate enterprise contracts for better terms

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
    "model": "llama-3.1-70b"
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
- [Llama 3.1 Model Card](https://huggingface.co/meta-llama/Llama-3.1-70B)
- [NV-EmbedQA-E5-v5 Model Card](https://huggingface.co/nvidia/NV-EmbedQA-E5-v5)
- [NVIDIA AI Enterprise](https://www.nvidia.com/en-us/data-center/products/ai-enterprise/)
- [Production AI Best Practices](https://docs.nvidia.com/nim/guides/production-deployment/)
