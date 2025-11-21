#!/usr/bin/env python3
"""
Create default admin user for warehouse operational assistant
"""

import asyncio
import asyncpg
import logging
import os
import bcrypt
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def create_default_admin():
    """Create default admin user"""
    try:
        # Connect to database
        conn = await asyncpg.connect(
            host=os.getenv("PGHOST", "localhost"),
            port=int(os.getenv("PGPORT", "5435")),
            user=os.getenv("POSTGRES_USER", "warehouse"),
            password=os.getenv("POSTGRES_PASSWORD", "changeme"),
            database=os.getenv("POSTGRES_DB", "warehouse")
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
        
        # Always update admin password to ensure it matches
        password = os.getenv("DEFAULT_ADMIN_PASSWORD", "changeme")
        password_bytes = password.encode('utf-8')
        if len(password_bytes) > 72:
            password_bytes = password_bytes[:72]
        salt = bcrypt.gensalt()
        hashed_password = bcrypt.hashpw(password_bytes, salt).decode('utf-8')
        
        if not admin_exists:
            logger.info("Creating default admin user...")
            
            await conn.execute("""
                INSERT INTO users (username, email, full_name, hashed_password, role, status)
                VALUES ($1, $2, $3, $4, $5, $6)
            """, "admin", "admin@warehouse.com", "System Administrator", hashed_password, "admin", "active")
            
            logger.info("Default admin user created")
        else:
            logger.info("Admin user already exists, updating password...")
            await conn.execute("""
                UPDATE users 
                SET hashed_password = $1, updated_at = CURRENT_TIMESTAMP
                WHERE username = 'admin'
            """, hashed_password)
            logger.info("Admin password updated")
        
        logger.info("Login credentials:")
        logger.info("   Username: admin")
        logger.info("   Password: [REDACTED - check environment variable DEFAULT_ADMIN_PASSWORD]")
        
        # Create a regular user for testing
        user_exists = await conn.fetchval("SELECT EXISTS(SELECT 1 FROM users WHERE username = 'user')")
        
        # Always update user password to ensure it matches
        user_password = os.getenv("DEFAULT_USER_PASSWORD", "changeme")
        user_password_bytes = user_password.encode('utf-8')
        if len(user_password_bytes) > 72:
            user_password_bytes = user_password_bytes[:72]
        user_salt = bcrypt.gensalt()
        user_hashed_password = bcrypt.hashpw(user_password_bytes, user_salt).decode('utf-8')
        
        if not user_exists:
            logger.info("Creating default user...")
            
            await conn.execute("""
                INSERT INTO users (username, email, full_name, hashed_password, role, status)
                VALUES ($1, $2, $3, $4, $5, $6)
            """, "user", "user@warehouse.com", "Regular User", user_hashed_password, "operator", "active")
            
            logger.info("Default user created")
        else:
            logger.info("User already exists, updating password...")
            await conn.execute("""
                UPDATE users 
                SET hashed_password = $1, updated_at = CURRENT_TIMESTAMP
                WHERE username = 'user'
            """, user_hashed_password)
            logger.info("User password updated")
        
        logger.info("User credentials:")
        logger.info("   Username: user")
        logger.info("   Password: [REDACTED - check environment variable DEFAULT_USER_PASSWORD]")
        
        await conn.close()
        logger.info("User setup complete!")
        
    except Exception as e:
        logger.error(f"Error creating users: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(create_default_admin())
