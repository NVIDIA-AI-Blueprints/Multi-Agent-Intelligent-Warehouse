/**
 * TerminalTypewriter — terminal-style progressive text reveal component.
 *
 * Animates communication, not reasoning. The completed semantic answer is
 * always available to assistive technology via an aria-live region.
 *
 * Rules:
 *   - Click anywhere on the text to skip to complete
 *   - Reduced-motion: renders immediately, no animation
 *   - Governance badges must be rendered OUTSIDE this component — they are
 *     never delayed by the animation
 */

import React from 'react';
import { Box, Typography } from '@mui/material';
import { useTypewriterReveal, TypewriterOptions } from './useTypewriterReveal';

interface TerminalTypewriterProps {
  text: string;
  turnKey: string;
  options?: TypewriterOptions;
  sx?: object;
}

export default function TerminalTypewriter({
  text,
  turnKey,
  options,
  sx,
}: TerminalTypewriterProps) {
  const { displayText, isTyping, skip } = useTypewriterReveal(text, turnKey, options);

  return (
    <Box
      sx={{ position: 'relative', cursor: isTyping ? 'pointer' : 'default', ...sx }}
      onClick={isTyping ? skip : undefined}
      title={isTyping ? 'Click to skip animation' : undefined}
    >
      {/* Visually hidden full text for screen readers — always present */}
      <Typography
        aria-live="polite"
        sx={{
          position: 'absolute',
          width: '1px',
          height: '1px',
          padding: 0,
          margin: '-1px',
          overflow: 'hidden',
          clip: 'rect(0,0,0,0)',
          whiteSpace: 'nowrap',
          border: 0,
        }}
      >
        {text}
      </Typography>

      {/* Animated visible text */}
      <Typography
        aria-hidden="true"
        sx={{
          fontFamily: 'monospace',
          fontSize: '0.8rem',
          color: '#C9D1D9',
          lineHeight: 1.5,
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
          ...sx,
        }}
      >
        {displayText}
        {isTyping && (
          <Box
            component="span"
            sx={{
              display: 'inline-block',
              width: '0.55em',
              height: '1em',
              background: '#3FB950',
              verticalAlign: 'text-bottom',
              ml: '1px',
              animation: 'blink 1s step-end infinite',
              '@keyframes blink': {
                '0%, 100%': { opacity: 1 },
                '50%': { opacity: 0 },
              },
            }}
          />
        )}
      </Typography>

      {isTyping && (
        <Typography sx={{
          fontFamily: 'monospace',
          fontSize: '0.52rem',
          color: '#30363D',
          mt: '2px',
          letterSpacing: '0.06em',
        }}>
          CLICK TO SKIP
        </Typography>
      )}
    </Box>
  );
}
