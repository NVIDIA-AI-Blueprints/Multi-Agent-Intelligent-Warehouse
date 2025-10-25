-- Model Tracking Tables for Dynamic Forecasting System
-- This script creates the necessary tables to track model performance dynamically

-- Table to track model training history
CREATE TABLE IF NOT EXISTS model_training_history (
    id SERIAL PRIMARY KEY,
    model_name VARCHAR(100) NOT NULL,
    training_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    training_type VARCHAR(50) NOT NULL, -- 'basic', 'advanced', 'retrain'
    accuracy_score DECIMAL(5,4),
    mape_score DECIMAL(6,2),
    training_duration_minutes INTEGER,
    models_trained INTEGER DEFAULT 1,
    status VARCHAR(20) DEFAULT 'completed', -- 'completed', 'failed', 'running'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Table to track model predictions and actual values for accuracy calculation
CREATE TABLE IF NOT EXISTS model_predictions (
    id SERIAL PRIMARY KEY,
    model_name VARCHAR(100) NOT NULL,
    sku VARCHAR(50) NOT NULL,
    prediction_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    predicted_value DECIMAL(10,2) NOT NULL,
    actual_value DECIMAL(10,2), -- NULL until actual value is known
    confidence_score DECIMAL(5,4),
    forecast_horizon_days INTEGER DEFAULT 30,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Table to track model performance metrics over time
CREATE TABLE IF NOT EXISTS model_performance_history (
    id SERIAL PRIMARY KEY,
    model_name VARCHAR(100) NOT NULL,
    evaluation_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    accuracy_score DECIMAL(5,4) NOT NULL,
    mape_score DECIMAL(6,2) NOT NULL,
    drift_score DECIMAL(5,4) NOT NULL,
    prediction_count INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL, -- 'HEALTHY', 'WARNING', 'NEEDS_RETRAINING'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Table for configuration settings (thresholds, etc.)
CREATE TABLE IF NOT EXISTS forecasting_config (
    id SERIAL PRIMARY KEY,
    config_key VARCHAR(100) UNIQUE NOT NULL,
    config_value TEXT NOT NULL,
    config_type VARCHAR(20) DEFAULT 'string', -- 'string', 'number', 'boolean'
    description TEXT,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Insert default configuration values
INSERT INTO forecasting_config (config_key, config_value, config_type, description) VALUES
('accuracy_threshold_healthy', '0.8', 'number', 'Minimum accuracy score for HEALTHY status'),
('accuracy_threshold_warning', '0.7', 'number', 'Minimum accuracy score for WARNING status'),
('drift_threshold_warning', '0.2', 'number', 'Maximum drift score for WARNING status'),
('drift_threshold_critical', '0.3', 'number', 'Maximum drift score before NEEDS_RETRAINING'),
('retraining_days_threshold', '7', 'number', 'Days since last training before WARNING status'),
('prediction_window_days', '7', 'number', 'Days to look back for prediction accuracy calculation'),
('confidence_threshold', '0.95', 'number', 'Maximum confidence score for reorder recommendations'),
('arrival_days_default', '5', 'number', 'Default days for estimated arrival date'),
('reorder_multiplier', '1.5', 'number', 'Multiplier for reorder point calculation')
ON CONFLICT (config_key) DO NOTHING;

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_model_training_history_model_name ON model_training_history(model_name);
CREATE INDEX IF NOT EXISTS idx_model_training_history_date ON model_training_history(training_date);
CREATE INDEX IF NOT EXISTS idx_model_predictions_model_name ON model_predictions(model_name);
CREATE INDEX IF NOT EXISTS idx_model_predictions_date ON model_predictions(prediction_date);
CREATE INDEX IF NOT EXISTS idx_model_predictions_sku ON model_predictions(sku);
CREATE INDEX IF NOT EXISTS idx_model_performance_model_name ON model_performance_history(model_name);
CREATE INDEX IF NOT EXISTS idx_model_performance_date ON model_performance_history(evaluation_date);

-- Insert sample training history data
INSERT INTO model_training_history (model_name, training_date, training_type, accuracy_score, mape_score, training_duration_minutes, models_trained, status) VALUES
('Random Forest', NOW() - INTERVAL '1 day', 'advanced', 0.85, 12.5, 15, 6, 'completed'),
('XGBoost', NOW() - INTERVAL '6 hours', 'advanced', 0.82, 15.8, 12, 6, 'completed'),
('Gradient Boosting', NOW() - INTERVAL '2 days', 'advanced', 0.78, 14.2, 18, 6, 'completed'),
('Linear Regression', NOW() - INTERVAL '3 days', 'basic', 0.72, 18.7, 8, 4, 'completed'),
('Ridge Regression', NOW() - INTERVAL '1 day', 'advanced', 0.75, 16.3, 14, 6, 'completed'),
('Support Vector Regression', NOW() - INTERVAL '4 days', 'basic', 0.70, 20.1, 10, 4, 'completed')
ON CONFLICT DO NOTHING;

-- Insert sample prediction data for accuracy calculation
INSERT INTO model_predictions (model_name, sku, predicted_value, actual_value, confidence_score) VALUES
('Random Forest', 'FRI004', 45.2, 43.8, 0.92),
('Random Forest', 'TOS005', 38.7, 41.2, 0.89),
('Random Forest', 'DOR005', 52.1, 49.8, 0.94),
('XGBoost', 'FRI004', 44.8, 43.8, 0.91),
('XGBoost', 'TOS005', 39.1, 41.2, 0.87),
('XGBoost', 'DOR005', 51.9, 49.8, 0.93),
('Gradient Boosting', 'CHE005', 36.5, 38.2, 0.88),
('Gradient Boosting', 'LAY006', 42.3, 40.1, 0.90),
('Linear Regression', 'FRI004', 46.1, 43.8, 0.85),
('Linear Regression', 'TOS005', 37.9, 41.2, 0.82),
('Ridge Regression', 'DOR005', 50.8, 49.8, 0.89),
('Support Vector Regression', 'CHE005', 35.7, 38.2, 0.83)
ON CONFLICT DO NOTHING;

-- Insert sample performance history
INSERT INTO model_performance_history (model_name, accuracy_score, mape_score, drift_score, prediction_count, status) VALUES
('Random Forest', 0.85, 12.5, 0.15, 1250, 'HEALTHY'),
('XGBoost', 0.82, 15.8, 0.18, 1180, 'HEALTHY'),
('Gradient Boosting', 0.78, 14.2, 0.22, 1100, 'WARNING'),
('Linear Regression', 0.72, 18.7, 0.31, 980, 'NEEDS_RETRAINING'),
('Ridge Regression', 0.75, 16.3, 0.25, 1050, 'WARNING'),
('Support Vector Regression', 0.70, 20.1, 0.35, 920, 'NEEDS_RETRAINING')
ON CONFLICT DO NOTHING;

-- Create a view for easy access to current model status
CREATE OR REPLACE VIEW current_model_status AS
SELECT 
    mth.model_name,
    mth.training_date as last_training_date,
    mph.accuracy_score,
    mph.mape_score,
    mph.drift_score,
    mph.prediction_count,
    mph.status,
    mph.evaluation_date
FROM model_training_history mth
LEFT JOIN LATERAL (
    SELECT *
    FROM model_performance_history mph2
    WHERE mph2.model_name = mth.model_name
    ORDER BY mph2.evaluation_date DESC
    LIMIT 1
) mph ON true
WHERE mth.training_date = (
    SELECT MAX(training_date)
    FROM model_training_history mth2
    WHERE mth2.model_name = mth.model_name
);

-- Grant permissions
GRANT SELECT, INSERT, UPDATE ON model_training_history TO warehouse;
GRANT SELECT, INSERT, UPDATE ON model_predictions TO warehouse;
GRANT SELECT, INSERT, UPDATE ON model_performance_history TO warehouse;
GRANT SELECT, INSERT, UPDATE ON forecasting_config TO warehouse;
GRANT SELECT ON current_model_status TO warehouse;

COMMENT ON TABLE model_training_history IS 'Tracks model training sessions and their outcomes';
COMMENT ON TABLE model_predictions IS 'Stores model predictions and actual values for accuracy calculation';
COMMENT ON TABLE model_performance_history IS 'Historical model performance metrics over time';
COMMENT ON TABLE forecasting_config IS 'Configuration settings for forecasting thresholds and parameters';
COMMENT ON VIEW current_model_status IS 'Current status of all models with latest performance metrics';
