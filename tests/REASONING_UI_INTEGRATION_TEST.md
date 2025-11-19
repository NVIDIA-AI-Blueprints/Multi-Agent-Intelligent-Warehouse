# Reasoning UI Integration Test Guide

## Overview

This document provides a comprehensive testing guide for Phase 2: Frontend Integration of the reasoning capability.

## Test Environment Setup

1. **Start the backend server:**
   ```bash
   ./scripts/start_server.sh
   ```

2. **Start the frontend (if not already running):**
   ```bash
   cd src/ui/web
   npm start
   ```

3. **Access the application:**
   - Web UI: http://localhost:3001
   - API: http://localhost:8001
   - API Docs: http://localhost:8001/docs

## Test Cases

### Test 1: Toggle Switch Visibility and Functionality

**Objective:** Verify the reasoning toggle switch is visible and functional.

**Steps:**
1. Navigate to the chat interface (`http://localhost:3001/chat`)
2. Locate the "Enable Reasoning" toggle switch above the input field
3. Verify the toggle is visible with a psychology icon (🧠)
4. Click the toggle to enable reasoning
5. Verify the toggle changes state (ON/OFF)
6. Verify the icon color changes to green (#76B900) when enabled

**Expected Results:**
- ✅ Toggle switch is visible
- ✅ Toggle changes state when clicked
- ✅ Icon color changes appropriately
- ✅ Toggle state persists during the session

---

### Test 2: Reasoning Type Selection UI

**Objective:** Verify the reasoning type selection UI appears and functions correctly.

**Steps:**
1. Enable the reasoning toggle (from Test 1)
2. Click the expand/collapse button next to the toggle
3. Verify a collapsible panel appears with reasoning type options
4. Verify all 5 reasoning types are listed:
   - Chain of Thought
   - Multi-Hop
   - Scenario Analysis
   - Causal Reasoning
   - Pattern Recognition
5. Select one or more reasoning types
6. Verify selected types appear as chips above the input field
7. Verify chips can be removed by clicking the delete icon
8. Collapse the panel and verify it can be expanded again

**Expected Results:**
- ✅ Collapsible panel appears when toggle is enabled
- ✅ All 5 reasoning types are listed with descriptions
- ✅ Types can be selected/deselected via checkboxes
- ✅ Selected types appear as removable chips
- ✅ Panel can be collapsed and expanded

---

### Test 3: Simple Query Without Reasoning

**Objective:** Verify that queries work normally when reasoning is disabled.

**Steps:**
1. Ensure reasoning toggle is OFF
2. Send a simple query: "What is the status of forklift FL-001?"
3. Verify the response is received normally
4. Verify no reasoning chain is displayed in the response

**Expected Results:**
- ✅ Query is processed successfully
- ✅ Response is displayed normally
- ✅ No reasoning chain visualization appears
- ✅ Response time is normal (no additional delay)

---

### Test 4: Complex Query With Reasoning Enabled

**Objective:** Verify reasoning is applied to complex queries when enabled.

**Steps:**
1. Enable the reasoning toggle
2. Leave reasoning types empty (auto-selection)
3. Send a complex query: "Why is forklift FL-001 showing high temperature readings and what actions should be taken?"
4. Wait for the response
5. Verify the response includes a reasoning chain visualization
6. Expand the reasoning chain accordion
7. Verify reasoning steps are displayed with:
   - Step numbers
   - Reasoning type labels
   - Descriptions
   - Reasoning text
   - Confidence scores
   - Progress bars

**Expected Results:**
- ✅ Response includes reasoning chain
- ✅ Reasoning chain is displayed in an accordion format
- ✅ All reasoning steps are visible with proper formatting
- ✅ Confidence scores are displayed
- ✅ Final conclusion is shown (if available)

---

### Test 5: Specific Reasoning Type Selection

**Objective:** Verify that specific reasoning types can be selected and used.

**Steps:**
1. Enable the reasoning toggle
2. Expand the reasoning type selection panel
3. Select "Causal Reasoning" and "Chain of Thought"
4. Send a query: "Analyze the recent increase in minor incidents in Zone C"
5. Verify the response includes reasoning
6. Verify the reasoning types used match the selected types (or are appropriate for the query)

**Expected Results:**
- ✅ Selected reasoning types are sent to the API
- ✅ Response includes reasoning chain
- ✅ Reasoning types in the response match or are appropriate for the query

---

### Test 6: Reasoning Chain Visualization

**Objective:** Verify the reasoning chain visualization component displays correctly.

**Steps:**
1. Enable reasoning and send a complex query
2. Verify the reasoning chain appears in the message bubble
3. Verify the compact view shows:
   - Chain ID or step count
   - Reasoning type chip
   - Overall confidence chip
   - Expandable accordion
4. Expand the accordion
5. Verify each step shows:
   - Step number
   - Reasoning type with color coding
   - Description
   - Reasoning text
   - Confidence score with progress bar
6. Verify the final conclusion section (if present)

**Expected Results:**
- ✅ Reasoning chain is displayed in compact mode by default
- ✅ Accordion can be expanded to show details
- ✅ Each step is properly formatted with color coding
- ✅ Confidence scores are displayed with visual indicators
- ✅ Final conclusion is highlighted

---

### Test 7: Multiple Messages With Reasoning

**Objective:** Verify reasoning works correctly across multiple messages.

**Steps:**
1. Enable reasoning
2. Send query 1: "Why is forklift FL-001 showing high temperature?"
3. Verify reasoning chain appears
4. Send query 2: "What if we optimize the picking route in Zone B?"
5. Verify reasoning chain appears for the second message
6. Verify both reasoning chains are independent and correctly displayed

**Expected Results:**
- ✅ Each message with reasoning shows its own reasoning chain
- ✅ Reasoning chains don't interfere with each other
- ✅ Previous reasoning chains remain visible and expandable

---

### Test 8: Error Handling

**Objective:** Verify graceful error handling when reasoning fails.

**Steps:**
1. Enable reasoning
2. Send a query that might cause an error (e.g., very long query, special characters)
3. Verify the system handles errors gracefully
4. Verify the response still appears even if reasoning fails
5. Verify no reasoning chain is shown if reasoning failed

**Expected Results:**
- ✅ System handles errors gracefully
- ✅ Response is still displayed even if reasoning fails
- ✅ No broken UI elements or crashes
- ✅ Error messages are user-friendly (if displayed)

---

### Test 9: Performance Testing

**Objective:** Verify reasoning doesn't significantly impact performance.

**Steps:**
1. Enable reasoning
2. Send a complex query and measure response time
3. Disable reasoning
4. Send the same query and measure response time
5. Compare response times
6. Verify the UI remains responsive during reasoning processing

**Expected Results:**
- ✅ Response time with reasoning is acceptable (< 10 seconds for complex queries)
- ✅ UI remains responsive during processing
- ✅ Loading indicators are shown appropriately

---

### Test 10: UI Responsiveness

**Objective:** Verify the UI is responsive and works on different screen sizes.

**Steps:**
1. Test on desktop (1920x1080)
2. Test on tablet (768x1024)
3. Test on mobile (375x667)
4. Verify reasoning toggle is accessible on all sizes
5. Verify reasoning chain visualization is readable on all sizes
6. Verify reasoning type selection panel is usable on all sizes

**Expected Results:**
- ✅ UI is responsive on all screen sizes
- ✅ Reasoning controls are accessible
- ✅ Reasoning chain visualization is readable
- ✅ No horizontal scrolling issues

---

## API Integration Verification

### Verify API Request

**Check Network Tab:**
1. Open browser DevTools (F12)
2. Go to Network tab
3. Enable reasoning and send a query
4. Find the `/api/v1/chat` request
5. Verify the request payload includes:
   ```json
   {
     "message": "...",
     "enable_reasoning": true,
     "reasoning_types": ["causal", "chain_of_thought"]  // if selected
   }
   ```

### Verify API Response

**Check Network Tab Response:**
1. Find the `/api/v1/chat` response
2. Verify the response includes:
   ```json
   {
     "reply": "...",
     "reasoning_chain": {
       "chain_id": "...",
       "reasoning_type": "...",
       "steps": [...],
       "final_conclusion": "...",
       "overall_confidence": 0.85
     },
     "reasoning_steps": [...]
   }
   ```

---

## Visual Regression Testing

### Screenshots to Capture

1. **Chat interface with reasoning toggle OFF**
2. **Chat interface with reasoning toggle ON**
3. **Reasoning type selection panel expanded**
4. **Message with reasoning chain (collapsed)**
5. **Message with reasoning chain (expanded)**
6. **Multiple messages with reasoning chains**

---

## Known Issues and Limitations

1. **Reasoning is only applied to complex queries** - Simple queries may not trigger reasoning even when enabled
2. **Auto-selection of reasoning types** - If no types are selected, the system auto-selects based on query complexity
3. **Performance impact** - Reasoning adds latency (typically 2-5 seconds for complex queries)

---

## Test Checklist

- [ ] Toggle switch is visible and functional
- [ ] Reasoning type selection UI appears and works
- [ ] Simple queries work without reasoning
- [ ] Complex queries trigger reasoning when enabled
- [ ] Specific reasoning types can be selected
- [ ] Reasoning chain visualization displays correctly
- [ ] Multiple messages with reasoning work correctly
- [ ] Error handling is graceful
- [ ] Performance is acceptable
- [ ] UI is responsive on different screen sizes
- [ ] API requests include reasoning parameters
- [ ] API responses include reasoning data

---

## Troubleshooting

### Issue: Reasoning toggle doesn't appear
**Solution:** Check that the frontend is using the latest code and refresh the page.

### Issue: Reasoning chain doesn't display
**Solution:** 
1. Check browser console for errors
2. Verify API response includes `reasoning_chain` or `reasoning_steps`
3. Check that the query is complex enough to trigger reasoning

### Issue: Reasoning types don't appear in selection
**Solution:** Check that `availableReasoningTypes` array is properly defined in `ChatInterfaceNew.tsx`.

### Issue: API request doesn't include reasoning parameters
**Solution:** 
1. Check that `enable_reasoning` state is properly set
2. Verify the `chatMutation.mutateAsync` call includes reasoning parameters
3. Check browser console for errors

---

## Success Criteria

Phase 2 is considered complete when:
- ✅ All test cases pass
- ✅ No linting errors
- ✅ UI is responsive and accessible
- ✅ Reasoning chains are displayed correctly
- ✅ API integration works end-to-end
- ✅ Error handling is graceful
- ✅ Performance is acceptable

---

**Last Updated:** 2025-01-16
**Status:** Ready for Testing


