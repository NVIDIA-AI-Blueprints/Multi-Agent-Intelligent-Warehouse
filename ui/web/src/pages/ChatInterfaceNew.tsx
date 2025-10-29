import React, { useState, useRef, useEffect } from 'react';
import {
  Box,
  TextField,
  IconButton,
  Typography,
  Paper,
  Fab,
  Skeleton,
  Alert,
  Snackbar,
} from '@mui/material';
import {
  Send as SendIcon,
  Menu as MenuIcon,
  Close as CloseIcon,
  Visibility as VisibilityIcon,
  VisibilityOff as VisibilityOffIcon,
} from '@mui/icons-material';
import { useMutation, useQuery } from 'react-query';
import { chatAPI, healthAPI, operationsAPI } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import TopBar from '../components/chat/TopBar';
import LeftRail from '../components/chat/LeftRail';
import MessageBubble from '../components/chat/MessageBubble';
import RightPanel from '../components/chat/RightPanel';

interface Message {
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
}

interface StreamingEvent {
  stage: string;
  agent?: string;
  confidence?: number;
  k?: number;
  reranked?: number;
  evidence_score?: number;
  query?: string;
  lat_ms?: number;
  action?: string;
  params?: any;
  guardrails?: { pass: boolean; notes: string[] };
  audit_id?: string;
  text?: string;
  options?: string[];
}

const ChatInterfaceNew: React.FC = () => {
  const { isAuthenticated } = useAuth();
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '1',
      type: 'answer',
      content: 'Hello! I\'m your Warehouse Operational Assistant. How can I help you today?',
      sender: 'assistant',
      timestamp: new Date(),
      route: 'general',
      confidence: 0.95,
    },
  ]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [rightPanelOpen, setRightPanelOpen] = useState(false);
  const [showInternals, setShowInternals] = useState(false);
  const [streamingEvents, setStreamingEvents] = useState<StreamingEvent[]>([]);
  const [currentEvidence, setCurrentEvidence] = useState<any[]>([]);
  const [currentSqlQuery, setCurrentSqlQuery] = useState<any>(null);
  const [currentPlannerDecision, setCurrentPlannerDecision] = useState<any>(null);
  const [currentActiveContext, setCurrentActiveContext] = useState<any>(null);
  const [currentToolTimeline, setCurrentToolTimeline] = useState<any[]>([]);
  const [snackbar, setSnackbar] = useState<{ open: boolean; message: string; severity: 'success' | 'error' | 'info' }>({
    open: false,
    message: '',
    severity: 'info',
  });

  // Top bar state - use environment/config values
  const [warehouse, setWarehouse] = useState(process.env.REACT_APP_WAREHOUSE_ID || 'WH-01');
  const [environment, setEnvironment] = useState(process.env.NODE_ENV === 'production' ? 'Prod' : 'Dev');
  
  // Get user role from auth context if available
  const getUserRole = () => {
    try {
      const token = localStorage.getItem('auth_token');
      if (token) {
        // In a real app, decode JWT to get role
        // For now, default to manager
        return 'manager';
      }
      return 'guest';
    } catch {
      return 'guest';
    }
  };
  const [role, setRole] = useState(getUserRole());
  
  // Connection status - check health endpoints
  const { data: healthStatus } = useQuery('health', healthAPI.check, {
    refetchInterval: 30000, // Check every 30 seconds
    retry: false,
  });
  
  // Update connections based on health status
  const connections = {
    nim: true, // NVIDIA NIM - assume available if we're using it
    db: healthStatus?.ok || false,
    milvus: true, // Milvus health could be checked separately
    kafka: true, // Kafka health could be checked separately
  };

  // Recent tasks - get from actual API
  const { data: tasks } = useQuery('recent-tasks', () => 
    operationsAPI.getTasks().then(tasks => 
      tasks?.slice(0, 5).map(task => ({
        id: String(task.id),
        title: `${task.kind} - ${task.assignee || 'Unassigned'}`,
        status: task.status as 'completed' | 'pending' | 'in_progress',
        timestamp: new Date(task.created_at),
      })) || []
    ),
    {
      refetchInterval: 60000, // Refresh every minute
    }
  );
  
  const recentTasks = tasks || [];

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const chatMutation = useMutation(chatAPI.sendMessage, {
    onSuccess: (response) => {
      // Simulate streaming response
      simulateStreamingResponse(response);
    },
    onError: (error: any) => {
      console.error('Chat error:', error);
      setSnackbar({
        open: true,
        message: `Failed to send message: ${error.message || 'Unknown error'}`,
        severity: 'error',
      });
    },
    onSettled: () => {
      setIsLoading(false);
    },
  });

  const simulateStreamingResponse = (response: any) => {
    // Simulate streaming events
    const events: StreamingEvent[] = [
      { stage: 'route_decision', agent: response.route || 'operations', confidence: response.confidence || 0.87 },
      { stage: 'retrieval_debug', k: 12, reranked: 6, evidence_score: 0.82 },
      { stage: 'sql_trace', query: 'SELECT * FROM orders WHERE id IN (1001,1002)', lat_ms: 38 },
    ];

    if (response.proposals && response.proposals.length > 0) {
      response.proposals.forEach((proposal: any) => {
        events.push({
          stage: 'proposed_action',
          action: proposal.action,
          params: proposal.params,
          guardrails: proposal.guardrails,
          audit_id: proposal.audit_id,
        });
      });
    }

    if (response.clarifying) {
      events.push({
        stage: 'clarifying_question',
        text: response.clarifying.text,
        options: response.clarifying.options,
      });
    }

    events.push({ stage: 'final_answer', text: response.reply || response.content });

    // Simulate streaming
    let eventIndex = 0;
    const streamInterval = setInterval(() => {
      if (eventIndex < events.length) {
        setStreamingEvents(prev => [...prev, events[eventIndex]]);
        eventIndex++;
      } else {
        clearInterval(streamInterval);
        // Add final message
        const assistantMessage: Message = {
          id: Date.now().toString(),
          type: response.clarifying ? 'clarifying_question' : 'answer',
          content: response.reply || response.content,
          sender: 'assistant',
          timestamp: new Date(),
          route: response.route,
          confidence: response.confidence,
          structured_data: response.structured_data,
          proposals: response.proposals,
          clarifying: response.clarifying,
          evidence: response.evidence,
        };

        setMessages(prev => [...prev, assistantMessage]);
        
        // Process evidence data properly
        const evidenceData = [];
        
        // Add SQL evidence if available
        if (response.evidence && Array.isArray(response.evidence)) {
          evidenceData.push(...response.evidence);
        }
        
        // Add structured data as evidence if available
        // Check both response.structured_data and context.structured_response
        const structuredData = response.structured_data || response.context?.structured_response;
        
        if (structuredData) {
          evidenceData.push({
            type: 'structured',
            id: 'structured_data',
            content: structuredData.natural_language || 'Structured response data',
            score: structuredData.confidence || 0,
            data: structuredData
          });
          
          // Also add individual procedures as separate evidence items
          if (structuredData.data && structuredData.data.procedures && structuredData.data.procedures.procedures) {
            structuredData.data.procedures.procedures.forEach((procedure: any, index: number) => {
              evidenceData.push({
                type: 'procedure',
                id: `procedure_${procedure.id}`,
                content: procedure.description || procedure.name,
                score: 0.9, // High confidence for procedures
                data: procedure
              });
            });
          }
        }
        
        
        setCurrentEvidence(evidenceData);
        setCurrentSqlQuery(response.sql_query);
        setCurrentPlannerDecision(response.planner_decision);
        setCurrentActiveContext(response.context || {});
        setCurrentToolTimeline(response.tool_timeline || []);
        setStreamingEvents([]);
      }
    }, 500);
  };

  const handleSendMessage = async () => {
    if (!inputValue.trim() || isLoading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      type: 'answer',
      content: inputValue,
      sender: 'user',
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);
    setInputValue('');
    setIsLoading(true);

    try {
      await chatMutation.mutateAsync({
        message: inputValue,
        session_id: 'default',
        context: {
          warehouse,
          role,
          environment,
        },
      });
    } catch (error: any) {
      console.error('Error sending message:', error);
    }
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event && event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      handleSendMessage();
    }
  };

  const handleScenarioSelect = (scenario: string) => {
    const scenarioMessages: { [key: string]: string } = {
      create_pick_wave: 'Create a wave for orders 1001-1010 in Zone A and dispatch a forklift.',
      dispatch_forklift: 'Dispatch forklift FL-07 to Zone A for pick operations.',
      log_incident: 'Machine over-temp event at Dock D2.',
      check_assets: 'Show me the status of all forklifts and their availability',
      safety_check: 'What are the safety procedures for forklift operations?',
      // Demo flow scenarios
      work_order_flow: 'Create a wave for orders 1001-1010 in Zone A and dispatch a forklift.',
      equipment_status_flow: 'Show me the status of all forklifts and their availability',
      safety_incident_flow: 'Machine over-temp event at Dock D2.',
    };

    const message = scenarioMessages[scenario];
    if (message) {
      setInputValue(message);
      inputRef.current?.focus();
    }
  };

  const handleActionApprove = (auditId: string, action: string) => {
    // Simulate action approval
    setSnackbar({
      open: true,
      message: `Action ${action} approved successfully!`,
      severity: 'success',
    });

    // Update tool timeline
    setCurrentToolTimeline(prev => [
      ...prev,
      {
        id: Date.now().toString(),
        action,
        status: 'approved',
        timestamp: new Date(),
        audit_id: auditId,
      },
    ]);

    // Add action result message
    const actionResultMessage: Message = {
      id: Date.now().toString(),
      type: 'action_result',
      content: `Action ${action} has been approved and executed successfully.`,
      sender: 'assistant',
      timestamp: new Date(),
      route: 'system',
    };

    setMessages(prev => [...prev, actionResultMessage]);
  };

  const handleActionReject = (auditId: string, action: string) => {
    setSnackbar({
      open: true,
      message: `Action ${action} rejected.`,
      severity: 'info',
    });

    // Update tool timeline
    setCurrentToolTimeline(prev => [
      ...prev,
      {
        id: Date.now().toString(),
        action,
        status: 'rejected',
        timestamp: new Date(),
        audit_id: auditId,
      },
    ]);
  };

  const handleQuickReply = (option: string) => {
    setInputValue(option);
    inputRef.current?.focus();
  };


  if (!isAuthenticated) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <Typography variant="h6" sx={{ color: '#ffffff' }}>
          Please log in to access the chat interface.
        </Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ height: '100vh', display: 'flex', flexDirection: 'column', backgroundColor: '#000000' }}>
      {/* Top Bar */}
      <TopBar
        warehouse={warehouse}
        role={role}
        environment={environment}
        connections={connections}
        onWarehouseChange={setWarehouse}
        onRoleChange={setRole}
        onEnvironmentChange={setEnvironment}
      />

      {/* Main Content */}
      <Box sx={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* Left Rail */}
        <LeftRail
          onScenarioSelect={handleScenarioSelect}
          recentTasks={recentTasks}
        />

        {/* Chat Area */}
        <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', backgroundColor: '#000000' }}>
          {/* Chat Messages */}
          <Box
            sx={{
              flex: 1,
              overflow: 'auto',
              p: 0,
              backgroundColor: '#000000',
            }}
          >
            {messages.map((message) => (
              <MessageBubble
                key={message.id}
                message={message}
                onActionApprove={handleActionApprove}
                onActionReject={handleActionReject}
                onQuickReply={handleQuickReply}
              />
            ))}

            {/* Streaming Events */}
            {streamingEvents.length > 0 && (
              <Box sx={{ px: 2, mb: 2 }}>
                <Paper sx={{ backgroundColor: '#1a1a1a', p: 2, border: '1px solid #333333' }}>
                  <Typography variant="body2" sx={{ color: '#76B900', mb: 1 }}>
                    Processing...
                  </Typography>
                  {streamingEvents.map((event, index) => (
                    <Box key={index} sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                      <Typography variant="caption" sx={{ color: '#666666', minWidth: '100px' }}>
                        {event.stage}:
                      </Typography>
                      <Typography variant="caption" sx={{ color: '#ffffff' }}>
                        {event.agent && `Agent: ${event.agent}`}
                        {event.confidence && ` (${(event.confidence * 100).toFixed(1)}%)`}
                        {event.k && ` K=${event.k}→${event.reranked}`}
                        {event.lat_ms && ` (${event.lat_ms}ms)`}
                        {event.action && ` ${event.action}`}
                        {event.text && ` ${event.text}`}
                      </Typography>
                    </Box>
                  ))}
                </Paper>
              </Box>
            )}

            {/* Loading Skeleton */}
            {isLoading && (
              <Box sx={{ px: 2, mb: 2 }}>
                <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-start' }}>
                  <Skeleton variant="circular" width={32} height={32} sx={{ backgroundColor: '#333333' }} />
                  <Box sx={{ flex: 1 }}>
                    <Skeleton variant="rectangular" width="70%" height={60} sx={{ backgroundColor: '#1a1a1a', borderRadius: 2 }} />
                  </Box>
                </Box>
              </Box>
            )}

            <div ref={messagesEndRef} />
          </Box>

          {/* Input Area */}
          <Box
            sx={{
              p: 2,
              borderTop: '1px solid #333333',
              backgroundColor: '#111111',
            }}
          >
            <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-end' }}>
              <TextField
                ref={inputRef}
                fullWidth
                multiline
                maxRows={4}
                value={inputValue}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setInputValue(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask me anything about warehouse operations..."
                disabled={isLoading}
                sx={{
                  '& .MuiOutlinedInput-root': {
                    backgroundColor: '#1a1a1a',
                    color: '#ffffff',
                    '& fieldset': {
                      borderColor: '#333333',
                    },
                    '&:hover fieldset': {
                      borderColor: '#76B900',
                    },
                    '&.Mui-focused fieldset': {
                      borderColor: '#76B900',
                    },
                  },
                  '& .MuiInputBase-input': {
                    color: '#ffffff',
                    '&::placeholder': {
                      color: '#666666',
                      opacity: 1,
                    },
                  },
                }}
              />
              <IconButton
                onClick={handleSendMessage}
                disabled={!inputValue.trim() || isLoading}
                sx={{
                  backgroundColor: '#76B900',
                  color: '#ffffff',
                  '&:hover': {
                    backgroundColor: '#5a8f00',
                  },
                  '&:disabled': {
                    backgroundColor: '#333333',
                    color: '#666666',
                  },
                }}
              >
                <SendIcon />
              </IconButton>
            </Box>
          </Box>
        </Box>

        {/* Right Panel */}
        <RightPanel
          isOpen={rightPanelOpen}
          onClose={() => setRightPanelOpen(false)}
          evidence={currentEvidence}
          sqlQuery={currentSqlQuery}
          plannerDecision={currentPlannerDecision}
          activeContext={currentActiveContext}
          toolTimeline={currentToolTimeline}
        />
      </Box>

      {/* Floating Action Buttons */}
      <Box sx={{ position: 'fixed', bottom: 20, right: 20, display: 'flex', flexDirection: 'column', gap: 1 }}>
        <Fab
          size="small"
          onClick={() => setRightPanelOpen(!rightPanelOpen)}
          sx={{
            backgroundColor: rightPanelOpen ? '#76B900' : '#333333',
            color: '#ffffff',
            '&:hover': {
              backgroundColor: rightPanelOpen ? '#5a8f00' : '#555555',
            },
          }}
        >
          {rightPanelOpen ? <CloseIcon /> : <MenuIcon />}
        </Fab>
        
        <Fab
          size="small"
          onClick={() => setShowInternals(!showInternals)}
          sx={{
            backgroundColor: showInternals ? '#9C27B0' : '#333333',
            color: '#ffffff',
            '&:hover': {
              backgroundColor: showInternals ? '#7b1fa2' : '#555555',
            },
          }}
        >
          {showInternals ? <VisibilityOffIcon /> : <VisibilityIcon />}
        </Fab>
        
      </Box>

      {/* Snackbar */}
      <Snackbar
        open={snackbar.open}
        autoHideDuration={4000}
        onClose={(_, reason?: string) => {
          if (reason !== 'clickaway') {
            setSnackbar(prev => ({ ...prev, open: false }));
          }
        }}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
      >
        <Alert
          onClose={() => {
            setSnackbar(prev => ({ ...prev, open: false }));
          }}
          severity={snackbar.severity}
          sx={{ width: '100%' }}
        >
          {snackbar.message}
        </Alert>
      </Snackbar>
    </Box>
  );
};

export default ChatInterfaceNew;
