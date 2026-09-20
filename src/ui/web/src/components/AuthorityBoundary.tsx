/**
 * AuthorityBoundary — reusable visual separator marking the MAIW Authority Boundary.
 *
 * Placed at the transition between AI recommendation and governed operational execution.
 *
 * Design contracts:
 * - Amber/orange accent (consistent with PENDING/APPROVAL governance color #D29922)
 * - Text-based — not color-only (accessible)
 * - Compact — a structural marker, not a marketing graphic
 * - Never rendered during active execution or post-execution stages
 *
 * See docs/ux/MAIW_AUTHORITY_UX.md for placement guidance.
 */

import React from 'react';
import { Box, Typography } from '@mui/material';
import {
  AUTHORITY_BOUNDARY_LABEL,
  AUTHORITY_BOUNDARY_SUBTEXT,
} from '../constants/authorityStates';

interface AuthorityBoundaryProps {
  /** Optional compact mode — omits the subtext for space-constrained layouts */
  compact?: boolean;
  /** Optional data-testid override */
  testId?: string;
}

const AuthorityBoundary: React.FC<AuthorityBoundaryProps> = ({
  compact = false,
  testId = 'authority-boundary',
}) => {
  return (
    <Box
      data-testid={testId}
      role="separator"
      aria-label={AUTHORITY_BOUNDARY_LABEL}
      sx={{
        display: 'flex',
        alignItems: 'center',
        gap: 1.5,
        py: 1,
        px: 0,
        my: 1,
      }}
    >
      {/* Left rule */}
      <Box sx={{ flex: 1, height: '1px', backgroundColor: '#D2992233' }} />

      {/* Center label */}
      <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 0.25, flexShrink: 0 }}>
        <Typography
          sx={{
            fontFamily: 'monospace',
            fontSize: '0.58rem',
            fontWeight: 700,
            color: '#D29922',
            letterSpacing: '0.14em',
            textTransform: 'uppercase',
            whiteSpace: 'nowrap',
          }}
        >
          {AUTHORITY_BOUNDARY_LABEL}
        </Typography>
        {!compact && (
          <Typography
            sx={{
              fontFamily: 'monospace',
              fontSize: '0.55rem',
              color: '#484F58',
              letterSpacing: '0.04em',
              whiteSpace: 'nowrap',
            }}
          >
            {AUTHORITY_BOUNDARY_SUBTEXT}
          </Typography>
        )}
      </Box>

      {/* Right rule */}
      <Box sx={{ flex: 1, height: '1px', backgroundColor: '#D2992233' }} />
    </Box>
  );
};

export default AuthorityBoundary;
