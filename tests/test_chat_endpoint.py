#!/usr/bin/env python3
"""
Test script for chat endpoint assessment.
Tests the /api/v1/chat endpoint and router behavior.
"""

import requests
import json
import time
from typing import Dict, Any, Optional

# Configuration
BACKEND_URL = "http://localhost:8001"
FRONTEND_URL = "http://localhost:3001"
CHAT_ENDPOINT = f"{BACKEND_URL}/api/v1/chat"
HEALTH_ENDPOINT = f"{BACKEND_URL}/api/v1/health"

# Test cases
TEST_CASES = [
    {
        "name": "Simple greeting",
        "message": "Hello",
        "session_id": "test_session_1",
        "expected_route": ["general", "greeting"],
    },
    {
        "name": "Equipment status query",
        "message": "Show me the status of all forklifts",
        "session_id": "test_session_2",
        "expected_route": ["equipment", "inventory"],
    },
    {
        "name": "Operations query",
        "message": "Create a wave for orders 1001-1010 in Zone A",
        "session_id": "test_session_3",
        "expected_route": ["operations"],
    },
    {
        "name": "Safety query",
        "message": "What are the safety procedures for forklift operations?",
        "session_id": "test_session_4",
        "expected_route": ["safety"],
    },
    {
        "name": "Empty message",
        "message": "",
        "session_id": "test_session_5",
        "should_fail": True,
    },
    {
        "name": "Very long message",
        "message": "A" * 10000,
        "session_id": "test_session_6",
        "should_fail": False,  # Should handle gracefully
    },
]


def test_health_endpoint() -> bool:
    """Test if backend is accessible."""
    try:
        response = requests.get(HEALTH_ENDPOINT, timeout=5)
        if response.status_code == 200:
            print("✅ Backend health check passed")
            return True
        else:
            print(f"❌ Backend health check failed: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Backend not accessible: {e}")
        return False


def test_chat_endpoint(
    message: str, session_id: str, context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Test the chat endpoint with a message."""
    payload = {
        "message": message,
        "session_id": session_id,
    }
    if context:
        payload["context"] = context

    try:
        start_time = time.time()
        response = requests.post(
            CHAT_ENDPOINT,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=60,  # 60 second timeout
        )
        elapsed_time = time.time() - start_time

        result = {
            "status_code": response.status_code,
            "response_time": elapsed_time,
            "success": response.status_code == 200,
        }

        if response.status_code == 200:
            try:
                data = response.json()
                result["data"] = data
                result["has_reply"] = "reply" in data
                result["route"] = data.get("route", "unknown")
                result["intent"] = data.get("intent", "unknown")
                result["confidence"] = data.get("confidence", 0.0)
            except json.JSONDecodeError:
                result["error"] = "Invalid JSON response"
                result["raw_response"] = response.text[:500]
        else:
            result["error"] = response.text[:500]

        return result
    except requests.exceptions.Timeout:
        return {
            "status_code": 0,
            "success": False,
            "error": "Request timed out after 60 seconds",
            "response_time": 60.0,
        }
    except requests.exceptions.RequestException as e:
        return {
            "status_code": 0,
            "success": False,
            "error": str(e),
            "response_time": 0.0,
        }


def test_frontend_routing() -> bool:
    """Test if frontend chat page is accessible."""
    try:
        response = requests.get(f"{FRONTEND_URL}/chat", timeout=5, allow_redirects=True)
        if response.status_code == 200:
            # Check if it's the React app (should contain React/HTML)
            if "react" in response.text.lower() or "<!DOCTYPE html>" in response.text:
                print("✅ Frontend chat page accessible")
                return True
        print(f"❌ Frontend chat page returned: {response.status_code}")
        return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Frontend not accessible: {e}")
        return False


def test_proxy_configuration() -> bool:
    """Test if proxy forwards requests correctly."""
    try:
        # Test through frontend proxy
        response = requests.post(
            f"{FRONTEND_URL}/api/v1/health",
            timeout=5,
        )
        if response.status_code == 200:
            print("✅ Proxy configuration working (health check through proxy)")
            return True
        else:
            print(f"⚠️  Proxy returned: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Proxy test failed: {e}")
        return False


def run_assessment():
    """Run comprehensive assessment of chat endpoint."""
    print("=" * 80)
    print("CHAT ENDPOINT ASSESSMENT")
    print("=" * 80)
    print()

    # Test 1: Backend health
    print("1. Testing Backend Health...")
    backend_healthy = test_health_endpoint()
    print()

    if not backend_healthy:
        print("❌ Backend is not accessible. Cannot continue with chat tests.")
        return

    # Test 2: Frontend routing
    print("2. Testing Frontend Routing...")
    frontend_accessible = test_frontend_routing()
    print()

    # Test 3: Proxy configuration
    print("3. Testing Proxy Configuration...")
    proxy_working = test_proxy_configuration()
    print()

    # Test 4: Chat endpoint tests
    print("4. Testing Chat Endpoint...")
    print("-" * 80)
    results = []
    for i, test_case in enumerate(TEST_CASES, 1):
        print(f"\nTest {i}: {test_case['name']}")
        print(f"  Message: {test_case['message'][:50]}...")
        
        result = test_chat_endpoint(
            test_case["message"],
            test_case["session_id"],
            context={"warehouse": "WH-01", "role": "manager", "environment": "Dev"},
        )
        
        results.append({
            "test_case": test_case,
            "result": result,
        })
        
        if result["success"]:
            print(f"  ✅ Status: {result['status_code']}")
            print(f"  ⏱️  Response time: {result['response_time']:.2f}s")
            print(f"  📍 Route: {result.get('route', 'N/A')}")
            print(f"  🎯 Intent: {result.get('intent', 'N/A')}")
            print(f"  📊 Confidence: {result.get('confidence', 0.0):.2f}")
            
            # Check if route matches expected
            if "expected_route" in test_case:
                expected = test_case["expected_route"]
                actual = result.get("route", "")
                if actual in expected:
                    print(f"  ✅ Route matches expected: {expected}")
                else:
                    print(f"  ⚠️  Route mismatch. Expected one of {expected}, got {actual}")
        else:
            print(f"  ❌ Failed: {result.get('error', 'Unknown error')}")
            if test_case.get("should_fail", False):
                print(f"  ✅ Expected failure (test case marked as should_fail)")
            else:
                print(f"  ⚠️  Unexpected failure")
        
        # Small delay between tests
        time.sleep(0.5)
    
    print()
    print("=" * 80)
    print("ASSESSMENT SUMMARY")
    print("=" * 80)
    print()
    
    # Summary statistics
    total_tests = len(results)
    successful_tests = sum(1 for r in results if r["result"]["success"])
    failed_tests = total_tests - successful_tests
    
    print(f"Total Tests: {total_tests}")
    print(f"✅ Successful: {successful_tests}")
    print(f"❌ Failed: {failed_tests}")
    print()
    
    # Response time statistics
    response_times = [r["result"]["response_time"] for r in results if r["result"]["success"]]
    if response_times:
        avg_time = sum(response_times) / len(response_times)
        max_time = max(response_times)
        min_time = min(response_times)
        print(f"Response Time Statistics:")
        print(f"  Average: {avg_time:.2f}s")
        print(f"  Min: {min_time:.2f}s")
        print(f"  Max: {max_time:.2f}s")
        print()
    
    # Route distribution
    routes = {}
    for r in results:
        if r["result"]["success"]:
            route = r["result"].get("route", "unknown")
            routes[route] = routes.get(route, 0) + 1
    
    if routes:
        print("Route Distribution:")
        for route, count in sorted(routes.items(), key=lambda x: x[1], reverse=True):
            print(f"  {route}: {count}")
        print()
    
    # Issues and recommendations
    print("ISSUES & RECOMMENDATIONS:")
    print("-" * 80)
    
    issues = []
    recommendations = []
    
    # Check for timeout issues
    timeout_tests = [r for r in results if r["result"].get("error") == "Request timed out after 60 seconds"]
    if timeout_tests:
        issues.append(f"{len(timeout_tests)} test(s) timed out")
        recommendations.append("Consider optimizing query processing or increasing timeout for complex queries")
    
    # Check for slow responses
    slow_tests = [r for r in results if r["result"].get("response_time", 0) > 10]
    if slow_tests:
        issues.append(f"{len(slow_tests)} test(s) took longer than 10 seconds")
        recommendations.append("Investigate performance bottlenecks in MCP planner or enhancement services")
    
    # Check for route mismatches
    route_mismatches = []
    for r in results:
        if r["result"]["success"] and "expected_route" in r["test_case"]:
            expected = r["test_case"]["expected_route"]
            actual = r["result"].get("route", "")
            if actual not in expected:
                route_mismatches.append(f"{r['test_case']['name']}: expected {expected}, got {actual}")
    
    if route_mismatches:
        issues.append(f"{len(route_mismatches)} route mismatch(es)")
        recommendations.append("Review intent classification logic in MCP planner")
    
    if not backend_healthy:
        issues.append("Backend health check failed")
        recommendations.append("Ensure backend is running on port 8001")
    
    if not frontend_accessible:
        issues.append("Frontend not accessible")
        recommendations.append("Ensure frontend is running on port 3001")
    
    if not proxy_working:
        issues.append("Proxy configuration may have issues")
        recommendations.append("Check setupProxy.js configuration and backend connectivity")
    
    if issues:
        for issue in issues:
            print(f"  ⚠️  {issue}")
    else:
        print("  ✅ No major issues detected")
    
    print()
    if recommendations:
        print("Recommendations:")
        for rec in recommendations:
            print(f"  • {rec}")
    else:
        print("  ✅ No recommendations at this time")
    
    print()
    print("=" * 80)


if __name__ == "__main__":
    run_assessment()

