#!/usr/bin/env python3
"""
Generate sample equipment telemetry data for testing.
"""

import asyncio
import asyncpg
import os
import random
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()


async def generate_telemetry_data():
    """Generate sample telemetry data for equipment."""
    conn = await asyncpg.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=int(os.getenv("PGPORT", "5435")),
        user=os.getenv("POSTGRES_USER", "warehouse"),
        password=os.getenv("POSTGRES_PASSWORD", "changeme"),
        database=os.getenv("POSTGRES_DB", "warehouse"),
    )

    try:
        # Get all equipment assets
        assets = await conn.fetch("SELECT asset_id, type FROM equipment_assets")
        
        if not assets:
            print("No equipment assets found. Please create equipment assets first.")
            return

        print(f"Generating telemetry data for {len(assets)} equipment assets...")

        # Clear existing telemetry data
        await conn.execute("DELETE FROM equipment_telemetry")
        print("Cleared existing telemetry data")

        # Generate telemetry for each asset
        for asset in assets:
            asset_id = asset["asset_id"]
            asset_type = asset["type"]

            # Generate metrics based on equipment type
            metrics = []
            if asset_type in ["forklift", "amr", "agv"]:
                metrics = [
                    ("battery_soc", 0, 100, "%"),
                    ("temp_c", 15, 35, "°C"),
                    ("speed", 0, 5, "m/s"),
                    ("location_x", 0, 200, "m"),
                    ("location_y", 0, 200, "m"),
                ]
            elif asset_type == "charger":
                metrics = [
                    ("temp_c", 20, 40, "°C"),
                    ("voltage", 40, 50, "V"),
                    ("current", 10, 20, "A"),
                    ("power", 400, 1000, "W"),
                ]
            elif asset_type == "scanner":
                metrics = [
                    ("battery_level", 50, 100, "%"),
                    ("signal_strength", 0, 100, "%"),
                    ("scan_count", 0, 1000, "count"),
                ]
            else:
                metrics = [
                    ("status", 0, 1, "binary"),
                    ("temp_c", 15, 35, "°C"),
                ]

            # Generate data points for the last 7 days, every hour
            start_time = datetime.now() - timedelta(days=7)
            current_time = start_time
            data_points = 0

            while current_time < datetime.now():
                for metric_name, min_val, max_val, unit in metrics:
                    # Generate realistic values with some variation
                    if metric_name == "battery_soc" or metric_name == "battery_level":
                        # Battery should generally decrease over time
                        base_value = 100 - (
                            (datetime.now() - current_time).total_seconds() / 3600 * 0.1
                        )
                        value = max(min_val, min(max_val, base_value + random.uniform(-5, 5)))
                    elif metric_name == "location_x" or metric_name == "location_y":
                        # Location should change gradually
                        value = random.uniform(min_val, max_val)
                    elif metric_name == "speed":
                        # Speed should be mostly 0 with occasional movement
                        value = random.uniform(0, max_val) if random.random() < 0.3 else 0.0
                    else:
                        value = random.uniform(min_val, max_val)

                    await conn.execute(
                        """
                        INSERT INTO equipment_telemetry (ts, equipment_id, metric, value)
                        VALUES ($1, $2, $3, $4)
                        """,
                        current_time,
                        asset_id,
                        metric_name,
                        value,
                    )
                    data_points += 1

                current_time += timedelta(hours=1)

            print(f"  ✅ {asset_id}: Generated {data_points} data points")

        # Verify data
        total_count = await conn.fetchval("SELECT COUNT(*) FROM equipment_telemetry")
        print(f"\n✅ Total telemetry records created: {total_count}")

    except Exception as e:
        print(f"❌ Error generating telemetry data: {e}")
        raise
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(generate_telemetry_data())

