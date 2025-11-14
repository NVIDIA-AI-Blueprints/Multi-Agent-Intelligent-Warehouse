#!/usr/bin/env python3
"""
Simple migration script to set up the database schema.
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def run_migrations():
    """Run database migrations."""
    
    # Database connection
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://warehouse:warehousepw@localhost:5435/warehouse")
    
    try:
        print("🔌 Connecting to database...")
        conn = await asyncpg.connect(DATABASE_URL)
        print("✅ Database connected successfully")
        
        # Create migration tracking table
        print("📋 Creating migration tracking table...")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                id SERIAL PRIMARY KEY,
                version VARCHAR(50) NOT NULL UNIQUE,
                description TEXT NOT NULL,
                applied_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                checksum VARCHAR(64) NOT NULL,
                execution_time_ms INTEGER,
                rollback_sql TEXT
            );
        """)
        
        # Create application metadata table
        print("📊 Creating application metadata table...")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS application_metadata (
                id SERIAL PRIMARY KEY,
                key VARCHAR(100) NOT NULL UNIQUE,
                value TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
        """)
        
        # Insert initial metadata
        print("📝 Inserting initial metadata...")
        await conn.execute("""
            INSERT INTO application_metadata (key, value, description) VALUES
                ('app_version', '0.1.0', 'Current application version'),
                ('schema_version', '0.1.0', 'Current database schema version'),
                ('migration_system', 'enabled', 'Database migration system status')
            ON CONFLICT (key) DO NOTHING;
        """)
        
        # Create basic warehouse tables
        print("🏭 Creating warehouse tables...")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS warehouse_locations (
                id SERIAL PRIMARY KEY,
                location_code VARCHAR(50) NOT NULL UNIQUE,
                location_name VARCHAR(200) NOT NULL,
                location_type VARCHAR(50) NOT NULL,
                parent_location_id INTEGER REFERENCES warehouse_locations(id),
                coordinates JSONB,
                dimensions JSONB,
                capacity JSONB,
                status VARCHAR(20) DEFAULT 'active',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
        """)
        
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS equipment (
                id SERIAL PRIMARY KEY,
                equipment_code VARCHAR(50) NOT NULL UNIQUE,
                equipment_name VARCHAR(200) NOT NULL,
                equipment_type VARCHAR(50) NOT NULL,
                manufacturer VARCHAR(100),
                model VARCHAR(100),
                serial_number VARCHAR(100),
                status VARCHAR(20) DEFAULT 'operational',
                location_id INTEGER REFERENCES warehouse_locations(id),
                specifications JSONB,
                maintenance_schedule JSONB,
                last_maintenance_date DATE,
                next_maintenance_date DATE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
        """)
        
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS inventory_items (
                id SERIAL PRIMARY KEY,
                item_code VARCHAR(50) NOT NULL UNIQUE,
                item_name VARCHAR(200) NOT NULL,
                description TEXT,
                category VARCHAR(100),
                subcategory VARCHAR(100),
                unit_of_measure VARCHAR(20) NOT NULL,
                dimensions JSONB,
                weight DECIMAL(10,3),
                status VARCHAR(20) DEFAULT 'active',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
        """)
        
        # Record migration
        print("📝 Recording migration...")
        await conn.execute("""
            INSERT INTO schema_migrations (version, description, checksum) VALUES
                ('001', 'Initial schema setup', 'abc123')
            ON CONFLICT (version) DO NOTHING;
        """)
        
        print("✅ Database migration completed successfully!")
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if 'conn' in locals():
            await conn.close()
            print("🔌 Database connection closed")

if __name__ == "__main__":
    asyncio.run(run_migrations())
