import React from 'react';
import { Paper, PaperProps } from '@mui/material';

interface CodeBlockProps extends Omit<PaperProps, 'children'> {
  children: string;
}

/**
 * Reusable code block component with consistent monospace styling.
 * Used for displaying code examples, JSON, and formatted text.
 */
export const CodeBlock: React.FC<CodeBlockProps> = ({ 
  children, 
  sx,
  ...props 
}) => {
  return (
    <Paper
      sx={{
        p: 2,
        bgcolor: 'grey.100',
        fontFamily: 'monospace',
        fontSize: '0.875rem',
        ...sx,
      }}
      {...props}
    >
      {children}
    </Paper>
  );
};

