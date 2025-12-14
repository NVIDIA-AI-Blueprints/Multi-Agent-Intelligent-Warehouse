# Multi-Agent-Intelligent-Warehouse 
*NVIDIA Blueprint–aligned multi-agent assistant for warehouse operations.*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18+-61dafb.svg)](https://reactjs.org/)
[![NVIDIA NIMs](https://img.shields.io/badge/NVIDIA-NIMs-76B900.svg)](https://www.nvidia.com/en-us/ai-data-science/nim/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15+-336791.svg)](https://www.postgresql.org/)
[![Milvus](https://img.shields.io/badge/Milvus-GPU%20Accelerated-00D4AA.svg)](https://milvus.io/)
[![Docker](https://img.shields.io/badge/Docker-Containerized-2496ED.svg)](https://www.docker.com/)
[![Prometheus](https://img.shields.io/badge/Prometheus-Monitoring-E6522C.svg)](https://prometheus.io/)
[![Grafana](https://img.shields.io/badge/Grafana-Dashboards-F46800.svg)](https://grafana.com/)

## Table of Contents

- [Overview](#overview)
- [Acronyms & Abbreviations](#acronyms--abbreviations)
- [System Architecture](#system-architecture)
- [Key Features](#key-features)
- [Quick Start](#quick-start)
- [Multi-Agent System](#multi-agent-system)
- [API Reference](#api-reference)
- [Monitoring & Observability](#monitoring--observability)
- [NeMo Guardrails](#nemo-guardrails)
- [Development Guide](#development-guide)
- [Contributing](#contributing)
- [License](#license)

## Acronyms & Abbreviations

| Acronym | Definition |
|---------|------------|
| **ADR** | Architecture Decision Record |
| **API** | Application Programming Interface |
| **BOL** | Bill of Lading |
| **cuML** | CUDA Machine Learning |
| **cuVS** | CUDA Vector Search |
| **EAO** | Equipment & Asset Operations (Agent) |
| **ERP** | Enterprise Resource Planning |
| **GPU** | Graphics Processing Unit |
| **HTTP/HTTPS** | Hypertext Transfer Protocol (Secure) |
| **IoT** | Internet of Things |
| **JSON** | JavaScript Object Notation |
| **JWT** | JSON Web Token |
| **KPI** | Key Performance Indicator |
| **LLM** | Large Language Model |
| **LOTO** | Lockout/Tagout |
| **MAPE** | Mean Absolute Percentage Error |
| **MCP** | Model Context Protocol |
| **NeMo** | NVIDIA NeMo |
| **NIM/NIMs** | NVIDIA Inference Microservices |
| **OCR** | Optical Character Recognition |
| **PPE** | Personal Protective Equipment |
| **QPS** | Queries Per Second |
| **RAG** | Retrieval-Augmented Generation |
| **RAPIDS** | Rapid Analytics Platform for Interactive Data Science |
| **RBAC** | Role-Based Access Control |
| **RFID** | Radio Frequency Identification |
| **RMSE** | Root Mean Square Error |
| **REST** | Representational State Transfer |
| **SDS** | Safety Data Sheet |
| **SKU** | Stock Keeping Unit |
| **SLA** | Service Level Agreement |
| **SOP** | Standard Operating Procedure |
| **SQL** | Structured Query Language |
| **UI** | User Interface |
| **UX** | User Experience |
| **WMS** | Warehouse Management System |

## Overview

This repository implements a production-grade Multi-Agent-Intelligent-Warehouse patterned on NVIDIA's AI Blueprints, featuring:

- **Multi-Agent AI System** - LangGraph-orchestrated Planner/Router + 5 Specialized Agents (Equipment, Operations, Safety, Forecasting, Document)
- **NVIDIA NeMo Integration** - Complete document processing pipeline with OCR, structured data extraction, and vision models
- **MCP Framework** - Model Context Protocol with dynamic tool discovery, execution, and adapter system
- **Hybrid RAG Stack** - PostgreSQL/TimescaleDB + Milvus vector database with intelligent query routing (90%+ accuracy)
- **Production-Grade Vector Search** - NV-EmbedQA-E5-v5 embeddings (1024-dim) with NVIDIA cuVS GPU acceleration (19x performance)
- **AI-Powered Demand Forecasting** - Multi-model ensemble (XGBoost, Random Forest, Gradient Boosting, Ridge, SVR) with NVIDIA RAPIDS GPU acceleration
- **Real-Time Monitoring** - Equipment status, telemetry, Prometheus metrics, Grafana dashboards, and system health
- **Enterprise Security** - JWT authentication + RBAC with 5 user roles, NeMo Guardrails for content safety, and comprehensive user management
- **System Integrations** - WMS (SAP EWM, Manhattan, Oracle), ERP (SAP ECC, Oracle), IoT sensors, RFID/Barcode scanners, Time Attendance systems
- **Advanced Features** - Redis caching, conversation memory, evidence scoring, intelligent query classification, automated reorder recommendations, business intelligence dashboards

## System Architecture

![Warehouse Operational Assistant Architecture](docs/architecture/diagrams/warehouse-assistant-architecture.png)

The architecture consists of:

1. **User/External Interaction Layer** - Entry point for users and external systems
2. **Warehouse Operational Assistant** - Central orchestrator managing specialized AI agents
3. **Agent Orchestration Framework** - LangGraph for workflow orchestration + MCP (Model Context Protocol) for tool discovery
4. **Multi-Agent System** - Five specialized agents:
   - **Equipment & Asset Operations Agent** - Equipment assets, assignments, maintenance, and telemetry
   - **Operations Coordination Agent** - Task planning and workflow management  
   - **Safety & Compliance Agent** - Safety monitoring, incident response, and compliance tracking
   - **Forecasting Agent** - Demand forecasting, reorder recommendations, and model performance monitoring
   - **Document Processing Agent** - OCR, structured data extraction, and document management
5. **API Services Layer** - Standardized interfaces for business logic and data access
6. **Data Retrieval & Processing** - SQL, Vector, and Knowledge Graph retrievers
7. **LLM Integration & Orchestration** - NVIDIA NIMs with LangGraph orchestration
8. **Data Storage Layer** - PostgreSQL, Vector DB, Knowledge Graph, and Telemetry databases
9. **Infrastructure Layer** - Kubernetes, NVIDIA GPU infrastructure, Edge devices, and Cloud

### Key Architectural Components

- **Multi-Agent Coordination**: LangGraph orchestrates complex workflows between specialized agents
- **MCP Integration**: Model Context Protocol enables seamless tool discovery and execution
- **Hybrid Data Processing**: Combines structured (PostgreSQL/TimescaleDB) and vector (Milvus) data
- **NVIDIA NIMs Integration**: LLM inference and embedding services for intelligent processing
- **Real-time Monitoring**: Comprehensive telemetry and equipment status tracking
- **Scalable Infrastructure**: Kubernetes orchestration with GPU acceleration

## Key Features

### Multi-Agent AI System
- **Planner/Router** - Intelligent query routing and workflow orchestration
- **Equipment & Asset Operations Agent** - Equipment management, maintenance, and telemetry
- **Operations Coordination Agent** - Task planning and workflow management
- **Safety & Compliance Agent** - Safety monitoring and incident response
- **Forecasting Agent** - Demand forecasting, reorder recommendations, and model performance monitoring
- **Document Processing Agent** - OCR, structured data extraction, and document management
- **MCP Integration** - Model Context Protocol with dynamic tool discovery

### Document Processing Pipeline
- **Multi-Format Support** - PDF, PNG, JPG, JPEG, TIFF, BMP files
- **5-Stage NVIDIA NeMo Pipeline** - Complete OCR and structured data extraction
- **Real-Time Processing** - Background processing with status tracking
- **Intelligent OCR** - `meta/llama-3.2-11b-vision-instruct` for text extraction
- **Structured Data Extraction** - Entity recognition and quality validation

### Advanced Search & Retrieval
- **Hybrid RAG Stack** - PostgreSQL/TimescaleDB + Milvus vector database
- **Production-Grade Vector Search** - NV-EmbedQA-E5-v5 embeddings (1024-dim)
- **GPU-Accelerated Search** - NVIDIA cuVS-powered vector search (19x performance)
- **Intelligent Query Routing** - Automatic SQL vs Vector vs Hybrid classification (90%+ accuracy)
- **Evidence Scoring** - Multi-factor confidence assessment with clarifying questions
- **Redis Caching** - Intelligent caching with 85%+ hit rate

### Demand Forecasting & Inventory Intelligence
- **🚀 GPU-Accelerated Forecasting** - **NVIDIA RAPIDS cuML** integration for enterprise-scale performance
  - **10-100x faster** training and inference compared to CPU-only
  - **Automatic GPU detection** - Falls back to CPU if GPU not available
  - **Full GPU acceleration** for Random Forest, Linear Regression, SVR via cuML
  - **XGBoost GPU support** via CUDA when RAPIDS is available
  - **Seamless integration** - No code changes needed, works out of the box
- **AI-Powered Demand Forecasting** - Multi-model ensemble with Random Forest, XGBoost, Gradient Boosting, Linear Regression, Ridge Regression, SVR
- **Advanced Feature Engineering** - Lag features, rolling statistics, seasonal patterns, promotional impacts
- **Hyperparameter Optimization** - Optuna-based tuning with Time Series Cross-Validation
- **Real-Time Predictions** - Live demand forecasts with confidence intervals
- **Automated Reorder Recommendations** - AI-suggested stock orders with urgency levels
- **Business Intelligence Dashboard** - Comprehensive analytics and performance monitoring

### System Integrations
- **WMS Integration** - SAP EWM, Manhattan, Oracle WMS
- **ERP Integration** - SAP ECC, Oracle ERP
- **IoT Integration** - Equipment monitoring, environmental sensors, safety systems
- **RFID/Barcode Scanning** - Honeywell, Zebra, generic scanners
- **Time Attendance** - Biometric systems, card readers, mobile apps

### Enterprise Security & Monitoring
- **Authentication** - JWT authentication + RBAC with 5 user roles
- **Real-Time Monitoring** - Prometheus metrics + Grafana dashboards
- **Equipment Telemetry** - Battery, temperature, charging analytics
- **System Health** - Comprehensive observability and alerting
- **NeMo Guardrails** - Content safety and compliance protection (see [NeMo Guardrails](#nemo-guardrails) section below)

#### Security Notes

**JWT Secret Key Configuration:**
- **Development**: If `JWT_SECRET_KEY` is not set, the application uses a default development key with warnings. This allows for easy local development.
- **Production**: The application **requires** `JWT_SECRET_KEY` to be set. If not set or using the default placeholder, the application will fail to start. Set `ENVIRONMENT=production` and provide a strong, unique `JWT_SECRET_KEY` in your `.env` file.
- **Best Practice**: Always set `JWT_SECRET_KEY` explicitly, even in development, using a strong random string (minimum 32 characters).

For more security information, see [docs/secrets.md](docs/secrets.md) and [SECURITY_REVIEW.md](SECURITY_REVIEW.md).

## Quick Start

**For complete deployment instructions, see [DEPLOYMENT.md](DEPLOYMENT.md).**

### Prerequisites

- **Python 3.9+** (check with `python3 --version`)
- **Node.js 20.0.0+** (LTS recommended) and npm (check with `node --version` and `npm --version`)
  - **Minimum**: Node.js 18.17.0+ (required for `node:path` protocol support)
  - **Recommended**: Node.js 20.x LTS for best compatibility
  - **Note**: Node.js 18.0.0 - 18.16.x will fail with `Cannot find module 'node:path'` error
- **Docker** and Docker Compose
- **Git** (to clone the repository)
- **PostgreSQL client** (`psql`) - Required for running database migrations
  - **Ubuntu/Debian**: `sudo apt-get install postgresql-client`
  - **macOS**: `brew install postgresql` or `brew install libpq`
  - **Windows**: Install from [PostgreSQL downloads](https://www.postgresql.org/download/windows/)
  - **Alternative**: Use Docker (see [DEPLOYMENT.md](DEPLOYMENT.md))

### Local Development Setup

For the fastest local development setup:

```bash
# 1. Clone repository
git clone https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse.git
cd Multi-Agent-Intelligent-Warehouse

# 2. Verify Node.js version (recommended before setup)
./scripts/setup/check_node_version.sh

# 3. Setup environment
./scripts/setup/setup_environment.sh

# 4. Configure environment variables (REQUIRED before starting services)
# Create .env file for Docker Compose (recommended location)
cp .env.example deploy/compose/.env
# Or create in project root: cp .env.example .env
# Edit with your values: nano deploy/compose/.env

# 5. Start infrastructure services
./scripts/setup/dev_up.sh

# 6. Run database migrations
source env/bin/activate

# Load environment variables from .env file (REQUIRED before running migrations)
# This ensures $POSTGRES_PASSWORD is available for the psql commands below
# If .env is in deploy/compose/ (recommended):
set -a && source deploy/compose/.env && set +a
# OR if .env is in project root:
# set -a && source .env && set +a

# Option A: Using Docker Compose (Recommended - no psql client needed)
docker-compose -f deploy/compose/docker-compose.dev.yaml exec -T timescaledb psql -U warehouse -d warehouse < data/postgres/000_schema.sql
docker-compose -f deploy/compose/docker-compose.dev.yaml exec -T timescaledb psql -U warehouse -d warehouse < data/postgres/001_equipment_schema.sql
docker-compose -f deploy/compose/docker-compose.dev.yaml exec -T timescaledb psql -U warehouse -d warehouse < data/postgres/002_document_schema.sql
docker-compose -f deploy/compose/docker-compose.dev.yaml exec -T timescaledb psql -U warehouse -d warehouse < data/postgres/004_inventory_movements_schema.sql
docker-compose -f deploy/compose/docker-compose.dev.yaml exec -T timescaledb psql -U warehouse -d warehouse < scripts/setup/create_model_tracking_tables.sql

# Option B: Using psql directly (alternative - requires PostgreSQL client installed)
# PGPASSWORD=${POSTGRES_PASSWORD:-changeme} psql -h localhost -p 5435 -U warehouse -d warehouse -f data/postgres/000_schema.sql
# PGPASSWORD=${POSTGRES_PASSWORD:-changeme} psql -h localhost -p 5435 -U warehouse -d warehouse -f data/postgres/001_equipment_schema.sql
# docker-compose -f deploy/compose/docker-compose.dev.yaml exec -T timescaledb psql -U warehouse -d warehouse < data/postgres/002_document_schema.sql
# docker-compose -f deploy/compose/docker-compose.dev.yaml exec -T timescaledb psql -U warehouse -d warehouse < data/postgres/004_inventory_movements_schema.sql
# docker-compose -f deploy/compose/docker-compose.dev.yaml exec -T timescaledb psql -U warehouse -d warehouse < scripts/setup/create_model_tracking_tables.sql

# 7. Create default users
python scripts/setup/create_default_users.py

# 8. Generate demo data (optional but recommended)
python scripts/data/quick_demo_data.py

# 9. Generate historical demand data for forecasting (optional, required for Forecasting page)
python scripts/data/generate_historical_demand.py

# 10. (Optional) Install RAPIDS GPU acceleration for forecasting
# This enables 10-100x faster forecasting with NVIDIA GPUs
# Requires: NVIDIA GPU with CUDA 12.x support
./scripts/setup/install_rapids.sh
# Or manually: pip install --extra-index-url=https://pypi.nvidia.com cudf-cu12 cuml-cu12

# 11. Start API server
./scripts/start_server.sh

# 12. Start frontend (in another terminal)
cd src/ui/web
npm install
npm start
```

**Access:**
- Frontend: http://localhost:3001 (login: `admin` / `changeme`)
- API: http://localhost:8001
- API Docs: http://localhost:8001/docs

**Service Endpoints:**
- **Postgres/Timescale**: `postgresql://warehouse:changeme@localhost:5435/warehouse`
- **Redis**: `localhost:6379`
- **Milvus gRPC**: `localhost:19530`
- **Kafka**: `localhost:9092`

### Environment Configuration

**⚠️ Important:** For Docker Compose deployments, the `.env` file location matters!

Docker Compose looks for `.env` files in this order:
1. Same directory as the compose file (`deploy/compose/.env`)
2. Current working directory (project root `.env`)

**Recommended:** Create `.env` in the same directory as your compose file for consistency:

```bash
# Option 1: In deploy/compose/ (recommended for Docker Compose)
cp .env.example deploy/compose/.env
nano deploy/compose/.env  # or your preferred editor

# Option 2: In project root (works if running commands from project root)
cp .env.example .env
nano .env  # or your preferred editor
```

**Critical Variables:**
- Database connection settings (POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, DB_HOST, DB_PORT)
- Redis connection (REDIS_HOST, REDIS_PORT)
- Milvus connection (MILVUS_HOST, MILVUS_PORT)
- JWT secret key (JWT_SECRET_KEY) - **Required in production**. In development, a default is used with warnings. See [Security Notes](#security-notes) below.
- Admin password (DEFAULT_ADMIN_PASSWORD)

**For AI Features (Optional):**
- NVIDIA API keys (NVIDIA_API_KEY, NEMO_*_API_KEY, LLAMA_*_API_KEY)

**Quick Setup for NVIDIA API Keys:**
```bash
python setup_nvidia_api.py
```

### Troubleshooting

**Node.js Version Issues:**
- **Error: "Cannot find module 'node:path'"**: Your Node.js version is too old
  - Check version: `node --version`
  - Minimum required: Node.js 18.17.0+
  - Recommended: Node.js 20.x LTS
  - Run version check: `./scripts/setup/check_node_version.sh`
  - Upgrade: `nvm install 20 && nvm use 20` (if using nvm)
  - Or download from: https://nodejs.org/
  - After upgrading, clear and reinstall: `cd src/ui/web && rm -rf node_modules package-lock.json && npm install`

**Database Connection Issues:**
- Ensure Docker containers are running: `docker ps`
- Check TimescaleDB logs: `docker logs wosa-timescaledb`
- Verify port 5435 is not in use

**API Server Won't Start:**
- Ensure virtual environment is activated: `source env/bin/activate`
- Check Python version: `python3 --version` (must be 3.9+)
- Use the startup script: `./scripts/start_server.sh`
- See [DEPLOYMENT.md](DEPLOYMENT.md) troubleshooting section

**Frontend Build Issues:**
- Verify Node.js version: `./scripts/setup/check_node_version.sh`
- Clear node_modules: `cd src/ui/web && rm -rf node_modules package-lock.json && npm install`
- Check for port conflicts: Ensure port 3001 is available

**For more help:** See [DEPLOYMENT.md](DEPLOYMENT.md) for detailed troubleshooting or open an issue on GitHub.

## Multi-Agent System

The Warehouse Operational Assistant uses a sophisticated multi-agent architecture with specialized AI agents for different aspects of warehouse operations.

### Equipment & Asset Operations Agent (EAO)

**Mission**: Ensure equipment is available, safe, and optimally used for warehouse workflows.

**Key Capabilities:**
- Equipment assignment and tracking
- Real-time telemetry monitoring (battery, temperature, charging status)
- Maintenance management and scheduling
- Asset tracking and location monitoring
- Equipment utilization analytics

**Action Tools:** `assign_equipment`, `get_equipment_status`, `create_maintenance_request`, `get_equipment_telemetry`, `update_equipment_location`, `get_equipment_utilization`, `create_equipment_reservation`, `get_equipment_history`

### Operations Coordination Agent

**Mission**: Coordinate warehouse operations, task planning, and workflow optimization.

**Key Capabilities:**
- Task management and assignment
- Workflow optimization (pick paths, resource allocation)
- Performance monitoring and KPIs
- Resource planning and allocation

**Action Tools:** `create_task`, `assign_task`, `optimize_pick_path`, `get_task_status`, `update_task_progress`, `get_performance_metrics`, `create_work_order`, `get_task_history`

### Safety & Compliance Agent

**Mission**: Ensure warehouse safety compliance and incident management.

**Key Capabilities:**
- Incident management and logging
- Safety procedures and checklists
- Compliance monitoring and training
- Emergency response coordination

**Action Tools:** `log_incident`, `start_checklist`, `broadcast_alert`, `create_corrective_action`, `lockout_tagout_request`, `near_miss_capture`, `retrieve_sds`

### Forecasting Agent

**Mission**: Provide AI-powered demand forecasting, reorder recommendations, and model performance monitoring.

**Key Capabilities:**
- Demand forecasting using multiple ML models
- Automated reorder recommendations with urgency levels
- Model performance monitoring (accuracy, MAPE, drift scores)
- Business intelligence and trend analysis
- Real-time predictions with confidence intervals

**Action Tools:** `get_forecast`, `get_batch_forecast`, `get_reorder_recommendations`, `get_model_performance`, `get_forecast_dashboard`, `get_business_intelligence`

**Forecasting Models:**
- Random Forest (82% accuracy, 15.8% MAPE)
- XGBoost (79.5% accuracy, 15.0% MAPE)
- Gradient Boosting (78% accuracy, 14.2% MAPE)
- Linear Regression, Ridge Regression, SVR

**Model Availability by Phase:**

| Model | Phase 1 & 2 | Phase 3 |
|-------|-------------|---------|
| Random Forest | ✅ | ✅ |
| XGBoost | ✅ | ✅ |
| Time Series | ✅ | ❌ |
| Gradient Boosting | ❌ | ✅ |
| Ridge Regression | ❌ | ✅ |
| SVR | ❌ | ✅ |
| Linear Regression | ❌ | ✅ |

### Document Processing Agent

**Mission**: Process warehouse documents with OCR and structured data extraction.

**Key Capabilities:**
- Multi-format document support (PDF, PNG, JPG, JPEG, TIFF, BMP)
- Intelligent OCR with NVIDIA NeMo
- Structured data extraction (invoices, receipts, BOLs)
- Quality assessment and validation

### MCP Integration

All agents are integrated with the **Model Context Protocol (MCP)** framework:
- **Dynamic Tool Discovery** - Real-time tool registration and discovery
- **Cross-Agent Communication** - Seamless tool sharing between agents
- **Intelligent Routing** - MCP-enhanced intent classification
- **Tool Execution Planning** - Context-aware tool execution

See [docs/architecture/mcp-integration.md](docs/architecture/mcp-integration.md) for detailed MCP documentation.

## API Reference

### Health & Status
- `GET /api/v1/health` - System health check
- `GET /api/v1/health/simple` - Simple health status
- `GET /api/v1/version` - API version information

### Authentication
- `POST /api/v1/auth/login` - User authentication
- `GET /api/v1/auth/me` - Get current user information
- `GET /api/v1/auth/users/public` - Get list of users for dropdown selection (public, no auth required)
- `GET /api/v1/auth/users` - Get all users (admin only)

### Chat
- `POST /api/v1/chat` - Chat with multi-agent system (requires NVIDIA API keys)

### Equipment & Assets
- `GET /api/v1/equipment` - List all equipment
- `GET /api/v1/equipment/{asset_id}` - Get equipment details
- `GET /api/v1/equipment/{asset_id}/status` - Get equipment status
- `GET /api/v1/equipment/{asset_id}/telemetry` - Get equipment telemetry
- `GET /api/v1/equipment/assignments` - Get equipment assignments
- `GET /api/v1/equipment/maintenance/schedule` - Get maintenance schedule
- `POST /api/v1/equipment/assign` - Assign equipment
- `POST /api/v1/equipment/release` - Release equipment
- `POST /api/v1/equipment/maintenance` - Schedule maintenance

### Forecasting
- `GET /api/v1/forecasting/dashboard` - Comprehensive forecasting dashboard
- `GET /api/v1/forecasting/real-time` - Real-time demand predictions
- `GET /api/v1/forecasting/reorder-recommendations` - Automated reorder suggestions
- `GET /api/v1/forecasting/model-performance` - Model performance metrics
- `GET /api/v1/forecasting/business-intelligence` - Business analytics
- `POST /api/v1/forecasting/batch-forecast` - Batch forecast for multiple SKUs
- `GET /api/v1/training/history` - Training history
- `POST /api/v1/training/start` - Start model training

### Document Processing
- `POST /api/v1/document/upload` - Upload document for processing
- `GET /api/v1/document/status/{document_id}` - Check processing status
- `GET /api/v1/document/results/{document_id}` - Get extraction results
- `GET /api/v1/document/analytics` - Document analytics

### Operations
- `GET /api/v1/operations/tasks` - List tasks
- `GET /api/v1/safety/incidents` - List safety incidents

**Full API Documentation:** http://localhost:8001/docs (Swagger UI)

## Monitoring & Observability

### Prometheus & Grafana Stack

The system includes comprehensive monitoring with Prometheus metrics collection and Grafana dashboards.

**Quick Start:**
```bash
# Start monitoring stack
./scripts/setup/setup_monitoring.sh
```

See [DEPLOYMENT.md](DEPLOYMENT.md) for detailed monitoring setup instructions.

**Access URLs:**
- **Grafana**: http://localhost:3000 (admin/changeme)
- **Prometheus**: http://localhost:9090
- **Alertmanager**: http://localhost:9093

**Key Metrics Tracked:**
- API request rates and latencies
- Equipment telemetry and status
- Agent performance and response times
- Database query performance
- Vector search performance
- Cache hit rates and memory usage

See [monitoring/](monitoring/) for dashboard configurations and alerting rules.

## NeMo Guardrails

The system implements **NVIDIA NeMo Guardrails** for content safety, security, and compliance protection. All user inputs and AI responses are validated through a comprehensive guardrails system to ensure safe and compliant interactions.

### Overview

The guardrails system provides **dual implementation support** with automatic fallback:

- **NeMo Guardrails SDK** (with Colang) - Intelligent, programmable guardrails using NVIDIA's official SDK
  - ✅ **Already included** in `requirements.txt` (`nemoguardrails>=0.19.0`)
  - Installed automatically when you run `pip install -r requirements.txt`
- **Pattern-Based Matching** - Fast, lightweight fallback using keyword/phrase matching
- **Feature Flag Control** - Runtime switching between implementations via `USE_NEMO_GUARDRAILS_SDK`
- **Automatic Fallback** - Seamlessly switches to pattern-based if SDK unavailable
- **Input & Output Validation** - Checks both user queries and AI responses
- **Timeout Protection** - Prevents hanging requests (3s input, 5s output)
- **Comprehensive Monitoring** - Metrics tracking for method usage and performance

### Protection Categories

The guardrails system protects against **88 patterns** across 5 categories:

1. **Jailbreak Attempts** (17 patterns) - Prevents instruction override attempts
2. **Safety Violations** (13 patterns) - Blocks unsafe operational guidance
3. **Security Violations** (15 patterns) - Prevents security information requests
4. **Compliance Violations** (12 patterns) - Ensures regulatory adherence
5. **Off-Topic Queries** (13 patterns) - Redirects non-warehouse queries

### Quick Configuration

```bash
# Enable SDK implementation (recommended)
USE_NEMO_GUARDRAILS_SDK=true

# NVIDIA API key (required for SDK)
NVIDIA_API_KEY=your-api-key-here

# Optional: Guardrails-specific configuration
RAIL_API_KEY=your-api-key-here  # Falls back to NVIDIA_API_KEY if not set
RAIL_API_URL=https://integrate.api.nvidia.com/v1
GUARDRAILS_TIMEOUT=10
GUARDRAILS_USE_API=true
```

### Integration

Guardrails are automatically integrated into the chat endpoint:
- **Input Safety Check** - Validates user queries before processing (3s timeout)
- **Output Safety Check** - Validates AI responses before returning (5s timeout)
- **Metrics Tracking** - Logs method used, performance, and safety status

### Testing

```bash
# Unit tests
pytest tests/unit/test_guardrails_sdk.py -v

# Integration tests (compares both implementations)
pytest tests/integration/test_guardrails_comparison.py -v -s

# Performance benchmarks
pytest tests/integration/test_guardrails_comparison.py::test_performance_benchmark -v -s
```

### Documentation

**📖 For comprehensive documentation, see: [Guardrails Implementation Guide](docs/architecture/guardrails-implementation.md)**

The detailed guide includes:
- Complete architecture overview
- Implementation details (SDK vs Pattern-based)
- All 88 guardrails patterns
- API interface documentation
- Configuration reference
- Monitoring & metrics
- Testing instructions
- Troubleshooting guide
- Future roadmap

**Key Files:**
- Service: `src/api/services/guardrails/guardrails_service.py`
- SDK Wrapper: `src/api/services/guardrails/nemo_sdk_service.py`
- Colang Config: `data/config/guardrails/rails.co`
- NeMo Config: `data/config/guardrails/config.yml`
- Legacy YAML: `data/config/guardrails/rails.yaml`

## Development Guide

### Repository Layout

```
.
├─ src/                    # Source code
│  ├─ api/                 # FastAPI application
│  ├─ retrieval/           # Retrieval services
│  ├─ memory/              # Memory services
│  ├─ adapters/            # External system adapters
│  └─ ui/                  # React web dashboard
├─ data/                   # SQL DDL/migrations, sample data
├─ deploy/                 # Deployment configurations
│  ├─ compose/             # Docker Compose files
│  ├─ helm/                # Helm charts
│  └─ scripts/             # Deployment scripts
├─ scripts/                # Utility scripts
│  ├─ setup/               # Setup scripts
│  ├─ forecasting/         # Forecasting scripts
│  └─ data/                # Data generation scripts
├─ tests/                  # Test suite
├─ docs/                   # Documentation
│  └─ architecture/        # Architecture documentation
└─ monitoring/             # Prometheus/Grafana configs
```

### Running Locally

**API Server:**
```bash
source env/bin/activate
./scripts/start_server.sh
```

**Frontend:**
```bash
cd src/ui/web
npm start
```

**Infrastructure:**
```bash
./scripts/setup/dev_up.sh
```

### Testing

```bash
# Run all tests
pytest tests/

# Run specific test suite
pytest tests/unit/
pytest tests/integration/
```

### Documentation

- **Architecture**: [docs/architecture/](docs/architecture/)
- **MCP Integration**: [docs/architecture/mcp-integration.md](docs/architecture/mcp-integration.md)
- **Forecasting**: [docs/forecasting/](docs/forecasting/)
- **Deployment**: [DEPLOYMENT.md](DEPLOYMENT.md) - Complete deployment guide with Docker and Kubernetes options

## Contributing

Contributions are welcome! Please see our contributing guidelines and code of conduct.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'feat: add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

**Commit Message Format:** We use [Conventional Commits](https://www.conventionalcommits.org/):
- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation changes
- `refactor:` - Code refactoring
- `test:` - Test additions/changes

## License

TBD (add your organization's license file).

---

For detailed documentation, see:
- [DEPLOYMENT.md](DEPLOYMENT.md) - Complete deployment guide with Docker and Kubernetes options
- [docs/](docs/) - Architecture and technical documentation
- [PRD.md](PRD.md) - Product Requirements Document
