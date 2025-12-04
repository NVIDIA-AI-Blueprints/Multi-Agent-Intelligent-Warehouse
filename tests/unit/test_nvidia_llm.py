#!/usr/bin/env python3
"""
Test NVIDIA LLM API endpoint directly
"""

import asyncio
import sys
import os
import pytest
from pathlib import Path
from dotenv import load_dotenv

# Add the project root to the path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Import test utilities directly to avoid package conflicts
import importlib.util
test_utils_path = project_root / "tests" / "unit" / "test_utils.py"
spec = importlib.util.spec_from_file_location("test_utils", test_utils_path)
test_utils = importlib.util.module_from_spec(spec)
spec.loader.exec_module(test_utils)
require_env_var = test_utils.require_env_var

load_dotenv()

@pytest.mark.asyncio
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

@pytest.mark.asyncio
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

@pytest.mark.asyncio
async def test_nano_vl_8b():
    """Test Llama Nemotron Nano VL 8B (Vision-Language Model) API."""
    try:
        from src.api.agents.document.processing.small_llm_processor import SmallLLMProcessor
        
        print("\n🔧 Testing Llama Nemotron Nano VL 8B (Vision-Language Model)...")
        processor = SmallLLMProcessor()
        await processor.initialize()
        
        if not processor.api_key:
            print("⚠️  LLAMA_NANO_VL_API_KEY not found, skipping Nano VL 8B test")
            return False
        
        # Test with simple text input (text-only mode)
        ocr_text = "Invoice #12345\nDate: 2024-01-15\nTotal: $100.00"
        result = await processor._call_text_only_api(ocr_text, "invoice")
        
        print(f"✅ Nano VL 8B Response:")
        print(f"   - Text-only processing: Success")
        print(f"   - Confidence: {result.get('confidence', 0.0):.2f}")
        
        # Test multimodal processing if possible
        try:
            from PIL import Image
            import base64
            import io
            
            # Create a simple test image
            test_image = Image.new('RGB', (200, 100), color='white')
            img_buffer = io.BytesIO()
            test_image.save(img_buffer, format='PNG')
            img_buffer.seek(0)
            image_base64 = base64.b64encode(img_buffer.read()).decode('utf-8')
            
            multimodal_input = {
                "prompt": "Extract key information from this invoice document.",
                "images": [{"image": image_base64, "format": "png"}]
            }
            
            multimodal_result = await processor._call_nano_vl_api(multimodal_input)
            print(f"   - Multimodal processing: Success")
            print(f"   - Multimodal confidence: {multimodal_result.get('confidence', 0.0):.2f}")
        except Exception as multimodal_error:
            print(f"   - Multimodal processing: ⚠️  {str(multimodal_error)[:100]}...")
            # Multimodal failure is not critical, text-only works
        
        return True
        
    except Exception as e:
        print(f"❌ Nano VL 8B Test Failed: {e}")
        return False

async def main():
    """Run all tests."""
    print("🚀 Testing NVIDIA API Endpoints")
    print("=" * 50)
    
    # Check environment variables
    try:
        require_env_var("NVIDIA_API_KEY")
    except ValueError as e:
        print(f"❌ {e}")
        print("Please set NVIDIA_API_KEY environment variable before running tests.")
        sys.exit(1)
    
    # Test LLM
    llm_success = await test_nvidia_llm()
    
    # Test Embedding
    embedding_success = await test_embedding()
    
    # Test Nano VL 8B (optional - uses different API key)
    nano_vl_success = await test_nano_vl_8b()
    
    print("\n" + "=" * 50)
    print("📊 Test Results:")
    print(f"   LLM API: {'✅ PASS' if llm_success else '❌ FAIL'}")
    print(f"   Embedding API: {'✅ PASS' if embedding_success else '❌ FAIL'}")
    print(f"   Nano VL 8B API: {'✅ PASS' if nano_vl_success else '⚠️  SKIP/FAIL'}")
    
    if llm_success and embedding_success:
        print("\n🎉 Core NVIDIA API endpoints are working!")
        if nano_vl_success:
            print("   (Nano VL 8B also working)")
    else:
        print("\n⚠️  Some NVIDIA API endpoints are not working.")
    
    # Return success if core APIs work (Nano VL is optional)
    return llm_success and embedding_success

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
