import React, { useState, useEffect } from 'react';
import { Box, Typography } from '@mui/material';
import WorldOverview from './WorldOverview';
import WorldChanges from './WorldChanges';
import WorldGraph from './WorldGraph';
import { GraphFocusContext } from '../../services/worldAPI';

type WorldTab = 'overview' | 'graph' | 'changes' | 'raw';
export type WorldView = 'base' | 'scenario' | 'live';

const TABS: { id: WorldTab; label: string; available: boolean }[] = [
  { id: 'overview', label: 'OVERVIEW', available: true },
  { id: 'graph', label: 'GRAPH', available: true },
  { id: 'changes', label: 'CHANGES', available: true },
  { id: 'raw', label: 'RAW', available: false },
];

const WORLD_VIEWS: { id: WorldView; label: string; disabled: boolean; tooltip?: string }[] = [
  { id: 'base', label: 'BASE', disabled: false },
  { id: 'scenario', label: 'SCENARIO', disabled: false },
  { id: 'live', label: 'LIVE', disabled: true, tooltip: 'COMING NEXT' },
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

function WorldViewSwitcher({
  worldView,
  onChange,
}: {
  worldView: WorldView;
  onChange: (v: WorldView) => void;
}) {
  return (
    <Box
      sx={{ display: 'flex', gap: 0 }}
      role="group"
      aria-label="World view selector"
      data-testid="world-view-switcher"
    >
      {WORLD_VIEWS.map((v, i) => (
        <Box
          key={v.id}
          component="button"
          disabled={v.disabled}
          aria-pressed={!v.disabled && worldView === v.id}
          aria-disabled={v.disabled}
          title={v.disabled ? v.tooltip : undefined}
          onClick={!v.disabled ? () => onChange(v.id) : undefined}
          sx={{
            background: !v.disabled && worldView === v.id ? '#1C2128' : 'transparent',
            border: '1px solid #21262D',
            borderLeft: i > 0 ? 'none' : '1px solid #21262D',
            borderRadius:
              i === 0
                ? '4px 0 0 4px'
                : i === WORLD_VIEWS.length - 1
                ? '0 4px 4px 0'
                : '0',
            px: '10px',
            py: '3px',
            fontFamily: 'monospace',
            fontSize: '0.62rem',
            fontWeight: !v.disabled && worldView === v.id ? 700 : 400,
            color: v.disabled ? '#30363D' : worldView === v.id ? '#58A6FF' : '#6E7681',
            cursor: v.disabled ? 'not-allowed' : 'pointer',
            textTransform: 'uppercase',
            letterSpacing: '0.06em',
            '&:hover': !v.disabled ? { color: '#58A6FF' } : {},
          }}
        >
          {v.label}
        </Box>
      ))}
    </Box>
  );
}

interface WorldShellProps {
  focusContext?: GraphFocusContext | null;
  onReturnToCopilot?: () => void;
}

export default function WorldShell({ focusContext, onReturnToCopilot }: WorldShellProps = {}) {
  const [tab, setTab] = useState<WorldTab>('overview');
  const [worldView, setWorldView] = useState<WorldView>('base');

  // When Copilot sends a graph focus context, auto-switch to GRAPH tab
  useEffect(() => {
    if (focusContext?.entityId) {
      setTab('graph');
    }
  }, [focusContext]);

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

      {/* World view switcher — shown below sub-tabs */}
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 2,
          px: 2,
          py: '6px',
          borderBottom: '1px solid #21262D',
          background: '#0D1117',
        }}
      >
        <Typography
          sx={{
            fontFamily: 'monospace',
            fontSize: '0.58rem',
            color: '#484F58',
            letterSpacing: '0.06em',
            textTransform: 'uppercase',
            flexShrink: 0,
          }}
        >
          View
        </Typography>
        <WorldViewSwitcher worldView={worldView} onChange={setWorldView} />
      </Box>

      {/* Tab content */}
      <Box sx={{ flexGrow: 1, overflow: 'auto' }}>
        {tab === 'overview' && <WorldOverview />}

        {tab === 'graph' && (
          <WorldGraph
            worldView={worldView}
            focusContext={focusContext}
            onReturnToCopilot={onReturnToCopilot}
          />
        )}

        {tab === 'changes' && <WorldChanges worldView={worldView} />}

        {tab === 'raw' && (
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
              RAW
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
