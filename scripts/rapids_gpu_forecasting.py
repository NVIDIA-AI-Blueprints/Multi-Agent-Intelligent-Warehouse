#!/usr/bin/env python3
"""
RAPIDS GPU-accelerated demand forecasting agent
Uses cuML for GPU-accelerated machine learning
"""

import asyncio
import asyncpg
import pandas as pd
import numpy as np
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import os
import sys

# Try to import RAPIDS cuML, fallback to CPU if not available
try:
    import cudf
    import cuml
    from cuml.ensemble import RandomForestRegressor as cuRandomForestRegressor
    from cuml.linear_model import LinearRegression as cuLinearRegression
    from cuml.svm import SVR as cuSVR
    from cuml.preprocessing import StandardScaler as cuStandardScaler
    from cuml.model_selection import train_test_split as cu_train_test_split
    from cuml.metrics import mean_squared_error as cu_mean_squared_error
    from cuml.metrics import mean_absolute_error as cu_mean_absolute_error
    RAPIDS_AVAILABLE = True
    print("✅ RAPIDS cuML detected - GPU acceleration enabled")
except ImportError:
    RAPIDS_AVAILABLE = False
    print("⚠️ RAPIDS cuML not available - falling back to CPU")

# CPU fallback imports
if not RAPIDS_AVAILABLE:
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.linear_model import LinearRegression, Ridge
    from sklearn.svm import SVR
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import mean_squared_error, mean_absolute_error
    import xgboost as xgb

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class RAPIDSForecastingAgent:
    """RAPIDS GPU-accelerated demand forecasting agent"""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or self._get_default_config()
        self.pg_conn = None
        self.models = {}
        self.feature_columns = []
        self.scaler = None
        self.use_gpu = RAPIDS_AVAILABLE
        
    def _get_default_config(self) -> Dict:
        """Get default configuration"""
        return {
            "lookback_days": 365,
            "forecast_days": 30,
            "test_size": 0.2,
            "random_state": 42,
            "n_estimators": 100,
            "max_depth": 10,
            "min_samples_split": 5,
            "min_samples_leaf": 2
        }
    
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
            logger.info("✅ Database connection established")
        except Exception as e:
            logger.error(f"❌ Database connection failed: {e}")
            raise
    
    async def get_all_skus(self) -> List[str]:
        """Get all SKUs from inventory"""
        query = "SELECT DISTINCT sku FROM inventory_items ORDER BY sku"
        results = await self.pg_conn.fetch(query)
        return [row['sku'] for row in results]
    
    async def extract_historical_data(self, sku: str) -> pd.DataFrame:
        """Extract historical demand data for a SKU"""
        logger.info(f"📊 Extracting historical data for {sku}")
        
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
            AND timestamp >= NOW() - INTERVAL '{self.config['lookback_days']} days'
        GROUP BY DATE(timestamp)
        ORDER BY date
        """
        
        results = await self.pg_conn.fetch(query, sku)
        
        if not results:
            logger.warning(f"⚠️ No historical data found for {sku}")
            return pd.DataFrame()
        
        # Convert to DataFrame
        df = pd.DataFrame([dict(row) for row in results])
        df['sku'] = sku
        
        # Convert to cuDF if RAPIDS is available
        if self.use_gpu:
            df = cudf.from_pandas(df)
            logger.info(f"✅ Data converted to cuDF for GPU processing: {len(df)} rows")
        
        return df
    
    def engineer_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Engineer features for machine learning"""
        logger.info("🔧 Engineering features...")
        
        if df.empty:
            return df
        
        # Create lag features
        for lag in [1, 3, 7, 14, 30]:
            df[f'demand_lag_{lag}'] = df['daily_demand'].shift(lag)
        
        # Rolling statistics
        for window in [7, 14, 30]:
            df[f'demand_rolling_mean_{window}'] = df['daily_demand'].rolling(window=window).mean()
            df[f'demand_rolling_std_{window}'] = df['daily_demand'].rolling(window=window).std()
        
        # Trend features
        df['demand_trend_7'] = df['daily_demand'].rolling(window=7).apply(lambda x: np.polyfit(range(len(x)), x, 1)[0] if len(x) > 1 else 0)
        df['demand_trend_30'] = df['daily_demand'].rolling(window=30).apply(lambda x: np.polyfit(range(len(x)), x, 1)[0] if len(x) > 1 else 0)
        
        # Brand-specific features
        df['brand'] = df['sku'].str[:3]
        brand_mapping = {
            'LAY': 'mainstream', 'DOR': 'premium', 'CHE': 'mainstream',
            'TOS': 'premium', 'FRI': 'value', 'RUF': 'mainstream',
            'SUN': 'specialty', 'POP': 'specialty', 'FUN': 'mainstream', 'SMA': 'specialty'
        }
        df['brand_tier'] = df['brand'].map(brand_mapping)
        
        # Encode categorical variables
        if self.use_gpu:
            # cuDF categorical encoding
            df['brand_encoded'] = df['brand'].astype('category').cat.codes
            df['brand_tier_encoded'] = df['brand_tier'].astype('category').cat.codes
            df['day_of_week_encoded'] = df['day_of_week'].astype('category').cat.codes
            df['month_encoded'] = df['month'].astype('category').cat.codes
            df['quarter_encoded'] = df['quarter'].astype('category').cat.codes
            df['year_encoded'] = df['year'].astype('category').cat.codes
        else:
            # Pandas categorical encoding
            df['brand_encoded'] = pd.Categorical(df['brand']).codes
            df['brand_tier_encoded'] = pd.Categorical(df['brand_tier']).codes
            df['day_of_week_encoded'] = pd.Categorical(df['day_of_week']).codes
            df['month_encoded'] = pd.Categorical(df['month']).codes
            df['quarter_encoded'] = pd.Categorical(df['quarter']).codes
            df['year_encoded'] = pd.Categorical(df['year']).codes
        
        # Fill NaN values
        df = df.fillna(0)
        
        # Define feature columns
        self.feature_columns = [col for col in df.columns if col not in [
            'date', 'daily_demand', 'sku', 'brand', 'brand_tier', 
            'day_of_week', 'month', 'quarter', 'year'
        ]]
        
        logger.info(f"✅ Feature engineering complete: {len(self.feature_columns)} features")
        return df
    
    def train_models(self, X, y):
        """Train machine learning models"""
        logger.info("🤖 Training models...")
        
        # Split data
        if self.use_gpu:
            X_train, X_test, y_train, y_test = cu_train_test_split(
                X, y, test_size=self.config['test_size'], random_state=self.config['random_state']
            )
        else:
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=self.config['test_size'], random_state=self.config['random_state']
            )
        
        # Scale features
        if self.use_gpu:
            self.scaler = cuStandardScaler()
        else:
            self.scaler = StandardScaler()
        
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)
        
        models = {}
        metrics = {}
        
        # 1. Random Forest
        logger.info("🌲 Training Random Forest...")
        if self.use_gpu:
            rf_model = cuRandomForestRegressor(
                n_estimators=self.config['n_estimators'],
                max_depth=self.config['max_depth'],
                random_state=self.config['random_state']
            )
        else:
            rf_model = RandomForestRegressor(
                n_estimators=self.config['n_estimators'],
                max_depth=self.config['max_depth'],
                random_state=self.config['random_state']
            )
        
        rf_model.fit(X_train_scaled, y_train)
        rf_pred = rf_model.predict(X_test_scaled)
        
        models['random_forest'] = rf_model
        if self.use_gpu:
            metrics['random_forest'] = {
                'mse': cu_mean_squared_error(y_test, rf_pred),
                'mae': cu_mean_absolute_error(y_test, rf_pred)
            }
        else:
            metrics['random_forest'] = {
                'mse': mean_squared_error(y_test, rf_pred),
                'mae': mean_absolute_error(y_test, rf_pred)
            }
        
        # 2. Linear Regression
        logger.info("📈 Training Linear Regression...")
        if self.use_gpu:
            lr_model = cuLinearRegression()
        else:
            lr_model = LinearRegression()
        
        lr_model.fit(X_train_scaled, y_train)
        lr_pred = lr_model.predict(X_test_scaled)
        
        models['linear_regression'] = lr_model
        if self.use_gpu:
            metrics['linear_regression'] = {
                'mse': cu_mean_squared_error(y_test, lr_pred),
                'mae': cu_mean_absolute_error(y_test, lr_pred)
            }
        else:
            metrics['linear_regression'] = {
                'mse': mean_squared_error(y_test, lr_pred),
                'mae': mean_absolute_error(y_test, lr_pred)
            }
        
        # 3. XGBoost (CPU only for now)
        if not self.use_gpu:
            logger.info("🚀 Training XGBoost...")
            xgb_model = xgb.XGBRegressor(
                n_estimators=100,
                max_depth=6,
                learning_rate=0.1,
                random_state=self.config['random_state']
            )
            xgb_model.fit(X_train_scaled, y_train)
            xgb_pred = xgb_model.predict(X_test_scaled)
            
            models['xgboost'] = xgb_model
            metrics['xgboost'] = {
                'mse': mean_squared_error(y_test, xgb_pred),
                'mae': mean_absolute_error(y_test, xgb_pred)
            }
        
        self.models = models
        
        # Log metrics
        for model_name, model_metrics in metrics.items():
            logger.info(f"✅ {model_name} - MSE: {model_metrics['mse']:.2f}, MAE: {model_metrics['mae']:.2f}")
        
        return models, metrics
    
    def generate_forecast(self, X_future, sku: str) -> Dict:
        """Generate forecast using trained models"""
        logger.info(f"🔮 Generating forecast for {sku}")
        
        if not self.models:
            raise ValueError("No models trained")
        
        # Scale future features
        X_future_scaled = self.scaler.transform(X_future)
        
        # Generate predictions from all models
        predictions = {}
        for model_name, model in self.models.items():
            pred = model.predict(X_future_scaled)
            if self.use_gpu:
                pred = pred.to_pandas().values if hasattr(pred, 'to_pandas') else pred
            predictions[model_name] = pred.tolist()
        
        # Ensemble prediction (simple average)
        ensemble_pred = np.mean([pred for pred in predictions.values()], axis=0)
        
        # Calculate confidence intervals (simplified)
        std_pred = np.std([pred for pred in predictions.values()], axis=0)
        confidence_intervals = {
            'lower': (ensemble_pred - 1.96 * std_pred).tolist(),
            'upper': (ensemble_pred + 1.96 * std_pred).tolist()
        }
        
        return {
            'predictions': ensemble_pred.tolist(),
            'confidence_intervals': confidence_intervals,
            'model_predictions': predictions,
            'forecast_date': datetime.now().isoformat()
        }
    
    async def run_batch_forecast(self) -> Dict:
        """Run batch forecasting for all SKUs"""
        logger.info("🚀 Starting RAPIDS GPU-accelerated batch forecasting...")
        
        await self.initialize_connection()
        skus = await self.get_all_skus()
        
        forecasts = {}
        successful_forecasts = 0
        
        for i, sku in enumerate(skus):
            try:
                logger.info(f"📊 Processing {sku} ({i+1}/{len(skus)})")
                
                # Extract historical data
                df = await self.extract_historical_data(sku)
                if df.empty:
                    logger.warning(f"⚠️ Skipping {sku} - no data")
                    continue
                
                # Engineer features
                df = self.engineer_features(df)
                if len(df) < 30:  # Need minimum data
                    logger.warning(f"⚠️ Skipping {sku} - insufficient data ({len(df)} rows)")
                    continue
                
                # Prepare features and target
                X = df[self.feature_columns].values
                y = df['daily_demand'].values
                
                # Train models
                models, metrics = self.train_models(X, y)
                
                # Generate future features for forecasting
                last_date = df['date'].iloc[-1] if hasattr(df['date'], 'iloc') else df['date'].values[-1]
                future_dates = pd.date_range(start=last_date + timedelta(days=1), periods=self.config['forecast_days'])
                
                # Create future feature matrix (simplified)
                X_future = np.zeros((self.config['forecast_days'], len(self.feature_columns)))
                for j, col in enumerate(self.feature_columns):
                    if 'lag' in col:
                        # Use recent values for lag features
                        X_future[:, j] = df[col].iloc[-1] if hasattr(df[col], 'iloc') else df[col].values[-1]
                    elif 'rolling' in col:
                        # Use recent rolling statistics
                        X_future[:, j] = df[col].iloc[-1] if hasattr(df[col], 'iloc') else df[col].values[-1]
                    else:
                        # Use default values for other features
                        X_future[:, j] = 0
                
                # Generate forecast
                forecast = self.generate_forecast(X_future, sku)
                forecasts[sku] = forecast
                successful_forecasts += 1
                
                logger.info(f"✅ {sku} forecast complete")
                
            except Exception as e:
                logger.error(f"❌ Failed to forecast {sku}: {e}")
                continue
        
        # Save forecasts
        output_file = "rapids_gpu_forecasts.json"
        with open(output_file, 'w') as f:
            json.dump(forecasts, f, indent=2)
        
        logger.info(f"🎉 RAPIDS GPU forecasting complete!")
        logger.info(f"📊 Generated forecasts for {successful_forecasts}/{len(skus)} SKUs")
        logger.info(f"💾 Forecasts saved to {output_file}")
        
        return {
            'forecasts': forecasts,
            'successful_forecasts': successful_forecasts,
            'total_skus': len(skus),
            'output_file': output_file,
            'gpu_acceleration': self.use_gpu
        }

async def main():
    """Main function"""
    logger.info("🚀 Starting RAPIDS GPU-accelerated demand forecasting...")
    
    agent = RAPIDSForecastingAgent()
    result = await agent.run_batch_forecast()
    
    print(f"\n🎉 Forecasting Complete!")
    print(f"📊 SKUs processed: {result['successful_forecasts']}/{result['total_skus']}")
    print(f"💾 Output file: {result['output_file']}")
    print(f"🚀 GPU acceleration: {'✅ Enabled' if result['gpu_acceleration'] else '❌ Disabled (CPU fallback)'}")

if __name__ == "__main__":
    asyncio.run(main())
