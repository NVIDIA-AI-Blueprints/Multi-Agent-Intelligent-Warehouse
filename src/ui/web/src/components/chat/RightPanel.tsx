import React, { useState } from 'react';
import {
  Box,
  Typography,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  List,
  ListItem,
  Chip,
  Card,
  CardContent,
  LinearProgress,
  IconButton,
  Button,
} from '@mui/material';
import {
  ExpandMore as ExpandMoreIcon,
  Code as CodeIcon,
  TableChart as TableChartIcon,
  Timeline as TimelineIcon,
  Security as SecurityIcon,
  Close as CloseIcon,
  Settings as SettingsIcon,
  Psychology as PsychologyIcon,
} from '@mui/icons-material';
import { ReasoningChain, ReasoningStep } from '../../services/api';
import ReasoningChainVisualization from './ReasoningChainVisualization';

interface RightPanelProps {
  isOpen: boolean;
  onClose: () => void;
  evidence: Array<{
    type: 'sql' | 'doc' | 'structured' | 'procedure';
    table?: string;
    rows?: number;
    lat_ms?: number;
    id?: string;
    score?: number;
    content?: string;
    data?: any;
  }>;
  sqlQuery?: {
    query: string;
    parameters: any[];
    result_sample: any[];
    execution_time: number;
  };
  plannerDecision?: {
    intent: string;
    confidence: number;
    reasoning: string;
  };
  activeContext?: {
    order?: string;
    work_order?: string;
    sku?: string;
    asset_id?: string;
    zone?: string;
  };
  toolTimeline?: Array<{
    id: string;
    action: string;
    status: 'proposed' | 'approved' | 'executed' | 'rejected';
    timestamp: Date;
    audit_id: string;
    result?: any;
  }>;
  reasoningChain?: ReasoningChain;
  reasoningSteps?: ReasoningStep[];
}

const RightPanel: React.FC<RightPanelProps> = ({
  isOpen,
  onClose,
  evidence,
  sqlQuery,
  plannerDecision,
  activeContext,
  toolTimeline,
  reasoningChain,
  reasoningSteps,
}) => {
  const [expandedSections, setExpandedSections] = useState<string[]>(['reasoning', 'evidence']);

  const handleSectionToggle = (section: string) => {
    setExpandedSections(prev =>
      prev.includes(section)
        ? prev.filter(s => s !== section)
        : [...prev, section]
    );
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'executed': return '#76B900';
      case 'approved': return '#2196F3';
      case 'proposed': return '#FF9800';
      case 'rejected': return '#f44336';
      default: return '#666666';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'executed': return '✅';
      case 'approved': return '👍';
      case 'proposed': return '⏳';
      case 'rejected': return '❌';
      default: return '❓';
    }
  };

  if (!isOpen) return null;

  return (
    <Box
      sx={{
        width: 350,
        height: '100%',
        backgroundColor: '#111111',
        borderLeft: '1px solid #333333',
        display: 'flex',
        flexDirection: 'column',
        position: 'relative',
      }}
    >
      {/* Header */}
      <Box
        sx={{
          p: 2,
          borderBottom: '1px solid #333333',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <Typography variant="h6" sx={{ color: '#ffffff', fontSize: '16px' }}>
          Evidence & Context
        </Typography>
        <IconButton onClick={onClose} size="small" sx={{ color: '#666666' }}>
          <CloseIcon />
        </IconButton>
      </Box>

      {/* Content */}
      <Box sx={{ flex: 1, overflow: 'auto', p: 2 }}>
        {/* Reasoning Chain - Show first if available */}
        {(reasoningChain || reasoningSteps) && (
          <Accordion
            expanded={expandedSections.includes('reasoning')}
            onChange={() => handleSectionToggle('reasoning')}
            sx={{
              backgroundColor: '#1a1a1a',
              border: '1px solid #333333',
              mb: 2,
              '&:before': { display: 'none' },
            }}
          >
            <AccordionSummary
              expandIcon={<ExpandMoreIcon sx={{ color: '#76B900' }} />}
              sx={{
                backgroundColor: '#0a0a0a',
                '&:hover': { backgroundColor: '#151515' },
              }}
            >
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <PsychologyIcon sx={{ color: '#76B900', fontSize: 20 }} />
                <Typography variant="body2" sx={{ color: '#ffffff', fontWeight: 'bold' }}>
                  Reasoning Chain
                </Typography>
                {reasoningChain && (
                  <Chip
                    label={`${reasoningChain.steps?.length || 0} steps`}
                    size="small"
                    sx={{
                      backgroundColor: '#76B900',
                      color: '#000000',
                      fontSize: '10px',
                      height: '18px',
                    }}
                  />
                )}
              </Box>
            </AccordionSummary>
            <AccordionDetails sx={{ p: 2 }}>
              <ReasoningChainVisualization
                reasoningChain={reasoningChain}
                reasoningSteps={reasoningSteps}
                compact={false}
              />
            </AccordionDetails>
          </Accordion>
        )}

        {/* Evidence List */}
        <Accordion
          expanded={expandedSections.includes('evidence')}
          onChange={() => handleSectionToggle('evidence')}
          sx={{
            backgroundColor: '#1a1a1a',
            border: '1px solid #333333',
            mb: 2,
            '&:before': { display: 'none' },
          }}
        >
          <AccordionSummary expandIcon={<ExpandMoreIcon sx={{ color: '#76B900' }} />}>
            <Typography sx={{ color: '#ffffff', display: 'flex', alignItems: 'center', gap: 1 }}>
              <TableChartIcon sx={{ color: '#76B900' }} />
              Evidence ({evidence.length})
            </Typography>
          </AccordionSummary>
          <AccordionDetails>
            <List dense>
              {evidence.map((item, index) => {
                // Safely extract all properties with fallbacks
                const itemType = typeof item?.type === 'string' ? item.type : 'unknown';
                const itemScore = typeof item?.score === 'number' ? item.score : 0;
                const itemContent = typeof item?.content === 'string' ? item.content : 'No content';
                const itemTable = typeof item?.table === 'string' ? item.table : '';
                const itemId = typeof item?.id === 'string' ? item.id : '';
                const itemRows = typeof item?.rows === 'number' ? item.rows : null;
                const itemLatMs = typeof item?.lat_ms === 'number' ? item.lat_ms : null;
                
                // Safely extract data properties
                const itemData = item?.data || {};
                const recommendations = Array.isArray(itemData?.recommendations) ? itemData.recommendations : [];
                const actionsTaken = Array.isArray(itemData?.actions_taken) ? itemData.actions_taken : [];
                
                return (
                  <ListItem key={index} sx={{ px: 0 }}>
                    <Card sx={{ width: '100%', backgroundColor: '#0a0a0a', border: '1px solid #333333' }}>
                      <CardContent sx={{ p: 1.5 }}>
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                          <Chip
                            label={itemType.toUpperCase()}
                            size="small"
                            sx={{
                              backgroundColor: itemType === 'sql' ? '#2196F3' : 
                                             itemType === 'doc' ? '#9C27B0' : 
                                             itemType === 'procedure' ? '#4CAF50' : '#FF9800',
                              color: '#ffffff',
                              fontSize: '10px',
                            }}
                          />
                          {itemScore > 0 && (
                            <Typography variant="caption" sx={{ color: '#76B900' }}>
                              {(itemScore * 100).toFixed(1)}%
                            </Typography>
                          )}
                        </Box>
                        
                        <Typography variant="body2" sx={{ color: '#ffffff', mb: 1 }}>
                          {itemTable || itemId || 'Structured Data'}
                        </Typography>
                        
                        <Typography variant="caption" sx={{ color: '#cccccc', display: 'block', mb: 1 }}>
                          {itemContent}
                        </Typography>
                        
                        {/* Special rendering for procedure items */}
                        {itemType === 'procedure' && itemData && (
                          <Box sx={{ mb: 1 }}>
                            <Typography variant="caption" sx={{ color: '#4CAF50', display: 'block', mb: 0.5, fontWeight: 'bold' }}>
                              {itemData.name || 'Safety Procedure'}
                            </Typography>
                            <Typography variant="caption" sx={{ color: '#ffffff', display: 'block', mb: 0.5 }}>
                              Category: {itemData.category || 'N/A'} | Priority: {itemData.priority || 'N/A'}
                            </Typography>
                            {itemData.steps && Array.isArray(itemData.steps) && (
                              <Box sx={{ mb: 1 }}>
                                <Typography variant="caption" sx={{ color: '#76B900', display: 'block', mb: 0.5 }}>
                                  Key Steps:
                                </Typography>
                                {itemData.steps.slice(0, 3).map((step: any, stepIndex: number) => (
                                  <Typography key={stepIndex} variant="caption" sx={{ color: '#ffffff', display: 'block', fontSize: '10px' }}>
                                    • {typeof step === 'string' ? step : JSON.stringify(step)}
                                  </Typography>
                                ))}
                                {itemData.steps.length > 3 && (
                                  <Typography variant="caption" sx={{ color: '#cccccc', display: 'block', fontSize: '10px', fontStyle: 'italic' }}>
                                    ... and {itemData.steps.length - 3} more steps
                                  </Typography>
                                )}
                              </Box>
                            )}
                          </Box>
                        )}
                        
                        {/* Recommendations */}
                        {recommendations.length > 0 && (
                          <Box sx={{ mb: 1 }}>
                            <Typography variant="caption" sx={{ color: '#76B900', display: 'block', mb: 0.5 }}>
                              Recommendations:
                            </Typography>
                            {recommendations.map((rec: any, recIndex: number) => (
                              <Typography key={recIndex} variant="caption" sx={{ color: '#ffffff', display: 'block', fontSize: '10px' }}>
                                • {typeof rec === 'string' ? rec : JSON.stringify(rec)}
                              </Typography>
                            ))}
                          </Box>
                        )}
                        
                        {/* Actions Taken */}
                        {actionsTaken.length > 0 && (
                          <Box sx={{ mb: 1 }}>
                            <Typography variant="caption" sx={{ color: '#FF9800', display: 'block', mb: 0.5 }}>
                              Actions Taken:
                            </Typography>
                            {actionsTaken.map((action: any, actionIndex: number) => (
                              <Typography key={actionIndex} variant="caption" sx={{ color: '#ffffff', display: 'block', fontSize: '10px' }}>
                                • {typeof action === 'string' ? action : JSON.stringify(action)}
                              </Typography>
                            ))}
                          </Box>
                        )}
                        
                        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                          {itemRows && (
                            <Chip
                              label={`${itemRows} rows`}
                              size="small"
                              sx={{ backgroundColor: '#333333', color: '#ffffff', fontSize: '10px' }}
                            />
                          )}
                          {itemLatMs && (
                            <Chip
                              label={`${itemLatMs}ms`}
                              size="small"
                              sx={{ backgroundColor: '#333333', color: '#ffffff', fontSize: '10px' }}
                            />
                          )}
                        </Box>

                        {itemScore > 0 && (
                          <LinearProgress
                            variant="determinate"
                            value={itemScore * 100}
                            sx={{
                              height: 3,
                              borderRadius: 1.5,
                              backgroundColor: '#333333',
                              mt: 1,
                              '& .MuiLinearProgress-bar': {
                                backgroundColor: itemScore >= 0.8 ? '#76B900' : itemScore >= 0.6 ? '#FF9800' : '#f44336',
                              },
                            }}
                          />
                        )}
                      </CardContent>
                    </Card>
                  </ListItem>
                );
              })}
            </List>
          </AccordionDetails>
        </Accordion>

        {/* SQL Inspector */}
        {sqlQuery && (
          <Accordion
            expanded={expandedSections.includes('sql')}
            onChange={() => handleSectionToggle('sql')}
            sx={{
              backgroundColor: '#1a1a1a',
              border: '1px solid #333333',
              mb: 2,
              '&:before': { display: 'none' },
            }}
          >
            <AccordionSummary expandIcon={<ExpandMoreIcon sx={{ color: '#76B900' }} />}>
              <Typography sx={{ color: '#ffffff', display: 'flex', alignItems: 'center', gap: 1 }}>
                <CodeIcon sx={{ color: '#2196F3' }} />
                SQL Inspector
              </Typography>
            </AccordionSummary>
            <AccordionDetails>
              <Card sx={{ backgroundColor: '#0a0a0a', border: '1px solid #333333' }}>
                <CardContent sx={{ p: 1.5 }}>
                  <Typography variant="body2" sx={{ color: '#ffffff', mb: 1, fontFamily: 'monospace' }}>
                    {sqlQuery.query}
                  </Typography>
                  
                  <Box sx={{ mb: 2 }}>
                    <Typography variant="caption" sx={{ color: '#666666' }}>
                      Parameters: {JSON.stringify(sqlQuery.parameters)}
                    </Typography>
                  </Box>

                  <Box sx={{ mb: 2 }}>
                    <Typography variant="caption" sx={{ color: '#666666' }}>
                      Execution Time: {sqlQuery.execution_time}ms
                    </Typography>
                  </Box>

                  {sqlQuery.result_sample.length > 0 && (
                    <Box>
                      <Typography variant="caption" sx={{ color: '#666666', mb: 1, display: 'block' }}>
                        Result Sample:
                      </Typography>
                      <Box sx={{ backgroundColor: '#000000', p: 1, borderRadius: 1, fontFamily: 'monospace', fontSize: '10px' }}>
                        {JSON.stringify(sqlQuery.result_sample, null, 2)}
                      </Box>
                    </Box>
                  )}
                </CardContent>
              </Card>
            </AccordionDetails>
          </Accordion>
        )}

        {/* Planner Decision */}
        {plannerDecision && (
          <Accordion
            expanded={expandedSections.includes('planner')}
            onChange={() => handleSectionToggle('planner')}
            sx={{
              backgroundColor: '#1a1a1a',
              border: '1px solid #333333',
              mb: 2,
              '&:before': { display: 'none' },
            }}
          >
            <AccordionSummary expandIcon={<ExpandMoreIcon sx={{ color: '#76B900' }} />}>
              <Typography sx={{ color: '#ffffff', display: 'flex', alignItems: 'center', gap: 1 }}>
                <SecurityIcon sx={{ color: '#9C27B0' }} />
                Planner Decision
              </Typography>
            </AccordionSummary>
            <AccordionDetails>
              <Card sx={{ backgroundColor: '#0a0a0a', border: '1px solid #333333' }}>
                <CardContent sx={{ p: 1.5 }}>
                  <Box sx={{ mb: 2 }}>
                    <Typography variant="body2" sx={{ color: '#ffffff', mb: 1 }}>
                      Intent: {plannerDecision.intent}
                    </Typography>
                    <LinearProgress
                      variant="determinate"
                      value={plannerDecision.confidence * 100}
                      sx={{
                        height: 4,
                        borderRadius: 2,
                        backgroundColor: '#333333',
                        '& .MuiLinearProgress-bar': {
                          backgroundColor: plannerDecision.confidence >= 0.8 ? '#76B900' : '#FF9800',
                        },
                      }}
                    />
                    <Typography variant="caption" sx={{ color: '#666666' }}>
                      Confidence: {(plannerDecision.confidence * 100).toFixed(1)}%
                    </Typography>
                  </Box>
                  
                  <Typography variant="body2" sx={{ color: '#cccccc' }}>
                    {typeof plannerDecision.reasoning === 'string' ? plannerDecision.reasoning : JSON.stringify(plannerDecision.reasoning)}
                  </Typography>
                </CardContent>
              </Card>
            </AccordionDetails>
          </Accordion>
        )}

        {/* Active Context */}
        {activeContext && (
          <Accordion
            expanded={expandedSections.includes('context')}
            onChange={() => handleSectionToggle('context')}
            sx={{
              backgroundColor: '#1a1a1a',
              border: '1px solid #333333',
              mb: 2,
              '&:before': { display: 'none' },
            }}
          >
            <AccordionSummary expandIcon={<ExpandMoreIcon sx={{ color: '#76B900' }} />}>
              <Typography sx={{ color: '#ffffff', display: 'flex', alignItems: 'center', gap: 1 }}>
                <TimelineIcon sx={{ color: '#FF9800' }} />
                Active Context
              </Typography>
            </AccordionSummary>
            <AccordionDetails>
              <Card sx={{ backgroundColor: '#0a0a0a', border: '1px solid #333333' }}>
                <CardContent sx={{ p: 1.5 }}>
                  {Object.entries(activeContext).map(([key, value]) => (
                    <Box key={key} sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                      <Typography variant="body2" sx={{ color: '#666666' }}>
                        {key.replace('_', ' ').toUpperCase()}:
                      </Typography>
                      <Typography variant="body2" sx={{ color: '#ffffff' }}>
                        {typeof value === 'string' ? value : JSON.stringify(value)}
                      </Typography>
                    </Box>
                  ))}
                </CardContent>
              </Card>
            </AccordionDetails>
          </Accordion>
        )}

        {/* Tool Timeline */}
        {toolTimeline && toolTimeline.length > 0 && (
          <Accordion
            expanded={expandedSections.includes('timeline')}
            onChange={() => handleSectionToggle('timeline')}
            sx={{
              backgroundColor: '#1a1a1a',
              border: '1px solid #333333',
              mb: 2,
              '&:before': { display: 'none' },
            }}
          >
            <AccordionSummary expandIcon={<ExpandMoreIcon sx={{ color: '#76B900' }} />}>
              <Typography sx={{ color: '#ffffff', display: 'flex', alignItems: 'center', gap: 1 }}>
                <TimelineIcon sx={{ color: '#76B900' }} />
                Tool Timeline ({toolTimeline.length})
              </Typography>
            </AccordionSummary>
            <AccordionDetails>
              <List dense>
                {toolTimeline.map((tool, index) => (
                  <ListItem key={tool.id} sx={{ px: 0 }}>
                    <Card sx={{ width: '100%', backgroundColor: '#0a0a0a', border: '1px solid #333333' }}>
                      <CardContent sx={{ p: 1.5 }}>
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                          <Typography variant="body2" sx={{ color: '#ffffff' }}>
                            {tool.action.replace(/_/g, ' ').toUpperCase()}
                          </Typography>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                            <Chip
                              label={`${getStatusIcon(tool.status)} ${tool.status}`}
                              size="small"
                              sx={{
                                backgroundColor: getStatusColor(tool.status),
                                color: '#ffffff',
                                fontSize: '10px',
                              }}
                            />
                          </Box>
                        </Box>
                        
                        <Typography variant="caption" sx={{ color: '#666666' }}>
                          {tool.timestamp.toLocaleTimeString()}
                        </Typography>
                        
                        <Typography variant="caption" sx={{ color: '#76B900', display: 'block', mt: 1 }}>
                          Audit ID: {tool.audit_id}
                        </Typography>

                        {tool.result && (
                          <Box sx={{ mt: 1, backgroundColor: '#000000', p: 1, borderRadius: 1 }}>
                            <Typography variant="caption" sx={{ color: '#666666' }}>
                              Result:
                            </Typography>
                            <Typography variant="caption" sx={{ color: '#ffffff', fontFamily: 'monospace', fontSize: '10px' }}>
                              {JSON.stringify(tool.result, null, 2)}
                            </Typography>
                          </Box>
                        )}
                      </CardContent>
                    </Card>
                  </ListItem>
                ))}
              </List>
            </AccordionDetails>
          </Accordion>
        )}

        {/* MCP Testing Section */}
        <Accordion
          expanded={expandedSections.includes('mcp')}
          onChange={() => handleSectionToggle('mcp')}
          sx={{
            backgroundColor: '#1a1a1a',
            border: '1px solid #333333',
            mb: 2,
            '&:before': { display: 'none' },
          }}
        >
          <AccordionSummary expandIcon={<ExpandMoreIcon sx={{ color: '#76B900' }} />}>
            <Typography sx={{ color: '#ffffff', display: 'flex', alignItems: 'center', gap: 1 }}>
              <SettingsIcon sx={{ color: '#76B900' }} />
              MCP Testing
            </Typography>
          </AccordionSummary>
          <AccordionDetails>
            <Typography variant="body2" sx={{ color: '#cccccc', mb: 2 }}>
              Test MCP tool discovery and execution
            </Typography>
            <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
              <Button
                variant="outlined"
                size="small"
                onClick={() => window.open('/mcp-test', '_blank')}
                sx={{ 
                  color: '#76B900', 
                  borderColor: '#76B900',
                  '&:hover': { borderColor: '#76B900', backgroundColor: 'rgba(118, 185, 0, 0.1)' }
                }}
              >
                Open MCP Panel
              </Button>
            </Box>
          </AccordionDetails>
        </Accordion>
      </Box>
    </Box>
  );
};

export default RightPanel;
