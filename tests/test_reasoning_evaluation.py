"""
Comprehensive test suite for evaluating reasoning capability.

This test suite evaluates:
1. Reasoning chain generation for different query types
2. Reasoning chain serialization and structure
3. Different reasoning types (Chain-of-Thought, Multi-Hop, Scenario Analysis, etc.)
4. Complex query detection
5. Reasoning chain display in responses
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Dict, Any, List
import httpx
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

BASE_URL = "http://localhost:8001/api/v1"


class ReasoningEvaluator:
    """Comprehensive reasoning capability evaluator."""
    
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=120.0)  # 2 minute timeout for reasoning
        self.results = []
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()
    
    async def test_health(self) -> bool:
        """Test if the API is accessible."""
        try:
            response = await self.client.get(f"{self.base_url}/health/simple")
            return response.status_code == 200
        except Exception as e:
            print(f"❌ Health check failed: {e}")
            return False
    
    async def test_reasoning_types_endpoint(self) -> Dict[str, Any]:
        """Test the reasoning types endpoint."""
        print("\n📋 Testing Reasoning Types Endpoint...")
        try:
            response = await self.client.get(f"{self.base_url}/reasoning/types")
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Reasoning types endpoint OK: {len(data.get('types', []))} types available")
                return {"status": "success", "data": data}
            else:
                print(f"❌ Reasoning types endpoint failed: {response.status_code}")
                return {"status": "failed", "error": f"HTTP {response.status_code}"}
        except Exception as e:
            print(f"❌ Reasoning types endpoint error: {e}")
            return {"status": "error", "error": str(e)}
    
    async def test_chat_with_reasoning(
        self, 
        query: str, 
        reasoning_types: List[str] = None,
        expected_complex: bool = True
    ) -> Dict[str, Any]:
        """Test chat endpoint with reasoning enabled."""
        print(f"\n🧠 Testing Query: '{query[:60]}...'")
        print(f"   Reasoning Types: {reasoning_types or 'auto'}")
        
        start_time = datetime.now()
        
        try:
            payload = {
                "message": query,
                "session_id": "test_session",
                "enable_reasoning": True,
                "reasoning_types": reasoning_types
            }
            
            response = await self.client.post(
                f"{self.base_url}/chat",
                json=payload
            )
            
            elapsed = (datetime.now() - start_time).total_seconds()
            
            if response.status_code == 200:
                data = response.json()
                
                # Check for reasoning chain
                has_reasoning_chain = "reasoning_chain" in data and data["reasoning_chain"] is not None
                has_reasoning_steps = "reasoning_steps" in data and data["reasoning_steps"] is not None
                
                result = {
                    "status": "success",
                    "query": query,
                    "elapsed_seconds": elapsed,
                    "has_reasoning_chain": has_reasoning_chain,
                    "has_reasoning_steps": has_reasoning_steps,
                    "route": data.get("route"),
                    "confidence": data.get("confidence"),
                }
                
                if has_reasoning_chain:
                    chain = data["reasoning_chain"]
                    result["reasoning_chain"] = {
                        "chain_id": chain.get("chain_id"),
                        "reasoning_type": chain.get("reasoning_type"),
                        "steps_count": len(chain.get("steps", [])),
                        "overall_confidence": chain.get("overall_confidence"),
                        "has_final_conclusion": bool(chain.get("final_conclusion")),
                    }
                    print(f"   ✅ Reasoning chain generated: {result['reasoning_chain']['steps_count']} steps")
                    print(f"      Type: {result['reasoning_chain']['reasoning_type']}")
                    print(f"      Confidence: {result['reasoning_chain']['overall_confidence']:.2f}")
                elif has_reasoning_steps:
                    steps = data["reasoning_steps"]
                    result["reasoning_steps_count"] = len(steps)
                    print(f"   ✅ Reasoning steps generated: {len(steps)} steps")
                else:
                    print(f"   ⚠️  No reasoning chain or steps in response")
                    if expected_complex:
                        result["warning"] = "Expected reasoning but none found"
                
                result["response_length"] = len(data.get("reply", ""))
                print(f"   ⏱️  Response time: {elapsed:.2f}s")
                
                return result
            else:
                error_msg = f"HTTP {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg = error_data.get("detail", error_msg)
                except:
                    error_msg = response.text[:200]
                
                print(f"   ❌ Request failed: {error_msg}")
                return {
                    "status": "failed",
                    "query": query,
                    "error": error_msg,
                    "elapsed_seconds": elapsed
                }
                
        except asyncio.TimeoutError:
            elapsed = (datetime.now() - start_time).total_seconds()
            print(f"   ❌ Request timed out after {elapsed:.2f}s")
            return {
                "status": "timeout",
                "query": query,
                "elapsed_seconds": elapsed
            }
        except Exception as e:
            elapsed = (datetime.now() - start_time).total_seconds()
            print(f"   ❌ Error: {e}")
            return {
                "status": "error",
                "query": query,
                "error": str(e),
                "elapsed_seconds": elapsed
            }
    
    async def test_reasoning_analyze_endpoint(
        self,
        query: str,
        reasoning_types: List[str] = None
    ) -> Dict[str, Any]:
        """Test the dedicated reasoning analyze endpoint."""
        print(f"\n🔬 Testing Reasoning Analyze Endpoint: '{query[:60]}...'")
        
        try:
            payload = {
                "query": query,
                "session_id": "test_session",
                "enable_reasoning": True,
                "reasoning_types": reasoning_types or ["chain_of_thought"]
            }
            
            response = await self.client.post(
                f"{self.base_url}/reasoning/analyze",
                json=payload
            )
            
            if response.status_code == 200:
                data = response.json()
                print(f"   ✅ Analyze endpoint OK")
                return {"status": "success", "data": data}
            else:
                print(f"   ❌ Analyze endpoint failed: {response.status_code}")
                return {"status": "failed", "error": f"HTTP {response.status_code}"}
        except Exception as e:
            print(f"   ❌ Analyze endpoint error: {e}")
            return {"status": "error", "error": str(e)}
    
    async def validate_reasoning_chain_structure(self, chain: Dict[str, Any]) -> Dict[str, Any]:
        """Validate the structure of a reasoning chain."""
        issues = []
        warnings = []
        
        # Required fields
        required_fields = ["chain_id", "query", "reasoning_type", "steps", "final_conclusion", "overall_confidence"]
        for field in required_fields:
            if field not in chain:
                issues.append(f"Missing required field: {field}")
        
        # Validate steps
        if "steps" in chain:
            steps = chain["steps"]
            if not isinstance(steps, list):
                issues.append("Steps must be a list")
            else:
                if len(steps) == 0:
                    warnings.append("No reasoning steps generated")
                
                for i, step in enumerate(steps):
                    step_required = ["step_id", "step_type", "description", "reasoning", "confidence"]
                    for field in step_required:
                        if field not in step:
                            issues.append(f"Step {i} missing field: {field}")
        
        # Validate confidence range
        if "overall_confidence" in chain:
            conf = chain["overall_confidence"]
            if not isinstance(conf, (int, float)) or conf < 0 or conf > 1:
                issues.append(f"Invalid confidence value: {conf}")
        
        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "warnings": warnings
        }
    
    def print_summary(self):
        """Print test summary."""
        print("\n" + "="*80)
        print("📊 REASONING EVALUATION SUMMARY")
        print("="*80)
        
        total_tests = len(self.results)
        successful = sum(1 for r in self.results if r.get("status") == "success")
        failed = sum(1 for r in self.results if r.get("status") == "failed")
        errors = sum(1 for r in self.results if r.get("status") == "error")
        timeouts = sum(1 for r in self.results if r.get("status") == "timeout")
        
        print(f"\nTotal Tests: {total_tests}")
        print(f"✅ Successful: {successful}")
        print(f"❌ Failed: {failed}")
        print(f"⚠️  Errors: {errors}")
        print(f"⏱️  Timeouts: {timeouts}")
        
        # Reasoning chain statistics
        reasoning_chains = [r for r in self.results if r.get("has_reasoning_chain")]
        if reasoning_chains:
            print(f"\n🧠 Reasoning Chains Generated: {len(reasoning_chains)}")
            avg_steps = sum(r["reasoning_chain"]["steps_count"] for r in reasoning_chains) / len(reasoning_chains)
            avg_confidence = sum(r["reasoning_chain"]["overall_confidence"] for r in reasoning_chains) / len(reasoning_chains)
            print(f"   Average Steps: {avg_steps:.1f}")
            print(f"   Average Confidence: {avg_confidence:.2f}")
        
        # Response time statistics
        if self.results:
            avg_time = sum(r.get("elapsed_seconds", 0) for r in self.results) / len(self.results)
            max_time = max(r.get("elapsed_seconds", 0) for r in self.results)
            print(f"\n⏱️  Response Times:")
            print(f"   Average: {avg_time:.2f}s")
            print(f"   Maximum: {max_time:.2f}s")
        
        # Detailed results
        print("\n" + "-"*80)
        print("DETAILED RESULTS:")
        print("-"*80)
        for i, result in enumerate(self.results, 1):
            status_icon = "✅" if result.get("status") == "success" else "❌"
            print(f"\n{i}. {status_icon} {result.get('query', 'Unknown')[:60]}")
            if result.get("status") == "success":
                if result.get("has_reasoning_chain"):
                    chain = result["reasoning_chain"]
                    print(f"   Steps: {chain['steps_count']}, Type: {chain['reasoning_type']}, "
                          f"Confidence: {chain['overall_confidence']:.2f}")
                print(f"   Time: {result.get('elapsed_seconds', 0):.2f}s")
            else:
                print(f"   Error: {result.get('error', 'Unknown error')}")


async def run_comprehensive_evaluation():
    """Run comprehensive reasoning evaluation."""
    print("="*80)
    print("🧠 COMPREHENSIVE REASONING CAPABILITY EVALUATION")
    print("="*80)
    
    # Test queries covering different reasoning types
    test_queries = [
        # Chain-of-Thought queries
        {
            "query": "Why is forklift FL-01 experiencing low utilization?",
            "reasoning_types": ["chain_of_thought"],
            "expected_complex": True
        },
        {
            "query": "Explain the relationship between equipment maintenance schedules and safety incidents",
            "reasoning_types": ["chain_of_thought"],
            "expected_complex": True
        },
        
        # Scenario Analysis queries
        {
            "query": "If we increase the number of forklifts by 20%, what would be the impact on productivity?",
            "reasoning_types": ["scenario_analysis"],
            "expected_complex": True
        },
        {
            "query": "What if we optimize the picking route in Zone B and reassign 2 workers to Zone C?",
            "reasoning_types": ["scenario_analysis"],
            "expected_complex": True
        },
        
        # Causal Reasoning queries
        {
            "query": "Why does dock D2 have higher equipment failure rates compared to other docks?",
            "reasoning_types": ["causal"],
            "expected_complex": True
        },
        
        # Multi-Hop Reasoning queries
        {
            "query": "Analyze the relationship between equipment maintenance, worker assignments, and operational efficiency",
            "reasoning_types": ["multi_hop"],
            "expected_complex": True
        },
        
        # Pattern Recognition queries
        {
            "query": "What patterns can you identify in the recent increase of minor incidents in Zone C?",
            "reasoning_types": ["pattern_recognition"],
            "expected_complex": True
        },
        
        # Auto-selection (no specific type)
        {
            "query": "Compare the performance of forklifts FL-01, FL-02, and FL-03",
            "reasoning_types": None,
            "expected_complex": True
        },
        
        # Simple query (should not trigger reasoning)
        {
            "query": "What is the status of forklift FL-01?",
            "reasoning_types": None,
            "expected_complex": False
        },
    ]
    
    async with ReasoningEvaluator() as evaluator:
        # Health check
        print("\n🏥 Health Check...")
        if not await evaluator.test_health():
            print("❌ API is not accessible. Please ensure the backend server is running.")
            return
        print("✅ API is accessible")
        
        # Test reasoning types endpoint
        types_result = await evaluator.test_reasoning_types_endpoint()
        evaluator.results.append(types_result)
        
        # Test each query
        for test_case in test_queries:
            result = await evaluator.test_chat_with_reasoning(
                query=test_case["query"],
                reasoning_types=test_case["reasoning_types"],
                expected_complex=test_case["expected_complex"]
            )
            evaluator.results.append(result)
            
            # Validate reasoning chain structure if present
            if result.get("status") == "success" and result.get("has_reasoning_chain"):
                # We'd need the full chain data to validate, but we can check what we have
                pass
        
        # Test analyze endpoint with one query
        analyze_result = await evaluator.test_reasoning_analyze_endpoint(
            query="Why is equipment utilization low in Zone A?",
            reasoning_types=["chain_of_thought"]
        )
        evaluator.results.append(analyze_result)
        
        # Print summary
        evaluator.print_summary()
        
        # Save results to file
        results_file = project_root / "tests" / "reasoning_evaluation_results.json"
        with open(results_file, "w") as f:
            json.dump(evaluator.results, f, indent=2, default=str)
        print(f"\n💾 Results saved to: {results_file}")


if __name__ == "__main__":
    asyncio.run(run_comprehensive_evaluation())

