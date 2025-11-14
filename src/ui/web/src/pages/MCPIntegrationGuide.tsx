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
  CheckCircle as CheckIcon,
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';

const MCPIntegrationGuide: React.FC = () => {
  const navigate = useNavigate();
  const [expandedSection, setExpandedSection] = useState<string | false>('overview');

  const handleChange = (panel: string) => (event: React.SyntheticEvent, isExpanded: boolean) => {
    setExpandedSection(isExpanded ? panel : false);
  };

  const mcpPhases = [
    {
      phase: "Phase 1: Foundation",
      status: "✅ Complete",
      description: "Core MCP infrastructure and basic tool discovery",
      components: [
        "MCP Server Implementation",
        "MCP Client Implementation", 
        "MCP-Enabled Base Classes",
        "ERP Adapter Migration",
        "Comprehensive Testing Framework",
        "Complete Documentation"
      ]
    },
    {
      phase: "Phase 2: Agent Integration", 
      status: "✅ Complete",
      description: "Dynamic tool discovery and agent integration",
      components: [
        "Dynamic Tool Discovery",
        "MCP-Enabled Agents",
        "Dynamic Tool Binding",
        "MCP-Based Routing",
        "Tool Validation"
      ]
    },
    {
      phase: "Phase 3: Full Migration",
      status: "✅ Complete", 
      description: "Complete adapter migration and production deployment",
      components: [
        "Complete Adapter Migration",
        "Service Discovery & Registry",
        "MCP Monitoring & Management",
        "End-to-End Testing",
        "Deployment Configurations",
        "Security Integration"
      ]
    }
  ];

  const mcpComponents = [
    {
      name: "MCP Server",
      description: "Tool registration, discovery, and execution with full protocol compliance",
      features: ["Tool Registration", "Protocol Compliance", "Error Handling", "Health Monitoring"],
      status: "✅ Production Ready"
    },
    {
      name: "MCP Client", 
      description: "Multi-server communication with HTTP and WebSocket support",
      features: ["Multi-Server Communication", "HTTP/WebSocket Support", "Resource Access", "Prompt Management"],
      status: "✅ Production Ready"
    },
    {
      name: "Tool Discovery Service",
      description: "Automatic tool discovery and registration system with intelligent search",
      features: ["Dynamic Registration", "Intelligent Search", "Tool Metadata", "Health Checks"],
      status: "✅ Production Ready"
    },
    {
      name: "Tool Binding Service",
      description: "Intelligent tool binding and execution framework with multiple strategies",
      features: ["Context-Aware Binding", "Multiple Strategies", "Execution Planning", "Performance Optimization"],
      status: "✅ Production Ready"
    },
    {
      name: "Tool Routing Service",
      description: "Advanced routing and tool selection logic with context awareness",
      features: ["Performance Routing", "Accuracy Routing", "Cost Routing", "Latency Routing"],
      status: "✅ Production Ready"
    },
    {
      name: "Service Discovery Registry",
      description: "Centralized service discovery and health monitoring",
      features: ["Service Registry", "Health Monitoring", "Load Balancing", "Failover"],
      status: "✅ Production Ready"
    }
  ];

  const apiEndpoints = [
    {
      category: "Tool Discovery",
      endpoints: [
        { method: "GET", path: "/api/v1/mcp/tools", description: "Discover available tools across all adapters" },
        { method: "GET", path: "/api/v1/mcp/tools/{adapter_id}", description: "Get tools for specific adapter" },
        { method: "POST", path: "/api/v1/mcp/tools/register", description: "Register new tool with MCP server" }
      ]
    },
    {
      category: "Tool Execution",
      endpoints: [
        { method: "POST", path: "/api/v1/mcp/execute", description: "Execute MCP tool with parameters" },
        { method: "POST", path: "/api/v1/mcp/execute/batch", description: "Execute multiple tools in batch" },
        { method: "GET", path: "/api/v1/mcp/execute/{execution_id}", description: "Get execution status and results" }
      ]
    },
    {
      category: "Service Management",
      endpoints: [
        { method: "GET", path: "/api/v1/mcp/status", description: "Get MCP system status and health" },
        { method: "GET", path: "/api/v1/mcp/adapters", description: "List all registered adapters" },
        { method: "POST", path: "/api/v1/mcp/adapters/register", description: "Register new MCP adapter" }
      ]
    }
  ];

  return (
    <Box sx={{ p: 3, maxWidth: 1200, mx: 'auto' }}>
      {/* Breadcrumbs */}
      <Breadcrumbs sx={{ mb: 2 }}>
        <Button startIcon={<ArrowBackIcon />} onClick={() => navigate('/documentation')}>
          Documentation
        </Button>
        <Typography color="text.primary">MCP Integration Guide</Typography>
      </Breadcrumbs>

      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h3" component="h1" gutterBottom sx={{ fontWeight: 'bold', color: 'primary.main' }}>
          MCP Integration Guide
        </Typography>
        <Typography variant="h5" component="h2" gutterBottom color="text.secondary">
          Complete Model Context Protocol Framework Documentation
        </Typography>
        <Typography variant="body1" sx={{ mb: 2 }}>
          Comprehensive guide to the Model Context Protocol (MCP) implementation in the Warehouse Operational Assistant. 
          This framework enables seamless communication between AI agents and external systems through dynamic tool discovery and execution.
        </Typography>
        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mb: 3 }}>
          <Chip label="Phase 3 Complete" color="success" />
          <Chip label="Production Ready" color="success" />
          <Chip label="Dynamic Tool Discovery" color="primary" />
          <Chip label="Multi-Server Communication" color="secondary" />
          <Chip label="Advanced Routing" color="info" />
        </Box>
      </Box>

      {/* Status Alert */}
      <Alert severity="success" sx={{ mb: 4 }}>
        <AlertTitle>🎉 MCP Framework Complete</AlertTitle>
        The Model Context Protocol integration has been successfully completed across all 3 phases. 
        The system now provides dynamic tool discovery, intelligent execution, and comprehensive monitoring capabilities.
      </Alert>

      {/* Overview */}
      <Accordion expanded={expandedSection === 'overview'} onChange={handleChange('overview')}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <ArchitectureIcon color="primary" />
            MCP Framework Overview
          </Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Box sx={{ mb: 3 }}>
            <Typography variant="h5" gutterBottom>
              What is MCP?
            </Typography>
            <Typography variant="body1" sx={{ mb: 2 }}>
              The Model Context Protocol (MCP) is a standardized protocol for tool discovery, execution, and communication 
              between AI agents and external systems. It provides a unified interface for dynamic tool management and execution.
            </Typography>
          </Box>

          <Grid container spacing={3}>
            {mcpComponents.map((component, index) => (
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
                      <Typography variant="subtitle2" gutterBottom>Key Features:</Typography>
                      <List dense>
                        {component.features.map((feature, featureIndex) => (
                          <ListItem key={featureIndex} sx={{ py: 0 }}>
                            <ListItemIcon>
                              <CodeIcon fontSize="small" />
                            </ListItemIcon>
                            <ListItemText primary={feature} primaryTypographyProps={{ variant: 'body2' }} />
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

      {/* Implementation Phases */}
      <Accordion expanded={expandedSection === 'phases'} onChange={handleChange('phases')}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <RocketIcon color="primary" />
            Implementation Phases
          </Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Grid container spacing={3}>
            {mcpPhases.map((phase, index) => (
              <Grid item xs={12} md={4} key={index}>
                <Card variant="outlined" sx={{ height: '100%' }}>
                  <CardContent>
                    <Typography variant="h6" gutterBottom>
                      {phase.phase}
                    </Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                      {phase.description}
                    </Typography>
                    <Box sx={{ mb: 2 }}>
                      <Typography variant="subtitle2" gutterBottom>Components:</Typography>
                      <List dense>
                        {phase.components.map((component, compIndex) => (
                          <ListItem key={compIndex} sx={{ py: 0 }}>
                            <ListItemIcon>
                              <CheckIcon fontSize="small" />
                            </ListItemIcon>
                            <ListItemText primary={component} primaryTypographyProps={{ variant: 'body2' }} />
                          </ListItem>
                        ))}
                      </List>
                    </Box>
                    <Chip 
                      label={phase.status} 
                      color={phase.status.includes('✅') ? 'success' : 'warning'}
                      size="small"
                    />
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </AccordionDetails>
      </Accordion>

      {/* API Reference */}
      <Accordion expanded={expandedSection === 'api'} onChange={handleChange('api')}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <ApiIcon color="primary" />
            MCP API Reference
          </Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Grid container spacing={3}>
            {apiEndpoints.map((category, index) => (
              <Grid item xs={12} md={4} key={index}>
                <Card variant="outlined">
                  <CardContent>
                    <Typography variant="h6" gutterBottom>
                      {category.category}
                    </Typography>
                    <List dense>
                      {category.endpoints.map((endpoint, epIndex) => (
                        <ListItem key={epIndex} sx={{ px: 0 }}>
                          <ListItemText
                            primary={
                              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                <Chip 
                                  label={endpoint.method} 
                                  size="small" 
                                  color={endpoint.method === 'GET' ? 'success' : 'primary'}
                                />
                                <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                                  {endpoint.path}
                                </Typography>
                              </Box>
                            }
                            secondary={endpoint.description}
                          />
                        </ListItem>
                      ))}
                    </List>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </AccordionDetails>
      </Accordion>

      {/* Usage Examples */}
      <Accordion expanded={expandedSection === 'examples'} onChange={handleChange('examples')}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <CodeIcon color="primary" />
            Usage Examples
          </Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Grid container spacing={3}>
            <Grid item xs={12} md={6}>
              <Card variant="outlined">
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    Tool Discovery
                  </Typography>
                  <Paper sx={{ p: 2, bgcolor: 'grey.100', fontFamily: 'monospace', fontSize: '0.875rem', mb: 2 }}>
{`# Discover all available tools
GET /api/v1/mcp/tools

# Response
{
  "tools": [
    {
      "name": "check_stock",
      "adapter": "equipment_asset_tools",
      "description": "Check inventory levels",
      "parameters": {
        "sku": "string",
        "site": "string"
      }
    }
  ]
}`}
                  </Paper>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} md={6}>
              <Card variant="outlined">
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    Tool Execution
                  </Typography>
                  <Paper sx={{ p: 2, bgcolor: 'grey.100', fontFamily: 'monospace', fontSize: '0.875rem', mb: 2 }}>
{`# Execute a tool
POST /api/v1/mcp/execute
{
  "tool_name": "check_stock",
  "adapter": "equipment_asset_tools",
  "parameters": {
    "sku": "ABC123",
    "site": "warehouse_1"
  }
}

# Response
{
  "execution_id": "exec_123",
  "status": "completed",
  "result": {
    "sku": "ABC123",
    "on_hand": 150,
    "available": 120
  }
}`}
                  </Paper>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </AccordionDetails>
      </Accordion>

      {/* Best Practices */}
      <Accordion expanded={expandedSection === 'practices'} onChange={handleChange('practices')}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <SchoolIcon color="primary" />
            Best Practices
          </Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Grid container spacing={3}>
            <Grid item xs={12} md={6}>
              <Card variant="outlined">
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    🚀 Performance Optimization
                  </Typography>
                  <List>
                    <ListItem>
                      <ListItemText 
                        primary="Use Batch Execution" 
                        secondary="Execute multiple tools in batch for better performance"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="Implement Caching" 
                        secondary="Cache tool results to reduce redundant executions"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="Monitor Tool Performance" 
                        secondary="Track execution times and optimize slow tools"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="Use Appropriate Routing" 
                        secondary="Choose routing strategy based on use case (performance vs accuracy)"
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
                    🔒 Security Considerations
                  </Typography>
                  <List>
                    <ListItem>
                      <ListItemText 
                        primary="Validate Tool Parameters" 
                        secondary="Always validate input parameters before tool execution"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="Implement Access Control" 
                        secondary="Control which tools can be executed by which users"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="Audit Tool Usage" 
                        secondary="Log all tool executions for security auditing"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="Handle Errors Gracefully" 
                        secondary="Implement proper error handling and rollback mechanisms"
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
          MCP Integration Guide - Warehouse Operational Assistant
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

export default MCPIntegrationGuide;
