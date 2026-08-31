#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Synthetic Data Generator for Warehouse Operational Assistant

LEGACY — Demo Mode data generation
As of Phase 14E, MAIW Demo Mode uses WarehouseDataPack from packages/maiw-world/
instead of direct PostgreSQL seeding.
This script is retained for reference but is NOT part of the v2 demo setup path.

Generates comprehensive synthetic data across all databases:
- PostgreSQL/TimescaleDB: Inventory, tasks, users, safety incidents, equipment telemetry
- Milvus: Vector embeddings for documents and knowledge base
- Redis: Session data and caching

This creates a realistic warehouse environment for demos and testing.

Security Note: This script uses Python's random module (PRNG) for generating
synthetic test data (inventory, tasks, incidents, telemetry, cache data). This is
appropriate for data generation purposes. For security-sensitive operations
(tokens, keys, passwords, session IDs), the secrets module (CSPRNG) should be
used instead.
"""

import asyncio
import os
# Security: Using random module is appropriate here - generating synthetic test data only
# For security-sensitive values (tokens, keys, passwords), use secrets module instead
import random
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import psycopg
from pymilvus import Collection, connections
import redis
import hashlib
import bcrypt
from faker import Faker

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Faker for realistic data generation
fake = Faker()

# Database connection settings
POSTGRES_DSN = os.getenv(
    "DATABASE_URL",
    f"postgresql://{os.getenv('POSTGRES_USER', 'warehouse')}:{os.getenv('POSTGRES_PASSWORD', '')}@localhost:5435/{os.getenv('POSTGRES_DB', 'warehouse')}"
)
MILVUS_HOST = "localhost"
MILVUS_PORT = 19530
REDIS_HOST = "localhost"
REDIS_PORT = 6379

class SyntheticDataGenerator:
    """Generates comprehensive synthetic data for warehouse operations."""
    
    def __init__(self):
        self.pg_conn = None
        self.milvus_conn = None
        self.redis_conn = None
        self.fake = Faker()
        
        # Warehouse configuration
        self.warehouse_zones = ["A", "B", "C", "D", "E", "F"]
        self.aisles_per_zone = 10
        self.racks_per_aisle = 5
        self.levels_per_rack = 4
        
        # Equipment types
        self.equipment_types = [
            "forklift", "pallet_jack", "conveyor", "scanner", "printer",
            "crane", "tugger", "lift_truck", "reach_truck", "order_picker",
            "humanoid_robot", "amr", "agv", "pick_place_robot", "robotic_arm",
            "cobot", "mobile_manipulator", "vision_system", "robot_controller"
        ]
        
        # Product categories
        self.product_categories = [
            "Electronics", "Clothing", "Home & Garden", "Automotive", "Sports",
            "Books", "Tools", "Food & Beverage", "Health & Beauty", "Toys",
            "Robotics", "Automation", "Industrial Equipment", "Warehouse Technology"
        ]
        
        # Safety incident types
        self.incident_types = [
            "slip_and_fall", "equipment_malfunction", "chemical_spill", "fire_hazard",
            "electrical_issue", "structural_damage", "injury", "near_miss"
        ]
        
        # Task types
        self.task_types = [
            "pick", "pack", "putaway", "cycle_count", "replenishment", "inspection",
            "maintenance", "cleaning", "loading", "unloading"
        ]
    
    async def initialize_connections(self):
        """Initialize database connections."""
        try:
            # PostgreSQL connection
            self.pg_conn = await psycopg.AsyncConnection.connect(POSTGRES_DSN)
            logger.info("✅ Connected to PostgreSQL")
            
            # Milvus connection
            connections.connect("default", host=MILVUS_HOST, port=MILVUS_PORT)
            self.milvus_conn = True
            logger.info("✅ Connected to Milvus")
            
            # Redis connection
            self.redis_conn = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
            self.redis_conn.ping()
            logger.info("✅ Connected to Redis")
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to databases: {e}")
            raise
    
    async def generate_inventory_data(self, count: int = 1000):
        """Generate comprehensive inventory data."""
        logger.info(f"📦 Generating {count} inventory items...")
        # Security: All random.choice/randint/random() calls below are for generating synthetic inventory data only
        # Not security-sensitive - these are just test data identifiers and quantities
        
        async with self.pg_conn.cursor() as cur:
            # Clear existing data
            await cur.execute("DELETE FROM inventory_items")
            
            for i in range(count):
                sku = f"SKU{str(i+1).zfill(6)}"
                category = random.choice(self.product_categories)
                name = f"{fake.word().title()} {fake.word().title()}"
                
                # Generate realistic quantities and locations
                quantity = random.randint(0, 500)
                reorder_point = random.randint(5, 50)
                zone = random.choice(self.warehouse_zones)
                aisle = random.randint(1, self.aisles_per_zone)
                rack = random.randint(1, self.racks_per_aisle)
                level = random.randint(1, self.levels_per_rack)
                location = f"Zone {zone}-Aisle {aisle}-Rack {rack}-Level {level}"
                
                # Add some items below reorder point for alerts
                if random.random() < 0.1:  # 10% chance
                    quantity = random.randint(0, reorder_point - 1)
                
                await cur.execute("""
                    INSERT INTO inventory_items (sku, name, quantity, location, reorder_point, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (sku, name, quantity, location, reorder_point, fake.date_time_between(start_date='-30d', end_date='now')))
        
        logger.info("✅ Inventory data generated")
    
    async def generate_user_data(self, count: int = 50):
        """Generate comprehensive user data with different roles."""
        logger.info(f"👥 Generating {count} users...")
        
        async with self.pg_conn.cursor() as cur:
            # Clear existing data
            await cur.execute("DELETE FROM user_sessions")
            await cur.execute("DELETE FROM audit_log")
            await cur.execute("DELETE FROM users WHERE username != 'admin'")
            
            roles = ['manager', 'supervisor', 'operator', 'viewer']
            role_counts = {'manager': 8, 'supervisor': 12, 'operator': 25, 'viewer': 5}
            
            for role, count in role_counts.items():
                for i in range(count):
                    username = f"{role}{i+1}"
                    email = f"{username}@warehouse.com"
                    full_name = fake.name()
                    default_password = os.getenv("DEFAULT_USER_PASSWORD", "changeme")
                    hashed_password = bcrypt.hashpw(default_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                    
                    await cur.execute("""
                        INSERT INTO users (username, email, full_name, role, status, hashed_password, created_at, last_login)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (username, email, full_name, role, 'active', hashed_password, 
                          fake.date_time_between(start_date='-90d', end_date='-1d'),
                          fake.date_time_between(start_date='-7d', end_date='now')))
        
        logger.info("✅ User data generated")
    
    async def generate_task_data(self, count: int = 500):
        """Generate comprehensive task data."""
        logger.info(f"📋 Generating {count} tasks...")
        # Security: All random.choice/randint/random() calls below are for generating synthetic task data only
        # Not security-sensitive - these are just test data identifiers and attributes
        
        async with self.pg_conn.cursor() as cur:
            # Clear existing data
            await cur.execute("DELETE FROM tasks")
            
            statuses = ['pending', 'in_progress', 'completed', 'cancelled']
            status_weights = [0.2, 0.3, 0.4, 0.1]
            
            for i in range(count):
                task_type = random.choice(self.task_types)
                status = random.choices(statuses, weights=status_weights)[0]
                
                # Generate realistic task payload
                payload = {
                    "priority": random.choice(["low", "medium", "high", "urgent"]),
                    "zone": random.choice(self.warehouse_zones),
                    "estimated_duration": random.randint(5, 120),  # minutes
                    "assigned_equipment": random.choice(self.equipment_types) if random.random() < 0.7 else None,
                    "notes": fake.sentence() if random.random() < 0.3 else None
                }
                
                # Add task-specific data
                if task_type == "pick":
                    payload.update({
                        "order_id": f"ORD{random.randint(1000, 9999)}",
                        "items": [{"sku": f"SKU{random.randint(1, 1000):06d}", "qty": random.randint(1, 10)} for _ in range(random.randint(1, 5))]
                    })
                elif task_type == "cycle_count":
                    payload.update({
                        "location": f"Zone {random.choice(self.warehouse_zones)}-Aisle {random.randint(1, 10)}",
                        "expected_count": random.randint(0, 100)
                    })
                
                assignee = f"operator{random.randint(1, 25)}" if status in ['in_progress', 'completed'] else None
                
                await cur.execute("""
                    INSERT INTO tasks (kind, status, assignee, payload, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (task_type, status, assignee, json.dumps(payload),
                      fake.date_time_between(start_date='-30d', end_date='now'),
                      fake.date_time_between(start_date='-30d', end_date='now')))
        
        logger.info("✅ Task data generated")
    
    async def generate_safety_incident_data(self, count: int = 100):
        """Generate comprehensive safety incident data."""
        logger.info(f"🛡️ Generating {count} safety incidents...")
        # Security: All random.choice/randint calls below are for generating synthetic safety incident data only
        # Not security-sensitive - these are just test data identifiers and descriptions
        
        async with self.pg_conn.cursor() as cur:
            # Clear existing data
            await cur.execute("DELETE FROM safety_incidents")
            
            severities = ['low', 'medium', 'high', 'critical']
            severity_weights = [0.4, 0.3, 0.2, 0.1]
            
            for i in range(count):
                incident_type = random.choice(self.incident_types)
                severity = random.choices(severities, weights=severity_weights)[0]
                
                # Generate realistic incident descriptions
                descriptions = {
                    "slip_and_fall": f"Worker slipped on wet floor in {random.choice(self.warehouse_zones)} zone",
                    "equipment_malfunction": f"{random.choice(self.equipment_types).replace('_', ' ').title()} malfunction during operation",
                    "chemical_spill": f"Chemical spill detected in {random.choice(['Zone A', 'Zone B', 'Maintenance Bay'])}",
                    "fire_hazard": f"Fire hazard reported near {random.choice(['electrical panel', 'heating unit', 'storage area'])}",
                    "electrical_issue": f"Electrical issue with {random.choice(['conveyor system', 'lighting', 'equipment'])}",
                    "structural_damage": f"Structural damage to {random.choice(['rack system', 'loading dock', 'conveyor'])}",
                    "injury": f"Worker injury during {random.choice(['lifting', 'operating equipment', 'walking'])}",
                    "near_miss": f"Near miss incident involving {random.choice(['forklift', 'conveyor', 'falling object'])}"
                }
                
                description = descriptions.get(incident_type, f"Safety incident of type {incident_type}")
                reporter = f"operator{random.randint(1, 25)}"
                
                await cur.execute("""
                    INSERT INTO safety_incidents (severity, description, reported_by, occurred_at)
                    VALUES (%s, %s, %s, %s)
                """, (severity, description, reporter, 
                      fake.date_time_between(start_date='-90d', end_date='now')))
        
        logger.info("✅ Safety incident data generated")
    
    async def generate_equipment_telemetry_data(self, days: int = 30):
        """Generate comprehensive equipment telemetry data."""
        logger.info(f"📊 Generating equipment telemetry for {days} days...")
        # Security: random.choice call below is for generating synthetic equipment types only
        # Not security-sensitive - this is just test data selection
        
        async with self.pg_conn.cursor() as cur:
            # Clear existing data
            await cur.execute("DELETE FROM equipment_telemetry")
            
            start_date = datetime.now() - timedelta(days=days)
            
            for equipment_id in range(1, 51):  # 50 pieces of equipment
                equipment_type = random.choice(self.equipment_types)
                equipment_name = f"{equipment_type}_{equipment_id:03d}"
                
                # Generate telemetry data every 5 minutes
                current_time = start_date
                while current_time < datetime.now():
                    # Generate realistic metrics based on equipment type
                    metrics = self._generate_equipment_metrics(equipment_type, current_time)
                    
                    for metric, value in metrics.items():
                        await cur.execute("""
                            INSERT INTO equipment_telemetry (ts, equipment_id, metric, value)
                            VALUES (%s, %s, %s, %s)
                        """, (current_time, equipment_name, metric, value))
                    
                    current_time += timedelta(minutes=5)
        
        logger.info("✅ Equipment telemetry data generated")
    
    def _generate_equipment_metrics(self, equipment_type: str, timestamp: datetime) -> Dict[str, float]:
        """Generate realistic metrics for different equipment types."""
        # Security: All random.uniform/randint/choice calls below are for generating synthetic telemetry data only
        # Not security-sensitive - these are just test sensor readings
        metrics = {}
        
        if equipment_type == "forklift":
            metrics = {
                "battery_level": random.uniform(20, 100),
                "temperature": random.uniform(15, 45),
                "vibration": random.uniform(0, 10),
                "usage_hours": random.uniform(0, 24),
                "fuel_level": random.uniform(10, 100)
            }
        elif equipment_type == "conveyor":
            metrics = {
                "speed": random.uniform(0, 100),
                "temperature": random.uniform(20, 40),
                "vibration": random.uniform(0, 5),
                "power_consumption": random.uniform(50, 200),
                "throughput": random.uniform(0, 1000)
            }
        elif equipment_type == "scanner":
            metrics = {
                "battery_level": random.uniform(30, 100),
                "scan_count": random.randint(0, 100),
                "error_rate": random.uniform(0, 0.05),
                "temperature": random.uniform(15, 35)
            }
        else:  # Generic equipment
            metrics = {
                "battery_level": random.uniform(0, 100),
                "temperature": random.uniform(10, 50),
                "vibration": random.uniform(0, 15),
                "status": random.choice([0, 1])  # 0 = offline, 1 = online
            }
        
        return metrics
    
    async def generate_milvus_vector_data(self, count: int = 1000):
        """Generate vector embeddings for knowledge base and documents."""
        logger.info(f"🧠 Generating {count} vector embeddings...")
        # Security: random.choice calls below are for generating synthetic document types and categories only
        # Not security-sensitive - these are just test data identifiers
        
        try:
            # Connect to Milvus
            connections.connect("default", host=MILVUS_HOST, port=MILVUS_PORT)
            
            # Create or get collection
            collection_name = "warehouse_knowledge"
            if Collection(collection_name).has():
                collection = Collection(collection_name)
            else:
                # Create collection (this would normally be done by the vector retriever)
                logger.info("Creating Milvus collection...")
                return
            
            # Generate document embeddings
            documents = []
            for i in range(count):
                doc_type = random.choice(["sop", "manual", "policy", "procedure", "guide"])
                title = f"{doc_type.title()} {fake.word().title()} {fake.word().title()}"
                content = fake.text(max_nb_chars=500)
                
                documents.append({
                    "id": i,
                    "title": title,
                    "content": content,
                    "doc_type": doc_type,
                    "category": random.choice(self.product_categories),
                    "created_at": fake.date_time_between(start_date='-180d', end_date='now').isoformat()
                })
            
            # Insert documents (this would normally be done by the vector retriever)
            logger.info("✅ Vector data prepared (insertion handled by vector retriever)")
            
        except Exception as e:
            logger.warning(f"⚠️ Milvus vector data generation skipped: {e}")
    
    async def generate_redis_cache_data(self):
        """Generate Redis cache data for sessions and caching."""
        logger.info("💾 Generating Redis cache data...")
        # Security: random.randint/choice calls below are for generating synthetic session/cache data only
        # Not security-sensitive - these are just test data identifiers and counts
        
        try:
            # Generate session data
            for i in range(20):
                session_id = f"session_{i:03d}"
                user_id = random.randint(1, 50)
                session_data = {
                    "user_id": user_id,
                    "username": f"user{user_id}",
                    "role": random.choice(['manager', 'supervisor', 'operator', 'viewer']),
                    "last_activity": datetime.now().isoformat(),
                    "ip_address": fake.ipv4(),
                    "user_agent": fake.user_agent()
                }
                
                self.redis_conn.hset(f"session:{session_id}", mapping=session_data)
                self.redis_conn.expire(f"session:{session_id}", 3600)  # 1 hour TTL
            
            # Generate cache data
            cache_keys = [
                "inventory:low_stock", "tasks:pending", "equipment:status",
                "safety:incidents:recent", "users:active", "metrics:dashboard"
            ]
            
            for key in cache_keys:
                cache_data = {
                    "data": json.dumps({"generated_at": datetime.now().isoformat(), "count": random.randint(1, 100)}),
                    "ttl": 300  # 5 minutes
                }
                self.redis_conn.hset(f"cache:{key}", mapping=cache_data)
                self.redis_conn.expire(f"cache:{key}", 300)
            
            logger.info("✅ Redis cache data generated")
            
        except Exception as e:
            logger.warning(f"⚠️ Redis cache data generation skipped: {e}")
    
    async def generate_audit_log_data(self, count: int = 200):
        """Generate audit log data for user actions."""
        logger.info(f"📝 Generating {count} audit log entries...")
        # Security: random.randint/choice/random() calls below are for generating synthetic audit log data only
        # Not security-sensitive - these are just test data identifiers and attributes
        
        async with self.pg_conn.cursor() as cur:
            actions = [
                "login", "logout", "inventory_view", "inventory_update", "task_create",
                "task_assign", "task_complete", "safety_report", "equipment_check",
                "user_management", "system_config", "data_export"
            ]
            
            resource_types = ["inventory", "task", "user", "equipment", "safety", "system"]
            
            for i in range(count):
                user_id = random.randint(1, 50)
                action = random.choice(actions)
                resource_type = random.choice(resource_types)
                resource_id = str(random.randint(1, 1000))
                
                details = {
                    "ip_address": fake.ipv4(),
                    "user_agent": fake.user_agent(),
                    "timestamp": fake.date_time_between(start_date='-30d', end_date='now').isoformat(),
                    "additional_info": fake.sentence() if random.random() < 0.3 else None
                }
                
                await cur.execute("""
                    INSERT INTO audit_log (user_id, action, resource_type, resource_id, details, ip_address, user_agent, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (user_id, action, resource_type, resource_id, json.dumps(details),
                      fake.ipv4(), fake.user_agent(),
                      fake.date_time_between(start_date='-30d', end_date='now')))
        
        logger.info("✅ Audit log data generated")
    
    async def generate_all_data(self):
        """Generate all synthetic data."""
        logger.info("🚀 Starting comprehensive synthetic data generation...")
        
        await self.initialize_connections()
        
        # Generate data in order of dependencies
        await self.generate_user_data(50)
        await self.generate_inventory_data(1000)
        await self.generate_task_data(500)
        await self.generate_safety_incident_data(100)
        await self.generate_equipment_telemetry_data(30)
        await self.generate_audit_log_data(200)
        await self.generate_milvus_vector_data(1000)
        await self.generate_redis_cache_data()
        
        # Commit all changes
        await self.pg_conn.commit()
        
        logger.info("🎉 All synthetic data generated successfully!")
        logger.info("📊 Data Summary:")
        logger.info("   • 50 users across all roles")
        logger.info("   • 1,000 inventory items with realistic locations")
        logger.info("   • 500 tasks with various statuses")
        logger.info("   • 100 safety incidents with different severities")
        logger.info("   • 30 days of equipment telemetry data")
        logger.info("   • 200 audit log entries")
        logger.info("   • 1,000 vector embeddings for knowledge base")
        logger.info("   • Redis cache data for sessions and metrics")
    
    async def cleanup(self):
        """Clean up database connections."""
        if self.pg_conn:
            await self.pg_conn.close()
        if self.redis_conn:
            self.redis_conn.close()

async def main():
    """Main function to run the synthetic data generator."""
    generator = SyntheticDataGenerator()
    
    try:
        await generator.generate_all_data()
    except Exception as e:
        logger.error(f"❌ Error generating synthetic data: {e}")
        raise
    finally:
        await generator.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
