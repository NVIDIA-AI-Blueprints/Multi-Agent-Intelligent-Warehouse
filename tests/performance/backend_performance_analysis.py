"""
Comprehensive Backend Performance Analysis

Tests backend performance across multiple dimensions:
- Latency (P50, P95, P99)
- Throughput
- Error rates
- Cache performance
- Concurrent request handling
- Different query types and routes
"""

import asyncio
import aiohttp
import time
import statistics
from typing import List, Dict, Any, Tuple
from datetime import datetime
import json
from collections import defaultdict


BASE_URL = "http://localhost:8001/api/v1"
CHAT_ENDPOINT = f"{BASE_URL}/chat"
HEALTH_ENDPOINT = f"{BASE_URL}/health/simple"
PERFORMANCE_STATS_ENDPOINT = f"{BASE_URL}/chat/performance/stats"


class PerformanceTestResult:
    """Container for performance test results."""
    
    def __init__(self, name: str):
        self.name = name
        self.latencies: List[float] = []
        self.errors: List[Dict[str, Any]] = []
        self.success_count = 0
        self.total_count = 0
        self.start_time = None
        self.end_time = None
        self.cache_hits = 0
        self.cache_misses = 0
    
    def add_result(self, latency: float, success: bool, error: str = None, cache_hit: bool = False):
        """Add a test result."""
        self.latencies.append(latency)
        self.total_count += 1
        if success:
            self.success_count += 1
            if cache_hit:
                self.cache_hits += 1
            else:
                self.cache_misses += 1
        else:
            self.errors.append({
                "error": error,
                "latency": latency,
                "timestamp": datetime.now().isoformat()
            })
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics for this test."""
        if not self.latencies:
            return {
                "name": self.name,
                "total": self.total_count,
                "success": self.success_count,
                "error_rate": 1.0 if self.total_count > 0 else 0.0,
                "message": "No successful requests"
            }
        
        sorted_latencies = sorted(self.latencies)
        n = len(sorted_latencies)
        
        return {
            "name": self.name,
            "total": self.total_count,
            "success": self.success_count,
            "errors": len(self.errors),
            "error_rate": len(self.errors) / self.total_count if self.total_count > 0 else 0.0,
            "success_rate": self.success_count / self.total_count if self.total_count > 0 else 0.0,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "cache_hit_rate": self.cache_hits / (self.cache_hits + self.cache_misses) if (self.cache_hits + self.cache_misses) > 0 else 0.0,
            "latency": {
                "p50": sorted_latencies[int(n * 0.50)] if n > 0 else 0,
                "p95": sorted_latencies[int(n * 0.95)] if n > 0 else 0,
                "p99": sorted_latencies[int(n * 0.99)] if n > 0 else 0,
                "mean": statistics.mean(self.latencies) if self.latencies else 0,
                "median": statistics.median(self.latencies) if self.latencies else 0,
                "min": min(self.latencies) if self.latencies else 0,
                "max": max(self.latencies) if self.latencies else 0,
                "std_dev": statistics.stdev(self.latencies) if len(self.latencies) > 1 else 0,
            },
            "duration": (self.end_time - self.start_time).total_seconds() if self.start_time and self.end_time else 0,
            "throughput": self.success_count / (self.end_time - self.start_time).total_seconds() if self.start_time and self.end_time and (self.end_time - self.start_time).total_seconds() > 0 else 0,
        }


async def send_chat_request(
    session: aiohttp.ClientSession,
    message: str,
    session_id: str = "perf-test",
    enable_reasoning: bool = False,
    timeout: int = 120
) -> Tuple[float, bool, str, Dict[str, Any]]:
    """Send a chat request and return latency, success, error, and response."""
    payload = {
        "message": message,
        "session_id": session_id,
        "enable_reasoning": enable_reasoning
    }
    
    start_time = time.time()
    try:
        async with session.post(CHAT_ENDPOINT, json=payload, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
            latency = (time.time() - start_time) * 1000  # Convert to ms
            if response.status == 200:
                data = await response.json()
                cache_hit = data.get("route") == "cached" or "cache" in str(data).lower()
                return latency, True, None, data
            else:
                error_text = await response.text()
                return latency, False, f"HTTP {response.status}: {error_text}", {}
    except asyncio.TimeoutError:
        latency = (time.time() - start_time) * 1000
        return latency, False, "Timeout", {}
    except Exception as e:
        latency = (time.time() - start_time) * 1000
        return latency, False, str(e), {}


async def test_health_check(session: aiohttp.ClientSession) -> Dict[str, Any]:
    """Test backend health endpoint."""
    print("\n🔍 Testing Health Endpoint...")
    result = PerformanceTestResult("Health Check")
    result.start_time = datetime.now()
    
    for i in range(10):
        start = time.time()
        try:
            async with session.get(HEALTH_ENDPOINT, timeout=aiohttp.ClientTimeout(total=5)) as response:
                latency = (time.time() - start) * 1000
                success = response.status == 200
                result.add_result(latency, success, None if success else f"HTTP {response.status}")
        except Exception as e:
            latency = (time.time() - start) * 1000
            result.add_result(latency, False, str(e))
        await asyncio.sleep(0.1)
    
    result.end_time = datetime.now()
    return result.get_stats()


async def test_simple_queries(session: aiohttp.ClientSession) -> Dict[str, Any]:
    """Test simple queries."""
    print("\n📝 Testing Simple Queries...")
    result = PerformanceTestResult("Simple Queries")
    result.start_time = datetime.now()
    
    simple_queries = [
        "What equipment is available?",
        "Show me today's tasks",
        "Check safety incidents",
        "What's the status?",
        "Hello",
    ]
    
    for query in simple_queries:
        latency, success, error, response = await send_chat_request(session, query, timeout=60)
        cache_hit = "cache" in str(response).lower() if response else False
        result.add_result(latency, success, error, cache_hit)
        await asyncio.sleep(0.5)
    
    result.end_time = datetime.now()
    return result.get_stats()


async def test_complex_queries(session: aiohttp.ClientSession) -> Dict[str, Any]:
    """Test complex queries."""
    print("\n🧠 Testing Complex Queries...")
    result = PerformanceTestResult("Complex Queries")
    result.start_time = datetime.now()
    
    complex_queries = [
        "What factors should be considered when optimizing warehouse layout?",
        "Analyze the relationship between equipment utilization and productivity",
        "Recommend strategies for improving warehouse efficiency",
        "Compare different warehouse layout configurations",
        "What are the best practices for inventory management?",
    ]
    
    for query in complex_queries:
        latency, success, error, response = await send_chat_request(session, query, timeout=120)
        cache_hit = "cache" in str(response).lower() if response else False
        result.add_result(latency, success, error, cache_hit)
        await asyncio.sleep(1)
    
    result.end_time = datetime.now()
    return result.get_stats()


async def test_equipment_queries(session: aiohttp.ClientSession) -> Dict[str, Any]:
    """Test equipment-specific queries."""
    print("\n🔧 Testing Equipment Queries...")
    result = PerformanceTestResult("Equipment Queries")
    result.start_time = datetime.now()
    
    equipment_queries = [
        "What equipment is available?",
        "Show me forklift status",
        "Check equipment maintenance schedule",
        "What's the utilization of equipment?",
        "List all equipment assets",
    ]
    
    for query in equipment_queries:
        latency, success, error, response = await send_chat_request(session, query, timeout=60)
        cache_hit = "cache" in str(response).lower() if response else False
        result.add_result(latency, success, error, cache_hit)
        await asyncio.sleep(0.5)
    
    result.end_time = datetime.now()
    return result.get_stats()


async def test_operations_queries(session: aiohttp.ClientSession) -> Dict[str, Any]:
    """Test operations-specific queries."""
    print("\n⚙️  Testing Operations Queries...")
    result = PerformanceTestResult("Operations Queries")
    result.start_time = datetime.now()
    
    operations_queries = [
        "What tasks need to be done today?",
        "Show me today's job list",
        "What work assignments are pending?",
        "What operations are scheduled?",
        "List all tasks",
    ]
    
    for query in operations_queries:
        latency, success, error, response = await send_chat_request(session, query, timeout=60)
        cache_hit = "cache" in str(response).lower() if response else False
        result.add_result(latency, success, error, cache_hit)
        await asyncio.sleep(0.5)
    
    result.end_time = datetime.now()
    return result.get_stats()


async def test_safety_queries(session: aiohttp.ClientSession) -> Dict[str, Any]:
    """Test safety-specific queries."""
    print("\n🛡️  Testing Safety Queries...")
    result = PerformanceTestResult("Safety Queries")
    result.start_time = datetime.now()
    
    safety_queries = [
        "Report a safety incident",
        "Check safety compliance",
        "What safety incidents occurred?",
        "Show safety violations",
        "List safety procedures",
    ]
    
    for query in safety_queries:
        latency, success, error, response = await send_chat_request(session, query, timeout=60)
        cache_hit = "cache" in str(response).lower() if response else False
        result.add_result(latency, success, error, cache_hit)
        await asyncio.sleep(0.5)
    
    result.end_time = datetime.now()
    return result.get_stats()


async def test_concurrent_requests(session: aiohttp.ClientSession, num_concurrent: int = 5) -> Dict[str, Any]:
    """Test concurrent request handling."""
    print(f"\n🔄 Testing Concurrent Requests ({num_concurrent} concurrent)...")
    result = PerformanceTestResult(f"Concurrent Requests ({num_concurrent})")
    result.start_time = datetime.now()
    
    query = "What equipment is available?"
    
    async def send_request():
        latency, success, error, response = await send_chat_request(session, query, timeout=60)
        cache_hit = "cache" in str(response).lower() if response else False
        result.add_result(latency, success, error, cache_hit)
        return latency, success
    
    # Send concurrent requests
    tasks = [send_request() for _ in range(num_concurrent)]
    await asyncio.gather(*tasks)
    
    result.end_time = datetime.now()
    return result.get_stats()


async def test_cache_performance(session: aiohttp.ClientSession) -> Dict[str, Any]:
    """Test cache performance by sending the same query twice."""
    print("\n💾 Testing Cache Performance...")
    result = PerformanceTestResult("Cache Performance")
    result.start_time = datetime.now()
    
    query = "What equipment is available?"
    
    # First request (cache miss)
    latency1, success1, error1, response1 = await send_chat_request(session, query, timeout=60)
    cache_hit1 = "cache" in str(response1).lower() if response1 else False
    result.add_result(latency1, success1, error1, cache_hit1)
    
    await asyncio.sleep(1)
    
    # Second request (should be cache hit)
    latency2, success2, error2, response2 = await send_chat_request(session, query, timeout=60)
    cache_hit2 = "cache" in str(response2).lower() if response2 else False
    result.add_result(latency2, success2, error2, cache_hit2)
    
    result.end_time = datetime.now()
    return result.get_stats()


async def test_reasoning_queries(session: aiohttp.ClientSession) -> Dict[str, Any]:
    """Test reasoning-enabled queries."""
    print("\n🧮 Testing Reasoning Queries...")
    result = PerformanceTestResult("Reasoning Queries")
    result.start_time = datetime.now()
    
    reasoning_queries = [
        "Analyze the relationship between equipment utilization and productivity",
        "What factors affect warehouse efficiency?",
    ]
    
    for query in reasoning_queries:
        latency, success, error, response = await send_chat_request(
            session, query, enable_reasoning=True, timeout=240
        )
        cache_hit = "cache" in str(response).lower() if response else False
        result.add_result(latency, success, error, cache_hit)
        await asyncio.sleep(2)
    
    result.end_time = datetime.now()
    return result.get_stats()


async def get_backend_stats(session: aiohttp.ClientSession) -> Dict[str, Any]:
    """Get backend performance statistics."""
    try:
        async with session.get(PERFORMANCE_STATS_ENDPOINT, params={"time_window_minutes": 60}) as response:
            if response.status == 200:
                return await response.json()
    except Exception as e:
        print(f"⚠️  Failed to get backend stats: {e}")
    return {}


async def main():
    """Run comprehensive performance analysis."""
    print("="*80)
    print("BACKEND PERFORMANCE ANALYSIS")
    print("="*80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Base URL: {BASE_URL}")
    
    results = {}
    
    async with aiohttp.ClientSession() as session:
        # Test 1: Health Check
        results["health"] = await test_health_check(session)
        
        # Test 2: Simple Queries
        results["simple"] = await test_simple_queries(session)
        
        # Test 3: Complex Queries
        results["complex"] = await test_complex_queries(session)
        
        # Test 4: Equipment Queries
        results["equipment"] = await test_equipment_queries(session)
        
        # Test 5: Operations Queries
        results["operations"] = await test_operations_queries(session)
        
        # Test 6: Safety Queries
        results["safety"] = await test_safety_queries(session)
        
        # Test 7: Concurrent Requests
        results["concurrent_5"] = await test_concurrent_requests(session, num_concurrent=5)
        results["concurrent_10"] = await test_concurrent_requests(session, num_concurrent=10)
        
        # Test 8: Cache Performance
        results["cache"] = await test_cache_performance(session)
        
        # Test 9: Reasoning Queries (optional - takes longer)
        # results["reasoning"] = await test_reasoning_queries(session)
        
        # Get backend stats
        backend_stats = await get_backend_stats(session)
        results["backend_stats"] = backend_stats
    
    # Generate report
    print("\n" + "="*80)
    print("PERFORMANCE ANALYSIS REPORT")
    print("="*80)
    
    # Overall summary
    all_latencies = []
    total_requests = 0
    total_errors = 0
    
    for test_name, test_result in results.items():
        if test_name == "backend_stats":
            continue
        if isinstance(test_result, dict) and "latency" in test_result:
            latencies = test_result["latency"]
            if latencies.get("mean", 0) > 0:
                all_latencies.append(latencies["mean"])
            total_requests += test_result.get("total", 0)
            total_errors += test_result.get("errors", 0)
    
    print(f"\n📊 Overall Summary:")
    print(f"   Total Requests: {total_requests}")
    print(f"   Total Errors: {total_errors}")
    print(f"   Overall Error Rate: {(total_errors/total_requests*100):.2f}%" if total_requests > 0 else "N/A")
    if all_latencies:
        print(f"   Average Latency: {statistics.mean(all_latencies):.2f}ms")
        print(f"   Median Latency: {statistics.median(all_latencies):.2f}ms")
    
    # Detailed results by test
    print(f"\n📈 Detailed Results by Test:")
    for test_name, test_result in results.items():
        if test_name == "backend_stats":
            continue
        if isinstance(test_result, dict):
            print(f"\n   {test_result.get('name', test_name)}:")
            print(f"      Requests: {test_result.get('success', 0)}/{test_result.get('total', 0)} successful")
            print(f"      Error Rate: {test_result.get('error_rate', 0)*100:.2f}%")
            if "latency" in test_result:
                lat = test_result["latency"]
                print(f"      Latency - P50: {lat.get('p50', 0):.2f}ms, P95: {lat.get('p95', 0):.2f}ms, P99: {lat.get('p99', 0):.2f}ms")
                print(f"      Latency - Mean: {lat.get('mean', 0):.2f}ms, Median: {lat.get('median', 0):.2f}ms")
            if test_result.get("cache_hit_rate", 0) > 0:
                print(f"      Cache Hit Rate: {test_result.get('cache_hit_rate', 0)*100:.2f}%")
            if test_result.get("throughput", 0) > 0:
                print(f"      Throughput: {test_result.get('throughput', 0):.2f} req/s")
    
    # Backend stats
    if results.get("backend_stats") and results["backend_stats"].get("success"):
        print(f"\n📊 Backend Performance Stats (from /chat/performance/stats):")
        perf = results["backend_stats"].get("performance", {})
        if perf:
            print(f"   Total Requests: {perf.get('total_requests', 0)}")
            print(f"   Cache Hit Rate: {perf.get('cache_hit_rate', 0)*100:.2f}%")
            print(f"   Error Rate: {perf.get('error_rate', 0)*100:.2f}%")
            print(f"   Success Rate: {perf.get('success_rate', 0)*100:.2f}%")
            if "latency" in perf:
                lat = perf["latency"]
                print(f"   Latency - P50: {lat.get('p50', 0):.2f}ms, P95: {lat.get('p95', 0):.2f}ms, P99: {lat.get('p99', 0):.2f}ms")
            if "route_distribution" in perf:
                print(f"   Route Distribution: {perf.get('route_distribution', {})}")
        
        alerts = results["backend_stats"].get("alerts", [])
        if alerts:
            print(f"\n⚠️  Active Alerts:")
            for alert in alerts:
                print(f"   [{alert.get('severity', 'unknown').upper()}] {alert.get('alert_type', 'unknown')}: {alert.get('message', '')}")
    
    # Recommendations
    print(f"\n💡 Recommendations:")
    
    # Check for high latency
    high_latency_tests = []
    for test_name, test_result in results.items():
        if test_name == "backend_stats":
            continue
        if isinstance(test_result, dict) and "latency" in test_result:
            p95 = test_result["latency"].get("p95", 0)
            if p95 > 30000:  # 30 seconds
                high_latency_tests.append((test_result.get("name", test_name), p95))
    
    if high_latency_tests:
        print(f"   ⚠️  High Latency Detected:")
        for test_name, p95 in high_latency_tests:
            print(f"      - {test_name}: P95 latency is {p95:.2f}ms (above 30s threshold)")
        print(f"      → Consider optimizing query processing or increasing timeouts")
    
    # Check for high error rates
    high_error_tests = []
    for test_name, test_result in results.items():
        if test_name == "backend_stats":
            continue
        if isinstance(test_result, dict):
            error_rate = test_result.get("error_rate", 0)
            if error_rate > 0.1:  # 10%
                high_error_tests.append((test_result.get("name", test_name), error_rate))
    
    if high_error_tests:
        print(f"   ⚠️  High Error Rate Detected:")
        for test_name, error_rate in high_error_tests:
            print(f"      - {test_name}: {error_rate*100:.2f}% error rate")
        print(f"      → Investigate error causes and improve error handling")
    
    # Check cache performance
    cache_tests = [r for r in results.values() if isinstance(r, dict) and r.get("cache_hit_rate", 0) > 0]
    if cache_tests:
        avg_cache_hit_rate = statistics.mean([r.get("cache_hit_rate", 0) for r in cache_tests])
        if avg_cache_hit_rate < 0.1:  # Less than 10%
            print(f"   ⚠️  Low Cache Hit Rate: {avg_cache_hit_rate*100:.2f}%")
            print(f"      → Consider cache warming or increasing TTL")
    
    # Check concurrent performance
    if "concurrent_10" in results:
        concurrent_result = results["concurrent_10"]
        if concurrent_result.get("error_rate", 0) > 0.2:  # 20%
            print(f"   ⚠️  Poor Concurrent Request Handling:")
            print(f"      - Error rate: {concurrent_result.get('error_rate', 0)*100:.2f}%")
            print(f"      → Consider request queuing or rate limiting")
    
    print(f"\n✅ Analysis completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Save detailed results to file
    report_file = "tests/performance/BACKEND_PERFORMANCE_REPORT.json"
    with open(report_file, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n📄 Detailed results saved to: {report_file}")


if __name__ == "__main__":
    asyncio.run(main())

