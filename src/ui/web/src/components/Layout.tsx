import React, { useState } from 'react';
import {
  AppBar,
  Box,
  CssBaseline,
  Divider,
  Drawer,
  IconButton,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Toolbar,
  Typography,
  useTheme,
  useMediaQuery,
  Menu,
  MenuItem,
  Avatar,
} from '@mui/material';
import {
  Menu as MenuIcon,
  Dashboard as DashboardIcon,
  Chat as ChatIcon,
  Build as EquipmentIcon,
  Work as OperationsIcon,
  Security as SafetyIcon,
  Analytics as AnalyticsIcon,
  Settings as SettingsIcon,
  Article as DocumentationIcon,
  Logout,
  Inventory2 as StateIcon,
  Gavel as DecisionIcon,
  Psychology as ModelIcon,
  Hub as CapabilityIcon,
  Timeline as ActivityIcon,
  MonitorHeart as HealthIcon,
} from '@mui/icons-material';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import StatusBar from './StatusBar';

const drawerWidth = 240;

interface LayoutProps {
  children: React.ReactNode;
}

const primaryNavItems = [
  { text: 'COMMAND', icon: <DashboardIcon />, path: '/command' },
  { text: 'STATE', icon: <StateIcon />, path: '/state' },
  { text: 'DECISIONS', icon: <DecisionIcon />, path: '/decisions' },
  { text: 'MODELS', icon: <ModelIcon />, path: '/models' },
  { text: 'CAPABILITIES', icon: <CapabilityIcon />, path: '/capabilities' },
  { text: 'ACTIVITY', icon: <ActivityIcon />, path: '/activity' },
  { text: 'HEALTH', icon: <HealthIcon />, path: '/health' },
];

const secondaryNavItems = [
  { text: 'Chat Assistant', icon: <ChatIcon />, path: '/chat' },
  { text: 'Equipment & Assets', icon: <EquipmentIcon />, path: '/equipment' },
  { text: 'Operations', icon: <OperationsIcon />, path: '/operations' },
  { text: 'Safety', icon: <SafetyIcon />, path: '/safety' },
  { text: 'Analytics', icon: <AnalyticsIcon />, path: '/analytics' },
  { text: 'MCP Testing', icon: <SettingsIcon />, path: '/mcp-test' },
  { text: 'Documentation', icon: <DocumentationIcon />, path: '/documentation' },
];

const Layout: React.FC<LayoutProps> = ({ children }) => {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
  const navigate = useNavigate();
  const location = useLocation();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const { user, logout } = useAuth();

  const handleDrawerToggle = () => {
    setMobileOpen(!mobileOpen);
  };

  const handleNavigation = (path: string) => {
    navigate(path);
    if (isMobile) {
      setMobileOpen(false);
    }
  };

  const handleUserMenuOpen = (event: React.MouseEvent<HTMLElement>) => {
    setAnchorEl(event.currentTarget);
  };

  const handleUserMenuClose = () => {
    setAnchorEl(null);
  };

  const handleLogout = () => {
    logout();
    navigate('/login');
    handleUserMenuClose();
  };

  const navItemSx = (path: string, mono = false) => ({
    mx: 1,
    borderRadius: 2,
    minHeight: 40,
    transition: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
    '&.Mui-selected': {
      backgroundColor: 'primary.main',
      color: 'primary.contrastText',
      '&:hover': { backgroundColor: 'primary.light' },
      '& .MuiListItemIcon-root': { color: 'primary.contrastText' },
    },
    '&:hover': { backgroundColor: 'rgba(118, 185, 0, 0.08)' },
    '& .MuiListItemIcon-root': {
      color: location.pathname === path ? 'primary.contrastText' : 'text.secondary',
      minWidth: 36,
    },
    '& .MuiListItemText-primary': {
      fontWeight: location.pathname === path ? 700 : 500,
      fontSize: mono ? '0.8rem' : '0.82rem',
      letterSpacing: mono ? '0.06em' : '0.01em',
      fontFamily: mono ? 'monospace' : 'inherit',
    },
  });

  const drawer = (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Toolbar sx={{
        borderBottom: '1px solid',
        borderColor: 'divider',
        minHeight: '64px !important',
        px: 2,
        flexShrink: 0,
      }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, width: '100%' }}>
          <Box
            component="img"
            src="/nvidia-logo.svg"
            alt="NVIDIA"
            sx={{ height: 22, width: 'auto', display: { xs: 'none', sm: 'block' } }}
            onError={(e: any) => { e.target.style.display = 'none'; }}
          />
          <Box>
            <Typography variant="body2" sx={{ fontWeight: 700, color: 'primary.main', fontFamily: 'monospace', fontSize: '0.7rem', letterSpacing: '0.08em' }}>
              MAIW v2
            </Typography>
            <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.65rem' }}>
              Command Center
            </Typography>
          </Box>
        </Box>
      </Toolbar>

      {/* Primary nav */}
      <List sx={{ pt: 1.5, flexShrink: 0 }}>
        {primaryNavItems.map((item) => (
          <ListItem key={item.text} disablePadding sx={{ mb: 0.25 }}>
            <ListItemButton
              selected={location.pathname === item.path}
              onClick={() => handleNavigation(item.path)}
              sx={navItemSx(item.path, true)}
            >
              <ListItemIcon>{item.icon}</ListItemIcon>
              <ListItemText primary={item.text} />
            </ListItemButton>
          </ListItem>
        ))}
      </List>

      <Divider sx={{ mx: 2, my: 1 }} />

      {/* Secondary nav */}
      <List sx={{ flexShrink: 0 }}>
        {secondaryNavItems.map((item) => (
          <ListItem key={item.text} disablePadding sx={{ mb: 0.25 }}>
            <ListItemButton
              selected={location.pathname === item.path}
              onClick={() => handleNavigation(item.path)}
              sx={navItemSx(item.path, false)}
            >
              <ListItemIcon>{item.icon}</ListItemIcon>
              <ListItemText primary={item.text} />
            </ListItemButton>
          </ListItem>
        ))}
      </List>
    </Box>
  );

  return (
    <Box sx={{ display: 'flex' }}>
      <CssBaseline />
      <AppBar
        position="fixed"
        sx={{
          width: { md: `calc(100% - ${drawerWidth}px)` },
          ml: { md: `${drawerWidth}px` },
          backgroundColor: 'background.paper',
          borderBottom: '1px solid',
          borderColor: 'divider',
          boxShadow: '0 1px 3px rgba(0, 0, 0, 0.3)',
        }}
      >
        <Toolbar sx={{ minHeight: '64px !important', px: 3 }}>
          <IconButton
            color="inherit"
            aria-label="open drawer"
            edge="start"
            onClick={handleDrawerToggle}
            sx={{ 
              mr: 2, 
              display: { md: 'none' },
              color: 'text.primary',
            }}
          >
            <MenuIcon />
          </IconButton>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, flexGrow: 1 }}>
            <Box
              component="img"
              src="/nvlogo.png"
              alt="NVIDIA"
              sx={{
                height: 24,
                width: 'auto',
                display: { xs: 'none', sm: 'block' },
              }}
              onError={(e: any) => {
                e.target.style.display = 'none';
              }}
            />
            <Typography 
              variant="h6" 
              noWrap 
              component="div" 
              sx={{ 
                fontWeight: 600,
                fontSize: '1.125rem',
                color: 'text.primary',
                letterSpacing: '0.01em',
              }}
            >
              Multi-Agent-Intelligent-Warehouse (MAIW)
            </Typography>
          </Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
            <Typography 
              variant="body2" 
              sx={{ 
                display: { xs: 'none', sm: 'block' },
                color: 'text.secondary',
                fontSize: '0.875rem',
                fontWeight: 500,
              }}
            >
              {user?.full_name || user?.username}
            </Typography>
            <IconButton
              size="small"
              aria-label="account of current user"
              aria-controls="user-menu"
              aria-haspopup="true"
              onClick={handleUserMenuOpen}
              sx={{
                color: 'text.primary',
              }}
            >
              <Avatar 
                sx={{ 
                  width: 36, 
                  height: 36,
                  backgroundColor: 'primary.main',
                  color: 'primary.contrastText',
                  fontWeight: 600,
                  fontSize: '0.875rem',
                }}
              >
                {user?.full_name?.charAt(0) || user?.username?.charAt(0) || 'U'}
              </Avatar>
            </IconButton>
            <Menu
              id="user-menu"
              anchorEl={anchorEl}
              anchorOrigin={{
                vertical: 'top',
                horizontal: 'right',
              }}
              keepMounted
              transformOrigin={{
                vertical: 'top',
                horizontal: 'right',
              }}
              open={Boolean(anchorEl)}
              onClose={handleUserMenuClose}
            >
              <MenuItem 
                onClick={handleLogout}
              >
                <ListItemIcon>
                  <Logout fontSize="small" />
                </ListItemIcon>
                <Typography variant="body2">Logout</Typography>
              </MenuItem>
            </Menu>
          </Box>
        </Toolbar>
      </AppBar>
      <Box
        component="nav"
        sx={{ width: { md: drawerWidth }, flexShrink: { md: 0 } }}
        aria-label="mailbox folders"
      >
        <Drawer
          variant="temporary"
          open={mobileOpen}
          onClose={handleDrawerToggle}
          ModalProps={{
            keepMounted: true,
          }}
          sx={{
            display: { xs: 'block', md: 'none' },
            '& .MuiDrawer-paper': { boxSizing: 'border-box', width: drawerWidth },
          }}
        >
          {drawer}
        </Drawer>
        <Drawer
          variant="permanent"
          sx={{
            display: { xs: 'none', md: 'block' },
            '& .MuiDrawer-paper': { boxSizing: 'border-box', width: drawerWidth },
          }}
          open
        >
          {drawer}
        </Drawer>
      </Box>
      <Box
        component="main"
        sx={{
          flexGrow: 1,
          pt: 3,
          px: 3,
          display: 'flex',
          flexDirection: 'column',
          minWidth: 0,
          backgroundColor: 'background.default',
          minHeight: '100vh',
        }}
      >
        <Toolbar />
        <Box sx={{ flex: 1, width: '100%', minWidth: 0, pb: 6 }}>
          {children}
        </Box>
      </Box>
      <StatusBar />
    </Box>
  );
};

export default Layout;
