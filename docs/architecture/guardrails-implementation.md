# NeMo Guardrails Implementation Overview

> **Historical implementation record.**
> This document reflects an earlier implementation phase (pre-MAIW v2) and may not describe
> the current MAIW v2 governance architecture. See [`docs/architecture/GOVERNANCE.md`](GOVERNANCE.md)
> for the current authoritative governance and authority-boundary design.

**Last Updated:** 2025-01-XX (historical)
**Status:** Historical — Phase 3 complete as of earlier implementation
**Implementation:** Parallel SDK and Pattern-Based Support

---

## Executive Summary

This document provides a comprehensive overview of the NeMo Guardrails implementation in the Warehouse Operational Assistant. The system supports both NVIDIA's NeMo Guardrails SDK (with Colang) and a pattern-based fallback implementation, allowing for runtime switching via feature flag.

**Current State (historical):** Dual implementation with feature flag control  
**Target State (historical):** Full NeMo Guardrails SDK integration with Colang-based programmable guardrails  
**Migration Status (historical):** Phase 3 Complete

---

## Architecture Overview

### Implementation Modes

The guardrails system supports two implementation modes:

1. **NeMo Guardrails SDK** (Phase 2+)
   - Uses NVIDIA's official SDK with Colang configuration
   - Programmable guardrails with intelligent pattern matching
   - Better accuracy and extensibility
   - Requires NVIDIA API keys

2. **Pattern-Based Matching** (Legacy/Fallback)
   - Custom implementation using regex patterns
   - Fast, lightweight, no external dependencies
   - Used as fallback when SDK unavailable
   - Fully backward compatible

### Feature Flag Control

```bash
# Enable SDK implementation
USE_NEMO_GUARDRAILS_SDK=true

# Use pattern-based implementation (default)
USE_NEMO_GUARDRAILS_SDK=false
```

The system automatically falls back to pattern-based implementation if:
- SDK is not installed
- SDK initialization fails
- API keys are not configured
- SDK encounters errors

---

## Implementation Details

### Core Components

#### 1. GuardrailsService (`src/api/services/guardrails/guardrails_service.py`)

Main service interface that supports both implementations:

```python
class GuardrailsService:
    """Service for NeMo Guardrails integration with multiple implementation modes."""
    
    def __init__(self, config: Optional[GuardrailsConfig] = None):
        # Automatically selects implementation based on feature flag
        # Falls back to pattern-based if SDK unavailable
```

**Key Features:**
- Automatic implementation selection
- Seamless fallback mechanism
- Consistent API interface
- Error handling and logging

#### 2. NeMoGuardrailsSDKService (`src/api/services/guardrails/nemo_sdk_service.py`)

SDK-specific service wrapper:

```python
class NeMoGuardrailsSDKService:
    """NeMo Guardrails SDK Service using Colang configuration."""
    
    async def check_input_safety(self, user_input: str, context: Optional[Dict] = None)
    async def check_output_safety(self, response: str, context: Optional[Dict] = None)
```

**Key Features:**
- Colang-based rail configuration
- Async initialization
- Intelligent violation detection
- Error handling with fallback

#### 3. Configuration Files

**Colang Rails** (`data/config/guardrails/rails.co`):
- Input rails: Jailbreak, Safety, Security, Compliance, Off-topic
- Output rails: Dangerous instructions, Security leakage, Compliance violations
- 88 patterns converted from legacy YAML

**NeMo Config** (`data/config/guardrails/config.yml`):
- Model configuration (OpenAI-compatible with NVIDIA NIM endpoints)
- Rails configuration
- Instructions and monitoring settings

**Legacy YAML** (`data/config/guardrails/rails.yaml`):
- Still used by pattern-based implementation
- Maintained for backward compatibility

---

## Guardrails Categories

### Input Rails (User Input Validation)

#### 1. Jailbreak Detection (17 patterns)
- **Purpose:** Prevent attempts to override system instructions
- **Patterns:** "ignore previous instructions", "roleplay", "override", "bypass", etc.
- **Response:** "I cannot ignore my instructions or roleplay as someone else. I'm here to help with warehouse operations."

#### 2. Safety Violations (13 patterns)
- **Purpose:** Block unsafe operational requests
- **Patterns:** "operate forklift without training", "bypass safety protocols", "work without PPE", etc.
- **Response:** "Safety is our top priority. I cannot provide guidance that bypasses safety protocols."

#### 3. Security Violations (15 patterns)
- **Purpose:** Prevent security information requests
- **Patterns:** "security codes", "access codes", "restricted areas", "alarm codes", etc.
- **Response:** "I cannot provide security-sensitive information. Please contact your security team."

#### 4. Compliance Violations (12 patterns)
- **Purpose:** Block requests to circumvent regulations
- **Patterns:** "avoid safety inspections", "skip compliance", "ignore regulations", etc.
- **Response:** "Compliance with safety regulations and company policies is mandatory."

#### 5. Off-Topic Queries (13 patterns)
- **Purpose:** Redirect non-warehouse related queries
- **Patterns:** "weather", "joke", "cooking", "sports", "politics", etc.
- **Response:** "I'm specialized in warehouse operations. How can I assist you with warehouse operations?"

### Output Rails (AI Response Validation)

#### 1. Dangerous Instructions (6 patterns)
- **Purpose:** Block AI responses containing unsafe guidance
- **Patterns:** "ignore safety", "bypass protocol", "skip training", etc.

#### 2. Security Information Leakage (7 patterns)
- **Purpose:** Prevent AI from revealing sensitive information
- **Patterns:** "security code", "access code", "password", "master key", etc.

#### 3. Compliance Violations (5 patterns)
- **Purpose:** Block AI responses suggesting non-compliance
- **Patterns:** "avoid inspection", "skip compliance", "ignore regulation", etc.

**Total Patterns:** 88 patterns across all categories

---

## API Interface

### GuardrailsResult

Both implementations return the same `GuardrailsResult` structure:

```python
@dataclass
class GuardrailsResult:
    is_safe: bool                    # Whether content is safe
    response: Optional[str] = None   # Alternative response if unsafe
    violations: List[str] = None     # List of detected violations
    confidence: float = 1.0          # Confidence score (0.0-1.0)
    processing_time: float = 0.0     # Processing time in seconds
    method_used: str = "pattern_matching"  # "sdk", "pattern_matching", or "api"
```

### Service Methods

```python
# Check user input safety
result: GuardrailsResult = await guardrails_service.check_input_safety(
    user_input: str,
    context: Optional[Dict[str, Any]] = None
)

# Check AI response safety
result: GuardrailsResult = await guardrails_service.check_output_safety(
    response: str,
    context: Optional[Dict[str, Any]] = None
)

# Process both input and output
result: GuardrailsResult = await guardrails_service.process_with_guardrails(
    user_input: str,
    ai_response: str,
    context: Optional[Dict[str, Any]] = None
)
```

---

## Integration Points

### Chat Endpoint (`src/api/routers/chat.py`)

The chat endpoint integrates guardrails at two points:

1. **Input Safety Check** (Line 640-654):
   ```python
   input_safety = await guardrails_service.check_input_safety(req.message, req.context)
   if not input_safety.is_safe:
       return _create_safety_violation_response(...)
   ```

2. **Output Safety Check** (Line 1055-1085):
   ```python
   output_safety = await guardrails_service.check_output_safety(result["response"], req.context)
   if not output_safety.is_safe:
       return _create_safety_violation_response(...)
   ```

**Features:**
- 3-second timeout for input checks
- 5-second timeout for output checks
- Automatic fallback on timeout/errors
- Metrics tracking for method used and performance

---

## Monitoring & Metrics

### Performance Monitor Integration

The system tracks comprehensive metrics:

#### Metrics Collected

1. **Guardrails Method Usage:**
   - `guardrails_check{method="sdk"}` - Count of SDK checks
   - `guardrails_check{method="pattern_matching"}` - Count of pattern checks
   - `guardrails_check{method="api"}` - Count of API checks

2. **Guardrails Performance:**
   - `guardrails_latency_ms{method="sdk"}` - SDK latency histogram
   - `guardrails_latency_ms{method="pattern_matching"}` - Pattern latency histogram
   - `guardrails_latency_ms{method="api"}` - API latency histogram

3. **Request Metrics:**
   - Method used for each check
   - Processing time per check
   - Safety status (safe/unsafe)
   - Confidence scores

#### Logging Format

```
🔒 Guardrails check: method=sdk, safe=True, time=45.2ms, confidence=0.95
🔒 Output guardrails check: method=pattern_matching, safe=True, time=12.3ms, confidence=0.90
```

#### Prometheus Queries

**Method Usage Distribution:**
```promql
sum(rate(guardrails_check[5m])) by (method)
```

**Average Latency by Method:**
```promql
avg(guardrails_latency_ms) by (method)
```

**Method Distribution Percentage:**
```promql
sum(guardrails_check) by (method) / sum(guardrails_check)
```

---

## Testing

### Test Coverage

#### Unit Tests (`tests/unit/test_guardrails_sdk.py`)
- SDK service initialization
- Input/output safety checking
- Format consistency
- Timeout handling
- Error scenarios

#### Integration Tests (`tests/integration/test_guardrails_comparison.py`)
- Side-by-side comparison of both implementations
- All violation categories tested
- Performance benchmarking
- API compatibility verification

**Test Cases:** 18 test cases covering all violation categories

### Running Tests

```bash
# Unit tests
pytest tests/unit/test_guardrails_sdk.py -v

# Integration tests
pytest tests/integration/test_guardrails_comparison.py -v -s

# Performance benchmarks
pytest tests/integration/test_guardrails_comparison.py::test_performance_benchmark -v -s

# All guardrails tests
pytest tests/unit/test_guardrails*.py tests/integration/test_guardrails*.py -v
```

---

## Configuration

### Environment Variables

```bash
# Feature flag to enable SDK implementation
USE_NEMO_GUARDRAILS_SDK=false  # Default: false (use pattern-based)

# NVIDIA API configuration (for SDK)
NVIDIA_API_KEY=your-api-key
RAIL_API_URL=https://integrate.api.nvidia.com/v1  # Optional, has default

# Legacy guardrails configuration (still supported)
GUARDRAILS_USE_API=true
RAIL_API_KEY=your-api-key  # Optional, falls back to NVIDIA_API_KEY
GUARDRAILS_TIMEOUT=10
```

### Configuration Files

- **Colang Rails:** `data/config/guardrails/rails.co`
- **NeMo Config:** `data/config/guardrails/config.yml`
- **Legacy YAML:** `data/config/guardrails/rails.yaml`

---

## Migration Phases Completed

### Phase 1: Preparation & Assessment ✅
- NeMo Guardrails SDK installed (v0.19.0)
- Current implementation reviewed (88 patterns documented)
- Patterns mapped to Colang rail types
- Integration points identified
- Dependency analysis completed
- Environment setup (dev branch created)

### Phase 2: Parallel Implementation ✅
- Colang configuration created (`rails.co`)
- NeMo Guardrails configuration (`config.yml`)
- SDK service wrapper implemented
- Feature flag support added
- Backward compatibility maintained

### Phase 3: Integration & Testing ✅
- Unit tests created and passing
- Integration tests created and passing
- All violation categories tested
- Performance benchmarking implemented
- API compatibility verified
- Chat endpoint integrated
- Monitoring and logging implemented

---

## Current Status

### ✅ Completed
- [x] SDK installation and configuration
- [x] Colang rails implementation (88 patterns)
- [x] Dual implementation support (SDK + Pattern-based)
- [x] Feature flag control
- [x] Comprehensive test coverage
- [x] Monitoring and metrics
- [x] Chat endpoint integration
- [x] Error handling and fallback

### ⚠️ Known Limitations
1. **Model Provider:** SDK uses OpenAI-compatible endpoints (NVIDIA NIM supports this)
2. **Output Rails:** Currently handled in service layer; can be enhanced with Python actions
3. **SDK Initialization:** Requires API keys; falls back gracefully if unavailable

---

## Future Steps

### Phase 4: Production Deployment & Optimization

#### 1. Gradual Rollout
- **Week 1-2:** Deploy with feature flag disabled (pattern-based only)
- **Week 3-4:** Enable SDK for 10% of requests (canary deployment)
- **Week 5-6:** Increase to 50% if metrics are positive
- **Week 7-8:** Full rollout to 100% if successful

#### 2. Monitoring & Optimization
- Monitor accuracy differences between implementations
- Track performance metrics (latency, throughput)
- Compare violation detection rates
- Optimize based on real-world usage patterns

#### 3. Output Rails Enhancement
- Implement Python actions for output validation in Colang
- Add more sophisticated output rails
- Improve detection accuracy for edge cases

#### 4. Advanced Features
- Custom rail definitions for domain-specific violations
- Machine learning-based pattern detection
- Adaptive confidence scoring
- Multi-language support

#### 5. Documentation & Training
- User guide for feature flag management
- Monitoring dashboard setup guide
- Troubleshooting guide
- Best practices documentation

---

## Risk Assessment

| Risk | Impact | Probability | Mitigation | Status |
|------|--------|-------------|------------|--------|
| SDK initialization failures | Medium | Medium | Automatic fallback to pattern-based | ✅ Mitigated |
| Configuration errors | Low | Low | Validation on startup | ✅ Mitigated |
| Performance degradation | Medium | Low | Feature flag allows easy rollback | ✅ Mitigated |
| API compatibility issues | Medium | Medium | OpenAI-compatible endpoints | ⚠️ Needs monitoring |
| Behavior differences | High | Medium | Extensive testing, gradual rollout | ⚠️ Needs monitoring |
| Accuracy variations | Medium | Medium | A/B testing, metrics tracking | ⚠️ Needs monitoring |

---

## Troubleshooting

### SDK Not Initializing

**Symptoms:** Logs show "SDK not available" or "Failed to initialize SDK"

**Solutions:**
1. Verify `USE_NEMO_GUARDRAILS_SDK=true` is set
2. Check `NVIDIA_API_KEY` is configured
3. Verify `nemoguardrails` package is installed: `pip install nemoguardrails`
4. Check Colang syntax: `python -c "from nemoguardrails import RailsConfig; RailsConfig.from_path('data/config/guardrails')"`
5. System will automatically fall back to pattern-based implementation

### High Latency

**Symptoms:** Guardrails checks taking >1 second

**Solutions:**
1. Check network connectivity to NVIDIA API endpoints
2. Verify API keys are valid
3. Consider using pattern-based implementation for lower latency
4. Review timeout settings (default: 3s input, 5s output)

### False Positives/Negatives

**Symptoms:** Legitimate queries blocked or violations not detected

**Solutions:**
1. Review Colang patterns in `rails.co`
2. Adjust confidence thresholds
3. Add custom patterns for domain-specific cases
4. Compare with pattern-based implementation results
5. Review logs for method used and confidence scores

---

## References

- [NVIDIA NeMo Guardrails Documentation](https://docs.nvidia.com/nemo/guardrails/latest/index.html)
- [Colang Language Reference](https://docs.nvidia.com/nemo/guardrails/latest/user-guide/colang.html)
- Project Files:
  - `src/api/services/guardrails/guardrails_service.py` - Main service
  - `src/api/services/guardrails/nemo_sdk_service.py` - SDK wrapper
  - `data/config/guardrails/rails.co` - Colang configuration
  - `data/config/guardrails/config.yml` - NeMo configuration
  - `tests/unit/test_guardrails_sdk.py` - Unit tests
  - `tests/integration/test_guardrails_comparison.py` - Integration tests

---

## Summary

The NeMo Guardrails implementation provides robust content safety and compliance protection for the Warehouse Operational Assistant. With dual implementation support, comprehensive testing, and extensive monitoring, the system is production-ready and can be gradually migrated to full SDK usage based on real-world performance and accuracy metrics.

**Key Achievements:**
- ✅ 88 patterns converted to Colang
- ✅ Dual implementation with seamless fallback
- ✅ Comprehensive test coverage
- ✅ Full monitoring and metrics
- ✅ Production-ready deployment

**Next Steps:**
- Gradual rollout with feature flag
- Monitor metrics and performance
- Optimize based on real-world usage
- Enhance output rails with Python actions

