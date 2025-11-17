# Reasoning Capability Enhancement - TODO Proposal

## Executive Summary

This document outlines a comprehensive plan to enhance all agents (Equipment, Operations, Forecasting, Document) with the existing Advanced Reasoning Engine capability, which is currently only integrated with the Safety Agent. The enhancement includes adding a UI toggle (ON/OFF) to enable/disable reasoning for all chat interactions.

**Current Status:**
- ✅ Reasoning Engine fully implemented (5 reasoning types)
- ✅ Safety Agent integrated with reasoning
- ❌ Other agents (Equipment, Operations, Forecasting, Document) lack reasoning
- ❌ Main chat router lacks reasoning integration
- ❌ No UI toggle for reasoning control

**Target Status:**
- ✅ All agents support reasoning capability
- ✅ Main chat router supports reasoning
- ✅ UI toggle to enable/disable reasoning per session
- ✅ Reasoning chain displayed in UI when enabled

---

## Current Implementation Analysis

### ✅ What's Already Built

1. **Advanced Reasoning Engine** (`src/api/services/reasoning/reasoning_engine.py`)
   - 5 reasoning types: Chain-of-Thought, Multi-Hop, Scenario Analysis, Causal, Pattern Recognition
   - Fully functional with NVIDIA NIM LLM integration
   - 954 lines of production-ready code

2. **Reasoning API Endpoints** (`src/api/routers/reasoning.py`)
   - `/api/v1/reasoning/analyze` - Direct reasoning analysis
   - `/api/v1/reasoning/chat-with-reasoning` - Chat with reasoning
   - `/api/v1/reasoning/insights/{session_id}` - Session insights
   - `/api/v1/reasoning/types` - Available reasoning types

3. **Safety Agent Integration** (`src/api/agents/safety/safety_agent.py`)
   - `enable_reasoning` parameter in `process_query()`
   - Automatic complex query detection
   - Reasoning type selection based on query content
   - Reasoning chain included in responses

### ❌ What's Missing

1. **Agent Integration**
   - Equipment Agent - No reasoning support
   - Operations Agent - No reasoning support
   - Forecasting Agent - No reasoning support
   - Document Agent - No reasoning support

2. **Main Chat Router Integration**
   - Chat endpoint (`/api/v1/chat`) doesn't accept `enable_reasoning` parameter
   - MCP Planner Graph doesn't pass reasoning context to agents
   - No reasoning chain in chat responses

3. **UI Components**
   - No reasoning toggle switch in chat interface
   - No reasoning chain visualization
   - No reasoning type selection UI

---

## TODO: Implementation Plan

### Phase 1: Backend Integration (Priority: High)

#### Task 1.1: Update Chat Router to Support Reasoning
**File:** `src/api/routers/chat.py`
**Estimated Time:** 2-3 hours

**Changes:**
- Add `enable_reasoning: bool = False` parameter to `ChatRequest` model
- Add `reasoning_types: Optional[List[str]] = None` parameter
- Pass reasoning parameters to MCP planner graph
- Include reasoning chain in chat response

**Code Changes:**
```python
class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    context: Optional[Dict[str, Any]] = None
    enable_reasoning: bool = False  # NEW
    reasoning_types: Optional[List[str]] = None  # NEW

class ChatResponse(BaseModel):
    reply: str
    route: Optional[str] = None
    intent: Optional[str] = None
    confidence: float = 0.0
    recommendations: List[str] = []
    reasoning_chain: Optional[Dict[str, Any]] = None  # NEW
    reasoning_steps: Optional[List[Dict[str, Any]]] = None  # NEW
```

#### Task 1.2: Update MCP Planner Graph to Support Reasoning
**File:** `src/api/graphs/mcp_integrated_planner_graph.py`
**Estimated Time:** 3-4 hours

**Changes:**
- Add `enable_reasoning` and `reasoning_types` to `MCPWarehouseState`
- Pass reasoning parameters to agent nodes
- Collect reasoning chains from agents
- Include reasoning in final response synthesis

**Code Changes:**
```python
class MCPWarehouseState(TypedDict):
    # ... existing fields ...
    enable_reasoning: bool  # NEW
    reasoning_types: Optional[List[str]]  # NEW
    reasoning_chain: Optional[Dict[str, Any]]  # NEW
```

#### Task 1.3: Integrate Reasoning into Equipment Agent
**File:** `src/api/agents/inventory/equipment_agent.py`
**Estimated Time:** 2-3 hours

**Changes:**
- Import `AdvancedReasoningEngine` and `ReasoningType`
- Add `enable_reasoning` parameter to `process_query()` method
- Implement `_is_complex_query()` method (similar to Safety Agent)
- Implement `_determine_reasoning_types()` method
- Integrate reasoning chain into response generation

**Reference:** Use Safety Agent implementation as template (`src/api/agents/safety/safety_agent.py:102-198`)

#### Task 1.4: Integrate Reasoning into Operations Agent
**File:** `src/api/agents/operations/operations_agent.py`
**Estimated Time:** 2-3 hours

**Changes:**
- Same as Task 1.3, but for Operations Agent
- Customize reasoning type selection for operations-specific queries
- Add operations-specific keywords for complex query detection

#### Task 1.5: Integrate Reasoning into Forecasting Agent
**File:** `src/api/agents/forecasting/forecasting_agent.py`
**Estimated Time:** 2-3 hours

**Changes:**
- Same as Task 1.3, but for Forecasting Agent
- Emphasize Scenario Analysis and Pattern Recognition for forecasting queries
- Add forecasting-specific keywords for complex query detection

#### Task 1.6: Integrate Reasoning into Document Agent
**File:** `src/api/agents/document/mcp_document_agent.py`
**Estimated Time:** 2-3 hours

**Changes:**
- Same as Task 1.3, but for Document Agent
- Focus on Causal Reasoning for document analysis queries
- Add document-specific keywords for complex query detection

#### Task 1.7: Update Agent Response Models
**Files:** 
- `src/api/agents/inventory/models/equipment_models.py`
- `src/api/agents/operations/models/operations_models.py`
- `src/api/agents/forecasting/models/forecasting_models.py`
- `src/api/agents/document/models/document_models.py`

**Estimated Time:** 1-2 hours

**Changes:**
- Add `reasoning_chain: Optional[Dict[str, Any]] = None` to all agent response models
- Add `reasoning_steps: Optional[List[Dict[str, Any]]] = None` to all agent response models

---

### Phase 2: Frontend Integration (Priority: High)

#### Task 2.1: Add Reasoning Toggle to Chat Interface
**File:** `src/ui/web/src/pages/ChatInterfaceNew.tsx`
**Estimated Time:** 2-3 hours

**Changes:**
- Add `enableReasoning` state variable (default: `false`)
- Add Material-UI Switch component for reasoning toggle
- Position toggle in chat header or input area
- Add tooltip explaining reasoning capability
- Persist toggle state in localStorage or session storage

**UI Design:**
```tsx
<Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
  <FormControlLabel
    control={
      <Switch
        checked={enableReasoning}
        onChange={(e) => setEnableReasoning(e.target.checked)}
        color="primary"
      />
    }
    label="Advanced Reasoning"
  />
  <Tooltip title="Enable step-by-step reasoning, multi-hop analysis, and scenario planning">
    <InfoIcon fontSize="small" color="action" />
  </Tooltip>
</Box>
```

#### Task 2.2: Update Chat API Service
**File:** `src/ui/web/src/services/api.ts`
**Estimated Time:** 30 minutes

**Changes:**
- Update `ChatRequest` interface to include `enable_reasoning?: boolean`
- Update `ChatResponse` interface to include `reasoning_chain?: any` and `reasoning_steps?: any[]`
- Pass `enable_reasoning` in chat API calls

**Code Changes:**
```typescript
interface ChatRequest {
  message: string;
  session_id?: string;
  context?: Record<string, any>;
  enable_reasoning?: boolean;  // NEW
  reasoning_types?: string[];  // NEW (optional)
}

interface ChatResponse {
  reply: string;
  route?: string;
  intent?: string;
  confidence: number;
  recommendations: string[];
  reasoning_chain?: any;  // NEW
  reasoning_steps?: any[];  // NEW
}
```

#### Task 2.3: Pass Reasoning Toggle to Chat API
**File:** `src/ui/web/src/pages/ChatInterfaceNew.tsx`
**Estimated Time:** 30 minutes

**Changes:**
- Include `enable_reasoning` in `chatMutation.mutateAsync()` call
- Pass reasoning state from toggle to API request

**Code Changes:**
```typescript
await chatMutation.mutateAsync({
  message: inputValue,
  session_id: 'default',
  context: { warehouse, role, environment },
  enable_reasoning: enableReasoning,  // NEW
});
```

#### Task 2.4: Create Reasoning Chain Visualization Component
**File:** `src/ui/web/src/components/chat/ReasoningChain.tsx` (NEW)
**Estimated Time:** 4-5 hours

**Changes:**
- Create new React component to display reasoning chain
- Show reasoning steps in expandable accordion or timeline
- Display reasoning type badges (Chain-of-Thought, Multi-Hop, etc.)
- Show confidence scores and execution time
- Add collapsible sections for detailed reasoning steps

**Component Structure:**
```tsx
interface ReasoningChainProps {
  reasoningChain: any;
  reasoningSteps?: any[];
}

const ReasoningChain: React.FC<ReasoningChainProps> = ({ reasoningChain, reasoningSteps }) => {
  // Display reasoning chain with:
  // - Reasoning type badges
  // - Step-by-step reasoning process
  // - Confidence scores
  // - Execution time
  // - Expandable details
};
```

#### Task 2.5: Integrate Reasoning Display in Message Bubble
**File:** `src/ui/web/src/components/chat/MessageBubble.tsx`
**Estimated Time:** 2-3 hours

**Changes:**
- Add reasoning chain display to assistant messages
- Show reasoning toggle indicator when reasoning is enabled
- Add expandable section for reasoning details
- Style reasoning chain with appropriate colors and icons

#### Task 2.6: Add Reasoning Type Selection (Optional Enhancement)
**File:** `src/ui/web/src/components/chat/ReasoningTypeSelector.tsx` (NEW)
**Estimated Time:** 3-4 hours

**Changes:**
- Create component for selecting specific reasoning types
- Show checkboxes for each reasoning type
- Allow users to enable/disable specific reasoning types
- Default to all types when reasoning is enabled

**UI Design:**
```tsx
<FormGroup>
  <FormControlLabel control={<Checkbox />} label="Chain-of-Thought" />
  <FormControlLabel control={<Checkbox />} label="Multi-Hop Reasoning" />
  <FormControlLabel control={<Checkbox />} label="Scenario Analysis" />
  <FormControlLabel control={<Checkbox />} label="Causal Reasoning" />
  <FormControlLabel control={<Checkbox />} label="Pattern Recognition" />
</FormGroup>
```

---

### Phase 3: Testing & Validation (Priority: Medium)

#### Task 3.1: Unit Tests for Agent Reasoning Integration
**Files:** 
- `tests/unit/test_equipment_agent_reasoning.py` (NEW)
- `tests/unit/test_operations_agent_reasoning.py` (NEW)
- `tests/unit/test_forecasting_agent_reasoning.py` (NEW)
- `tests/unit/test_document_agent_reasoning.py` (NEW)

**Estimated Time:** 4-5 hours

**Test Cases:**
- Test reasoning enabled/disabled scenarios
- Test complex query detection
- Test reasoning type selection
- Test reasoning chain generation
- Test error handling when reasoning fails

#### Task 3.2: Integration Tests for Chat Router with Reasoning
**File:** `tests/integration/test_chat_reasoning.py` (NEW)
**Estimated Time:** 2-3 hours

**Test Cases:**
- Test chat endpoint with `enable_reasoning=true`
- Test reasoning chain in response
- Test reasoning toggle persistence
- Test reasoning with different agents

#### Task 3.3: E2E Tests for UI Reasoning Toggle
**File:** `tests/e2e/test_reasoning_ui.py` (NEW)
**Estimated Time:** 2-3 hours

**Test Cases:**
- Test reasoning toggle ON/OFF
- Test reasoning chain display in UI
- Test reasoning with different query types
- Test reasoning type selection (if implemented)

#### Task 3.4: Performance Testing
**Estimated Time:** 2-3 hours

**Test Cases:**
- Measure response time with reasoning enabled vs disabled
- Test reasoning with complex queries
- Test reasoning with multiple concurrent requests
- Optimize reasoning execution time if needed

---

### Phase 4: Documentation & Polish (Priority: Low)

#### Task 4.1: Update API Documentation
**File:** `docs/api/README.md`
**Estimated Time:** 1 hour

**Changes:**
- Document `enable_reasoning` parameter in chat endpoint
- Document reasoning chain in response schema
- Add examples of reasoning-enabled queries

#### Task 4.2: Update User Documentation
**File:** `src/ui/web/src/pages/Documentation.tsx`
**Estimated Time:** 1 hour

**Changes:**
- Add section explaining reasoning capability
- Document how to use reasoning toggle
- Explain different reasoning types
- Add examples of reasoning-enhanced responses

#### Task 4.3: Update Architecture Documentation
**File:** `docs/architecture/REASONING_ENGINE_OVERVIEW.md`
**Estimated Time:** 1 hour

**Changes:**
- Update implementation status
- Document agent integration
- Document UI integration
- Add architecture diagrams

---

## Implementation Priority

### High Priority (Must Have)
1. ✅ Task 1.1: Update Chat Router to Support Reasoning
2. ✅ Task 1.2: Update MCP Planner Graph to Support Reasoning
3. ✅ Task 1.3-1.6: Integrate Reasoning into All Agents
4. ✅ Task 2.1: Add Reasoning Toggle to Chat Interface
5. ✅ Task 2.2-2.3: Update Chat API Service and Pass Toggle

### Medium Priority (Should Have)
6. ✅ Task 2.4: Create Reasoning Chain Visualization Component
7. ✅ Task 2.5: Integrate Reasoning Display in Message Bubble
8. ✅ Task 3.1-3.3: Testing & Validation

### Low Priority (Nice to Have)
9. ✅ Task 2.6: Add Reasoning Type Selection
10. ✅ Task 3.4: Performance Testing
11. ✅ Task 4.1-4.3: Documentation Updates

---

## Estimated Timeline

- **Phase 1 (Backend):** 15-20 hours
- **Phase 2 (Frontend):** 12-18 hours
- **Phase 3 (Testing):** 10-14 hours
- **Phase 4 (Documentation):** 3 hours

**Total Estimated Time:** 40-55 hours (1-1.5 weeks for a single developer)

---

## Technical Considerations

### 1. Performance Impact
- **Concern:** Reasoning adds latency (typically 2-5 seconds for complex queries)
- **Solution:** 
  - Only enable reasoning for complex queries (automatic detection)
  - Make reasoning optional (user-controlled toggle)
  - Cache reasoning results for similar queries
  - Use async processing for reasoning steps

### 2. Cost Impact
- **Concern:** Reasoning uses more LLM tokens (increased API costs)
- **Solution:**
  - User-controlled toggle (opt-in)
  - Automatic detection of complex queries (only use when needed)
  - Limit reasoning types based on query complexity

### 3. User Experience
- **Concern:** Reasoning may confuse users with too much detail
- **Solution:**
  - Collapsible reasoning chain display
  - Clear visual separation between response and reasoning
  - Tooltip explaining reasoning capability
  - Default to OFF (opt-in)

### 4. Backward Compatibility
- **Concern:** Changes to API may break existing clients
- **Solution:**
  - Make `enable_reasoning` optional (default: `false`)
  - Make `reasoning_chain` optional in responses
  - Maintain existing API contract

---

## Success Criteria

### Functional Requirements
- ✅ All agents support reasoning capability
- ✅ Chat router accepts and processes reasoning requests
- ✅ UI toggle enables/disables reasoning
- ✅ Reasoning chain displayed in UI when enabled
- ✅ Reasoning works with all agent types (Equipment, Operations, Forecasting, Document, Safety)

### Non-Functional Requirements
- ✅ Response time with reasoning < 10 seconds for complex queries
- ✅ Reasoning toggle persists across sessions (localStorage)
- ✅ Reasoning chain visualization is clear and user-friendly
- ✅ No breaking changes to existing API
- ✅ All tests pass

### User Experience Requirements
- ✅ Reasoning toggle is easily accessible
- ✅ Reasoning chain is clearly separated from main response
- ✅ Users can expand/collapse reasoning details
- ✅ Tooltip explains reasoning capability
- ✅ Default state is OFF (opt-in)

---

## Future Enhancements

1. **Reasoning Analytics Dashboard**
   - Track reasoning usage statistics
   - Analyze reasoning effectiveness
   - Identify most common reasoning types

2. **Custom Reasoning Types**
   - Allow users to define custom reasoning types
   - Domain-specific reasoning patterns
   - Industry-specific reasoning logic

3. **Reasoning Learning**
   - Learn from user feedback on reasoning quality
   - Improve reasoning type selection
   - Optimize reasoning prompts

4. **Reasoning Export**
   - Export reasoning chains as PDF/JSON
   - Share reasoning chains with team
   - Audit trail for decision-making

---

## References

- **Reasoning Engine:** `src/api/services/reasoning/reasoning_engine.py`
- **Safety Agent Integration:** `src/api/agents/safety/safety_agent.py:102-198`
- **Reasoning API:** `src/api/routers/reasoning.py`
- **Current Chat Router:** `src/api/routers/chat.py`
- **MCP Planner Graph:** `src/api/graphs/mcp_integrated_planner_graph.py`
- **Chat UI:** `src/ui/web/src/pages/ChatInterfaceNew.tsx`
- **Reasoning Overview:** `docs/architecture/REASONING_ENGINE_OVERVIEW.md`

---

**Document Version:** 1.0  
**Last Updated:** 2025-01-16  
**Status:** Proposal - Ready for Implementation

