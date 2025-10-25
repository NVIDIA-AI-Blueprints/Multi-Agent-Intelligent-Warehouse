#!/usr/bin/env python3
"""
Phase 3: Advanced RAPIDS cuML Model Implementation

Implements GPU-accelerated ensemble models with hyperparameter optimization,
cross-validation, and model selection using NVIDIA RAPIDS cuML.
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
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
import optuna
from optuna.samplers import TPESampler

# RAPIDS cuML imports (will be available in container)
try:
    import cudf
    import cuml
    from cuml.ensemble import RandomForestRegressor as cuRF
    from cuml.linear_model import LinearRegression as cuLR
    from cuml.svm import SVR as cuSVR
    from cuml.metrics import mean_squared_error as cu_mse, mean_absolute_error as cu_mae
    from cuml.preprocessing import StandardScaler as cuStandardScaler
    RAPIDS_AVAILABLE = True
except ImportError:
    RAPIDS_AVAILABLE = False
    print("⚠️  RAPIDS cuML not available. Running in CPU mode.")

# Fallback to CPU libraries
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.linear_model import LinearRegression, Ridge, Lasso
from sklearn.svm import SVR
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import GridSearchCV
import xgboost as xgb

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class ModelConfig:
    """Advanced model configuration"""
    prediction_horizon_days: int = 30
    lookback_days: int = 180
    min_training_samples: int = 30
    validation_split: float = 0.2
    test_split: float = 0.1
    cross_validation_folds: int = 5
    hyperparameter_trials: int = 100
    ensemble_weights: Dict[str, float] = None
    use_gpu: bool = True
    
    def __post_init__(self):
        if self.ensemble_weights is None:
            self.ensemble_weights = {
                'random_forest': 0.25,
                'gradient_boosting': 0.2,
                'xgboost': 0.25,
                'linear_regression': 0.15,
                'ridge_regression': 0.1,
                'svr': 0.05
            }

@dataclass
class ModelPerformance:
    """Model performance metrics"""
    model_name: str
    mse: float
    mae: float
    rmse: float
    r2: float
    mape: float
    training_time: float
    prediction_time: float
    cross_val_scores: List[float]
    best_params: Dict[str, Any]

class AdvancedRAPIDSForecastingAgent:
    """Advanced GPU-accelerated demand forecasting agent with cuML"""
    
    def __init__(self, config: ModelConfig = None):
        self.config = config or ModelConfig()
        self.pg_conn = None
        self.models = {}
        self.scalers = {}
        self.feature_columns = []
        self.model_performance = {}
        self.use_gpu = RAPIDS_AVAILABLE and self.config.use_gpu
        
        if self.use_gpu:
            logger.info("🚀 NVIDIA RAPIDS cuML initialized - GPU acceleration enabled")
        else:
            logger.warning("⚠️  Running in CPU mode - install RAPIDS for GPU acceleration")

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

    async def extract_historical_data(self, sku: str) -> pd.DataFrame:
        """Extract and preprocess historical demand data"""
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
            AND timestamp >= NOW() - INTERVAL '{self.config.lookback_days} days'
        GROUP BY DATE(timestamp)
        ORDER BY date
        """
        
        results = await self.pg_conn.fetch(query, sku)
        
        if not results:
            raise ValueError(f"No historical data found for SKU {sku}")
        
        # Convert to DataFrame
        if self.use_gpu:
            df = cudf.DataFrame([dict(row) for row in results])
        else:
            df = pd.DataFrame([dict(row) for row in results])
        
        df['sku'] = sku
        logger.info(f"📈 Extracted {len(df)} days of historical data")
        return df

    def engineer_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Advanced feature engineering"""
        logger.info("🔧 Engineering advanced features...")
        
        # Sort by date
        df = df.sort_values('date').reset_index(drop=True)
        
        # Lag features
        for lag in [1, 3, 7, 14, 30]:
            df[f'demand_lag_{lag}'] = df['daily_demand'].shift(lag)
        
        # Rolling statistics
        for window in [7, 14, 30]:
            df[f'demand_rolling_mean_{window}'] = df['daily_demand'].rolling(window=window).mean()
            df[f'demand_rolling_std_{window}'] = df['daily_demand'].rolling(window=window).std()
            df[f'demand_rolling_max_{window}'] = df['daily_demand'].rolling(window=window).max()
            df[f'demand_rolling_min_{window}'] = df['daily_demand'].rolling(window=window).min()
        
        # Advanced trend features
        df['demand_trend_7'] = df['daily_demand'].rolling(window=7).apply(
            lambda x: np.polyfit(range(len(x)), x, 1)[0] if len(x) == 7 else 0
        )
        df['demand_trend_14'] = df['daily_demand'].rolling(window=14).apply(
            lambda x: np.polyfit(range(len(x)), x, 1)[0] if len(x) == 14 else 0
        )
        
        # Seasonal decomposition
        df['demand_seasonal'] = df.groupby('day_of_week')['daily_demand'].transform('mean')
        df['demand_monthly_seasonal'] = df.groupby('month')['daily_demand'].transform('mean')
        
        # Promotional impact
        df['promotional_boost'] = 1.0
        df.loc[df['is_super_bowl'] == 1, 'promotional_boost'] = 2.5
        df.loc[df['is_july_4th'] == 1, 'promotional_boost'] = 2.0
        
        # Interaction features
        df['weekend_summer'] = df['is_weekend'] * df['is_summer']
        df['holiday_weekend'] = df['is_holiday_season'] * df['is_weekend']
        
        # Brand features
        df['brand'] = df['sku'].str[:3]
        brand_mapping = {
            'LAY': 'mainstream', 'DOR': 'premium', 'CHE': 'mainstream',
            'TOS': 'premium', 'FRI': 'value', 'RUF': 'mainstream',
            'SUN': 'specialty', 'POP': 'specialty', 'FUN': 'mainstream', 'SMA': 'specialty'
        }
        df['brand_tier'] = df['brand'].map(brand_mapping)
        df['brand_encoded'] = pd.Categorical(df['brand']).codes
        df['brand_tier_encoded'] = pd.Categorical(df['brand_tier']).codes
        
        # Advanced statistical features
        df['demand_zscore_7'] = (df['daily_demand'] - df['demand_rolling_mean_7']) / df['demand_rolling_std_7']
        df['demand_percentile_30'] = df['daily_demand'].rolling(window=30).rank(pct=True)
        
        # Remove NaN values
        df = df.dropna()
        
        self.feature_columns = [col for col in df.columns if col not in ['date', 'daily_demand', 'sku', 'brand', 'brand_tier']]
        logger.info(f"✅ Engineered {len(self.feature_columns)} advanced features")
        
        return df

    def optimize_hyperparameters(self, X_train: pd.DataFrame, y_train: pd.Series, model_name: str) -> Dict[str, Any]:
        """Hyperparameter optimization using Optuna"""
        logger.info(f"🔍 Optimizing hyperparameters for {model_name}...")
        
        def objective(trial):
            if model_name == 'random_forest':
                params = {
                    'n_estimators': trial.suggest_int('n_estimators', 50, 200),
                    'max_depth': trial.suggest_int('max_depth', 5, 20),
                    'min_samples_split': trial.suggest_int('min_samples_split', 2, 10),
                    'min_samples_leaf': trial.suggest_int('min_samples_leaf', 1, 5),
                    'max_features': trial.suggest_categorical('max_features', ['sqrt', 'log2', None])
                }
                if self.use_gpu:
                    model = cuRF(**params)
                else:
                    model = RandomForestRegressor(**params, random_state=42)
                    
            elif model_name == 'gradient_boosting':
                params = {
                    'n_estimators': trial.suggest_int('n_estimators', 50, 200),
                    'max_depth': trial.suggest_int('max_depth', 3, 10),
                    'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.3),
                    'subsample': trial.suggest_float('subsample', 0.6, 1.0)
                }
                model = GradientBoostingRegressor(**params, random_state=42)
                
            elif model_name == 'xgboost':
                params = {
                    'n_estimators': trial.suggest_int('n_estimators', 50, 300),
                    'max_depth': trial.suggest_int('max_depth', 3, 12),
                    'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.3),
                    'subsample': trial.suggest_float('subsample', 0.6, 1.0),
                    'colsample_bytree': trial.suggest_float('colsample_bytree', 0.6, 1.0),
                    'reg_alpha': trial.suggest_float('reg_alpha', 0.0, 10.0),
                    'reg_lambda': trial.suggest_float('reg_lambda', 0.0, 10.0)
                }
                model = xgb.XGBRegressor(**params, random_state=42)
                
            elif model_name == 'ridge_regression':
                params = {
                    'alpha': trial.suggest_float('alpha', 0.1, 100.0, log=True)
                }
                model = Ridge(**params, random_state=42)
                
            elif model_name == 'svr':
                params = {
                    'C': trial.suggest_float('C', 0.1, 100.0, log=True),
                    'gamma': trial.suggest_categorical('gamma', ['scale', 'auto']),
                    'kernel': trial.suggest_categorical('kernel', ['rbf', 'linear', 'poly'])
                }
                if self.use_gpu:
                    model = cuSVR(**params)
                else:
                    model = SVR(**params)
            
            # Cross-validation
            tscv = TimeSeriesSplit(n_splits=self.config.cross_validation_folds)
            scores = []
            
            for train_idx, val_idx in tscv.split(X_train):
                if isinstance(X_train, np.ndarray):
                    X_tr, X_val = X_train[train_idx], X_train[val_idx]
                else:
                    X_tr, X_val = X_train.iloc[train_idx], X_train.iloc[val_idx]
                
                if isinstance(y_train, np.ndarray):
                    y_tr, y_val = y_train[train_idx], y_train[val_idx]
                else:
                    y_tr, y_val = y_train.iloc[train_idx], y_train.iloc[val_idx]
                
                model.fit(X_tr, y_tr)
                pred = model.predict(X_val)
                score = mean_squared_error(y_val, pred)
                scores.append(score)
            
            return np.mean(scores)
        
        study = optuna.create_study(direction='minimize', sampler=TPESampler())
        study.optimize(objective, n_trials=self.config.hyperparameter_trials)
        
        logger.info(f"✅ Best parameters for {model_name}: {study.best_params}")
        return study.best_params

    def train_advanced_models(self, df: pd.DataFrame) -> Tuple[Dict[str, any], Dict[str, ModelPerformance]]:
        """Train advanced models with hyperparameter optimization"""
        logger.info("🤖 Training advanced models with hyperparameter optimization...")
        
        X = df[self.feature_columns]
        y = df['daily_demand']
        
        # Split data
        train_size = int(len(df) * (1 - self.config.validation_split - self.config.test_split))
        val_size = int(len(df) * self.config.validation_split)
        
        X_train = X[:train_size]
        X_val = X[train_size:train_size + val_size]
        X_test = X[train_size + val_size:]
        
        y_train = y[:train_size]
        y_val = y[train_size:train_size + val_size]
        y_test = y[train_size + val_size:]
        
        models = {}
        performance = {}
        
        # Scale features
        if self.use_gpu:
            scaler = cuStandardScaler()
        else:
            scaler = StandardScaler()
        
        X_train_scaled = scaler.fit_transform(X_train)
        X_val_scaled = scaler.transform(X_val)
        X_test_scaled = scaler.transform(X_test)
        
        self.scalers['main'] = scaler
        
        # Train each model with hyperparameter optimization
        model_configs = {
            'random_forest': {'weight': 0.25},
            'gradient_boosting': {'weight': 0.2},
            'xgboost': {'weight': 0.25},
            'linear_regression': {'weight': 0.15},
            'ridge_regression': {'weight': 0.1},
            'svr': {'weight': 0.05}
        }
        
        for model_name, config in model_configs.items():
            logger.info(f"🔧 Training {model_name}...")
            
            # Optimize hyperparameters
            best_params = self.optimize_hyperparameters(X_train_scaled, y_train, model_name)
            
            # Train final model
            start_time = datetime.now()
            
            if model_name == 'random_forest':
                if self.use_gpu:
                    model = cuRF(**best_params)
                else:
                    model = RandomForestRegressor(**best_params, random_state=42)
                    
            elif model_name == 'gradient_boosting':
                model = GradientBoostingRegressor(**best_params, random_state=42)
                
            elif model_name == 'xgboost':
                model = xgb.XGBRegressor(**best_params, random_state=42)
                
            elif model_name == 'linear_regression':
                if self.use_gpu:
                    model = cuLR()
                else:
                    model = LinearRegression()
                    
            elif model_name == 'ridge_regression':
                model = Ridge(**best_params, random_state=42)
                
            elif model_name == 'svr':
                if self.use_gpu:
                    model = cuSVR(**best_params)
                else:
                    model = SVR(**best_params)
            
            model.fit(X_train_scaled, y_train)
            training_time = (datetime.now() - start_time).total_seconds()
            
            # Evaluate model
            start_time = datetime.now()
            y_pred = model.predict(X_test_scaled)
            prediction_time = (datetime.now() - start_time).total_seconds()
            
            # Calculate metrics
            mse = mean_squared_error(y_test, y_pred)
            mae = mean_absolute_error(y_test, y_pred)
            rmse = np.sqrt(mse)
            r2 = r2_score(y_test, y_pred)
            mape = np.mean(np.abs((y_test - y_pred) / y_test)) * 100
            
            # Cross-validation scores
            tscv = TimeSeriesSplit(n_splits=self.config.cross_validation_folds)
            cv_scores = []
            
            for train_idx, val_idx in tscv.split(X_train_scaled):
                X_tr, X_val_cv = X_train_scaled[train_idx], X_train_scaled[val_idx]
                if isinstance(y_train, np.ndarray):
                    y_tr, y_val_cv = y_train[train_idx], y_train[val_idx]
                else:
                    y_tr, y_val_cv = y_train.iloc[train_idx], y_train.iloc[val_idx]
                
                model_cv = model.__class__(**best_params) if hasattr(model, '__class__') else model
                model_cv.fit(X_tr, y_tr)
                pred_cv = model_cv.predict(X_val_cv)
                score_cv = mean_squared_error(y_val_cv, pred_cv)
                cv_scores.append(score_cv)
            
            models[model_name] = model
            performance[model_name] = ModelPerformance(
                model_name=model_name,
                mse=mse,
                mae=mae,
                rmse=rmse,
                r2=r2,
                mape=mape,
                training_time=training_time,
                prediction_time=prediction_time,
                cross_val_scores=cv_scores,
                best_params=best_params
            )
            
            logger.info(f"✅ {model_name} - RMSE: {rmse:.2f}, R²: {r2:.3f}, MAPE: {mape:.1f}%")
        
        self.model_performance = performance
        logger.info("✅ All advanced models trained successfully")
        return models, performance

    def generate_ensemble_forecast(self, models: Dict, df: pd.DataFrame, horizon_days: int) -> Dict[str, Any]:
        """Generate ensemble forecast with uncertainty quantification"""
        logger.info(f"🔮 Generating {horizon_days}-day ensemble forecast...")
        
        # Get latest features
        latest_features = df[self.feature_columns].iloc[-1:].values
        latest_features_scaled = self.scalers['main'].transform(latest_features)
        
        predictions = {}
        model_predictions = {}
        
        # Generate predictions from each model
        for model_name, model in models.items():
            # Simple approach: use last known features for all future predictions
            pred = model.predict(latest_features_scaled)[0]
            model_predictions[model_name] = [pred] * horizon_days
        
        # Weighted ensemble prediction
        ensemble_pred = np.zeros(horizon_days)
        weights = self.config.ensemble_weights
        
        for model_name, pred in model_predictions.items():
            weight = weights.get(model_name, 0.2)
            ensemble_pred += weight * np.array(pred)
        
        # Calculate uncertainty
        pred_std = np.std(list(model_predictions.values()), axis=0)
        confidence_intervals = []
        
        for i, (pred, std) in enumerate(zip(ensemble_pred, pred_std)):
            ci_lower = max(0, pred - 1.96 * std)
            ci_upper = pred + 1.96 * std
            confidence_intervals.append((ci_lower, ci_upper))
        
        # Feature importance (from Random Forest)
        feature_importance = {}
        if 'random_forest' in models:
            rf_model = models['random_forest']
            if hasattr(rf_model, 'feature_importances_'):
                for i, feature in enumerate(self.feature_columns):
                    feature_importance[feature] = float(rf_model.feature_importances_[i])
        
        return {
            'predictions': ensemble_pred.tolist(),
            'confidence_intervals': confidence_intervals,
            'model_predictions': model_predictions,
            'feature_importance': feature_importance,
            'ensemble_weights': weights,
            'uncertainty_std': pred_std.tolist()
        }

    async def forecast_demand_advanced(self, sku: str, horizon_days: int = None) -> Dict[str, Any]:
        """Advanced demand forecasting with hyperparameter optimization"""
        if horizon_days is None:
            horizon_days = self.config.prediction_horizon_days
        
        logger.info(f"🎯 Advanced forecasting for {sku} ({horizon_days} days)")
        
        try:
            # Extract and engineer features
            df = await self.extract_historical_data(sku)
            df = self.engineer_features(df)
            
            if len(df) < self.config.min_training_samples:
                raise ValueError(f"Insufficient data for {sku}: {len(df)} samples")
            
            # Train advanced models
            models, performance = self.train_advanced_models(df)
            
            # Generate ensemble forecast
            forecast = self.generate_ensemble_forecast(models, df, horizon_days)
            
            # Add performance metrics
            forecast['model_performance'] = {
                name: {
                    'mse': perf.mse,
                    'mae': perf.mae,
                    'rmse': perf.rmse,
                    'r2': perf.r2,
                    'mape': perf.mape,
                    'training_time': perf.training_time,
                    'prediction_time': perf.prediction_time,
                    'cv_scores_mean': np.mean(perf.cross_val_scores),
                    'cv_scores_std': np.std(perf.cross_val_scores)
                }
                for name, perf in performance.items()
            }
            
            forecast['sku'] = sku
            forecast['forecast_date'] = datetime.now().isoformat()
            forecast['horizon_days'] = horizon_days
            forecast['gpu_acceleration'] = self.use_gpu
            
            logger.info(f"✅ Advanced forecast completed for {sku}")
            return forecast
            
        except Exception as e:
            logger.error(f"❌ Advanced forecasting failed for {sku}: {e}")
            raise

    async def run_advanced_forecasting(self, skus: List[str] = None, horizon_days: int = 30):
        """Run advanced forecasting pipeline"""
        logger.info("🚀 Starting Phase 3: Advanced RAPIDS Demand Forecasting...")
        
        try:
            await self.initialize_connection()
            
            # Get SKUs to forecast
            if skus is None:
                query = "SELECT DISTINCT sku FROM inventory_movements WHERE movement_type = 'outbound' LIMIT 5"
                sku_results = await self.pg_conn.fetch(query)
                skus = [row['sku'] for row in sku_results]
            
            logger.info(f"📈 Advanced forecasting for {len(skus)} SKUs")
            
            # Generate forecasts
            forecasts = {}
            for sku in skus:
                try:
                    forecasts[sku] = await self.forecast_demand_advanced(sku, horizon_days)
                except Exception as e:
                    logger.error(f"Failed to forecast {sku}: {e}")
                    continue
            
            # Save results
            with open('phase3_advanced_forecasts.json', 'w') as f:
                json.dump(forecasts, f, indent=2, default=str)
            
            logger.info("🎉 Phase 3: Advanced forecasting completed!")
            logger.info(f"📊 Generated advanced forecasts for {len(forecasts)} SKUs")
            
            # Show performance summary
            if forecasts:
                sample_sku = list(forecasts.keys())[0]
                sample_forecast = forecasts[sample_sku]
                logger.info(f"📈 Sample advanced forecast for {sample_sku}:")
                logger.info(f"   • Next 7 days: {[round(p, 1) for p in sample_forecast['predictions'][:7]]}")
                logger.info(f"   • GPU acceleration: {sample_forecast['gpu_acceleration']}")
                
                # Show model performance
                perf = sample_forecast['model_performance']
                logger.info("🏆 Model Performance Summary:")
                for model_name, metrics in perf.items():
                    logger.info(f"   • {model_name}: RMSE={metrics['rmse']:.2f}, R²={metrics['r2']:.3f}, MAPE={metrics['mape']:.1f}%")
            
        except Exception as e:
            logger.error(f"❌ Error in advanced forecasting: {e}")
            raise
        finally:
            if self.pg_conn:
                await self.pg_conn.close()

async def main():
    """Main entry point for Phase 3"""
    config = ModelConfig(
        prediction_horizon_days=30,
        lookback_days=180,
        min_training_samples=30,
        cross_validation_folds=5,
        hyperparameter_trials=50  # Reduced for faster execution
    )
    
    agent = AdvancedRAPIDSForecastingAgent(config)
    
    # Test with a few SKUs
    test_skus = ['LAY001', 'LAY002', 'DOR001']
    await agent.run_advanced_forecasting(skus=test_skus, horizon_days=30)

if __name__ == "__main__":
    asyncio.run(main())
