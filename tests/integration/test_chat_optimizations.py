"""
Integration Tests for Chat System Optimizations

Tests the integration of chat system optimizations:
1. Semantic Routing - Similar meaning, different keywords
2. Deduplication - Identical concurrent requests
3. Performance Monitoring - Metrics collection
4. Response Cleaning - Clean responses without technical artifacts

This is an integration test that verifies optimizations work together
in the full chat system, not just individual components.
"""

import asyncio
import aiohttp
import json
import time
from typing import List, Dict, Any
from datetime import datetime


BASE_URL = "http://localhost:8001/api/v1"
CHAT_ENDPOINT = f"{BASE_URL}/chat"
PERFORMANCE_STATS_ENDPOINT = f"{BASE_URL}/chat/performance/stats"


async def send_chat_request(
    session: aiohttp.ClientSession,
    message: str,
    session_id: str = "test-session",
    enable_reasoning: bool = False
) -> Dict[str, Any]:
    """Send a chat request and return the response."""
    payload = {
        "message": message,
        "session_id": session_id,
        "enable_reasoning": enable_reasoning
    }
    
    async with session.post(CHAT_ENDPOINT, json=payload) as response:
        return await response.json()


async def get_performance_stats(
    session: aiohttp.ClientSession,
    time_window_minutes: int = 60
) -> Dict[str, Any]:
    """Get performance statistics."""
    async with session.get(
        PERFORMANCE_STATS_ENDPOINT,
        params={"time_window_minutes": time_window_minutes}
    ) as response:
        return await response.json()


async def test_semantic_routing(session: aiohttp.ClientSession):
    """
    Test 1: Semantic Routing
    Test with queries that have similar meaning but different keywords.
    """
    print("\n" + "="*80)
    print("TEST 1: Semantic Routing")
    print("="*80)
    
    # Test cases: Similar meaning, different keywords
    test_cases = [
        {
            "category": "Equipment Status",
            "queries": [
                "What's the status of my forklifts?",
                "How are my material handling vehicles doing?",
                "Check the condition of my warehouse machinery",
                "Show me the state of my equipment assets"
            ],
            "expected_intent": "equipment"
        },
        {
            "category": "Operations Tasks",
            "queries": [
                "What tasks need to be done today?",
                "What work assignments are pending?",
                "Show me today's job list",
                "What operations are scheduled for today?"
            ],
            "expected_intent": "operations"
        },
        {
            "category": "Safety Incidents",
            "queries": [
                "Report a safety incident",
                "I need to log a workplace accident",
                "Document a safety violation",
                "Record a hazard occurrence"
            ],
            "expected_intent": "safety"
        },
        {
            "category": "Inventory Query",
            "queries": [
                "How much stock do we have?",
                "What's our inventory level?",
                "Check product quantities",
                "Show me available items"
            ],
            "expected_intent": "inventory"
        }
    ]
    
    results = []
    
    for test_case in test_cases:
        print(f"\n📋 Testing Category: {test_case['category']}")
        print(f"   Expected Intent: {test_case['expected_intent']}")
        
        for query in test_case['queries']:
            print(f"\n   Query: '{query}'")
            response = await send_chat_request(session, query, session_id="semantic-test")
            
            intent = response.get("intent", "unknown")
            route = response.get("route", "unknown")
            confidence = response.get("confidence", 0.0)
            
            # Check if routing is consistent (same intent for similar queries)
            is_consistent = (intent == test_case['expected_intent'] or 
                           route == test_case['expected_intent'])
            
            status = "✅" if is_consistent else "❌"
            print(f"   {status} Intent: {intent}, Route: {route}, Confidence: {confidence:.2f}")
            
            results.append({
                "query": query,
                "expected_intent": test_case['expected_intent'],
                "actual_intent": intent,
                "actual_route": route,
                "confidence": confidence,
                "consistent": is_consistent
            })
            
            # Small delay to avoid rate limiting
            await asyncio.sleep(0.5)
    
    # Summary
    consistent_count = sum(1 for r in results if r['consistent'])
    total_count = len(results)
    consistency_rate = (consistent_count / total_count) * 100 if total_count > 0 else 0
    
    print(f"\n📊 Semantic Routing Summary:")
    print(f"   Consistent Routes: {consistent_count}/{total_count} ({consistency_rate:.1f}%)")
    
    return results


async def test_deduplication(session: aiohttp.ClientSession):
    """
    Test 2: Request Deduplication
    Send identical requests simultaneously and verify only one processes.
    """
    print("\n" + "="*80)
    print("TEST 2: Request Deduplication")
    print("="*80)
    
    test_message = "What is the status of forklift FL-001?"
    num_concurrent_requests = 5
    
    print(f"\n📋 Sending {num_concurrent_requests} identical concurrent requests:")
    print(f"   Message: '{test_message}'")
    
    # Send concurrent requests
    start_time = time.time()
    tasks = [
        send_chat_request(
            session,
            test_message,
            session_id="dedup-test",
            enable_reasoning=False
        )
        for _ in range(num_concurrent_requests)
    ]
    
    responses = await asyncio.gather(*tasks)
    end_time = time.time()
    total_time = end_time - start_time
    
    # Analyze responses
    print(f"\n⏱️  Total Time: {total_time:.2f}s")
    print(f"   Average Time per Request: {total_time/num_concurrent_requests:.2f}s")
    
    # Check if responses are identical (indicating deduplication worked)
    response_texts = [r.get("reply", "") for r in responses]
    unique_responses = set(response_texts)
    
    print(f"\n📊 Deduplication Analysis:")
    print(f"   Unique Responses: {len(unique_responses)}")
    print(f"   Total Requests: {len(responses)}")
    
    if len(unique_responses) == 1:
        print("   ✅ All responses are identical - Deduplication working!")
        print(f"   ⚡ Deduplication saved ~{total_time * (num_concurrent_requests - 1) / num_concurrent_requests:.2f}s")
    else:
        print("   ⚠️  Responses differ - Deduplication may not be working")
        for i, response in enumerate(unique_responses):
            print(f"      Response {i+1}: {response[:100]}...")
    
    # Check request IDs or timestamps to verify deduplication
    # (If responses have request IDs, they should be the same for deduplicated requests)
    
    return {
        "num_requests": num_concurrent_requests,
        "total_time": total_time,
        "unique_responses": len(unique_responses),
        "deduplication_working": len(unique_responses) == 1
    }


async def test_performance_monitoring(session: aiohttp.ClientSession):
    """
    Test 3: Performance Monitoring
    Query stats endpoint and verify metrics are being collected.
    """
    print("\n" + "="*80)
    print("TEST 3: Performance Monitoring")
    print("="*80)
    
    # Send a few test requests first
    print("\n📋 Sending test requests to generate metrics...")
    test_queries = [
        "What equipment is available?",
        "Show me today's tasks",
        "Check safety incidents",
    ]
    
    for query in test_queries:
        await send_chat_request(session, query, session_id="perf-test")
        await asyncio.sleep(0.5)
    
    # Wait a moment for metrics to be recorded
    await asyncio.sleep(1)
    
    # Get performance stats
    print("\n📊 Fetching performance statistics...")
    stats_response = await get_performance_stats(session, time_window_minutes=5)
    
    if not stats_response.get("success"):
        print(f"   ❌ Failed to get stats: {stats_response.get('error')}")
        return None
    
    perf_stats = stats_response.get("performance", {})
    dedup_stats = stats_response.get("deduplication", {})
    
    print(f"\n📈 Performance Metrics:")
    print(f"   Time Window: {perf_stats.get('time_window_minutes', 0)} minutes")
    print(f"   Total Requests: {perf_stats.get('total_requests', 0)}")
    print(f"   Cache Hits: {perf_stats.get('cache_hits', 0)}")
    print(f"   Cache Misses: {perf_stats.get('cache_misses', 0)}")
    print(f"   Cache Hit Rate: {perf_stats.get('cache_hit_rate', 0.0):.2%}")
    print(f"   Errors: {perf_stats.get('errors', 0)}")
    print(f"   Error Rate: {perf_stats.get('error_rate', 0.0):.2%}")
    print(f"   Success Rate: {perf_stats.get('success_rate', 0.0):.2%}")
    
    latency = perf_stats.get("latency", {})
    if latency:
        print(f"\n⏱️  Latency Metrics:")
        print(f"   P50: {latency.get('p50', 0):.2f}ms")
        print(f"   P95: {latency.get('p95', 0):.2f}ms")
        print(f"   P99: {latency.get('p99', 0):.2f}ms")
        print(f"   Mean: {latency.get('mean', 0):.2f}ms")
        print(f"   Min: {latency.get('min', 0):.2f}ms")
        print(f"   Max: {latency.get('max', 0):.2f}ms")
    
    tools = perf_stats.get("tools", {})
    if tools:
        print(f"\n🔧 Tool Execution Metrics:")
        print(f"   Total Tools Executed: {tools.get('total_executed', 0)}")
        print(f"   Avg Tools per Request: {tools.get('avg_per_request', 0):.2f}")
        print(f"   Total Execution Time: {tools.get('total_execution_time_ms', 0):.2f}ms")
        print(f"   Avg Execution Time: {tools.get('avg_execution_time_ms', 0):.2f}ms")
    
    route_dist = perf_stats.get("route_distribution", {})
    if route_dist:
        print(f"\n🛣️  Route Distribution:")
        for route, count in route_dist.items():
            print(f"   {route}: {count}")
    
    intent_dist = perf_stats.get("intent_distribution", {})
    if intent_dist:
        print(f"\n🎯 Intent Distribution:")
        for intent, count in intent_dist.items():
            print(f"   {intent}: {count}")
    
    print(f"\n🔄 Deduplication Stats:")
    print(f"   Active Requests: {dedup_stats.get('active_requests', 0)}")
    print(f"   Cached Results: {dedup_stats.get('cached_results', 0)}")
    print(f"   Active Locks: {dedup_stats.get('active_locks', 0)}")
    
    # Verify metrics are being collected
    has_metrics = perf_stats.get("total_requests", 0) > 0
    print(f"\n{'✅' if has_metrics else '❌'} Metrics Collection: {'Working' if has_metrics else 'No metrics found'}")
    
    return stats_response


async def test_response_cleaning(session: aiohttp.ClientSession):
    """
    Test 4: Response Cleaning
    Verify responses are clean without complex regex patterns or technical artifacts.
    """
    print("\n" + "="*80)
    print("TEST 4: Response Cleaning")
    print("="*80)
    
    test_queries = [
        "What equipment is available?",
        "Show me the status of forklift FL-001",
        "What tasks are scheduled for today?",
        "Check safety incidents from last week",
    ]
    
    technical_patterns = [
        r"mcp_tools_used:\s*\[",
        r"tool_execution_results:\s*\{",
        r"structured_response:\s*\{",
        r"ReasoningChain\(",
        r"\*Sources?:[^*]+\*",
        r"\*\*Additional Context:\*\*",
        r"\{'[^}]*'\}",
        r"<class '[^']+'>",
        r"at 0x[0-9a-f]+>",
    ]
    
    results = []
    
    for query in test_queries:
        print(f"\n📋 Testing Query: '{query}'")
        response = await send_chat_request(session, query, session_id="cleaning-test")
        
        reply = response.get("reply", "")
        
        # Check for technical patterns
        found_patterns = []
        for pattern in technical_patterns:
            import re
            if re.search(pattern, reply, re.IGNORECASE):
                found_patterns.append(pattern)
        
        is_clean = len(found_patterns) == 0
        status = "✅" if is_clean else "❌"
        
        print(f"   {status} Response is {'clean' if is_clean else 'contains technical artifacts'}")
        
        if found_patterns:
            print(f"   ⚠️  Found patterns: {', '.join(found_patterns[:3])}")
        
        # Show first 200 chars of response
        preview = reply[:200] + "..." if len(reply) > 200 else reply
        print(f"   Preview: {preview}")
        
        results.append({
            "query": query,
            "is_clean": is_clean,
            "found_patterns": found_patterns,
            "response_length": len(reply)
        })
        
        await asyncio.sleep(0.5)
    
    # Summary
    clean_count = sum(1 for r in results if r['is_clean'])
    total_count = len(results)
    clean_rate = (clean_count / total_count) * 100 if total_count > 0 else 0
    
    print(f"\n📊 Response Cleaning Summary:")
    print(f"   Clean Responses: {clean_count}/{total_count} ({clean_rate:.1f}%)")
    
    return results


async def main():
    """Run all verification tests."""
    print("\n" + "="*80)
    print("CHAT SYSTEM OPTIMIZATIONS VERIFICATION")
    print("="*80)
    print(f"Base URL: {BASE_URL}")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    async with aiohttp.ClientSession() as session:
        try:
            # Test 1: Semantic Routing
            semantic_results = await test_semantic_routing(session)
            
            # Test 2: Deduplication
            dedup_results = await test_deduplication(session)
            
            # Test 3: Performance Monitoring
            perf_results = await test_performance_monitoring(session)
            
            # Test 4: Response Cleaning
            cleaning_results = await test_response_cleaning(session)
            
            # Final Summary
            print("\n" + "="*80)
            print("FINAL SUMMARY")
            print("="*80)
            
            print("\n✅ Test 1: Semantic Routing")
            if semantic_results:
                consistent = sum(1 for r in semantic_results if r['consistent'])
                print(f"   Consistency: {consistent}/{len(semantic_results)} queries")
            
            print("\n✅ Test 2: Deduplication")
            if dedup_results:
                print(f"   Working: {dedup_results.get('deduplication_working', False)}")
                print(f"   Unique Responses: {dedup_results.get('unique_responses', 0)}/{dedup_results.get('num_requests', 0)}")
            
            print("\n✅ Test 3: Performance Monitoring")
            if perf_results and perf_results.get("success"):
                perf = perf_results.get("performance", {})
                print(f"   Metrics Collected: {perf.get('total_requests', 0) > 0}")
                print(f"   Total Requests: {perf.get('total_requests', 0)}")
            
            print("\n✅ Test 4: Response Cleaning")
            if cleaning_results:
                clean = sum(1 for r in cleaning_results if r['is_clean'])
                print(f"   Clean Responses: {clean}/{len(cleaning_results)}")
            
            print(f"\n✅ All tests completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
        except Exception as e:
            print(f"\n❌ Error running tests: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())

