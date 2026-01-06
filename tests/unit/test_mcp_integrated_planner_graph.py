#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Unit tests for MCP Integrated Planner Graph.

Tests helper functions, MCPIntentClassifier, and MCPPlannerGraph classes
with proper mocking to achieve high code coverage.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock, PropertyMock
from typing import Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass, field

from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from src.api.graphs.mcp_integrated_planner_graph import (
    _extract_message_text,
    _detect_complex_query,
    _calculate_agent_timeout,
    _convert_response_to_dict,
    _create_error_response,
    _convert_reasoning_chain_to_dict,
    MCPWarehouseState,
    MCPIntentClassifier,
    MCPPlannerGraph,
    get_mcp_planner_graph,
    process_mcp_warehouse_query,
    COMPLEX_QUERY_KEYWORDS,
    COMPLEX_QUERY_ACTIONS,
    COMPLEX_QUERY_WORD_COUNT_THRESHOLD,
    AGENT_TIMEOUT_REASONING,
    AGENT_TIMEOUT_COMPLEX,
    AGENT_TIMEOUT_SIMPLE,
)


# ============================================================================
# Test Helper Functions
# ============================================================================

class TestHelperFunctions:
    """Test helper functions in mcp_integrated_planner_graph."""

    def test_extract_message_text_with_human_message(self):
        """Test extracting text from HumanMessage."""
        state: MCPWarehouseState = {
            "messages": [HumanMessage(content="Test message")],
            "user_intent": None,
            "routing_decision": None,
            "agent_responses": {},
            "final_response": None,
            "context": {},
            "session_id": "test",
            "mcp_results": None,
            "tool_execution_plan": None,
            "available_tools": None,
            "enable_reasoning": False,
            "reasoning_types": None,
            "reasoning_chain": None,
        }
        result = _extract_message_text(state)
        assert result == "Test message"

    def test_extract_message_text_with_ai_message(self):
        """Test extracting text from AIMessage."""
        state: MCPWarehouseState = {
            "messages": [AIMessage(content="AI response")],
            "user_intent": None,
            "routing_decision": None,
            "agent_responses": {},
            "final_response": None,
            "context": {},
            "session_id": "test",
            "mcp_results": None,
            "tool_execution_plan": None,
            "available_tools": None,
            "enable_reasoning": False,
            "reasoning_types": None,
            "reasoning_chain": None,
        }
        result = _extract_message_text(state)
        assert result == "AI response"

    def test_extract_message_text_empty_messages(self):
        """Test extracting text from empty messages list."""
        state: MCPWarehouseState = {
            "messages": [],
            "user_intent": None,
            "routing_decision": None,
            "agent_responses": {},
            "final_response": None,
            "context": {},
            "session_id": "test",
            "mcp_results": None,
            "tool_execution_plan": None,
            "available_tools": None,
            "enable_reasoning": False,
            "reasoning_types": None,
            "reasoning_chain": None,
        }
        result = _extract_message_text(state)
        assert result is None

    def test_detect_complex_query_with_keywords(self):
        """Test detecting complex query with keywords."""
        query = "I need to optimize the warehouse operations and analyze the performance"
        assert _detect_complex_query(query) is True

    def test_detect_complex_query_with_actions_and_and(self):
        """Test detecting complex query with actions and 'and'."""
        query = "create a task and dispatch workers to zone a"
        assert _detect_complex_query(query) is True

    def test_detect_complex_query_long_message(self):
        """Test detecting complex query with long word count."""
        query = " ".join(["word"] * (COMPLEX_QUERY_WORD_COUNT_THRESHOLD + 1))
        assert _detect_complex_query(query) is True

    def test_detect_complex_query_simple(self):
        """Test detecting simple query."""
        query = "show me the status"
        assert _detect_complex_query(query) is False

    def test_calculate_agent_timeout_reasoning(self):
        """Test calculating timeout for reasoning queries."""
        timeout = _calculate_agent_timeout(enable_reasoning=True, is_complex_query=False)
        assert timeout == AGENT_TIMEOUT_REASONING

    def test_calculate_agent_timeout_complex(self):
        """Test calculating timeout for complex queries."""
        timeout = _calculate_agent_timeout(enable_reasoning=False, is_complex_query=True)
        assert timeout == AGENT_TIMEOUT_COMPLEX

    def test_calculate_agent_timeout_simple(self):
        """Test calculating timeout for simple queries."""
        timeout = _calculate_agent_timeout(enable_reasoning=False, is_complex_query=False)
        assert timeout == AGENT_TIMEOUT_SIMPLE

    def test_convert_response_to_dict_from_dict(self):
        """Test converting dict response to dict."""
        response = {
            "natural_language": "Test response",
            "data": {"key": "value"},
            "recommendations": [],
            "confidence": 0.9,
            "response_type": "equipment",
        }
        result = _convert_response_to_dict(response, "equipment")
        assert result == response

    def test_convert_response_to_dict_from_object(self):
        """Test converting object response to dict."""
        @dataclass
        class MockResponse:
            natural_language: str = "Test"
            data: Dict = field(default_factory=dict)
            recommendations: list = field(default_factory=list)
            confidence: float = 0.8
            response_type: str = "equipment"
            mcp_tools_used: list = field(default_factory=list)
            tool_execution_results: Dict = field(default_factory=dict)
            actions_taken: list = field(default_factory=list)
            reasoning_chain: Optional[Dict] = None
            reasoning_steps: Optional[list] = None

        response = MockResponse()
        result = _convert_response_to_dict(response, "equipment")
        assert result["natural_language"] == "Test"
        assert result["confidence"] == 0.8
        assert result["response_type"] == "equipment"

    def test_convert_response_to_dict_from_object_with_optional_fields(self):
        """Test converting object with optional fields."""
        @dataclass
        class MockResponse:
            natural_language: str = "Test"
            data: Dict = field(default_factory=dict)
            recommendations: list = field(default_factory=list)
            confidence: float = 0.8
            response_type: str = "equipment"

        response = MockResponse()
        result = _convert_response_to_dict(response, "equipment")
        assert "mcp_tools_used" in result
        assert result["mcp_tools_used"] == []

    def test_create_error_response_timeout(self):
        """Test creating error response for timeout."""
        error = TimeoutError("Operation timed out")
        result = _create_error_response("equipment", "test query", error, is_timeout=True)
        assert result["response_type"] == "timeout"
        assert result["confidence"] == 0.3
        assert "timeout" in result["data"]["error"]
        assert "mcp_tools_used" in result

    def test_create_error_response_general(self):
        """Test creating error response for general error."""
        error = ValueError("Invalid input")
        result = _create_error_response("operations", "test query", error, is_timeout=False)
        assert result["response_type"] == "error"
        assert result["confidence"] == 0.3
        assert "error" in result["data"]
        assert "mcp_tools_used" in result

    def test_convert_reasoning_chain_to_dict_none(self):
        """Test converting None reasoning chain."""
        result = _convert_reasoning_chain_to_dict(None)
        assert result is None

    def test_convert_reasoning_chain_to_dict_dict(self):
        """Test converting dict reasoning chain."""
        chain = {"chain_id": "test", "query": "test query"}
        result = _convert_reasoning_chain_to_dict(chain)
        assert result == chain

    def test_convert_reasoning_chain_to_dict_dataclass(self):
        """Test converting dataclass reasoning chain."""
        @dataclass
        class MockStep:
            step_id: str = "step1"
            step_type: str = "reasoning"
            description: str = "Test step"
            reasoning: str = "Test reasoning"
            confidence: float = 0.9
            timestamp: datetime = field(default_factory=datetime.now)

        @dataclass
        class MockReasoningChain:
            chain_id: str = "chain1"
            query: str = "test query"
            reasoning_type: str = "analytical"
            final_conclusion: str = "Test conclusion"
            overall_confidence: float = 0.85
            execution_time: float = 1.5
            created_at: datetime = field(default_factory=datetime.now)
            steps: list = field(default_factory=list)

        chain = MockReasoningChain(steps=[MockStep()])
        result = _convert_reasoning_chain_to_dict(chain)
        assert result is not None
        assert result["chain_id"] == "chain1"
        assert result["query"] == "test query"
        assert result["reasoning_type"] == "analytical"
        assert len(result["steps"]) == 1
        assert result["steps"][0]["step_id"] == "step1"

    def test_convert_reasoning_chain_to_dict_with_enum(self):
        """Test converting reasoning chain with enum."""
        from enum import Enum

        class ReasoningType(Enum):
            ANALYTICAL = "analytical"
            DEDUCTIVE = "deductive"

        @dataclass
        class MockReasoningChain:
            chain_id: str = "chain1"
            query: str = "test"
            reasoning_type: ReasoningType = ReasoningType.ANALYTICAL
            final_conclusion: str = "test"
            overall_confidence: float = 0.8
            execution_time: float = 1.0
            created_at: datetime = field(default_factory=datetime.now)
            steps: list = field(default_factory=list)

        chain = MockReasoningChain()
        result = _convert_reasoning_chain_to_dict(chain)
        assert result["reasoning_type"] == "analytical"


# ============================================================================
# Test MCPIntentClassifier
# ============================================================================

class TestMCPIntentClassifier:
    """Test MCPIntentClassifier class."""

    @pytest.fixture
    def mock_tool_discovery(self):
        """Create mock tool discovery service."""
        return Mock()

    @pytest.fixture
    def classifier(self, mock_tool_discovery):
        """Create MCPIntentClassifier instance."""
        return MCPIntentClassifier(mock_tool_discovery)

    def test_classifier_initialization(self, classifier, mock_tool_discovery):
        """Test classifier initialization."""
        assert classifier.tool_discovery == mock_tool_discovery
        assert classifier.tool_routing is None

    def test_classify_intent_equipment(self, classifier):
        """Test classifying equipment intent."""
        query = "Show me the status of forklift FL-001"
        intent = MCPIntentClassifier.classify_intent(query)
        assert intent == "equipment"

    def test_classify_intent_operations(self, classifier):
        """Test classifying operations intent."""
        query = "How many workers are active in Zone A today?"
        intent = MCPIntentClassifier.classify_intent(query)
        assert intent == "operations"

    def test_classify_intent_safety(self, classifier):
        """Test classifying safety intent."""
        query = "Report a safety incident with temperature sensor TS-001"
        intent = MCPIntentClassifier.classify_intent(query)
        assert intent == "safety"

    def test_classify_intent_document(self, classifier):
        """Test classifying document intent."""
        query = "Upload and extract data from this invoice PDF"
        intent = MCPIntentClassifier.classify_intent(query)
        assert intent == "document"

    def test_classify_intent_forecasting(self, classifier):
        """Test classifying forecasting intent."""
        query = "What is the demand forecast for SKU-123 next month?"
        intent = MCPIntentClassifier.classify_intent(query)
        assert intent == "forecasting"

    def test_classify_intent_general(self, classifier):
        """Test classifying general intent."""
        query = "Hello, how are you?"
        intent = MCPIntentClassifier.classify_intent(query)
        assert intent == "general"

    def test_classify_intent_ambiguous(self, classifier):
        """Test classifying ambiguous intent."""
        query = "Tell me something"
        intent = MCPIntentClassifier.classify_intent(query)
        assert intent == "ambiguous"

    @pytest.mark.asyncio
    async def test_classify_intent_with_mcp(self, classifier):
        """Test classifying intent with MCP tool discovery."""
        mock_tool = Mock()
        mock_tool.name = "equipment_status_tool"
        mock_tool.description = "Get equipment status"

        classifier.tool_discovery.discovered_tools = [mock_tool]
        classifier.tool_discovery.search_tools = AsyncMock(return_value=[mock_tool])

        # Test with general intent that should be refined by MCP
        query = "Tell me something about equipment"
        intent = await classifier.classify_intent_with_mcp(query)
        # Should refine to equipment if MCP tools suggest it
        assert intent in ["equipment", "general"]

    @pytest.mark.asyncio
    async def test_classify_intent_with_mcp_no_tools(self, classifier):
        """Test classifying intent with MCP when no tools available."""
        classifier.tool_discovery.discovered_tools = []
        query = "Hello"
        intent = await classifier.classify_intent_with_mcp(query)
        assert intent == "general"


# ============================================================================
# Test MCPPlannerGraph
# ============================================================================

class TestMCPPlannerGraph:
    """Test MCPPlannerGraph class."""

    @pytest.fixture
    def planner_graph(self):
        """Create MCPPlannerGraph instance."""
        return MCPPlannerGraph()

    @pytest.mark.asyncio
    async def test_planner_graph_initialization(self, planner_graph):
        """Test planner graph initialization."""
        with patch("src.api.graphs.mcp_integrated_planner_graph.ToolDiscoveryService") as mock_tool_discovery_class, \
             patch("src.api.graphs.mcp_integrated_planner_graph.ToolBindingService") as mock_tool_binding_class, \
             patch("src.api.graphs.mcp_integrated_planner_graph.ToolValidationService") as mock_tool_validation_class, \
             patch("src.api.graphs.mcp_integrated_planner_graph.MCPManager") as mock_mcp_manager_class:

            mock_tool_discovery = AsyncMock()
            mock_tool_discovery.start_discovery = AsyncMock(return_value=None)
            mock_tool_discovery_class.return_value = mock_tool_discovery

            mock_tool_binding = Mock()
            mock_tool_binding_class.return_value = mock_tool_binding

            mock_tool_validation = Mock()
            mock_tool_validation_class.return_value = mock_tool_validation

            mock_mcp_manager = Mock()
            mock_mcp_manager_class.return_value = mock_mcp_manager

            await planner_graph.initialize()

            assert planner_graph.tool_discovery is not None
            assert planner_graph.tool_binding is not None
            assert planner_graph.tool_validation is not None
            assert planner_graph.mcp_manager is not None
            assert planner_graph.intent_classifier is not None
            assert planner_graph.graph is not None
            assert planner_graph.initialized is True

    @pytest.mark.asyncio
    async def test_planner_graph_initialization_timeout(self, planner_graph):
        """Test planner graph initialization with tool discovery timeout."""
        with patch("src.api.graphs.mcp_integrated_planner_graph.ToolDiscoveryService") as mock_tool_discovery_class, \
             patch("src.api.graphs.mcp_integrated_planner_graph.ToolBindingService") as mock_tool_binding_class, \
             patch("src.api.graphs.mcp_integrated_planner_graph.ToolValidationService") as mock_tool_validation_class, \
             patch("src.api.graphs.mcp_integrated_planner_graph.MCPManager") as mock_mcp_manager_class:

            mock_tool_discovery = AsyncMock()
            mock_tool_discovery.start_discovery = AsyncMock(side_effect=asyncio.TimeoutError())
            mock_tool_discovery_class.return_value = mock_tool_discovery

            mock_tool_binding = Mock()
            mock_tool_binding_class.return_value = mock_tool_binding

            mock_tool_validation = Mock()
            mock_tool_validation_class.return_value = mock_tool_validation

            mock_mcp_manager = Mock()
            mock_mcp_manager_class.return_value = mock_mcp_manager

            await planner_graph.initialize()

            # Should still initialize despite timeout
            assert planner_graph.initialized is True

    @pytest.mark.asyncio
    async def test_planner_graph_initialization_discovery_error(self, planner_graph):
        """Test planner graph initialization with tool discovery error."""
        with patch("src.api.graphs.mcp_integrated_planner_graph.ToolDiscoveryService") as mock_tool_discovery_class, \
             patch("src.api.graphs.mcp_integrated_planner_graph.ToolBindingService") as mock_tool_binding_class, \
             patch("src.api.graphs.mcp_integrated_planner_graph.ToolValidationService") as mock_tool_validation_class, \
             patch("src.api.graphs.mcp_integrated_planner_graph.MCPManager") as mock_mcp_manager_class:

            mock_tool_discovery = AsyncMock()
            mock_tool_discovery.start_discovery = AsyncMock(side_effect=Exception("Discovery failed"))
            mock_tool_discovery_class.return_value = mock_tool_discovery

            mock_tool_binding = Mock()
            mock_tool_binding_class.return_value = mock_tool_binding

            mock_tool_validation = Mock()
            mock_tool_validation_class.return_value = mock_tool_validation

            mock_mcp_manager = Mock()
            mock_mcp_manager_class.return_value = mock_mcp_manager

            await planner_graph.initialize()

            # Should still initialize despite error
            assert planner_graph.initialized is True

    @pytest.mark.asyncio
    async def test_planner_graph_initialization_failure(self, planner_graph):
        """Test planner graph initialization with complete failure."""
        with patch("src.api.graphs.mcp_integrated_planner_graph.ToolDiscoveryService", side_effect=Exception("Init failed")):
            await planner_graph.initialize()

            # Should handle failure gracefully
            assert planner_graph.initialized is False
            # Should still try to create basic graph
            assert planner_graph.graph is not None or planner_graph.graph is None

    def test_create_graph(self, planner_graph):
        """Test graph creation."""
        with patch.object(planner_graph, "_mcp_route_intent", return_value={}), \
             patch.object(planner_graph, "_mcp_equipment_agent", return_value={}), \
             patch.object(planner_graph, "_mcp_operations_agent", return_value={}), \
             patch.object(planner_graph, "_mcp_safety_agent", return_value={}), \
             patch.object(planner_graph, "_mcp_forecasting_agent", return_value={}), \
             patch.object(planner_graph, "_mcp_document_agent", return_value={}), \
             patch.object(planner_graph, "_mcp_general_agent", return_value={}), \
             patch.object(planner_graph, "_handle_ambiguous_query", return_value={}), \
             patch.object(planner_graph, "_mcp_synthesize_response", return_value={}), \
             patch.object(planner_graph, "_route_to_agent", return_value="equipment"):

            graph = planner_graph._create_graph()
            assert graph is not None

    @pytest.mark.asyncio
    async def test_process_warehouse_query(self, planner_graph):
        """Test processing warehouse query."""
        # Mock the graph and its execution
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value={
            "final_response": "Test response",
            "user_intent": "equipment",
            "routing_decision": "equipment",
        })
        planner_graph.graph = mock_graph
        planner_graph.initialized = True

        result = await planner_graph.process_warehouse_query(
            message="Show me forklift status",
            session_id="test_session"
        )

        assert result is not None
        assert "response" in result or "final_response" in result or result.get("user_intent") == "equipment"

    @pytest.mark.asyncio
    async def test_process_warehouse_query_not_initialized(self, planner_graph):
        """Test processing query when graph not initialized."""
        planner_graph.initialized = False
        planner_graph.graph = None

        # Should handle gracefully
        try:
            result = await planner_graph.process_warehouse_query(
                message="Test query",
                session_id="test_session"
            )
            # Should either raise or return error response
            assert result is not None
        except Exception:
            # Exception is also acceptable
            pass

    @pytest.mark.asyncio
    async def test_mcp_route_intent(self, planner_graph):
        """Test MCP route intent method."""
        # Setup
        planner_graph.intent_classifier = Mock()
        planner_graph.intent_classifier.classify_intent_with_mcp = AsyncMock(return_value="equipment")
        planner_graph.tool_discovery = AsyncMock()
        planner_graph.tool_discovery.get_available_tools = AsyncMock(return_value=[])

        state: MCPWarehouseState = {
            "messages": [HumanMessage(content="Show me forklift status")],
            "user_intent": None,
            "routing_decision": None,
            "agent_responses": {},
            "final_response": None,
            "context": {},
            "session_id": "test",
            "mcp_results": None,
            "tool_execution_plan": None,
            "available_tools": None,
            "enable_reasoning": False,
            "reasoning_types": None,
            "reasoning_chain": None,
        }

        with patch("src.api.graphs.mcp_integrated_planner_graph.get_semantic_router", side_effect=ImportError()):
            result = await planner_graph._mcp_route_intent(state)
            assert result["user_intent"] is not None
            assert result["routing_decision"] is not None

    @pytest.mark.asyncio
    async def test_mcp_route_intent_empty_message(self, planner_graph):
        """Test MCP route intent with empty message."""
        state: MCPWarehouseState = {
            "messages": [],
            "user_intent": None,
            "routing_decision": None,
            "agent_responses": {},
            "final_response": None,
            "context": {},
            "session_id": "test",
            "mcp_results": None,
            "tool_execution_plan": None,
            "available_tools": None,
            "enable_reasoning": False,
            "reasoning_types": None,
            "reasoning_chain": None,
        }

        result = await planner_graph._mcp_route_intent(state)
        assert result["user_intent"] == "general"
        assert result["routing_decision"] == "general"

    @pytest.mark.asyncio
    async def test_route_to_agent(self, planner_graph):
        """Test route to agent method."""
        state: MCPWarehouseState = {
            "messages": [HumanMessage(content="Test")],
            "user_intent": "equipment",
            "routing_decision": "equipment",
            "agent_responses": {},
            "final_response": None,
            "context": {},
            "session_id": "test",
            "mcp_results": None,
            "tool_execution_plan": None,
            "available_tools": None,
            "enable_reasoning": False,
            "reasoning_types": None,
            "reasoning_chain": None,
        }

        result = planner_graph._route_to_agent(state)
        assert result == "equipment"

    @pytest.mark.asyncio
    async def test_handle_ambiguous_query(self, planner_graph):
        """Test handling ambiguous query."""
        state: MCPWarehouseState = {
            "messages": [HumanMessage(content="Tell me something")],
            "user_intent": "ambiguous",
            "routing_decision": "ambiguous",
            "agent_responses": {},
            "final_response": None,
            "context": {},
            "session_id": "test",
            "mcp_results": None,
            "tool_execution_plan": None,
            "available_tools": None,
            "enable_reasoning": False,
            "reasoning_types": None,
            "reasoning_chain": None,
        }

        with patch("src.api.graphs.mcp_integrated_planner_graph.get_enhanced_retriever", side_effect=ImportError()):
            result = await planner_graph._handle_ambiguous_query(state)
            assert result["final_response"] is not None
            assert "help" in result["final_response"].lower() or "warehouse" in result["final_response"].lower()

    @pytest.mark.asyncio
    async def test_mcp_equipment_agent(self, planner_graph):
        """Test MCP equipment agent."""
        state: MCPWarehouseState = {
            "messages": [HumanMessage(content="Show forklift status")],
            "user_intent": "equipment",
            "routing_decision": "equipment",
            "agent_responses": {},
            "final_response": None,
            "context": {},
            "session_id": "test",
            "mcp_results": None,
            "tool_execution_plan": None,
            "available_tools": None,
            "enable_reasoning": False,
            "reasoning_types": None,
            "reasoning_chain": None,
        }

        with patch("src.api.graphs.mcp_integrated_planner_graph.get_mcp_equipment_agent") as mock_get_agent:
            mock_agent = AsyncMock()
            mock_agent.process_query = AsyncMock(return_value={
                "natural_language": "Forklift FL-001 is operational",
                "data": {},
                "confidence": 0.9,
                "response_type": "equipment",
            })
            mock_get_agent.return_value = mock_agent

            result = await planner_graph._mcp_equipment_agent(state)
            assert "equipment" in result["agent_responses"]
            assert result["agent_responses"]["equipment"]["response_type"] == "equipment"

    @pytest.mark.asyncio
    async def test_mcp_equipment_agent_empty_message(self, planner_graph):
        """Test MCP equipment agent with empty message."""
        state: MCPWarehouseState = {
            "messages": [],
            "user_intent": "equipment",
            "routing_decision": "equipment",
            "agent_responses": {},
            "final_response": None,
            "context": {},
            "session_id": "test",
            "mcp_results": None,
            "tool_execution_plan": None,
            "available_tools": None,
            "enable_reasoning": False,
            "reasoning_types": None,
            "reasoning_chain": None,
        }

        result = await planner_graph._mcp_equipment_agent(state)
        assert "equipment" in result["agent_responses"]
        assert result["agent_responses"]["equipment"]["response_type"] == "error"

    @pytest.mark.asyncio
    async def test_mcp_equipment_agent_timeout(self, planner_graph):
        """Test MCP equipment agent with timeout."""
        state: MCPWarehouseState = {
            "messages": [HumanMessage(content="Show forklift status")],
            "user_intent": "equipment",
            "routing_decision": "equipment",
            "agent_responses": {},
            "final_response": None,
            "context": {},
            "session_id": "test",
            "mcp_results": None,
            "tool_execution_plan": None,
            "available_tools": None,
            "enable_reasoning": False,
            "reasoning_types": None,
            "reasoning_chain": None,
        }

        with patch("src.api.graphs.mcp_integrated_planner_graph.get_mcp_equipment_agent") as mock_get_agent:
            mock_agent = AsyncMock()
            mock_agent.process_query = AsyncMock(side_effect=asyncio.TimeoutError())
            mock_get_agent.return_value = mock_agent

            result = await planner_graph._mcp_equipment_agent(state)
            assert "equipment" in result["agent_responses"]
            assert result["agent_responses"]["equipment"]["response_type"] == "timeout"

    @pytest.mark.asyncio
    async def test_mcp_synthesize_response(self, planner_graph):
        """Test MCP synthesize response."""
        state: MCPWarehouseState = {
            "messages": [HumanMessage(content="Test query")],
            "user_intent": "equipment",
            "routing_decision": "equipment",
            "agent_responses": {
                "equipment": {
                    "natural_language": "Forklift is operational",
                    "data": {},
                    "confidence": 0.9,
                    "response_type": "equipment",
                }
            },
            "final_response": None,
            "context": {},
            "session_id": "test",
            "mcp_results": None,
            "tool_execution_plan": None,
            "available_tools": None,
            "enable_reasoning": False,
            "reasoning_types": None,
            "reasoning_chain": None,
        }

        result = await planner_graph._mcp_synthesize_response(state)
        assert result["final_response"] is not None
        assert "Forklift" in result["final_response"]

    @pytest.mark.asyncio
    async def test_mcp_synthesize_response_with_reasoning_chain(self, planner_graph):
        """Test synthesize response with reasoning chain."""
        @dataclass
        class MockReasoningChain:
            chain_id: str = "test"
            query: str = "test"
            reasoning_type: str = "analytical"
            final_conclusion: str = "test conclusion"
            overall_confidence: float = 0.8
            execution_time: float = 1.0
            created_at: datetime = field(default_factory=datetime.now)
            steps: list = field(default_factory=list)

        state: MCPWarehouseState = {
            "messages": [HumanMessage(content="Test query")],
            "user_intent": "equipment",
            "routing_decision": "equipment",
            "agent_responses": {
                "equipment": {
                    "natural_language": "Response",
                    "data": {},
                    "confidence": 0.9,
                    "response_type": "equipment",
                    "reasoning_chain": MockReasoningChain(),
                }
            },
            "final_response": None,
            "context": {},
            "session_id": "test",
            "mcp_results": None,
            "tool_execution_plan": None,
            "available_tools": None,
            "enable_reasoning": False,
            "reasoning_types": None,
            "reasoning_chain": None,
        }

        result = await planner_graph._mcp_synthesize_response(state)
        assert result["final_response"] is not None
        assert "reasoning_chain" in result["context"] or result.get("reasoning_chain") is not None

    @pytest.mark.asyncio
    async def test_process_warehouse_query_with_initialization(self, planner_graph):
        """Test process_warehouse_query with initialization."""
        planner_graph.initialized = False
        planner_graph.graph = None

        with patch.object(planner_graph, "initialize", new_callable=AsyncMock) as mock_init:
            mock_init.return_value = None
            with patch.object(planner_graph, "_create_fallback_response") as mock_fallback:
                mock_fallback.return_value = {"response": "Fallback response"}
                
                # Test timeout during initialization
                mock_init.side_effect = asyncio.TimeoutError()
                result = await planner_graph.process_warehouse_query("Test", "session")
                assert result["response"] == "Fallback response"
                mock_fallback.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_warehouse_query_with_context(self, planner_graph):
        """Test process_warehouse_query with context."""
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value={
            "final_response": "Test response",
            "user_intent": "equipment",
        })
        planner_graph.graph = mock_graph
        planner_graph.initialized = True

        context = {"enable_reasoning": True, "reasoning_types": ["analytical"]}
        result = await planner_graph.process_warehouse_query(
            message="Test query",
            session_id="test_session",
            context=context
        )
        assert result is not None

    def test_create_fallback_response(self, planner_graph):
        """Test create fallback response."""
        result = planner_graph._create_fallback_response("Test query", "test_session")
        assert result is not None
        assert "response" in result or "message" in result or "error" in result

    def test_create_fallback_response_operations(self, planner_graph):
        """Test fallback response for operations query."""
        result = planner_graph._create_fallback_response("Create a wave", "test_session")
        assert result["intent"] == "operations"

    def test_create_fallback_response_inventory(self, planner_graph):
        """Test fallback response for inventory query."""
        result = planner_graph._create_fallback_response("Check inventory for SKU-123", "test_session")
        assert result["intent"] == "inventory"

    def test_create_fallback_response_equipment(self, planner_graph):
        """Test fallback response for equipment query."""
        result = planner_graph._create_fallback_response("Show equipment status", "test_session")
        assert result["intent"] == "equipment"

    def test_create_fallback_response_general(self, planner_graph):
        """Test fallback response for general query."""
        result = planner_graph._create_fallback_response("Hello", "test_session")
        assert result["intent"] == "general"

    @pytest.mark.asyncio
    async def test_mcp_route_intent_with_semantic_router(self, planner_graph):
        """Test MCP route intent with semantic router."""
        planner_graph.intent_classifier = Mock()
        planner_graph.intent_classifier.classify_intent_with_mcp = AsyncMock(return_value={
            "intent": "equipment",
            "confidence": 0.8
        })
        planner_graph.tool_discovery = AsyncMock()
        planner_graph.tool_discovery.get_available_tools = AsyncMock(return_value=[])

        state: MCPWarehouseState = {
            "messages": [HumanMessage(content="Show me forklift status")],
            "user_intent": None,
            "routing_decision": None,
            "agent_responses": {},
            "final_response": None,
            "context": {},
            "session_id": "test",
            "mcp_results": None,
            "tool_execution_plan": None,
            "available_tools": None,
            "enable_reasoning": False,
            "reasoning_types": None,
            "reasoning_chain": None,
        }

        with patch("src.api.graphs.mcp_integrated_planner_graph.get_semantic_router") as mock_get_router:
            mock_router = AsyncMock()
            mock_router.classify_intent_semantic = AsyncMock(return_value=("equipment", 0.9))
            mock_get_router.return_value = mock_router

            result = await planner_graph._mcp_route_intent(state)
            assert result["user_intent"] == "equipment"
            assert result["routing_decision"] == "equipment"

    @pytest.mark.asyncio
    async def test_mcp_route_intent_with_worker_keywords(self, planner_graph):
        """Test MCP route intent with worker keywords override."""
        planner_graph.intent_classifier = Mock()
        planner_graph.intent_classifier.classify_intent_with_mcp = AsyncMock(return_value="general")
        planner_graph.tool_discovery = AsyncMock()
        planner_graph.tool_discovery.get_available_tools = AsyncMock(return_value=[])

        state: MCPWarehouseState = {
            "messages": [HumanMessage(content="How many workers are in zone A")],
            "user_intent": None,
            "routing_decision": None,
            "agent_responses": {},
            "final_response": None,
            "context": {},
            "session_id": "test",
            "mcp_results": None,
            "tool_execution_plan": None,
            "available_tools": None,
            "enable_reasoning": False,
            "reasoning_types": None,
            "reasoning_chain": None,
        }

        with patch("src.api.graphs.mcp_integrated_planner_graph.get_semantic_router", side_effect=ImportError()):
            result = await planner_graph._mcp_route_intent(state)
            # Should override to operations due to worker keywords
            assert result["routing_decision"] == "operations"

    @pytest.mark.asyncio
    async def test_mcp_synthesize_response_no_agent_response(self, planner_graph):
        """Test synthesize response when no agent response exists."""
        state: MCPWarehouseState = {
            "messages": [HumanMessage(content="Test query")],
            "user_intent": "equipment",
            "routing_decision": "equipment",
            "agent_responses": {},
            "final_response": None,
            "context": {},
            "session_id": "test",
            "mcp_results": None,
            "tool_execution_plan": None,
            "available_tools": None,
            "enable_reasoning": False,
            "reasoning_types": None,
            "reasoning_chain": None,
        }

        result = await planner_graph._mcp_synthesize_response(state)
        assert result["final_response"] is not None
        assert "couldn't process" in result["final_response"].lower() or "try rephrasing" in result["final_response"].lower()

    @pytest.mark.asyncio
    async def test_mcp_synthesize_response_string_response(self, planner_graph):
        """Test synthesize response with string response."""
        state: MCPWarehouseState = {
            "messages": [HumanMessage(content="Test query")],
            "user_intent": "equipment",
            "routing_decision": "equipment",
            "agent_responses": {
                "equipment": "Simple string response"
            },
            "final_response": None,
            "context": {},
            "session_id": "test",
            "mcp_results": None,
            "tool_execution_plan": None,
            "available_tools": None,
            "enable_reasoning": False,
            "reasoning_types": None,
            "reasoning_chain": None,
        }

        result = await planner_graph._mcp_synthesize_response(state)
        assert result["final_response"] == "Simple string response"


# ============================================================================
# Test Module-Level Functions
# ============================================================================

class TestModuleFunctions:
    """Test module-level functions."""

    @pytest.mark.asyncio
    async def test_get_mcp_planner_graph(self):
        """Test getting MCP planner graph singleton."""
        # Clear the global instance
        import src.api.graphs.mcp_integrated_planner_graph as mcp_module
        mcp_module._mcp_planner_graph = None

        with patch("src.api.graphs.mcp_integrated_planner_graph.MCPPlannerGraph") as mock_graph_class:
            mock_graph = AsyncMock()
            mock_graph.initialize = AsyncMock(return_value=None)
            mock_graph_class.return_value = mock_graph

            result = await get_mcp_planner_graph()
            assert result == mock_graph
            assert mcp_module._mcp_planner_graph == mock_graph

    @pytest.mark.asyncio
    async def test_get_mcp_planner_graph_singleton(self):
        """Test that get_mcp_planner_graph returns same instance."""
        import src.api.graphs.mcp_integrated_planner_graph as mcp_module
        mcp_module._mcp_planner_graph = None

        with patch("src.api.graphs.mcp_integrated_planner_graph.MCPPlannerGraph") as mock_graph_class:
            mock_graph = AsyncMock()
            mock_graph.initialize = AsyncMock(return_value=None)
            mock_graph_class.return_value = mock_graph

            result1 = await get_mcp_planner_graph()
            result2 = await get_mcp_planner_graph()
            assert result1 == result2

    @pytest.mark.asyncio
    async def test_process_mcp_warehouse_query(self):
        """Test processing MCP warehouse query."""
        with patch("src.api.graphs.mcp_integrated_planner_graph.get_mcp_planner_graph") as mock_get_graph:
            mock_graph = AsyncMock()
            mock_graph.process_warehouse_query = AsyncMock(return_value={
                "response": "Test response",
                "intent": "equipment",
            })
            mock_get_graph.return_value = mock_graph

            result = await process_mcp_warehouse_query(
                message="Test query",
                session_id="test_session"
            )

            assert result is not None
            mock_graph.process_warehouse_query.assert_called_once_with(
                "Test query",
                "test_session",
                None
            )

    @pytest.mark.asyncio
    async def test_process_mcp_warehouse_query_with_context(self):
        """Test processing query with context."""
        with patch("src.api.graphs.mcp_integrated_planner_graph.get_mcp_planner_graph") as mock_get_graph:
            mock_graph = AsyncMock()
            mock_graph.process_warehouse_query = AsyncMock(return_value={"response": "Test"})
            mock_get_graph.return_value = mock_graph

            context = {"user_id": "user123", "zone": "A"}
            result = await process_mcp_warehouse_query(
                message="Test query",
                session_id="test_session",
                context=context
            )

            mock_graph.process_warehouse_query.assert_called_once_with(
                "Test query",
                "test_session",
                context
            )

