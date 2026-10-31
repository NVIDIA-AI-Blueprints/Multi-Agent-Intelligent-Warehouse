# Evidence Scoring System

## Overview

The Evidence Scoring System provides advanced confidence assessment and quality control for AI responses through multi-factor analysis and intelligent validation.

## Architecture

### Multi-Factor Evidence Scoring

The system evaluates evidence quality using five weighted factors:

1. **Vector Similarity Scoring (30% weight)**
   - Measures semantic similarity between query and retrieved content
   - Uses cosine similarity with configurable thresholds
   - Accounts for query complexity and content length

2. **Source Authority & Credibility (25% weight)**
   - Evaluates source reliability and expertise
   - Considers source type (official docs, user manuals, expert content)
   - Tracks source reputation and validation history

3. **Content Freshness & Recency (20% weight)**
   - Prioritizes recent and up-to-date information
   - Uses temporal decay functions for older content
   - Considers content update frequency and versioning

4. **Cross-Reference Validation (15% weight)**
   - Validates information across multiple sources
   - Identifies conflicting or contradictory information
   - Measures consensus and agreement levels

5. **Source Diversity Scoring (10% weight)**
   - Ensures varied source coverage
   - Prevents bias from single-source dominance
   - Promotes comprehensive information gathering

### Confidence Assessment

#### Thresholds
- **High Confidence**: Evidence score ≥ 0.8
- **Medium Confidence**: 0.6 ≤ Evidence score < 0.8
- **Low Confidence**: Evidence score < 0.6

#### Quality Indicators
- **Source Count**: Minimum 2 distinct sources required
- **Agreement Level**: Cross-source consensus measurement
- **Freshness Score**: Content age and update frequency
- **Authority Score**: Source credibility and expertise

### Intelligent Clarifying Questions

#### Question Generation
- **Context-Aware**: Questions tailored to query type and domain
- **Ambiguity Detection**: Identifies specific areas of uncertainty
- **Priority Ranking**: Critical, high, medium, low priority questions
- **Follow-up Suggestions**: Progressive question refinement

#### Question Types
- **Equipment-Specific**: "Which specific equipment are you asking about?"
- **Location-Specific**: "Which warehouse zone or area?"
- **Time-Specific**: "What time period are you interested in?"
- **Scope-Specific**: "Are you asking about current status or historical data?"

## Implementation

### Evidence Scoring Algorithm

```python
def calculate_evidence_score(evidence_pack):
    """Calculate comprehensive evidence score."""
    
    # Vector similarity (30%)
    vector_score = calculate_vector_similarity(evidence_pack.query, evidence_pack.content)
    
    # Source authority (25%)
    authority_score = evaluate_source_authority(evidence_pack.source)
    
    # Content freshness (20%)
    freshness_score = calculate_content_freshness(evidence_pack.timestamp)
    
    # Cross-reference validation (15%)
    validation_score = validate_cross_references(evidence_pack.sources)
    
    # Source diversity (10%)
    diversity_score = calculate_source_diversity(evidence_pack.sources)
    
    # Weighted combination
    evidence_score = (
        vector_score * 0.30 +
        authority_score * 0.25 +
        freshness_score * 0.20 +
        validation_score * 0.15 +
        diversity_score * 0.10
    )
    
    return evidence_score
```

### Confidence Assessment

```python
def assess_confidence(evidence_score, source_count, agreement_level):
    """Assess overall confidence level."""
    
    if evidence_score >= 0.8:
        return "high"
    elif evidence_score >= 0.6:
        return "medium"
    else:
        return "low"
```

### Clarifying Questions Engine

```python
def generate_clarifying_questions(query, evidence_pack, confidence_level):
    """Generate context-aware clarifying questions."""
    
    if confidence_level == "low":
        questions = []
        
        # Equipment-specific questions
        if "equipment" in query.lower() and not extract_equipment_id(query):
            questions.append("Which specific equipment are you asking about?")
        
        # Location-specific questions
        if "location" in query.lower() and not extract_location(query):
            questions.append("Which warehouse zone or area?")
        
        # Time-specific questions
        if "status" in query.lower() and not extract_timeframe(query):
            questions.append("What time period are you interested in?")
        
        return prioritize_questions(questions)
    
    return []
```

## Performance Benefits

### Accuracy Improvements
- **Reduced Hallucinations**: Evidence scoring prevents low-quality responses
- **Better Source Validation**: Multi-factor analysis ensures reliable information
- **Improved Confidence**: Users know when to trust AI responses

### User Experience
- **Transparent AI**: Users see confidence levels and evidence quality
- **Actionable Feedback**: Clarifying questions help users refine queries
- **Quality Indicators**: Visual confidence indicators in UI

### System Reliability
- **Consistent Quality**: Standardized evidence evaluation across all queries
- **Adaptive Learning**: System learns from user feedback and corrections
- **Error Prevention**: Proactive quality control prevents poor responses

## Configuration

### Evidence Scoring Parameters

Illustrative only — there is no YAML config file; the defaults live in the
`config` dict of `src/retrieval/vector/evidence_scoring.py`.

```yaml
evidence_scoring:
  weights:
    vector_similarity: 0.30
    source_authority: 0.25
    content_freshness: 0.20
    cross_reference: 0.15
    source_diversity: 0.10
  
  thresholds:
    high_confidence: 0.8
    medium_confidence: 0.6
    low_confidence: 0.0
  
  requirements:
    min_sources: 2
    min_agreement: 0.8
    max_age_days: 365
```

### Clarifying Questions Settings

```yaml
clarifying_questions:
  enabled: true
  max_questions: 3
  priority_order: ["critical", "high", "medium", "low"]
  
  question_types:
    equipment_specific: true
    location_specific: true
    time_specific: true
    scope_specific: true
```

## Monitoring & Analytics

### Metrics Tracked
- **Evidence Score Distribution**: Average, median, percentile scores
- **Confidence Level Distribution**: High/medium/low confidence ratios
- **Question Generation Rate**: Frequency of clarifying questions
- **User Satisfaction**: Feedback on response quality
- **Source Diversity**: Variety of sources used

### Performance Monitoring
- **Response Time Impact**: Evidence scoring overhead
- **Accuracy Improvements**: Before/after quality metrics
- **User Engagement**: Interaction with confidence indicators
- **Error Reduction**: Decrease in low-quality responses

## Future Enhancements

### Planned Features
- **Machine Learning Integration**: Learn from user feedback
- **Dynamic Weight Adjustment**: Adapt weights based on domain
- **Advanced Question Types**: More sophisticated question generation
- **Real-time Validation**: Live evidence quality monitoring
- **Cross-Domain Learning**: Apply learnings across different domains
