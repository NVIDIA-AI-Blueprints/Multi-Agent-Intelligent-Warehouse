import React, { useState } from 'react';
import {
  Box,
  Typography,
  Paper,
  Grid,
  Card,
  CardContent,
  Button,
  Chip,
  Divider,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Link,
  Alert,
  AlertTitle,
  Breadcrumbs,
  ImageList,
  ImageListItem,
} from '@mui/material';
import {
  ExpandMore as ExpandMoreIcon,
  Code as CodeIcon,
  Architecture as ArchitectureIcon,
  Security as SecurityIcon,
  Speed as SpeedIcon,
  Storage as StorageIcon,
  Cloud as CloudIcon,
  BugReport as BugReportIcon,
  Rocket as RocketIcon,
  School as SchoolIcon,
  GitHub as GitHubIcon,
  Article as ArticleIcon,
  Build as BuildIcon,
  Api as ApiIcon,
  Dashboard as DashboardIcon,
  ArrowBack as ArrowBackIcon,
  CheckCircle as CheckCircleIcon,
  AccountTree as AccountTreeIcon,
  Timeline as TimelineIcon,
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';

const ArchitectureDiagrams: React.FC = () => {
  const navigate = useNavigate();
  const [expandedSection, setExpandedSection] = useState<string | false>('overview');

  const handleChange = (panel: string) => (event: React.SyntheticEvent, isExpanded: boolean) => {
    setExpandedSection(isExpanded ? panel : false);
  };

  const architectureComponents = [
    {
      name: "Frontend Layer",
      description: "React-based user interface with Material-UI components",
      technologies: ["React", "TypeScript", "Material-UI", "React Router"],
      responsibilities: [
        "User interface rendering",
        "Real-time chat interface",
        "Dashboard visualizations",
        "Equipment management UI",
        "Operations monitoring",
        "Safety incident reporting"
      ],
      status: "✅ Complete"
    },
    {
      name: "API Gateway",
      description: "FastAPI-based API gateway with authentication and routing",
      technologies: ["FastAPI", "Python", "JWT", "OpenAPI"],
      responsibilities: [
        "Request routing and load balancing",
        "Authentication and authorization",
        "API documentation (Swagger)",
        "Rate limiting and throttling",
        "Request/response validation",
        "Error handling and logging"
      ],
      status: "✅ Complete"
    },
    {
      name: "Multi-Agent System",
      description: "LangGraph-orchestrated multi-agent system with specialized agents",
      technologies: ["LangGraph", "NVIDIA NIMs", "MCP Framework", "Python"],
      responsibilities: [
        "Intent classification and routing",
        "Agent orchestration and coordination",
        "Tool discovery and execution",
        "Context management and memory",
        "Response generation and formatting",
        "Error handling and fallbacks"
      ],
      status: "✅ Complete"
    },
    {
      name: "Specialized Agents",
      description: "Domain-specific agents for equipment, operations, and safety",
      technologies: ["Python", "MCP Tools", "NVIDIA NIMs", "Custom Logic"],
      responsibilities: [
        "Equipment & Asset Operations",
        "Operations Coordination",
        "Safety & Compliance",
        "Tool execution and validation",
        "Domain-specific reasoning",
        "Action planning and execution"
      ],
      status: "✅ Complete"
    },
    {
      name: "MCP Framework",
      description: "Model Context Protocol for dynamic tool discovery and execution",
      technologies: ["MCP Protocol", "Python", "HTTP/WebSocket", "Tool Registry"],
      responsibilities: [
        "Dynamic tool discovery",
        "Tool binding and execution",
        "Service discovery and registry",
        "Tool validation and monitoring",
        "Multi-server communication",
        "Resource management"
      ],
      status: "✅ Complete"
    },
    {
      name: "Reasoning Engine",
      description: "Advanced reasoning capabilities with multiple reasoning types",
      technologies: ["NVIDIA NIMs", "Chain-of-Thought", "Multi-Hop", "Scenario Analysis"],
      responsibilities: [
        "Chain-of-thought reasoning",
        "Multi-hop reasoning",
        "Scenario analysis",
        "Causal reasoning",
        "Pattern recognition",
        "Confidence scoring"
      ],
      status: "✅ Complete"
    },
    {
      name: "Data Layer",
      description: "Hybrid data storage with PostgreSQL/TimescaleDB and Milvus",
      technologies: ["PostgreSQL", "TimescaleDB", "Milvus", "Redis", "SQL"],
      responsibilities: [
        "Structured data storage",
        "Time-series data management",
        "Vector similarity search",
        "Caching and session management",
        "Data migration and versioning",
        "Backup and recovery"
      ],
      status: "✅ Complete"
    },
    {
      name: "External Integrations",
      description: "Adapters for WMS, IoT, RFID/Barcode, and Time Attendance systems",
      technologies: ["REST APIs", "WebSocket", "Database Connectors", "Protocol Adapters"],
      responsibilities: [
        "WMS system integration",
        "IoT sensor data collection",
        "RFID/Barcode scanning",
        "Time and attendance tracking",
        "ERP system integration",
        "Third-party API management"
      ],
      status: "🔄 In Progress"
    },
    {
      name: "Monitoring Stack",
      description: "Comprehensive monitoring with Prometheus, Grafana, and Alertmanager",
      technologies: ["Prometheus", "Grafana", "Alertmanager", "Node Exporter"],
      responsibilities: [
        "Metrics collection and storage",
        "Visualization and dashboards",
        "Alert routing and notifications",
        "Performance monitoring",
        "Health checks and status",
        "Log aggregation and analysis"
      ],
      status: "✅ Complete"
    }
  ];

  const dataFlowSteps = [
    {
      step: 1,
      title: "User Input",
      description: "User sends message through React frontend",
      components: ["React UI", "Chat Interface", "WebSocket/HTTP"],
      details: "User types message in chat interface, frontend validates input and sends to API gateway"
    },
    {
      step: 2,
      title: "API Gateway Processing",
      description: "FastAPI gateway handles authentication and routing",
      components: ["FastAPI", "JWT Validation", "Rate Limiting"],
      details: "Gateway validates JWT token, applies rate limiting, and routes request to appropriate service"
    },
    {
      step: 3,
      title: "Intent Classification",
      description: "NVIDIA NIMs classifies user intent and determines routing",
      components: ["NVIDIA NIMs", "Intent Classifier", "Routing Logic"],
      details: "LLM analyzes user message to determine intent (equipment, operations, safety) and routing strategy"
    },
    {
      step: 4,
      title: "Agent Selection",
      description: "LangGraph selects appropriate specialized agent",
      components: ["LangGraph", "Agent Router", "Context Manager"],
      details: "Based on intent classification, system selects Equipment, Operations, or Safety agent"
    },
    {
      step: 5,
      title: "Tool Discovery",
      description: "MCP framework discovers available tools for the task",
      components: ["MCP Server", "Tool Registry", "Service Discovery"],
      details: "MCP framework queries tool registry to find relevant tools for the agent's task"
    },
    {
      step: 6,
      title: "Tool Execution",
      description: "Selected tools are executed with proper parameters",
      components: ["MCP Client", "Tool Binding", "Execution Engine"],
      details: "Tools are bound to execution context and executed with validated parameters"
    },
    {
      step: 7,
      title: "Data Retrieval",
      description: "Hybrid RAG system retrieves relevant data",
      components: ["PostgreSQL", "Milvus", "Vector Search", "SQL Queries"],
      details: "System queries both structured (PostgreSQL) and vector (Milvus) databases for relevant information"
    },
    {
      step: 8,
      title: "Reasoning Analysis",
      description: "Advanced reasoning engine processes results",
      components: ["Reasoning Engine", "Chain-of-Thought", "Scenario Analysis"],
      details: "Reasoning engine applies appropriate reasoning type to analyze retrieved data and generate insights"
    },
    {
      step: 9,
      title: "Response Generation",
      description: "NVIDIA NIMs generates final response",
      components: ["NVIDIA NIMs", "Response Formatter", "Structured Data"],
      details: "LLM generates natural language response with structured data and recommendations"
    },
    {
      step: 10,
      title: "Response Delivery",
      description: "Response is sent back to user through API gateway",
      components: ["API Gateway", "WebSocket/HTTP", "React UI"],
      details: "Response is formatted and sent back through API gateway to frontend for display"
    }
  ];

  const systemArchitecture = {
    title: "System Architecture Overview",
    description: "High-level view of the Multi-Agent-Intelligent-Warehouse architecture showing all major components and their relationships",
    components: [
      { name: "Frontend", type: "UI Layer", color: "#1976d2" },
      { name: "API Gateway", type: "Gateway Layer", color: "#388e3c" },
      { name: "Multi-Agent System", type: "Processing Layer", color: "#f57c00" },
      { name: "MCP Framework", type: "Tool Layer", color: "#7b1fa2" },
      { name: "Data Layer", type: "Storage Layer", color: "#d32f2f" },
      { name: "External Systems", type: "Integration Layer", color: "#455a64" },
      { name: "Monitoring", type: "Observability Layer", color: "#00796b" }
    ]
  };

  const agentFlowDiagram = {
    title: "Agent Flow Diagram",
    description: "Detailed flow showing how requests are processed through the multi-agent system",
    flow: [
      "User Input → Intent Classification → Agent Selection → Tool Discovery → Tool Execution → Data Retrieval → Reasoning → Response Generation → User Output"
    ]
  };

  const mcpArchitecture = {
    title: "MCP Framework Architecture",
    description: "Model Context Protocol framework showing tool discovery, binding, and execution",
    components: [
      "MCP Server (Tool Registration)",
      "MCP Client (Multi-Server Communication)",
      "Tool Discovery Service (Dynamic Registration)",
      "Tool Binding Service (Intelligent Binding)",
      "Tool Routing Service (Context-Aware Routing)",
      "Service Discovery Registry (Health Monitoring)"
    ]
  };

  return (
    <Box sx={{ p: 3, maxWidth: 1200, mx: 'auto' }}>
      {/* Breadcrumbs */}
      <Breadcrumbs sx={{ mb: 2 }}>
        <Button startIcon={<ArrowBackIcon />} onClick={() => navigate('/documentation')}>
          Documentation
        </Button>
        <Typography color="text.primary">Architecture Diagrams</Typography>
      </Breadcrumbs>

      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h3" component="h1" gutterBottom sx={{ fontWeight: 'bold', color: 'primary.main' }}>
          Architecture Diagrams
        </Typography>
        <Typography variant="h5" component="h2" gutterBottom color="text.secondary">
          System Architecture and Flow Diagrams
        </Typography>
        <Typography variant="body1" sx={{ mb: 2 }}>
          Comprehensive visual documentation of the Multi-Agent-Intelligent-Warehouse architecture, 
          including system components, data flow, agent interactions, and MCP framework design.
        </Typography>
        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mb: 3 }}>
          <Chip label="System Architecture" color="primary" />
          <Chip label="Data Flow" color="secondary" />
          <Chip label="Agent Interactions" color="info" />
          <Chip label="MCP Framework" color="warning" />
          <Chip label="Production Ready" color="success" />
        </Box>
      </Box>

      {/* Status Alert */}
      <Alert severity="success" sx={{ mb: 4 }}>
        <AlertTitle>🏗️ Complete Architecture Documentation</AlertTitle>
        The system architecture is fully documented with detailed component descriptions, 
        data flow diagrams, and interaction patterns for all major system components.
      </Alert>

      {/* System Architecture Overview */}
      <Accordion expanded={expandedSection === 'overview'} onChange={handleChange('overview')}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <ArchitectureIcon color="primary" />
            System Architecture Overview
          </Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Box sx={{ mb: 3 }}>
            <Typography variant="h5" gutterBottom>
              {systemArchitecture.title}
            </Typography>
            <Typography variant="body1" sx={{ mb: 2 }}>
              {systemArchitecture.description}
            </Typography>
          </Box>

          <Grid container spacing={3}>
            {architectureComponents.map((component, index) => (
              <Grid item xs={12} md={6} key={index}>
                <Card variant="outlined" sx={{ height: '100%' }}>
                  <CardContent>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
                      <BuildIcon color="primary" />
                      <Typography variant="h6">{component.name}</Typography>
                    </Box>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                      {component.description}
                    </Typography>
                    <Box sx={{ mb: 2 }}>
                      <Typography variant="subtitle2" gutterBottom>Technologies:</Typography>
                      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                        {component.technologies.map((tech, techIndex) => (
                          <Chip key={techIndex} label={tech} size="small" variant="outlined" />
                        ))}
                      </Box>
                    </Box>
                    <Box sx={{ mb: 2 }}>
                      <Typography variant="subtitle2" gutterBottom>Responsibilities:</Typography>
                      <List dense>
                        {component.responsibilities.map((responsibility, respIndex) => (
                          <ListItem key={respIndex} sx={{ py: 0 }}>
                            <ListItemIcon>
                              <CheckCircleIcon fontSize="small" />
                            </ListItemIcon>
                            <ListItemText primary={responsibility} primaryTypographyProps={{ variant: 'body2' }} />
                          </ListItem>
                        ))}
                      </List>
                    </Box>
                    <Chip 
                      label={component.status} 
                      color={component.status.includes('✅') ? 'success' : 'warning'}
                      size="small"
                    />
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </AccordionDetails>
      </Accordion>

      {/* Data Flow Diagram */}
      <Accordion expanded={expandedSection === 'dataflow'} onChange={handleChange('dataflow')}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <TimelineIcon color="primary" />
            Data Flow Diagram
          </Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Box sx={{ mb: 3 }}>
            <Typography variant="h5" gutterBottom>
              Request Processing Flow
            </Typography>
            <Typography variant="body1" sx={{ mb: 2 }}>
              Detailed step-by-step flow showing how user requests are processed through the entire system, 
              from frontend input to response delivery.
            </Typography>
          </Box>

          <Grid container spacing={2}>
            {dataFlowSteps.map((step, index) => (
              <Grid item xs={12} md={6} key={index}>
                <Card variant="outlined">
                  <CardContent>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
                      <Chip label={`Step ${step.step}`} color="primary" />
                      <Typography variant="h6">{step.title}</Typography>
                    </Box>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                      {step.description}
                    </Typography>
                    <Box sx={{ mb: 2 }}>
                      <Typography variant="subtitle2" gutterBottom>Components:</Typography>
                      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                        {step.components.map((component, compIndex) => (
                          <Chip key={compIndex} label={component} size="small" variant="outlined" />
                        ))}
                      </Box>
                    </Box>
                    <Typography variant="body2" sx={{ fontStyle: 'italic' }}>
                      {step.details}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </AccordionDetails>
      </Accordion>

      {/* Agent Flow Diagram */}
      <Accordion expanded={expandedSection === 'agentflow'} onChange={handleChange('agentflow')}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <AccountTreeIcon color="primary" />
            Agent Flow Diagram
          </Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Box sx={{ mb: 3 }}>
            <Typography variant="h5" gutterBottom>
              {agentFlowDiagram.title}
            </Typography>
            <Typography variant="body1" sx={{ mb: 2 }}>
              {agentFlowDiagram.description}
            </Typography>
          </Box>

          <Card variant="outlined">
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Multi-Agent Processing Flow
              </Typography>
              <Paper sx={{ p: 3, bgcolor: 'grey.50', textAlign: 'center' }}>
                <Typography variant="body1" sx={{ fontFamily: 'monospace', fontSize: '1.1rem' }}>
                  {agentFlowDiagram.flow[0]}
                </Typography>
              </Paper>
            </CardContent>
          </Card>

          <Grid container spacing={3} sx={{ mt: 2 }}>
            <Grid item xs={12} md={4}>
              <Card variant="outlined">
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    Equipment Agent
                  </Typography>
                  <List dense>
                    <ListItem sx={{ py: 0 }}>
                      <ListItemText primary="Equipment lookup and status" primaryTypographyProps={{ variant: 'body2' }} />
                    </ListItem>
                    <ListItem sx={{ py: 0 }}>
                      <ListItemText primary="Equipment dispatch and assignment" primaryTypographyProps={{ variant: 'body2' }} />
                    </ListItem>
                    <ListItem sx={{ py: 0 }}>
                      <ListItemText primary="Maintenance scheduling" primaryTypographyProps={{ variant: 'body2' }} />
                    </ListItem>
                    <ListItem sx={{ py: 0 }}>
                      <ListItemText primary="Availability checking" primaryTypographyProps={{ variant: 'body2' }} />
                    </ListItem>
                  </List>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} md={4}>
              <Card variant="outlined">
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    Operations Agent
                  </Typography>
                  <List dense>
                    <ListItem sx={{ py: 0 }}>
                      <ListItemText primary="Pick wave creation" primaryTypographyProps={{ variant: 'body2' }} />
                    </ListItem>
                    <ListItem sx={{ py: 0 }}>
                      <ListItemText primary="Task assignment" primaryTypographyProps={{ variant: 'body2' }} />
                    </ListItem>
                    <ListItem sx={{ py: 0 }}>
                      <ListItemText primary="Workflow optimization" primaryTypographyProps={{ variant: 'body2' }} />
                    </ListItem>
                    <ListItem sx={{ py: 0 }}>
                      <ListItemText primary="Performance monitoring" primaryTypographyProps={{ variant: 'body2' }} />
                    </ListItem>
                  </List>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} md={4}>
              <Card variant="outlined">
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    Safety Agent
                  </Typography>
                  <List dense>
                    <ListItem sx={{ py: 0 }}>
                      <ListItemText primary="Incident reporting" primaryTypographyProps={{ variant: 'body2' }} />
                    </ListItem>
                    <ListItem sx={{ py: 0 }}>
                      <ListItemText primary="Safety compliance" primaryTypographyProps={{ variant: 'body2' }} />
                    </ListItem>
                    <ListItem sx={{ py: 0 }}>
                      <ListItemText primary="Risk assessment" primaryTypographyProps={{ variant: 'body2' }} />
                    </ListItem>
                    <ListItem sx={{ py: 0 }}>
                      <ListItemText primary="Training management" primaryTypographyProps={{ variant: 'body2' }} />
                    </ListItem>
                  </List>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </AccordionDetails>
      </Accordion>

      {/* MCP Architecture */}
      <Accordion expanded={expandedSection === 'mcp'} onChange={handleChange('mcp')}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <BuildIcon color="primary" />
            MCP Framework Architecture
          </Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Box sx={{ mb: 3 }}>
            <Typography variant="h5" gutterBottom>
              {mcpArchitecture.title}
            </Typography>
            <Typography variant="body1" sx={{ mb: 2 }}>
              {mcpArchitecture.description}
            </Typography>
          </Box>

          <Grid container spacing={3}>
            {mcpArchitecture.components.map((component, index) => (
              <Grid item xs={12} md={6} key={index}>
                <Card variant="outlined">
                  <CardContent>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
                      <Chip label={index + 1} color="primary" />
                      <Typography variant="h6">{component}</Typography>
                    </Box>
                    <Typography variant="body2" color="text.secondary">
                      Core component of the MCP framework providing essential functionality for tool management and execution.
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </AccordionDetails>
      </Accordion>

      {/* Technology Stack */}
      <Accordion expanded={expandedSection === 'techstack'} onChange={handleChange('techstack')}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <CodeIcon color="primary" />
            Technology Stack
          </Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Grid container spacing={3}>
            <Grid item xs={12} md={6}>
              <Card variant="outlined">
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    Frontend Technologies
                  </Typography>
                  <List dense>
                    <ListItem>
                      <ListItemText 
                        primary="React 18" 
                        secondary="Modern React with hooks and concurrent features"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="TypeScript" 
                        secondary="Type-safe JavaScript development"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="Material-UI" 
                        secondary="Google Material Design components"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="React Router" 
                        secondary="Client-side routing and navigation"
                      />
                    </ListItem>
                  </List>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} md={6}>
              <Card variant="outlined">
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    Backend Technologies
                  </Typography>
                  <List dense>
                    <ListItem>
                      <ListItemText 
                        primary="FastAPI" 
                        secondary="Modern Python web framework with automatic API docs"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="LangGraph" 
                        secondary="Multi-agent orchestration and workflow management"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="NVIDIA NIMs" 
                        secondary="Llama 3.3 Nemotron Super 49B + NV-EmbedQA-E5-v5 embeddings"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="MCP Framework" 
                        secondary="Model Context Protocol for tool discovery and execution"
                      />
                    </ListItem>
                  </List>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} md={6}>
              <Card variant="outlined">
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    Data Technologies
                  </Typography>
                  <List dense>
                    <ListItem>
                      <ListItemText 
                        primary="PostgreSQL" 
                        secondary="Primary relational database for structured data"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="TimescaleDB" 
                        secondary="Time-series data extension for telemetry"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="Milvus" 
                        secondary="Vector database for semantic search"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="Redis" 
                        secondary="In-memory caching and session storage"
                      />
                    </ListItem>
                  </List>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} md={6}>
              <Card variant="outlined">
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    Infrastructure Technologies
                  </Typography>
                  <List dense>
                    <ListItem>
                      <ListItemText 
                        primary="Docker" 
                        secondary="Containerization for consistent deployments"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="Kubernetes" 
                        secondary="Container orchestration for production"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="Prometheus" 
                        secondary="Metrics collection and monitoring"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="Grafana" 
                        secondary="Visualization and dashboarding"
                      />
                    </ListItem>
                  </List>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </AccordionDetails>
      </Accordion>

      {/* Footer */}
      <Box sx={{ mt: 4, pt: 3, borderTop: 1, borderColor: 'divider' }}>
        <Typography variant="body2" color="text.secondary" align="center">
          Architecture Diagrams - Multi-Agent-Intelligent-Warehouse
        </Typography>
        <Box sx={{ display: 'flex', justifyContent: 'center', gap: 2, mt: 2 }}>
          <Button 
            variant="outlined" 
            startIcon={<GitHubIcon />}
            href="https://github.com/T-DevH/warehouse-operational-assistant"
            target="_blank"
            rel="noopener noreferrer"
          >
            View Source
          </Button>
          <Button variant="outlined" startIcon={<DashboardIcon />}>
            Live Demo
          </Button>
        </Box>
      </Box>
    </Box>
  );
};

export default ArchitectureDiagrams;
