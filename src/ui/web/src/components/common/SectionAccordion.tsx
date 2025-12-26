import React, { ReactNode } from 'react';
import {
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Typography,
} from '@mui/material';
import { ExpandMore as ExpandMoreIcon } from '@mui/icons-material';
import { SvgIconComponent } from '@mui/icons-material';

interface SectionAccordionProps {
  id: string;
  expanded: boolean | string;
  onChange: (panel: string) => (event: React.SyntheticEvent, isExpanded: boolean) => void;
  icon: SvgIconComponent;
  title: string;
  children: ReactNode;
}

/**
 * Reusable accordion component for API reference sections.
 * Provides consistent styling and structure for collapsible sections.
 */
export const SectionAccordion: React.FC<SectionAccordionProps> = ({
  id,
  expanded,
  onChange,
  icon: Icon,
  title,
  children,
}) => {
  return (
    <Accordion expanded={expanded === id} onChange={onChange(id)}>
      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
        <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Icon color="primary" />
          {title}
        </Typography>
      </AccordionSummary>
      <AccordionDetails>
        {children}
      </AccordionDetails>
    </Accordion>
  );
};

