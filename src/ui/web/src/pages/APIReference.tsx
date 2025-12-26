import React, { useState } from 'react';
import {
  Box,
  Typography,
  Paper,
  Grid,
  Button,
  Chip,
  List,
  ListItem,
  ListItemText,
  Alert,
  AlertTitle,
  Breadcrumbs,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
} from '@mui/material';
import {
  Code as CodeIcon,
  Cloud as CloudIcon,
  BugReport as BugReportIcon,
  Api as ApiIcon,
  Dashboard as DashboardIcon,
  ArrowBack as ArrowBackIcon,
  CheckCircle as CheckCircleIcon,
  GitHub as GitHubIcon,
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { CodeBlock, SectionAccordion, InfoCard, MethodChip, StatusChip } from '../components/common';

const APIReference: React.FC = () => {
  const navigate = useNavigate();
  const [expandedSection, setExpandedSection] = useState<string | false>('overview');

  const handleChange = (panel: string) => (event: React.SyntheticEvent, isExpanded: boolean) => {
    setExpandedSection(isExpanded ? panel : false);
  };

  const apiCategories = [
    {
      name: "Core Chat",
      description: "Main chat interface and agent routing",
      endpoints: [
        { method: "POST", path: "/api/v1/chat", description: "Main chat interface with agent routing", status: "✅ Working" },
        { method: "GET", path: "/api/v1/health", description: "System health check", status: "✅ Working" },
        { method: "GET", path: "/api/v1/metrics", description: "Prometheus metrics", status: "✅ Working" }
      ]
    },
    {
      name: "Agent Operations",
      description: "Specialized agent operations and tool execution",
      endpoints: [
        { method: "GET", path: "/api/v1/equipment/assignments", description: "Get equipment assignments", status: "✅ Working" },
        { method: "POST", path: "/api/v1/operations/waves", description: "Create pick waves", status: "✅ Working" },
        { method: "POST", path: "/api/v1/safety/incidents", description: "Log safety incidents", status: "✅ Working" },
        { method: "GET", path: "/api/v1/equipment/status", description: "Get equipment status", status: "✅ Working" },
        { method: "POST", path: "/api/v1/operations/tasks", description: "Assign tasks to workers", status: "✅ Working" }
      ]
    },
    {
      name: "MCP Framework",
      description: "Model Context Protocol tool discovery and execution",
      endpoints: [
        { method: "GET", path: "/api/v1/mcp/tools", description: "Discover available tools", status: "✅ Working" },
        { method: "GET", path: "/api/v1/mcp/status", description: "MCP system status", status: "✅ Working" },
        { method: "POST", path: "/api/v1/mcp/execute", description: "Execute MCP tools", status: "✅ Working" },
        { method: "GET", path: "/api/v1/mcp/adapters", description: "List registered adapters", status: "✅ Working" }
      ]
    },
    {
      name: "Reasoning Engine",
      description: "Advanced reasoning capabilities and analysis",
      endpoints: [
        { method: "POST", path: "/api/v1/reasoning/analyze", description: "Deep reasoning analysis", status: "✅ Working" },
        { method: "GET", path: "/api/v1/reasoning/types", description: "Available reasoning types", status: "✅ Working" },
        { method: "POST", path: "/api/v1/reasoning/chat-with-reasoning", description: "Chat with reasoning", status: "✅ Working" },
        { method: "GET", path: "/api/v1/reasoning/insights", description: "Get reasoning insights", status: "⚠️ Partial" }
      ]
    },
    {
      name: "Authentication",
      description: "User authentication and authorization",
      endpoints: [
        { method: "POST", path: "/api/v1/auth/login", description: "User login", status: "✅ Working" },
        { method: "POST", path: "/api/v1/auth/logout", description: "User logout", status: "✅ Working" },
        { method: "GET", path: "/api/v1/auth/profile", description: "Get user profile", status: "✅ Working" },
        { method: "POST", path: "/api/v1/auth/refresh", description: "Refresh JWT token", status: "✅ Working" },
        { method: "GET", path: "/api/v1/auth/users/public", description: "Get list of users for dropdown selection (public, no auth required)", status: "✅ Working" },
        { method: "GET", path: "/api/v1/auth/users", description: "Get all users (admin only)", status: "✅ Working" }
      ]
    },
    {
      name: "Monitoring",
      description: "System monitoring and observability",
      endpoints: [
        { method: "GET", path: "/api/v1/monitoring/health", description: "Detailed health check", status: "✅ Working" },
        { method: "GET", path: "/api/v1/monitoring/metrics", description: "System metrics", status: "✅ Working" },
        { method: "GET", path: "/api/v1/monitoring/logs", description: "System logs", status: "✅ Working" },
        { method: "GET", path: "/api/v1/monitoring/alerts", description: "Active alerts", status: "✅ Working" }
      ]
    }
  ];

  const requestExamples = [
    {
      title: "Chat Request",
      description: "Send a message to the chat interface",
      method: "POST",
      path: "/api/v1/chat",
      request: {
        "message": "Dispatch forklift FL-02 to Zone A for pick operations",
        "session_id": "user_session_123",
        "context": {
          "user_id": "user_456",
          "role": "operator"
        }
      },
      response: {
        "response_id": "resp_789",
        "message": "Forklift FL-02 has been successfully dispatched to Zone A for pick operations. Estimated arrival time is 5 minutes.",
        "agent": "equipment_agent",
        "confidence": 0.92,
        "structured_data": {
          "equipment_id": "FL-02",
          "destination": "Zone A",
          "operation": "pick operations",
          "status": "dispatched",
          "eta": "5 minutes"
        },
        "actions_taken": [
          {
            "action": "dispatch_equipment",
            "equipment_id": "FL-02",
            "destination": "Zone A"
          }
        ]
      }
    },
    {
      title: "Tool Discovery",
      description: "Discover available MCP tools",
      method: "GET",
      path: "/api/v1/mcp/tools",
      request: null,
      response: {
        "tools": [
          {
            "name": "check_stock",
            "adapter": "equipment_asset_tools",
            "description": "Check inventory levels for specific SKUs",
            "parameters": {
              "sku": "string",
              "site": "string",
              "locations": "array"
            },
            "return_type": "StockInfo"
          },
          {
            "name": "dispatch_equipment",
            "adapter": "operations_action_tools", 
            "description": "Dispatch equipment to specific locations",
            "parameters": {
              "equipment_id": "string",
              "destination": "string",
              "operation": "string"
            },
            "return_type": "DispatchResult"
          }
        ],
        "total_tools": 23,
        "adapters": ["equipment_asset_tools", "operations_action_tools", "safety_action_tools"]
      }
    },
    {
      title: "Reasoning Analysis",
      description: "Perform deep reasoning analysis",
      method: "POST",
      path: "/api/v1/reasoning/analyze",
      request: {
        "query": "What factors should be considered when optimizing warehouse layout?",
        "reasoning_types": ["chain_of_thought", "scenario_analysis"],
        "context": {
          "warehouse_type": "distribution_center",
          "current_layout": "zone_based"
        }
      },
      response: {
        "analysis_id": "analysis_456",
        "reasoning_chains": [
          {
            "type": "chain_of_thought",
            "steps": [
              "Analyze current warehouse layout efficiency",
              "Identify bottlenecks in material flow",
              "Consider space utilization optimization",
              "Evaluate impact on worker productivity"
            ],
            "conclusion": "Zone-based layout with dynamic routing optimization"
          }
        ],
        "confidence": 0.87,
        "recommendations": [
          "Implement dynamic routing algorithms",
          "Optimize zone boundaries based on order patterns",
          "Consider vertical space utilization"
        ]
      }
    }
  ];

  const statusCodes = [
    { code: 200, description: "Success", meaning: "Request completed successfully" },
    { code: 201, description: "Created", meaning: "Resource created successfully" },
    { code: 400, description: "Bad Request", meaning: "Invalid request parameters" },
    { code: 401, description: "Unauthorized", meaning: "Authentication required" },
    { code: 403, description: "Forbidden", meaning: "Insufficient permissions" },
    { code: 404, description: "Not Found", meaning: "Resource not found" },
    { code: 422, description: "Unprocessable Entity", meaning: "Validation error" },
    { code: 500, description: "Internal Server Error", meaning: "Server error occurred" }
  ];

  return (
    <Box sx={{ p: 3, maxWidth: 1200, mx: 'auto' }}>
      {/* Breadcrumbs */}
      <Breadcrumbs sx={{ mb: 2 }}>
        <Button startIcon={<ArrowBackIcon />} onClick={() => navigate('/documentation')}>
          Documentation
        </Button>
        <Typography color="text.primary">API Reference</Typography>
      </Breadcrumbs>

      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h3" component="h1" gutterBottom sx={{ fontWeight: 'bold', color: 'primary.main' }}>
          API Reference
        </Typography>
        <Typography variant="h5" component="h2" gutterBottom color="text.secondary">
          Comprehensive API Documentation
        </Typography>
        <Typography variant="body1" sx={{ mb: 2 }}>
          Complete reference for all API endpoints in the Multi-Agent-Intelligent-Warehouse. 
          This documentation covers authentication, agent operations, MCP framework, reasoning engine, and monitoring APIs.
        </Typography>
        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mb: 3 }}>
          <Chip label="REST API" color="primary" />
          <Chip label="OpenAPI/Swagger" color="secondary" />
          <Chip label="JWT Authentication" color="info" />
          <Chip label="Real-time" color="warning" />
          <Chip label="Production Ready" color="success" />
        </Box>
      </Box>

      {/* Status Alert */}
      <Alert severity="success" sx={{ mb: 4 }}>
        <AlertTitle>✅ All Core APIs Working</AlertTitle>
        All essential API endpoints are operational and tested. The system provides comprehensive REST API coverage 
        with proper authentication, error handling, and documentation.
      </Alert>

      {/* Base URL */}
      <SectionAccordion
        id="base"
        expanded={expandedSection}
        onChange={handleChange}
        icon={CloudIcon}
        title="Base URL & Authentication"
      >
        <Grid container spacing={3}>
          <Grid item xs={12} md={6}>
            <InfoCard title="🌐 Base URLs">
              <List>
                <ListItem>
                  <ListItemText 
                    primary="Development" 
                    secondary="http://localhost:8002"
                  />
                </ListItem>
                <ListItem>
                  <ListItemText 
                    primary="Staging" 
                    secondary="https://staging-api.warehouse-assistant.com"
                  />
                </ListItem>
                <ListItem>
                  <ListItemText 
                    primary="Production" 
                    secondary="https://api.warehouse-assistant.com"
                  />
                </ListItem>
              </List>
            </InfoCard>
          </Grid>
          <Grid item xs={12} md={6}>
            <InfoCard title="🔐 Authentication">
              <Typography variant="body2" sx={{ mb: 2 }}>
                All API requests require JWT authentication via Authorization header:
              </Typography>
              <CodeBlock>
{`Authorization: Bearer <jwt_token>

# Example
curl -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
  -H "Content-Type: application/json"
  https://api.warehouse-assistant.com/api/v1/chat`}
              </CodeBlock>
            </InfoCard>
          </Grid>
        </Grid>
      </SectionAccordion>

      {/* API Categories */}
      <SectionAccordion
        id="endpoints"
        expanded={expandedSection}
        onChange={handleChange}
        icon={ApiIcon}
        title="API Endpoints"
      >
        <Grid container spacing={3}>
          {apiCategories.map((category, index) => (
            <Grid item xs={12} md={6} key={index}>
              <InfoCard title={category.name} description={category.description} sx={{ height: '100%' }}>
                <List dense>
                  {category.endpoints.map((endpoint, epIndex) => (
                    <ListItem key={epIndex} sx={{ px: 0 }}>
                      <ListItemText
                        primary={
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                            <MethodChip method={endpoint.method} />
                            <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                              {endpoint.path}
                            </Typography>
                            <StatusChip status={endpoint.status} />
                          </Box>
                        }
                        secondary={endpoint.description}
                      />
                    </ListItem>
                  ))}
                </List>
              </InfoCard>
            </Grid>
          ))}
        </Grid>
      </SectionAccordion>

      {/* Request Examples */}
      <SectionAccordion
        id="examples"
        expanded={expandedSection}
        onChange={handleChange}
        icon={CodeIcon}
        title="Request Examples"
      >
        <Grid container spacing={3}>
          {requestExamples.map((example, index) => (
            <Grid item xs={12} key={index}>
              <InfoCard title={example.title} description={example.description}>
                <Grid container spacing={2}>
                  <Grid item xs={12} md={6}>
                    <Typography variant="subtitle2" gutterBottom>
                      Request ({example.method} {example.path})
                    </Typography>
                    <CodeBlock>
                      {example.request ? JSON.stringify(example.request, null, 2) : 'No request body'}
                    </CodeBlock>
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <Typography variant="subtitle2" gutterBottom>
                      Response
                    </Typography>
                    <CodeBlock>
                      {JSON.stringify(example.response, null, 2)}
                    </CodeBlock>
                  </Grid>
                </Grid>
              </InfoCard>
            </Grid>
          ))}
        </Grid>
      </SectionAccordion>

      {/* Status Codes */}
      <SectionAccordion
        id="status"
        expanded={expandedSection}
        onChange={handleChange}
        icon={CheckCircleIcon}
        title="HTTP Status Codes"
      >
        <TableContainer component={Paper}>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>Code</TableCell>
                <TableCell>Description</TableCell>
                <TableCell>Meaning</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {statusCodes.map((status, index) => (
                <TableRow key={index}>
                  <TableCell>
                    <Chip 
                      label={status.code} 
                      color={status.code < 300 ? 'success' : status.code < 400 ? 'warning' : 'error'}
                      size="small"
                    />
                  </TableCell>
                  <TableCell>{status.description}</TableCell>
                  <TableCell>{status.meaning}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </SectionAccordion>

      {/* Error Handling */}
      <SectionAccordion
        id="errors"
        expanded={expandedSection}
        onChange={handleChange}
        icon={BugReportIcon}
        title="Error Handling"
      >
        <Grid container spacing={3}>
          <Grid item xs={12} md={6}>
            <InfoCard title="🚨 Error Response Format">
              <CodeBlock sx={{ mb: 2 }}>
{`{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid request parameters",
    "details": {
      "field": "sku",
      "issue": "SKU must be alphanumeric"
    },
    "timestamp": "2024-01-15T10:30:00Z",
    "request_id": "req_123456"
  }
}`}
              </CodeBlock>
            </InfoCard>
          </Grid>
          <Grid item xs={12} md={6}>
            <InfoCard title="🔧 Common Error Codes">
              <List dense>
                <ListItem>
                  <ListItemText 
                    primary="VALIDATION_ERROR" 
                    secondary="Request validation failed"
                  />
                </ListItem>
                <ListItem>
                  <ListItemText 
                    primary="AUTHENTICATION_REQUIRED" 
                    secondary="Valid JWT token required"
                  />
                </ListItem>
                <ListItem>
                  <ListItemText 
                    primary="INSUFFICIENT_PERMISSIONS" 
                    secondary="User lacks required permissions"
                  />
                </ListItem>
                <ListItem>
                  <ListItemText 
                    primary="RESOURCE_NOT_FOUND" 
                    secondary="Requested resource doesn't exist"
                  />
                </ListItem>
                <ListItem>
                  <ListItemText 
                    primary="RATE_LIMIT_EXCEEDED" 
                    secondary="Too many requests"
                  />
                </ListItem>
              </List>
            </InfoCard>
          </Grid>
        </Grid>
      </SectionAccordion>

      {/* Footer */}
      <Box sx={{ mt: 4, pt: 3, borderTop: 1, borderColor: 'divider' }}>
        <Typography variant="body2" color="text.secondary" align="center">
          API Reference - Multi-Agent-Intelligent-Warehouse
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

export default APIReference;
