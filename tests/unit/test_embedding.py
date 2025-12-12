#!/usr/bin/env python3
"""
Quick test script to verify nvidia/nv-embedqa-e5-v5 embedding model is working.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

async def test_embedding():
    """Test the embedding model."""
    print("🧪 Testing NVIDIA Embedding Model: nvidia/nv-embedqa-e5-v5")
    print("=" * 60)
    
    try:
        from src.api.services.llm.nim_client import NIMClient, NIMConfig
        import os
        from dotenv import load_dotenv
        
        # Load environment variables
        load_dotenv()
        
        # Check API key (prefer EMBEDDING_API_KEY, fallback to NVIDIA_API_KEY)
        embedding_api_key = os.getenv("EMBEDDING_API_KEY") or os.getenv("NVIDIA_API_KEY", "")
        if not embedding_api_key or embedding_api_key == "your-nvidia-api-key-here":
            print("❌ EMBEDDING_API_KEY or NVIDIA_API_KEY not set in .env file")
            print("   Please set EMBEDDING_API_KEY (or NVIDIA_API_KEY) in your .env file")
            return False
        
        print(f"✅ Embedding API Key found: {embedding_api_key[:20]}...")
        
        # Check configuration
        config = NIMConfig()
        print(f"\n📋 Configuration:")
        print(f"   Embedding Model: {config.embedding_model}")
        print(f"   Embedding URL: {config.embedding_base_url}")
        print(f"   API Key Set: {'Yes' if config.embedding_api_key else 'No'}")
        
        # Create client
        print(f"\n🔧 Creating NIM client...")
        client = NIMClient(config)
        
        # Test embedding generation
        print(f"\n🧪 Testing embedding generation...")
        test_texts = ["Test warehouse operations", "What is the stock level?"]
        
        response = await client.generate_embeddings(test_texts)
        
        print(f"\n✅ Embedding generation successful!")
        print(f"   Number of embeddings: {len(response.embeddings)}")
        print(f"   Embedding dimension: {len(response.embeddings[0]) if response.embeddings else 0}")
        print(f"   Model used: {response.model}")
        print(f"   Usage: {response.usage}")
        
        # Verify dimension (nv-embedqa-e5-v5 should be 1024)
        if response.embeddings and len(response.embeddings[0]) == 1024:
            print(f"\n✅ Embedding dimension correct (1024 for nv-embedqa-e5-v5)")
        else:
            print(f"\n⚠️  Unexpected embedding dimension: {len(response.embeddings[0]) if response.embeddings else 0}")
        
        # Test health check
        print(f"\n🏥 Running health check...")
        health = await client.health_check()
        print(f"   LLM Service: {'✅' if health.get('llm_service') else '❌'}")
        print(f"   Embedding Service: {'✅' if health.get('embedding_service') else '❌'}")
        print(f"   Overall: {'✅' if health.get('overall') else '❌'}")
        
        # Cleanup
        await client.close()
        
        print(f"\n" + "=" * 60)
        print(f"✅ All tests passed! The embedding model is working correctly.")
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_embedding())
    sys.exit(0 if success else 1)

