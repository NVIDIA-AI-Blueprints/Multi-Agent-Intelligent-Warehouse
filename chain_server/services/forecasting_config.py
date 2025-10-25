"""
Configuration system for forecasting parameters and thresholds
"""

import os
from typing import Dict, Any, Union
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

@dataclass
class ForecastingConfig:
    """Configuration class for forecasting parameters"""
    
    # Model Performance Thresholds
    accuracy_threshold_healthy: float = 0.8
    accuracy_threshold_warning: float = 0.7
    drift_threshold_warning: float = 0.2
    drift_threshold_critical: float = 0.3
    retraining_days_threshold: int = 7
    
    # Prediction and Accuracy Calculation
    prediction_window_days: int = 7
    historical_window_days: int = 14
    
    # Reorder Recommendations
    confidence_threshold: float = 0.95
    arrival_days_default: int = 5
    reorder_multiplier: float = 1.5
    
    # Model Status Determination
    min_prediction_count: int = 100
    accuracy_tolerance: float = 0.1  # 10% tolerance for accuracy calculation
    
    # Training Configuration
    max_training_history_days: int = 30
    min_models_for_ensemble: int = 3
    
    @classmethod
    def from_env(cls) -> 'ForecastingConfig':
        """Load configuration from environment variables"""
        return cls(
            accuracy_threshold_healthy=float(os.getenv('FORECASTING_ACCURACY_HEALTHY', '0.8')),
            accuracy_threshold_warning=float(os.getenv('FORECASTING_ACCURACY_WARNING', '0.7')),
            drift_threshold_warning=float(os.getenv('FORECASTING_DRIFT_WARNING', '0.2')),
            drift_threshold_critical=float(os.getenv('FORECASTING_DRIFT_CRITICAL', '0.3')),
            retraining_days_threshold=int(os.getenv('FORECASTING_RETRAINING_DAYS', '7')),
            prediction_window_days=int(os.getenv('FORECASTING_PREDICTION_WINDOW', '7')),
            historical_window_days=int(os.getenv('FORECASTING_HISTORICAL_WINDOW', '14')),
            confidence_threshold=float(os.getenv('FORECASTING_CONFIDENCE_THRESHOLD', '0.95')),
            arrival_days_default=int(os.getenv('FORECASTING_ARRIVAL_DAYS', '5')),
            reorder_multiplier=float(os.getenv('FORECASTING_REORDER_MULTIPLIER', '1.5')),
            min_prediction_count=int(os.getenv('FORECASTING_MIN_PREDICTIONS', '100')),
            accuracy_tolerance=float(os.getenv('FORECASTING_ACCURACY_TOLERANCE', '0.1')),
            max_training_history_days=int(os.getenv('FORECASTING_MAX_HISTORY_DAYS', '30')),
            min_models_for_ensemble=int(os.getenv('FORECASTING_MIN_MODELS', '3'))
        )
    
    @classmethod
    async def from_database(cls, db_pool) -> 'ForecastingConfig':
        """Load configuration from database"""
        try:
            query = """
            SELECT config_key, config_value, config_type
            FROM forecasting_config
            """
            
            async with db_pool.acquire() as conn:
                result = await conn.fetch(query)
                
            config_dict = {}
            for row in result:
                key = row['config_key']
                value = row['config_value']
                config_type = row['config_type']
                
                # Convert value based on type
                if config_type == 'number':
                    config_dict[key] = float(value)
                elif config_type == 'boolean':
                    config_dict[key] = value.lower() in ('true', '1', 'yes', 'on')
                else:
                    config_dict[key] = value
            
            return cls(**config_dict)
            
        except Exception as e:
            logger.warning(f"Could not load config from database: {e}")
            return cls.from_env()
    
    async def save_to_database(self, db_pool) -> None:
        """Save configuration to database"""
        try:
            config_items = [
                ('accuracy_threshold_healthy', str(self.accuracy_threshold_healthy), 'number'),
                ('accuracy_threshold_warning', str(self.accuracy_threshold_warning), 'number'),
                ('drift_threshold_warning', str(self.drift_threshold_warning), 'number'),
                ('drift_threshold_critical', str(self.drift_threshold_critical), 'number'),
                ('retraining_days_threshold', str(self.retraining_days_threshold), 'number'),
                ('prediction_window_days', str(self.prediction_window_days), 'number'),
                ('historical_window_days', str(self.historical_window_days), 'number'),
                ('confidence_threshold', str(self.confidence_threshold), 'number'),
                ('arrival_days_default', str(self.arrival_days_default), 'number'),
                ('reorder_multiplier', str(self.reorder_multiplier), 'number'),
                ('min_prediction_count', str(self.min_prediction_count), 'number'),
                ('accuracy_tolerance', str(self.accuracy_tolerance), 'number'),
                ('max_training_history_days', str(self.max_training_history_days), 'number'),
                ('min_models_for_ensemble', str(self.min_models_for_ensemble), 'number')
            ]
            
            async with db_pool.acquire() as conn:
                for key, value, config_type in config_items:
                    await conn.execute("""
                        INSERT INTO forecasting_config (config_key, config_value, config_type, updated_at)
                        VALUES ($1, $2, $3, NOW())
                        ON CONFLICT (config_key) 
                        DO UPDATE SET 
                            config_value = EXCLUDED.config_value,
                            config_type = EXCLUDED.config_type,
                            updated_at = NOW()
                    """, key, value, config_type)
            
            logger.info("Configuration saved to database")
            
        except Exception as e:
            logger.error(f"Could not save config to database: {e}")
            raise
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary"""
        return {
            'accuracy_threshold_healthy': self.accuracy_threshold_healthy,
            'accuracy_threshold_warning': self.accuracy_threshold_warning,
            'drift_threshold_warning': self.drift_threshold_warning,
            'drift_threshold_critical': self.drift_threshold_critical,
            'retraining_days_threshold': self.retraining_days_threshold,
            'prediction_window_days': self.prediction_window_days,
            'historical_window_days': self.historical_window_days,
            'confidence_threshold': self.confidence_threshold,
            'arrival_days_default': self.arrival_days_default,
            'reorder_multiplier': self.reorder_multiplier,
            'min_prediction_count': self.min_prediction_count,
            'accuracy_tolerance': self.accuracy_tolerance,
            'max_training_history_days': self.max_training_history_days,
            'min_models_for_ensemble': self.min_models_for_ensemble
        }
    
    def validate(self) -> bool:
        """Validate configuration values"""
        errors = []
        
        if not 0 <= self.accuracy_threshold_healthy <= 1:
            errors.append("accuracy_threshold_healthy must be between 0 and 1")
        
        if not 0 <= self.accuracy_threshold_warning <= 1:
            errors.append("accuracy_threshold_warning must be between 0 and 1")
        
        if self.accuracy_threshold_warning >= self.accuracy_threshold_healthy:
            errors.append("accuracy_threshold_warning must be less than accuracy_threshold_healthy")
        
        if not 0 <= self.drift_threshold_warning <= 1:
            errors.append("drift_threshold_warning must be between 0 and 1")
        
        if not 0 <= self.drift_threshold_critical <= 1:
            errors.append("drift_threshold_critical must be between 0 and 1")
        
        if self.drift_threshold_warning >= self.drift_threshold_critical:
            errors.append("drift_threshold_warning must be less than drift_threshold_critical")
        
        if self.retraining_days_threshold <= 0:
            errors.append("retraining_days_threshold must be positive")
        
        if self.prediction_window_days <= 0:
            errors.append("prediction_window_days must be positive")
        
        if self.historical_window_days <= 0:
            errors.append("historical_window_days must be positive")
        
        if not 0 <= self.confidence_threshold <= 1:
            errors.append("confidence_threshold must be between 0 and 1")
        
        if self.arrival_days_default <= 0:
            errors.append("arrival_days_default must be positive")
        
        if self.reorder_multiplier <= 0:
            errors.append("reorder_multiplier must be positive")
        
        if self.min_prediction_count <= 0:
            errors.append("min_prediction_count must be positive")
        
        if not 0 <= self.accuracy_tolerance <= 1:
            errors.append("accuracy_tolerance must be between 0 and 1")
        
        if self.max_training_history_days <= 0:
            errors.append("max_training_history_days must be positive")
        
        if self.min_models_for_ensemble <= 0:
            errors.append("min_models_for_ensemble must be positive")
        
        if errors:
            logger.error(f"Configuration validation errors: {errors}")
            return False
        
        return True

# Global configuration instance
_config: ForecastingConfig = None

def get_config() -> ForecastingConfig:
    """Get the global configuration instance"""
    global _config
    if _config is None:
        _config = ForecastingConfig.from_env()
    return _config

async def load_config_from_db(db_pool) -> ForecastingConfig:
    """Load configuration from database and set as global"""
    global _config
    _config = await ForecastingConfig.from_database(db_pool)
    return _config

async def save_config_to_db(config: ForecastingConfig, db_pool) -> None:
    """Save configuration to database"""
    await config.save_to_database(db_pool)
    global _config
    _config = config
