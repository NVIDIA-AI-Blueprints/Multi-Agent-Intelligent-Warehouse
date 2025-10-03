# Changelog

All notable changes to this project will be documented in this file. See [Conventional Commits](https://conventionalcommits.org) for commit guidelines.

## [Unreleased]

### Fixed
- Fixed equipment assignments endpoint returning 404 errors
- Fixed database schema discrepancies between documentation and implementation
- Fixed React runtime error in chat interface (event parameter issue)
- Fixed MessageBubble component syntax error (missing opening brace)
- Fixed ChatInterfaceNew component "event is undefined" runtime error
- Cleaned up all ESLint warnings in UI (25 warnings resolved)
- Fixed missing chatAPI export causing compilation errors
- Fixed API port conflict by updating frontend to use port 8002

### Features
- Initial implementation of Warehouse Operational Assistant
- Multi-agent architecture with Safety, Operations, and Equipment agents
- NVIDIA NIM integration for LLM and embedding services
- Hybrid RAG system with SQL and vector retrieval
- Real-time chat interface with evidence panel
- Equipment asset management and tracking
- Safety procedure management and compliance
- Operations coordination and task management
- Equipment assignments endpoint with proper database queries
- Equipment telemetry monitoring with extended time windows
- Production-grade vector search with NV-EmbedQA-E5-v5 embeddings
- GPU-accelerated vector search with NVIDIA cuVS
- Advanced evidence scoring and intelligent clarifying questions
- MCP (Model Context Protocol) framework fully integrated
- MCP-enabled agents with dynamic tool discovery and execution
- MCP-integrated planner graph with intelligent routing
- End-to-end MCP workflow processing
- Cross-agent tool sharing and communication
- MCP Testing UI with dynamic tool discovery interface
- MCP Testing navigation link in left sidebar
- Comprehensive monitoring with Prometheus/Grafana
- Enterprise security with JWT/OAuth2 and RBAC

### Technical Details
- FastAPI backend with async/await support
- React frontend with Material-UI components
- PostgreSQL/TimescaleDB for structured data
- Milvus vector database for semantic search
- Docker containerization for deployment
- Comprehensive API documentation with OpenAPI/Swagger

## [1.0.0] - 2025-09-11

### Initial Release
- Complete warehouse operational assistant system
- Evidence panel with structured data display
- Version control and semantic release setup
