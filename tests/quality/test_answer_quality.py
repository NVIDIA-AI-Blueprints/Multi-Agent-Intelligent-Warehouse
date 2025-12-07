"""
Test script for answer quality assessment.

Tests agent responses for natural language quality, completeness, and correctness.
"""

import asyncio
import sys
import os
from pathlib import Path
from typing import Dict, Any, List
import json
from datetime import datetime

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


async def test_agent_response(
    agent_name: str, query: str, agent, query_class
) -> Dict[str, Any]:
    """Test a single agent response."""
    print(f"\n{'='*80}")
    print(f"Testing {agent_name}: {query}")
    print(f"{'='*80}")
    
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
        
        # Prepare result
        result = {
            "agent": agent_name,
            "query": query,
            "response": {
                "natural_language": response.natural_language[:200] + "..." if len(response.natural_language) > 200 else response.natural_language,
                "confidence": response.confidence,
                "response_type": response.response_type,
                "recommendations_count": len(response.recommendations),
                "actions_taken_count": len(response.actions_taken or []),
                "tools_used": response.mcp_tools_used or [],
            },
            "validation": {
                "is_valid": validation_result.is_valid,
                "score": validation_result.score,
                "issues": validation_result.issues,
                "warnings": validation_result.warnings,
                "suggestions": validation_result.suggestions,
            },
            "timestamp": datetime.now().isoformat(),
        }
        
        # Print results
        print(f"\n✅ Response Generated")
        print(f"   Natural Language: {response.natural_language[:150]}...")
        print(f"   Confidence: {response.confidence:.2f}")
        print(f"   Tools Used: {len(response.mcp_tools_used or [])}")
        
        print(f"\n📊 Validation Results")
        print(f"   Valid: {'✅' if validation_result.is_valid else '❌'}")
        print(f"   Score: {validation_result.score:.2f}")
        
        if validation_result.issues:
            print(f"   Issues: {len(validation_result.issues)}")
            for issue in validation_result.issues:
                print(f"      - {issue}")
        
        if validation_result.warnings:
            print(f"   Warnings: {len(validation_result.warnings)}")
            for warning in validation_result.warnings:
                print(f"      - {warning}")
        
        if validation_result.suggestions:
            print(f"   Suggestions: {len(validation_result.suggestions)}")
            for suggestion in validation_result.suggestions:
                print(f"      - {suggestion}")
        
        return result
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return {
            "agent": agent_name,
            "query": query,
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }


async def run_quality_tests():
    """Run quality tests for all agents."""
    print("="*80)
    print("ANSWER QUALITY TEST SUITE")
    print("="*80)
    print(f"Started at: {datetime.now().isoformat()}")
    
    results = []
    
    # Initialize agents
    try:
        operations_agent = MCPOperationsCoordinationAgent()
        equipment_agent = MCPEquipmentAssetOperationsAgent()
        safety_agent = MCPSafetyComplianceAgent()
    except Exception as e:
        print(f"❌ Failed to initialize agents: {e}")
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
            result = await test_agent_response(agent_name, query, agent, query_class)
            results.append(result)
            
            # Small delay between queries
            await asyncio.sleep(1)
    
    # Generate summary
    print(f"\n{'='*80}")
    print("TEST SUMMARY")
    print(f"{'='*80}")
    
    total_tests = len(results)
    successful_tests = len([r for r in results if "error" not in r])
    failed_tests = total_tests - successful_tests
    
    valid_responses = len([r for r in results if r.get("validation", {}).get("is_valid", False)])
    invalid_responses = successful_tests - valid_responses
    
    avg_score = sum(r.get("validation", {}).get("score", 0) for r in results if "error" not in r) / successful_tests if successful_tests > 0 else 0
    avg_confidence = sum(r.get("response", {}).get("confidence", 0) for r in results if "error" not in r) / successful_tests if successful_tests > 0 else 0
    
    print(f"\n📊 Overall Statistics:")
    print(f"   Total Tests: {total_tests}")
    print(f"   Successful: {successful_tests} ({successful_tests/total_tests*100:.1f}%)")
    print(f"   Failed: {failed_tests} ({failed_tests/total_tests*100:.1f}%)")
    print(f"   Valid Responses: {valid_responses} ({valid_responses/successful_tests*100:.1f}%)")
    print(f"   Invalid Responses: {invalid_responses} ({invalid_responses/successful_tests*100:.1f}%)")
    print(f"   Average Validation Score: {avg_score:.2f}")
    print(f"   Average Confidence: {avg_confidence:.2f}")
    
    # Breakdown by agent
    print(f"\n📈 Breakdown by Agent:")
    for agent_name in ["operations", "equipment", "safety"]:
        agent_results = [r for r in results if r.get("agent") == agent_name]
        agent_successful = len([r for r in agent_results if "error" not in r])
        agent_valid = len([r for r in agent_results if r.get("validation", {}).get("is_valid", False)])
        agent_avg_score = sum(r.get("validation", {}).get("score", 0) for r in agent_results if "error" not in r) / agent_successful if agent_successful > 0 else 0
        
        print(f"   {agent_name.capitalize()}:")
        print(f"      Tests: {len(agent_results)}")
        print(f"      Successful: {agent_successful}")
        print(f"      Valid: {agent_valid}")
        print(f"      Avg Score: {agent_avg_score:.2f}")
    
    # Save results
    results_file = project_root / "tests" / "quality" / "quality_test_results.json"
    results_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(results_file, "w") as f:
        json.dump({
            "summary": {
                "total_tests": total_tests,
                "successful_tests": successful_tests,
                "failed_tests": failed_tests,
                "valid_responses": valid_responses,
                "invalid_responses": invalid_responses,
                "avg_validation_score": avg_score,
                "avg_confidence": avg_confidence,
            },
            "results": results,
            "timestamp": datetime.now().isoformat(),
        }, f, indent=2)
    
    print(f"\n💾 Results saved to: {results_file}")
    print(f"\n✅ Test suite completed at: {datetime.now().isoformat()}")


if __name__ == "__main__":
    asyncio.run(run_quality_tests())

