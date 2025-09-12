-- Migration: 003_timescale_hypertables.sql
-- Description: Create TimescaleDB hypertables for time-series data
-- Version: 0.1.0
-- Created: 2024-01-01T00:00:00Z

-- Create telemetry_data table for IoT sensor data
CREATE TABLE IF NOT EXISTS telemetry_data (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    equipment_id UUID NOT NULL REFERENCES equipment(id),
    sensor_type VARCHAR(50) NOT NULL, -- 'temperature', 'humidity', 'vibration', 'pressure', etc.
    sensor_value DECIMAL(15,6) NOT NULL,
    unit VARCHAR(20) NOT NULL,
    quality_score DECIMAL(3,2), -- 0.00 to 1.00
    metadata JSONB,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Create operation_metrics table for operational KPIs
CREATE TABLE IF NOT EXISTS operation_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    operation_id UUID REFERENCES operations(id),
    metric_name VARCHAR(100) NOT NULL, -- 'duration', 'efficiency', 'accuracy', 'throughput'
    metric_value DECIMAL(15,6) NOT NULL,
    unit VARCHAR(20) NOT NULL,
    context JSONB, -- Additional context for the metric
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Create inventory_movements table for tracking inventory changes
CREATE TABLE IF NOT EXISTS inventory_movements (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    item_id UUID NOT NULL REFERENCES inventory_items(id),
    location_id UUID NOT NULL REFERENCES warehouse_locations(id),
    movement_type VARCHAR(50) NOT NULL, -- 'inbound', 'outbound', 'transfer', 'adjustment'
    quantity_change DECIMAL(15,3) NOT NULL, -- Positive for inbound, negative for outbound
    quantity_before DECIMAL(15,3) NOT NULL,
    quantity_after DECIMAL(15,3) NOT NULL,
    operation_id UUID REFERENCES operations(id),
    reference_document VARCHAR(100), -- PO number, SO number, etc.
    notes TEXT,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Create equipment_events table for equipment status changes and events
CREATE TABLE IF NOT EXISTS equipment_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    equipment_id UUID NOT NULL REFERENCES equipment(id),
    event_type VARCHAR(50) NOT NULL, -- 'start', 'stop', 'maintenance', 'error', 'warning'
    event_data JSONB,
    severity VARCHAR(20) DEFAULT 'info', -- 'info', 'warning', 'error', 'critical'
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Create performance_metrics table for system performance monitoring
CREATE TABLE IF NOT EXISTS performance_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    service_name VARCHAR(100) NOT NULL, -- 'chain_server', 'inventory_retriever', etc.
    metric_name VARCHAR(100) NOT NULL, -- 'response_time', 'memory_usage', 'cpu_usage', etc.
    metric_value DECIMAL(15,6) NOT NULL,
    unit VARCHAR(20) NOT NULL,
    tags JSONB, -- Additional tags for filtering
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Convert tables to TimescaleDB hypertables
-- Note: This requires TimescaleDB extension to be installed
-- CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Convert telemetry_data to hypertable
SELECT create_hypertable('telemetry_data', 'timestamp', if_not_exists => TRUE);

-- Convert operation_metrics to hypertable
SELECT create_hypertable('operation_metrics', 'timestamp', if_not_exists => TRUE);

-- Convert inventory_movements to hypertable
SELECT create_hypertable('inventory_movements', 'timestamp', if_not_exists => TRUE);

-- Convert equipment_events to hypertable
SELECT create_hypertable('equipment_events', 'timestamp', if_not_exists => TRUE);

-- Convert performance_metrics to hypertable
SELECT create_hypertable('performance_metrics', 'timestamp', if_not_exists => TRUE);

-- Create indexes for time-series queries
CREATE INDEX IF NOT EXISTS idx_telemetry_data_equipment_timestamp ON telemetry_data(equipment_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_telemetry_data_sensor_type ON telemetry_data(sensor_type, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_telemetry_data_timestamp ON telemetry_data(timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_operation_metrics_operation ON operation_metrics(operation_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_operation_metrics_name ON operation_metrics(metric_name, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_operation_metrics_timestamp ON operation_metrics(timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_inventory_movements_item ON inventory_movements(item_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_inventory_movements_location ON inventory_movements(location_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_inventory_movements_type ON inventory_movements(movement_type, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_inventory_movements_timestamp ON inventory_movements(timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_equipment_events_equipment ON equipment_events(equipment_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_equipment_events_type ON equipment_events(event_type, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_equipment_events_severity ON equipment_events(severity, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_equipment_events_timestamp ON equipment_events(timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_performance_metrics_service ON performance_metrics(service_name, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_performance_metrics_name ON performance_metrics(metric_name, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_performance_metrics_timestamp ON performance_metrics(timestamp DESC);

-- Create continuous aggregates for common queries
-- Daily equipment telemetry summary
CREATE MATERIALIZED VIEW IF NOT EXISTS daily_equipment_telemetry
WITH (timescaledb.continuous) AS
SELECT 
    equipment_id,
    sensor_type,
    DATE_TRUNC('day', timestamp) as day,
    AVG(sensor_value) as avg_value,
    MIN(sensor_value) as min_value,
    MAX(sensor_value) as max_value,
    COUNT(*) as sample_count
FROM telemetry_data
GROUP BY equipment_id, sensor_type, DATE_TRUNC('day', timestamp);

-- Create refresh policy for the continuous aggregate
SELECT add_continuous_aggregate_policy('daily_equipment_telemetry',
    start_offset => INTERVAL '1 day',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour');

-- Daily operation metrics summary
CREATE MATERIALIZED VIEW IF NOT EXISTS daily_operation_metrics
WITH (timescaledb.continuous) AS
SELECT 
    operation_id,
    metric_name,
    DATE_TRUNC('day', timestamp) as day,
    AVG(metric_value) as avg_value,
    MIN(metric_value) as min_value,
    MAX(metric_value) as max_value,
    COUNT(*) as sample_count
FROM operation_metrics
GROUP BY operation_id, metric_name, DATE_TRUNC('day', timestamp);

-- Create refresh policy for the continuous aggregate
SELECT add_continuous_aggregate_policy('daily_operation_metrics',
    start_offset => INTERVAL '1 day',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour');

-- Daily inventory movement summary
CREATE MATERIALIZED VIEW IF NOT EXISTS daily_inventory_movements
WITH (timescaledb.continuous) AS
SELECT 
    item_id,
    location_id,
    movement_type,
    DATE_TRUNC('day', timestamp) as day,
    SUM(quantity_change) as total_quantity_change,
    COUNT(*) as movement_count
FROM inventory_movements
GROUP BY item_id, location_id, movement_type, DATE_TRUNC('day', timestamp);

-- Create refresh policy for the continuous aggregate
SELECT add_continuous_aggregate_policy('daily_inventory_movements',
    start_offset => INTERVAL '1 day',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour');

-- Add data retention policies (keep data for 1 year by default)
SELECT add_retention_policy('telemetry_data', INTERVAL '1 year');
SELECT add_retention_policy('operation_metrics', INTERVAL '1 year');
SELECT add_retention_policy('inventory_movements', INTERVAL '1 year');
SELECT add_retention_policy('equipment_events', INTERVAL '1 year');
SELECT add_retention_policy('performance_metrics', INTERVAL '1 year');
