#!/usr/bin/env python3
"""
Generate demand forecasts for all 38 SKUs in the warehouse system.
This script creates comprehensive forecasts using multiple ML models.
"""

import asyncio
import asyncpg
import json
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.svm import SVR
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import mean_absolute_error, mean_squared_error
import warnings
warnings.filterwarnings('ignore')

class AllSKUForecastingEngine:
    def __init__(self):
        self.db_config = {
            'host': 'localhost',
            'port': 5435,
            'user': 'warehouse',
            'password': 'warehousepw',
            'database': 'warehouse'
        }
        self.conn = None
        self.models = {
            'Random Forest': RandomForestRegressor(n_estimators=100, random_state=42),
            'XGBoost': None,  # Will be set if available
            'Gradient Boosting': GradientBoostingRegressor(n_estimators=100, random_state=42),
            'Linear Regression': LinearRegression(),
            'Ridge Regression': Ridge(alpha=1.0),
            'Support Vector Regression': SVR(kernel='rbf', C=1.0, gamma='scale')
        }
        
        # Try to import XGBoost
        try:
            import xgboost as xgb
            self.models['XGBoost'] = xgb.XGBRegressor(
                n_estimators=100,
                max_depth=6,
                learning_rate=0.1,
                random_state=42,
                tree_method='hist',
                device='cuda' if self._check_cuda() else 'cpu'
            )
            print("✅ XGBoost loaded with GPU support" if self._check_cuda() else "✅ XGBoost loaded with CPU fallback")
        except ImportError:
            print("⚠️ XGBoost not available, using alternative models")
            del self.models['XGBoost']

    def _check_cuda(self):
        """Check if CUDA is available for XGBoost"""
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False

    async def connect_db(self):
        """Connect to PostgreSQL database"""
        try:
            self.conn = await asyncpg.connect(**self.db_config)
            print("✅ Connected to PostgreSQL database")
        except Exception as e:
            print(f"❌ Database connection failed: {e}")
            raise

    async def close_db(self):
        """Close database connection"""
        if self.conn:
            await self.conn.close()
            print("✅ Database connection closed")

    async def get_all_skus(self):
        """Get all SKUs from inventory"""
        query = "SELECT sku FROM inventory_items ORDER BY sku"
        rows = await self.conn.fetch(query)
        skus = [row['sku'] for row in rows]
        print(f"📦 Found {len(skus)} SKUs to forecast")
        return skus

    async def generate_historical_data(self, sku, days=365):
        """Generate realistic historical demand data for a SKU"""
        print(f"📊 Generating historical data for {sku}")
        
        # Base demand varies by SKU category
        category = sku[:3]
        base_demand = {
            'CHE': 35, 'DOR': 40, 'FRI': 30, 'FUN': 25, 'LAY': 45,
            'POP': 20, 'RUF': 35, 'SMA': 15, 'SUN': 25, 'TOS': 35
        }.get(category, 30)
        
        # Generate time series
        dates = pd.date_range(start=datetime.now() - timedelta(days=days), 
                             end=datetime.now() - timedelta(days=1), freq='D')
        
        # Create realistic demand patterns
        demand = []
        for i, date in enumerate(dates):
            # Base demand with seasonal variation
            seasonal_factor = 1 + 0.3 * np.sin(2 * np.pi * i / 365)  # Annual seasonality
            monthly_factor = 1 + 0.2 * np.sin(2 * np.pi * date.month / 12)  # Monthly seasonality
            
            # Weekend effect
            weekend_factor = 1.2 if date.weekday() >= 5 else 1.0
            
            # Holiday effects
            holiday_factor = 1.0
            if date.month == 12:  # December holidays
                holiday_factor = 1.5
            elif date.month == 7 and date.day == 4:  # July 4th
                holiday_factor = 1.3
            elif date.month == 2 and date.day == 14:  # Super Bowl (approximate)
                holiday_factor = 1.2
            
            # Random noise
            noise = np.random.normal(0, 0.1)
            
            # Calculate final demand
            final_demand = base_demand * seasonal_factor * monthly_factor * weekend_factor * holiday_factor
            final_demand = max(0, final_demand + noise)  # Ensure non-negative
            
            demand.append(round(final_demand, 2))
        
        return pd.DataFrame({
            'date': dates,
            'demand': demand,
            'sku': sku
        })

    def create_features(self, df):
        """Create advanced features for forecasting"""
        df = df.copy()
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').reset_index(drop=True)
        
        # Time-based features
        df['day_of_week'] = df['date'].dt.dayofweek
        df['month'] = df['date'].dt.month
        df['quarter'] = df['date'].dt.quarter
        df['year'] = df['date'].dt.year
        df['is_weekend'] = (df['day_of_week'] >= 5).astype(int)
        
        # Seasonal features
        df['is_summer'] = df['month'].isin([6, 7, 8]).astype(int)
        df['is_holiday_season'] = df['month'].isin([11, 12]).astype(int)
        df['is_super_bowl'] = ((df['month'] == 2) & (df['day_of_week'] == 6)).astype(int)
        df['is_july_4th'] = ((df['month'] == 7) & (df['date'].dt.day == 4)).astype(int)
        
        # Lag features
        for lag in [1, 3, 7, 14, 30]:
            df[f'demand_lag_{lag}'] = df['demand'].shift(lag)
        
        # Rolling statistics
        for window in [7, 14, 30]:
            df[f'demand_rolling_mean_{window}'] = df['demand'].rolling(window=window).mean()
            df[f'demand_rolling_std_{window}'] = df['demand'].rolling(window=window).std()
            df[f'demand_rolling_max_{window}'] = df['demand'].rolling(window=window).max()
        
        # Trend features
        df['demand_trend_7'] = df['demand'].rolling(window=7).apply(lambda x: np.polyfit(range(len(x)), x, 1)[0] if len(x) == 7 else 0)
        
        # Seasonal decomposition
        df['demand_seasonal'] = df['demand'].rolling(window=7).mean() - df['demand'].rolling(window=30).mean()
        df['demand_monthly_seasonal'] = df.groupby('month')['demand'].transform('mean') - df['demand'].mean()
        
        # Promotional features
        df['promotional_boost'] = np.random.uniform(0.8, 1.2, len(df))
        
        # Interaction features
        df['weekend_summer'] = df['is_weekend'] * df['is_summer']
        df['holiday_weekend'] = df['is_holiday_season'] * df['is_weekend']
        
        # Categorical encoding
        df['brand_encoded'] = pd.Categorical(df['sku'].str[:3]).codes
        df['brand_tier_encoded'] = pd.Categorical(df['sku'].str[3:]).codes
        df['day_of_week_encoded'] = pd.Categorical(df['day_of_week']).codes
        df['month_encoded'] = pd.Categorical(df['month']).codes
        df['quarter_encoded'] = pd.Categorical(df['quarter']).codes
        df['year_encoded'] = pd.Categorical(df['year']).codes
        
        return df

    def train_models(self, X_train, y_train):
        """Train all available models"""
        trained_models = {}
        
        for name, model in self.models.items():
            if model is None:
                continue
                
            try:
                print(f"🤖 Training {name}...")
                model.fit(X_train, y_train)
                trained_models[name] = model
                print(f"✅ {name} trained successfully")
            except Exception as e:
                print(f"❌ Failed to train {name}: {e}")
        
        return trained_models

    def generate_forecast(self, trained_models, X_future, horizon_days=30):
        """Generate forecast using ensemble of models"""
        predictions = {}
        confidence_intervals = {}
        feature_importance = {}
        
        for name, model in trained_models.items():
            try:
                # Generate predictions
                pred = model.predict(X_future)
                predictions[name] = pred
                
                # Calculate confidence intervals (simplified)
                if hasattr(model, 'predict_proba'):
                    # For models that support uncertainty
                    std_dev = np.std(pred) * 0.1  # Simplified uncertainty
                else:
                    std_dev = np.std(pred) * 0.15
                
                ci_lower = pred - 1.96 * std_dev
                ci_upper = pred + 1.96 * std_dev
                confidence_intervals[name] = list(zip(ci_lower, ci_upper))
                
                # Feature importance
                if hasattr(model, 'feature_importances_'):
                    feature_importance[name] = dict(zip(X_future.columns, model.feature_importances_))
                elif hasattr(model, 'coef_'):
                    feature_importance[name] = dict(zip(X_future.columns, abs(model.coef_)))
                
            except Exception as e:
                print(f"❌ Error generating forecast with {name}: {e}")
        
        return predictions, confidence_intervals, feature_importance

    async def forecast_sku(self, sku):
        """Generate comprehensive forecast for a single SKU"""
        print(f"\n🎯 Forecasting {sku}")
        
        # Generate historical data
        historical_df = await self.generate_historical_data(sku)
        
        # Create features
        feature_df = self.create_features(historical_df)
        
        # Prepare training data
        feature_columns = [col for col in feature_df.columns if col not in ['date', 'demand', 'sku']]
        X = feature_df[feature_columns].fillna(0)
        y = feature_df['demand']
        
        # Remove rows with NaN values
        valid_indices = ~(X.isna().any(axis=1) | y.isna())
        X = X[valid_indices]
        y = y[valid_indices]
        
        if len(X) < 30:  # Need minimum data for training
            print(f"⚠️ Insufficient data for {sku}, skipping")
            return None
        
        # Split data for training
        split_point = int(len(X) * 0.8)
        X_train, X_test = X[:split_point], X[split_point:]
        y_train, y_test = y[:split_point], y[split_point:]
        
        # Train models
        trained_models = self.train_models(X_train, y_train)
        
        if not trained_models:
            print(f"❌ No models trained successfully for {sku}")
            return None
        
        # Generate future features for forecasting
        last_date = feature_df['date'].max()
        future_dates = pd.date_range(start=last_date + timedelta(days=1), periods=30, freq='D')
        
        # Create future feature matrix
        future_features = []
        for i, date in enumerate(future_dates):
            # Use the last known values and extrapolate
            last_row = feature_df.iloc[-1].copy()
            last_row['date'] = date
            last_row['day_of_week'] = date.dayofweek
            last_row['month'] = date.month
            last_row['quarter'] = date.quarter
            last_row['year'] = date.year
            last_row['is_weekend'] = 1 if date.weekday() >= 5 else 0
            last_row['is_summer'] = 1 if date.month in [6, 7, 8] else 0
            last_row['is_holiday_season'] = 1 if date.month in [11, 12] else 0
            last_row['is_super_bowl'] = 1 if (date.month == 2 and date.weekday() == 6) else 0
            last_row['is_july_4th'] = 1 if (date.month == 7 and date.day == 4) else 0
            
            # Update lag features with predictions
            for lag in [1, 3, 7, 14, 30]:
                if i >= lag:
                    last_row[f'demand_lag_{lag}'] = future_features[i-lag]['demand'] if 'demand' in future_features[i-lag] else last_row[f'demand_lag_{lag}']
            
            future_features.append(last_row)
        
        future_df = pd.DataFrame(future_features)
        X_future = future_df[feature_columns].fillna(0)
        
        # Generate forecasts
        predictions, confidence_intervals, feature_importance = self.generate_forecast(
            trained_models, X_future
        )
        
        # Use ensemble average as final prediction
        ensemble_pred = np.mean([pred for pred in predictions.values()], axis=0)
        ensemble_ci = np.mean([ci for ci in confidence_intervals.values()], axis=0)
        
        # Calculate model performance metrics
        model_metrics = {}
        for name, model in trained_models.items():
            try:
                y_pred = model.predict(X_test)
                mae = mean_absolute_error(y_test, y_pred)
                rmse = np.sqrt(mean_squared_error(y_test, y_pred))
                mape = np.mean(np.abs((y_test - y_pred) / y_test)) * 100
                
                model_metrics[name] = {
                    'mae': mae,
                    'rmse': rmse,
                    'mape': mape,
                    'accuracy': max(0, 100 - mape)
                }
            except Exception as e:
                print(f"❌ Error calculating metrics for {name}: {e}")
        
        # Find best model
        best_model = min(model_metrics.keys(), key=lambda x: model_metrics[x]['mae'])
        
        result = {
            'sku': sku,
            'predictions': ensemble_pred.tolist(),
            'confidence_intervals': ensemble_ci.tolist(),
            'feature_importance': feature_importance.get(best_model, {}),
            'model_metrics': model_metrics,
            'best_model': best_model,
            'forecast_date': datetime.now().isoformat(),
            'horizon_days': 30,
            'training_samples': len(X_train),
            'test_samples': len(X_test)
        }
        
        print(f"✅ {sku} forecast complete - Best model: {best_model} (MAE: {model_metrics[best_model]['mae']:.2f})")
        return result

    async def generate_all_forecasts(self):
        """Generate forecasts for all SKUs"""
        print("🚀 Starting comprehensive SKU forecasting...")
        
        # Get all SKUs
        skus = await self.get_all_skus()
        
        # Generate forecasts for each SKU
        all_forecasts = {}
        successful_forecasts = 0
        
        for i, sku in enumerate(skus, 1):
            print(f"\n📊 Progress: {i}/{len(skus)} SKUs")
            try:
                forecast = await self.forecast_sku(sku)
                if forecast:
                    all_forecasts[sku] = forecast
                    successful_forecasts += 1
            except Exception as e:
                print(f"❌ Error forecasting {sku}: {e}")
        
        print(f"\n🎉 Forecasting complete!")
        print(f"✅ Successfully forecasted: {successful_forecasts}/{len(skus)} SKUs")
        
        return all_forecasts

    def save_forecasts(self, forecasts, filename='all_sku_forecasts.json'):
        """Save forecasts to JSON file"""
        try:
            with open(filename, 'w') as f:
                json.dump(forecasts, f, indent=2, default=str)
            print(f"💾 Forecasts saved to {filename}")
        except Exception as e:
            print(f"❌ Error saving forecasts: {e}")

async def main():
    """Main execution function"""
    engine = AllSKUForecastingEngine()
    
    try:
        await engine.connect_db()
        forecasts = await engine.generate_all_forecasts()
        engine.save_forecasts(forecasts)
        
        # Print summary
        print(f"\n📈 FORECASTING SUMMARY")
        print(f"Total SKUs: {len(forecasts)}")
        print(f"Forecast horizon: 30 days")
        print(f"Models used: {list(engine.models.keys())}")
        
        # Show sample results
        if forecasts:
            sample_sku = list(forecasts.keys())[0]
            sample_forecast = forecasts[sample_sku]
            print(f"\n📊 Sample forecast ({sample_sku}):")
            print(f"Best model: {sample_forecast['best_model']}")
            print(f"Training samples: {sample_forecast['training_samples']}")
            print(f"First 5 predictions: {sample_forecast['predictions'][:5]}")
        
    except Exception as e:
        print(f"❌ Error in main execution: {e}")
    finally:
        await engine.close_db()

if __name__ == "__main__":
    asyncio.run(main())
