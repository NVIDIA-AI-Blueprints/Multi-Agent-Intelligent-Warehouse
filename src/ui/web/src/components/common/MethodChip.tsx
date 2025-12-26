import React from 'react';
import { Chip, ChipProps } from '@mui/material';

interface MethodChipProps extends Omit<ChipProps, 'label' | 'color'> {
  method: string;
}

/**
 * Reusable chip component for HTTP methods with consistent color coding.
 * GET = success (green), others = primary (blue).
 */
export const MethodChip: React.FC<MethodChipProps> = ({ 
  method, 
  ...props 
}) => {
  const color = method === 'GET' ? 'success' : 'primary';
  
  return (
    <Chip
      label={method}
      size="small"
      color={color}
      {...props}
    />
  );
};

