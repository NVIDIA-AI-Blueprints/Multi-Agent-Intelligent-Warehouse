import React, { useState } from 'react';
import { Box, Typography, Drawer, IconButton } from '@mui/material';
import { Menu as MenuIcon } from '@mui/icons-material';
import { useNavigate, useLocation } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { healthAPI } from '../services/api';
import StatusBar from './StatusBar';

interface LayoutProps {
  children: React.ReactNode;
}

const NAV = [
  { label: 'COMMAND', path: '/command' },
  { label: 'STATE', path: '/state' },
  { label: 'DECISIONS', path: '/decisions' },
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
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100vh', backgroundColor: '#080C10', overflow: 'hidden' }}>

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
          <Typography sx={{ fontFamily: 'monospace', fontWeight: 700, fontSize: '0.75rem', color: '#E6EDF3', letterSpacing: '0.04em', whiteSpace: 'nowrap' }}>
            MAIW COMMAND CENTER
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
