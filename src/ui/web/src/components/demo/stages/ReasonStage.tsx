/**
 * ReasonStage — wraps AgenticReasoningCanvas for the REASON stage.
 *
 * UX-1B: Shows AgentActivity compact panel above the reasoning canvas,
 * giving operators visibility into which agent is working and what SOP
 * it is following. Expert mode shows developer fields.
 *
 * The canvas renders the full structured reasoning arc:
 *   OBSERVED EVIDENCE → AGENT INTERPRETATION → CAPABILITIES/SKILLS → RECOMMENDED RESPONSE
 *
 * SSE-only fallback (pre-analysis): shows a waiting state via the canvas's empty pillars.
 */

import React from 'react';
import { Box, Typography } from '@mui/material';
import { StageSection, MonoText, StageContentPaneProps } from '../StageContentPane';
import AgenticReasoningCanvas from '../AgenticReasoningCanvas';
import AgentActivity from '../AgentActivity';

export default function ReasonStage({ analysisResult, expertMode, agentTask }: StageContentPaneProps) {
  return (
    <Box data-testid="reason-stage">
      {/* Stage header */}
      <StageSection>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <Typography sx={{
            fontFamily: 'monospace', fontSize: '0.72rem', fontWeight: 700,
            color: '#58A6FF', textTransform: 'uppercase', letterSpacing: '0.06em',
          }}>
            Reason
          </Typography>
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#484F58' }}>
            Agentic reasoning trace
          </Typography>
        </Box>
      </StageSection>

      {/* UX-1B: Agent activity panel (compact, above reasoning content) */}
      <StageSection>
        <AgentActivity
          task={agentTask ?? null}
          expertMode={expertMode}
          compact
        />
      </StageSection>

      <AgenticReasoningCanvas analysisResult={analysisResult} expertMode={expertMode} />
    </Box>
  );
}
