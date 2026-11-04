import React from 'react';
import { Box, Typography } from '@mui/material';

/** Inline error for a failed demo API call (message from describeDemoApiError). */
export default function ApiErrorNotice({
  title,
  message,
  testId,
}: {
  title: string;
  message: string;
  testId?: string;
}) {
  return (
    <Box
      role="alert"
      data-testid={testId}
      sx={{
        background: '#1a0f0f',
        border: '1px solid #6e1111',
        borderRadius: '6px',
        px: 1.5,
        py: 1,
      }}
    >
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.68rem', fontWeight: 700, color: '#F85149' }}>
        {title}
      </Typography>
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#C9D1D9', mt: 0.25, wordBreak: 'break-word' }}>
        {message}
      </Typography>
    </Box>
  );
}
