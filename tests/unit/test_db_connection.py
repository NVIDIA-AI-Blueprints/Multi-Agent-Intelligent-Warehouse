#!/usr/bin/env python3
"""
Test database connection and authentication
"""

import asyncio
import sys
import os
sys.path.append('.')

from src.retrieval.structured import SQLRetriever
from src.api.services.auth.user_service import UserService

async def test_connection():
    """Test database connection and authentication."""
    print("🔍 Testing database connection...")
    
    try:
        # Test SQL retriever
        sql_retriever = SQLRetriever()
        await sql_retriever.initialize()
        print("✅ SQL Retriever initialized")
        
        # Test simple query
        result = await sql_retriever.fetch_one("SELECT 1 as test")
        print(f"✅ Simple query result: {result}")
        
        # Test user service
        user_service = UserService()
        await user_service.initialize()
        print("✅ User service initialized")
        
        # Test user lookup
        user = await user_service.get_user_for_auth("admin")
        if user:
            print(f"✅ Found user: {user.username}")
        else:
            print("❌ User not found")
        
        await sql_retriever.close()
        print("✅ Database connection test completed")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_connection())
