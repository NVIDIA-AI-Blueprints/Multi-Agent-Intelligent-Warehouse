#!/usr/bin/env python3
"""
Test NVIDIA LLM API endpoint directly
"""

import asyncio
import sys
import os
from dotenv import load_dotenv

# Add the project root to the path
sys.path.append('.')

load_dotenv()

async def test_nvidia_llm():
    """Test NVIDIA LLM API directly."""
    try:
        from src.api.services.llm.nim_client import NIMClient
        
        print("🔧 Initializing NVIDIA NIM Client...")
        client = NIMClient()
        
        print("🧪 Testing LLM generation...")
        messages = [
            {"role": "user", "content": "What is 2+2? Please provide a simple answer."}
        ]
        response = await client.generate_response(
            messages=messages,
            max_tokens=100,
            temperature=0.1
        )
        
        print(f"✅ NVIDIA LLM Response: {response}")
        return True
        
    except Exception as e:
        print(f"❌ NVIDIA LLM Test Failed: {e}")
        return False

async def test_embedding():
    """Test NVIDIA Embedding API."""
    try:
        from src.api.services.llm.nim_client import NIMClient
        
        print("\n🔧 Testing NVIDIA Embedding API...")
        client = NIMClient()
        
        print("🧪 Testing embedding generation...")
        embedding = await client.generate_embeddings(["Test warehouse operations"])
        
        print(f"✅ Embedding generated: {len(embedding.embeddings[0])} dimensions")
        print(f"   First 5 values: {embedding.embeddings[0][:5]}")
        return True
        
    except Exception as e:
        print(f"❌ NVIDIA Embedding Test Failed: {e}")
        return False

async def main():
    """Run all tests."""
    print("🚀 Testing NVIDIA API Endpoints")
    print("=" * 50)
    
    # Test LLM
    llm_success = await test_nvidia_llm()
    
    # Test Embedding
    embedding_success = await test_embedding()
    
    print("\n" + "=" * 50)
    print("📊 Test Results:")
    print(f"   LLM API: {'✅ PASS' if llm_success else '❌ FAIL'}")
    print(f"   Embedding API: {'✅ PASS' if embedding_success else '❌ FAIL'}")
    
    if llm_success and embedding_success:
        print("\n🎉 All NVIDIA API endpoints are working!")
    else:
        print("\n⚠️  Some NVIDIA API endpoints are not working.")
    
    return llm_success and embedding_success

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
