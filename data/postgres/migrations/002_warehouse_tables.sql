-- Migration: 002_warehouse_tables.sql
-- Description: Create core warehouse operational tables
-- Version: 0.1.0
-- Created: 2024-01-01T00:00:00Z

-- Create warehouse locations table
CREATE TABLE IF NOT EXISTS warehouse_locations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    location_code VARCHAR(50) NOT NULL UNIQUE,
    location_name VARCHAR(200) NOT NULL,
    location_type VARCHAR(50) NOT NULL, -- 'zone', 'aisle', 'rack', 'shelf', 'bin'
    parent_location_id UUID REFERENCES warehouse_locations(id),
    coordinates JSONB, -- For 3D coordinates {x, y, z}
    dimensions JSONB, -- For physical dimensions {length, width, height}
    capacity JSONB, -- For capacity constraints
    status VARCHAR(20) DEFAULT 'active', -- 'active', 'inactive', 'maintenance'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create equipment table
CREATE TABLE IF NOT EXISTS equipment (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    equipment_code VARCHAR(50) NOT NULL UNIQUE,
    equipment_name VARCHAR(200) NOT NULL,
    equipment_type VARCHAR(50) NOT NULL, -- 'forklift', 'conveyor', 'crane', 'scanner', etc.
    manufacturer VARCHAR(100),
    model VARCHAR(100),
    serial_number VARCHAR(100),
    status VARCHAR(20) DEFAULT 'operational', -- 'operational', 'maintenance', 'out_of_service'
    location_id UUID REFERENCES warehouse_locations(id),
    specifications JSONB,
    maintenance_schedule JSONB,
    last_maintenance_date DATE,
    next_maintenance_date DATE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create inventory_items table
CREATE TABLE IF NOT EXISTS inventory_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    item_code VARCHAR(50) NOT NULL UNIQUE,
    item_name VARCHAR(200) NOT NULL,
    description TEXT,
    category VARCHAR(100),
    subcategory VARCHAR(100),
    unit_of_measure VARCHAR(20) NOT NULL, -- 'pcs', 'kg', 'm', 'l', etc.
    dimensions JSONB, -- Physical dimensions
    weight DECIMAL(10,3),
    status VARCHAR(20) DEFAULT 'active', -- 'active', 'discontinued', 'recalled'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create inventory_locations table (many-to-many relationship)
CREATE TABLE IF NOT EXISTS inventory_locations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    item_id UUID NOT NULL REFERENCES inventory_items(id) ON DELETE CASCADE,
    location_id UUID NOT NULL REFERENCES warehouse_locations(id) ON DELETE CASCADE,
    quantity DECIMAL(15,3) NOT NULL DEFAULT 0,
    reserved_quantity DECIMAL(15,3) NOT NULL DEFAULT 0,
    available_quantity DECIMAL(15,3) GENERATED ALWAYS AS (quantity - reserved_quantity) STORED,
    min_quantity DECIMAL(15,3) DEFAULT 0,
    max_quantity DECIMAL(15,3),
    reorder_point DECIMAL(15,3),
    last_counted_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(item_id, location_id)
);

-- Create operations table
CREATE TABLE IF NOT EXISTS operations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    operation_code VARCHAR(50) NOT NULL UNIQUE,
    operation_name VARCHAR(200) NOT NULL,
    operation_type VARCHAR(50) NOT NULL, -- 'receiving', 'putaway', 'picking', 'shipping', 'cycle_count'
    status VARCHAR(20) DEFAULT 'pending', -- 'pending', 'in_progress', 'completed', 'cancelled'
    priority INTEGER DEFAULT 5, -- 1-10, 1 being highest
    assigned_to VARCHAR(100),
    equipment_id UUID REFERENCES equipment(id),
    source_location_id UUID REFERENCES warehouse_locations(id),
    target_location_id UUID REFERENCES warehouse_locations(id),
    scheduled_start TIMESTAMP WITH TIME ZONE,
    scheduled_end TIMESTAMP WITH TIME ZONE,
    actual_start TIMESTAMP WITH TIME ZONE,
    actual_end TIMESTAMP WITH TIME ZONE,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create operation_items table (items involved in operations)
CREATE TABLE IF NOT EXISTS operation_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    operation_id UUID NOT NULL REFERENCES operations(id) ON DELETE CASCADE,
    item_id UUID NOT NULL REFERENCES inventory_items(id),
    location_id UUID NOT NULL REFERENCES warehouse_locations(id),
    quantity DECIMAL(15,3) NOT NULL,
    unit_cost DECIMAL(10,2),
    status VARCHAR(20) DEFAULT 'pending', -- 'pending', 'completed', 'cancelled'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create safety_incidents table
CREATE TABLE IF NOT EXISTS safety_incidents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    incident_code VARCHAR(50) NOT NULL UNIQUE,
    incident_type VARCHAR(50) NOT NULL, -- 'injury', 'near_miss', 'equipment_failure', 'spill'
    severity VARCHAR(20) NOT NULL, -- 'low', 'medium', 'high', 'critical'
    status VARCHAR(20) DEFAULT 'open', -- 'open', 'investigating', 'resolved', 'closed'
    description TEXT NOT NULL,
    location_id UUID REFERENCES warehouse_locations(id),
    equipment_id UUID REFERENCES equipment(id),
    reported_by VARCHAR(100) NOT NULL,
    assigned_to VARCHAR(100),
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL,
    reported_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    resolved_at TIMESTAMP WITH TIME ZONE,
    resolution_notes TEXT,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_warehouse_locations_type ON warehouse_locations(location_type);
CREATE INDEX IF NOT EXISTS idx_warehouse_locations_status ON warehouse_locations(status);
CREATE INDEX IF NOT EXISTS idx_warehouse_locations_parent ON warehouse_locations(parent_location_id);

CREATE INDEX IF NOT EXISTS idx_equipment_type ON equipment(equipment_type);
CREATE INDEX IF NOT EXISTS idx_equipment_status ON equipment(status);
CREATE INDEX IF NOT EXISTS idx_equipment_location ON equipment(location_id);

CREATE INDEX IF NOT EXISTS idx_inventory_items_category ON inventory_items(category);
CREATE INDEX IF NOT EXISTS idx_inventory_items_status ON inventory_items(status);

CREATE INDEX IF NOT EXISTS idx_inventory_locations_item ON inventory_locations(item_id);
CREATE INDEX IF NOT EXISTS idx_inventory_locations_location ON inventory_locations(location_id);
CREATE INDEX IF NOT EXISTS idx_inventory_locations_available ON inventory_locations(available_quantity);

CREATE INDEX IF NOT EXISTS idx_operations_type ON operations(operation_type);
CREATE INDEX IF NOT EXISTS idx_operations_status ON operations(status);
CREATE INDEX IF NOT EXISTS idx_operations_priority ON operations(priority);
CREATE INDEX IF NOT EXISTS idx_operations_scheduled ON operations(scheduled_start);

CREATE INDEX IF NOT EXISTS idx_operation_items_operation ON operation_items(operation_id);
CREATE INDEX IF NOT EXISTS idx_operation_items_item ON operation_items(item_id);

CREATE INDEX IF NOT EXISTS idx_safety_incidents_type ON safety_incidents(incident_type);
CREATE INDEX IF NOT EXISTS idx_safety_incidents_severity ON safety_incidents(severity);
CREATE INDEX IF NOT EXISTS idx_safety_incidents_status ON safety_incidents(status);
CREATE INDEX IF NOT EXISTS idx_safety_incidents_occurred ON safety_incidents(occurred_at);

-- Add triggers for updated_at
CREATE TRIGGER tr_warehouse_locations_updated_at
    BEFORE UPDATE ON warehouse_locations
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER tr_equipment_updated_at
    BEFORE UPDATE ON equipment
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER tr_inventory_items_updated_at
    BEFORE UPDATE ON inventory_items
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER tr_inventory_locations_updated_at
    BEFORE UPDATE ON inventory_locations
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER tr_operations_updated_at
    BEFORE UPDATE ON operations
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER tr_operation_items_updated_at
    BEFORE UPDATE ON operation_items
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER tr_safety_incidents_updated_at
    BEFORE UPDATE ON safety_incidents
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Add audit triggers
CREATE TRIGGER tr_warehouse_locations_audit
    AFTER INSERT OR UPDATE OR DELETE ON warehouse_locations
    FOR EACH ROW
    EXECUTE FUNCTION audit_trigger_function();

CREATE TRIGGER tr_equipment_audit
    AFTER INSERT OR UPDATE OR DELETE ON equipment
    FOR EACH ROW
    EXECUTE FUNCTION audit_trigger_function();

CREATE TRIGGER tr_inventory_items_audit
    AFTER INSERT OR UPDATE OR DELETE ON inventory_items
    FOR EACH ROW
    EXECUTE FUNCTION audit_trigger_function();

CREATE TRIGGER tr_inventory_locations_audit
    AFTER INSERT OR UPDATE OR DELETE ON inventory_locations
    FOR EACH ROW
    EXECUTE FUNCTION audit_trigger_function();

CREATE TRIGGER tr_operations_audit
    AFTER INSERT OR UPDATE OR DELETE ON operations
    FOR EACH ROW
    EXECUTE FUNCTION audit_trigger_function();

CREATE TRIGGER tr_operation_items_audit
    AFTER INSERT OR UPDATE OR DELETE ON operation_items
    FOR EACH ROW
    EXECUTE FUNCTION audit_trigger_function();

CREATE TRIGGER tr_safety_incidents_audit
    AFTER INSERT OR UPDATE OR DELETE ON safety_incidents
    FOR EACH ROW
    EXECUTE FUNCTION audit_trigger_function();
