#!/usr/bin/env python3
"""
Phase 4 & 5: Advanced API Integration and Business Intelligence

Implements real-time forecasting endpoints, model monitoring,
business intelligence dashboards, and automated reorder recommendations.
"""

import asyncio
import asyncpg
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any
import json
import numpy as np
import pandas as pd
from dataclasses import dataclass
import os
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field, field_validator
# from src.api.services.forecasting_config import get_config, load_config_from_db
import redis
import asyncio
from enum import Enum

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Error message constants
ERROR_HORIZON_DAYS_MIN = "horizon_days must be at least 1"

# Pydantic models for API
class ForecastRequest(BaseModel):
    sku: str
    horizon_days: int = Field(default=30, ge=1, le=365, description="Forecast horizon in days (1-365)")
    include_confidence_intervals: bool = True
    include_feature_importance: bool = True
    
    @field_validator('horizon_days')
    @classmethod
    def validate_horizon_days(cls, v: int) -> int:
        """Validate and restrict horizon_days to prevent loop boundary injection attacks."""
        # Enforce maximum limit to prevent DoS attacks
        MAX_HORIZON_DAYS = 365
        if v > MAX_HORIZON_DAYS:
            logger.warning(f"horizon_days {v} exceeds maximum {MAX_HORIZON_DAYS}, restricting to {MAX_HORIZON_DAYS}")
            return MAX_HORIZON_DAYS
        if v < 1:
            raise ValueError(ERROR_HORIZON_DAYS_MIN)
        return v

class BatchForecastRequest(BaseModel):
    skus: List[str] = Field(..., min_length=1, max_length=100, description="List of SKUs to forecast (max 100)")
    horizon_days: int = Field(default=30, ge=1, le=365, description="Forecast horizon in days (1-365)")
    
    @field_validator('horizon_days')
    @classmethod
    def validate_horizon_days(cls, v: int) -> int:
        """Validate and restrict horizon_days to prevent loop boundary injection attacks."""
        # Enforce maximum limit to prevent DoS attacks
        MAX_HORIZON_DAYS = 365
        if v > MAX_HORIZON_DAYS:
            logger.warning(f"horizon_days {v} exceeds maximum {MAX_HORIZON_DAYS}, restricting to {MAX_HORIZON_DAYS}")
            return MAX_HORIZON_DAYS
        if v < 1:
            raise ValueError(ERROR_HORIZON_DAYS_MIN)
        return v
    
    @field_validator('skus')
    @classmethod
    def validate_skus(cls, v: List[str]) -> List[str]:
        """Validate and restrict SKU list size to prevent DoS attacks."""
        # Enforce maximum limit to prevent DoS attacks from large batch requests
        MAX_SKUS = 100
        if len(v) > MAX_SKUS:
            logger.warning(f"SKU list size {len(v)} exceeds maximum {MAX_SKUS}, restricting to first {MAX_SKUS} SKUs")
            return v[:MAX_SKUS]
        if len(v) == 0:
            raise ValueError("SKU list cannot be empty")
        return v

class ReorderRecommendation(BaseModel):
    sku: str
    current_stock: int
    recommended_order_quantity: int
    urgency_level: str
    reason: str
    confidence_score: float
    estimated_arrival_date: str

class ModelPerformanceMetrics(BaseModel):
    model_name: str
    accuracy_score: float
    mape: float
    last_training_date: str
    prediction_count: int
    drift_score: float
    status: str

class BusinessIntelligenceSummary(BaseModel):
    total_skus: int
    low_stock_items: int
    high_demand_items: int
    forecast_accuracy: float
    reorder_recommendations: int
    model_performance: List[ModelPerformanceMetrics]

# Router for advanced forecasting
router = APIRouter(prefix="/api/v1/forecasting", tags=["Advanced Forecasting"])

class AdvancedForecastingService:
    """Advanced forecasting service with business intelligence"""
    
    def __init__(self):
        self.pg_conn = None
        self.db_pool = None  # Add db_pool attribute for compatibility
        self.redis_client = None
        self.model_cache = {}
        self.config = None  # get_config()
        self.performance_metrics = {}
        
    async def initialize(self):
        """Initialize database and Redis connections"""
        try:
            # PostgreSQL connection
            self.pg_conn = await asyncpg.connect(
                host="localhost",
                port=5435,
                user="warehouse",
                password=os.getenv("POSTGRES_PASSWORD", ""),
                database="warehouse"
            )
            
            # Set db_pool to pg_conn for compatibility with model performance methods
            self.db_pool = self.pg_conn
            
            # Redis connection for caching
            self.redis_client = redis.Redis(host='localhost', port=6379, db=0)
            
            logger.info("✅ Advanced forecasting service initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize forecasting service: {e}")
            raise

    async def get_real_time_forecast(self, sku: str, horizon_days: int = 30) -> Dict[str, Any]:
        """Get real-time forecast with caching"""
        # Security: Validate and restrict horizon_days to prevent loop boundary injection attacks
        MAX_HORIZON_DAYS = 365
        if horizon_days > MAX_HORIZON_DAYS:
            logger.warning(f"horizon_days {horizon_days} exceeds maximum {MAX_HORIZON_DAYS}, restricting to {MAX_HORIZON_DAYS}")
            horizon_days = MAX_HORIZON_DAYS
        if horizon_days < 1:
            raise ValueError(ERROR_HORIZON_DAYS_MIN)
        
        cache_key = f"forecast:{sku}:{horizon_days}"
        
        # Check cache first
        try:
            cached_forecast = self.redis_client.get(cache_key)
            if cached_forecast:
                logger.info(f"📊 Using cached forecast for {sku}")
                return json.loads(cached_forecast)
        except Exception as e:
            logger.warning(f"Cache read failed: {e}")
        
        # Generate new forecast
        logger.info(f"🔮 Generating real-time forecast for {sku}")
        
        try:
            # Get historical data
            query = f"""
            SELECT 
                DATE(timestamp) as date,
                SUM(quantity) as daily_demand,
                EXTRACT(DOW FROM DATE(timestamp)) as day_of_week,
                EXTRACT(MONTH FROM DATE(timestamp)) as month,
                CASE 
                    WHEN EXTRACT(DOW FROM DATE(timestamp)) IN (0, 6) THEN 1 
                    ELSE 0 
                END as is_weekend,
                CASE 
                    WHEN EXTRACT(MONTH FROM DATE(timestamp)) IN (6, 7, 8) THEN 1 
                    ELSE 0 
                END as is_summer
            FROM inventory_movements 
            WHERE sku = $1 
                AND movement_type = 'outbound'
                AND timestamp >= NOW() - INTERVAL '180 days'
            GROUP BY DATE(timestamp)
            ORDER BY date
            """
            
            results = await self.pg_conn.fetch(query, sku)
            
            if not results:
                raise ValueError(f"No historical data found for SKU {sku}")
            
            df = pd.DataFrame([dict(row) for row in results])
            df = df.sort_values('date').reset_index(drop=True)
            
            # Simple forecasting logic (can be replaced with advanced models)
            recent_demand = df['daily_demand'].tail(30).mean()
            seasonal_factor = 1.0
            
            # Apply seasonal adjustments
            if df['is_summer'].iloc[-1] == 1:
                seasonal_factor = 1.2  # 20% increase in summer
            elif df['is_weekend'].iloc[-1] == 1:
                seasonal_factor = 0.8  # 20% decrease on weekends
            
            # Generate forecast
            base_forecast = recent_demand * seasonal_factor
            predictions = [base_forecast * (1 + np.random.normal(0, 0.1)) for _ in range(horizon_days)]
            
            # Calculate confidence intervals
            std_dev = np.std(df['daily_demand'].tail(30))
            confidence_intervals = [
                (max(0, pred - 1.96 * std_dev), pred + 1.96 * std_dev)
                for pred in predictions
            ]
            
            forecast_result = {
                'sku': sku,
                'predictions': predictions,
                'confidence_intervals': confidence_intervals,
                'forecast_date': datetime.now().isoformat(),
                'horizon_days': horizon_days,
                'model_type': 'real_time_simple',
                'seasonal_factor': seasonal_factor,
                'recent_average_demand': float(recent_demand)
            }
            
            # Save prediction to database for tracking
            try:
                if self.pg_conn and predictions and len(predictions) > 0:
                    # Use "Real-Time Simple" as model name for this forecast type
                    model_name = "Real-Time Simple"
                    predicted_value = float(predictions[0])  # First day prediction
                    
                    await self.pg_conn.execute("""
                        INSERT INTO model_predictions 
                        (model_name, sku, predicted_value, prediction_date, forecast_horizon_days)
                        VALUES ($1, $2, $3, $4, $5)
                        ON CONFLICT DO NOTHING
                    """,
                        model_name,
                        sku,
                        predicted_value,
                        datetime.now(),
                        horizon_days
                    )
            except Exception as e:
                logger.warning(f"Failed to save prediction to database: {e}")
            
            # Cache the result for 1 hour
            try:
                self.redis_client.setex(cache_key, 3600, json.dumps(forecast_result, default=str))
            except Exception as e:
                logger.warning(f"Cache write failed: {e}")
            
            return forecast_result
            
        except Exception as e:
            logger.error(f"❌ Real-time forecasting failed for {sku}: {e}")
            raise

    async def generate_reorder_recommendations(self) -> List[ReorderRecommendation]:
        """Generate automated reorder recommendations"""
        logger.info("📦 Generating reorder recommendations...")
        
        try:
            # Get current inventory levels
            inventory_query = """
            SELECT sku, name, quantity, reorder_point, location
            FROM inventory_items
            WHERE quantity <= reorder_point * 1.5
            ORDER BY quantity ASC
            """
            
            inventory_results = await self.pg_conn.fetch(inventory_query)
            
            recommendations = []
            
            for item in inventory_results:
                sku = item['sku']
                current_stock = item['quantity']
                reorder_point = item['reorder_point']
                
                # Get recent demand forecast
                try:
                    forecast = await self.get_real_time_forecast(sku, 30)
                    avg_daily_demand = forecast['recent_average_demand']
                except:
                    avg_daily_demand = 10  # Default fallback
                
                # Calculate recommended order quantity
                safety_stock = max(reorder_point, avg_daily_demand * 7)  # 7 days safety stock
                recommended_quantity = int(safety_stock * 2) - current_stock
                recommended_quantity = max(0, recommended_quantity)
                
                # Determine urgency level
                days_remaining = current_stock / max(avg_daily_demand, 1)
                
                if days_remaining <= 3:
                    urgency = "CRITICAL"
                    reason = "Stock will run out in 3 days or less"
                elif days_remaining <= 7:
                    urgency = "HIGH"
                    reason = "Stock will run out within a week"
                elif days_remaining <= 14:
                    urgency = "MEDIUM"
                    reason = "Stock will run out within 2 weeks"
                else:
                    urgency = "LOW"
                    reason = "Stock levels are adequate"
                
                # Calculate confidence score
                confidence_score = min(0.95, max(0.5, 1.0 - (days_remaining / 30)))
                
                # Estimate arrival date (assuming 3-5 business days)
                arrival_date = datetime.now() + timedelta(days=5)
                
                recommendation = ReorderRecommendation(
                    sku=sku,
                    current_stock=current_stock,
                    recommended_order_quantity=recommended_quantity,
                    urgency_level=urgency,
                    reason=reason,
                    confidence_score=confidence_score,
                    estimated_arrival_date=arrival_date.isoformat()
                )
                
                recommendations.append(recommendation)
            
            logger.info(f"✅ Generated {len(recommendations)} reorder recommendations")
            return recommendations
            
        except Exception as e:
            logger.error(f"❌ Failed to generate reorder recommendations: {e}")
            raise

    async def get_model_performance_metrics(self) -> List[ModelPerformanceMetrics]:
        """Get model performance metrics and drift detection"""
        logger.info("📊 Calculating model performance metrics...")
        
        try:
            # Try to get real metrics first, fallback to simulated if needed
            try:
                metrics = await self._calculate_real_model_metrics()
                if metrics:
                    return metrics
            except Exception as e:
                logger.warning(f"Could not calculate real metrics, using fallback: {e}")
            
            # Fallback to simulated metrics (to be replaced with real data)
            metrics = [
                ModelPerformanceMetrics(
                    model_name="Random Forest",
                    accuracy_score=0.85,
                    mape=12.5,
                    last_training_date=(datetime.now() - timedelta(days=1)).isoformat(),
                    prediction_count=1250,
                    drift_score=0.15,
                    status="HEALTHY"
                ),
                ModelPerformanceMetrics(
                    model_name="XGBoost",
                    accuracy_score=0.82,
                    mape=15.8,
                    last_training_date=(datetime.now() - timedelta(hours=6)).isoformat(),
                    prediction_count=1180,
                    drift_score=0.18,
                    status="HEALTHY"
                ),
                ModelPerformanceMetrics(
                    model_name="Gradient Boosting",
                    accuracy_score=0.78,
                    mape=14.2,
                    last_training_date=(datetime.now() - timedelta(days=2)).isoformat(),
                    prediction_count=1100,
                    drift_score=0.22,
                    status="WARNING"
                ),
                ModelPerformanceMetrics(
                    model_name="Linear Regression",
                    accuracy_score=0.72,
                    mape=18.7,
                    last_training_date=(datetime.now() - timedelta(days=3)).isoformat(),
                    prediction_count=980,
                    drift_score=0.31,
                    status="NEEDS_RETRAINING"
                ),
                ModelPerformanceMetrics(
                    model_name="Ridge Regression",
                    accuracy_score=0.75,
                    mape=16.3,
                    last_training_date=(datetime.now() - timedelta(days=1)).isoformat(),
                    prediction_count=1050,
                    drift_score=0.25,
                    status="WARNING"
                ),
                ModelPerformanceMetrics(
                    model_name="Support Vector Regression",
                    accuracy_score=0.70,
                    mape=20.1,
                    last_training_date=(datetime.now() - timedelta(days=4)).isoformat(),
                    prediction_count=920,
                    drift_score=0.35,
                    status="NEEDS_RETRAINING"
                )
            ]
            
            return metrics
            
        except Exception as e:
            logger.error(f"❌ Failed to get model performance metrics: {e}")
            raise
    
    async def _calculate_real_model_metrics(self) -> List[ModelPerformanceMetrics]:
        """Calculate real model performance metrics from actual data"""
        metrics = []
        
        try:
            # Get model names from actual training history or model registry
            model_names = await self._get_active_model_names()
            
            if not model_names:
                logger.warning("No active model names found, returning empty list")
                return []
            
            logger.info(f"📊 Calculating metrics for {len(model_names)} models: {model_names}")
            
            for model_name in model_names:
                try:
                    # Calculate actual performance metrics
                    accuracy = await self._calculate_model_accuracy(model_name)
                    mape = await self._calculate_model_mape(model_name)
                    prediction_count = await self._get_prediction_count(model_name)
                    drift_score = await self._calculate_drift_score(model_name)
                    last_training = await self._get_last_training_date(model_name)
                    status = self._determine_model_status(accuracy, drift_score, last_training)
                    
                    metrics.append(ModelPerformanceMetrics(
                        model_name=model_name,
                        accuracy_score=accuracy,
                        mape=mape,
                        last_training_date=last_training.isoformat(),
                        prediction_count=prediction_count,
                        drift_score=drift_score,
                        status=status
                    ))
                    
                    logger.info(f"✅ Calculated metrics for {model_name}: accuracy={accuracy:.3f}, MAPE={mape:.1f}")
                    
                except Exception as e:
                    logger.warning(f"Could not calculate metrics for {model_name}: {e}")
                    import traceback
                    logger.warning(traceback.format_exc())
                    continue
            
            if metrics:
                logger.info(f"✅ Successfully calculated metrics for {len(metrics)} models")
            else:
                logger.warning("⚠️  No metrics calculated, returning empty list")
            
            return metrics
            
        except Exception as e:
            logger.error(f"❌ Error in _calculate_real_model_metrics: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    async def _get_active_model_names(self) -> List[str]:
        """Get list of active model names from training history or model registry"""
        try:
            # Query training history to get recently trained models
            # Use subquery to get distinct model names ordered by most recent training
            query = """
            SELECT DISTINCT ON (model_name) model_name
            FROM model_training_history 
            WHERE training_date >= NOW() - INTERVAL '30 days'
            ORDER BY model_name, training_date DESC
            """
            
            result = await self.db_pool.fetch(query)
            if result and len(result) > 0:
                model_names = [row['model_name'] for row in result]
                logger.info(f"📊 Found {len(model_names)} active models in database: {model_names}")
                return model_names
            
            # Fallback to default models if no training history
            logger.warning("No active models found in database, using fallback list")
            return ["Random Forest", "XGBoost", "Gradient Boosting", "Linear Regression", "Ridge Regression", "Support Vector Regression"]
            
        except Exception as e:
            logger.warning(f"Could not get active model names: {e}")
            import traceback
            logger.warning(traceback.format_exc())
            return ["Random Forest", "XGBoost", "Gradient Boosting", "Linear Regression", "Ridge Regression", "Support Vector Regression"]
    
    async def _calculate_model_accuracy(self, model_name: str) -> float:
        """Calculate actual model accuracy from training history or predictions"""
        try:
            # First, try to get accuracy from most recent training
            training_query = """
            SELECT accuracy_score
            FROM model_training_history 
            WHERE model_name = $1 
            AND training_date >= NOW() - INTERVAL '30 days'
            ORDER BY training_date DESC
            LIMIT 1
            """
            
            result = await self.db_pool.fetchval(training_query, model_name)
            if result is not None:
                return float(result)
            
            # Fallback: try to calculate from predictions with actual values
            prediction_query = """
            SELECT 
                AVG(CASE 
                    WHEN ABS(predicted_value - actual_value) / NULLIF(actual_value, 0) <= 0.1 THEN 1.0 
                    ELSE 0.0 
                END) as accuracy
            FROM model_predictions 
            WHERE model_name = $1 
            AND prediction_date >= NOW() - INTERVAL '7 days'
            AND actual_value IS NOT NULL
            """
            
            result = await self.db_pool.fetchval(prediction_query, model_name)
            return float(result) if result is not None else 0.75
                
        except Exception as e:
            logger.warning(f"Could not calculate accuracy for {model_name}: {e}")
            return 0.75  # Default accuracy
    
    async def _calculate_model_mape(self, model_name: str) -> float:
        """Calculate Mean Absolute Percentage Error from training history or predictions"""
        try:
            # First, try to get MAPE from most recent training
            training_query = """
            SELECT mape_score
            FROM model_training_history 
            WHERE model_name = $1 
            AND training_date >= NOW() - INTERVAL '30 days'
            ORDER BY training_date DESC
            LIMIT 1
            """
            
            result = await self.db_pool.fetchval(training_query, model_name)
            if result is not None:
                return float(result)
            
            # Fallback: try to calculate from predictions with actual values
            prediction_query = """
            SELECT 
                AVG(ABS(predicted_value - actual_value) / NULLIF(actual_value, 0)) * 100 as mape
            FROM model_predictions 
            WHERE model_name = $1 
            AND prediction_date >= NOW() - INTERVAL '7 days'
            AND actual_value IS NOT NULL AND actual_value > 0
            """
            
            result = await self.db_pool.fetchval(prediction_query, model_name)
            return float(result) if result is not None else 15.0
                
        except Exception as e:
            logger.warning(f"Could not calculate MAPE for {model_name}: {e}")
            return 15.0  # Default MAPE
    
    async def _get_prediction_count(self, model_name: str) -> int:
        """Get count of recent predictions for the model"""
        try:
            query = """
            SELECT COUNT(*) 
            FROM model_predictions 
            WHERE model_name = $1 
            AND prediction_date >= NOW() - INTERVAL '7 days'
            """
            
            result = await self.db_pool.fetchval(query, model_name)
            return int(result) if result is not None else 1000
                
        except Exception as e:
            logger.warning(f"Could not get prediction count for {model_name}: {e}")
            return 1000  # Default count
    
    async def _calculate_drift_score(self, model_name: str) -> float:
        """Calculate model drift score based on recent performance degradation"""
        try:
            # Compare recent performance with historical performance
            query = """
            WITH recent_performance AS (
                SELECT AVG(ABS(predicted_value - actual_value) / NULLIF(actual_value, 0)) as recent_error
                FROM model_predictions 
                WHERE model_name = $1 
                AND prediction_date >= NOW() - INTERVAL '3 days'
                AND actual_value IS NOT NULL
            ),
            historical_performance AS (
                SELECT AVG(ABS(predicted_value - actual_value) / NULLIF(actual_value, 0)) as historical_error
                FROM model_predictions 
                WHERE model_name = $1 
                AND prediction_date BETWEEN NOW() - INTERVAL '14 days' AND NOW() - INTERVAL '7 days'
                AND actual_value IS NOT NULL
            )
            SELECT 
                CASE 
                    WHEN historical_performance.historical_error > 0 
                    THEN (recent_performance.recent_error - historical_performance.historical_error) / historical_performance.historical_error
                    ELSE 0.0
                END as drift_score
            FROM recent_performance, historical_performance
            """
            
            result = await self.db_pool.fetchval(query, model_name)
            return max(0.0, float(result)) if result is not None else 0.2
                
        except Exception as e:
            logger.warning(f"Could not calculate drift score for {model_name}: {e}")
            return 0.2  # Default drift score
    
    async def _get_last_training_date(self, model_name: str) -> datetime:
        """Get the last training date for the model"""
        try:
            query = """
            SELECT MAX(training_date) 
            FROM model_training_history 
            WHERE model_name = $1
            """
            
            result = await self.db_pool.fetchval(query, model_name)
            if result:
                # PostgreSQL returns timezone-aware datetime if column is TIMESTAMP WITH TIME ZONE
                # or timezone-naive if TIMESTAMP WITHOUT TIME ZONE
                # Convert to timezone-naive for consistency
                if isinstance(result, datetime):
                    if result.tzinfo is not None:
                        # Convert to UTC and remove timezone info
                        from datetime import timezone
                        result = result.astimezone(timezone.utc).replace(tzinfo=None)
                    return result
                    
        except Exception as e:
            logger.warning(f"Could not get last training date for {model_name}: {e}")
        
        # Fallback to recent date (timezone-naive)
        return datetime.now() - timedelta(days=1)
    
    def _determine_model_status(self, accuracy: float, drift_score: float, last_training: datetime) -> str:
        """Determine model status based on performance metrics"""
        # Handle timezone-aware vs timezone-naive datetime comparison
        now = datetime.now()
        if last_training.tzinfo is not None:
            # If last_training is timezone-aware, make now timezone-aware too
            from datetime import timezone
            now = datetime.now(timezone.utc)
        elif now.tzinfo is not None:
            # If now is timezone-aware but last_training is not, make last_training naive
            last_training = last_training.replace(tzinfo=None)
        
        days_since_training = (now - last_training).days
        
        # Use hardcoded thresholds temporarily
        accuracy_threshold_warning = 0.7
        accuracy_threshold_healthy = 0.8
        drift_threshold_warning = 0.2
        drift_threshold_critical = 0.3
        retraining_days_threshold = 7
        
        if accuracy < accuracy_threshold_warning or drift_score > drift_threshold_critical:
            return "NEEDS_RETRAINING"
        elif accuracy < accuracy_threshold_healthy or drift_score > drift_threshold_warning or days_since_training > retraining_days_threshold:
            return "WARNING"
        else:
            return "HEALTHY"

    async def get_business_intelligence_summary(self) -> BusinessIntelligenceSummary:
        """Get comprehensive business intelligence summary"""
        logger.info("📈 Generating business intelligence summary...")
        
        try:
            # Get inventory summary
            inventory_query = """
            SELECT 
                COUNT(*) as total_skus,
                COUNT(CASE WHEN quantity <= reorder_point THEN 1 END) as low_stock_items,
                AVG(quantity) as avg_quantity
            FROM inventory_items
            """
            
            inventory_summary = await self.pg_conn.fetchrow(inventory_query)
            
            # Get demand summary
            demand_query = """
            SELECT 
                COUNT(DISTINCT sku) as active_skus,
                AVG(daily_demand) as avg_daily_demand
            FROM (
                SELECT 
                    sku,
                    DATE(timestamp) as date,
                    SUM(quantity) as daily_demand
                FROM inventory_movements 
                WHERE movement_type = 'outbound'
                    AND timestamp >= NOW() - INTERVAL '30 days'
                GROUP BY sku, DATE(timestamp)
            ) daily_demands
            """
            
            demand_summary = await self.pg_conn.fetchrow(demand_query)
            
            # Get model performance
            model_metrics = await self.get_model_performance_metrics()
            
            # Get reorder recommendations
            reorder_recommendations = await self.generate_reorder_recommendations()
            
            # Calculate overall forecast accuracy (simplified)
            forecast_accuracy = np.mean([m.accuracy_score for m in model_metrics])
            
            summary = BusinessIntelligenceSummary(
                total_skus=inventory_summary['total_skus'],
                low_stock_items=inventory_summary['low_stock_items'],
                high_demand_items=len([r for r in reorder_recommendations if r.urgency_level in ['HIGH', 'CRITICAL']]),
                forecast_accuracy=forecast_accuracy,
                reorder_recommendations=len(reorder_recommendations),
                model_performance=model_metrics
            )
            
            logger.info("✅ Business intelligence summary generated")
            return summary
            
        except Exception as e:
            logger.error(f"❌ Failed to generate business intelligence summary: {e}")
            raise

    async def get_enhanced_business_intelligence(self) -> Dict[str, Any]:
        """Get comprehensive business intelligence with analytics, trends, and visualizations"""
        logger.info("📊 Generating enhanced business intelligence...")
        
        try:
            # 1. Inventory Analytics
            inventory_query = """
            SELECT 
                COUNT(*) as total_skus,
                COUNT(CASE WHEN quantity <= reorder_point THEN 1 END) as low_stock_items,
                COUNT(CASE WHEN quantity > reorder_point * 2 THEN 1 END) as overstock_items,
                AVG(quantity) as avg_quantity,
                SUM(quantity) as total_quantity,
                AVG(reorder_point) as avg_reorder_point
            FROM inventory_items
            """
            inventory_analytics = await self.pg_conn.fetchrow(inventory_query)
            
            # 2. Demand Analytics (Last 30 days)
            demand_query = """
            SELECT 
                sku,
                DATE(timestamp) as date,
                SUM(CASE WHEN movement_type = 'outbound' THEN quantity ELSE 0 END) as daily_demand,
                SUM(CASE WHEN movement_type = 'inbound' THEN quantity ELSE 0 END) as daily_receipts
            FROM inventory_movements 
            WHERE timestamp >= NOW() - INTERVAL '30 days'
            GROUP BY sku, DATE(timestamp)
            ORDER BY date DESC
            """
            demand_data = await self.pg_conn.fetch(demand_query)
            
            # 3. Category Performance Analysis
            category_query = """
            SELECT 
                SUBSTRING(sku, 1, 3) as category,
                COUNT(*) as sku_count,
                AVG(quantity) as avg_quantity,
                SUM(quantity) as category_quantity,
                COUNT(CASE WHEN quantity <= reorder_point THEN 1 END) as low_stock_count
            FROM inventory_items
            GROUP BY SUBSTRING(sku, 1, 3)
            ORDER BY category_quantity DESC
            """
            category_analytics = await self.pg_conn.fetch(category_query)
            
            # 4. Top/Bottom Performers
            top_performers_query = """
            SELECT 
                sku,
                SUM(CASE WHEN movement_type = 'outbound' THEN quantity ELSE 0 END) as total_demand,
                COUNT(CASE WHEN movement_type = 'outbound' THEN 1 END) as movement_count,
                AVG(CASE WHEN movement_type = 'outbound' THEN quantity ELSE 0 END) as avg_daily_demand
            FROM inventory_movements 
            WHERE timestamp >= NOW() - INTERVAL '30 days'
                AND movement_type = 'outbound'
            GROUP BY sku
            ORDER BY total_demand DESC
            LIMIT 10
            """
            top_performers = await self.pg_conn.fetch(top_performers_query)
            
            bottom_performers_query = """
            SELECT 
                sku,
                SUM(CASE WHEN movement_type = 'outbound' THEN quantity ELSE 0 END) as total_demand,
                COUNT(CASE WHEN movement_type = 'outbound' THEN 1 END) as movement_count,
                AVG(CASE WHEN movement_type = 'outbound' THEN quantity ELSE 0 END) as avg_daily_demand
            FROM inventory_movements 
            WHERE timestamp >= NOW() - INTERVAL '30 days'
                AND movement_type = 'outbound'
            GROUP BY sku
            ORDER BY total_demand ASC
            LIMIT 10
            """
            bottom_performers = await self.pg_conn.fetch(bottom_performers_query)
            
            # 5. Forecast Analytics - Generate real-time forecasts for all SKUs
            forecast_analytics = {}
            try:
                # Get all SKUs from inventory
                sku_query = """
                    SELECT DISTINCT sku 
                    FROM inventory_items 
                    ORDER BY sku
                    LIMIT 100
                """
                sku_results = await self.pg_conn.fetch(sku_query)
                
                if sku_results:
                    logger.info(f"📊 Generating real-time forecasts for {len(sku_results)} SKUs for trend analysis...")
                    total_predicted_demand = 0
                    trending_up = 0
                    trending_down = 0
                    stable_trends = 0
                    successful_forecasts = 0
                    
                    for row in sku_results:
                        sku = row['sku']
                        try:
                            # Get real-time forecast (uses cache if available)
                            forecast = await self.get_real_time_forecast(sku, horizon_days=30)
                            predictions = forecast.get('predictions', [])
                            
                            if predictions and len(predictions) > 0:
                                successful_forecasts += 1
                                avg_demand = sum(predictions) / len(predictions)
                                total_predicted_demand += avg_demand
                                
                                # Determine trend (compare first vs last prediction)
                                if len(predictions) >= 2:
                                    first_pred = predictions[0]
                                    last_pred = predictions[-1]
                                    # 5% threshold for trend detection
                                    if first_pred < last_pred * 0.95:  # Decreasing by 5%+
                                        trending_down += 1
                                    elif first_pred > last_pred * 1.05:  # Increasing by 5%+
                                        trending_up += 1
                                    else:
                                        stable_trends += 1
                                else:
                                    stable_trends += 1
                        except Exception as e:
                            logger.warning(f"Failed to generate forecast for SKU {sku} in trend analysis: {e}")
                            continue
                    
                    if successful_forecasts > 0:
                        # Get average accuracy from model performance
                        model_performance = await self.get_model_performance_metrics()
                        avg_accuracy = np.mean([m.accuracy_score for m in model_performance]) * 100 if model_performance else 0
                        
                        forecast_analytics = {
                            "total_predicted_demand": round(total_predicted_demand, 1),
                            "trending_up": trending_up,
                            "trending_down": trending_down,
                            "stable_trends": stable_trends,
                            "avg_forecast_accuracy": round(avg_accuracy, 1),
                            "skus_forecasted": successful_forecasts
                        }
                        logger.info(f"✅ Generated forecast analytics: {trending_up} up, {trending_down} down, {stable_trends} stable")
                    else:
                        logger.warning("No successful forecasts generated for trend analysis")
            except Exception as e:
                logger.error(f"Error generating forecast analytics: {e}")
                # forecast_analytics remains empty dict if there's an error
            
            # 6. Seasonal Analysis
            seasonal_query = """
            SELECT 
                EXTRACT(MONTH FROM timestamp) as month,
                EXTRACT(DOW FROM timestamp) as day_of_week,
                SUM(CASE WHEN movement_type = 'outbound' THEN quantity ELSE 0 END) as demand
            FROM inventory_movements 
            WHERE timestamp >= NOW() - INTERVAL '90 days'
                AND movement_type = 'outbound'
            GROUP BY EXTRACT(MONTH FROM timestamp), EXTRACT(DOW FROM timestamp)
            ORDER BY month, day_of_week
            """
            seasonal_data = await self.pg_conn.fetch(seasonal_query)
            
            # 7. Reorder Analysis
            reorder_query = """
            SELECT 
                sku,
                quantity,
                reorder_point,
                CASE 
                    WHEN quantity <= reorder_point THEN 'CRITICAL'
                    WHEN quantity <= reorder_point * 1.5 THEN 'HIGH'
                    WHEN quantity <= reorder_point * 2 THEN 'MEDIUM'
                    ELSE 'LOW'
                END as urgency_level
            FROM inventory_items
            WHERE quantity <= reorder_point * 2
            ORDER BY quantity ASC
            """
            reorder_analysis = await self.pg_conn.fetch(reorder_query)
            
            # 8. Model Performance Analytics
            model_performance = await self.get_model_performance_metrics()
            model_analytics = {
                "total_models": len(model_performance),
                "avg_accuracy": round(np.mean([m.accuracy_score for m in model_performance]) * 100, 1),  # Convert to percentage
                "best_model": max(model_performance, key=lambda x: x.accuracy_score).model_name if model_performance else "N/A",
                "worst_model": min(model_performance, key=lambda x: x.accuracy_score).model_name if model_performance else "N/A",
                "models_above_80": len([m for m in model_performance if m.accuracy_score > 0.80]),  # Fixed: accuracy_score is 0-1, not 0-100
                "models_below_70": len([m for m in model_performance if m.accuracy_score < 0.70])  # Fixed: accuracy_score is 0-1, not 0-100
            }
            
            # 9. Business KPIs
            # Calculate forecast coverage from forecast_analytics if available
            forecast_coverage = 0
            if forecast_analytics and 'skus_forecasted' in forecast_analytics:
                forecast_coverage = round((forecast_analytics['skus_forecasted'] / inventory_analytics['total_skus']) * 100, 1)
            
            kpis = {
                "inventory_turnover": round(inventory_analytics['total_quantity'] / max(sum([r['total_demand'] for r in top_performers]), 1), 2),
                "stockout_risk": round((inventory_analytics['low_stock_items'] / inventory_analytics['total_skus']) * 100, 1),
                "overstock_percentage": round((inventory_analytics['overstock_items'] / inventory_analytics['total_skus']) * 100, 1),
                "forecast_coverage": forecast_coverage,
                "demand_volatility": round(np.std([r['total_demand'] for r in top_performers]) / np.mean([r['total_demand'] for r in top_performers]), 2) if top_performers else 0
            }
            
            # 10. Recommendations
            recommendations = []
            
            # Low stock recommendations
            if inventory_analytics['low_stock_items'] > 0:
                recommendations.append({
                    "type": "urgent",
                    "title": "Low Stock Alert",
                    "description": f"{inventory_analytics['low_stock_items']} items are below reorder point",
                    "action": "Review and place orders immediately"
                })
            
            # Overstock recommendations
            if inventory_analytics['overstock_items'] > 0:
                recommendations.append({
                    "type": "warning",
                    "title": "Overstock Alert",
                    "description": f"{inventory_analytics['overstock_items']} items are overstocked",
                    "action": "Consider promotional pricing or redistribution"
                })
            
            # Model performance recommendations
            if model_analytics['models_below_70'] > 0:
                recommendations.append({
                    "type": "info",
                    "title": "Model Performance",
                    "description": f"{model_analytics['models_below_70']} models performing below 70% accuracy",
                    "action": "Retrain models with more recent data"
                })
            
            # Forecast trend recommendations
            if forecast_analytics and forecast_analytics['trending_down'] > forecast_analytics['trending_up']:
                recommendations.append({
                    "type": "warning",
                    "title": "Demand Trend",
                    "description": "More SKUs showing declining demand trends",
                    "action": "Review marketing strategies and product positioning"
                })
            
            enhanced_bi = {
                "inventory_analytics": dict(inventory_analytics),
                "category_analytics": [dict(row) for row in category_analytics],
                "top_performers": [dict(row) for row in top_performers],
                "bottom_performers": [dict(row) for row in bottom_performers],
                "forecast_analytics": forecast_analytics,
                "seasonal_data": [dict(row) for row in seasonal_data],
                "reorder_analysis": [dict(row) for row in reorder_analysis],
                "model_analytics": model_analytics,
                "business_kpis": kpis,
                "recommendations": recommendations,
                "generated_at": datetime.now().isoformat()
            }
            
            logger.info("✅ Enhanced business intelligence generated successfully")
            return enhanced_bi
            
        except Exception as e:
            logger.error(f"❌ Failed to generate enhanced business intelligence: {e}")
            raise

# Global service instance
forecasting_service = AdvancedForecastingService()

# API Endpoints
@router.post("/real-time")
async def get_real_time_forecast(request: ForecastRequest):
    """Get real-time forecast for a specific SKU"""
    try:
        await forecasting_service.initialize()
        forecast = await forecasting_service.get_real_time_forecast(
            request.sku, 
            request.horizon_days
        )
        return forecast
    except Exception as e:
        logger.error(f"Error in real-time forecast: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/reorder-recommendations")
async def get_reorder_recommendations():
    """Get automated reorder recommendations"""
    try:
        await forecasting_service.initialize()
        recommendations = await forecasting_service.generate_reorder_recommendations()
        return {
            "recommendations": recommendations,
            "generated_at": datetime.now().isoformat(),
            "total_count": len(recommendations)
        }
    except Exception as e:
        logger.error(f"Error generating reorder recommendations: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/model-performance")
async def get_model_performance():
    """Get model performance metrics and drift detection"""
    try:
        await forecasting_service.initialize()
        metrics = await forecasting_service.get_model_performance_metrics()
        return {
            "model_metrics": metrics,
            "generated_at": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting model performance: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/business-intelligence")
async def get_business_intelligence():
    """Get comprehensive business intelligence summary"""
    try:
        await forecasting_service.initialize()
        summary = await forecasting_service.get_business_intelligence_summary()
        return summary
    except Exception as e:
        logger.error(f"Error generating business intelligence: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/business-intelligence/enhanced")
async def get_enhanced_business_intelligence():
    """Get comprehensive business intelligence with analytics and trends"""
    try:
        await forecasting_service.initialize()
        enhanced_bi = await forecasting_service.get_enhanced_business_intelligence()
        return enhanced_bi
    except Exception as e:
        logger.error(f"Error generating enhanced business intelligence: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def get_forecast_summary_data():
    """Get forecast summary data dynamically from real-time forecasts"""
    try:
        # Ensure service is initialized
        await forecasting_service.initialize()
        
        # Get all SKUs from inventory
        sku_query = """
            SELECT DISTINCT sku 
            FROM inventory_items 
            ORDER BY sku
            LIMIT 100
        """
        
        sku_results = await forecasting_service.pg_conn.fetch(sku_query)
        
        if not sku_results:
            logger.warning("No SKUs found in inventory")
            return {
                "forecast_summary": {},
                "total_skus": 0,
                "generated_at": datetime.now().isoformat()
            }
        
        summary = {}
        current_date = datetime.now().isoformat()
        
        logger.info(f"🔮 Generating dynamic forecasts for {len(sku_results)} SKUs...")
        
        # Generate forecasts for each SKU (use cached when available)
        for row in sku_results:
            sku = row['sku']
            try:
                # Get real-time forecast (uses cache if available)
                forecast = await forecasting_service.get_real_time_forecast(sku, horizon_days=30)
                
                # Extract predictions
                predictions = forecast.get('predictions', [])
                if not predictions or len(predictions) == 0:
                    logger.warning(f"No predictions for SKU {sku}")
                    continue
                
                # Calculate summary statistics
                avg_demand = sum(predictions) / len(predictions)
                min_demand = min(predictions)
                max_demand = max(predictions)
                
                # Determine trend
                if len(predictions) >= 2:
                    trend = "increasing" if predictions[0] < predictions[-1] else "decreasing" if predictions[0] > predictions[-1] else "stable"
                else:
                    trend = "stable"
                
                # Use forecast_date from the forecast response, or current date
                forecast_date = forecast.get('forecast_date', current_date)
                
                summary[sku] = {
                    "average_daily_demand": round(avg_demand, 1),
                    "min_demand": round(min_demand, 1),
                    "max_demand": round(max_demand, 1),
                    "trend": trend,
                    "forecast_date": forecast_date
                }
                
            except Exception as e:
                logger.warning(f"Failed to generate forecast for SKU {sku}: {e}")
                # Skip this SKU and continue with others
                continue
        
        logger.info(f"✅ Generated dynamic forecast summary for {len(summary)} SKUs")
        return {
            "forecast_summary": summary,
            "total_skus": len(summary),
            "generated_at": current_date
        }
        
    except Exception as e:
        logger.error(f"❌ Error getting forecast summary data: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            "forecast_summary": {},
            "total_skus": 0,
            "generated_at": datetime.now().isoformat()
        }

@router.get("/dashboard")
async def get_forecasting_dashboard():
    """Get comprehensive forecasting dashboard data"""
    try:
        await forecasting_service.initialize()
        
        # Get all dashboard data
        # Get enhanced business intelligence
        enhanced_bi = await forecasting_service.get_enhanced_business_intelligence()
        reorder_recs = await forecasting_service.generate_reorder_recommendations()
        model_metrics = await forecasting_service.get_model_performance_metrics()
        
        # Get forecast summary data
        forecast_summary = await get_forecast_summary_data()
        
        dashboard_data = {
            "business_intelligence": enhanced_bi,
            "reorder_recommendations": reorder_recs,
            "model_performance": model_metrics,
            "forecast_summary": forecast_summary,
            "generated_at": datetime.now().isoformat()
        }
        
        return dashboard_data
        
    except Exception as e:
        logger.error(f"Error generating dashboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/batch-forecast")
async def batch_forecast(request: BatchForecastRequest):
    """Generate forecasts for multiple SKUs in batch"""
    try:
        if not request.skus or len(request.skus) == 0:
            raise HTTPException(status_code=400, detail="SKU list cannot be empty")
        
        # Security: Additional validation to prevent DoS attacks from large batch requests
        MAX_SKUS = 100
        if len(request.skus) > MAX_SKUS:
            logger.warning(f"Batch request contains {len(request.skus)} SKUs, restricting to first {MAX_SKUS}")
            request.skus = request.skus[:MAX_SKUS]
        
        await forecasting_service.initialize()
        
        forecasts = {}
        for sku in request.skus:
            try:
                forecasts[sku] = await forecasting_service.get_real_time_forecast(sku, request.horizon_days)
            except Exception as e:
                logger.error(f"Failed to forecast {sku}: {e}")
                forecasts[sku] = {"error": str(e)}
        
        return {
            "forecasts": forecasts,
            "total_skus": len(request.skus),
            "successful_forecasts": len([f for f in forecasts.values() if "error" not in f]),
            "generated_at": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in batch forecast: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Health check endpoint
@router.get("/health")
async def health_check():
    """Health check for forecasting service"""
    try:
        await forecasting_service.initialize()
        return {
            "status": "healthy",
            "service": "advanced_forecasting",
            "timestamp": datetime.now().isoformat(),
            "database_connected": forecasting_service.pg_conn is not None,
            "redis_connected": forecasting_service.redis_client is not None
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }
