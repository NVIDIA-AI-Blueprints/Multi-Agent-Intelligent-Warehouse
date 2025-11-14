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
} from '@mui/material';
import {
  ExpandMore as ExpandMoreIcon,
  PlayArrow as PlayIcon,
  Refresh as RefreshIcon,
  Search as SearchIcon,
  CheckCircle as CheckCircleIcon,
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

const MCPTestingPanel: React.FC = () => {
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

  // Load MCP status and tools on component mount
  useEffect(() => {
    loadMcpData();
  }, []);

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
      
      const result = await mcpAPI.testWorkflow(testMessage);
      setTestResult(result);
      
      if (result.status === 'success') {
        setSuccess(`Workflow test completed successfully`);
      } else {
        setError(`Workflow test failed: ${result.error || 'Unknown error'}`);
      }
      
    } catch (err: any) {
      setError(`Workflow test failed: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleExecuteTool = async (toolId: string) => {
    try {
      setLoading(true);
      setError(null);
      
      const result = await mcpAPI.executeTool(toolId, { test: true });
      console.log(`Tool ${toolId} executed:`, result);
      
      // Show success message
      setError(`Tool ${toolId} executed successfully!`);
      
    } catch (err: any) {
      setError(`Tool execution failed: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box sx={{ p: 2 }}>
      <Typography variant="h5" gutterBottom>
        MCP Testing Panel
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

      <Grid container spacing={2}>
        {/* MCP Status */}
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

        {/* Tool Search */}
        <Grid item xs={12} md={6}>
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
                            onClick={() => handleExecuteTool(tool.tool_id)}
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
        </Grid>

        {/* Discovered Tools */}
        <Grid item xs={12}>
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
                      {tools.map((tool) => (
                        <ListItem key={tool.tool_id}>
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
                            <IconButton
                              edge="end"
                              onClick={() => handleExecuteTool(tool.tool_id)}
                              disabled={loading}
                            >
                              <PlayIcon />
                            </IconButton>
                          </ListItemSecondaryAction>
                        </ListItem>
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

        {/* Workflow Testing */}
        <Grid item xs={12}>
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
        </Grid>
      </Grid>
    </Box>
  );
};

export default MCPTestingPanel;
