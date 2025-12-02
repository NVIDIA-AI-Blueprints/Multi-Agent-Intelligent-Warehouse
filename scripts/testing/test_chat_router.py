#!/usr/bin/env python3
"""
Test script for chat router and all agents.
Tests different scenarios and measures LLM API query latency.
"""

import asyncio
import time
import json
import requests
from typing import Dict, List, Tuple
from datetime import datetime

API_BASE = "http://localhost:8001/api/v1"
SESSION_ID = "test_session_" + datetime.now().strftime("%Y%m%d_%H%M%S")

# Test scenarios for each agent
TEST_SCENARIOS = {
    "equipment": [
        "Show me the status of forklift FL-01",
        "What equipment is available in Zone A?",
        "Get me the telemetry for forklift FL-02",
        "List all equipment in maintenance",
    ],
    "operations": [
        "Dispatch forklift FL-01 to Zone A for pick operations",
        "Create a new task for Zone B",
        "Show me the current tasks",
        "What's the status of task TASK-001?",
    ],
    "safety": [
        "Report a safety incident in Zone C",
        "What safety procedures are required for forklift operation?",
        "Show me recent safety incidents",
        "I need to perform lockout tagout for equipment FL-03",
    ],
    "forecasting": [
        "Show me reorder recommendations for high-priority items",
        "What's the demand forecast for SKU-12345?",
        "Show me the forecasting model performance",
        "Get me the forecast dashboard",
    ],
    "document": [
        "Process the invoice document I uploaded",
        "What documents are pending processing?",
        "Show me the results for document DOC-001",
    ],
    "general": [
        "Hello, how are you?",
        "What can you help me with?",
        "Tell me about the warehouse system",
    ],
}

def test_chat_endpoint(message: str, session_id: str = SESSION_ID) -> Tuple[Dict, float]:
    """Test the chat endpoint and measure latency."""
    url = f"{API_BASE}/chat"
    payload = {
        "message": message,
        "session_id": session_id,
        "enable_reasoning": False,
    }
    
    start_time = time.time()
    try:
        # Increased timeout to 180s to match backend timeout for complex operations queries
        response = requests.post(url, json=payload, timeout=180)
        latency = time.time() - start_time
        
        if response.status_code == 200:
            return response.json(), latency
        else:
            return {"error": f"HTTP {response.status_code}", "details": response.text}, latency
    except requests.exceptions.Timeout:
        latency = time.time() - start_time
        return {"error": "Request timeout", "latency": latency}, latency
    except Exception as e:
        latency = time.time() - start_time
        return {"error": str(e), "latency": latency}, latency

def analyze_response(response: Dict, expected_agent: str) -> Dict:
    """Analyze the response to determine routing and performance."""
    analysis = {
        "routed_to": response.get("route", "unknown"),
        "intent": response.get("intent", "unknown"),
        "confidence": response.get("confidence", 0.0),
        "has_reply": bool(response.get("reply")),
        "has_structured_data": bool(response.get("structured_data")),
        "has_recommendations": bool(response.get("recommendations")),
        "has_actions_taken": bool(response.get("actions_taken")),
        "correct_routing": response.get("route", "").lower() == expected_agent.lower(),
    }
    return analysis

def print_test_results(results: List[Dict]):
    """Print formatted test results."""
    print("\n" + "="*80)
    print("CHAT ROUTER & AGENT TEST RESULTS")
    print("="*80)
    
    # Overall statistics
    total_tests = len(results)
    successful_routes = sum(1 for r in results if r["analysis"]["correct_routing"])
    avg_latency = sum(r["latency"] for r in results) / total_tests if total_tests > 0 else 0
    max_latency = max((r["latency"] for r in results), default=0)
    min_latency = min((r["latency"] for r in results), default=0)
    
    print(f"\n📊 OVERALL STATISTICS:")
    print(f"   Total Tests: {total_tests}")
    print(f"   Successful Routes: {successful_routes}/{total_tests} ({successful_routes/total_tests*100:.1f}%)")
    print(f"   Average Latency: {avg_latency:.2f}s")
    print(f"   Min Latency: {min_latency:.2f}s")
    print(f"   Max Latency: {max_latency:.2f}s")
    
    # Group by agent
    print(f"\n📋 RESULTS BY AGENT:")
    agent_stats = {}
    for result in results:
        agent = result["expected_agent"]
        if agent not in agent_stats:
            agent_stats[agent] = {
                "count": 0,
                "correct": 0,
                "latencies": [],
                "avg_confidence": [],
            }
        agent_stats[agent]["count"] += 1
        if result["analysis"]["correct_routing"]:
            agent_stats[agent]["correct"] += 1
        agent_stats[agent]["latencies"].append(result["latency"])
        agent_stats[agent]["avg_confidence"].append(result["analysis"]["confidence"])
    
    for agent, stats in agent_stats.items():
        avg_lat = sum(stats["latencies"]) / len(stats["latencies"])
        avg_conf = sum(stats["avg_confidence"]) / len(stats["avg_confidence"])
        print(f"\n   {agent.upper()} Agent:")
        print(f"      Tests: {stats['count']}")
        print(f"      Correct Routing: {stats['correct']}/{stats['count']} ({stats['correct']/stats['count']*100:.1f}%)")
        print(f"      Avg Latency: {avg_lat:.2f}s")
        print(f"      Avg Confidence: {avg_conf:.2f}")
    
    # Detailed results
    print(f"\n📝 DETAILED TEST RESULTS:")
    for i, result in enumerate(results, 1):
        status = "✅" if result["analysis"]["correct_routing"] else "❌"
        print(f"\n   Test {i}: {status} {result['expected_agent'].upper()}")
        print(f"      Query: {result['message'][:60]}...")
        print(f"      Routed to: {result['analysis']['routed_to']}")
        print(f"      Intent: {result['analysis']['intent']}")
        print(f"      Confidence: {result['analysis']['confidence']:.2f}")
        print(f"      Latency: {result['latency']:.2f}s")
        if result.get("error"):
            print(f"      ⚠️  Error: {result['error']}")
    
    # LLM API Latency Analysis
    print(f"\n⚡ LLM API LATENCY ANALYSIS:")
    latencies = [r["latency"] for r in results]
    latencies_sorted = sorted(latencies)
    p50 = latencies_sorted[len(latencies_sorted)//2] if latencies_sorted else 0
    p95 = latencies_sorted[int(len(latencies_sorted)*0.95)] if latencies_sorted else 0
    p99 = latencies_sorted[int(len(latencies_sorted)*0.99)] if latencies_sorted else 0
    
    print(f"   P50 (Median): {p50:.2f}s")
    print(f"   P95: {p95:.2f}s")
    print(f"   P99: {p99:.2f}s")
    print(f"   Average: {avg_latency:.2f}s")
    
    # Performance assessment
    print(f"\n🎯 PERFORMANCE ASSESSMENT:")
    if avg_latency < 2.0:
        print("   ✅ Excellent: Average latency < 2s")
    elif avg_latency < 5.0:
        print("   🟡 Good: Average latency < 5s")
    elif avg_latency < 10.0:
        print("   🟠 Acceptable: Average latency < 10s")
    else:
        print("   🔴 Slow: Average latency >= 10s")
    
    if successful_routes / total_tests >= 0.9:
        print("   ✅ Excellent: Routing accuracy >= 90%")
    elif successful_routes / total_tests >= 0.7:
        print("   🟡 Good: Routing accuracy >= 70%")
    else:
        print("   🔴 Poor: Routing accuracy < 70%")
    
    print("\n" + "="*80)

def main():
    """Run all test scenarios."""
    print("🚀 Starting Chat Router & Agent Tests...")
    print(f"   Session ID: {SESSION_ID}")
    print(f"   API Base: {API_BASE}\n")
    
    results = []
    
    for agent_type, scenarios in TEST_SCENARIOS.items():
        print(f"Testing {agent_type.upper()} agent...")
        for scenario in scenarios:
            print(f"  → {scenario[:50]}...")
            response, latency = test_chat_endpoint(scenario)
            
            analysis = {}
            if "error" not in response:
                analysis = analyze_response(response, agent_type)
            else:
                analysis = {
                    "routed_to": "error",
                    "intent": "error",
                    "confidence": 0.0,
                    "correct_routing": False,
                }
            
            results.append({
                "expected_agent": agent_type,
                "message": scenario,
                "response": response,
                "latency": latency,
                "analysis": analysis,
                "error": response.get("error") if "error" in response else None,
            })
            
            # Small delay between requests
            time.sleep(0.5)
    
    print_test_results(results)
    
    # Save results to file in test_results directory
    import os
    test_results_dir = os.path.join(os.path.dirname(__file__), "..", "..", "test_results")
    os.makedirs(test_results_dir, exist_ok=True)
    output_file = os.path.join(test_results_dir, f"test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n💾 Results saved to: {output_file}")

if __name__ == "__main__":
    main()

