/**
 * ReasonStage — wraps AgenticReasoningCanvas for the REASON stage.
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

export default function ReasonStage({ analysisResult }: StageContentPaneProps) {
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

      <AgenticReasoningCanvas analysisResult={analysisResult} />
    </Box>
  );
}
