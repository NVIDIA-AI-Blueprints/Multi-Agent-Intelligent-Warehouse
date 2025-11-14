import React from 'react';
import {
  Box,
  Grid,
  Paper,
  Typography,
  Card,
  CardContent,
  Chip,
} from '@mui/material';
import {
  Build as EquipmentIcon,
  Work as OperationsIcon,
  Security as SafetyIcon,
} from '@mui/icons-material';
import { useQuery } from 'react-query';
import { healthAPI, equipmentAPI, operationsAPI, safetyAPI } from '../services/api';

const Dashboard: React.FC = () => {
  const { data: healthStatus } = useQuery('health', healthAPI.check);
  const { data: equipmentAssets } = useQuery('equipment', equipmentAPI.getAllAssets);
  const { data: tasks } = useQuery('tasks', operationsAPI.getTasks);
  const { data: incidents } = useQuery('incidents', safetyAPI.getIncidents);

  // For equipment assets, we'll show assets that need maintenance instead of low stock
  const maintenanceNeeded = equipmentAssets?.filter(asset => 
    asset.status === 'maintenance' || 
    (asset.next_pm_due && new Date(asset.next_pm_due) <= new Date())
  ) || [];
  const pendingTasks = tasks?.filter(task => task.status === 'pending') || [];
  const recentIncidents = incidents?.slice(0, 5) || [];

  const stats = [
    {
      title: 'Total Equipment Assets',
      value: equipmentAssets?.length || 0,
      icon: <EquipmentIcon />,
      color: 'primary',
    },
    {
      title: 'Maintenance Needed',
      value: maintenanceNeeded.length,
      icon: <EquipmentIcon />,
      color: 'warning',
    },
    {
      title: 'Pending Tasks',
      value: pendingTasks.length,
      icon: <OperationsIcon />,
      color: 'info',
    },
    {
      title: 'Recent Incidents',
      value: recentIncidents.length,
      icon: <SafetyIcon />,
      color: 'error',
    },
  ];

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Dashboard
      </Typography>
      
      {/* System Status */}
      <Paper sx={{ p: 2, mb: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <Typography variant="h6">System Status</Typography>
          <Chip
            label={healthStatus?.ok ? 'Online' : 'Offline'}
            color={healthStatus?.ok ? 'success' : 'error'}
            variant="outlined"
          />
        </Box>
      </Paper>

      {/* Statistics Cards */}
      <Grid container spacing={3} sx={{ mb: 3 }}>
        {stats.map((stat, index) => (
          <Grid item xs={12} sm={6} md={3} key={index}>
            <Card>
              <CardContent>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                  <Box sx={{ color: `${stat.color}.main` }}>
                    {stat.icon}
                  </Box>
                  <Box>
                    <Typography variant="h4" component="div">
                      {stat.value}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {stat.title}
                    </Typography>
                  </Box>
                </Box>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>

      <Grid container spacing={3}>
        {/* Equipment Maintenance Needed */}
        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" gutterBottom>
              Equipment Maintenance Needed
            </Typography>
            {maintenanceNeeded.length > 0 ? (
              <Box>
                {maintenanceNeeded.map((asset) => (
                  <Box key={asset.asset_id} sx={{ mb: 2 }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Typography variant="body1">{asset.asset_id} - {asset.type}</Typography>
                      <Chip 
                        label={asset.status} 
                        color={asset.status === 'maintenance' ? 'error' : 'warning'} 
                        size="small" 
                      />
                    </Box>
                    <Typography variant="body2" color="text.secondary">
                      Model: {asset.model || 'N/A'} | Zone: {asset.zone || 'N/A'}
                    </Typography>
                    {asset.next_pm_due && (
                      <Typography variant="body2" color="text.secondary">
                        Next PM: {new Date(asset.next_pm_due).toLocaleDateString()}
                      </Typography>
                    )}
                  </Box>
                ))}
              </Box>
            ) : (
              <Typography color="text.secondary">All equipment is in good condition</Typography>
            )}
          </Paper>
        </Grid>

        {/* Recent Tasks */}
        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" gutterBottom>
              Recent Tasks
            </Typography>
            {pendingTasks.length > 0 ? (
              <Box>
                {pendingTasks.slice(0, 5).map((task) => (
                  <Box key={task.id} sx={{ mb: 2 }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Typography variant="body1">{task.kind}</Typography>
                      <Chip label={task.status} color="info" size="small" />
                    </Box>
                    <Typography variant="body2" color="text.secondary">
                      Assignee: {task.assignee || 'Unassigned'}
                    </Typography>
                  </Box>
                ))}
              </Box>
            ) : (
              <Typography color="text.secondary">No pending tasks</Typography>
            )}
          </Paper>
        </Grid>

        {/* Recent Incidents */}
        <Grid item xs={12}>
          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" gutterBottom>
              Recent Safety Incidents
            </Typography>
            {recentIncidents.length > 0 ? (
              <Box>
                {recentIncidents.map((incident) => (
                  <Box key={incident.id} sx={{ mb: 2 }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Typography variant="body1">{incident.description}</Typography>
                      <Chip label={incident.severity} color="error" size="small" />
                    </Box>
                    <Typography variant="body2" color="text.secondary">
                      Reported by: {incident.reported_by} | {new Date(incident.occurred_at).toLocaleDateString()}
                    </Typography>
                  </Box>
                ))}
              </Box>
            ) : (
              <Typography color="text.secondary">No recent incidents</Typography>
            )}
          </Paper>
        </Grid>
      </Grid>
    </Box>
  );
};

export default Dashboard;
