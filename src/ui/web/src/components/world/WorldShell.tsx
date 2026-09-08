import React, { useState } from 'react';
import { Box, Typography } from '@mui/material';
import WorldOverview from './WorldOverview';

type WorldTab = 'overview' | 'graph' | 'changes' | 'raw';

const TABS: { id: WorldTab; label: string; available: boolean }[] = [
  { id: 'overview', label: 'OVERVIEW', available: true },
  { id: 'graph', label: 'GRAPH', available: false },
  { id: 'changes', label: 'CHANGES', available: false },
  { id: 'raw', label: 'RAW', available: false },
];

function WorldTabSwitcher({
  tab,
  onChange,
}: {
  tab: WorldTab;
  onChange: (t: WorldTab) => void;
}) {
  return (
    <Box sx={{ display: 'flex', gap: 0 }} role="group" aria-label="World Explorer tabs">
      {TABS.map((t, i) => (
        <Box
          key={t.id}
          component="button"
          disabled={!t.available}
          aria-pressed={tab === t.id}
          aria-disabled={!t.available}
          onClick={t.available ? () => onChange(t.id) : undefined}
          sx={{
            background: tab === t.id && t.available ? '#1C2128' : 'transparent',
            border: '1px solid #21262D',
            borderLeft: i > 0 ? 'none' : '1px solid #21262D',
            borderRadius:
              i === 0
                ? '4px 0 0 4px'
                : i === TABS.length - 1
                ? '0 4px 4px 0'
                : '0',
            px: '10px',
            py: '4px',
            fontFamily: 'monospace',
            fontSize: '0.65rem',
            fontWeight: tab === t.id && t.available ? 700 : 400,
            color: !t.available ? '#30363D' : tab === t.id ? '#C9D1D9' : '#6E7681',
            cursor: t.available ? 'pointer' : 'not-allowed',
            textTransform: 'uppercase',
            letterSpacing: '0.06em',
            '&:hover': t.available ? { color: '#C9D1D9' } : {},
          }}
        >
          {t.label}
          {!t.available && (
            <Box
              component="span"
              sx={{
                ml: '5px',
                fontFamily: 'monospace',
                fontSize: '0.52rem',
                color: '#30363D',
                border: '1px solid #21262D',
                borderRadius: '3px',
                px: '3px',
                py: '0px',
                lineHeight: 1.6,
              }}
            >
              SOON
            </Box>
          )}
        </Box>
      ))}
    </Box>
  );
}

export default function WorldShell() {
  const [tab, setTab] = useState<WorldTab>('overview');

  return (
    <Box
      data-testid="world-shell"
      sx={{ display: 'flex', flexDirection: 'column', flexGrow: 1, background: '#0D1117' }}
    >
      {/* Sub-tab bar */}
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 2,
          px: 2,
          py: '7px',
          borderBottom: '1px solid #21262D',
          background: '#0D1117',
        }}
      >
        <Typography
          sx={{
            fontFamily: 'monospace',
            fontSize: '0.65rem',
            color: '#484F58',
            letterSpacing: '0.06em',
            textTransform: 'uppercase',
            flexShrink: 0,
          }}
        >
          World Explorer
        </Typography>
        <Box sx={{ width: '1px', height: 14, background: '#21262D', flexShrink: 0 }} />
        <WorldTabSwitcher tab={tab} onChange={setTab} />
      </Box>

      {/* Tab content */}
      <Box sx={{ flexGrow: 1, overflow: 'auto' }}>
        {tab === 'overview' && <WorldOverview />}

        {tab !== 'overview' && (
          <Box
            sx={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              minHeight: 240,
              gap: 1,
            }}
          >
            <Typography
              sx={{
                fontFamily: 'monospace',
                fontSize: '0.72rem',
                color: '#30363D',
                textTransform: 'uppercase',
                letterSpacing: '0.08em',
              }}
            >
              {TABS.find((t) => t.id === tab)?.label ?? tab}
            </Typography>
            <Typography
              sx={{
                fontFamily: 'monospace',
                fontSize: '0.62rem',
                color: '#21262D',
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
              }}
            >
              Coming next
            </Typography>
          </Box>
        )}
      </Box>
    </Box>
  );
}
