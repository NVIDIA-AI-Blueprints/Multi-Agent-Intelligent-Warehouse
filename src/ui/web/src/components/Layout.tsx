import React, { useState } from 'react';
import { Box, Typography, Drawer, IconButton } from '@mui/material';
import { Menu as MenuIcon } from '@mui/icons-material';
import { useNavigate, useLocation } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { healthAPI } from '../services/api';
import { useDemoStatus } from '../hooks/useDemoStatus';
import StatusBar from './StatusBar';

interface LayoutProps {
  children: React.ReactNode;
}

const NAV = [
  { label: 'OPERATIONS', path: '/demo' },   // Primary operator surface
  { label: 'WORLD', path: '/world' },
  { label: 'RELIABILITY', path: '/command' }, // Governance & system overview
  { label: 'MODELS', path: '/models' },
  { label: 'CAPABILITIES', path: '/capabilities' },
  { label: 'ACTIVITY', path: '/activity' },
];

const WAREHOUSE_ID = process.env.REACT_APP_WAREHOUSE_ID || 'DC-47';

const Layout: React.FC<LayoutProps> = ({ children }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);

  const { data: live } = useQuery({
    queryKey: ['live'],
    queryFn: healthAPI.getLive,
    refetchInterval: 15000,
    retry: 0,
    staleTime: 10000,
  });
  const isLive = live?.status === 'alive';

  // Demo mode detection — threaded from backend status so all pages show the indicator
  const { isDemoMode } = useDemoStatus();

  const NavItems = () => (
    <>
      {NAV.map(({ label, path }) => {
        const active = location.pathname.startsWith(path);
        return (
          <Box
            key={path}
            onClick={() => { navigate(path); setMobileOpen(false); }}
            sx={{
              px: { xs: 1.5, md: 2 },
              py: 0.5,
              cursor: 'pointer',
              position: 'relative',
              color: active ? '#E6EDF3' : '#484F58',
              fontFamily: 'monospace',
              fontWeight: active ? 700 : 500,
              fontSize: '0.72rem',
              letterSpacing: '0.07em',
              textTransform: 'uppercase',
              whiteSpace: 'nowrap',
              transition: 'color 0.15s',
              '&:hover': { color: active ? '#E6EDF3' : '#8B949E' },
              '&::after': active ? {
                content: '""',
                position: 'absolute',
                bottom: 0,
                left: 0,
                right: 0,
                height: '2px',
                backgroundColor: '#76B900',
              } : {},
            }}
          >
            {label}
          </Box>
        );
      })}
    </>
  );

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100vh', width: '100%', backgroundColor: '#080C10', overflow: 'hidden' }}>

      {/* Top bar */}
      <Box
        sx={{
          height: 48,
          minHeight: 48,
          display: 'flex',
          alignItems: 'stretch',
          borderBottom: '1px solid #1C2128',
          backgroundColor: '#0D1117',
          flexShrink: 0,
          px: 2,
          gap: 0,
        }}
      >
        {/* Brand */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, pr: 3, borderRight: '1px solid #1C2128', mr: 2, flexShrink: 0 }}>
          <Box
            component="img"
            src="/nvidia-logo.svg"
            alt="NVIDIA"
            sx={{ height: 16, width: 'auto' }}
            onError={(e: any) => { e.target.style.display = 'none'; }}
          />
          <Typography component="h1" sx={{ fontFamily: 'monospace', fontWeight: 700, fontSize: '0.75rem', color: '#E6EDF3', letterSpacing: '0.04em', whiteSpace: 'nowrap' }}>
            MAIW OPERATIONS
          </Typography>
        </Box>

        {/* LIVE indicator */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, pr: 2.5, borderRight: '1px solid #1C2128', mr: 2, flexShrink: 0 }}>
          <Box sx={{
            width: 7, height: 7, borderRadius: '50%',
            backgroundColor: isLive ? '#3FB950' : '#484F58',
            boxShadow: isLive ? '0 0 6px #3FB950' : 'none',
            animation: isLive ? 'livePulse 2s ease-in-out infinite' : 'none',
            '@keyframes livePulse': { '0%,100%': { opacity: 1 }, '50%': { opacity: 0.5 } },
          }} />
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.67rem', fontWeight: 700, color: isLive ? '#3FB950' : '#484F58', letterSpacing: '0.06em' }}>
            {isLive ? 'LIVE' : 'OFFLINE'}
          </Typography>
        </Box>

        {/* Warehouse ID */}
        <Box sx={{ display: { xs: 'none', sm: 'flex' }, alignItems: 'center', pr: 2.5, borderRight: '1px solid #1C2128', mr: 2, flexShrink: 0 }}>
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.67rem', color: '#8B949E', letterSpacing: '0.04em' }}>
            WAREHOUSE: <Box component="span" sx={{ color: '#C9D1D9', fontWeight: 700 }}>{WAREHOUSE_ID}</Box>
          </Typography>
        </Box>

        {/* Demo mode indicator — visible across all pages during synthetic warehouse sessions */}
        {isDemoMode && (
          <Box
            data-testid="demo-mode-indicator"
            sx={{
              display: { xs: 'none', sm: 'flex' },
              alignItems: 'center',
              px: 1.25, py: 0,
              mr: 2,
              borderRight: '1px solid #1C2128',
            }}
          >
            <Box sx={{
              background: '#0d2146',
              border: '1px solid #1F3458',
              borderRadius: '3px',
              px: '6px', py: '2px',
              fontFamily: 'monospace', fontSize: '0.6rem',
              color: '#58A6FF', letterSpacing: '0.08em',
              textTransform: 'uppercase',
              whiteSpace: 'nowrap',
            }}>
              SIMULATED WAREHOUSE
            </Box>
          </Box>
        )}

        {/* Desktop nav */}
        <Box sx={{ display: { xs: 'none', md: 'flex' }, alignItems: 'stretch', gap: 0 }}>
          <NavItems />
        </Box>

        {/* Right spacer + mobile hamburger */}
        <Box sx={{ flexGrow: 1 }} />
        <IconButton
          onClick={() => setMobileOpen(true)}
          sx={{ display: { md: 'none' }, color: '#484F58', p: 0.5 }}
          size="small"
        >
          <MenuIcon sx={{ fontSize: 18 }} />
        </IconButton>
      </Box>

      {/* Mobile nav drawer */}
      <Drawer
        open={mobileOpen}
        onClose={() => setMobileOpen(false)}
        sx={{ '& .MuiDrawer-paper': { backgroundColor: '#0D1117', borderRight: '1px solid #1C2128', width: 200, pt: 2 } }}
      >
        <Box sx={{ display: 'flex', flexDirection: 'column' }}>
          <NavItems />
        </Box>
      </Drawer>

      {/* Content */}
      <Box
        sx={{
          flex: 1,
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {children}
      </Box>

      <StatusBar />
    </Box>
  );
};

export default Layout;
