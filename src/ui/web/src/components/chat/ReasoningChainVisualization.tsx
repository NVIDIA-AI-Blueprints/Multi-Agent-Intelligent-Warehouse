import React from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Chip,
  LinearProgress,
  Tooltip,
} from '@mui/material';
import {
  Psychology as PsychologyIcon,
  Timeline as TimelineIcon,
  CheckCircle as CheckCircleIcon,
} from '@mui/icons-material';
import { ReasoningChain, ReasoningStep } from '../../services/api';

interface ReasoningChainVisualizationProps {
  reasoningChain?: ReasoningChain;
  reasoningSteps?: ReasoningStep[];
  compact?: boolean;
}

const ReasoningChainVisualization: React.FC<ReasoningChainVisualizationProps> = ({
  reasoningChain,
  reasoningSteps,
  compact = false,
}) => {
  // Use reasoningChain if available, otherwise construct from reasoningSteps
  const chain = reasoningChain || (reasoningSteps ? {
    chain_id: 'generated',
    query: '',
    reasoning_type: reasoningSteps[0]?.step_type || 'unknown',
    steps: reasoningSteps,
    final_conclusion: '',
    overall_confidence: reasoningSteps.reduce((acc, step) => acc + step.confidence, 0) / reasoningSteps.length,
  } : null);

  if (!chain) return null;

  const getReasoningTypeColor = (type: string) => {
    const normalizedType = type.toLowerCase();
    if (normalizedType.includes('causal')) return '#FF9800';
    if (normalizedType.includes('scenario')) return '#2196F3';
    if (normalizedType.includes('pattern')) return '#9C27B0';
    if (normalizedType.includes('multi')) return '#00BCD4';
    if (normalizedType.includes('chain')) return '#76B900';
    return '#666666';
  };

  const getReasoningTypeIcon = (type: string) => {
    const normalizedType = type.toLowerCase();
    if (normalizedType.includes('causal')) return '🔗';
    if (normalizedType.includes('scenario')) return '🔮';
    if (normalizedType.includes('pattern')) return '🔍';
    if (normalizedType.includes('multi')) return '🔀';
    if (normalizedType.includes('chain')) return '🧠';
    return '💭';
  };

  const getConfidenceColor = (confidence: number) => {
    if (confidence >= 0.8) return '#76B900';
    if (confidence >= 0.6) return '#FF9800';
    return '#f44336';
  };

  if (compact) {
    // Render directly without accordion - always visible, cannot collapse
    return (
      <Box sx={{ mt: 1 }}>
        <Card
          sx={{
            backgroundColor: '#fafafa',
            border: '1px solid #e0e0e0',
            boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
          }}
        >
          <CardContent>
            {/* Header */}
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
              <PsychologyIcon sx={{ color: getReasoningTypeColor(chain.reasoning_type) }} />
              <Typography variant="body2" sx={{ flex: 1, color: '#333333', fontWeight: 'bold' }}>
                Reasoning Chain ({chain.steps?.length || 0} steps)
              </Typography>
              <Chip
                label={chain.reasoning_type.replace(/_/g, ' ').toUpperCase()}
                size="small"
                sx={{
                  backgroundColor: getReasoningTypeColor(chain.reasoning_type),
                  color: '#ffffff',
                  fontSize: '10px',
                }}
              />
              {chain.overall_confidence && (
                <Chip
                  label={`${(chain.overall_confidence * 100).toFixed(0)}%`}
                  size="small"
                  sx={{
                    backgroundColor: getConfidenceColor(chain.overall_confidence),
                    color: '#ffffff',
                    fontSize: '10px',
                  }}
                />
              )}
            </Box>
            
            {/* Content - always visible */}
            <Box>
                {chain.steps?.map((step, index) => (
                  <Card
                    key={step.step_id || index}
                    sx={{
                      mt: index > 0 ? 1 : 0,
                      backgroundColor: '#ffffff',
                      border: '1px solid #e0e0e0',
                      boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
                    }}
                  >
                    <CardContent>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                        <Typography variant="caption" sx={{ color: '#76B900', fontWeight: 'bold' }}>
                          Step {index + 1}
                        </Typography>
                        <Chip
                          label={step.step_type.replace(/_/g, ' ').toUpperCase()}
                          size="small"
                          sx={{
                            backgroundColor: getReasoningTypeColor(step.step_type),
                            color: '#ffffff',
                            fontSize: '9px',
                          }}
                        />
                        <Box sx={{ flex: 1 }} />
                        <Tooltip title={`Confidence: ${(step.confidence * 100).toFixed(1)}%`}>
                          <Chip
                            label={`${(step.confidence * 100).toFixed(0)}%`}
                            size="small"
                            sx={{
                              backgroundColor: getConfidenceColor(step.confidence),
                              color: '#ffffff',
                              fontSize: '9px',
                            }}
                          />
                        </Tooltip>
                      </Box>
                      <Typography variant="body2" sx={{ color: '#333333', mb: 1, fontWeight: 'bold' }}>
                        {step.description}
                      </Typography>
                      <Typography variant="body2" sx={{ color: '#666666', fontSize: '0.875rem' }}>
                        {step.reasoning}
                      </Typography>
                      <LinearProgress
                        variant="determinate"
                        value={step.confidence * 100}
                        sx={{
                          mt: 1,
                          height: 3,
                          borderRadius: 1,
                          backgroundColor: '#e0e0e0',
                          '& .MuiLinearProgress-bar': {
                            backgroundColor: getConfidenceColor(step.confidence),
                          },
                        }}
                      />
                    </CardContent>
                  </Card>
                ))}
                {chain.final_conclusion && (
                  <Card
                    sx={{
                      mt: 2,
                      backgroundColor: '#f0f8e8',
                      border: '1px solid #76B900',
                      boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
                    }}
                  >
                    <CardContent>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                        <CheckCircleIcon sx={{ color: '#76B900' }} />
                        <Typography variant="body2" sx={{ color: '#76B900', fontWeight: 'bold' }}>
                          Final Conclusion
                        </Typography>
                      </Box>
                      <Typography variant="body2" sx={{ color: '#333333' }}>
                        {chain.final_conclusion}
                      </Typography>
                    </CardContent>
                  </Card>
                )}
              </Box>
          </CardContent>
        </Card>
      </Box>
    );
  }

  return (
    <Card
      sx={{
        mt: 1,
        backgroundColor: '#fafafa',
        border: '1px solid #e0e0e0',
        boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
      }}
    >
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
          <PsychologyIcon sx={{ color: getReasoningTypeColor(chain.reasoning_type) }} />
          <Typography variant="h6" sx={{ color: '#333333', flex: 1, fontWeight: 500 }}>
            Reasoning Chain
          </Typography>
          <Chip
            label={chain.reasoning_type.replace(/_/g, ' ').toUpperCase()}
            size="small"
            sx={{
              backgroundColor: getReasoningTypeColor(chain.reasoning_type),
              color: '#ffffff',
            }}
          />
          {chain.overall_confidence && (
            <Tooltip title={`Overall Confidence: ${(chain.overall_confidence * 100).toFixed(1)}%`}>
              <Chip
                label={`${(chain.overall_confidence * 100).toFixed(0)}%`}
                size="small"
                sx={{
                  backgroundColor: getConfidenceColor(chain.overall_confidence),
                  color: '#ffffff',
                }}
              />
            </Tooltip>
          )}
        </Box>

        {chain.query && (
          <Box sx={{ mb: 2, p: 1, backgroundColor: '#ffffff', borderRadius: 1, border: '1px solid #e0e0e0' }}>
            <Typography variant="caption" sx={{ color: '#666666' }}>
              Query:
            </Typography>
            <Typography variant="body2" sx={{ color: '#333333', mt: 0.5 }}>
              {chain.query}
            </Typography>
          </Box>
        )}

        <Box sx={{ mb: 2 }}>
          <Typography variant="body2" sx={{ color: '#666666', mb: 1, fontWeight: 500 }}>
            Reasoning Steps ({chain.steps?.length || 0}):
          </Typography>
          {chain.steps?.map((step, index) => (
            <Card
              key={step.step_id || index}
              sx={{
                mt: index > 0 ? 1 : 0,
                backgroundColor: '#ffffff',
                border: '1px solid #e0e0e0',
                boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
              }}
            >
              <CardContent>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                  <TimelineIcon sx={{ color: getReasoningTypeColor(step.step_type), fontSize: 16 }} />
                  <Typography variant="caption" sx={{ color: '#76B900', fontWeight: 'bold' }}>
                    Step {index + 1}
                  </Typography>
                  <Chip
                    label={step.step_type.replace(/_/g, ' ').toUpperCase()}
                    size="small"
                    sx={{
                      backgroundColor: getReasoningTypeColor(step.step_type),
                      color: '#ffffff',
                      fontSize: '9px',
                    }}
                  />
                  <Box sx={{ flex: 1 }} />
                  <Tooltip title={`Confidence: ${(step.confidence * 100).toFixed(1)}%`}>
                    <Chip
                      label={`${(step.confidence * 100).toFixed(0)}%`}
                      size="small"
                      sx={{
                        backgroundColor: getConfidenceColor(step.confidence),
                        color: '#ffffff',
                        fontSize: '9px',
                      }}
                    />
                  </Tooltip>
                </Box>
                <Typography variant="body2" sx={{ color: '#333333', mb: 1, fontWeight: 'bold' }}>
                  {step.description}
                </Typography>
                <Typography variant="body2" sx={{ color: '#666666', fontSize: '0.875rem' }}>
                  {step.reasoning}
                </Typography>
                <LinearProgress
                  variant="determinate"
                  value={step.confidence * 100}
                  sx={{
                    mt: 1,
                    height: 3,
                    borderRadius: 1,
                    backgroundColor: '#e0e0e0',
                    '& .MuiLinearProgress-bar': {
                      backgroundColor: getConfidenceColor(step.confidence),
                    },
                  }}
                />
              </CardContent>
            </Card>
          ))}
        </Box>

        {chain.final_conclusion && (
          <Card
            sx={{
              backgroundColor: '#f0f8e8',
              border: '1px solid #76B900',
              boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
            }}
          >
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                <CheckCircleIcon sx={{ color: '#76B900' }} />
                <Typography variant="body2" sx={{ color: '#76B900', fontWeight: 'bold' }}>
                  Final Conclusion
                </Typography>
              </Box>
              <Typography variant="body2" sx={{ color: '#333333' }}>
                {chain.final_conclusion}
              </Typography>
            </CardContent>
          </Card>
        )}
      </CardContent>
    </Card>
  );
};

export default ReasoningChainVisualization;


