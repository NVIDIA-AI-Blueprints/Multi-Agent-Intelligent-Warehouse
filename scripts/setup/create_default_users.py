#!/usr/bin/env python3
"""
Create default admin user for warehouse operational assistant
"""

import asyncio
import asyncpg
import logging
from datetime import datetime
from passlib.context import CryptContext

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

async def create_default_admin():
    """Create default admin user"""
    try:
        # Connect to database
        conn = await asyncpg.connect(
            host="localhost",
            port=5435,
            user="warehouse",
            password="warehousepw",
            database="warehouse"
        )
        
        logger.info("Connected to database")
        
        # Check if users table exists
        table_exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'users'
            );
        """)
        
        if not table_exists:
            logger.info("Creating users table...")
            await conn.execute("""
                CREATE TABLE users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(50) UNIQUE NOT NULL,
                    email VARCHAR(100) UNIQUE NOT NULL,
                    full_name VARCHAR(100) NOT NULL,
                    hashed_password VARCHAR(255) NOT NULL,
                    role VARCHAR(20) NOT NULL DEFAULT 'user',
                    status VARCHAR(20) NOT NULL DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP
                );
            """)
            logger.info("Users table created")
        
        # Check if admin user exists
        admin_exists = await conn.fetchval("SELECT EXISTS(SELECT 1 FROM users WHERE username = 'admin')")
        
        if not admin_exists:
            logger.info("Creating default admin user...")
            
            # Hash password using bcrypt (same as JWT handler)
            password = "password123"
            hashed_password = pwd_context.hash(password)
            
            await conn.execute("""
                INSERT INTO users (username, email, full_name, hashed_password, role, status)
                VALUES ($1, $2, $3, $4, $5, $6)
            """, "admin", "admin@warehouse.com", "System Administrator", hashed_password, "admin", "active")
            
            logger.info("Default admin user created")
            logger.info("Login credentials:")
            logger.info("   Username: admin")
            logger.info("   Password: password123")
        else:
            logger.info("Admin user already exists")
        
        # Create a regular user for testing
        user_exists = await conn.fetchval("SELECT EXISTS(SELECT 1 FROM users WHERE username = 'user')")
        
        if not user_exists:
            logger.info("Creating default user...")
            
            password = "user123"
            hashed_password = pwd_context.hash(password)
            
            await conn.execute("""
                INSERT INTO users (username, email, full_name, hashed_password, role, status)
                VALUES ($1, $2, $3, $4, $5, $6)
            """, "user", "user@warehouse.com", "Regular User", hashed_password, "operator", "active")
            
            logger.info("Default user created")
            logger.info("User credentials:")
            logger.info("   Username: user")
            logger.info("   Password: user123")
        
        await conn.close()
        logger.info("User setup complete!")
        
    except Exception as e:
        logger.error(f"Error creating users: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(create_default_admin())
