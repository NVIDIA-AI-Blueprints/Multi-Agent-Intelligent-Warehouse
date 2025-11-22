CREATE TABLE IF NOT EXISTS inventory_items (
  id SERIAL PRIMARY KEY,
  sku TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  quantity INTEGER NOT NULL DEFAULT 0,
  location TEXT,
  reorder_point INTEGER DEFAULT 0,
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tasks (
  id SERIAL PRIMARY KEY,
  kind TEXT NOT NULL,          -- pick, pack, putaway, cycle_count
  status TEXT NOT NULL DEFAULT 'pending',
  assignee TEXT,
  payload JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS safety_incidents (
  id SERIAL PRIMARY KEY,
  severity TEXT,
  description TEXT,
  reported_by TEXT,
  occurred_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS equipment_telemetry (
  ts TIMESTAMPTZ NOT NULL,
  equipment_id TEXT NOT NULL,
  metric TEXT NOT NULL,
  value DOUBLE PRECISION NOT NULL
);

-- User role and status ENUM types
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'user_role') THEN
    CREATE TYPE user_role AS ENUM ('admin', 'manager', 'supervisor', 'operator', 'viewer');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'user_status') THEN
    CREATE TYPE user_status AS ENUM ('active', 'inactive', 'suspended', 'pending');
  END IF;
END $$;

-- User authentication and authorization tables
CREATE TABLE IF NOT EXISTS users (
  id SERIAL PRIMARY KEY,
  username TEXT UNIQUE NOT NULL,
  email TEXT UNIQUE NOT NULL,
  full_name TEXT NOT NULL,
  role user_role NOT NULL,
  status user_status NOT NULL DEFAULT 'active',
  hashed_password TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  last_login TIMESTAMPTZ
);

-- User sessions for token management
CREATE TABLE IF NOT EXISTS user_sessions (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  refresh_token_hash TEXT NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now(),
  is_revoked BOOLEAN DEFAULT FALSE
);

-- Audit log for user actions
CREATE TABLE IF NOT EXISTS audit_log (
  id SERIAL PRIMARY KEY,
  user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
  action TEXT NOT NULL,
  resource_type TEXT,
  resource_id TEXT,
  details JSONB DEFAULT '{}'::jsonb,
  ip_address INET,
  user_agent TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname=timescaledb) THEN
    CREATE EXTENSION IF NOT EXISTS timescaledb;
  END IF;
EXCEPTION WHEN OTHERS THEN NULL;
END $$;

DO $$
BEGIN
  PERFORM create_hypertable(equipment_telemetry,ts, if_not_exists=>TRUE);
EXCEPTION WHEN OTHERS THEN NULL;
END $$;

-- Sample Frito-Lay product data
INSERT INTO inventory_items (sku, name, quantity, location, reorder_point) VALUES
  ('LAY001', 'Lay''s Classic Potato Chips 9oz', 1250, 'Zone A-Aisle 1-Rack 2-Level 3', 200),
  ('LAY002', 'Lay''s Barbecue Potato Chips 9oz', 980, 'Zone A-Aisle 1-Rack 2-Level 2', 150),
  ('DOR001', 'Doritos Nacho Cheese Tortilla Chips 9.75oz', 1120, 'Zone A-Aisle 2-Rack 1-Level 3', 180),
  ('DOR002', 'Doritos Cool Ranch Tortilla Chips 9.75oz', 890, 'Zone A-Aisle 2-Rack 1-Level 2', 140),
  ('CHE001', 'Cheetos Crunchy Cheese Flavored Snacks 8.5oz', 750, 'Zone A-Aisle 3-Rack 2-Level 3', 120),
  ('CHE002', 'Cheetos Puffs Cheese Flavored Snacks 8.5oz', 680, 'Zone A-Aisle 3-Rack 2-Level 2', 110),
  ('TOS001', 'Tostitos Original Restaurant Style Tortilla Chips 13oz', 420, 'Zone B-Aisle 1-Rack 3-Level 1', 80),
  ('TOS002', 'Tostitos Scoops Tortilla Chips 10oz', 380, 'Zone B-Aisle 1-Rack 3-Level 2', 70),
  ('FRI001', 'Fritos Original Corn Chips 9.25oz', 320, 'Zone B-Aisle 2-Rack 1-Level 1', 60),
  ('FRI002', 'Fritos Chili Cheese Corn Chips 9.25oz', 280, 'Zone B-Aisle 2-Rack 1-Level 2', 50),
  ('RUF001', 'Ruffles Original Potato Chips 9oz', 450, 'Zone B-Aisle 3-Rack 2-Level 1', 85),
  ('RUF002', 'Ruffles Cheddar & Sour Cream Potato Chips 9oz', 390, 'Zone B-Aisle 3-Rack 2-Level 2', 75),
  ('SUN001', 'SunChips Original Multigrain Snacks 7oz', 180, 'Zone C-Aisle 1-Rack 1-Level 1', 40),
  ('SUN002', 'SunChips Harvest Cheddar Multigrain Snacks 7oz', 160, 'Zone C-Aisle 1-Rack 1-Level 2', 35),
  ('POP001', 'PopCorners Sea Salt Popcorn Chips 5oz', 95, 'Zone C-Aisle 2-Rack 2-Level 1', 25),
  ('POP002', 'PopCorners White Cheddar Popcorn Chips 5oz', 85, 'Zone C-Aisle 2-Rack 2-Level 2', 20)
ON CONFLICT (sku) DO UPDATE SET
  name = EXCLUDED.name,
  quantity = EXCLUDED.quantity,
  location = EXCLUDED.location,
  reorder_point = EXCLUDED.reorder_point,
  updated_at = now();

-- Sample users should be created using the setup script: scripts/setup/create_default_users.py
-- This script properly generates password hashes from environment variables and does not expose
-- sensitive credentials in source code. Never hardcode password hashes in SQL files.
--
-- To create default users, run:
--   python scripts/setup/create_default_users.py
--
-- The script uses the following environment variables:
--   - DEFAULT_ADMIN_PASSWORD: Password for the admin user (default: 'changeme')
--   - DEFAULT_USER_PASSWORD: Password for regular users (default: 'changeme')
--
-- For production deployments, always set strong passwords via environment variables.
