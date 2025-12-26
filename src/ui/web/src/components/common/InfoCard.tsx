import React, { ReactNode } from 'react';
import {
  Card,
  CardContent,
  Typography,
  CardProps,
} from '@mui/material';

interface InfoCardProps extends CardProps {
  title: string;
  children: ReactNode;
  description?: string;
}

/**
 * Reusable info card component with consistent styling.
 * Used for displaying structured information in cards.
 */
export const InfoCard: React.FC<InfoCardProps> = ({
  title,
  description,
  children,
  sx,
  ...props
}) => {
  return (
    <Card variant="outlined" sx={sx} {...props}>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          {title}
        </Typography>
        {description && (
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            {description}
          </Typography>
        )}
        {children}
      </CardContent>
    </Card>
  );
};

