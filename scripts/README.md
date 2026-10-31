# Scripts Directory

This directory contains utility scripts for the Warehouse Operational Assistant system, organized by purpose.

## 📁 Directory Structure

```
scripts/
├── data/              # Data generation scripts
├── forecasting/       # Forecasting and ML model scripts
├── lib/               # Shared helpers (.env loader, deployment identity, check_model_config.py)
├── models/            # Local NIM setup/check scripts
├── qualification/     # Reference-deployment qualification probes
├── security/          # Dependency blocklist checker
├── setup/            # Environment, database, gateway and sandbox setup scripts
├── testing/          # Test and validation scripts (incl. run_core_ci.sh)
├── tools/            # Utility and helper scripts
├── start_server.sh   # Development API server startup script
├── *_reference_deployment.sh  # Reference deployment lifecycle: preflight, start, status,
│                              # smoke_test, restart, stop, qualify
├── counterfactual_eval.py, trace_capture.py  # Demo evaluation artifacts
└── README.md         # This file
```

The reference (single-node) deployment scripts are documented in
[docs/operations/REFERENCE_DEPLOYMENT_RUNBOOK.md](../docs/operations/REFERENCE_DEPLOYMENT_RUNBOOK.md).

---

## 🚀 Quick Start

### Start the API Server

Prerequisite: `env/` (from `./scripts/setup/setup_environment.sh`) must also
contain the MAIW packages, which `setup_environment.sh` does not install:

```bash
source env/bin/activate
pip install -e packages/maiw-contracts -e packages/maiw-mcp -e packages/maiw-state \
    -e packages/maiw-models -e packages/maiw-skills -e packages/maiw-decision \
    -e packages/maiw-execution -e packages/maiw-agents -e packages/maiw-world \
    -e apps/api
```

```bash
./scripts/start_server.sh
```

This will:
- Activate the virtual environment
- Check dependencies
- Start the FastAPI server on port 8001
- Provide access to API docs at http://localhost:8001/docs

### Generate Demo Data

For a quick demo setup:

```bash
cd scripts/data
./run_quick_demo.sh
```

For comprehensive data:

```bash
cd scripts/data
./run_data_generation.sh
```

---

## 📊 Data Generation Scripts

Located in `scripts/data/` - Generate realistic warehouse data for demos and testing.

### Quick Demo Data Generator

**Script:** `scripts/data/run_quick_demo.sh`  
**Python:** `scripts/data/quick_demo_data.py`

Generates a minimal dataset for quick demos:
- 12 users across all roles
- 25 inventory items (including low stock alerts)
- 8 tasks with various statuses
- 8 safety incidents with different severities
- 7 days of equipment telemetry data
- 50 audit log entries

**Usage:**
```bash
cd scripts/data
./run_quick_demo.sh
```

### Full Synthetic Data Generator

**Script:** `scripts/data/run_data_generation.sh`  
**Python:** `scripts/data/generate_synthetic_data.py`

Generates comprehensive warehouse simulation data:
- 50 users across all roles
- 1,000 inventory items with realistic locations
- 500 tasks with various statuses and realistic payloads
- 100 safety incidents with different severities and types
- 30 days of equipment telemetry data (50 pieces of equipment)
- 200 audit log entries for user actions
- 1,000 vector embeddings for knowledge base
- Redis cache data for sessions and metrics

**Usage:**
```bash
cd scripts/data
./run_data_generation.sh
```

### Historical Demand Data Generator (Required for Forecasting)

**Script:** `scripts/data/generate_historical_demand.py`

**⚠️ Important:** This script is **separate** from the demo/synthetic data generators and is **required** for the forecasting system to work. It generates historical inventory movement data that forecasting models need to make predictions.

**What it generates:**
- Historical `inventory_movements` data (180 days by default)
- Outbound movements (demand/consumption) with realistic patterns
- Inbound movements (restocking) 
- Adjustments (inventory corrections)
- Seasonal patterns, promotional spikes, and brand-specific demand characteristics
- Frito-Lay product-specific demand profiles

**Why it's separate:**
- Forecasting requires extensive historical data (180+ days)
- Uses sophisticated demand modeling (seasonality, promotions, brand profiles)
- Can be run independently after initial data setup
- Not needed for basic demo/testing (only for forecasting features)

**Usage:**
```bash
cd scripts/data
source ../../env/bin/activate
export $(grep -E "^POSTGRES_" ../../.env | xargs)
python generate_historical_demand.py
```

**When to run:**
- After running `quick_demo_data.py` or `generate_synthetic_data.py`
- Before using the Forecasting page in the UI
- When you need to test forecasting features
- When historical demand data is missing or needs regeneration

**Output:**
- ~7,000+ inventory movements across all SKUs
- 180 days of historical demand patterns
- Brand-specific demand characteristics (Lay's, Doritos, Cheetos, etc.)

### Additional Data Generators

- **`generate_equipment_telemetry.py`** - Generate equipment telemetry time-series data
- **`generate_all_sku_forecasts.py`** - Generate forecasts for all SKUs

### Database Coverage

- **PostgreSQL/TimescaleDB**: All structured data including inventory, tasks, users, safety incidents, equipment telemetry, audit logs, and **inventory_movements** (historical demand data)
- **Milvus**: Vector embeddings for knowledge base and document search
- **Redis**: Session data, cache data, and real-time metrics

**Note:** The `inventory_movements` table is only populated by `generate_historical_demand.py` and is required for forecasting features.

### Data Types Generated

#### 👥 Users
- **Roles**: admin, manager, supervisor, operator, viewer
- **Realistic Names**: Generated using Faker library
- **Authentication**: Properly hashed passwords (set via `DEFAULT_ADMIN_PASSWORD` env var)
- **Activity**: Last login times and session data

#### Inventory Items
- **SKUs**: Realistic product codes (SKU001, SKU002, etc.) or Frito-Lay product codes (LAY001, DOR001, etc.)
- **Locations**: Zone-based warehouse locations (Zone A-Aisle 1-Rack 2-Level 3)
- **Quantities**: Realistic stock levels with some items below reorder point
- **Categories**: Electronics, Clothing, Home & Garden, Automotive, Tools, etc.

#### Inventory Movements (Historical Demand Data)
- **Movement Types**: inbound (restocking), outbound (demand/consumption), adjustment (corrections)
- **Time Range**: 180 days of historical data by default
- **Demand Patterns**: Seasonal variations, promotional spikes, weekend effects, brand-specific characteristics
- **Usage**: Required for forecasting system to generate demand predictions
- **Note**: Only generated by `generate_historical_demand.py` (not included in quick demo or synthetic data generators)

#### Tasks
- **Types**: pick, pack, putaway, cycle_count, replenishment, inspection
- **Statuses**: pending, in_progress, completed, cancelled
- **Payloads**: Realistic task data including order IDs, priorities, equipment assignments
- **Assignees**: Linked to actual users in the system

#### Safety Incidents
- **Types**: slip_and_fall, equipment_malfunction, chemical_spill, fire_hazard, etc.
- **Severities**: low, medium, high, critical
- **Descriptions**: Realistic incident descriptions
- **Reporters**: Linked to actual users

#### Equipment Telemetry
- **Equipment Types**: forklift, pallet_jack, conveyor, scanner, printer, crane, etc.
- **Metrics**: battery_level, temperature, vibration, usage_hours, power_consumption
- **Time Series**: Realistic data points over time with proper timestamps
- **Equipment Status**: Online/offline states and performance metrics

#### Audit Logs
- **Actions**: login, logout, inventory_view, task_create, safety_report, etc.
- **Resource Types**: inventory, task, user, equipment, safety, system
- **Details**: IP addresses, user agents, timestamps, additional context
- **User Tracking**: All actions linked to actual users

---

## 🤖 Forecasting Scripts

Located in `scripts/forecasting/` - Demand forecasting and ML model training.

**⚠️ Prerequisites:** Before running forecasting scripts, ensure you have generated historical demand data using `scripts/data/generate_historical_demand.py`. The forecasting system requires historical `inventory_movements` data to generate predictions.

### Phase 1 & 2 Forecasting

**Script:** `scripts/forecasting/phase1_phase2_forecasting_agent.py`

Basic forecasting models (XGBoost, Random Forest, Gradient Boosting, Ridge Regression, SVR, Linear Regression).

**Usage:**
```bash
python scripts/forecasting/phase1_phase2_forecasting_agent.py
```

### Phase 3 Advanced Forecasting

**Script:** `scripts/forecasting/phase3_advanced_forecasting.py`

Advanced forecasting with model performance tracking and database integration.

**Usage:**
```bash
python scripts/forecasting/phase3_advanced_forecasting.py
```

### RAPIDS GPU-Accelerated Forecasting

**Script:** `scripts/forecasting/rapids_gpu_forecasting.py`

GPU-accelerated demand forecasting using NVIDIA RAPIDS cuML for high-performance forecasting.

**Usage:**
```bash
python scripts/forecasting/rapids_gpu_forecasting.py
```

**Features:**
- Automatic GPU detection and CPU fallback
- Multiple ML models (Random Forest, Linear Regression, SVR, XGBoost)
- Ensemble predictions with confidence intervals
- Database integration for model tracking

### Forecasting Summary

**Script:** `scripts/forecasting/phase1_phase2_summary.py`

Generate summary reports for forecasting results.

---

## ⚙️ Setup Scripts

Located in `scripts/setup/` - Environment and database setup.

### Environment Setup

**Script:** `scripts/setup/setup_environment.sh`

Sets up Python virtual environment and installs dependencies.

**Usage:**
```bash
./scripts/setup/setup_environment.sh
```

### Development Infrastructure

**Script:** `scripts/setup/dev_up.sh`

Starts the full Docker Compose dev stack (`deploy/compose/docker-compose.dev.yaml`): datastores (PostgreSQL, Redis, Kafka, Milvus, etc.), the four MCP servers, the backend API (:8001), the frontend (:3001) and nginx (:3000), all bound to 127.0.0.1.

**Usage:**
```bash
./scripts/setup/dev_up.sh
```

### Database Setup

**Script:** `scripts/setup/create_default_users.py`

Creates default users with proper password hashing. This script:
- Generates unique bcrypt password hashes with random salts
- Reads passwords from environment variables (never hardcoded)
- Does not expose credentials in source code
- **Security:** The SQL schema does not contain hardcoded password hashes - users must be created via this script

**Usage:**
```bash
# Set password via environment variable (optional, defaults to 'changeme' for development)
export DEFAULT_ADMIN_PASSWORD=your-secure-password-here

# Create default users
python scripts/setup/create_default_users.py
```

**Environment Variables:**
- `DEFAULT_ADMIN_PASSWORD` - Password for admin user (default: `changeme` for development only)
- `DEFAULT_USER_PASSWORD` - Password for regular users (default: `changeme` for development only)

**⚠️ Production:** Always set strong, unique passwords via environment variables. Never use default passwords in production.

**SQL Script:** `scripts/setup/create_model_tracking_tables.sql`

Creates tables for tracking model training history and predictions.

**Usage:**
```bash
PGPASSWORD=${POSTGRES_PASSWORD:-changeme} psql -h localhost -p 5435 -U warehouse -d warehouse -f scripts/setup/create_model_tracking_tables.sql
```

### RAPIDS Installation

**Script:** `scripts/setup/install_rapids.sh`

Installs NVIDIA RAPIDS cuML for GPU-accelerated forecasting.

**Usage:**
```bash
./scripts/setup/install_rapids.sh
```

**Additional Scripts:**
- `setup_rapids_gpu.sh` - GPU-specific RAPIDS setup
- `setup_rapids_phase1.sh` - Phase 1 RAPIDS setup

---

## 🧪 Testing Scripts

Located in `scripts/testing/` - Test and validation scripts.

### Chat Functionality Test

**Script:** `scripts/testing/test_chat_functionality.py`

Tests the chat endpoint and MCP agent routing. **Legacy:** it calls `POST /api/v1/chat`, which the v2 API (`maiw_api.app:app`) does not mount, so it only works against the legacy development server (`src/api/app.py`). The v2 conversational endpoint is `POST /api/v1/copilot/turn`.

**Usage:**
```bash
python scripts/testing/test_chat_functionality.py
```

### RAPIDS Forecasting Test

**Script:** `scripts/testing/test_rapids_forecasting.py`

Tests the RAPIDS GPU-accelerated forecasting agent.

**Usage:**
```bash
python scripts/testing/test_rapids_forecasting.py
```

---

## 🛠️ Utility Tools

Located in `scripts/tools/` - Utility and helper scripts.

### GPU Benchmarks

**Script:** `scripts/tools/benchmark_gpu_milvus.py`

Benchmarks GPU performance for Milvus vector operations.

### Debug Tools

**Script:** `scripts/tools/debug_chat_response.py`

Debug tool for analyzing chat responses and agent routing. **Legacy:** calls `POST /api/v1/chat`, which the v2 API does not mount.

### Demo Scripts

- **`gpu_demo.py`** - GPU acceleration demonstration
- **`mcp_gpu_integration_demo.py`** - MCP GPU integration demonstration

### Build Tools

**Script:** `scripts/tools/build-and-tag.sh`

Docker build and tagging utility.

---

## 🛠️ Technical Details

### Prerequisites

- Python 3.11+
- PostgreSQL/TimescaleDB running on port 5435
- Redis running on port 6379 (optional)
- Milvus running on port 19530 (optional)
- NVIDIA GPU with CUDA (for RAPIDS scripts, optional)

### Dependencies

Install data generation dependencies:

```bash
pip install -r scripts/requirements_synthetic_data.txt
```

Main dependencies:
- `psycopg[binary]` - PostgreSQL async driver
- `bcrypt` - Password hashing
- `faker` - Realistic data generation
- `pymilvus` - Milvus vector database client
- `redis` - Redis client
- `asyncpg` - Async PostgreSQL driver

### Database Credentials

Scripts use environment variables for database credentials:

- **PostgreSQL**: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`
- **Redis**: `REDIS_HOST` (default: `localhost:6379`)
- **Milvus**: `MILVUS_HOST` (default: `localhost:19530`)

---

## ⚠️ Important Notes

### Data Safety

- **WARNING**: Data generation scripts will DELETE existing data before generating new data
- **Backup**: Always backup your database before running data generation
- **Production**: Never run these scripts on production databases

### Performance

- **Quick Demo**: ~30 seconds to generate
- **Full Synthetic**: ~5-10 minutes to generate
- **Database Size**: Full synthetic data creates ~100MB+ of data

### Troubleshooting

- **Connection Issues**: Ensure all databases are running
- **Permission Issues**: Check database user permissions
- **Memory Issues**: Reduce data counts for large datasets
- **Foreign Key Errors**: Ensure data generation order respects dependencies

---

## 📚 Additional Documentation

- **Reference Deployment**: See `docs/operations/REFERENCE_DEPLOYMENT_RUNBOOK.md` for the lifecycle scripts
- **Forecasting Docs**: See `docs/forecasting/` for forecasting documentation
- **Deployment Guide**: See `DEPLOYMENT.md` for deployment instructions

---

## 🎯 Use Cases

### Demo Preparation

1. **Quick Demo**: Use `scripts/data/run_quick_demo.sh` for fast setup
2. **Full Demo**: Use `scripts/data/run_data_generation.sh` for comprehensive data
3. **Custom Data**: Modify the Python scripts for specific requirements

### Testing

- **Unit Testing**: Generate specific data sets for testing
- **Performance Testing**: Create large datasets for load testing
- **Integration Testing**: Ensure all systems work with realistic data

### Development

- **Feature Development**: Test new features with realistic data
- **Bug Reproduction**: Create specific data scenarios for debugging
- **UI Development**: Populate frontend with realistic warehouse data

---

## ✅ Success Indicators

After running the data generators, you should see:

- All database tables populated with realistic data
- Frontend showing populated inventory, tasks, and incidents
- Monitoring dashboards displaying metrics and KPIs
- User authentication working with generated users
- Action tools executing with realistic data context

Your warehouse is now ready for an impressive demo!
