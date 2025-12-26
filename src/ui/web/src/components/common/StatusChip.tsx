import React from 'react';
import { Chip, ChipProps } from '@mui/material';

interface StatusChipProps extends Omit<ChipProps, 'label' | 'color'> {
  status: string;
}

/**
 * Reusable chip component for status indicators with consistent color coding.
 * ✅ = success (green), ⚠️ = warning (orange/yellow).
 */
export const StatusChip: React.FC<StatusChipProps> = ({ 
  status, 
  ...props 
}) => {
  const color = status.includes('✅') ? 'success' : 'warning';
  
  return (
    <Chip
      label={status}
      size="small"
      color={color}
      {...props}
    />
  );
};

