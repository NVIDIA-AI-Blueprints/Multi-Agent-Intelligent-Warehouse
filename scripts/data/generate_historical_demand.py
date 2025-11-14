#!/usr/bin/env python3
"""
Frito-Lay Historical Demand Data Generator

Generates realistic historical inventory movement data for all Frito-Lay products
with seasonal patterns, promotional spikes, and brand-specific characteristics.
"""

import asyncio
import asyncpg
import random
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import logging
from dataclasses import dataclass
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class ProductProfile:
    """Product demand characteristics"""
    sku: str
    name: str
    base_daily_demand: float
    seasonality_strength: float  # 0-1, how much seasonal variation
    promotional_sensitivity: float  # 0-1, how much promotions affect demand
    weekend_boost: float  # Multiplier for weekends
    brand_category: str  # 'premium', 'mainstream', 'value', 'specialty'

class FritoLayDemandGenerator:
    """Generates realistic demand patterns for Frito-Lay products"""
    
    def __init__(self):
        self.pg_conn = None
        
        # Brand-specific characteristics based on Frito-Lay market data
        self.brand_profiles = {
            'LAY': ProductProfile(
                sku='LAY', name='Lay\'s', base_daily_demand=45.0,
                seasonality_strength=0.6, promotional_sensitivity=0.7,
                weekend_boost=1.3, brand_category='mainstream'
            ),
            'DOR': ProductProfile(
                sku='DOR', name='Doritos', base_daily_demand=40.0,
                seasonality_strength=0.8, promotional_sensitivity=0.9,
                weekend_boost=1.5, brand_category='premium'
            ),
            'CHE': ProductProfile(
                sku='CHE', name='Cheetos', base_daily_demand=35.0,
                seasonality_strength=0.5, promotional_sensitivity=0.6,
                weekend_boost=1.2, brand_category='mainstream'
            ),
            'TOS': ProductProfile(
                sku='TOS', name='Tostitos', base_daily_demand=25.0,
                seasonality_strength=0.9, promotional_sensitivity=0.8,
                weekend_boost=1.8, brand_category='premium'
            ),
            'FRI': ProductProfile(
                sku='FRI', name='Fritos', base_daily_demand=20.0,
                seasonality_strength=0.4, promotional_sensitivity=0.5,
                weekend_boost=1.1, brand_category='value'
            ),
            'RUF': ProductProfile(
                sku='RUF', name='Ruffles', base_daily_demand=30.0,
                seasonality_strength=0.6, promotional_sensitivity=0.7,
                weekend_boost=1.3, brand_category='mainstream'
            ),
            'SUN': ProductProfile(
                sku='SUN', name='SunChips', base_daily_demand=15.0,
                seasonality_strength=0.7, promotional_sensitivity=0.6,
                weekend_boost=1.2, brand_category='specialty'
            ),
            'POP': ProductProfile(
                sku='POP', name='PopCorners', base_daily_demand=12.0,
                seasonality_strength=0.5, promotional_sensitivity=0.7,
                weekend_boost=1.1, brand_category='specialty'
            ),
            'FUN': ProductProfile(
                sku='FUN', name='Funyuns', base_daily_demand=18.0,
                seasonality_strength=0.6, promotional_sensitivity=0.8,
                weekend_boost=1.4, brand_category='mainstream'
            ),
            'SMA': ProductProfile(
                sku='SMA', name='Smartfood', base_daily_demand=10.0,
                seasonality_strength=0.4, promotional_sensitivity=0.5,
                weekend_boost=1.1, brand_category='specialty'
            )
        }
        
        # Seasonal patterns (monthly multipliers)
        self.seasonal_patterns = {
            'mainstream': [0.8, 0.7, 0.9, 1.1, 1.2, 1.3, 1.4, 1.3, 1.1, 1.0, 0.9, 0.8],
            'premium': [0.7, 0.6, 0.8, 1.0, 1.1, 1.2, 1.3, 1.2, 1.0, 0.9, 0.8, 0.7],
            'value': [0.9, 0.8, 1.0, 1.1, 1.2, 1.2, 1.3, 1.2, 1.1, 1.0, 0.9, 0.9],
            'specialty': [0.6, 0.5, 0.7, 0.9, 1.0, 1.1, 1.2, 1.1, 0.9, 0.8, 0.7, 0.6]
        }
        
        # Major promotional events
        self.promotional_events = [
            {'name': 'Super Bowl', 'date': '2025-02-09', 'impact': 2.5, 'duration': 7},
            {'name': 'March Madness', 'date': '2025-03-15', 'impact': 1.8, 'duration': 14},
            {'name': 'Memorial Day', 'date': '2025-05-26', 'impact': 1.6, 'duration': 5},
            {'name': 'Fourth of July', 'date': '2025-07-04', 'impact': 2.0, 'duration': 7},
            {'name': 'Labor Day', 'date': '2025-09-01', 'impact': 1.5, 'duration': 5},
            {'name': 'Halloween', 'date': '2025-10-31', 'impact': 1.4, 'duration': 10},
            {'name': 'Thanksgiving', 'date': '2025-11-27', 'impact': 1.7, 'duration': 7},
            {'name': 'Christmas', 'date': '2025-12-25', 'impact': 1.9, 'duration': 14},
            {'name': 'New Year', 'date': '2026-01-01', 'impact': 1.3, 'duration': 5}
        ]

    async def create_movements_table(self):
        """Create inventory_movements table if it doesn't exist"""
        logger.info("🔧 Creating inventory_movements table...")
        
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS inventory_movements (
            id SERIAL PRIMARY KEY,
            sku TEXT NOT NULL,
            movement_type TEXT NOT NULL CHECK (movement_type IN ('inbound', 'outbound', 'adjustment')),
            quantity INTEGER NOT NULL,
            timestamp TIMESTAMPTZ NOT NULL,
            location TEXT,
            notes TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        
        CREATE INDEX IF NOT EXISTS idx_inventory_movements_sku ON inventory_movements(sku);
        CREATE INDEX IF NOT EXISTS idx_inventory_movements_timestamp ON inventory_movements(timestamp);
        CREATE INDEX IF NOT EXISTS idx_inventory_movements_type ON inventory_movements(movement_type);
        CREATE INDEX IF NOT EXISTS idx_inventory_movements_sku_timestamp ON inventory_movements(sku, timestamp);
        """
        
        await self.pg_conn.execute(create_table_sql)
        logger.info("✅ inventory_movements table created")

    async def initialize_connection(self):
        """Initialize database connection"""
        try:
            self.pg_conn = await asyncpg.connect(
                host="localhost",
                port=5435,
                user="warehouse",
                password="warehousepw",
                database="warehouse"
            )
            logger.info("✅ Connected to PostgreSQL")
        except Exception as e:
            logger.error(f"❌ Failed to connect to PostgreSQL: {e}")
            raise

    async def get_all_products(self) -> List[Dict]:
        """Get all Frito-Lay products from inventory"""
        try:
            query = "SELECT sku, name, quantity, location, reorder_point FROM inventory_items ORDER BY sku"
            products = await self.pg_conn.fetch(query)
            return [dict(product) for product in products]
        except Exception as e:
            logger.error(f"Error fetching products: {e}")
            return []

    def calculate_daily_demand(self, product: Dict, profile: ProductProfile, date: datetime) -> int:
        """Calculate realistic daily demand for a product"""
        
        # Base demand
        base_demand = profile.base_daily_demand
        
        # Add product-specific variation (±20%)
        product_variation = random.uniform(0.8, 1.2)
        
        # Weekend boost
        weekend_multiplier = 1.0
        if date.weekday() >= 5:  # Saturday or Sunday
            weekend_multiplier = profile.weekend_boost
        
        # Seasonal variation
        month = date.month - 1  # 0-indexed
        seasonal_multiplier = self.seasonal_patterns[profile.brand_category][month]
        seasonal_effect = 1.0 + (seasonal_multiplier - 1.0) * profile.seasonality_strength
        
        # Promotional effects
        promotional_multiplier = self.get_promotional_effect(date, profile)
        
        # Random daily variation (±15%)
        daily_variation = random.uniform(0.85, 1.15)
        
        # Calculate final demand
        final_demand = (
            base_demand * 
            product_variation * 
            weekend_multiplier * 
            seasonal_effect * 
            promotional_multiplier * 
            daily_variation
        )
        
        # Ensure minimum demand of 1
        return max(1, int(round(final_demand)))

    def get_promotional_effect(self, date: datetime, profile: ProductProfile) -> float:
        """Calculate promotional effect for a given date"""
        promotional_multiplier = 1.0
        
        for event in self.promotional_events:
            event_date = datetime.strptime(event['date'], '%Y-%m-%d')
            days_diff = (date - event_date).days
            
            # Check if date is within promotional period
            if 0 <= days_diff < event['duration']:
                # Calculate promotional impact based on product sensitivity
                impact = event['impact'] * profile.promotional_sensitivity
                
                # Decay effect over time
                decay_factor = 1.0 - (days_diff / event['duration']) * 0.5
                promotional_multiplier = max(1.0, impact * decay_factor)
                break
        
        return promotional_multiplier

    async def generate_historical_movements(self, days_back: int = 180):
        """Generate historical inventory movements for all products"""
        logger.info(f"📊 Generating {days_back} days of historical data...")
        
        products = await self.get_all_products()
        logger.info(f"Found {len(products)} products to process")
        
        movements = []
        start_date = datetime.now() - timedelta(days=days_back)
        
        for product in products:
            sku = product['sku']
            brand = sku[:3]
            
            if brand not in self.brand_profiles:
                logger.warning(f"Unknown brand {brand} for SKU {sku}")
                continue
                
            profile = self.brand_profiles[brand]
            
            # Generate daily movements
            for day_offset in range(days_back):
                current_date = start_date + timedelta(days=day_offset)
                
                # Calculate daily demand
                daily_demand = self.calculate_daily_demand(product, profile, current_date)
                
                # Add some inbound movements (restocking)
                if random.random() < 0.1:  # 10% chance of inbound movement
                    inbound_quantity = random.randint(50, 200)
                    movements.append({
                        'sku': sku,
                        'movement_type': 'inbound',
                        'quantity': inbound_quantity,
                        'timestamp': current_date,
                        'location': product['location'],
                        'notes': f'Restock delivery'
                    })
                
                # Add outbound movements (demand/consumption)
                movements.append({
                    'sku': sku,
                    'movement_type': 'outbound',
                    'quantity': daily_demand,
                    'timestamp': current_date,
                    'location': product['location'],
                    'notes': f'Daily demand consumption'
                })
                
                # Add occasional adjustments
                if random.random() < 0.02:  # 2% chance of adjustment
                    adjustment = random.randint(-5, 5)
                    if adjustment != 0:
                        movements.append({
                            'sku': sku,
                            'movement_type': 'adjustment',
                            'quantity': abs(adjustment),
                            'timestamp': current_date,
                            'location': product['location'],
                            'notes': f'Inventory adjustment: {"+" if adjustment > 0 else "-"}'
                        })
        
        logger.info(f"Generated {len(movements)} total movements")
        return movements

    async def store_movements(self, movements: List[Dict]):
        """Store movements in the database"""
        logger.info("💾 Storing movements in database...")
        
        try:
            # Clear existing movements
            await self.pg_conn.execute("DELETE FROM inventory_movements")
            
            # Insert new movements in batches
            batch_size = 1000
            for i in range(0, len(movements), batch_size):
                batch = movements[i:i + batch_size]
                
                values = []
                for movement in batch:
                    values.append((
                        movement['sku'],
                        movement['movement_type'],
                        movement['quantity'],
                        movement['timestamp'],
                        movement['location'],
                        movement['notes']
                    ))
                
                await self.pg_conn.executemany("""
                    INSERT INTO inventory_movements 
                    (sku, movement_type, quantity, timestamp, location, notes)
                    VALUES ($1, $2, $3, $4, $5, $6)
                """, values)
                
                logger.info(f"Stored batch {i//batch_size + 1}/{(len(movements)-1)//batch_size + 1}")
            
            logger.info("✅ All movements stored successfully")
            
        except Exception as e:
            logger.error(f"❌ Error storing movements: {e}")
            raise

    async def generate_demand_summary(self, movements: List[Dict]) -> Dict:
        """Generate summary statistics for the historical data"""
        logger.info("📈 Generating demand summary...")
        
        summary = {
            'total_movements': len(movements),
            'date_range': {
                'start': min(m['timestamp'] for m in movements),
                'end': max(m['timestamp'] for m in movements)
            },
            'products': {},
            'brand_performance': {},
            'seasonal_patterns': {},
            'promotional_impact': {}
        }
        
        # Group by SKU
        by_sku = {}
        for movement in movements:
            sku = movement['sku']
            if sku not in by_sku:
                by_sku[sku] = []
            by_sku[sku].append(movement)
        
        # Calculate product statistics
        for sku, sku_movements in by_sku.items():
            outbound_movements = [m for m in sku_movements if m['movement_type'] == 'outbound']
            total_demand = sum(m['quantity'] for m in outbound_movements)
            avg_daily_demand = total_demand / len(outbound_movements) if outbound_movements else 0
            
            summary['products'][sku] = {
                'total_demand': total_demand,
                'avg_daily_demand': round(avg_daily_demand, 2),
                'movement_count': len(sku_movements),
                'demand_variability': self.calculate_variability(outbound_movements)
            }
        
        # Calculate brand performance
        brand_totals = {}
        for sku, stats in summary['products'].items():
            brand = sku[:3]
            if brand not in brand_totals:
                brand_totals[brand] = {'total_demand': 0, 'product_count': 0}
            brand_totals[brand]['total_demand'] += stats['total_demand']
            brand_totals[brand]['product_count'] += 1
        
        for brand, totals in brand_totals.items():
            summary['brand_performance'][brand] = {
                'total_demand': totals['total_demand'],
                'avg_demand_per_product': round(totals['total_demand'] / totals['product_count'], 2),
                'product_count': totals['product_count']
            }
        
        return summary

    def calculate_variability(self, movements: List[Dict]) -> float:
        """Calculate demand variability (coefficient of variation)"""
        if len(movements) < 2:
            return 0.0
        
        quantities = [m['quantity'] for m in movements]
        mean_qty = np.mean(quantities)
        std_qty = np.std(quantities)
        
        return round(std_qty / mean_qty, 3) if mean_qty > 0 else 0.0

    async def run(self, days_back: int = 180):
        """Main execution method"""
        logger.info("🚀 Starting Frito-Lay historical data generation...")
        
        try:
            await self.initialize_connection()
            
            # Create the movements table
            await self.create_movements_table()
            
            # Generate historical movements
            movements = await self.generate_historical_movements(days_back)
            
            # Store in database
            await self.store_movements(movements)
            
            # Generate summary
            summary = await self.generate_demand_summary(movements)
            
            # Save summary to file
            with open('historical_demand_summary.json', 'w') as f:
                json.dump(summary, f, indent=2, default=str)
            
            logger.info("🎉 Historical data generation completed successfully!")
            logger.info(f"📊 Summary:")
            logger.info(f"   • Total movements: {summary['total_movements']:,}")
            logger.info(f"   • Products processed: {len(summary['products'])}")
            logger.info(f"   • Date range: {summary['date_range']['start'].strftime('%Y-%m-%d')} to {summary['date_range']['end'].strftime('%Y-%m-%d')}")
            logger.info(f"   • Brands: {', '.join(summary['brand_performance'].keys())}")
            
            # Show top performing products
            top_products = sorted(
                summary['products'].items(), 
                key=lambda x: x[1]['total_demand'], 
                reverse=True
            )[:5]
            
            logger.info("🏆 Top 5 products by total demand:")
            for sku, stats in top_products:
                logger.info(f"   • {sku}: {stats['total_demand']:,} units ({stats['avg_daily_demand']:.1f} avg/day)")
            
        except Exception as e:
            logger.error(f"❌ Error in data generation: {e}")
            raise
        finally:
            if self.pg_conn:
                await self.pg_conn.close()

async def main():
    """Main entry point"""
    generator = FritoLayDemandGenerator()
    await generator.run(days_back=180)

if __name__ == "__main__":
    asyncio.run(main())
