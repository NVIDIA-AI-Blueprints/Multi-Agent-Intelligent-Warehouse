#!/usr/bin/env python3
"""
Test NVIDIA NIM Integration for Warehouse Operational Assistant

This script tests the full LLM integration with various inventory queries.
"""

import asyncio
import json
import sys
from pathlib import Path

async def test_nvidia_integration():
    """Test the full NVIDIA NIM integration."""
    print("🧪 Testing NVIDIA NIM Integration")
    print("=" * 50)
    
    try:
        # Test 1: NIM Client Health Check
        print("\n1️⃣ Testing NIM Client Health Check...")
        from src.api.services.llm.nim_client import get_nim_client
        
        nim_client = await get_nim_client()
        health = await nim_client.health_check()
        
        print(f"   LLM Service: {'✅' if health['llm_service'] else '❌'}")
        print(f"   Embedding Service: {'✅' if health['embedding_service'] else '❌'}")
        print(f"   Overall: {'✅' if health['overall'] else '❌'}")
        
        if not health['overall']:
            print("❌ NVIDIA NIM services are not healthy. Please check your API key and connection.")
            return False
        
        # Test 2: Inventory Agent Initialization
        print("\n2️⃣ Testing Inventory Intelligence Agent...")
        from src.api.agents.inventory.inventory_agent import get_inventory_agent
        
        inventory_agent = await get_inventory_agent()
        print("   ✅ Inventory Intelligence Agent initialized")
        
        # Test 3: Sample Queries
        test_queries = [
            "What is the stock level for SKU123?",
            "Which items need reordering?",
            "Show me low stock items",
            "Where is the Blue Pallet Jack located?",
            "Help me plan cycle counting for Aisle A3"
        ]
        
        print("\n3️⃣ Testing Sample Inventory Queries...")
        for i, query in enumerate(test_queries, 1):
            print(f"\n   Query {i}: {query}")
            try:
                response = await inventory_agent.process_query(query, session_id="test")
                
                print(f"   Response Type: {response.response_type}")
                print(f"   Confidence: {response.confidence:.2f}")
                print(f"   Natural Language: {response.natural_language[:100]}...")
                print(f"   Recommendations: {len(response.recommendations)} items")
                
                if response.structured_data:
                    print(f"   Structured Data: {json.dumps(response.structured_data, indent=2)[:200]}...")
                
            except Exception as e:
                print(f"   ❌ Error: {e}")
        
        # Test 4: API Endpoint Test
        print("\n4️⃣ Testing API Endpoint...")
        import httpx
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    "http://localhost:8001/api/v1/chat",
                    json={"message": "What is the stock level for SKU123?"},
                    headers={"Content-Type": "application/json"},
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    print("   ✅ API endpoint responding")
                    print(f"   Route: {data.get('route')}")
                    print(f"   Intent: {data.get('intent')}")
                    print(f"   Confidence: {data.get('confidence')}")
                    print(f"   Reply: {data.get('reply', '')[:100]}...")
                else:
                    print(f"   ❌ API endpoint error: {response.status_code}")
                    
            except Exception as e:
                print(f"   ❌ API endpoint test failed: {e}")
        
        print("\n🎉 NVIDIA NIM Integration Test Complete!")
        return True
        
    except Exception as e:
        print(f"❌ Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_llm_capabilities():
    """Test specific LLM capabilities."""
    print("\n🧠 Testing LLM Capabilities")
    print("=" * 30)
    
    try:
        from src.api.services.llm.nim_client import get_nim_client
        
        nim_client = await get_nim_client()
        
        # Test 1: Basic LLM Response
        print("\n1️⃣ Testing Basic LLM Response...")
        messages = [
            {"role": "system", "content": "You are a warehouse inventory expert."},
            {"role": "user", "content": "What is the difference between SKU and barcode?"}
        ]
        
        response = await nim_client.generate_response(messages, temperature=0.1, max_tokens=200)
        print(f"   Response: {response.content[:150]}...")
        print(f"   Model: {response.model}")
        print(f"   Usage: {response.usage}")
        
        # Test 2: Embedding Generation
        print("\n2️⃣ Testing Embedding Generation...")
        texts = ["warehouse inventory management", "safety procedures", "equipment maintenance"]
        
        embedding_response = await nim_client.generate_embeddings(texts)
        print(f"   Generated {len(embedding_response.embeddings)} embeddings")
        print(f"   Embedding dimension: {len(embedding_response.embeddings[0])}")
        print(f"   Model: {embedding_response.model}")
        
        print("   ✅ LLM capabilities working correctly")
        return True
        
    except Exception as e:
        print(f"   ❌ LLM capabilities test failed: {e}")
        return False

if __name__ == "__main__":
    async def main():
        print("🚀 NVIDIA NIM Integration Test Suite")
        print("=" * 50)
        
        # Check if API key is set
        import os
        from dotenv import load_dotenv
        load_dotenv()
        
        api_key = os.getenv("NVIDIA_API_KEY")
        if not api_key or api_key == "your_nvidia_api_key_here":
            print("❌ NVIDIA API key not configured.")
            print("Please run: python setup_nvidia_api.py")
            sys.exit(1)
        
        # Run tests
        llm_success = await test_llm_capabilities()
        integration_success = await test_nvidia_integration()
        
        if llm_success and integration_success:
            print("\n🎉 All tests passed! NVIDIA NIM integration is working correctly.")
        else:
            print("\n❌ Some tests failed. Please check the errors above.")
            sys.exit(1)
    
    asyncio.run(main())
