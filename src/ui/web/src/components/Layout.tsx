import React, { useState } from 'react';
import {
  AppBar,
  Box,
  CssBaseline,
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
  Inventory as InventoryIcon,
  Work as OperationsIcon,
  Security as SafetyIcon,
  TrendingUp as ForecastingIcon,
  Analytics as AnalyticsIcon,
  Settings as SettingsIcon,
  Article as DocumentationIcon,
  Description as DocumentIcon,
  Logout,
} from '@mui/icons-material';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

const drawerWidth = 240;

interface LayoutProps {
  children: React.ReactNode;
}

const menuItems = [
  { text: 'Dashboard', icon: <DashboardIcon />, path: '/' },
  { text: 'Chat Assistant', icon: <ChatIcon />, path: '/chat' },
  { text: 'Equipment & Assets', icon: <EquipmentIcon />, path: '/equipment' },
  { text: 'Forecasting', icon: <ForecastingIcon />, path: '/forecasting' },
  { text: 'Operations', icon: <OperationsIcon />, path: '/operations' },
  { text: 'Safety', icon: <SafetyIcon />, path: '/safety' },
  { text: 'Document Extraction', icon: <DocumentIcon />, path: '/documents' },
  { text: 'Analytics', icon: <AnalyticsIcon />, path: '/analytics' },
  { text: 'Documentation', icon: <DocumentationIcon />, path: '/documentation' },
  { text: 'MCP Testing', icon: <SettingsIcon />, path: '/mcp-test' },
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

  const drawer = (
    <div>
      <Toolbar>
        <Typography variant="h6" noWrap component="div" sx={{ fontWeight: 'bold' }}>
          Warehouse Assistant
        </Typography>
      </Toolbar>
      <List>
        {menuItems.map((item) => (
          <ListItem key={item.text} disablePadding>
            <ListItemButton
              selected={location.pathname === item.path}
              onClick={() => handleNavigation(item.path)}
              sx={{
                '&.Mui-selected': {
                  backgroundColor: theme.palette.primary.main,
                  color: 'white',
                  '&:hover': {
                    backgroundColor: theme.palette.primary.dark,
                  },
                  '& .MuiListItemIcon-root': {
                    color: 'white',
                  },
                },
              }}
            >
              <ListItemIcon>{item.icon}</ListItemIcon>
              <ListItemText primary={item.text} />
            </ListItemButton>
          </ListItem>
        ))}
      </List>
    </div>
  );

  return (
    <Box sx={{ display: 'flex' }}>
      <CssBaseline />
      <AppBar
        position="fixed"
        sx={{
          width: { md: `calc(100% - ${drawerWidth}px)` },
          ml: { md: `${drawerWidth}px` },
        }}
      >
        <Toolbar>
          <IconButton
            color="inherit"
            aria-label="open drawer"
            edge="start"
            onClick={handleDrawerToggle}
            sx={{ mr: 2, display: { md: 'none' } }}
          >
            <MenuIcon />
          </IconButton>
          <Typography variant="h6" noWrap component="div" sx={{ flexGrow: 1 }}>
            Warehouse Operational Assistant
          </Typography>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Typography variant="body2" sx={{ display: { xs: 'none', sm: 'block' } }}>
              {user?.full_name || user?.username}
            </Typography>
            <IconButton
              size="large"
              aria-label="account of current user"
              aria-controls="user-menu"
              aria-haspopup="true"
              onClick={handleUserMenuOpen}
              color="inherit"
            >
              <Avatar sx={{ width: 32, height: 32 }}>
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
              <MenuItem onClick={handleLogout}>
                <ListItemIcon>
                  <Logout fontSize="small" />
                </ListItemIcon>
                Logout
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
          p: 3,
          width: { md: `calc(100% - ${drawerWidth}px)` },
        }}
      >
        <Toolbar />
        {children}
      </Box>
    </Box>
  );
};

export default Layout;
