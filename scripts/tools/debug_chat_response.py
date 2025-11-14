#!/usr/bin/env python3
"""
Debug Chat Response

Detailed debugging of chat responses to identify the issue.
"""

import asyncio
import aiohttp
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def debug_chat():
    """Debug chat response in detail."""
    async with aiohttp.ClientSession() as session:
        # Test a simple query
        payload = {
            "message": "What equipment do we have?",
            "session_id": "debug_session",
            "context": {}
        }
        
        logger.info("🔍 Sending chat request...")
        logger.info(f"Payload: {json.dumps(payload, indent=2)}")
        
        async with session.post(
            "http://localhost:8001/api/v1/chat",
            json=payload,
            headers={"Content-Type": "application/json"}
        ) as response:
            
            logger.info(f"📡 Response status: {response.status}")
            logger.info(f"📡 Response headers: {dict(response.headers)}")
            
            response_text = await response.text()
            logger.info(f"📡 Raw response text: {response_text}")
            
            try:
                response_json = await response.json()
                logger.info(f"📊 Parsed JSON response:")
                logger.info(json.dumps(response_json, indent=2, default=str))
                
                # Check specific fields
                logger.info("\n🔍 Field Analysis:")
                logger.info(f"  reply: '{response_json.get('reply', 'MISSING')}'")
                logger.info(f"  route: '{response_json.get('route', 'MISSING')}'")
                logger.info(f"  intent: '{response_json.get('intent', 'MISSING')}'")
                logger.info(f"  session_id: '{response_json.get('session_id', 'MISSING')}'")
                logger.info(f"  context: {response_json.get('context', 'MISSING')}")
                logger.info(f"  structured_data: {response_json.get('structured_data', 'MISSING')}")
                logger.info(f"  recommendations: {response_json.get('recommendations', 'MISSING')}")
                logger.info(f"  confidence: {response_json.get('confidence', 'MISSING')}")
                logger.info(f"  actions_taken: {response_json.get('actions_taken', 'MISSING')}")
                
            except Exception as e:
                logger.error(f"❌ Failed to parse JSON response: {e}")

if __name__ == "__main__":
    asyncio.run(debug_chat())
