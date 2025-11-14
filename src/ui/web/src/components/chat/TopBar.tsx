import React from 'react';
import {
  AppBar,
  Toolbar,
  Typography,
  Select,
  MenuItem,
  Chip,
  Box,
  IconButton,
  Tooltip,
} from '@mui/material';
import {
  Settings as SettingsIcon,
  Wifi as WifiIcon,
  WifiOff as WifiOffIcon,
} from '@mui/icons-material';

interface TopBarProps {
  warehouse: string;
  role: string;
  environment: string;
  connections: {
    nim: boolean;
    db: boolean;
    milvus: boolean;
    kafka: boolean;
  };
  onWarehouseChange: (warehouse: string) => void;
  onRoleChange: (role: string) => void;
  onEnvironmentChange: (env: string) => void;
}

const TopBar: React.FC<TopBarProps> = ({
  warehouse,
  role,
  environment,
  connections,
  onWarehouseChange,
  onRoleChange,
  onEnvironmentChange,
}) => {
  const getConnectionIcon = (connected: boolean) => {
    return connected ? <WifiIcon /> : <WifiOffIcon />;
  };

  return (
    <AppBar 
      position="static" 
      sx={{ 
        backgroundColor: '#000000',
        borderBottom: '1px solid #333333',
        boxShadow: 'none',
      }}
    >
      <Toolbar sx={{ minHeight: '48px !important', gap: 2 }}>
        {/* Warehouse Selector */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Typography variant="body2" sx={{ color: '#ffffff', minWidth: '80px' }}>
            Warehouse:
          </Typography>
          <Select
            value={warehouse}
            onChange={(e) => onWarehouseChange(e.target.value)}
            size="small"
            sx={{
              color: '#ffffff',
              '& .MuiOutlinedInput-notchedOutline': {
                borderColor: '#76B900',
              },
              '& .MuiSvgIcon-root': {
                color: '#76B900',
              },
              minWidth: 120,
            }}
          >
            <MenuItem value="WH-01">WH-01</MenuItem>
            <MenuItem value="WH-02">WH-02</MenuItem>
            <MenuItem value="WH-03">WH-03</MenuItem>
          </Select>
        </Box>

        {/* Role Selector */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Typography variant="body2" sx={{ color: '#ffffff', minWidth: '50px' }}>
            Role:
          </Typography>
          <Select
            value={role}
            onChange={(e) => onRoleChange(e.target.value)}
            size="small"
            sx={{
              color: '#ffffff',
              '& .MuiOutlinedInput-notchedOutline': {
                borderColor: '#76B900',
              },
              '& .MuiSvgIcon-root': {
                color: '#76B900',
              },
              minWidth: 120,
            }}
          >
            <MenuItem value="operator">Operator</MenuItem>
            <MenuItem value="supervisor">Supervisor</MenuItem>
            <MenuItem value="manager">Manager</MenuItem>
            <MenuItem value="admin">Admin</MenuItem>
          </Select>
        </Box>

        {/* Environment */}
        <Chip
          label={environment}
          size="small"
          sx={{
            backgroundColor: environment === 'Prod' ? '#f44336' : '#76B900',
            color: '#ffffff',
            fontWeight: 'bold',
          }}
        />

        {/* Connection Health */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, ml: 'auto' }}>
          <Tooltip title="NIM Connection">
            <IconButton size="small">
              {getConnectionIcon(connections.nim)}
            </IconButton>
          </Tooltip>
          <Tooltip title="Database Connection">
            <IconButton size="small">
              {getConnectionIcon(connections.db)}
            </IconButton>
          </Tooltip>
          <Tooltip title="Milvus Connection">
            <IconButton size="small">
              {getConnectionIcon(connections.milvus)}
            </IconButton>
          </Tooltip>
          <Tooltip title="Kafka Connection">
            <IconButton size="small">
              {getConnectionIcon(connections.kafka)}
            </IconButton>
          </Tooltip>
        </Box>

        {/* Time Window */}
        <Typography variant="body2" sx={{ color: '#ffffff', minWidth: '100px' }}>
          {new Date().toLocaleTimeString()}
        </Typography>

        {/* Settings */}
        <IconButton size="small" sx={{ color: '#76B900' }}>
          <SettingsIcon />
        </IconButton>
      </Toolbar>
    </AppBar>
  );
};

export default TopBar;
