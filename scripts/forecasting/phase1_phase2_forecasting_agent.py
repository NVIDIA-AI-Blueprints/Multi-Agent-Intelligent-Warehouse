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
Phase 1 & 2: RAPIDS Demand Forecasting Agent - CPU Fallback Version

Implements data extraction and feature engineering pipeline for Frito-Lay products.
GPU acceleration will be added when RAPIDS container is available.
"""

import asyncio
import asyncpg
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from pathlib import Path
import json
import numpy as np
import pandas as pd
from dataclasses import dataclass
import os

# CPU fallback libraries
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_squared_error, mean_absolute_error
from sklearn.preprocessing import StandardScaler
import xgboost as xgb

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database connection constants
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5435"))
DB_USER = os.getenv("POSTGRES_USER", "warehouse")
DB_NAME = os.getenv("POSTGRES_DB", "warehouse")

@dataclass
class ForecastingConfig:
    """Configuration for demand forecasting"""
    prediction_horizon_days: int = 30
    lookback_days: int = 180
    min_training_samples: int = 30
    validation_split: float = 0.2
    ensemble_weights: Dict[str, float] = None
    
    def __post_init__(self):
        if self.ensemble_weights is None:
            self.ensemble_weights = {
                'random_forest': 0.4,
                'xgboost': 0.4,
                'time_series': 0.2
            }

@dataclass
class ForecastResult:
    """Result of demand forecasting"""
    sku: str
    predictions: List[float]
    confidence_intervals: List[Tuple[float, float]]
    model_metrics: Dict[str, float]
    feature_importance: Dict[str, float]
    forecast_date: datetime
    horizon_days: int

class RAPIDSForecastingAgent:
    """Demand forecasting agent with RAPIDS integration (CPU fallback)"""
    
    def __init__(self, config: ForecastingConfig = None):
        self.config = config or ForecastingConfig()
        self.pg_conn = None
        self.models = {}
        self.scalers = {}
        self.feature_columns = []
        self.use_gpu = False  # Will be True when RAPIDS is available
        
        logger.info("🚀 RAPIDS Forecasting Agent initialized (CPU mode)")
        logger.info("💡 Install RAPIDS container for GPU acceleration")

    async def initialize_connection(self):
        """Initialize database connection"""
        try:
            self.pg_conn = await asyncpg.connect(
                host=DB_HOST,
                port=DB_PORT,
                user=DB_USER,
                password=os.getenv("POSTGRES_PASSWORD", ""),
                database=DB_NAME
            )
            logger.info("✅ Connected to PostgreSQL")
        except Exception as e:
            logger.error(f"❌ Failed to connect to PostgreSQL: {e}")
            raise

    async def _fetch_sku_list(self, query: str) -> List[str]:
        """
        Helper method to fetch SKU list from database.
        
        Args:
            query: SQL query that returns rows with 'sku' column
            
        Returns:
            List of SKU strings
        """
        if not self.pg_conn:
            await self.initialize_connection()
        
        rows = await self.pg_conn.fetch(query)
        return [row['sku'] for row in rows]

    async def get_all_skus(self) -> List[str]:
        """Get all SKUs from the inventory"""
        query = "SELECT sku FROM inventory_items ORDER BY sku"
        skus = await self._fetch_sku_list(query)
        logger.info(f"📦 Retrieved {len(skus)} SKUs from database")
        return skus

    async def extract_historical_data(self, sku: str) -> pd.DataFrame:
        """Phase 2: Extract and preprocess historical demand data"""
        logger.info(f"📊 Phase 2: Extracting historical data for {sku}")
        
        query = f"""
        SELECT 
            DATE(timestamp) as date,
            SUM(quantity) as daily_demand,
            EXTRACT(DOW FROM DATE(timestamp)) as day_of_week,
            EXTRACT(MONTH FROM DATE(timestamp)) as month,
            EXTRACT(QUARTER FROM DATE(timestamp)) as quarter,
            EXTRACT(YEAR FROM DATE(timestamp)) as year,
            CASE 
                WHEN EXTRACT(DOW FROM DATE(timestamp)) IN (0, 6) THEN 1 
                ELSE 0 
            END as is_weekend,
            CASE 
                WHEN EXTRACT(MONTH FROM DATE(timestamp)) IN (6, 7, 8) THEN 1 
                ELSE 0 
            END as is_summer,
            CASE 
                WHEN EXTRACT(MONTH FROM DATE(timestamp)) IN (11, 12, 1) THEN 1 
                ELSE 0 
            END as is_holiday_season,
            CASE 
                WHEN EXTRACT(MONTH FROM DATE(timestamp)) IN (2) AND EXTRACT(DAY FROM DATE(timestamp)) BETWEEN 9 AND 15 THEN 1 
                ELSE 0 
            END as is_super_bowl,
            CASE 
                WHEN EXTRACT(MONTH FROM DATE(timestamp)) IN (7) AND EXTRACT(DAY FROM DATE(timestamp)) BETWEEN 1 AND 7 THEN 1 
                ELSE 0 
            END as is_july_4th
        FROM inventory_movements 
        WHERE sku = $1 
            AND movement_type = 'outbound'
            AND timestamp >= NOW() - INTERVAL '{self.config.lookback_days} days'
        GROUP BY DATE(timestamp)
        ORDER BY date
        """
        
        results = await self.pg_conn.fetch(query, sku)
        
        if not results:
            raise ValueError(f"No historical data found for SKU {sku}")
        
        # Convert to DataFrame
        df = pd.DataFrame([dict(row) for row in results])
        df['sku'] = sku  # Add SKU column
        
        logger.info(f"📈 Extracted {len(df)} days of historical data")
        return df

    def engineer_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Phase 2: Engineer features based on NVIDIA best practices"""
        logger.info("🔧 Phase 2: Engineering features...")
        
        # Sort by date
        df = df.sort_values('date').reset_index(drop=True)
        
        # Lag features (NVIDIA best practice)
        for lag in [1, 3, 7, 14, 30]:
            df[f'demand_lag_{lag}'] = df['daily_demand'].shift(lag)
        
        # Rolling statistics
        rolling_windows = [7, 14, 30]
        rolling_stats = ['mean', 'std', 'max']
        for window in rolling_windows:
            rolling_series = df['daily_demand'].rolling(window=window)
            for stat in rolling_stats:
                df[f'demand_rolling_{stat}_{window}'] = getattr(rolling_series, stat)()
        
        # Trend features
        df['demand_trend_7'] = df['daily_demand'].rolling(window=7).apply(
            lambda x: np.polyfit(range(len(x)), x, 1)[0] if len(x) == 7 else 0
        )
        
        # Seasonal decomposition features
        df['demand_seasonal'] = df.groupby('day_of_week')['daily_demand'].transform('mean')
        df['demand_monthly_seasonal'] = df.groupby('month')['daily_demand'].transform('mean')
        
        # Promotional impact features
        df['promotional_boost'] = 1.0
        df.loc[df['is_super_bowl'] == 1, 'promotional_boost'] = 2.5
        df.loc[df['is_july_4th'] == 1, 'promotional_boost'] = 2.0
        
        # Interaction features
        df['weekend_summer'] = df['is_weekend'] * df['is_summer']
        df['holiday_weekend'] = df['is_holiday_season'] * df['is_weekend']
        
        # Brand-specific features (extract from SKU)
        df['brand'] = df['sku'].str[:3]
        brand_mapping = {
            'LAY': 'mainstream', 'DOR': 'premium', 'CHE': 'mainstream',
            'TOS': 'premium', 'FRI': 'value', 'RUF': 'mainstream',
            'SUN': 'specialty', 'POP': 'specialty', 'FUN': 'mainstream', 'SMA': 'specialty'
        }
        df['brand_tier'] = df['brand'].map(brand_mapping)
        
        # Encode categorical variables
        categorical_columns = ['brand', 'brand_tier', 'day_of_week', 'month', 'quarter', 'year']
        for col in categorical_columns:
            if col in df.columns:
                df[f'{col}_encoded'] = pd.Categorical(df[col]).codes
        
        # Remove rows with NaN values from lag features
        df = df.dropna()
        
        self.feature_columns = [col for col in df.columns if col not in ['date', 'daily_demand', 'sku', 'brand', 'brand_tier', 'day_of_week', 'month', 'quarter', 'year']]
        logger.info(f"✅ Engineered {len(self.feature_columns)} features")
        
        return df

    def _train_and_evaluate_model(
        self, 
        model, 
        model_name: str, 
        X_train: pd.DataFrame, 
        y_train: pd.Series, 
        X_val: pd.DataFrame, 
        y_val: pd.Series
    ) -> Tuple[any, Dict[str, float]]:
        """
        Train a model and evaluate it on validation set.
        
        Args:
            model: Model instance to train
            model_name: Name of the model for logging
            X_train: Training features
            y_train: Training target
            X_val: Validation features
            y_val: Validation target
            
        Returns:
            Tuple of (trained_model, metrics_dict)
        """
        model.fit(X_train, y_train)
        predictions = model.predict(X_val)
        metrics = {
            'mse': mean_squared_error(y_val, predictions),
            'mae': mean_absolute_error(y_val, predictions)
        }
        return model, metrics
    
    def train_models(self, df: pd.DataFrame) -> Tuple[Dict[str, any], Dict[str, Dict]]:
        """Train multiple models (CPU fallback)"""
        logger.info("🤖 Training forecasting models...")
        
        X = df[self.feature_columns]
        y = df['daily_demand']
        
        # Split data
        split_idx = int(len(df) * (1 - self.config.validation_split))
        X_train, X_val = X[:split_idx], X[split_idx:]
        y_train, y_val = y[:split_idx], y[split_idx:]
        
        models = {}
        metrics = {}
        
        # 1. Random Forest
        rf_model, rf_metrics = self._train_and_evaluate_model(
            RandomForestRegressor(n_estimators=100, max_depth=10, random_state=42),
            'random_forest',
            X_train, y_train, X_val, y_val
        )
        models['random_forest'] = rf_model
        metrics['random_forest'] = rf_metrics
        
        # 2. XGBoost
        xgb_model, xgb_metrics = self._train_and_evaluate_model(
            xgb.XGBRegressor(
                n_estimators=100,
                max_depth=6,
                learning_rate=0.1,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=42
            ),
            'xgboost',
            X_train, y_train, X_val, y_val
        )
        models['xgboost'] = xgb_model
        metrics['xgboost'] = xgb_metrics
        
        # 3. Time Series Model
        ts_model = self._train_time_series_model(df)
        models['time_series'] = ts_model
        
        logger.info("✅ All models trained successfully")
        return models, metrics

    def _train_time_series_model(self, df: pd.DataFrame) -> Dict:
        """Train a simple time series model"""
        # Simple exponential smoothing implementation
        alpha = 0.3
        demand_values = df['daily_demand'].values
        
        # Calculate exponential moving average
        ema = [demand_values[0]]
        for i in range(1, len(demand_values)):
            ema.append(alpha * demand_values[i] + (1 - alpha) * ema[i-1])
        
        return {
            'type': 'exponential_smoothing',
            'alpha': alpha,
            'last_value': ema[-1],
            'trend': np.mean(np.diff(ema[-7:])) if len(ema) >= 7 else 0
        }

    def generate_forecast(self, models: Dict, df: pd.DataFrame, horizon_days: int) -> ForecastResult:
        """Generate ensemble forecast"""
        logger.info(f"🔮 Generating {horizon_days}-day forecast...")
        
        # Get latest features
        latest_features = df[self.feature_columns].iloc[-1:].values
        
        predictions = []
        model_predictions = {}
        
        # Generate predictions from each model
        for model_name, model in models.items():
            if model_name == 'time_series':
                # Time series forecast
                ts_pred = self._time_series_forecast(model, horizon_days)
                model_predictions[model_name] = ts_pred
            else:
                # ML model forecast (simplified - using last known features)
                pred = model.predict(latest_features)
                # Extend prediction for horizon (simplified approach)
                ts_pred = [pred[0]] * horizon_days
                model_predictions[model_name] = ts_pred
        
        # Ensemble prediction
        ensemble_pred = np.zeros(horizon_days)
        for model_name, pred in model_predictions.items():
            weight = self.config.ensemble_weights.get(model_name, 0.33)
            ensemble_pred += weight * np.array(pred)
        
        predictions = ensemble_pred.tolist()
        
        # Calculate confidence intervals (simplified)
        confidence_intervals = []
        for pred in predictions:
            std_dev = np.std(list(model_predictions.values()))
            ci_lower = max(0, pred - 1.96 * std_dev)
            ci_upper = pred + 1.96 * std_dev
            confidence_intervals.append((ci_lower, ci_upper))
        
        # Calculate feature importance (from Random Forest)
        feature_importance = {}
        if 'random_forest' in models:
            rf_model = models['random_forest']
            for i, feature in enumerate(self.feature_columns):
                feature_importance[feature] = float(rf_model.feature_importances_[i])
        
        return ForecastResult(
            sku=df['sku'].iloc[0],
            predictions=predictions,
            confidence_intervals=confidence_intervals,
            model_metrics={},
            feature_importance=feature_importance,
            forecast_date=datetime.now(),
            horizon_days=horizon_days
        )

    def _create_forecast_summary(self, forecasts: Dict[str, ForecastResult]) -> Dict[str, Dict]:
        """
        Create summary dictionary from forecast results.
        
        Args:
            forecasts: Dictionary of SKU to ForecastResult
            
        Returns:
            Summary dictionary
        """
        results_summary = {}
        for sku, forecast in forecasts.items():
            results_summary[sku] = {
                'predictions': forecast.predictions,
                'confidence_intervals': forecast.confidence_intervals,
                'feature_importance': forecast.feature_importance,
                'forecast_date': forecast.forecast_date.isoformat(),
                'horizon_days': forecast.horizon_days
            }
        return results_summary
    
    def _write_json_file(self, file_path: str, data: Dict) -> None:
        """
        Helper method to write JSON data to file.
        
        Args:
            file_path: Path to output file
            data: Dictionary to serialize as JSON
        """
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            json.dump(data, f, indent=2, default=str)

    def _save_forecast_results(
        self, 
        results_summary: Dict, 
        output_file: str, 
        sample_file: Path
    ) -> None:
        """
        Save forecast results to multiple locations.
        
        Args:
            results_summary: Summary dictionary to save
            output_file: Path to runtime output file
            sample_file: Path to sample/reference file
        """
        # Save to root for runtime use
        self._write_json_file(output_file, results_summary)
        
        # Also save to data/sample/forecasts/ for reference
        self._write_json_file(str(sample_file), results_summary)
    
    def _time_series_forecast(self, ts_model: Dict, horizon_days: int) -> List[float]:
        """Generate time series forecast"""
        predictions = []
        last_value = ts_model['last_value']
        trend = ts_model['trend']
        
        for i in range(horizon_days):
            pred = last_value + trend * (i + 1)
            predictions.append(max(0, pred))  # Ensure non-negative
        
        return predictions

    async def forecast_demand(self, sku: str, horizon_days: int = None) -> ForecastResult:
        """Main forecasting method"""
        if horizon_days is None:
            horizon_days = self.config.prediction_horizon_days
        
        logger.info(f"🎯 Forecasting demand for {sku} ({horizon_days} days)")
        
        try:
            # Phase 2: Extract historical data
            df = await self.extract_historical_data(sku)
            
            # Phase 2: Engineer features
            df = self.engineer_features(df)
            
            if len(df) < self.config.min_training_samples:
                raise ValueError(f"Insufficient data for {sku}: {len(df)} samples")
            
            # Train models
            models, metrics = self.train_models(df)
            
            # Generate forecast
            forecast = self.generate_forecast(models, df, horizon_days)
            forecast.model_metrics = metrics
            
            logger.info(f"✅ Forecast completed for {sku}")
            return forecast
            
        except Exception as e:
            logger.error(f"❌ Forecasting failed for {sku}: {e}")
            raise

    async def batch_forecast(self, skus: List[str], horizon_days: int = None) -> Dict[str, ForecastResult]:
        """Forecast demand for multiple SKUs"""
        logger.info(f"📊 Batch forecasting for {len(skus)} SKUs")
        
        results = {}
        for sku in skus:
            try:
                results[sku] = await self.forecast_demand(sku, horizon_days)
            except Exception as e:
                logger.error(f"Failed to forecast {sku}: {e}")
                continue
        
        logger.info(f"✅ Batch forecast completed: {len(results)} successful")
        return results

    async def run(self, skus: List[str] = None, horizon_days: int = 30):
        """Main execution method"""
        logger.info("🚀 Starting Phase 1 & 2: RAPIDS Demand Forecasting Agent...")
        
        try:
            await self.initialize_connection()
            
            # Get SKUs to forecast
            if skus is None:
                query = "SELECT DISTINCT sku FROM inventory_movements WHERE movement_type = 'outbound' LIMIT 10"
                skus = await self._fetch_sku_list(query)
            
            logger.info(f"📈 Forecasting demand for {len(skus)} SKUs")
            
            # Generate forecasts
            forecasts = await self.batch_forecast(skus, horizon_days)
            
            # Save results
            results_summary = self._create_forecast_summary(forecasts)
            
            # Save to both root (for runtime) and data/sample/forecasts/ (for reference)
            output_file = os.path.join(os.getenv("FORECAST_OUTPUT_DIR", ""), "phase1_phase2_forecasts.json")
            sample_dir = Path(os.getenv("FORECAST_OUTPUT_DIR", "data/sample/forecasts"))
            sample_file = sample_dir / "phase1_phase2_forecasts.json"
            
            self._save_forecast_results(results_summary, output_file, sample_file)
            
            logger.info("🎉 Phase 1 & 2 completed successfully!")
            logger.info(f"📊 Generated forecasts for {len(forecasts)} SKUs")
            logger.info(f"💾 Forecasts saved to {output_file} (runtime) and {sample_file} (reference)")
            
            # Show sample results
            if forecasts:
                sample_sku = list(forecasts.keys())[0]
                sample_forecast = forecasts[sample_sku]
                logger.info(f"📈 Sample forecast for {sample_sku}:")
                logger.info(f"   • Next 7 days: {sample_forecast.predictions[:7]}")
                logger.info(f"   • Top features: {list(sample_forecast.feature_importance.keys())[:3]}")
            
        except Exception as e:
            logger.error(f"❌ Error in forecasting: {e}")
            raise
        finally:
            if self.pg_conn:
                await self.pg_conn.close()

async def main():
    """Main entry point"""
    config = ForecastingConfig(
        prediction_horizon_days=30,
        lookback_days=180,
        min_training_samples=30
    )
    
    agent = RAPIDSForecastingAgent(config)
    
    # Process all SKUs in the system
    all_skus = await agent.get_all_skus()
    logger.info(f"📦 Found {len(all_skus)} SKUs to forecast")
    await agent.run(skus=all_skus, horizon_days=30)

if __name__ == "__main__":
    asyncio.run(main())
