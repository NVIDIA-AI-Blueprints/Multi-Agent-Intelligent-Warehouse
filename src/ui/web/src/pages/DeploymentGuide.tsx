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
  Stepper,
  Step,
  StepLabel,
  StepContent,
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
  Storage as DockerIcon,
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';

const DeploymentGuide: React.FC = () => {
  const navigate = useNavigate();
  const [expandedSection, setExpandedSection] = useState<string | false>('overview');

  const handleChange = (panel: string) => (event: React.SyntheticEvent, isExpanded: boolean) => {
    setExpandedSection(isExpanded ? panel : false);
  };

  const deploymentEnvironments = [
    {
      name: "Development",
      description: "Local development environment",
      requirements: {
        cpu: "2 cores",
        ram: "4GB",
        storage: "20GB SSD",
        network: "100 Mbps"
      },
      services: ["PostgreSQL", "Redis", "Milvus", "NVIDIA NIMs"],
      status: "✅ Ready"
    },
    {
      name: "Staging",
      description: "Pre-production testing environment",
      requirements: {
        cpu: "4 cores",
        ram: "8GB",
        storage: "50GB SSD",
        network: "1 Gbps"
      },
      services: ["PostgreSQL", "Redis", "Milvus", "NVIDIA NIMs", "Prometheus", "Grafana"],
      status: "✅ Ready"
    },
    {
      name: "Production",
      description: "Production environment with high availability",
      requirements: {
        cpu: "8+ cores",
        ram: "16GB+",
        storage: "100GB+ SSD",
        network: "10 Gbps"
      },
      services: ["PostgreSQL Cluster", "Redis Cluster", "Milvus Cluster", "NVIDIA NIMs", "Full Monitoring Stack", "Load Balancer"],
      status: "🔄 In Progress"
    }
  ];

  const deploymentMethods = [
    {
      name: "Docker Compose",
      description: "Simple containerized deployment for development and small production",
      pros: ["Easy setup", "Single command deployment", "Good for development"],
      cons: ["Single node only", "Limited scalability", "No high availability"],
      commands: [
        "docker-compose up -d",
        "docker-compose logs -f",
        "docker-compose down"
      ],
      status: "✅ Available"
    },
  ];

  const deploymentSteps = [
    {
      label: "Prerequisites",
      description: "Install required software and dependencies",
      content: [
        "Install Docker and Docker Compose",
        "Set up NVIDIA GPU drivers (for Milvus)",
        "Configure NVIDIA API keys"
      ]
    },
    {
      label: "Configuration",
      description: "Configure environment variables and settings",
      content: [
        "Copy .env.example to .env",
        "Set database credentials",
        "Configure NVIDIA API keys",
        "Set up monitoring endpoints",
        "Configure security settings"
      ]
    },
    {
      label: "Database Setup",
      description: "Initialize databases and run migrations",
      content: [
        "Start PostgreSQL/TimescaleDB",
        "Run database migrations",
        "Initialize Milvus collections",
        "Set up Redis configuration",
        "Verify database connections"
      ]
    },
    {
      label: "Service Deployment",
      description: "Deploy application services",
      content: [
        "Deploy core services (API, agents)",
        "Deploy MCP framework",
        "Deploy monitoring stack",
        "Deploy frontend application",
        "Verify all services are running"
      ]
    },
    {
      label: "Health Checks",
      description: "Verify deployment and run health checks",
      content: [
        "Check API health endpoints",
        "Verify agent functionality",
        "Test MCP tool discovery",
        "Check monitoring dashboards",
        "Run integration tests"
      ]
    }
  ];

  const monitoringSetup = [
    {
      service: "Prometheus",
      description: "Metrics collection and storage",
      port: 9090,
      config: "monitoring/prometheus/prometheus.yml",
      status: "✅ Configured"
    },
    {
      service: "Grafana",
      description: "Visualization and dashboards",
      port: 3000,
      config: "monitoring/grafana/dashboards/",
      status: "✅ Configured"
    },
    {
      service: "Alertmanager",
      description: "Alert routing and notifications",
      port: 9093,
      config: "monitoring/alertmanager/alertmanager.yml",
      status: "✅ Configured"
    },
    {
      service: "Node Exporter",
      description: "System metrics collection",
      port: 9100,
      config: "Built-in",
      status: "✅ Configured"
    }
  ];

  return (
    <Box sx={{ p: 3, maxWidth: 1200, mx: 'auto' }}>
      {/* Breadcrumbs */}
      <Breadcrumbs sx={{ mb: 2 }}>
        <Button startIcon={<ArrowBackIcon />} onClick={() => navigate('/documentation')}>
          Documentation
        </Button>
        <Typography color="text.primary">Deployment Guide</Typography>
      </Breadcrumbs>

      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h3" component="h1" gutterBottom sx={{ fontWeight: 'bold', color: 'primary.main' }}>
          Deployment Guide
        </Typography>
        <Typography variant="h5" component="h2" gutterBottom color="text.secondary">
          Production Deployment Instructions
        </Typography>
        <Typography variant="body1" sx={{ mb: 2 }}>
          Comprehensive guide for deploying the Multi-Agent-Intelligent-Warehouse across different environments. 
          This guide covers Docker Compose deployment with monitoring and security configurations.
        </Typography>
        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mb: 3 }}>
          <Chip label="Docker" color="primary" />
          <Chip label="Production Ready" color="success" />
          <Chip label="Monitoring" color="warning" />
        </Box>
      </Box>

      {/* Status Alert */}
      <Alert severity="info" sx={{ mb: 4 }}>
        <AlertTitle>🚀 Multiple Deployment Options</AlertTitle>
        The system supports multiple deployment methods from simple Docker Compose for development 
        for production environments.
      </Alert>

      {/* Deployment Environments */}
      <Accordion expanded={expandedSection === 'environments'} onChange={handleChange('environments')}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <CloudIcon color="primary" />
            Deployment Environments
          </Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Grid container spacing={3}>
            {deploymentEnvironments.map((env, index) => (
              <Grid item xs={12} md={4} key={index}>
                <Card variant="outlined" sx={{ height: '100%' }}>
                  <CardContent>
                    <Typography variant="h6" gutterBottom>
                      {env.name}
                    </Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                      {env.description}
                    </Typography>
                    <Box sx={{ mb: 2 }}>
                      <Typography variant="subtitle2" gutterBottom>Requirements:</Typography>
                      <List dense>
                        <ListItem sx={{ py: 0 }}>
                          <ListItemText primary={`CPU: ${env.requirements.cpu}`} primaryTypographyProps={{ variant: 'body2' }} />
                        </ListItem>
                        <ListItem sx={{ py: 0 }}>
                          <ListItemText primary={`RAM: ${env.requirements.ram}`} primaryTypographyProps={{ variant: 'body2' }} />
                        </ListItem>
                        <ListItem sx={{ py: 0 }}>
                          <ListItemText primary={`Storage: ${env.requirements.storage}`} primaryTypographyProps={{ variant: 'body2' }} />
                        </ListItem>
                        <ListItem sx={{ py: 0 }}>
                          <ListItemText primary={`Network: ${env.requirements.network}`} primaryTypographyProps={{ variant: 'body2' }} />
                        </ListItem>
                      </List>
                    </Box>
                    <Box sx={{ mb: 2 }}>
                      <Typography variant="subtitle2" gutterBottom>Services:</Typography>
                      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                        {env.services.map((service, serviceIndex) => (
                          <Chip key={serviceIndex} label={service} size="small" variant="outlined" />
                        ))}
                      </Box>
                    </Box>
                    <Chip 
                      label={env.status} 
                      color={env.status.includes('✅') ? 'success' : 'warning'}
                      size="small"
                    />
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </AccordionDetails>
      </Accordion>

      {/* Deployment Methods */}
      <Accordion expanded={expandedSection === 'methods'} onChange={handleChange('methods')}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <BuildIcon color="primary" />
            Deployment Methods
          </Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Grid container spacing={3}>
            {deploymentMethods.map((method, index) => (
              <Grid item xs={12} md={4} key={index}>
                <Card variant="outlined" sx={{ height: '100%' }}>
                  <CardContent>
                    <Typography variant="h6" gutterBottom>
                      {method.name}
                    </Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                      {method.description}
                    </Typography>
                    <Box sx={{ mb: 2 }}>
                      <Typography variant="subtitle2" gutterBottom>Pros:</Typography>
                      <List dense>
                        {method.pros.map((pro, proIndex) => (
                          <ListItem key={proIndex} sx={{ py: 0 }}>
                            <ListItemIcon>
                              <CheckCircleIcon fontSize="small" color="success" />
                            </ListItemIcon>
                            <ListItemText primary={pro} primaryTypographyProps={{ variant: 'body2' }} />
                          </ListItem>
                        ))}
                      </List>
                    </Box>
                    <Box sx={{ mb: 2 }}>
                      <Typography variant="subtitle2" gutterBottom>Commands:</Typography>
                      {method.commands.map((command, cmdIndex) => (
                        <Paper key={cmdIndex} sx={{ p: 1, bgcolor: 'grey.100', fontFamily: 'monospace', fontSize: '0.75rem', mb: 1 }}>
                          {command}
                        </Paper>
                      ))}
                    </Box>
                    <Chip 
                      label={method.status} 
                      color={method.status.includes('✅') ? 'success' : 'warning'}
                      size="small"
                    />
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </AccordionDetails>
      </Accordion>

      {/* Deployment Steps */}
      <Accordion expanded={expandedSection === 'steps'} onChange={handleChange('steps')}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <RocketIcon color="primary" />
            Step-by-Step Deployment
          </Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Stepper orientation="vertical">
            {deploymentSteps.map((step, index) => (
              <Step key={step.label} active={true}>
                <StepLabel>{step.label}</StepLabel>
                <StepContent>
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                    {step.description}
                  </Typography>
                  <List dense>
                    {step.content.map((item, itemIndex) => (
                      <ListItem key={itemIndex} sx={{ py: 0 }}>
                        <ListItemIcon>
                          <CheckCircleIcon fontSize="small" color="primary" />
                        </ListItemIcon>
                        <ListItemText primary={item} primaryTypographyProps={{ variant: 'body2' }} />
                      </ListItem>
                    ))}
                  </List>
                </StepContent>
              </Step>
            ))}
          </Stepper>
        </AccordionDetails>
      </Accordion>

      {/* Monitoring Setup */}
      <Accordion expanded={expandedSection === 'monitoring'} onChange={handleChange('monitoring')}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <DashboardIcon color="primary" />
            Monitoring Setup
          </Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Grid container spacing={3}>
            {monitoringSetup.map((service, index) => (
              <Grid item xs={12} md={6} key={index}>
                <Card variant="outlined">
                  <CardContent>
                    <Typography variant="h6" gutterBottom>
                      {service.service}
                    </Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                      {service.description}
                    </Typography>
                    <List dense>
                      <ListItem sx={{ py: 0 }}>
                        <ListItemText 
                          primary={`Port: ${service.port}`} 
                          primaryTypographyProps={{ variant: 'body2' }}
                        />
                      </ListItem>
                      <ListItem sx={{ py: 0 }}>
                        <ListItemText 
                          primary={`Config: ${service.config}`} 
                          primaryTypographyProps={{ variant: 'body2' }}
                        />
                      </ListItem>
                    </List>
                    <Chip 
                      label={service.status} 
                      color={service.status.includes('✅') ? 'success' : 'warning'}
                      size="small"
                    />
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </AccordionDetails>
      </Accordion>

      {/* Security Configuration */}
      <Accordion expanded={expandedSection === 'security'} onChange={handleChange('security')}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <SecurityIcon color="primary" />
            Security Configuration
          </Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Grid container spacing={3}>
            <Grid item xs={12} md={6}>
              <Card variant="outlined">
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    🔐 Authentication
                  </Typography>
                  <List>
                    <ListItem>
                      <ListItemText 
                        primary="JWT Token Configuration" 
                        secondary="Set secure JWT secret and expiration times"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="OAuth2 Integration" 
                        secondary="Configure OAuth2 providers for SSO"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="Role-Based Access Control" 
                        secondary="Configure user roles and permissions"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="API Rate Limiting" 
                        secondary="Implement rate limiting for API endpoints"
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
                    🛡️ Network Security
                  </Typography>
                  <List>
                    <ListItem>
                      <ListItemText 
                        primary="HTTPS Configuration" 
                        secondary="Enable SSL/TLS for all communications"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="Firewall Rules" 
                        secondary="Configure firewall rules for service access"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="Network Policies" 
                        secondary="Implement network policies and firewall rules"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="Secrets Management" 
                        secondary="Use Docker secrets or external secret management"
                      />
                    </ListItem>
                  </List>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </AccordionDetails>
      </Accordion>

      {/* Troubleshooting */}
      <Accordion expanded={expandedSection === 'troubleshooting'} onChange={handleChange('troubleshooting')}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <BugReportIcon color="primary" />
            Troubleshooting
          </Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Grid container spacing={3}>
            <Grid item xs={12} md={6}>
              <Card variant="outlined">
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    🚨 Common Issues
                  </Typography>
                  <List>
                    <ListItem>
                      <ListItemText 
                        primary="Database Connection Failed" 
                        secondary="Check PostgreSQL credentials and network connectivity"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="NVIDIA API Errors" 
                        secondary="Verify API keys and quota limits"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="MCP Tool Discovery Fails" 
                        secondary="Check adapter registration and tool definitions"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="Memory Issues" 
                        secondary="Increase container memory limits or optimize queries"
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
                    🔧 Debug Commands
                  </Typography>
                  <List>
                    <ListItem>
                      <ListItemText 
                        primary="Check Service Status" 
                        secondary="docker-compose ps or kubectl get pods"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="View Logs" 
                        secondary="docker-compose logs -f or kubectl logs -f"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="Health Check" 
                        secondary="curl http://localhost:8002/api/v1/health"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="Database Check" 
                        secondary="psql -h localhost -p 5435 -U warehouse_user"
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
          Deployment Guide - Multi-Agent-Intelligent-Warehouse
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

export default DeploymentGuide;
