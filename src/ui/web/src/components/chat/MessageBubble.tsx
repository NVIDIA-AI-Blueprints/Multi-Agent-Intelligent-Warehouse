import React from 'react';
import {
  Box,
  Typography,
  Avatar,
  Chip,
  Card,
  CardContent,
  Button,
  LinearProgress,
  Tooltip,
} from '@mui/material';
import {
  CheckCircle as CheckCircleIcon,
  Cancel as CancelIcon,
  Info as InfoIcon,
  Warning as WarningIcon,
  Error as ErrorIcon,
  ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon,
} from '@mui/icons-material';
import ReasoningChainVisualization from './ReasoningChainVisualization';
import { ReasoningChain, ReasoningStep } from '../../services/api';

interface MessageBubbleProps {
  message: {
    id: string;
    type: 'answer' | 'clarifying_question' | 'proposed_action' | 'action_result' | 'evidence' | 'notice' | 'warning' | 'error';
    content: string;
    sender: 'user' | 'assistant';
    timestamp: Date;
    route?: string;
    confidence?: number;
    structured_data?: any;
    proposals?: Array<{
      action: string;
      params: any;
      guardrails: { pass: boolean; notes: string[] };
      audit_id: string;
    }>;
    clarifying?: {
      text: string;
      options: string[];
    };
    evidence?: Array<{
      type: 'sql' | 'doc';
      table?: string;
      rows?: number;
      lat_ms?: number;
      id?: string;
      score?: number;
    }>;
    reasoning_chain?: ReasoningChain;
    reasoning_steps?: ReasoningStep[];
  };
  onActionApprove: (auditId: string, action: string) => void;
  onActionReject: (auditId: string, action: string) => void;
  onQuickReply: (option: string) => void;
}

const MessageBubble: React.FC<MessageBubbleProps> = ({
  message,
  onActionApprove,
  onActionReject,
  onQuickReply,
}) => {
  const [expanded, setExpanded] = React.useState(false);

  const getAgentIcon = (route?: string) => {
    switch (route) {
      case 'equipment': return '🔧';
      case 'operations': return '📋';
      case 'safety': return '🛡️';
      default: return '🤖';
    }
  };

  const getAgentColor = (route?: string) => {
    switch (route) {
      case 'equipment': return '#76B900';
      case 'operations': return '#2196F3';
      case 'safety': return '#FF9800';
      default: return '#9C27B0';
    }
  };

  const getConfidenceColor = (confidence?: number) => {
    if (!confidence) return '#666666';
    if (confidence >= 0.8) return '#76B900';
    if (confidence >= 0.6) return '#FF9800';
    return '#f44336';
  };

  const getConfidenceIcon = (confidence?: number) => {
    if (!confidence) return null;
    if (confidence >= 0.8) return '🟢';
    if (confidence >= 0.6) return '🟡';
    return '🔴';
  };

  const renderStructuredData = () => {
    if (!message.structured_data) return null;

    // Handle the actual API response structure
    if (message.structured_data.response_type === 'equipment_info') {
      return (
        <Card sx={{ mt: 1, backgroundColor: '#fafafa', border: '1px solid #e0e0e0', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
          <CardContent>
            <Typography variant="h6" sx={{ color: '#333333', mb: 1, fontWeight: 500 }}>
              Equipment Information
            </Typography>
            <Typography variant="body2" sx={{ color: '#666666', mb: 2 }}>
              {typeof message.structured_data.natural_language === 'string' 
                ? message.structured_data.natural_language 
                : 'No description available'}
            </Typography>
            
            {message.structured_data.data && (
              <Box sx={{ mb: 2 }}>
                <Typography variant="body2" sx={{ color: '#333333', mb: 1, fontWeight: 500 }}>
                  Data Summary:
                </Typography>
                <Box sx={{ backgroundColor: '#ffffff', p: 1, borderRadius: 1, fontFamily: 'monospace', fontSize: '10px', border: '1px solid #e0e0e0' }}>
                  <pre style={{ color: '#333333', margin: 0, whiteSpace: 'pre-wrap' }}>
                    {JSON.stringify(message.structured_data.data, null, 2)}
                  </pre>
                </Box>
              </Box>
            )}

            {message.structured_data.recommendations && message.structured_data.recommendations.length > 0 && (
              <Box sx={{ mb: 2 }}>
                <Typography variant="body2" sx={{ color: '#333333', mb: 1, fontWeight: 500 }}>
                  Recommendations:
                </Typography>
                {message.structured_data.recommendations.map((rec: string, index: number) => (
                  <Typography key={index} variant="caption" sx={{ color: '#76B900', display: 'block' }}>
                    • {rec}
                  </Typography>
                ))}
              </Box>
            )}

            {message.structured_data.confidence && (
              <Box sx={{ mb: 2 }}>
                <Typography variant="body2" sx={{ color: '#333333', mb: 1, fontWeight: 500 }}>
                  Confidence: {(message.structured_data.confidence * 100).toFixed(1)}%
                </Typography>
                <LinearProgress
                  variant="determinate"
                  value={message.structured_data.confidence * 100}
                  sx={{
                    height: 4,
                    borderRadius: 2,
                    backgroundColor: '#e0e0e0',
                    '& .MuiLinearProgress-bar': {
                      backgroundColor: message.structured_data.confidence >= 0.8 ? '#76B900' : '#FF9800',
                    },
                  }}
                />
              </Box>
            )}
          </CardContent>
        </Card>
      );
    }

    // Handle table structure (legacy)
    if (message.structured_data.type === 'table') {
      return (
        <Card sx={{ mt: 1, backgroundColor: '#fafafa', border: '1px solid #e0e0e0', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
          <CardContent>
            <Typography variant="h6" sx={{ color: '#333333', mb: 1, fontWeight: 500 }}>
              {message.structured_data.title}
            </Typography>
            <Box sx={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', color: '#333333' }}>
                <thead>
                  <tr>
                    {message.structured_data.headers.map((header: string, index: number) => (
                      <th key={index} style={{ padding: '8px', textAlign: 'left', borderBottom: '1px solid #e0e0e0', fontWeight: 500 }}>
                        {header}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {message.structured_data.rows.map((row: any[], rowIndex: number) => (
                    <tr key={rowIndex}>
                      {row.map((cell: any, cellIndex: number) => (
                        <td key={cellIndex} style={{ padding: '8px', borderBottom: '1px solid #e0e0e0' }}>
                          {cell}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </Box>
          </CardContent>
        </Card>
      );
    }

    // Fallback: render as JSON if it's an object
    if (typeof message.structured_data === 'object') {
      return (
        <Card sx={{ mt: 1, backgroundColor: '#fafafa', border: '1px solid #e0e0e0', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
          <CardContent>
            <Typography variant="h6" sx={{ color: '#333333', mb: 1, fontWeight: 500 }}>
              Structured Data
            </Typography>
            <Box sx={{ backgroundColor: '#ffffff', p: 1, borderRadius: 1, fontFamily: 'monospace', fontSize: '10px', border: '1px solid #e0e0e0' }}>
              <pre style={{ color: '#333333', margin: 0, whiteSpace: 'pre-wrap' }}>
                {JSON.stringify(message.structured_data, null, 2)}
              </pre>
            </Box>
          </CardContent>
        </Card>
      );
    }

    return null;
  };

  const renderProposedActions = () => {
    if (!message.proposals || message.proposals.length === 0) return null;

    return (
      <Box sx={{ mt: 1 }}>
        {message.proposals.map((proposal, index) => (
          <Card key={index} sx={{ mt: 1, backgroundColor: '#fafafa', border: '1px solid #e0e0e0', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
            <CardContent>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                <Typography variant="h6" sx={{ color: '#333333', fontWeight: 500 }}>
                  {proposal.action.replace(/_/g, ' ').toUpperCase()}
                </Typography>
                <Chip
                  label={proposal.guardrails.pass ? 'PASS' : 'FAIL'}
                  size="small"
                  sx={{
                    backgroundColor: proposal.guardrails.pass ? '#76B900' : '#f44336',
                    color: '#ffffff',
                  }}
                />
              </Box>
              
              <Typography variant="body2" sx={{ color: '#666666', mb: 2 }}>
                Parameters: {JSON.stringify(proposal.params, null, 2)}
              </Typography>

              {proposal.guardrails.notes.length > 0 && (
                <Box sx={{ mb: 2 }}>
                  <Typography variant="body2" sx={{ color: '#333333', mb: 1, fontWeight: 500 }}>
                    Guardrails:
                  </Typography>
                  {proposal.guardrails.notes.map((note, noteIndex) => (
                    <Chip
                      key={noteIndex}
                      label={note}
                      size="small"
                      sx={{ mr: 1, mb: 1, backgroundColor: '#e0e0e0', color: '#333333' }}
                    />
                  ))}
                </Box>
              )}

              <Box sx={{ display: 'flex', gap: 1 }}>
                <Button
                  variant="contained"
                  size="small"
                  startIcon={<CheckCircleIcon />}
                  onClick={() => onActionApprove(proposal.audit_id, proposal.action)}
                  sx={{
                    backgroundColor: '#76B900',
                    '&:hover': { backgroundColor: '#5a8f00' },
                  }}
                >
                  Approve
                </Button>
                <Button
                  variant="outlined"
                  size="small"
                  startIcon={<CancelIcon />}
                  onClick={() => onActionReject(proposal.audit_id, proposal.action)}
                  sx={{
                    borderColor: '#f44336',
                    color: '#f44336',
                    '&:hover': { borderColor: '#d32f2f', backgroundColor: 'rgba(244, 67, 54, 0.1)' },
                  }}
                >
                  Reject
                </Button>
              </Box>
            </CardContent>
          </Card>
        ))}
      </Box>
    );
  };

  const renderClarifyingQuestion = () => {
    if (!message.clarifying) return null;

    return (
      <Card sx={{ mt: 1, backgroundColor: '#fafafa', border: '1px solid #e0e0e0', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
        <CardContent>
          <Typography variant="h6" sx={{ color: '#333333', mb: 1, fontWeight: 500 }}>
            {message.clarifying.text}
          </Typography>
          <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
            {message.clarifying.options.map((option, index) => (
              <Chip
                key={index}
                label={option}
                clickable
                onClick={() => onQuickReply(option)}
                sx={{
                  backgroundColor: '#e0e0e0',
                  color: '#333333',
                  '&:hover': { backgroundColor: '#76B900', color: '#ffffff' },
                }}
              />
            ))}
          </Box>
        </CardContent>
      </Card>
    );
  };

  const renderNotice = () => {
    if (message.type !== 'notice' && message.type !== 'warning' && message.type !== 'error') return null;

    const getNoticeIcon = () => {
      switch (message.type) {
        case 'warning': return <WarningIcon sx={{ color: '#FF9800' }} />;
        case 'error': return <ErrorIcon sx={{ color: '#f44336' }} />;
        default: return <InfoIcon sx={{ color: '#2196F3' }} />;
      }
    };

    const getNoticeColor = () => {
      switch (message.type) {
        case 'warning': return '#FF9800';
        case 'error': return '#f44336';
        default: return '#2196F3';
      }
    };

    return (
      <Card sx={{ mt: 1, backgroundColor: '#fafafa', border: `1px solid ${getNoticeColor()}`, boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
        <CardContent>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            {getNoticeIcon()}
            <Typography variant="body1" sx={{ color: '#333333' }}>
              {message.content}
            </Typography>
          </Box>
        </CardContent>
      </Card>
    );
  };

  const isUser = message.sender === 'user';

  return (
    <Box
      sx={{
        display: 'flex',
        justifyContent: isUser ? 'flex-end' : 'flex-start',
        mb: 2,
        px: 2,
      }}
    >
      <Box
        sx={{
          maxWidth: '70%',
          display: 'flex',
          flexDirection: isUser ? 'row-reverse' : 'row',
          alignItems: 'flex-start',
          gap: 1,
        }}
      >
        {/* Avatar */}
        {!isUser && (
          <Avatar
            sx={{
              width: 32,
              height: 32,
              backgroundColor: getAgentColor(message.route),
              border: `2px solid ${getAgentColor(message.route)}`,
            }}
          >
            {getAgentIcon(message.route)}
          </Avatar>
        )}

        {/* Message Content */}
        <Box
          sx={{
            backgroundColor: isUser ? '#76B900' : '#ffffff',
            color: isUser ? '#ffffff' : '#333333',
            borderRadius: 2,
            p: 2,
            border: isUser ? 'none' : '1px solid #e0e0e0',
            minWidth: 200,
            boxShadow: isUser ? 'none' : '0 1px 3px rgba(0,0,0,0.1)',
          }}
        >
          {/* Message Header */}
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
            <Typography variant="body2" sx={{ color: isUser ? '#ffffff' : '#666666', fontWeight: 500 }}>
              {isUser ? 'You' : `${message.route || 'Assistant'}`}
            </Typography>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              {message.confidence && (
                <Tooltip title={`Confidence: ${(message.confidence * 100).toFixed(1)}%`}>
                  <Chip
                    label={`${getConfidenceIcon(message.confidence)} ${(message.confidence * 100).toFixed(0)}%`}
                    size="small"
                    sx={{
                      backgroundColor: getConfidenceColor(message.confidence),
                      color: '#ffffff',
                      fontSize: '10px',
                    }}
                  />
                </Tooltip>
              )}
              <Typography variant="caption" sx={{ color: isUser ? 'rgba(255,255,255,0.8)' : '#999999' }}>
                {message.timestamp.toLocaleTimeString()}
              </Typography>
            </Box>
          </Box>

          {/* Message Content */}
          <Typography variant="body1" sx={{ color: isUser ? '#ffffff' : '#333333', mb: 1 }}>
            {message.content}
          </Typography>

          {/* Confidence Bar */}
          {message.confidence && (
            <Box sx={{ mb: 1 }}>
              <LinearProgress
                variant="determinate"
                value={message.confidence * 100}
                sx={{
                  height: 4,
                  borderRadius: 2,
                  backgroundColor: isUser ? 'rgba(255,255,255,0.3)' : '#e0e0e0',
                  '& .MuiLinearProgress-bar': {
                    backgroundColor: getConfidenceColor(message.confidence),
                  },
                }}
              />
            </Box>
          )}

          {/* Reasoning Chain - shown BEFORE structured data */}
          {(message.reasoning_chain || message.reasoning_steps) && (
            <Box sx={{ mt: 1, mb: 1 }}>
              <ReasoningChainVisualization
                reasoningChain={message.reasoning_chain}
                reasoningSteps={message.reasoning_steps}
                compact={true}
              />
            </Box>
          )}

          {/* Structured Data - shown AFTER reasoning chain */}
          {renderStructuredData()}

          {/* Proposed Actions */}
          {renderProposedActions()}

          {/* Clarifying Question */}
          {renderClarifyingQuestion()}

          {/* Notice/Warning/Error */}
          {renderNotice()}

          {/* Evidence Toggle */}
          {message.evidence && message.evidence.length > 0 && (
            <Box sx={{ mt: 1 }}>
              <Button
                size="small"
                onClick={() => setExpanded(!expanded)}
                endIcon={expanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                sx={{ color: '#76B900' }}
              >
                Evidence ({message.evidence.length})
              </Button>
              {expanded && (
                <Box sx={{ mt: 1 }}>
                  {message.evidence.map((evidence, index) => (
                    <Chip
                      key={index}
                      label={`${evidence.type.toUpperCase()}: ${evidence.table || evidence.id} (${evidence.score?.toFixed(2) || evidence.rows} rows)`}
                      size="small"
                      sx={{
                        mr: 1,
                        mb: 1,
                        backgroundColor: evidence.type === 'sql' ? '#2196F3' : '#9C27B0',
                        color: '#ffffff',
                      }}
                    />
                  ))}
                </Box>
              )}
            </Box>
          )}
        </Box>
      </Box>
    </Box>
  );
};

export default MessageBubble;
