import React, { useState } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Button,
  Stepper,
  Step,
  StepLabel,
  StepContent,
  Chip,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
} from '@mui/material';
import {
  PlayArrow as PlayIcon,
  CheckCircle as CheckIcon,
  RadioButtonUnchecked as UncheckedIcon,
  Assignment as AssignmentIcon,
  Inventory as InventoryIcon,
  Security as SecurityIcon,
} from '@mui/icons-material';

interface DemoScriptProps {
  onScenarioSelect: (scenario: string) => void;
}

const DemoScript: React.FC<DemoScriptProps> = ({ onScenarioSelect }) => {
  const [activeStep, setActiveStep] = useState(0);
  const [completedSteps, setCompletedSteps] = useState<number[]>([]);
  const [currentFlow, setCurrentFlow] = useState<string | null>(null);

  const demoFlows = [
    {
      id: 'work_order_flow',
      title: 'Work Order → Wave → Equipment Dispatch',
      description: 'Operations + EAO Agent collaboration',
      icon: <AssignmentIcon />,
      steps: [
        {
          label: 'User Request',
          description: 'User: "Create a wave for Orders 1001–1010 in Zone A and dispatch a forklift."',
          expected: 'Route → Operations (0.88)',
        },
        {
          label: 'Data Retrieval',
          description: 'Retrieval → top-12→6; SQL for order lines (38ms)',
          expected: 'Evidence: Order lines, zone layout',
        },
        {
          label: 'Proposed Actions',
          description: 'generate_pick_wave (params shown, SLA gain + travel time)',
          expected: 'Action card with Approve/Reject',
        },
        {
          label: 'Equipment Assignment',
          description: 'assign_equipment(asset_id=FL-07, zone=A)',
          expected: 'Equipment assignment card',
        },
        {
          label: 'User Approval',
          description: 'User clicks Approve (Tier 1)',
          expected: 'Success toast + audit IDs',
        },
        {
          label: 'Results',
          description: 'WMS wave id + equipment assignment',
          expected: 'action_result with links',
        },
      ],
    },
    {
      id: 'equipment_status_flow',
      title: 'Equipment Status Check & Assignment',
      description: 'Equipment/SQL path with asset management',
      icon: <InventoryIcon />,
      steps: [
        {
          label: 'User Request',
          description: 'User: "Show me the status of all forklifts and their availability"',
          expected: 'Route: Equipment (0.95)',
        },
        {
          label: 'Equipment Query',
          description: 'Execute equipment status query with filters',
          expected: 'SQL inspector shows query + results',
        },
        {
          label: 'Results Table',
          description: 'Table card: Equipment status breakdown',
          expected: 'Structured data table with asset details',
        },
        {
          label: 'Assignment Proposal',
          description: 'Proposed action assign_equipment for available forklifts',
          expected: 'Action card with equipment parameters',
        },
        {
          label: 'Approval',
          description: 'Approve → action_result with assignment details',
          expected: 'Success confirmation with asset ID',
        },
      ],
    },
    {
      id: 'safety_incident_flow',
      title: 'Safety Incident Response',
      description: 'Safety + EAO Agent collaboration',
      icon: <SecurityIcon />,
      steps: [
        {
          label: 'Incident Report',
          description: 'User: "Machine over-temp event at Dock D2."',
          expected: 'Route: Safety (0.95)',
        },
        {
          label: 'Proposed Actions',
          description: 'broadcast_alert(zone=D2), lockout_tagout_request(asset_id=DL-4), start_checklist(forklift_pre_op)',
          expected: 'Multiple action cards',
        },
        {
          label: 'User Decisions',
          description: 'Approve first two; reject third',
          expected: 'Selective approval/rejection',
        },
        {
          label: 'Evidence Panel',
          description: 'Policy spans + telemetry rows (Timescale)',
          expected: 'Evidence with source links',
        },
        {
          label: 'Summary',
          description: 'Final message summarizes actions, links to tickets, next steps',
          expected: 'Comprehensive action summary',
        },
      ],
    },
  ];

  const handleStepComplete = (stepIndex: number, flowId: string) => {
    if (currentFlow === flowId && !completedSteps.includes(stepIndex)) {
      setCompletedSteps([...completedSteps, stepIndex]);
      // Auto-advance to next step if not the last step
      const flow = demoFlows.find(f => f.id === flowId);
      if (flow && stepIndex < flow.steps.length - 1) {
        setActiveStep(stepIndex + 1);
      }
    }
  };

  const handleStepClick = (stepIndex: number, flowId: string) => {
    if (currentFlow === flowId) {
      setActiveStep(stepIndex);
    }
  };

  const handleFlowStart = (flowId: string) => {
    onScenarioSelect(flowId);
    setCurrentFlow(flowId);
    setActiveStep(0);
    setCompletedSteps([]);
  };

  const getStepIcon = (stepIndex: number) => {
    if (completedSteps.includes(stepIndex)) {
      return <CheckIcon sx={{ color: '#76B900' }} />;
    }
    return <UncheckedIcon sx={{ color: '#666666' }} />;
  };

  return (
    <Box sx={{ p: 2, backgroundColor: '#ffffff', height: '100%', overflow: 'auto' }}>
      <Typography variant="h6" sx={{ color: '#333333', mb: 3, textAlign: 'center', fontWeight: 500 }}>
        Demo Scripts
      </Typography>

      {demoFlows.map((flow, flowIndex) => (
        <Card key={flow.id} sx={{ mb: 3, backgroundColor: '#fafafa', border: '1px solid #e0e0e0', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
          <CardContent>
            <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
              <Box sx={{ color: '#76B900', mr: 2 }}>
                {flow.icon}
              </Box>
              <Box sx={{ flex: 1 }}>
                <Typography variant="h6" sx={{ color: '#333333', fontSize: '16px', fontWeight: 500 }}>
                  {flow.title}
                </Typography>
                <Typography variant="body2" sx={{ color: '#666666' }}>
                  {flow.description}
                </Typography>
                {currentFlow === flow.id && (
                  <Box sx={{ mt: 1 }}>
                    <Typography variant="caption" sx={{ color: '#76B900', fontWeight: 500 }}>
                      Progress: {completedSteps.length} / {flow.steps.length} steps completed
                    </Typography>
                    <Box sx={{ width: '100%', height: 4, backgroundColor: '#e0e0e0', borderRadius: 2, mt: 0.5 }}>
                      <Box 
                        sx={{ 
                          width: `${(completedSteps.length / flow.steps.length) * 100}%`, 
                          height: '100%', 
                          backgroundColor: '#76B900', 
                          borderRadius: 2,
                          transition: 'width 0.3s ease'
                        }} 
                      />
                    </Box>
                  </Box>
                )}
              </Box>
              <Box sx={{ display: 'flex', gap: 1 }}>
                {currentFlow === flow.id && (
                  <Button
                    variant="outlined"
                    size="small"
                    onClick={() => {
                      setCurrentFlow(null);
                      setActiveStep(0);
                      setCompletedSteps([]);
                    }}
                    sx={{
                      color: '#666666',
                      borderColor: '#e0e0e0',
                      '&:hover': { 
                        backgroundColor: '#f5f5f5',
                        borderColor: '#666666'
                      },
                    }}
                  >
                    Reset
                  </Button>
                )}
                <Button
                  variant="contained"
                  startIcon={<PlayIcon />}
                  onClick={() => handleFlowStart(flow.id)}
                  sx={{
                    backgroundColor: '#76B900',
                    color: '#ffffff',
                    '&:hover': { backgroundColor: '#5a8f00' },
                  }}
                >
                  {currentFlow === flow.id ? 'Restart' : 'Start'}
                </Button>
              </Box>
            </Box>

            <Stepper activeStep={activeStep} orientation="vertical">
              {flow.steps.map((step, stepIndex) => {
                const isCompleted = completedSteps.includes(stepIndex);
                const isActive = currentFlow === flow.id && activeStep === stepIndex;
                const isClickable = currentFlow === flow.id;
                
                return (
                  <Step key={stepIndex}>
                    <StepLabel
                      StepIconComponent={() => getStepIcon(stepIndex)}
                      onClick={() => isClickable && handleStepClick(stepIndex, flow.id)}
                      sx={{
                        cursor: isClickable ? 'pointer' : 'default',
                        '& .MuiStepLabel-label': {
                          color: isActive ? '#76B900' : isCompleted ? '#76B900' : '#333333',
                          fontSize: '14px',
                          fontWeight: isActive ? 'bold' : 'normal',
                        },
                        '&:hover': isClickable ? {
                          '& .MuiStepLabel-label': {
                            color: '#76B900',
                          },
                        } : {},
                      }}
                    >
                      {step.label}
                    </StepLabel>
                    <StepContent>
                      <Box sx={{ mb: 2 }}>
                        <Typography variant="body2" sx={{ color: '#666666', mb: 1 }}>
                          {step.description}
                        </Typography>
                        <Chip
                          label={step.expected}
                          size="small"
                          sx={{
                            backgroundColor: isCompleted ? '#76B900' : '#e0e0e0',
                            color: isCompleted ? '#ffffff' : '#333333',
                            fontSize: '10px',
                          }}
                        />
                      </Box>
                      {currentFlow === flow.id && (
                        <Button
                          size="small"
                          onClick={() => handleStepComplete(stepIndex, flow.id)}
                          disabled={isCompleted}
                          variant={isCompleted ? "outlined" : "contained"}
                          sx={{
                            backgroundColor: isCompleted ? 'transparent' : '#76B900',
                            color: isCompleted ? '#76B900' : '#000000',
                            borderColor: '#76B900',
                            '&:hover': {
                              backgroundColor: isCompleted ? '#76B900' : '#5a8f00',
                              color: isCompleted ? '#000000' : '#ffffff',
                            },
                            '&:disabled': {
                              backgroundColor: 'transparent',
                              color: '#76B900',
                              borderColor: '#76B900',
                            },
                          }}
                        >
                          {isCompleted ? '✓ Completed' : 'Mark Complete'}
                        </Button>
                      )}
                    </StepContent>
                  </Step>
                );
              })}
            </Stepper>
          </CardContent>
        </Card>
      ))}

      <Card sx={{ backgroundColor: '#fafafa', border: '1px solid #e0e0e0', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
        <CardContent>
          <Typography variant="h6" sx={{ color: '#333333', mb: 2, fontSize: '16px', fontWeight: 500 }}>
            Demo Tips
          </Typography>
          <List dense>
            <ListItem>
              <ListItemIcon>
                <CheckIcon sx={{ color: '#76B900', fontSize: '16px' }} />
              </ListItemIcon>
              <ListItemText
                primary="Choose WH-01, Role Manager"
                primaryTypographyProps={{ fontSize: '12px', color: '#333333' }}
              />
            </ListItem>
            <ListItem>
              <ListItemIcon>
                <CheckIcon sx={{ color: '#76B900', fontSize: '16px' }} />
              </ListItemIcon>
              <ListItemText
                primary="Toggle Show Internals for detailed view"
                primaryTypographyProps={{ fontSize: '12px', color: '#333333' }}
              />
            </ListItem>
            <ListItem>
              <ListItemIcon>
                <CheckIcon sx={{ color: '#76B900', fontSize: '16px' }} />
              </ListItemIcon>
              <ListItemText
                primary="Check Evidence & Tool timeline in right panel"
                primaryTypographyProps={{ fontSize: '12px', color: '#333333' }}
              />
            </ListItem>
            <ListItem>
              <ListItemIcon>
                <CheckIcon sx={{ color: '#76B900', fontSize: '16px' }} />
              </ListItemIcon>
              <ListItemText
                primary="Use quick replies for clarifying questions"
                primaryTypographyProps={{ fontSize: '12px', color: '#333333' }}
              />
            </ListItem>
          </List>
        </CardContent>
      </Card>
    </Box>
  );
};

export default DemoScript;
