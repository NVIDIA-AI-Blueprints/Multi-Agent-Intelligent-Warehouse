import React, { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Button,
  TextField,
  Chip,
  List,
  ListItem,
  ListItemText,
  ListItemSecondaryAction,
  IconButton,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Alert,
  CircularProgress,
  Grid,
  Paper,
  Divider,
  Tabs,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Badge,
  Tooltip,
  LinearProgress,
  Collapse,
} from '@mui/material';
import {
  ExpandMore as ExpandMoreIcon,
  PlayArrow as PlayIcon,
  Refresh as RefreshIcon,
  Search as SearchIcon,
  CheckCircle as CheckCircleIcon,
  Error as ErrorIcon,
  Info as InfoIcon,
  History as HistoryIcon,
  Speed as SpeedIcon,
  Assessment as AssessmentIcon,
  Code as CodeIcon,
  Visibility as VisibilityIcon,
} from '@mui/icons-material';
import { mcpAPI } from '../services/api';

interface MCPTool {
  tool_id: string;
  name: string;
  description: string;
  category: string;
  source: string;
  capabilities: string[];
  metadata: any;
  parameters?: any;  // Tool parameter schema
  relevance_score?: number;
}

interface MCPStatus {
  status: string;
  tool_discovery: {
    discovered_tools: number;
    discovery_sources: number;
    is_running: boolean;
  };
  services: {
    tool_discovery: string;
    tool_binding: string;
    tool_routing: string;
    tool_validation: string;
  };
}

interface ExecutionHistory {
  id: string;
  timestamp: Date;
  tool_id: string;
  tool_name: string;
  success: boolean;
  execution_time: number;
  result: any;
  error?: string;
}

interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

function TabPanel(props: TabPanelProps) {
  const { children, value, index, ...other } = props;
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`mcp-tabpanel-${index}`}
      aria-labelledby={`mcp-tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ p: 3 }}>{children}</Box>}
    </div>
  );
}

const EnhancedMCPTestingPanel: React.FC = () => {
  const [mcpStatus, setMcpStatus] = useState<MCPStatus | null>(null);
  const [tools, setTools] = useState<MCPTool[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<MCPTool[]>([]);
  const [testMessage, setTestMessage] = useState('');
  const [testResult, setTestResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [refreshLoading, setRefreshLoading] = useState(false);
  const [tabValue, setTabValue] = useState(0);
  const [executionHistory, setExecutionHistory] = useState<ExecutionHistory[]>([]);
  const [showToolDetails, setShowToolDetails] = useState<string | null>(null);
  const [toolParameters, setToolParameters] = useState<{ [key: string]: any }>({});
  const [selectedToolForExecution, setSelectedToolForExecution] = useState<MCPTool | null>(null);
  const [showParameterDialog, setShowParameterDialog] = useState(false);
  const [agentsStatus, setAgentsStatus] = useState<any>(null);
  const [selectedHistoryEntry, setSelectedHistoryEntry] = useState<ExecutionHistory | null>(null);
  const [performanceMetrics, setPerformanceMetrics] = useState({
    totalExecutions: 0,
    successRate: 0,
    averageExecutionTime: 0,
    lastExecutionTime: 0
  });

  // Load MCP status and tools on component mount
  useEffect(() => {
    loadMcpData();
    loadExecutionHistory();
    loadAgentsStatus();
  }, []);

  const loadAgentsStatus = async () => {
    try {
      const status = await mcpAPI.getAgents();
      setAgentsStatus(status);
    } catch (err: any) {
      console.warn(`Failed to load agents status: ${err.message}`);
    }
  };

  const loadMcpData = async () => {
    try {
      setLoading(true);
      setError(null);
      setSuccess(null);
      
      // Load MCP status
      const status = await mcpAPI.getStatus();
      setMcpStatus(status);
      
      // Load discovered tools
      const toolsData = await mcpAPI.getTools();
      setTools(toolsData.tools || []);
      
      if (toolsData.tools && toolsData.tools.length > 0) {
        setSuccess(`Successfully loaded ${toolsData.tools.length} MCP tools`);
      } else {
        setError('No MCP tools discovered. Try refreshing discovery.');
      }
      
    } catch (err: any) {
      setError(`Failed to load MCP data: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const loadExecutionHistory = () => {
    const history = JSON.parse(localStorage.getItem('mcp_execution_history') || '[]');
    setExecutionHistory(history);
    updatePerformanceMetrics(history);
  };

  const updatePerformanceMetrics = (history: ExecutionHistory[]) => {
    if (history.length === 0) return;
    
    const totalExecutions = history.length;
    const successfulExecutions = history.filter(h => h.success).length;
    const successRate = (successfulExecutions / totalExecutions) * 100;
    const averageExecutionTime = history.reduce((sum, h) => sum + h.execution_time, 0) / totalExecutions;
    const lastExecutionTime = history[history.length - 1]?.execution_time || 0;
    
    setPerformanceMetrics({
      totalExecutions,
      successRate,
      averageExecutionTime,
      lastExecutionTime
    });
  };

  const handleRefreshDiscovery = async () => {
    try {
      setRefreshLoading(true);
      setError(null);
      setSuccess(null);
      
      const result = await mcpAPI.refreshDiscovery();
      setSuccess(`Discovery refreshed: ${result.total_tools} tools found`);
      
      // Reload data after refresh
      await loadMcpData();
      
    } catch (err: any) {
      setError(`Failed to refresh discovery: ${err.message}`);
    } finally {
      setRefreshLoading(false);
    }
  };

  const handleSearchTools = async () => {
    if (!searchQuery.trim()) return;
    
    try {
      setLoading(true);
      setError(null);
      setSuccess(null);
      
      const results = await mcpAPI.searchTools(searchQuery);
      setSearchResults(results.tools || []);
      
      if (results.tools && results.tools.length > 0) {
        setSuccess(`Found ${results.tools.length} tools matching "${searchQuery}"`);
      } else {
        setError(`No tools found matching "${searchQuery}". Try a different search term.`);
      }
      
    } catch (err: any) {
      setError(`Search failed: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleTestWorkflow = async () => {
    if (!testMessage.trim()) return;
    
    try {
      setLoading(true);
      setError(null);
      setSuccess(null);
      
      const startTime = Date.now();
      const result = await mcpAPI.testWorkflow(testMessage);
      const executionTime = Date.now() - startTime;
      
      setTestResult(result);
      
      // Add to execution history
      const historyEntry: ExecutionHistory = {
        id: Date.now().toString(),
        timestamp: new Date(),
        tool_id: 'workflow_test',
        tool_name: 'MCP Workflow Test',
        success: result.status === 'success',
        execution_time: executionTime,
        result: result,
        error: result.status !== 'success' ? result.error : undefined
      };
      
      const newHistory = [historyEntry, ...executionHistory.slice(0, 49)]; // Keep last 50
      setExecutionHistory(newHistory);
      localStorage.setItem('mcp_execution_history', JSON.stringify(newHistory));
      updatePerformanceMetrics(newHistory);
      
      if (result.status === 'success') {
        setSuccess(`Workflow test completed successfully in ${executionTime}ms`);
      } else {
        setError(`Workflow test failed: ${result.error || 'Unknown error'}`);
      }
      
    } catch (err: any) {
      setError(`Workflow test failed: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleExecuteTool = async (toolId: string, toolName: string, parameters?: any) => {
    try {
      setLoading(true);
      setError(null);
      
      const startTime = Date.now();
      const execParams = parameters || toolParameters[toolId] || { test: true };
      const result = await mcpAPI.executeTool(toolId, execParams);
      const executionTime = Date.now() - startTime;
      
      // Add to execution history
      const historyEntry: ExecutionHistory = {
        id: Date.now().toString(),
        timestamp: new Date(),
        tool_id: toolId,
        tool_name: toolName,
        success: true,
        execution_time: executionTime,
        result: result
      };
      
      const newHistory = [historyEntry, ...executionHistory.slice(0, 49)];
      setExecutionHistory(newHistory);
      localStorage.setItem('mcp_execution_history', JSON.stringify(newHistory));
      updatePerformanceMetrics(newHistory);
      
      setSuccess(`Tool ${toolName} executed successfully in ${executionTime}ms`);
      
    } catch (err: any) {
      const historyEntry: ExecutionHistory = {
        id: Date.now().toString(),
        timestamp: new Date(),
        tool_id: toolId,
        tool_name: toolName,
        success: false,
        execution_time: 0,
        result: null,
        error: err.message
      };
      
      const newHistory = [historyEntry, ...executionHistory.slice(0, 49)];
      setExecutionHistory(newHistory);
      localStorage.setItem('mcp_execution_history', JSON.stringify(newHistory));
      updatePerformanceMetrics(newHistory);
      
      setError(`Tool execution failed: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const renderToolDetails = (tool: MCPTool) => (
    <Collapse in={showToolDetails === tool.tool_id} timeout="auto" unmountOnExit>
      <Box sx={{ mt: 2, p: 2, bgcolor: 'grey.50', borderRadius: 1 }}>
        <Typography variant="subtitle2" gutterBottom>Tool Details:</Typography>
        <Typography variant="body2" sx={{ mb: 1 }}>
          <strong>ID:</strong> {tool.tool_id}
        </Typography>
        <Typography variant="body2" sx={{ mb: 1 }}>
          <strong>Source:</strong> {tool.source}
        </Typography>
        <Typography variant="body2" sx={{ mb: 1 }}>
          <strong>Category:</strong> {tool.category}
        </Typography>
        <Typography variant="body2" sx={{ mb: 1 }}>
          <strong>Capabilities:</strong> {tool.capabilities?.join(', ') || 'None'}
        </Typography>
        {tool.parameters && (
          <Box sx={{ mb: 2 }}>
            <Typography variant="body2" sx={{ mb: 1 }}>
              <strong>Parameters:</strong>
            </Typography>
            <Paper sx={{ p: 1, bgcolor: 'white', maxHeight: 200, overflow: 'auto' }}>
              <pre style={{ fontSize: '0.75rem', margin: 0 }}>
                {JSON.stringify(tool.parameters, null, 2)}
              </pre>
            </Paper>
          </Box>
        )}
        {tool.metadata && (
          <Typography variant="body2" sx={{ mb: 1 }}>
            <strong>Metadata:</strong>
            <pre style={{ fontSize: '0.75rem', marginTop: 4 }}>
              {JSON.stringify(tool.metadata, null, 2)}
            </pre>
          </Typography>
        )}
      </Box>
    </Collapse>
  );

  return (
    <Box sx={{ p: 2 }}>
      <Typography variant="h5" gutterBottom>
        Enhanced MCP Testing Dashboard
      </Typography>
      
      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {success && (
        <Alert severity="success" sx={{ mb: 2 }} onClose={() => setSuccess(null)}>
          {success}
        </Alert>
      )}

      {/* Performance Metrics */}
      <Grid container spacing={2} sx={{ mb: 3 }}>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                <PlayIcon color="primary" sx={{ mr: 1 }} />
                <Box>
                  <Typography variant="h6">{performanceMetrics.totalExecutions}</Typography>
                  <Typography variant="body2" color="text.secondary">Total Executions</Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                <CheckCircleIcon color="success" sx={{ mr: 1 }} />
                <Box>
                  <Typography variant="h6">{performanceMetrics.successRate.toFixed(1)}%</Typography>
                  <Typography variant="body2" color="text.secondary">Success Rate</Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                <SpeedIcon color="info" sx={{ mr: 1 }} />
                <Box>
                  <Typography variant="h6">{performanceMetrics.averageExecutionTime.toFixed(0)}ms</Typography>
                  <Typography variant="body2" color="text.secondary">Avg Execution Time</Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                <AssessmentIcon color="warning" sx={{ mr: 1 }} />
                <Box>
                  <Typography variant="h6">{mcpStatus?.tool_discovery.discovered_tools || 0}</Typography>
                  <Typography variant="body2" color="text.secondary">Available Tools</Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 2 }}>
        <Tabs value={tabValue} onChange={(e, newValue) => setTabValue(newValue)}>
          <Tab label="Status & Discovery" />
          <Tab label="Tool Search" />
          <Tab label="Workflow Testing" />
          <Tab label="Execution History" />
        </Tabs>
      </Box>

      <TabPanel value={tabValue} index={0}>
        <Grid container spacing={2}>
          {/* Agent Status Section */}
          {agentsStatus && (
            <Grid item xs={12}>
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    Agent Status
                  </Typography>
                  <Grid container spacing={2}>
                    {Object.entries(agentsStatus.agents || {}).map(([agentName, agentInfo]: [string, any]) => (
                      <Grid item xs={12} sm={6} md={4} key={agentName}>
                        <Paper sx={{ p: 2, bgcolor: agentInfo.status === 'operational' ? 'success.light' : 'error.light' }}>
                          <Typography variant="subtitle1" fontWeight="bold" sx={{ textTransform: 'capitalize' }}>
                            {agentName}
                          </Typography>
                          <Chip 
                            label={agentInfo.status} 
                            color={agentInfo.status === 'operational' ? 'success' : 'error'}
                            size="small"
                            sx={{ mt: 1, mb: 1 }}
                          />
                          <Typography variant="body2">
                            MCP Enabled: {agentInfo.mcp_enabled ? 'Yes' : 'No'}
                          </Typography>
                          <Typography variant="body2">
                            Tools Available: {agentInfo.tool_count || 0}
                          </Typography>
                          {agentInfo.note && (
                            <Typography variant="caption" color="text.secondary">
                              {agentInfo.note}
                            </Typography>
                          )}
                        </Paper>
                      </Grid>
                    ))}
                  </Grid>
                </CardContent>
              </Card>
            </Grid>
          )}

          <Grid item xs={12} md={6}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  MCP Framework Status
                </Typography>
                
                {mcpStatus ? (
                  <Box>
                    <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                      <CheckCircleIcon color="success" sx={{ mr: 1 }} />
                      <Typography variant="body1">
                        Status: <strong>{mcpStatus.status}</strong>
                      </Typography>
                    </Box>
                    
                    <Typography variant="body2" gutterBottom>
                      <strong>Tool Discovery:</strong>
                    </Typography>
                    <Typography variant="body2" sx={{ ml: 2 }}>
                      • Discovered Tools: {mcpStatus.tool_discovery.discovered_tools}
                    </Typography>
                    <Typography variant="body2" sx={{ ml: 2 }}>
                      • Discovery Sources: {mcpStatus.tool_discovery.discovery_sources}
                    </Typography>
                    <Typography variant="body2" sx={{ ml: 2 }}>
                      • Running: {mcpStatus.tool_discovery.is_running ? 'Yes' : 'No'}
                    </Typography>
                    
                    <Divider sx={{ my: 2 }} />
                    
                    <Typography variant="body2" gutterBottom>
                      <strong>Services:</strong>
                    </Typography>
                    {Object.entries(mcpStatus.services).map(([service, status]) => (
                      <Box key={service} sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                        <Chip 
                          label={status} 
                          color={status === 'operational' ? 'success' : 'error'}
                          size="small"
                          sx={{ mr: 1 }}
                        />
                        <Typography variant="body2">
                          {service.replace('_', ' ').toUpperCase()}
                        </Typography>
                      </Box>
                    ))}
                    
                    <Button
                      variant="outlined"
                      startIcon={refreshLoading ? <CircularProgress size={16} /> : <RefreshIcon />}
                      onClick={handleRefreshDiscovery}
                      disabled={refreshLoading || loading}
                      sx={{ mt: 2 }}
                    >
                      {refreshLoading ? 'Refreshing...' : 'Refresh Discovery'}
                    </Button>
                  </Box>
                ) : (
                  <CircularProgress />
                )}
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={6}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Discovered Tools ({tools.length})
                </Typography>
                
                {tools.length > 0 ? (
                  <Accordion>
                    <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                      <Typography>View All Tools</Typography>
                    </AccordionSummary>
                    <AccordionDetails>
                      <List dense>
                        {tools.slice(0, 10).map((tool) => (
                          <React.Fragment key={tool.tool_id}>
                            <ListItem>
                              <ListItemText
                                primary={tool.name}
                                secondary={
                                  <Box>
                                    <Typography variant="body2" color="text.secondary">
                                      {tool.description}
                                    </Typography>
                                    <Box sx={{ mt: 1 }}>
                                      <Chip label={tool.category} size="small" sx={{ mr: 1 }} />
                                      <Chip label={tool.source} size="small" />
                                    </Box>
                                  </Box>
                                }
                              />
                              <ListItemSecondaryAction>
                                <Tooltip title="View Details">
                                  <IconButton
                                    edge="end"
                                    onClick={() => setShowToolDetails(
                                      showToolDetails === tool.tool_id ? null : tool.tool_id
                                    )}
                                  >
                                    <VisibilityIcon />
                                  </IconButton>
                                </Tooltip>
                                <Tooltip title="Execute Tool">
                                  <IconButton
                                    edge="end"
                                    onClick={() => {
                                      if (tool.parameters && Object.keys(tool.parameters).length > 0) {
                                        setSelectedToolForExecution(tool);
                                        setShowParameterDialog(true);
                                      } else {
                                        handleExecuteTool(tool.tool_id, tool.name);
                                      }
                                    }}
                                    disabled={loading}
                                    sx={{ ml: 1 }}
                                  >
                                    <PlayIcon />
                                  </IconButton>
                                </Tooltip>
                              </ListItemSecondaryAction>
                            </ListItem>
                            {renderToolDetails(tool)}
                          </React.Fragment>
                        ))}
                      </List>
                    </AccordionDetails>
                  </Accordion>
                ) : (
                  <Typography variant="body2" color="text.secondary">
                    No tools discovered yet. Try refreshing discovery.
                  </Typography>
                )}
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </TabPanel>

      <TabPanel value={tabValue} index={1}>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Tool Search
            </Typography>
            
            <Box sx={{ display: 'flex', gap: 1, mb: 2 }}>
              <TextField
                fullWidth
                label="Search tools..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && handleSearchTools()}
              />
              <Button
                variant="contained"
                startIcon={<SearchIcon />}
                onClick={handleSearchTools}
                disabled={loading || !searchQuery.trim()}
              >
                Search
              </Button>
            </Box>
            
            {searchResults.length > 0 && (
              <Box>
                <Typography variant="body2" gutterBottom>
                  Found {searchResults.length} tools:
                </Typography>
                <List dense>
                  {searchResults.map((tool) => (
                    <ListItem key={tool.tool_id}>
                      <ListItemText
                        primary={tool.name}
                        secondary={`${tool.description} (${tool.category})`}
                      />
                      <ListItemSecondaryAction>
                        <IconButton
                          edge="end"
                          onClick={() => handleExecuteTool(tool.tool_id, tool.name)}
                          disabled={loading}
                        >
                          <PlayIcon />
                        </IconButton>
                      </ListItemSecondaryAction>
                    </ListItem>
                  ))}
                </List>
              </Box>
            )}
          </CardContent>
        </Card>
      </TabPanel>

      <TabPanel value={tabValue} index={2}>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              MCP Workflow Testing
            </Typography>
            
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              Test the complete MCP workflow with sample messages:
            </Typography>
            
            <Box sx={{ display: 'flex', gap: 1, mb: 2, flexWrap: 'wrap' }}>
              <Button
                variant="outlined"
                size="small"
                onClick={() => setTestMessage("Show me the status of forklift FL-001")}
              >
                Equipment Status
              </Button>
              <Button
                variant="outlined"
                size="small"
                onClick={() => setTestMessage("Create a new picking task for order ORD-123")}
              >
                Create Task
              </Button>
              <Button
                variant="outlined"
                size="small"
                onClick={() => setTestMessage("Report a safety incident in zone A")}
              >
                Safety Report
              </Button>
              <Button
                variant="outlined"
                size="small"
                onClick={() => setTestMessage("What equipment is available?")}
              >
                Available Equipment
              </Button>
              <Button
                variant="outlined"
                size="small"
                onClick={() => setTestMessage("Generate a demand forecast for SKU-12345")}
              >
                Forecasting
              </Button>
              <Button
                variant="outlined"
                size="small"
                onClick={() => setTestMessage("Show me reorder recommendations")}
              >
                Reorder Recommendations
              </Button>
              <Button
                variant="outlined"
                size="small"
                onClick={() => setTestMessage("Upload and process a document")}
              >
                Document Processing
              </Button>
            </Box>
            
            <Box sx={{ display: 'flex', gap: 1, mb: 2 }}>
              <TextField
                fullWidth
                label="Test message..."
                value={testMessage}
                onChange={(e) => setTestMessage(e.target.value)}
                placeholder="e.g., Show me the status of forklift FL-001"
              />
              <Button
                variant="contained"
                startIcon={loading ? <CircularProgress size={16} /> : <PlayIcon />}
                onClick={handleTestWorkflow}
                disabled={loading || !testMessage.trim()}
              >
                {loading ? 'Testing...' : 'Test Workflow'}
              </Button>
            </Box>
            
            {testResult && (
              <Paper sx={{ p: 2, bgcolor: 'grey.50' }}>
                <Typography variant="subtitle2" gutterBottom>
                  Workflow Test Result:
                </Typography>
                <Typography variant="body2" component="pre" sx={{ whiteSpace: 'pre-wrap' }}>
                  {JSON.stringify(testResult, null, 2)}
                </Typography>
              </Paper>
            )}
          </CardContent>
        </Card>
      </TabPanel>

      <TabPanel value={tabValue} index={3}>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Execution History
            </Typography>
            
            {executionHistory.length > 0 ? (
              <TableContainer>
                <Table>
                  <TableHead>
                    <TableRow>
                      <TableCell>Timestamp</TableCell>
                      <TableCell>Tool</TableCell>
                      <TableCell>Status</TableCell>
                      <TableCell>Execution Time</TableCell>
                      <TableCell>Actions</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {executionHistory.map((entry) => (
                      <TableRow key={entry.id}>
                        <TableCell>
                          {entry.timestamp.toLocaleString()}
                        </TableCell>
                        <TableCell>
                          <Typography variant="body2" fontWeight="medium">
                            {entry.tool_name}
                          </Typography>
                          <Typography variant="caption" color="text.secondary">
                            {entry.tool_id}
                          </Typography>
                        </TableCell>
                        <TableCell>
                          <Chip
                            icon={entry.success ? <CheckCircleIcon /> : <ErrorIcon />}
                            label={entry.success ? 'Success' : 'Failed'}
                            color={entry.success ? 'success' : 'error'}
                            size="small"
                          />
                        </TableCell>
                        <TableCell>
                          {entry.execution_time}ms
                        </TableCell>
                        <TableCell>
                          <Tooltip title="View Details">
                            <IconButton 
                              size="small"
                              onClick={() => setSelectedHistoryEntry(entry)}
                            >
                              <InfoIcon />
                            </IconButton>
                          </Tooltip>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            ) : (
              <Typography variant="body2" color="text.secondary">
                No execution history yet. Execute some tools to see history.
              </Typography>
            )}
          </CardContent>
        </Card>
      </TabPanel>

      {/* Parameter Input Dialog */}
      {showParameterDialog && selectedToolForExecution && (
        <Box
          sx={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            bgcolor: 'rgba(0,0,0,0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1300,
          }}
          onClick={() => setShowParameterDialog(false)}
        >
          <Paper
            sx={{ p: 3, maxWidth: 600, maxHeight: '80vh', overflow: 'auto' }}
            onClick={(e) => e.stopPropagation()}
          >
            <Typography variant="h6" gutterBottom>
              Execute Tool: {selectedToolForExecution.name}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              {selectedToolForExecution.description}
            </Typography>
            <Typography variant="subtitle2" gutterBottom>
              Parameters:
            </Typography>
            <TextField
              fullWidth
              multiline
              rows={8}
              value={JSON.stringify(toolParameters[selectedToolForExecution.tool_id] || {}, null, 2)}
              onChange={(e) => {
                try {
                  const params = JSON.parse(e.target.value);
                  setToolParameters({
                    ...toolParameters,
                    [selectedToolForExecution.tool_id]: params,
                  });
                } catch (err) {
                  // Invalid JSON, keep as is
                }
              }}
              placeholder='{"param1": "value1", "param2": "value2"}'
              sx={{ mb: 2, fontFamily: 'monospace' }}
            />
            <Box sx={{ display: 'flex', gap: 1, justifyContent: 'flex-end' }}>
              <Button onClick={() => setShowParameterDialog(false)}>Cancel</Button>
              <Button
                variant="contained"
                onClick={() => {
                  handleExecuteTool(
                    selectedToolForExecution.tool_id,
                    selectedToolForExecution.name,
                    toolParameters[selectedToolForExecution.tool_id]
                  );
                  setShowParameterDialog(false);
                }}
              >
                Execute
              </Button>
            </Box>
          </Paper>
        </Box>
      )}

      {/* Execution History Details Dialog */}
      {selectedHistoryEntry && (
        <Box
          sx={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            bgcolor: 'rgba(0,0,0,0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1300,
          }}
          onClick={() => setSelectedHistoryEntry(null)}
        >
          <Paper
            sx={{ p: 3, maxWidth: 800, maxHeight: '80vh', overflow: 'auto' }}
            onClick={(e) => e.stopPropagation()}
          >
            <Typography variant="h6" gutterBottom>
              Execution Details: {selectedHistoryEntry.tool_name}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              {selectedHistoryEntry.timestamp.toLocaleString()}
            </Typography>
            <Divider sx={{ my: 2 }} />
            <Typography variant="subtitle2" gutterBottom>
              Status: {selectedHistoryEntry.success ? 'Success' : 'Failed'}
            </Typography>
            <Typography variant="body2" sx={{ mb: 2 }}>
              Execution Time: {selectedHistoryEntry.execution_time}ms
            </Typography>
            {selectedHistoryEntry.error && (
              <Alert severity="error" sx={{ mb: 2 }}>
                {selectedHistoryEntry.error}
              </Alert>
            )}
            {selectedHistoryEntry.result && (
              <Box>
                <Typography variant="subtitle2" gutterBottom>
                  Result:
                </Typography>
                <Paper sx={{ p: 2, bgcolor: 'grey.50', maxHeight: 400, overflow: 'auto' }}>
                  <pre style={{ fontSize: '0.75rem', margin: 0 }}>
                    {JSON.stringify(selectedHistoryEntry.result, null, 2)}
                  </pre>
                </Paper>
              </Box>
            )}
            <Box sx={{ display: 'flex', justifyContent: 'flex-end', mt: 2 }}>
              <Button onClick={() => setSelectedHistoryEntry(null)}>Close</Button>
            </Box>
          </Paper>
        </Box>
      )}
    </Box>
  );
};

export default EnhancedMCPTestingPanel;
