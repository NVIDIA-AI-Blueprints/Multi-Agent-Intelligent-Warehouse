import React from 'react';
import {
  Box,
  Typography,
  Paper,
  Grid,
  Card,
  CardContent,
} from '@mui/material';
import {
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
} from 'recharts';
import { useQuery } from 'react-query';
import { equipmentAPI, safetyAPI } from '../services/api';

const Analytics: React.FC = () => {
  const { data: equipmentAssets } = useQuery('equipment', equipmentAPI.getAllAssets);
  const { data: incidents } = useQuery('incidents', safetyAPI.getIncidents);

  // Equipment assets data processing
  const equipmentTrendData = React.useMemo(() => {
    if (!equipmentAssets) return [];
    
    // Group equipment by type
    const equipmentByType = equipmentAssets.reduce((acc, asset) => {
      const type = asset.type || 'Unknown';
      if (!acc[type]) {
        acc[type] = 0;
      }
      acc[type]++;
      return acc;
    }, {} as Record<string, number>);

    // Convert to chart data format
    return Object.entries(equipmentByType).map(([type, count]) => ({
      type,
      count,
      percentage: ((count / equipmentAssets.length) * 100).toFixed(1)
    }));
  }, [equipmentAssets]);

  // Equipment status distribution
  const equipmentStatusData = React.useMemo(() => {
    if (!equipmentAssets) return [];
    
    const statusCounts = equipmentAssets.reduce((acc, asset) => {
      const status = asset.status || 'Unknown';
      if (!acc[status]) {
        acc[status] = 0;
      }
      acc[status]++;
      return acc;
    }, {} as Record<string, number>);

    return Object.entries(statusCounts).map(([status, count]) => ({
      status,
      count,
      percentage: ((count / equipmentAssets.length) * 100).toFixed(1)
    }));
  }, [equipmentAssets]);


  const incidentSeverityData = [
    { severity: 'Low', count: incidents?.filter(i => i.severity === 'low').length || 0 },
    { severity: 'Medium', count: incidents?.filter(i => i.severity === 'medium').length || 0 },
    { severity: 'High', count: incidents?.filter(i => i.severity === 'high').length || 0 },
    { severity: 'Critical', count: incidents?.filter(i => i.severity === 'critical').length || 0 },
  ];

  const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042'];

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Analytics Dashboard
      </Typography>

      <Grid container spacing={3}>
        {/* Equipment Assets by Type */}
        <Grid item xs={12} md={8}>
          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" gutterBottom>
              Equipment Assets by Type
            </Typography>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={equipmentTrendData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="type" />
                <YAxis />
                <Tooltip 
                  formatter={(value, name) => [value, 'Count']}
                  labelFormatter={(label) => `Type: ${label}`}
                />
                <Legend />
                <Bar dataKey="count" fill="#8884d8" name="Equipment Count" />
              </BarChart>
            </ResponsiveContainer>
          </Paper>
        </Grid>

        {/* Equipment Status Distribution */}
        <Grid item xs={12} md={4}>
          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" gutterBottom>
              Equipment Status
            </Typography>
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={equipmentStatusData}
                  cx="50%"
                  cy="50%"
                  labelLine={false}
                  label={({ status, percent }) => `${status} ${(percent * 100).toFixed(0)}%`}
                  outerRadius={80}
                  fill="#8884d8"
                  dataKey="count"
                >
                  {equipmentStatusData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </Paper>
        </Grid>

        {/* Equipment Type Breakdown */}
        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" gutterBottom>
              Equipment Type Breakdown
            </Typography>
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={equipmentTrendData}
                  cx="50%"
                  cy="50%"
                  labelLine={false}
                  label={({ type, percent }) => `${type} ${(percent * 100).toFixed(0)}%`}
                  outerRadius={80}
                  fill="#8884d8"
                  dataKey="count"
                >
                  {equipmentTrendData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </Paper>
        </Grid>

        {/* Incident Severity */}
        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" gutterBottom>
              Incident Severity Distribution
            </Typography>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={incidentSeverityData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="severity" />
                <YAxis />
                <Tooltip />
                <Bar dataKey="count" fill="#8884d8" />
              </BarChart>
            </ResponsiveContainer>
          </Paper>
        </Grid>

        {/* Equipment Key Metrics */}
        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" gutterBottom>
              Equipment Key Metrics
            </Typography>
            <Grid container spacing={2}>
              <Grid item xs={6}>
                <Card>
                  <CardContent>
                    <Typography color="textSecondary" gutterBottom>
                      Total Equipment Assets
                    </Typography>
                    <Typography variant="h4">
                      {equipmentAssets?.length || 0}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={6}>
                <Card>
                  <CardContent>
                    <Typography color="textSecondary" gutterBottom>
                      Available Equipment
                    </Typography>
                    <Typography variant="h4">
                      {equipmentAssets?.filter(asset => asset.status === 'available').length || 0}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={6}>
                <Card>
                  <CardContent>
                    <Typography color="textSecondary" gutterBottom>
                      Assigned Equipment
                    </Typography>
                    <Typography variant="h4">
                      {equipmentAssets?.filter(asset => asset.status === 'assigned').length || 0}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={6}>
                <Card>
                  <CardContent>
                    <Typography color="textSecondary" gutterBottom>
                      Maintenance Needed
                    </Typography>
                    <Typography variant="h4">
                      {equipmentAssets?.filter(asset => 
                        asset.status === 'maintenance' || 
                        (asset.next_pm_due && new Date(asset.next_pm_due) <= new Date())
                      ).length || 0}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          </Paper>
        </Grid>
      </Grid>
    </Box>
  );
};

export default Analytics;
