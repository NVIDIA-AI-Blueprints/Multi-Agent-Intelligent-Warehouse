import React, { useState } from 'react';
import {
  Box,
  Typography,
  Tooltip,
  Chip,
  IconButton,
  Drawer,
} from '@mui/material';
import {
  Dashboard as DashboardIcon,
  Inventory2 as StateIcon,
  Gavel as DecisionIcon,
  Psychology as ModelIcon,
  Hub as CapabilityIcon,
  Timeline as ActivityIcon,
  MonitorHeart as HealthIcon,
  Chat as ChatIcon,
  Build as EquipmentIcon,
  Work as OperationsIcon,
  Security as SafetyIcon,
  Settings as SettingsIcon,
  Article as DocsIcon,
  Menu as MenuIcon,
} from '@mui/icons-material';
import { useNavigate, useLocation } from 'react-router-dom';
import { useRuntimeStatus } from '../hooks/useRuntimeStatus';
import StatusBar from './StatusBar';

interface LayoutProps {
  children: React.ReactNode;
}

const PRIMARY_NAV = [
  { label: 'COMMAND', path: '/command', icon: <DashboardIcon sx={{ fontSize: 14 }} /> },
  { label: 'STATE', path: '/state', icon: <StateIcon sx={{ fontSize: 14 }} /> },
  { label: 'DECISIONS', path: '/decisions', icon: <DecisionIcon sx={{ fontSize: 14 }} /> },
  { label: 'MODELS', path: '/models', icon: <ModelIcon sx={{ fontSize: 14 }} /> },
  { label: 'CAPABILITIES', path: '/capabilities', icon: <CapabilityIcon sx={{ fontSize: 14 }} /> },
  { label: 'ACTIVITY', path: '/activity', icon: <ActivityIcon sx={{ fontSize: 14 }} /> },
  { label: 'HEALTH', path: '/health', icon: <HealthIcon sx={{ fontSize: 14 }} /> },
];

const SECONDARY_NAV = [
  { label: 'Chat', path: '/chat', icon: <ChatIcon sx={{ fontSize: 13 }} /> },
  { label: 'Equipment', path: '/equipment', icon: <EquipmentIcon sx={{ fontSize: 13 }} /> },
  { label: 'Operations', path: '/operations', icon: <OperationsIcon sx={{ fontSize: 13 }} /> },
  { label: 'Safety', path: '/safety', icon: <SafetyIcon sx={{ fontSize: 13 }} /> },
  { label: 'MCP Testing', path: '/mcp-test', icon: <SettingsIcon sx={{ fontSize: 13 }} /> },
  { label: 'Docs', path: '/documentation', icon: <DocsIcon sx={{ fontSize: 13 }} /> },
];

const PIPELINE_STAGES = [
  { step: '01', label: 'OBSERVE', field: 'state_provider_available' as const },
  { step: '02', label: 'REASON', field: 'model_gateway_available' as const },
  { step: '03', label: 'PROPOSE', field: 'equipment_agent_available' as const },
  { step: '04', label: 'DECIDE', field: 'decision_engine_available' as const },
  { step: '05', label: 'EXECUTE', field: 'equipment_executor_available' as const },
  { step: '06', label: 'MCP', field: 'equipment_mcp_configured' as const },
  { step: '07', label: 'BACKEND', field: 'runtime_initialized' as const },
];

const MCP_DOMAINS = [
  { label: 'Inventory', field: 'inventory_mcp_configured' as const, port: '8765' },
  { label: 'Equipment', field: 'equipment_mcp_configured' as const, port: '8766' },
  { label: 'Labor', field: 'labor_mcp_configured' as const, port: '8767' },
  { label: 'Wave', field: 'wave_mcp_configured' as const, port: '8768' },
];

function StatusDot({ ok }: { ok: boolean | undefined }) {
  const color = ok === undefined ? '#30363D' : ok ? '#3FB950' : '#484F58';
  return (
    <Box
      sx={{
        width: 6,
        height: 6,
        borderRadius: '50%',
        backgroundColor: color,
        flexShrink: 0,
        boxShadow: ok ? `0 0 4px ${color}` : 'none',
      }}
    />
  );
}

const LeftPanel: React.FC<{ onNavigate?: () => void }> = ({ onNavigate }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const { data: runtime } = useRuntimeStatus();

  const go = (path: string) => {
    navigate(path);
    onNavigate?.();
  };

  return (
    <Box
      sx={{
        width: 200,
        backgroundColor: '#080C10',
        borderRight: '1px solid #1C2128',
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        overflowY: 'auto',
        flexShrink: 0,
        '&::-webkit-scrollbar': { width: 4 },
        '&::-webkit-scrollbar-track': { background: 'transparent' },
        '&::-webkit-scrollbar-thumb': { background: '#21262D', borderRadius: 2 },
      }}
    >
      {/* Pipeline stages */}
      <Box sx={{ p: 1.5, pb: 0.5 }}>
        <Typography
          variant="caption"
          sx={{
            color: '#484F58',
            fontFamily: 'monospace',
            fontSize: '0.65rem',
            letterSpacing: '0.1em',
            fontWeight: 700,
            textTransform: 'uppercase',
            display: 'block',
            px: 0.5,
            mb: 0.5,
          }}
        >
          AI Pipeline
        </Typography>
        {PIPELINE_STAGES.map(({ step, label, field }) => {
          const ok = runtime?.[field];
          return (
            <Box
              key={step}
              sx={{
                display: 'flex',
                alignItems: 'center',
                gap: 1,
                px: 0.75,
                py: 0.6,
                borderRadius: 0.75,
                '&:hover': { backgroundColor: '#0D1117' },
              }}
            >
              <Typography
                sx={{
                  fontFamily: 'monospace',
                  fontSize: '0.6rem',
                  color: ok ? '#76B900' : '#30363D',
                  fontWeight: 700,
                  width: 20,
                  flexShrink: 0,
                }}
              >
                {step}
              </Typography>
              <Typography
                sx={{
                  fontFamily: 'monospace',
                  fontSize: '0.72rem',
                  color: ok ? '#C9D1D9' : '#484F58',
                  fontWeight: 600,
                  letterSpacing: '0.04em',
                  flexGrow: 1,
                }}
              >
                {label}
              </Typography>
              <StatusDot ok={ok} />
            </Box>
          );
        })}
      </Box>

      <Box sx={{ mx: 1.5, my: 1, borderTop: '1px solid #1C2128' }} />

      {/* MCP domains */}
      <Box sx={{ px: 1.5, pb: 0.5 }}>
        <Typography
          variant="caption"
          sx={{
            color: '#484F58',
            fontFamily: 'monospace',
            fontSize: '0.65rem',
            letterSpacing: '0.1em',
            fontWeight: 700,
            textTransform: 'uppercase',
            display: 'block',
            px: 0.5,
            mb: 0.5,
          }}
        >
          MCP Domains
        </Typography>
        {MCP_DOMAINS.map(({ label, field, port }) => {
          const ok = runtime?.[field];
          return (
            <Box
              key={label}
              sx={{
                display: 'flex',
                alignItems: 'center',
                gap: 1,
                px: 0.75,
                py: 0.5,
                borderRadius: 0.75,
              }}
            >
              <StatusDot ok={ok} />
              <Typography sx={{ fontFamily: 'monospace', fontSize: '0.72rem', color: ok ? '#8B949E' : '#30363D', flexGrow: 1 }}>
                {label}
              </Typography>
              <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#30363D' }}>
                :{port}
              </Typography>
            </Box>
          );
        })}
      </Box>

      <Box sx={{ mx: 1.5, my: 1, borderTop: '1px solid #1C2128' }} />

      {/* Secondary nav */}
      <Box sx={{ px: 1, pb: 2 }}>
        <Typography
          variant="caption"
          sx={{
            color: '#484F58',
            fontFamily: 'monospace',
            fontSize: '0.65rem',
            letterSpacing: '0.1em',
            fontWeight: 700,
            textTransform: 'uppercase',
            display: 'block',
            px: 0.75,
            mb: 0.5,
          }}
        >
          Tools
        </Typography>
        {SECONDARY_NAV.map(({ label, path, icon }) => {
          const active = location.pathname === path;
          return (
            <Box
              key={path}
              onClick={() => go(path)}
              sx={{
                display: 'flex',
                alignItems: 'center',
                gap: 1,
                px: 0.75,
                py: 0.55,
                borderRadius: 0.75,
                cursor: 'pointer',
                borderLeft: active ? '2px solid #76B900' : '2px solid transparent',
                backgroundColor: active ? 'rgba(118,185,0,0.06)' : 'transparent',
                '&:hover': { backgroundColor: '#0D1117' },
              }}
            >
              <Box sx={{ color: active ? '#76B900' : '#484F58', display: 'flex', alignItems: 'center' }}>{icon}</Box>
              <Typography
                sx={{
                  fontSize: '0.78rem',
                  color: active ? '#E6EDF3' : '#6E7681',
                  fontWeight: active ? 600 : 400,
                }}
              >
                {label}
              </Typography>
            </Box>
          );
        })}
      </Box>
    </Box>
  );
};

const Layout: React.FC<LayoutProps> = ({ children }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100vh', backgroundColor: '#080C10', overflow: 'hidden' }}>
      {/* Top navigation bar */}
      <Box
        sx={{
          height: 44,
          minHeight: 44,
          display: 'flex',
          alignItems: 'center',
          px: 2,
          gap: 1,
          borderBottom: '1px solid #1C2128',
          backgroundColor: '#0D1117',
          flexShrink: 0,
          zIndex: 10,
        }}
      >
        {/* Mobile hamburger */}
        <IconButton
          onClick={() => setMobileOpen(true)}
          sx={{ display: { md: 'none' }, color: '#484F58', p: 0.5, mr: 0.5 }}
          size="small"
        >
          <MenuIcon sx={{ fontSize: 18 }} />
        </IconButton>

        {/* Logo + brand */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mr: 2, flexShrink: 0 }}>
          <Box
            component="img"
            src="/nvidia-logo.svg"
            alt="NVIDIA"
            sx={{ height: 18, width: 'auto' }}
            onError={(e: any) => { e.target.style.display = 'none'; }}
          />
          <Box sx={{ display: { xs: 'none', sm: 'flex' }, alignItems: 'center', gap: 0.75 }}>
            <Typography
              sx={{
                fontFamily: 'monospace',
                fontWeight: 700,
                fontSize: '0.75rem',
                color: '#76B900',
                letterSpacing: '0.06em',
              }}
            >
              MAIW
            </Typography>
            <Typography sx={{ color: '#30363D', fontSize: '0.75rem' }}>v2</Typography>
          </Box>
        </Box>

        {/* Primary nav pills */}
        <Box sx={{ display: { xs: 'none', md: 'flex' }, alignItems: 'center', gap: 0.5, flexGrow: 1 }}>
          {PRIMARY_NAV.map(({ label, path, icon }) => {
            const active = location.pathname === path;
            return (
              <Box
                key={path}
                onClick={() => navigate(path)}
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 0.5,
                  px: 1.25,
                  py: 0.5,
                  borderRadius: '20px',
                  cursor: 'pointer',
                  border: '1px solid',
                  borderColor: active ? '#76B900' : '#21262D',
                  backgroundColor: active ? 'rgba(118,185,0,0.12)' : 'transparent',
                  transition: 'all 0.15s ease',
                  '&:hover': {
                    borderColor: active ? '#76B900' : '#30363D',
                    backgroundColor: active ? 'rgba(118,185,0,0.15)' : 'rgba(255,255,255,0.03)',
                  },
                }}
              >
                <Box sx={{ color: active ? '#76B900' : '#484F58', display: 'flex', alignItems: 'center' }}>{icon}</Box>
                <Typography
                  sx={{
                    fontFamily: 'monospace',
                    fontWeight: 700,
                    fontSize: '0.68rem',
                    letterSpacing: '0.06em',
                    color: active ? '#76B900' : '#6E7681',
                  }}
                >
                  {label}
                </Typography>
              </Box>
            );
          })}
        </Box>

        {/* Right: operator chip */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, ml: 'auto', flexShrink: 0 }}>
          <Chip
            label="OPERATOR"
            size="small"
            sx={{
              height: 22,
              backgroundColor: 'rgba(118,185,0,0.1)',
              border: '1px solid rgba(118,185,0,0.3)',
              color: '#76B900',
              fontFamily: 'monospace',
              fontWeight: 700,
              fontSize: '0.6rem',
              letterSpacing: '0.08em',
            }}
          />
        </Box>
      </Box>

      {/* Main content row */}
      <Box sx={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* Left panel — desktop */}
        <Box sx={{ display: { xs: 'none', md: 'flex' }, flexDirection: 'column', height: '100%' }}>
          <LeftPanel />
        </Box>

        {/* Mobile drawer */}
        <Drawer
          open={mobileOpen}
          onClose={() => setMobileOpen(false)}
          sx={{
            display: { xs: 'block', md: 'none' },
            '& .MuiDrawer-paper': { backgroundColor: '#080C10', border: 'none', width: 220 },
          }}
        >
          <LeftPanel onNavigate={() => setMobileOpen(false)} />
        </Drawer>

        {/* Center content */}
        <Box
          sx={{
            flex: 1,
            overflowY: 'auto',
            p: { xs: 1.5, md: 2.5 },
            pb: 5,
            '&::-webkit-scrollbar': { width: 4 },
            '&::-webkit-scrollbar-track': { background: 'transparent' },
            '&::-webkit-scrollbar-thumb': { background: '#21262D', borderRadius: 2 },
          }}
        >
          {children}
        </Box>
      </Box>

      {/* Bottom status bar */}
      <StatusBar />
    </Box>
  );
};

export default Layout;
