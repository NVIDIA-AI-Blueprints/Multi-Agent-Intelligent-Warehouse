"""
Enhanced Test script for answer quality assessment with log analysis.

Tests agent responses for natural language quality, completeness, and correctness.
Captures and analyzes logs to provide insights and recommendations.
"""

import asyncio
import sys
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
import json
import re
from datetime import datetime
from collections import defaultdict
import logging
from io import StringIO

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.api.agents.operations.mcp_operations_agent import (
    MCPOperationsCoordinationAgent,
    MCPOperationsQuery,
)
from src.api.agents.inventory.mcp_equipment_agent import (
    MCPEquipmentAssetOperationsAgent,
    MCPEquipmentQuery,
)
from src.api.agents.safety.mcp_safety_agent import (
    MCPSafetyComplianceAgent,
    MCPSafetyQuery,
)
from src.api.services.validation import get_response_validator


# Test queries for each agent
TEST_QUERIES = {
    "operations": [
        "Create a wave for orders 1001-1010 in Zone A",
        "Dispatch forklift FL-07 to Zone A for pick operations",
        "What's the status of task TASK_PICK_20251206_155737?",
        "Show me all available workers in Zone B",
    ],
    "equipment": [
        "What's the status of our forklift fleet?",
        "Show me all available forklifts in Zone A",
        "When is FL-01 due for maintenance?",
        "What equipment is currently in maintenance?",
    ],
    "safety": [
        "What are the forklift operations safety procedures?",
        "Report a machine over-temp event at Dock D2",
        "What safety incidents have occurred today?",
        "Show me the safety checklist for equipment maintenance",
    ],
}


class LogAnalyzer:
    """Analyzes logs to extract insights and patterns."""
    
    def __init__(self):
        self.log_buffer = StringIO()
        self.log_handler = None
        self.log_patterns = {
            "routing": {
                "pattern": r"routing_decision|Intent classified|Semantic routing",
                "count": 0,
                "examples": []
            },
            "tool_execution": {
                "pattern": r"Executing.*tool|Tool.*executed|tool.*success|tool.*failed",
                "count": 0,
                "examples": []
            },
            "llm_calls": {
                "pattern": r"LLM generation|generate_response|nim_client",
                "count": 0,
                "examples": []
            },
            "validation": {
                "pattern": r"validation|Validation|Response validation",
                "count": 0,
                "examples": []
            },
            "errors": {
                "pattern": r"ERROR:.*|Exception:|Traceback|Failed to|failed with|error occurred",
                "count": 0,
                "examples": []
            },
            "warnings": {
                "pattern": r"WARNING|Warning|warning",
                "count": 0,
                "examples": []
            },
            "timeouts": {
                "pattern": r"timeout|Timeout|TIMEOUT",
                "count": 0,
                "examples": []
            },
            "cache": {
                "pattern": r"Cache hit|Cache miss|cached|Cache entry|Cache hit for|Cached result",
                "count": 0,
                "examples": []
            },
            "confidence": {
                "pattern": r"confidence|Confidence|CONFIDENCE",
                "count": 0,
                "examples": []
            },
            "tool_discovery": {
                "pattern": r"tool.*discover|discovered.*tool|Tool discovery",
                "count": 0,
                "examples": []
            }
        }
    
    def setup_log_capture(self):
        """Setup log capture for analysis."""
        # Create a custom handler that captures logs
        self.log_handler = logging.StreamHandler(self.log_buffer)
        self.log_handler.setLevel(logging.DEBUG)
        
        # Get root logger and add handler
        root_logger = logging.getLogger()
        root_logger.addHandler(self.log_handler)
        root_logger.setLevel(logging.DEBUG)
    
    def analyze_logs(self) -> Dict[str, Any]:
        """Analyze captured logs for patterns and insights."""
        log_content = self.log_buffer.getvalue()
        
        analysis = {
            "total_log_lines": len(log_content.split('\n')),
            "patterns": {},
            "insights": [],
            "recommendations": []
        }
        
        # Analyze each pattern
        for pattern_name, pattern_info in self.log_patterns.items():
            matches = re.findall(pattern_info["pattern"], log_content, re.IGNORECASE)
            pattern_info["count"] = len(matches)
            
            # Extract example lines
            lines = log_content.split('\n')
            pattern_info["examples"] = [
                line.strip() for line in lines 
                if re.search(pattern_info["pattern"], line, re.IGNORECASE)
            ][:5]  # Keep first 5 examples
            
            analysis["patterns"][pattern_name] = {
                "count": pattern_info["count"],
                "examples": pattern_info["examples"][:3]  # Keep top 3 for report
            }
        
        # Generate insights
        analysis["insights"] = self._generate_insights(analysis)
        
        # Generate recommendations
        analysis["recommendations"] = self._generate_recommendations(analysis)
        
        return analysis
    
    def _generate_insights(self, analysis: Dict[str, Any]) -> List[str]:
        """Generate insights from log analysis."""
        insights = []
        patterns = analysis["patterns"]
        
        # Routing insights
        if patterns.get("routing", {}).get("count", 0) > 0:
            insights.append(f"Routing decisions made: {patterns['routing']['count']} times")
        
        # Tool execution insights
        tool_count = patterns.get("tool_execution", {}).get("count", 0)
        if tool_count > 0:
            insights.append(f"Tool executions detected: {tool_count} operations")
        
        # Error insights
        error_count = patterns.get("errors", {}).get("count", 0)
        if error_count > 0:
            insights.append(f"⚠️ Errors detected: {error_count} occurrences")
        else:
            insights.append("✅ No errors detected in logs")
        
        # Warning insights
        warning_count = patterns.get("warnings", {}).get("count", 0)
        if warning_count > 0:
            insights.append(f"⚠️ Warnings detected: {warning_count} occurrences")
        
        # Timeout insights
        timeout_count = patterns.get("timeouts", {}).get("count", 0)
        if timeout_count > 0:
            insights.append(f"⏱️ Timeouts detected: {timeout_count} occurrences")
        
        # LLM call insights
        llm_count = patterns.get("llm_calls", {}).get("count", 0)
        if llm_count > 0:
            insights.append(f"LLM calls made: {llm_count} requests")
        
        # Cache insights
        cache_count = patterns.get("cache", {}).get("count", 0)
        if cache_count > 0:
            insights.append(f"Cache operations: {cache_count} hits/misses")
        
        return insights
    
    def _generate_recommendations(self, analysis: Dict[str, Any]) -> List[str]:
        """Generate recommendations based on log analysis."""
        recommendations = []
        patterns = analysis["patterns"]
        
        # Error recommendations
        if patterns.get("errors", {}).get("count", 0) > 5:
            recommendations.append({
                "priority": "high",
                "category": "error_handling",
                "message": "High error rate detected. Review error patterns and improve error handling.",
                "action": "Analyze error examples and implement better error recovery mechanisms"
            })
        
        # Timeout recommendations
        if patterns.get("timeouts", {}).get("count", 0) > 0:
            recommendations.append({
                "priority": "medium",
                "category": "performance",
                "message": "Timeouts detected. Consider optimizing query processing or increasing timeouts.",
                "action": "Review timeout occurrences and optimize slow operations"
            })
        
        # Tool execution recommendations
        tool_count = patterns.get("tool_execution", {}).get("count", 0)
        if tool_count == 0:
            recommendations.append({
                "priority": "low",
                "category": "tool_usage",
                "message": "No tool executions detected. Verify tool discovery and execution is working.",
                "action": "Check tool discovery service and ensure tools are being called"
            })
        
        # LLM call recommendations
        llm_count = patterns.get("llm_calls", {}).get("count", 0)
        if llm_count > 20:
            recommendations.append({
                "priority": "medium",
                "category": "performance",
                "message": "High number of LLM calls. Consider caching or optimizing prompts.",
                "action": "Review LLM call patterns and implement caching where appropriate"
            })
        
        # Validation recommendations
        validation_count = patterns.get("validation", {}).get("count", 0)
        if validation_count == 0:
            recommendations.append({
                "priority": "low",
                "category": "quality",
                "message": "No validation detected. Ensure response validation is enabled.",
                "action": "Verify validation service is being called for all responses"
            })
        
        return recommendations
    
    def clear_logs(self):
        """Clear the log buffer."""
        self.log_buffer = StringIO()
        if self.log_handler:
            self.log_handler.stream = self.log_buffer


async def test_agent_response(
    agent_name: str, query: str, agent, query_class, log_analyzer: LogAnalyzer
) -> Dict[str, Any]:
    """Test a single agent response with log analysis."""
    print(f"\n{'='*80}")
    print(f"Testing {agent_name}: {query}")
    print(f"{'='*80}")
    
    # Clear logs before test
    log_analyzer.clear_logs()
    
    start_time = datetime.now()
    
    try:
        # Create query object
        if agent_name == "operations":
            query_obj = MCPOperationsQuery(
                intent="general",
                entities={},
                context={},
                user_query=query,
            )
            response = await agent.process_query(query, context={}, session_id="test")
        elif agent_name == "equipment":
            response = await agent.process_query(query, context={}, session_id="test")
        elif agent_name == "safety":
            response = await agent.process_query(query, context={}, session_id="test")
        else:
            return {"error": f"Unknown agent: {agent_name}"}
        
        end_time = datetime.now()
        processing_time = (end_time - start_time).total_seconds()
        
        # Validate response
        validator = get_response_validator()
        validation_result = validator.validate(
            response={
                "natural_language": response.natural_language,
                "confidence": response.confidence,
                "response_type": response.response_type,
                "recommendations": response.recommendations,
                "actions_taken": response.actions_taken,
                "mcp_tools_used": response.mcp_tools_used or [],
                "tool_execution_results": response.tool_execution_results or {},
            },
            query=query,
            tool_results=response.tool_execution_results or {},
        )
        
        # Analyze logs
        log_analysis = log_analyzer.analyze_logs()
        
        # Prepare result
        result = {
            "agent": agent_name,
            "query": query,
            "processing_time_seconds": processing_time,
            "response": {
                "natural_language": response.natural_language[:200] + "..." if len(response.natural_language) > 200 else response.natural_language,
                "confidence": response.confidence,
                "response_type": response.response_type,
                "recommendations_count": len(response.recommendations),
                "actions_taken_count": len(response.actions_taken or []),
                "tools_used": response.mcp_tools_used or [],
                "tools_used_count": len(response.mcp_tools_used or []),
            },
            "validation": {
                "is_valid": validation_result.is_valid,
                "score": validation_result.score,
                "issues": validation_result.issues,
                "warnings": validation_result.warnings,
                "suggestions": validation_result.suggestions,
            },
            "log_analysis": log_analysis,
            "timestamp": datetime.now().isoformat(),
        }
        
        # Print results
        print(f"\n✅ Response Generated")
        print(f"   Natural Language: {response.natural_language[:150]}...")
        print(f"   Confidence: {response.confidence:.2f}")
        print(f"   Tools Used: {len(response.mcp_tools_used or [])}")
        print(f"   Processing Time: {processing_time:.2f}s")
        
        print(f"\n📊 Validation Results")
        print(f"   Valid: {'✅' if validation_result.is_valid else '❌'}")
        print(f"   Score: {validation_result.score:.2f}")
        
        if validation_result.issues:
            print(f"   Issues: {len(validation_result.issues)}")
            for issue in validation_result.issues[:3]:
                print(f"      - {issue}")
        
        if validation_result.warnings:
            print(f"   Warnings: {len(validation_result.warnings)}")
            for warning in validation_result.warnings[:3]:
                print(f"      - {warning}")
        
        print(f"\n📋 Log Analysis")
        print(f"   Total Log Lines: {log_analysis['total_log_lines']}")
        print(f"   Routing Decisions: {log_analysis['patterns'].get('routing', {}).get('count', 0)}")
        print(f"   Tool Executions: {log_analysis['patterns'].get('tool_execution', {}).get('count', 0)}")
        print(f"   LLM Calls: {log_analysis['patterns'].get('llm_calls', {}).get('count', 0)}")
        print(f"   Errors: {log_analysis['patterns'].get('errors', {}).get('count', 0)}")
        print(f"   Warnings: {log_analysis['patterns'].get('warnings', {}).get('count', 0)}")
        
        return result
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        
        # Analyze logs even on error
        log_analysis = log_analyzer.analyze_logs()
        
        return {
            "agent": agent_name,
            "query": query,
            "error": str(e),
            "log_analysis": log_analysis,
            "timestamp": datetime.now().isoformat(),
        }


async def run_quality_tests():
    """Run enhanced quality tests for all agents with log analysis."""
    print("="*80)
    print("ENHANCED ANSWER QUALITY TEST SUITE WITH LOG ANALYSIS")
    print("="*80)
    print(f"Started at: {datetime.now().isoformat()}")
    
    # Setup log analyzer
    log_analyzer = LogAnalyzer()
    log_analyzer.setup_log_capture()
    
    results = []
    
    # Initialize agents
    try:
        print("\n🔧 Initializing agents...")
        operations_agent = MCPOperationsCoordinationAgent()
        await operations_agent.initialize()
        
        equipment_agent = MCPEquipmentAssetOperationsAgent()
        await equipment_agent.initialize()
        
        safety_agent = MCPSafetyComplianceAgent()
        await safety_agent.initialize()
        
        print("✅ All agents initialized successfully")
    except Exception as e:
        print(f"❌ Failed to initialize agents: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Test each agent
    for agent_name, queries in TEST_QUERIES.items():
        print(f"\n{'#'*80}")
        print(f"Testing {agent_name.upper()} Agent")
        print(f"{'#'*80}")
        
        agent = {
            "operations": operations_agent,
            "equipment": equipment_agent,
            "safety": safety_agent,
        }[agent_name]
        
        query_class = {
            "operations": MCPOperationsQuery,
            "equipment": MCPEquipmentQuery,
            "safety": MCPSafetyQuery,
        }[agent_name]
        
        for query in queries:
            result = await test_agent_response(agent_name, query, agent, query_class, log_analyzer)
            results.append(result)
            
            # Small delay between queries
            await asyncio.sleep(1)
    
    # Generate comprehensive summary
    print(f"\n{'='*80}")
    print("COMPREHENSIVE TEST SUMMARY")
    print(f"{'='*80}")
    
    total_tests = len(results)
    successful_tests = len([r for r in results if "error" not in r])
    failed_tests = total_tests - successful_tests
    
    valid_responses = len([r for r in results if r.get("validation", {}).get("is_valid", False)])
    invalid_responses = successful_tests - valid_responses
    
    avg_score = sum(r.get("validation", {}).get("score", 0) for r in results if "error" not in r) / successful_tests if successful_tests > 0 else 0
    avg_confidence = sum(r.get("response", {}).get("confidence", 0) for r in results if "error" not in r) / successful_tests if successful_tests > 0 else 0
    avg_processing_time = sum(r.get("processing_time_seconds", 0) for r in results if "error" not in r) / successful_tests if successful_tests > 0 else 0
    
    # Aggregate log analysis
    all_log_patterns = defaultdict(int)
    all_insights = []
    all_recommendations = []
    
    for result in results:
        if "log_analysis" in result:
            log_analysis = result["log_analysis"]
            for pattern_name, pattern_data in log_analysis.get("patterns", {}).items():
                all_log_patterns[pattern_name] += pattern_data.get("count", 0)
            all_insights.extend(log_analysis.get("insights", []))
            all_recommendations.extend(log_analysis.get("recommendations", []))
    
    print(f"\n📊 Overall Statistics:")
    print(f"   Total Tests: {total_tests}")
    print(f"   Successful: {successful_tests} ({successful_tests/total_tests*100:.1f}%)")
    print(f"   Failed: {failed_tests} ({failed_tests/total_tests*100:.1f}%)")
    print(f"   Valid Responses: {valid_responses} ({valid_responses/successful_tests*100:.1f}%)")
    print(f"   Invalid Responses: {invalid_responses} ({invalid_responses/successful_tests*100:.1f}%)")
    print(f"   Average Validation Score: {avg_score:.2f}")
    print(f"   Average Confidence: {avg_confidence:.2f}")
    print(f"   Average Processing Time: {avg_processing_time:.2f}s")
    
    # Breakdown by agent
    print(f"\n📈 Breakdown by Agent:")
    for agent_name in ["operations", "equipment", "safety"]:
        agent_results = [r for r in results if r.get("agent") == agent_name]
        agent_successful = len([r for r in agent_results if "error" not in r])
        agent_valid = len([r for r in agent_results if r.get("validation", {}).get("is_valid", False)])
        agent_avg_score = sum(r.get("validation", {}).get("score", 0) for r in agent_results if "error" not in r) / agent_successful if agent_successful > 0 else 0
        agent_avg_time = sum(r.get("processing_time_seconds", 0) for r in agent_results if "error" not in r) / agent_successful if agent_successful > 0 else 0
        
        print(f"   {agent_name.capitalize()}:")
        print(f"      Tests: {len(agent_results)}")
        print(f"      Successful: {agent_successful}")
        print(f"      Valid: {agent_valid}")
        print(f"      Avg Score: {agent_avg_score:.2f}")
        print(f"      Avg Time: {agent_avg_time:.2f}s")
    
    # Log analysis summary
    print(f"\n📋 Aggregate Log Analysis:")
    for pattern_name, count in sorted(all_log_patterns.items(), key=lambda x: x[1], reverse=True):
        print(f"   {pattern_name}: {count}")
    
    # Save comprehensive results
    results_file = project_root / "tests" / "quality" / "quality_test_results_enhanced.json"
    results_file.parent.mkdir(parents=True, exist_ok=True)
    
    comprehensive_results = {
        "summary": {
            "total_tests": total_tests,
            "successful_tests": successful_tests,
            "failed_tests": failed_tests,
            "valid_responses": valid_responses,
            "invalid_responses": invalid_responses,
            "avg_validation_score": avg_score,
            "avg_confidence": avg_confidence,
            "avg_processing_time_seconds": avg_processing_time,
        },
        "log_analysis": {
            "aggregate_patterns": dict(all_log_patterns),
            "insights": list(set(all_insights)),  # Remove duplicates
            "recommendations": all_recommendations,
        },
        "results": results,
        "timestamp": datetime.now().isoformat(),
    }
    
    with open(results_file, "w") as f:
        json.dump(comprehensive_results, f, indent=2)
    
    print(f"\n💾 Results saved to: {results_file}")
    print(f"\n✅ Test suite completed at: {datetime.now().isoformat()}")
    
    return comprehensive_results


if __name__ == "__main__":
    asyncio.run(run_quality_tests())

