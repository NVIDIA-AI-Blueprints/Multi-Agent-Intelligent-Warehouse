-- Rollback for initial schema migration
-- This will remove all created tables and schemas

-- Drop triggers first
DROP TRIGGER IF EXISTS update_equipment_assets_updated_at ON warehouse.equipment_assets;
DROP TRIGGER IF EXISTS update_equipment_assignments_updated_at ON warehouse.equipment_assignments;
DROP TRIGGER IF EXISTS update_maintenance_schedule_updated_at ON warehouse.maintenance_schedule;
DROP TRIGGER IF EXISTS update_safety_incidents_updated_at ON warehouse.safety_incidents;
DROP TRIGGER IF EXISTS update_safety_procedures_updated_at ON warehouse.safety_procedures;
DROP TRIGGER IF EXISTS update_tasks_updated_at ON warehouse.tasks;

-- Drop function
DROP FUNCTION IF EXISTS update_updated_at_column();

-- Drop tables
DROP TABLE IF EXISTS telemetry.equipment_telemetry CASCADE;
DROP TABLE IF EXISTS warehouse.tasks CASCADE;
DROP TABLE IF EXISTS warehouse.safety_procedures CASCADE;
DROP TABLE IF EXISTS warehouse.safety_incidents CASCADE;
DROP TABLE IF EXISTS warehouse.maintenance_schedule CASCADE;
DROP TABLE IF EXISTS warehouse.equipment_assignments CASCADE;
DROP TABLE IF EXISTS warehouse.equipment_assets CASCADE;

-- Drop schemas
DROP SCHEMA IF EXISTS telemetry CASCADE;
DROP SCHEMA IF EXISTS warehouse CASCADE;
