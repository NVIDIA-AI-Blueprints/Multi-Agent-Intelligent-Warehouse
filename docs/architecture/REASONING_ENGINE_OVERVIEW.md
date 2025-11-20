# Agent Reasoning Capability Overview

## Executive Summary

The Warehouse Operational Assistant implements a comprehensive **Advanced Reasoning Engine** with 5 distinct reasoning types. **The reasoning engine is now fully integrated with ALL agents** (Equipment, Operations, Safety, Forecasting, Document) and the main chat router. Reasoning can be enabled/disabled via the chat API and UI, and reasoning chains are displayed in the chat interface.

## Implementation Status

### ✅ Fully Implemented

1. **Reasoning Engine Core** (`src/api/services/reasoning/reasoning_engine.py`)
   - Complete implementation with all 5 reasoning types
   - 954 lines of code
   - Fully functional with NVIDIA NIM LLM integration

2. **Reasoning API Endpoints** (`src/api/routers/reasoning.py`)
   - `/api/v1/reasoning/analyze` - Direct reasoning analysis
   - `/api/v1/reasoning/chat-with-reasoning` - Chat with reasoning
   - `/api/v1/reasoning/insights/{session_id}` - Session insights
   - `/api/v1/reasoning/types` - Available reasoning types

3. **Main Chat Router Integration** (`src/api/routers/chat.py`)
   - ✅ Fully integrated with reasoning engine
   - ✅ Supports `enable_reasoning` and `reasoning_types` parameters
   - ✅ Extracts and includes reasoning chains in responses
   - ✅ Dynamic timeout handling for reasoning-enabled queries

4. **MCP Planner Graph Integration** (`src/api/graphs/mcp_integrated_planner_graph.py`)
   - ✅ Fully integrated with reasoning engine
   - ✅ Passes reasoning parameters to all agents
   - ✅ Extracts reasoning chains from agent responses
   - ✅ Includes reasoning in context for response synthesis

5. **All Agent Integrations** (Phase 1 Complete)
   - ✅ **Equipment Agent** (`src/api/agents/inventory/mcp_equipment_agent.py`) - Fully integrated
   - ✅ **Operations Agent** (`src/api/agents/operations/mcp_operations_agent.py`) - Fully integrated
   - ✅ **Safety Agent** (`src/api/agents/safety/mcp_safety_agent.py`) - Fully integrated
   - ✅ **Forecasting Agent** (`src/api/agents/forecasting/forecasting_agent.py`) - Fully integrated
   - ✅ **Document Agent** (`src/api/agents/document/mcp_document_agent.py`) - Fully integrated

6. **Frontend Integration** (`src/ui/web/src/pages/ChatInterfaceNew.tsx`)
   - ✅ UI toggle to enable/disable reasoning
   - ✅ Reasoning type selection
   - ✅ Reasoning chain visualization in chat messages
   - ✅ Reasoning steps displayed with expandable UI

### ✅ Phase 1 Complete

All agents now support:
- `enable_reasoning` parameter in `process_query()`
- Automatic complex query detection via `_is_complex_query()`
- Reasoning type selection via `_determine_reasoning_types()`
- Reasoning chain included in agent responses
- Graceful fallback when reasoning is disabled or fails

## Reasoning Types Implemented

### 1. Chain-of-Thought Reasoning (`CHAIN_OF_THOUGHT`)

**Purpose**: Step-by-step thinking process with clear reasoning steps

**Implementation**:
- Breaks down queries into 5 analysis steps:
  1. What is the user asking for?
  2. What information do I need to answer this?
  3. What are the key entities and relationships?
  4. What are the potential approaches to solve this?
  5. What are the constraints and considerations?

**Code Location**: `reasoning_engine.py:234-304`

**Usage**: Always included in all agents for complex queries when reasoning is enabled

### 2. Multi-Hop Reasoning (`MULTI_HOP`)

**Purpose**: Connect information across different data sources

**Implementation**:
- Step 1: Identify information needs from multiple sources
- Step 2: Gather data from equipment, workforce, safety, and inventory
- Step 3: Connect information across sources to answer query

**Code Location**: `reasoning_engine.py:306-425`

**Data Sources**:
- Equipment status and telemetry
- Workforce and task data
- Safety incidents and procedures
- Inventory and stock levels

### 3. Scenario Analysis (`SCENARIO_ANALYSIS`)

**Purpose**: What-if reasoning and alternative scenario analysis

**Implementation**:
- Analyzes 5 scenarios:
  1. Best case scenario
  2. Worst case scenario
  3. Most likely scenario
  4. Alternative approaches
  5. Risk factors and mitigation

**Code Location**: `reasoning_engine.py:427-530`

**Use Cases**: Planning, risk assessment, decision support

### 4. Causal Reasoning (`CAUSAL`)

**Purpose**: Cause-and-effect analysis and relationship identification

**Implementation**:
- Step 1: Identify potential causes and effects
- Step 2: Analyze causal strength and evidence
- Evaluates direct and indirect causal relationships

**Code Location**: `reasoning_engine.py:532-623`

**Use Cases**: Root cause analysis, incident investigation

### 5. Pattern Recognition (`PATTERN_RECOGNITION`)

**Purpose**: Learn from query patterns and user behavior

**Implementation**:
- Step 1: Analyze current query patterns
- Step 2: Learn from historical patterns (last 10 queries)
- Step 3: Generate insights and recommendations

**Code Location**: `reasoning_engine.py:625-742`

**Features**:
- Query pattern tracking
- User behavior analysis
- Historical pattern learning
- Insight generation

## How It Works

### Agent Integration Pattern

All agents follow the same pattern for reasoning integration:

```python
# In any agent's process_query() method (e.g., mcp_equipment_agent.py)

# Step 1: Check if reasoning should be enabled
if enable_reasoning and self.reasoning_engine and self._is_complex_query(query):
    # Step 2: Determine reasoning types based on query content
    reasoning_types = self._determine_reasoning_types(query, context)
    
    # Step 3: Process with reasoning
    reasoning_chain = await self.reasoning_engine.process_with_reasoning(
        query=query,
        context=context or {},
        reasoning_types=reasoning_types,
        session_id=session_id,
    )
    
    # Step 4: Use reasoning chain in response generation
    response = await self._generate_response_with_tools(
        query, tool_results, session_id, reasoning_chain=reasoning_chain
    )
```

### Chat Router Integration

The main chat router (`src/api/routers/chat.py`) supports reasoning:

```python
# Chat request includes reasoning parameters
@router.post("/chat")
async def chat(req: ChatRequest):
    # req.enable_reasoning: bool = False
    # req.reasoning_types: Optional[List[str]] = None
    
    # Pass to MCP planner graph
    result = await mcp_planner_graph.process(
        message=req.message,
        enable_reasoning=req.enable_reasoning,
        reasoning_types=req.reasoning_types,
        ...
    )
    
    # Extract reasoning chain from result
    reasoning_chain = result.get("reasoning_chain")
    reasoning_steps = result.get("reasoning_steps")
    
    # Include in response
    return ChatResponse(
        ...,
        reasoning_chain=reasoning_chain,
        reasoning_steps=reasoning_steps
    )
```

### Complex Query Detection

All agents use `_is_complex_query()` to determine if reasoning should be enabled:

**Complex Query Indicators**:
- Keywords: "analyze", "compare", "relationship", "scenario", "what if", "cause", "effect", "pattern", "trend", "explain", "investigate", etc.
- Query length and structure
- Context complexity

### Reasoning Type Selection

Each agent automatically selects reasoning types based on query content and agent-specific logic:

- **Always**: Chain-of-Thought (for all complex queries)
- **Multi-Hop**: If query contains "analyze", "compare", "relationship", "connection", "across", "multiple"
- **Scenario Analysis**: If query contains "what if", "scenario", "alternative", "option", "plan", "strategy"
  - **Operations Agent**: Always includes scenario analysis for workflow optimization queries
  - **Forecasting Agent**: Always includes scenario analysis + pattern recognition for forecasting queries
- **Causal**: If query contains "cause", "effect", "because", "result", "consequence", "due to", "leads to"
  - **Safety Agent**: Always includes causal reasoning for safety queries
  - **Document Agent**: Uses causal reasoning for quality analysis
- **Pattern Recognition**: If query contains "pattern", "trend", "learn", "insight", "recommendation", "optimize", "improve"
  - **Forecasting Agent**: Always includes pattern recognition for forecasting queries

## API Usage

### Chat API with Reasoning

The main chat endpoint now supports reasoning:

```bash
POST /api/v1/chat
{
  "message": "What if we optimize the picking route in Zone B and reassign 2 workers to Zone C?",
  "session_id": "user123",
  "enable_reasoning": true,
  "reasoning_types": ["scenario_analysis", "chain_of_thought"]  // Optional
}
```

**Response**:
```json
{
  "reply": "Optimizing the picking route in Zone B could result in...",
  "route": "operations",
  "intent": "operations",
  "reasoning_chain": {
    "chain_id": "REASON_20251117_153549",
    "query": "...",
    "reasoning_type": "scenario_analysis",
    "steps": [...],
    "final_conclusion": "...",
    "overall_confidence": 0.8
  },
  "reasoning_steps": [
    {
      "step_id": "SCENARIO_1",
      "step_type": "scenario_analysis",
      "description": "Best case scenario",
      "reasoning": "...",
      "confidence": 0.85
    }
  ],
  "structured_data": {...},
  "confidence": 0.8
}
```

### Direct Reasoning Analysis

```bash
POST /api/v1/reasoning/analyze
{
  "query": "What are the potential causes of equipment failures?",
  "context": {},
  "reasoning_types": ["chain_of_thought", "causal"],
  "session_id": "user123"
}
```

**Response**:
```json
{
  "chain_id": "REASON_20251116_143022",
  "query": "...",
  "reasoning_type": "multi_hop",
  "steps": [
    {
      "step_id": "COT_1",
      "step_type": "query_analysis",
      "description": "...",
      "reasoning": "...",
      "confidence": 0.8,
      ...
    }
  ],
  "final_conclusion": "...",
  "overall_confidence": 0.85,
  "execution_time": 2.34
}
```

### Chat with Reasoning

```bash
POST /api/v1/reasoning/chat-with-reasoning
{
  "query": "Analyze the relationship between equipment maintenance and safety incidents",
  "session_id": "user123"
}
```

### Get Reasoning Insights

```bash
GET /api/v1/reasoning/insights/user123
```

**Response**:
```json
{
  "session_id": "user123",
  "total_queries": 15,
  "reasoning_types": {
    "chain_of_thought": 15,
    "multi_hop": 8,
    "causal": 5
  },
  "average_confidence": 0.82,
  "average_execution_time": 2.1,
  "common_patterns": {
    "equipment": 12,
    "safety": 10,
    "maintenance": 8
  },
  "recommendations": []
}
```

## Current Status

### ✅ Completed (Phase 1)

1. **Full Agent Integration**
   - ✅ All 5 agents (Equipment, Operations, Safety, Forecasting, Document) support reasoning
   - ✅ Main chat router supports reasoning
   - ✅ MCP planner graph passes reasoning parameters to agents
   - ✅ Reasoning chains included in all agent responses

2. **Frontend Integration**
   - ✅ UI toggle to enable/disable reasoning
   - ✅ Reasoning type selection in UI
   - ✅ Reasoning chain visualization in chat messages
   - ✅ Reasoning steps displayed with expandable UI components

3. **Query Complexity Detection**
   - ✅ All agents detect complex queries automatically
   - ✅ Reasoning only applied to complex queries (performance optimization)
   - ✅ Simple queries skip reasoning even when enabled

### ⚠️ Current Limitations

1. **Performance Impact**
   - Reasoning adds 2-5 seconds to response time for complex queries
   - Multiple LLM calls per reasoning type
   - Timeout handling implemented (230s for complex reasoning queries)

2. **No Persistence**
   - Reasoning chains stored in memory only
   - Lost on server restart
   - No historical analysis of reasoning patterns

3. **No Caching**
   - Similar queries re-run reasoning (no caching)
   - Could optimize by caching reasoning results for identical queries

## Future Enhancements (Phase 2+)

### 1. Add Persistence

**Priority**: Medium

**Implementation**:
- Store reasoning chains in PostgreSQL
- Create `reasoning_chains` table
- Enable historical analysis
- Support reasoning insights dashboard
- Track reasoning effectiveness over time

### 2. Optimize Performance

**Priority**: Medium

**Optimizations**:
- Cache reasoning results for similar queries
- Parallel execution of reasoning types
- Early termination for simple queries
- Reduce LLM calls where possible
- Batch reasoning for multiple queries

### 3. Enhanced Reasoning Visualization

**Priority**: Low

**Features**:
- Interactive reasoning step exploration
- Reasoning confidence visualization
- Comparison of different reasoning approaches
- Reasoning chain export/import

### 4. Reasoning Analytics

**Priority**: Low

**Features**:
- Track reasoning usage patterns
- Measure reasoning effectiveness
- Identify queries that benefit most from reasoning
- A/B testing of reasoning strategies

## Testing

### Manual Testing

1. **Test Chat API with Reasoning Enabled**:
   ```bash
   curl -X POST http://localhost:8001/api/v1/chat \
     -H "Content-Type: application/json" \
     -d '{
       "message": "What if we optimize the picking route in Zone B and reassign 2 workers to Zone C?",
       "session_id": "test123",
       "enable_reasoning": true,
       "reasoning_types": ["scenario_analysis", "chain_of_thought"]
     }'
   ```

2. **Test Equipment Agent with Reasoning**:
   ```bash
   curl -X POST http://localhost:8001/api/v1/chat \
     -H "Content-Type: application/json" \
     -d '{
       "message": "Why does dock D2 have higher equipment failure rates compared to other docks?",
       "session_id": "test123",
       "enable_reasoning": true
     }'
   ```

3. **Test Direct Reasoning API**:
   ```bash
   curl -X POST http://localhost:8001/api/v1/reasoning/analyze \
     -H "Content-Type: application/json" \
     -d '{
       "query": "Analyze the relationship between maintenance and safety",
       "reasoning_types": ["chain_of_thought", "causal"]
     }'
   ```

### Automated Testing

**Test File**: `tests/test_reasoning_integration.py`

**Test Coverage**:
- ✅ Chain-of-thought reasoning for all agents
- ✅ Multi-hop reasoning
- ✅ Scenario analysis
- ✅ Causal reasoning
- ✅ Pattern recognition
- ✅ Complex query detection
- ✅ Reasoning type selection
- ✅ Reasoning disabled scenarios
- ✅ Error handling and graceful fallback

**Test Results**: See `tests/REASONING_INTEGRATION_SUMMARY.md` and `tests/REASONING_EVALUATION_REPORT.md`

## Conclusion

The Advanced Reasoning Engine is **fully implemented, functional, and integrated** across the entire system. **Phase 1 is complete** with:

1. ✅ **Main chat router integration** - Reasoning enabled via API parameters
2. ✅ **All agent integration** - Equipment, Operations, Safety, Forecasting, and Document agents all support reasoning
3. ✅ **Frontend visualization** - UI toggle, reasoning type selection, and reasoning chain display
4. ✅ **MCP planner graph integration** - Reasoning parameters passed through the orchestration layer
5. ✅ **Complex query detection** - Automatic detection and reasoning application

The reasoning engine now provides significant value for complex queries across all domains. **Phase 2 enhancements** (persistence, performance optimization, analytics) will further improve the system's capabilities.

**Status**: ✅ **Production Ready** - All core functionality operational

**Documentation**: See `tests/REASONING_INTEGRATION_SUMMARY.md` for detailed implementation status and `tests/REASONING_EVALUATION_REPORT.md` for evaluation results.

