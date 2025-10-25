#!/usr/bin/env python3
"""
Update admin user password with proper bcrypt hashing
"""

import asyncio
import asyncpg
import logging
from passlib.context import CryptContext

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

async def update_admin_password():
    """Update admin user password with bcrypt"""
    try:
        # Connect to database
        conn = await asyncpg.connect(
            host="localhost",
            port=5435,
            user="warehouse",
            password="warehousepw",
            database="warehouse"
        )
        
        logger.info("✅ Connected to database")
        
        # Update admin password with bcrypt
        password = "admin123"
        hashed_password = pwd_context.hash(password)
        
        await conn.execute("""
            UPDATE users 
            SET hashed_password = $1, updated_at = CURRENT_TIMESTAMP
            WHERE username = 'admin'
        """, hashed_password)
        
        logger.info("✅ Admin password updated with bcrypt")
        logger.info("📝 Login credentials:")
        logger.info("   Username: admin")
        logger.info("   Password: admin123")
        
        await conn.close()
        logger.info("🎉 Password update complete!")
        
    except Exception as e:
        logger.error(f"❌ Error updating password: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(update_admin_password())
