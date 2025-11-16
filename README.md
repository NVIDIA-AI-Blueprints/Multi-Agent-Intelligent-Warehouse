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

## Overview

This repository implements a production-grade Multi-Agent-Intelligent-Warehouse patterned on NVIDIA's AI Blueprints, featuring:

- **Multi-Agent AI System** - LangGraph-orchestrated Planner/Router + 5 Specialized Agents (Equipment, Operations, Safety, Forecasting, Document)
- **NVIDIA NeMo Integration** - Complete document processing pipeline with OCR, structured data extraction, and vision models
- **MCP Framework** - Model Context Protocol with dynamic tool discovery, execution, and adapter system
- **Hybrid RAG Stack** - PostgreSQL/TimescaleDB + Milvus vector database with intelligent query routing (90%+ accuracy)
- **Production-Grade Vector Search** - NV-EmbedQA-E5-v5 embeddings (1024-dim) with NVIDIA cuVS GPU acceleration (19x performance)
- **AI-Powered Demand Forecasting** - Multi-model ensemble (XGBoost, Random Forest, Gradient Boosting, Ridge, SVR) with NVIDIA RAPIDS GPU acceleration
- **Real-Time Monitoring** - Equipment status, telemetry, Prometheus metrics, Grafana dashboards, and system health
- **Enterprise Security** - JWT/OAuth2 + RBAC with 5 user roles, NeMo Guardrails for content safety, and comprehensive user management
- **System Integrations** - WMS (SAP EWM, Manhattan, Oracle), ERP (SAP ECC, Oracle), IoT sensors, RFID/Barcode scanners, Time Attendance systems
- **Advanced Features** - Redis caching, conversation memory, evidence scoring, intelligent query classification, automated reorder recommendations, business intelligence dashboards

## System Architecture(Will update with nvidia blue print style)

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
- **AI-Powered Demand Forecasting** - Multi-model ensemble with Random Forest, XGBoost, Gradient Boosting, Linear Regression, Ridge Regression, SVR
- **Advanced Feature Engineering** - Lag features, rolling statistics, seasonal patterns, promotional impacts
- **Hyperparameter Optimization** - Optuna-based tuning with Time Series Cross-Validation
- **Real-Time Predictions** - Live demand forecasts with confidence intervals
- **Automated Reorder Recommendations** - AI-suggested stock orders with urgency levels
- **Business Intelligence Dashboard** - Comprehensive analytics and performance monitoring
- **GPU Acceleration** - NVIDIA RAPIDS cuML integration for enterprise-scale forecasting (10-100x faster)

### System Integrations
- **WMS Integration** - SAP EWM, Manhattan, Oracle WMS
- **ERP Integration** - SAP ECC, Oracle ERP
- **IoT Integration** - Equipment monitoring, environmental sensors, safety systems
- **RFID/Barcode Scanning** - Honeywell, Zebra, generic scanners
- **Time Attendance** - Biometric systems, card readers, mobile apps

### Enterprise Security & Monitoring
- **Authentication** - JWT/OAuth2 + RBAC with 5 user roles
- **Real-Time Monitoring** - Prometheus metrics + Grafana dashboards
- **Equipment Telemetry** - Battery, temperature, charging analytics
- **System Health** - Comprehensive observability and alerting
- **NeMo Guardrails** - Content safety and compliance protection (see [NeMo Guardrails](#nemo-guardrails) section below)

## Quick Start

**For the fastest setup, see [QUICK_START.md](QUICK_START.md). For detailed deployment instructions, see [DEPLOYMENT.md](DEPLOYMENT.md).**

### Prerequisites

- **Python 3.9+** (check with `python3 --version`)
- **Node.js 18+** and npm (check with `node --version` and `npm --version`)
- **Docker** and Docker Compose
- **Git** (to clone the repository)

### Step 1: Clone and Navigate to Repository

```bash
git clone https://github.com/T-DevH/Multi-Agent-Intelligent-Warehouse.git
cd Multi-Agent-Intelligent-Warehouse
```

### Step 2: Set Up Python Virtual Environment

```bash
# Using the setup script (recommended)
./scripts/setup/setup_environment.sh

# Or manually:
python3 -m venv env
source env/bin/activate  # Linux/macOS
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 3: Configure Environment Variables

```bash
# Copy the example environment file
cp .env.example .env

# Edit .env file with your configuration
# At minimum, ensure database credentials match the Docker setup
```

**Required Environment Variables:**
- Database connection settings (PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE)
- Redis connection (REDIS_HOST, REDIS_PORT)
- Milvus connection (MILVUS_HOST, MILVUS_PORT)
- JWT secret key (JWT_SECRET_KEY)

**For AI Features (Optional):**
- NVIDIA API keys (NVIDIA_API_KEY, NEMO_*_API_KEY, LLAMA_*_API_KEY)

**Quick Setup for NVIDIA API Keys:**
```bash
python setup_nvidia_api.py
```

### Step 4: Start Development Infrastructure

```bash
# Start infrastructure services (TimescaleDB, Redis, Kafka, Milvus)
./scripts/setup/dev_up.sh
```

**Service Endpoints:**
- **Postgres/Timescale**: `postgresql://warehouse:changeme@localhost:5435/warehouse`
- **Redis**: `localhost:6379`
- **Milvus gRPC**: `localhost:19530`
- **Kafka**: `localhost:9092`

### Step 5: Initialize Database Schema

```bash
# Ensure virtual environment is activated
source env/bin/activate

# Run all required schema files in order
PGPASSWORD=${POSTGRES_PASSWORD:-changeme} psql -h localhost -p 5435 -U warehouse -d warehouse -f data/postgres/000_schema.sql
PGPASSWORD=${POSTGRES_PASSWORD:-changeme} psql -h localhost -p 5435 -U warehouse -d warehouse -f data/postgres/001_equipment_schema.sql
PGPASSWORD=${POSTGRES_PASSWORD:-changeme} psql -h localhost -p 5435 -U warehouse -d warehouse -f data/postgres/002_document_schema.sql
PGPASSWORD=${POSTGRES_PASSWORD:-changeme} psql -h localhost -p 5435 -U warehouse -d warehouse -f data/postgres/004_inventory_movements_schema.sql

# Create model tracking tables (required for forecasting features)
PGPASSWORD=${POSTGRES_PASSWORD:-changeme} psql -h localhost -p 5435 -U warehouse -d warehouse -f scripts/setup/create_model_tracking_tables.sql
```

### Step 6: Create Default Users

```bash
# Create default admin and operator users
python scripts/setup/create_default_users.py
```

**Default Credentials:**
- **Admin user**: `admin` / `changeme` (role: admin)
- **Operator user**: `user` / `changeme` (role: operator)

### Step 7: Install RAPIDS for GPU-Accelerated Forecasting

For GPU-accelerated demand forecasting (10-100x faster), install NVIDIA RAPIDS:

```bash
source env/bin/activate
./scripts/setup/install_rapids.sh
```

**Requirements:**
- NVIDIA GPU with CUDA Compute Capability 7.0+
- CUDA 11.2+ or 12.0+
- 16GB+ GPU memory (recommended)

See [RAPIDS Setup Guide](docs/forecasting/RAPIDS_SETUP.md) for detailed instructions.

### Step 8: Start the API Server

```bash
# Using the startup script (recommended)
./scripts/start_server.sh

# Or manually:
source env/bin/activate
python -m uvicorn src.api.app:app --reload --port 8001 --host 0.0.0.0
```

**API Endpoints:**
- **API**: http://localhost:8001
- **API Documentation (Swagger)**: http://localhost:8001/docs
- **OpenAPI Schema**: http://localhost:8001/openapi.json
- **Health Check**: http://localhost:8001/api/v1/health

### Step 9: Start the Frontend

```bash
cd src/ui/web
npm install  # First time only
npm start
```

**Frontend:**
- **Web UI**: http://localhost:3001
- **Login**: `admin` / `changeme`

### Step 10: Verify Installation

```bash
# Test API health endpoint
curl http://localhost:8001/api/v1/health

# Test authentication
curl -X POST http://localhost:8001/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"changeme"}'
```

### Troubleshooting

**Database Connection Issues:**
- Ensure Docker containers are running: `docker ps`
- Check TimescaleDB logs: `docker logs wosa-timescaledb`
- Verify port 5435 is not in use

**API Server Won't Start:**
- Ensure virtual environment is activated: `source env/bin/activate`
- Check Python version: `python3 --version` (must be 3.9+)
- Use the startup script: `./scripts/start_server.sh`
- See [DEPLOYMENT.md](DEPLOYMENT.md) troubleshooting section

**For more help:** See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) or open an issue on GitHub.

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
./deploy/scripts/setup_monitoring.sh
```

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

NeMo Guardrails provides multi-layer protection for the warehouse operational assistant:

- **Input Safety Validation** - Checks user queries before processing
- **Output Safety Validation** - Validates AI responses before returning to users
- **Pattern-Based Detection** - Identifies violations using keyword and phrase matching
- **Timeout Protection** - Prevents hanging requests with configurable timeouts
- **Graceful Degradation** - Continues operation even if guardrails fail

### Protection Categories

The guardrails system protects against:

#### 1. Jailbreak Attempts
Detects attempts to override system instructions:
- "ignore previous instructions"
- "forget everything"
- "pretend to be"
- "roleplay as"
- "bypass"
- "jailbreak"

#### 2. Safety Violations
Prevents guidance that could endanger workers or equipment:
- Operating equipment without training
- Bypassing safety protocols
- Working without personal protective equipment (PPE)
- Unsafe equipment operation

#### 3. Security Violations
Blocks requests for sensitive security information:
- Security codes and access codes
- Restricted area access
- Alarm codes
- System bypass instructions

#### 4. Compliance Violations
Ensures adherence to regulations and policies:
- Avoiding safety inspections
- Skipping compliance requirements
- Ignoring regulations
- Working around safety rules

#### 5. Off-Topic Queries
Redirects non-warehouse related queries:
- Weather, jokes, cooking recipes
- Sports, politics, entertainment
- General knowledge questions

### Configuration

Guardrails configuration is defined in `data/config/guardrails/rails.yaml`:

```yaml
# Safety and compliance rules
safety_rules:
  - name: "jailbreak_detection"
    patterns:
      - "ignore previous instructions"
      - "forget everything"
      # ... more patterns
    response: "I cannot ignore my instructions..."

  - name: "safety_violations"
    patterns:
      - "operate forklift without training"
      - "bypass safety protocols"
      # ... more patterns
    response: "Safety is our top priority..."
```

**Configuration Features:**
- Pattern-based rule definitions
- Custom response messages for each violation type
- Monitoring and logging configuration
- Conversation limits and constraints

### Integration

Guardrails are integrated into the chat endpoint at two critical points:

1. **Input Safety Check** (before processing):
   ```python
   input_safety = await guardrails_service.check_input_safety(req.message)
   if not input_safety.is_safe:
       return safety_response
   ```

2. **Output Safety Check** (after AI response):
   ```python
   output_safety = await guardrails_service.check_output_safety(ai_response)
   if not output_safety.is_safe:
       return safety_response
   ```

**Timeout Protection:**
- Input check: 3-second timeout
- Output check: 5-second timeout
- Graceful degradation on timeout

### Testing

Comprehensive test suite available in `tests/unit/test_guardrails.py`:

```bash
# Run guardrails tests
python tests/unit/test_guardrails.py
```

**Test Coverage:**
- 18 test scenarios covering all violation categories
- Legitimate query validation
- Performance testing with concurrent requests
- Response time measurement

**Test Categories:**
- Jailbreak attempts (2 tests)
- Safety violations (3 tests)
- Security violations (3 tests)
- Compliance violations (2 tests)
- Off-topic queries (3 tests)
- Legitimate warehouse queries (4 tests)

### Service Implementation

The guardrails service (`src/api/services/guardrails/guardrails_service.py`) provides:

- **GuardrailsService** class with async methods
- **Pattern matching** for violation detection
- **Safety response generation** based on violation types
- **Configuration loading** from YAML files
- **Error handling** with graceful degradation

### Response Format

When a violation is detected, the system returns:

```json
{
  "reply": "Safety is our top priority. I cannot provide guidance...",
  "route": "guardrails",
  "intent": "safety_violation",
  "context": {
    "safety_violations": ["Safety violation: 'operate forklift without training'"]
  },
  "confidence": 0.9
}
```

### Monitoring

Guardrails activity is logged and monitored:

- **Log Level**: INFO
- **Conversation Logging**: Enabled
- **Rail Hits Logging**: Enabled
- **Metrics Tracked**:
  - Conversation length
  - Rail hits (violations detected)
  - Response time
  - Safety violations
  - Compliance issues

### Best Practices

1. **Regular Updates**: Review and update patterns in `rails.yaml` based on new threats
2. **Monitoring**: Monitor guardrails logs for patterns and trends
3. **Testing**: Run test suite after configuration changes
4. **Customization**: Adjust timeout values based on your infrastructure
5. **Response Messages**: Keep safety responses professional and helpful

### Future Enhancements

Planned improvements:
- Integration with full NeMo Guardrails SDK
- LLM-based violation detection (beyond pattern matching)
- Machine learning for adaptive threat detection
- Enhanced monitoring dashboards

**Related Documentation:**
- Configuration file: `data/config/guardrails/rails.yaml`
- Service implementation: `src/api/services/guardrails/guardrails_service.py`
- Test suite: `tests/unit/test_guardrails.py`

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
- **Deployment**: [DEPLOYMENT.md](DEPLOYMENT.md)
- **Quick Start**: [QUICK_START.md](QUICK_START.md)

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
- [DEPLOYMENT.md](DEPLOYMENT.md) - Complete deployment guide
- [QUICK_START.md](QUICK_START.md) - Quick start guide
- [docs/](docs/) - Architecture and technical documentation
- [PRD.md](PRD.md) - Product Requirements Document
