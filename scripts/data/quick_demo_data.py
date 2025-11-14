#!/usr/bin/env python3
"""
Quick Demo Data Generator

Generates a smaller set of realistic demo data for quick testing and demos.
This is faster than the full synthetic data generator and perfect for demos.
"""

import asyncio
import random
import json
import logging
from datetime import datetime, timedelta
import psycopg
import bcrypt

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database connection settings
POSTGRES_DSN = "postgresql://warehouse:warehousepw@localhost:5435/warehouse"

class QuickDemoDataGenerator:
    """Generates quick demo data for warehouse operations."""
    
    def __init__(self):
        self.pg_conn = None
        
        # Demo warehouse configuration
        self.warehouse_zones = ["A", "B", "C", "D"]
        self.equipment_types = ["forklift", "pallet_jack", "conveyor", "scanner"]
        self.product_categories = ["Electronics", "Clothing", "Home & Garden", "Automotive", "Tools"]
        self.incident_types = ["slip_and_fall", "equipment_malfunction", "near_miss", "injury"]
        self.task_types = ["pick", "pack", "putaway", "cycle_count", "replenishment"]
    
    async def initialize_connection(self):
        """Initialize database connection."""
        try:
            self.pg_conn = await psycopg.AsyncConnection.connect(POSTGRES_DSN)
            logger.info("✅ Connected to PostgreSQL")
        except Exception as e:
            logger.error(f"❌ Failed to connect to PostgreSQL: {e}")
            raise
    
    async def generate_demo_inventory(self):
        """Generate demo inventory data."""
        logger.info("📦 Generating demo inventory data...")
        
        async with self.pg_conn.cursor() as cur:
            # Clear existing data
            await cur.execute("DELETE FROM inventory_items")
            
            # Generate realistic Frito-Lay products
            demo_items = [
                # Lay's Products
                ("LAY001", "Lay's Classic Potato Chips 9oz", 1250, "Zone A-Aisle 1-Rack 2-Level 3", 200),
                ("LAY002", "Lay's Barbecue Potato Chips 9oz", 980, "Zone A-Aisle 1-Rack 2-Level 2", 150),
                ("LAY003", "Lay's Salt & Vinegar Potato Chips 9oz", 750, "Zone A-Aisle 1-Rack 2-Level 1", 120),
                ("LAY004", "Lay's Sour Cream & Onion Potato Chips 9oz", 890, "Zone A-Aisle 1-Rack 3-Level 3", 140),
                ("LAY005", "Lay's Limón Potato Chips 9oz", 420, "Zone A-Aisle 1-Rack 3-Level 2", 80),
                
                # Doritos Products
                ("DOR001", "Doritos Nacho Cheese Tortilla Chips 9.75oz", 1120, "Zone A-Aisle 2-Rack 1-Level 3", 180),
                ("DOR002", "Doritos Cool Ranch Tortilla Chips 9.75oz", 890, "Zone A-Aisle 2-Rack 1-Level 2", 140),
                ("DOR003", "Doritos Spicy Nacho Tortilla Chips 9.75oz", 680, "Zone A-Aisle 2-Rack 1-Level 1", 110),
                ("DOR004", "Doritos Flamin' Hot Nacho Tortilla Chips 9.75oz", 520, "Zone A-Aisle 2-Rack 2-Level 3", 85),
                
                # Cheetos Products
                ("CHE001", "Cheetos Crunchy Cheese Flavored Snacks 8.5oz", 750, "Zone A-Aisle 3-Rack 2-Level 3", 120),
                ("CHE002", "Cheetos Puffs Cheese Flavored Snacks 8.5oz", 680, "Zone A-Aisle 3-Rack 2-Level 2", 110),
                ("CHE003", "Cheetos Flamin' Hot Crunchy Snacks 8.5oz", 480, "Zone A-Aisle 3-Rack 2-Level 1", 80),
                ("CHE004", "Cheetos White Cheddar Puffs 8.5oz", 320, "Zone A-Aisle 3-Rack 3-Level 3", 60),
                
                # Tostitos Products
                ("TOS001", "Tostitos Original Restaurant Style Tortilla Chips 13oz", 420, "Zone B-Aisle 1-Rack 3-Level 1", 80),
                ("TOS002", "Tostitos Scoops Tortilla Chips 10oz", 380, "Zone B-Aisle 1-Rack 3-Level 2", 70),
                ("TOS003", "Tostitos Hint of Lime Tortilla Chips 10oz", 290, "Zone B-Aisle 1-Rack 3-Level 3", 55),
                ("TOS004", "Tostitos Chunky Salsa Medium 16oz", 180, "Zone B-Aisle 1-Rack 4-Level 1", 40),
                
                # Fritos Products
                ("FRI001", "Fritos Original Corn Chips 9.25oz", 320, "Zone B-Aisle 2-Rack 1-Level 1", 60),
                ("FRI002", "Fritos Chili Cheese Corn Chips 9.25oz", 280, "Zone B-Aisle 2-Rack 1-Level 2", 50),
                ("FRI003", "Fritos Honey BBQ Corn Chips 9.25oz", 190, "Zone B-Aisle 2-Rack 1-Level 3", 35),
                
                # Ruffles Products
                ("RUF001", "Ruffles Original Potato Chips 9oz", 450, "Zone B-Aisle 3-Rack 2-Level 1", 85),
                ("RUF002", "Ruffles Cheddar & Sour Cream Potato Chips 9oz", 390, "Zone B-Aisle 3-Rack 2-Level 2", 75),
                ("RUF003", "Ruffles All Dressed Potato Chips 9oz", 280, "Zone B-Aisle 3-Rack 2-Level 3", 50),
                
                # SunChips Products
                ("SUN001", "SunChips Original Multigrain Snacks 7oz", 180, "Zone C-Aisle 1-Rack 1-Level 1", 40),
                ("SUN002", "SunChips Harvest Cheddar Multigrain Snacks 7oz", 160, "Zone C-Aisle 1-Rack 1-Level 2", 35),
                ("SUN003", "SunChips French Onion Multigrain Snacks 7oz", 120, "Zone C-Aisle 1-Rack 1-Level 3", 25),
                
                # PopCorners Products
                ("POP001", "PopCorners Sea Salt Popcorn Chips 5oz", 95, "Zone C-Aisle 2-Rack 2-Level 1", 25),
                ("POP002", "PopCorners White Cheddar Popcorn Chips 5oz", 85, "Zone C-Aisle 2-Rack 2-Level 2", 20),
                ("POP003", "PopCorners Sweet & Salty Kettle Corn Chips 5oz", 65, "Zone C-Aisle 2-Rack 2-Level 3", 15),
                
                # Funyuns Products
                ("FUN001", "Funyuns Onion Flavored Rings 6oz", 140, "Zone C-Aisle 3-Rack 1-Level 1", 30),
                ("FUN002", "Funyuns Flamin' Hot Onion Flavored Rings 6oz", 95, "Zone C-Aisle 3-Rack 1-Level 2", 20),
                
                # Smartfood Products
                ("SMA001", "Smartfood White Cheddar Popcorn 6.75oz", 110, "Zone C-Aisle 4-Rack 1-Level 1", 25),
                ("SMA002", "Smartfood Delight Sea Salt Popcorn 6oz", 85, "Zone C-Aisle 4-Rack 1-Level 2", 18),
                
                # Low stock items (below reorder point for alerts)
                ("LAY006", "Lay's Kettle Cooked Original Potato Chips 8.5oz", 15, "Zone A-Aisle 1-Rack 4-Level 1", 25),
                ("DOR005", "Doritos Dinamita Chile Limón Rolled Tortilla Chips 4.5oz", 8, "Zone A-Aisle 2-Rack 3-Level 1", 15),
                ("CHE005", "Cheetos Mac 'n Cheese Crunchy Snacks 4oz", 12, "Zone A-Aisle 3-Rack 4-Level 1", 20),
                ("TOS005", "Tostitos Artisan Recipes Fire Roasted Chipotle Tortilla Chips 10oz", 5, "Zone B-Aisle 1-Rack 5-Level 1", 15),
                ("FRI004", "Fritos Scoops Corn Chips 9.25oz", 3, "Zone B-Aisle 2-Rack 2-Level 1", 10),
            ]
            
            for sku, name, quantity, location, reorder_point in demo_items:
                await cur.execute("""
                    INSERT INTO inventory_items (sku, name, quantity, location, reorder_point, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (sku, name, quantity, location, reorder_point, datetime.now()))
        
        logger.info("✅ Demo inventory data generated")
    
    async def generate_demo_users(self):
        """Generate demo user data."""
        logger.info("👥 Generating demo user data...")
        
        async with self.pg_conn.cursor() as cur:
            # Clear existing data
            await cur.execute("DELETE FROM user_sessions")
            await cur.execute("DELETE FROM audit_log")
            await cur.execute("DELETE FROM users WHERE username != 'admin'")
            
            # Generate demo users
            demo_users = [
                ("manager1", "manager1@warehouse.com", "Sarah Johnson", "manager"),
                ("manager2", "manager2@warehouse.com", "Michael Chen", "manager"),
                ("supervisor1", "supervisor1@warehouse.com", "Emily Rodriguez", "supervisor"),
                ("supervisor2", "supervisor2@warehouse.com", "David Kim", "supervisor"),
                ("supervisor3", "supervisor3@warehouse.com", "Lisa Wang", "supervisor"),
                ("operator1", "operator1@warehouse.com", "James Wilson", "operator"),
                ("operator2", "operator2@warehouse.com", "Maria Garcia", "operator"),
                ("operator3", "operator3@warehouse.com", "Robert Brown", "operator"),
                ("operator4", "operator4@warehouse.com", "Jennifer Davis", "operator"),
                ("operator5", "operator5@warehouse.com", "Christopher Lee", "operator"),
                ("viewer1", "viewer1@warehouse.com", "Amanda Taylor", "viewer"),
                ("viewer2", "viewer2@warehouse.com", "Daniel Martinez", "viewer"),
            ]
            
            hashed_password = bcrypt.hashpw("password123".encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            
            for username, email, full_name, role in demo_users:
                await cur.execute("""
                    INSERT INTO users (username, email, full_name, role, status, hashed_password, created_at, last_login)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (username, email, full_name, role, 'active', hashed_password,
                      datetime.now() - timedelta(days=30),
                      datetime.now() - timedelta(hours=random.randint(1, 24))))
        
        logger.info("✅ Demo user data generated")
    
    async def generate_demo_tasks(self):
        """Generate demo task data."""
        logger.info("📋 Generating demo task data...")
        
        async with self.pg_conn.cursor() as cur:
            # Clear existing data
            await cur.execute("DELETE FROM tasks")
            
            # Generate demo tasks
            demo_tasks = [
                ("pick", "in_progress", "operator1", {
                    "priority": "high",
                    "zone": "A",
                    "order_id": "ORD1001",
                    "items": [{"sku": "SKU001", "qty": 2}, {"sku": "SKU003", "qty": 1}]
                }),
                ("pack", "pending", None, {
                    "priority": "medium",
                    "zone": "B",
                    "order_id": "ORD1002",
                    "estimated_duration": 30
                }),
                ("putaway", "completed", "operator2", {
                    "priority": "low",
                    "zone": "C",
                    "items": [{"sku": "SKU005", "qty": 10}]
                }),
                ("cycle_count", "in_progress", "operator3", {
                    "priority": "medium",
                    "zone": "D",
                    "location": "Zone D-Aisle 1",
                    "expected_count": 25
                }),
                ("replenishment", "pending", None, {
                    "priority": "high",
                    "zone": "A",
                    "items": [{"sku": "SKU021", "qty": 5}]
                }),
                ("pick", "completed", "operator4", {
                    "priority": "medium",
                    "zone": "B",
                    "order_id": "ORD1003",
                    "items": [{"sku": "SKU007", "qty": 1}]
                }),
                ("pack", "in_progress", "operator5", {
                    "priority": "high",
                    "zone": "C",
                    "order_id": "ORD1004",
                    "estimated_duration": 45
                }),
                ("inspection", "pending", None, {
                    "priority": "low",
                    "zone": "D",
                    "equipment": "forklift_001"
                }),
            ]
            
            for task_type, status, assignee, payload in demo_tasks:
                await cur.execute("""
                    INSERT INTO tasks (kind, status, assignee, payload, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (task_type, status, assignee, json.dumps(payload),
                      datetime.now() - timedelta(hours=random.randint(1, 48)),
                      datetime.now() - timedelta(hours=random.randint(0, 24))))
        
        logger.info("✅ Demo task data generated")
    
    async def generate_demo_safety_incidents(self):
        """Generate demo safety incident data."""
        logger.info("🛡️ Generating demo safety incident data...")
        
        async with self.pg_conn.cursor() as cur:
            # Clear existing data
            await cur.execute("DELETE FROM safety_incidents")
            
            # Generate demo safety incidents
            demo_incidents = [
                ("medium", "Worker slipped on wet floor in Zone A", "operator1"),
                ("high", "Forklift malfunction during operation", "supervisor1"),
                ("low", "Near miss incident involving conveyor belt", "operator2"),
                ("critical", "Chemical spill detected in Zone B", "manager1"),
                ("medium", "Electrical issue with lighting system", "operator3"),
                ("low", "Minor injury during lifting operation", "operator4"),
                ("high", "Fire hazard reported near heating unit", "supervisor2"),
                ("medium", "Structural damage to rack system", "operator5"),
            ]
            
            for severity, description, reporter in demo_incidents:
                await cur.execute("""
                    INSERT INTO safety_incidents (severity, description, reported_by, occurred_at)
                    VALUES (%s, %s, %s, %s)
                """, (severity, description, reporter,
                      datetime.now() - timedelta(days=random.randint(1, 30))))
        
        logger.info("✅ Demo safety incident data generated")
    
    async def generate_demo_equipment_telemetry(self):
        """Generate demo equipment telemetry data."""
        logger.info("📊 Generating demo equipment telemetry data...")
        
        async with self.pg_conn.cursor() as cur:
            # Clear existing data
            await cur.execute("DELETE FROM equipment_telemetry")
            
            # Generate telemetry for last 7 days
            equipment_list = [
                "forklift_001", "forklift_002", "pallet_jack_001", "conveyor_001",
                "scanner_001", "scanner_002", "printer_001", "crane_001"
            ]
            
            start_time = datetime.now() - timedelta(days=7)
            
            for equipment_id in equipment_list:
                current_time = start_time
                while current_time < datetime.now():
                    # Generate realistic metrics
                    metrics = {
                        "battery_level": random.uniform(20, 100),
                        "temperature": random.uniform(15, 45),
                        "vibration": random.uniform(0, 10),
                        "status": random.choice([0, 1])
                    }
                    
                    for metric, value in metrics.items():
                        await cur.execute("""
                            INSERT INTO equipment_telemetry (ts, equipment_id, metric, value)
                            VALUES (%s, %s, %s, %s)
                        """, (current_time, equipment_id, metric, value))
                    
                    current_time += timedelta(hours=1)
        
        logger.info("✅ Demo equipment telemetry data generated")
    
    async def generate_demo_audit_log(self):
        """Generate demo audit log data."""
        logger.info("📝 Generating demo audit log data...")
        
        async with self.pg_conn.cursor() as cur:
            # Clear existing data
            await cur.execute("DELETE FROM audit_log")
            
            # Generate demo audit log entries
            actions = ["login", "logout", "inventory_view", "task_create", "safety_report", "equipment_check"]
            resource_types = ["inventory", "task", "user", "equipment", "safety"]
            
            # Get the actual user IDs from the database
            await cur.execute("SELECT id FROM users ORDER BY id")
            user_ids = [row[0] for row in await cur.fetchall()]
            
            for i in range(50):
                user_id = random.choice(user_ids)
                action = random.choice(actions)
                resource_type = random.choice(resource_types)
                resource_id = str(random.randint(1, 100))
                
                details = {
                    "ip_address": f"192.168.1.{random.randint(100, 200)}",
                    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "timestamp": (datetime.now() - timedelta(hours=random.randint(1, 168))).isoformat()
                }
                
                await cur.execute("""
                    INSERT INTO audit_log (user_id, action, resource_type, resource_id, details, ip_address, user_agent, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (user_id, action, resource_type, resource_id, json.dumps(details),
                      f"192.168.1.{random.randint(100, 200)}",
                      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                      datetime.now() - timedelta(hours=random.randint(1, 168))))
        
        logger.info("✅ Demo audit log data generated")
    
    async def generate_all_demo_data(self):
        """Generate all demo data."""
        logger.info("🚀 Starting quick demo data generation...")
        
        await self.initialize_connection()
        
        # Generate data in order of dependencies
        await self.generate_demo_users()
        await self.generate_demo_inventory()
        await self.generate_demo_tasks()
        await self.generate_demo_safety_incidents()
        await self.generate_demo_equipment_telemetry()
        await self.generate_demo_audit_log()
        
        # Commit all changes
        await self.pg_conn.commit()
        
        logger.info("🎉 Demo data generation completed successfully!")
        logger.info("📊 Demo Data Summary:")
        logger.info("   • 12 users across all roles")
        logger.info("   • 35 Frito-Lay products (including low stock alerts)")
        logger.info("   • 8 tasks with various statuses")
        logger.info("   • 8 safety incidents with different severities")
        logger.info("   • 7 days of equipment telemetry data")
        logger.info("   • 50 audit log entries")
        logger.info("")
        logger.info("🚀 Your warehouse is ready for a quick demo!")
    
    async def cleanup(self):
        """Clean up database connection."""
        if self.pg_conn:
            await self.pg_conn.close()

async def main():
    """Main function to run the demo data generator."""
    generator = QuickDemoDataGenerator()
    
    try:
        await generator.generate_all_demo_data()
    except Exception as e:
        logger.error(f"❌ Error generating demo data: {e}")
        raise
    finally:
        await generator.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
