import React, { useState } from 'react';
import {
  Box,
  Typography,
  Paper,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Grid,
  Chip,
  Alert,
  Card,
  CardContent,
  Tabs,
  Tab,
  List,
  ListItem,
  ListItemText,
  IconButton,
  Tooltip,
  CircularProgress,
  Drawer,
  Divider,
  LinearProgress,
  Stack,
} from '@mui/material';
import { DataGrid, GridColDef } from '@mui/x-data-grid';
import {
  Add as AddIcon,
  Edit as EditIcon,
  Assignment as AssignmentIcon,
  Build as BuildIcon,
  Security as SecurityIcon,
  TrendingUp as TrendingUpIcon,
  Visibility as VisibilityIcon,
  Close as CloseIcon,
  CalendarToday as CalendarIcon,
  Factory as FactoryIcon,
  Settings as SettingsIcon,
  BatteryChargingFull as BatteryIcon,
  Speed as SpeedIcon,
  LocationOn as LocationIcon,
  Person as PersonIcon,
  CheckCircle as CheckCircleIcon,
  Warning as WarningIcon,
  Info as InfoIcon,
} from '@mui/icons-material';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, Legend, ResponsiveContainer } from 'recharts';
import { useQuery, useMutation, useQueryClient } from 'react-query';
import { equipmentAPI, EquipmentAsset } from '../services/api';

interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

function TabPanel(props: TabPanelProps) {
  const { children, value, index, ...other } = props;

  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`equipment-tabpanel-${index}`}
      aria-labelledby={`equipment-tab-${index}`}
      style={{ width: '100%' }}
      {...other}
    >
      {value === index && <Box sx={{ width: '100%' }}>{children}</Box>}
    </div>
  );
}

const EquipmentNew: React.FC = () => {
  const [open, setOpen] = useState(false);
  const [selectedAsset, setSelectedAsset] = useState<EquipmentAsset | null>(null);
  const [formData, setFormData] = useState<Partial<EquipmentAsset>>({});
  const [activeTab, setActiveTab] = useState(0);
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerAssetId, setDrawerAssetId] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const { data: equipmentAssets, isLoading, error } = useQuery(
    'equipment',
    equipmentAPI.getAllAssets
  );

  const { data: assignments } = useQuery(
    'equipment-assignments',
    () => equipmentAPI.getAssignments(undefined, undefined, true),
    { enabled: activeTab === 1 }
  );

  const { data: maintenanceSchedule } = useQuery(
    'equipment-maintenance',
    () => equipmentAPI.getMaintenanceSchedule(undefined, undefined, 30),
    { enabled: activeTab === 2 }
  );

  const { data: telemetryData, isLoading: telemetryLoading } = useQuery(
    ['equipment-telemetry', selectedAssetId],
    () => selectedAssetId ? equipmentAPI.getTelemetry(selectedAssetId, undefined, 168) : [],
    { enabled: !!selectedAssetId && activeTab === 3 }
  );

  // Fetch detailed asset data for drawer
  const { data: drawerAsset, isLoading: drawerAssetLoading } = useQuery(
    ['equipment-asset-detail', drawerAssetId],
    () => drawerAssetId ? equipmentAPI.getAsset(drawerAssetId) : null,
    { enabled: !!drawerAssetId }
  );

  // Fetch telemetry for drawer
  const { data: drawerTelemetryRaw, isLoading: drawerTelemetryLoading } = useQuery(
    ['equipment-telemetry-drawer', drawerAssetId],
    () => drawerAssetId ? equipmentAPI.getTelemetry(drawerAssetId, undefined, 168) : [],
    { enabled: !!drawerAssetId && drawerOpen }
  );

  // Transform telemetry data for chart
  const drawerTelemetry = React.useMemo(() => {
    if (!drawerTelemetryRaw || !Array.isArray(drawerTelemetryRaw) || drawerTelemetryRaw.length === 0) return [];
    
    // Group by timestamp and aggregate metrics
    const grouped: Record<string, Record<string, any>> = {};
    drawerTelemetryRaw.forEach((item: any) => {
      const timestamp = item.timestamp || item.ts;
      if (!timestamp) return;
      
      const timeKey = new Date(timestamp).toISOString();
      if (!grouped[timeKey]) {
        grouped[timeKey] = { timestamp: new Date(timestamp).getTime(), timeLabel: new Date(timestamp).toLocaleString() };
      }
      const metricName = item.metric || 'value';
      grouped[timeKey][metricName] = item.value;
    });
    
    return Object.values(grouped).sort((a: any, b: any) => a.timestamp - b.timestamp);
  }, [drawerTelemetryRaw]);

  // Get unique metrics for chart lines
  const telemetryMetrics = React.useMemo(() => {
    if (!drawerTelemetryRaw || !Array.isArray(drawerTelemetryRaw)) return [];
    return Array.from(new Set(drawerTelemetryRaw.map((item: any) => item.metric).filter(Boolean)));
  }, [drawerTelemetryRaw]);

  // Fetch maintenance schedule for drawer
  const { data: drawerMaintenance, isLoading: drawerMaintenanceLoading } = useQuery(
    ['equipment-maintenance-drawer', drawerAssetId],
    () => drawerAssetId ? equipmentAPI.getMaintenanceSchedule(drawerAssetId, undefined, 90) : [],
    { enabled: !!drawerAssetId && drawerOpen }
  );

  const assignMutation = useMutation(equipmentAPI.assignAsset, {
    onSuccess: () => {
      queryClient.invalidateQueries('equipment-assignments');
      setOpen(false);
    },
  });

  const releaseMutation = useMutation(equipmentAPI.releaseAsset, {
    onSuccess: () => {
      queryClient.invalidateQueries('equipment-assignments');
      queryClient.invalidateQueries('equipment');
    },
  });

  const maintenanceMutation = useMutation(equipmentAPI.scheduleMaintenance, {
    onSuccess: () => {
      queryClient.invalidateQueries('equipment-maintenance');
      setOpen(false);
    },
  });

  const handleOpen = (asset?: EquipmentAsset) => {
    if (asset) {
      setSelectedAsset(asset);
      setFormData(asset);
    } else {
      setSelectedAsset(null);
      setFormData({});
    }
    setOpen(true);
  };

  const handleClose = () => {
    setOpen(false);
    setSelectedAsset(null);
    setFormData({});
  };

  const handleAssign = () => {
    if (selectedAsset) {
      assignMutation.mutate({
        asset_id: selectedAsset.asset_id,
        assignee: formData.owner_user || 'system',
        assignment_type: 'task',
        notes: 'Manual assignment from UI',
      });
    }
  };

  const handleRelease = (assetId: string) => {
    releaseMutation.mutate({
      asset_id: assetId,
      released_by: 'system',
      notes: 'Manual release from UI',
    });
  };

  const handleScheduleMaintenance = () => {
    if (selectedAsset) {
      maintenanceMutation.mutate({
        asset_id: selectedAsset.asset_id,
        maintenance_type: 'preventive',
        description: formData.metadata?.maintenance_description || 'Scheduled maintenance',
        scheduled_by: 'system',
        scheduled_for: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString(),
        estimated_duration_minutes: 60,
        priority: 'medium',
      });
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'available': return 'success';
      case 'assigned': return 'info';
      case 'charging': return 'warning';
      case 'maintenance': return 'error';
      case 'out_of_service': return 'error';
      default: return 'default';
    }
  };

  const getTypeIcon = (type: string) => {
    switch (type) {
      case 'forklift': return '🚛';
      case 'amr': return '🤖';
      case 'agv': return '🚚';
      case 'scanner': return '📱';
      case 'charger': return '🔌';
      case 'conveyor': return '📦';
      case 'humanoid': return '👤';
      default: return '⚙️';
    }
  };

  const handleAssetClick = (assetId: string) => {
    setDrawerAssetId(assetId);
    setDrawerOpen(true);
  };

  const handleDrawerClose = () => {
    setDrawerOpen(false);
    setDrawerAssetId(null);
  };

  const columns: GridColDef[] = [
    { 
      field: 'asset_id', 
      headerName: 'Asset ID', 
      width: 150,
      renderCell: (params) => (
        <Box 
          sx={{ 
            display: 'flex', 
            alignItems: 'center', 
            gap: 1,
            cursor: 'pointer',
            '&:hover': {
              textDecoration: 'underline',
              color: 'primary.main',
            }
          }}
          onClick={() => handleAssetClick(params.value)}
        >
          <span>{getTypeIcon(params.row.type)}</span>
          <Typography variant="body2" sx={{ fontWeight: 'bold' }}>
            {params.value}
          </Typography>
        </Box>
      ),
    },
    { field: 'type', headerName: 'Type', width: 120 },
    { field: 'model', headerName: 'Model', flex: 1, minWidth: 200 },
    { field: 'zone', headerName: 'Zone', width: 120 },
    {
      field: 'status',
      headerName: 'Status',
      width: 140,
      renderCell: (params) => (
        <Chip
          label={params.value}
          color={getStatusColor(params.value) as any}
          size="small"
        />
      ),
    },
    { field: 'owner_user', headerName: 'Assigned To', flex: 1, minWidth: 150 },
    {
      field: 'next_pm_due',
      headerName: 'Next PM',
      width: 140,
      renderCell: (params) => 
        params.value ? new Date(params.value).toLocaleDateString() : 'N/A',
    },
    {
      field: 'actions',
      headerName: 'Actions',
      width: 150,
      renderCell: (params) => (
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Tooltip title="View Details">
            <IconButton
              size="small"
              onClick={() => {
                setSelectedAssetId(params.row.asset_id);
                setActiveTab(3);
              }}
            >
              <VisibilityIcon />
            </IconButton>
          </Tooltip>
          <Tooltip title="Edit">
            <IconButton
              size="small"
              onClick={() => handleOpen(params.row)}
            >
              <EditIcon />
            </IconButton>
          </Tooltip>
        </Box>
      ),
    },
  ];

  if (error) {
    return (
      <Box>
        <Typography variant="h4" gutterBottom>
          Equipment & Asset Operations
        </Typography>
        <Alert severity="error">
          Failed to load equipment data. Please try again.
        </Alert>
      </Box>
    );
  }

  return (
    <Box sx={{ width: '100%', maxWidth: 'none', p: 3 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h4" gutterBottom>
          Equipment & Asset Operations
        </Typography>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={() => handleOpen()}
          sx={{ backgroundColor: '#76B900', '&:hover': { backgroundColor: '#5a8f00' } }}
        >
          Add Asset
        </Button>
      </Box>

      {/* Tabs */}
      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <Tabs
          value={activeTab}
          onChange={(_, newValue) => {
            setActiveTab(newValue);
            // Auto-select first asset when switching to Telemetry tab if none selected
            if (newValue === 3 && !selectedAssetId && equipmentAssets && equipmentAssets.length > 0) {
              setSelectedAssetId(equipmentAssets[0].asset_id);
            }
          }}
        >
          <Tab label="Assets" icon={<BuildIcon />} />
          <Tab label="Assignments" icon={<AssignmentIcon />} />
          <Tab label="Maintenance" icon={<SecurityIcon />} />
          <Tab label="Telemetry" icon={<TrendingUpIcon />} />
        </Tabs>
      </Box>

      {/* Assets Tab */}
      <TabPanel value={activeTab} index={0}>
        <Paper sx={{ height: 600, width: '100%' }}>
          <DataGrid
            rows={equipmentAssets || []}
            columns={columns}
            loading={isLoading}
            pageSize={10}
            rowsPerPageOptions={[10, 25, 50]}
            disableSelectionOnClick
            getRowId={(row) => row.asset_id}
            sx={{
              border: 'none',
              '& .MuiDataGrid-cell': {
                borderBottom: '1px solid #f0f0f0',
              },
              '& .MuiDataGrid-row': {
                minHeight: '48px !important',
              },
              '& .MuiDataGrid-columnHeaders': {
                backgroundColor: '#f5f5f5',
                fontWeight: 'bold',
              },
            }}
          />
        </Paper>
      </TabPanel>

      {/* Assignments Tab */}
      <TabPanel value={activeTab} index={1}>
        <Paper sx={{ p: 2, mb: 3 }}>
          <Typography variant="h6" gutterBottom>
            Active Assignments
          </Typography>
          {assignments && assignments.length > 0 ? (
            <List>
              {assignments.map((assignment: any) => (
                <Card key={assignment.id} sx={{ mb: 2 }}>
                  <CardContent>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Box>
                        <Typography variant="h6">
                          {assignment.asset_id}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          Assigned to: {assignment.assignee}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          Type: {assignment.assignment_type}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          Since: {new Date(assignment.assigned_at).toLocaleString()}
                        </Typography>
                      </Box>
                      <Button
                        variant="outlined"
                        color="error"
                        onClick={() => handleRelease(assignment.asset_id)}
                      >
                        Release
                      </Button>
                    </Box>
                  </CardContent>
                </Card>
              ))}
            </List>
          ) : (
            <Typography variant="body2" color="text.secondary">
              No active assignments
            </Typography>
          )}
        </Paper>
      </TabPanel>

      {/* Maintenance Tab */}
      <TabPanel value={activeTab} index={2}>
        <Paper sx={{ p: 2, mb: 3 }}>
          <Typography variant="h6" gutterBottom>
            Maintenance Schedule
          </Typography>
          {maintenanceSchedule && maintenanceSchedule.length > 0 ? (
            <List>
              {maintenanceSchedule.map((maintenance: any) => (
                <Card key={maintenance.id} sx={{ mb: 2 }}>
                  <CardContent>
                    <Typography variant="h6">
                      {maintenance.asset_id} - {maintenance.maintenance_type}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {maintenance.description}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Scheduled: {new Date(maintenance.performed_at).toLocaleString()}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Duration: {maintenance.duration_minutes} minutes
                    </Typography>
                  </CardContent>
                </Card>
              ))}
            </List>
          ) : (
            <Typography variant="body2" color="text.secondary">
              No scheduled maintenance
            </Typography>
          )}
        </Paper>
      </TabPanel>

      {/* Telemetry Tab */}
      <TabPanel value={activeTab} index={3}>
        <Paper sx={{ p: 2, mb: 3 }}>
          <Typography variant="h6" gutterBottom>
            Equipment Telemetry
          </Typography>
          {equipmentAssets && equipmentAssets.length > 0 ? (
            <Box>
              <Box sx={{ mb: 2 }}>
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  Select an asset to view telemetry data:
                </Typography>
                <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mb: 2 }}>
                  {equipmentAssets.map((asset) => (
                    <Chip
                      key={asset.asset_id}
                      label={`${asset.asset_id} (${asset.type})`}
                      onClick={() => setSelectedAssetId(asset.asset_id)}
                      color={selectedAssetId === asset.asset_id ? 'primary' : 'default'}
                      variant={selectedAssetId === asset.asset_id ? 'filled' : 'outlined'}
                      sx={{ cursor: 'pointer' }}
                    />
                  ))}
                </Box>
              </Box>
              {selectedAssetId ? (
                <Box>
                  <Typography variant="body2" color="text.secondary" gutterBottom>
                    Asset: {selectedAssetId}
                  </Typography>
                  {telemetryLoading ? (
                    <Box sx={{ display: 'flex', justifyContent: 'center', p: 3 }}>
                      <CircularProgress />
                    </Box>
                  ) : telemetryData && telemetryData.length > 0 ? (
                    <List>
                      {telemetryData.map((data: any, index: number) => (
                        <ListItem key={index}>
                          <ListItemText
                            primary={`${data.metric}: ${data.value} ${data.unit || ''}`}
                            secondary={`${new Date(data.timestamp).toLocaleString()}${data.quality_score ? ` (Quality: ${(data.quality_score * 100).toFixed(1)}%)` : ''}`}
                          />
                        </ListItem>
                      ))}
                    </List>
                  ) : (
                    <Alert severity="info" sx={{ mt: 2 }}>
                      No telemetry data available for {selectedAssetId} in the last 7 days.
                      <Typography variant="body2" sx={{ mt: 1 }}>
                        Telemetry data may not have been generated yet, or the asset may not have any recent telemetry records.
                      </Typography>
                    </Alert>
                  )}
                </Box>
              ) : (
                <Alert severity="info">
                  Please select an asset from the list above to view telemetry data.
                </Alert>
              )}
            </Box>
          ) : (
            <Typography variant="body2" color="text.secondary">
              No equipment assets available
            </Typography>
          )}
        </Paper>
      </TabPanel>

      {/* Asset Details Dialog */}
      <Dialog open={open} onClose={handleClose} maxWidth="md" fullWidth>
        <DialogTitle>
          {selectedAsset ? 'Edit Asset' : 'Add New Asset'}
        </DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Asset ID"
                value={formData.asset_id || ''}
                onChange={(e) => setFormData({ ...formData, asset_id: e.target.value })}
                disabled={!!selectedAsset}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Type"
                value={formData.type || ''}
                onChange={(e) => setFormData({ ...formData, type: e.target.value })}
                select
                SelectProps={{ native: true }}
              >
                <option value="">Select Type</option>
                <option value="forklift">Forklift</option>
                <option value="amr">AMR</option>
                <option value="agv">AGV</option>
                <option value="scanner">Scanner</option>
                <option value="charger">Charger</option>
                <option value="conveyor">Conveyor</option>
                <option value="humanoid">Humanoid</option>
              </TextField>
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Model"
                value={formData.model || ''}
                onChange={(e) => setFormData({ ...formData, model: e.target.value })}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Zone"
                value={formData.zone || ''}
                onChange={(e) => setFormData({ ...formData, zone: e.target.value })}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Status"
                value={formData.status || ''}
                onChange={(e) => setFormData({ ...formData, status: e.target.value })}
                select
                SelectProps={{ native: true }}
              >
                <option value="">Select Status</option>
                <option value="available">Available</option>
                <option value="assigned">Assigned</option>
                <option value="charging">Charging</option>
                <option value="maintenance">Maintenance</option>
                <option value="out_of_service">Out of Service</option>
              </TextField>
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Owner/User"
                value={formData.owner_user || ''}
                onChange={(e) => setFormData({ ...formData, owner_user: e.target.value })}
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleClose}>Cancel</Button>
          <Button
            onClick={selectedAsset ? handleAssign : handleScheduleMaintenance}
            variant="contained"
            sx={{ backgroundColor: '#76B900', '&:hover': { backgroundColor: '#5a8f00' } }}
          >
            {selectedAsset ? 'Update' : 'Create'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Asset Details Drawer */}
      <Drawer
        anchor="right"
        open={drawerOpen}
        onClose={handleDrawerClose}
        PaperProps={{
          sx: {
            width: { xs: '100%', sm: '600px', md: '700px' },
            maxWidth: '90vw',
          },
        }}
      >
        <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'auto' }}>
          {/* Header */}
          <Box
            sx={{
              p: 3,
              backgroundColor: 'primary.main',
              color: 'white',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}
          >
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <Typography variant="h5" sx={{ fontWeight: 'bold' }}>
                {drawerAssetLoading ? (
                  <CircularProgress size={24} sx={{ color: 'white' }} />
                ) : (
                  <>
                    <span style={{ fontSize: '1.5rem', marginRight: '8px' }}>
                      {drawerAsset ? getTypeIcon(drawerAsset.type) : '⚙️'}
                    </span>
                    {drawerAsset?.asset_id || drawerAssetId}
                  </>
                )}
              </Typography>
            </Box>
            <IconButton onClick={handleDrawerClose} sx={{ color: 'white' }}>
              <CloseIcon />
            </IconButton>
          </Box>

          {/* Content */}
          <Box sx={{ p: 3, flex: 1, overflow: 'auto' }}>
            {drawerAssetLoading ? (
              <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '400px' }}>
                <CircularProgress />
              </Box>
            ) : drawerAsset ? (
              <Stack spacing={3}>
                {/* Status Card */}
                <Card sx={{ background: 'linear-gradient(135deg, #4caf50 0%, #2e7d32 100%)', color: 'white' }}>
                  <CardContent>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Box>
                        <Typography variant="overline" sx={{ opacity: 0.9 }}>
                          Current Status
                        </Typography>
                        <Typography variant="h4" sx={{ fontWeight: 'bold', mt: 1 }}>
                          {drawerAsset.status.toUpperCase()}
                        </Typography>
                      </Box>
                      <Chip
                        label={drawerAsset.status}
                        color={getStatusColor(drawerAsset.status) as any}
                        sx={{ 
                          backgroundColor: 'rgba(255, 255, 255, 0.2)',
                          color: 'white',
                          fontWeight: 'bold',
                          fontSize: '0.875rem',
                        }}
                      />
                    </Box>
                  </CardContent>
                </Card>

                {/* Basic Information Grid */}
                <Grid container spacing={2}>
                  <Grid item xs={12} sm={6}>
                    <Card sx={{ height: '100%' }}>
                      <CardContent>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                          <BuildIcon color="primary" />
                          <Typography variant="subtitle2" color="text.secondary">
                            Type
                          </Typography>
                        </Box>
                        <Typography variant="h6">{drawerAsset.type}</Typography>
                      </CardContent>
                    </Card>
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <Card sx={{ height: '100%' }}>
                      <CardContent>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                          <SettingsIcon color="primary" />
                          <Typography variant="subtitle2" color="text.secondary">
                            Model
                          </Typography>
                        </Box>
                        <Typography variant="h6">{drawerAsset.model || 'N/A'}</Typography>
                      </CardContent>
                    </Card>
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <Card sx={{ height: '100%' }}>
                      <CardContent>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                          <LocationIcon color="primary" />
                          <Typography variant="subtitle2" color="text.secondary">
                            Zone
                          </Typography>
                        </Box>
                        <Typography variant="h6">{drawerAsset.zone || 'N/A'}</Typography>
                      </CardContent>
                    </Card>
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <Card sx={{ height: '100%' }}>
                      <CardContent>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                          <PersonIcon color="primary" />
                          <Typography variant="subtitle2" color="text.secondary">
                            Assigned To
                          </Typography>
                        </Box>
                        <Typography variant="h6">{drawerAsset.owner_user || 'Unassigned'}</Typography>
                      </CardContent>
                    </Card>
                  </Grid>
                </Grid>

                {/* Manufacturing Year */}
                {drawerAsset.metadata?.manufacturing_year && (
                  <Card sx={{ background: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)', color: 'white' }}>
                    <CardContent>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                        <FactoryIcon sx={{ fontSize: 40 }} />
                        <Box>
                          <Typography variant="overline" sx={{ opacity: 0.9 }}>
                            Manufacturing Year
                          </Typography>
                          <Typography variant="h4" sx={{ fontWeight: 'bold' }}>
                            {drawerAsset.metadata.manufacturing_year}
                          </Typography>
                        </Box>
                      </Box>
                    </CardContent>
                  </Card>
                )}

                {/* Maintenance Cards */}
                <Grid container spacing={2}>
                  <Grid item xs={12} sm={6}>
                    <Card sx={{ borderLeft: '4px solid', borderLeftColor: 'success.main' }}>
                      <CardContent>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
                          <CheckCircleIcon color="success" />
                          <Typography variant="subtitle1" sx={{ fontWeight: 'bold' }}>
                            Last Maintenance
                          </Typography>
                        </Box>
                        {drawerAsset.last_maintenance ? (
                          <Box>
                            <Typography variant="h6" sx={{ mb: 1 }}>
                              {new Date(drawerAsset.last_maintenance).toLocaleDateString()}
                            </Typography>
                            <Typography variant="body2" color="text.secondary">
                              {new Date(drawerAsset.last_maintenance).toLocaleTimeString()}
                            </Typography>
                          </Box>
                        ) : (
                          <Typography variant="body2" color="text.secondary">
                            No maintenance records
                          </Typography>
                        )}
                      </CardContent>
                    </Card>
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <Card sx={{ borderLeft: '4px solid', borderLeftColor: 'warning.main' }}>
                      <CardContent>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
                          <CalendarIcon color="warning" />
                          <Typography variant="subtitle1" sx={{ fontWeight: 'bold' }}>
                            Next Maintenance
                          </Typography>
                        </Box>
                        {drawerAsset.next_pm_due ? (
                          <Box>
                            <Typography variant="h6" sx={{ mb: 1 }}>
                              {new Date(drawerAsset.next_pm_due).toLocaleDateString()}
                            </Typography>
                            <Typography variant="body2" color="text.secondary">
                              {Math.ceil((new Date(drawerAsset.next_pm_due).getTime() - Date.now()) / (1000 * 60 * 60 * 24))} days remaining
                            </Typography>
                          </Box>
                        ) : (
                          <Typography variant="body2" color="text.secondary">
                            Not scheduled
                          </Typography>
                        )}
                      </CardContent>
                    </Card>
                  </Grid>
                </Grid>

                {/* Telemetry Chart */}
                {drawerTelemetry && drawerTelemetry.length > 0 && (
                  <Card>
                    <CardContent>
                      <Typography variant="h6" sx={{ mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
                        <TrendingUpIcon color="primary" />
                        Telemetry Data (Last 7 Days)
                      </Typography>
                      {drawerTelemetryLoading ? (
                        <Box sx={{ display: 'flex', justifyContent: 'center', p: 3 }}>
                          <CircularProgress />
                        </Box>
                      ) : (
                        <Box sx={{ height: 300 }}>
                          <ResponsiveContainer width="100%" height="100%">
                            <LineChart data={drawerTelemetry.slice(-50)}>
                              <CartesianGrid strokeDasharray="3 3" />
                              <XAxis 
                                dataKey="timeLabel" 
                                tick={{ fontSize: 12 }}
                                angle={-45}
                                textAnchor="end"
                                height={80}
                              />
                              <YAxis />
                              <RechartsTooltip />
                              <Legend />
                              {telemetryMetrics.length > 0 ? (
                                telemetryMetrics.map((metric: string, index: number) => {
                                  const colors = ['#8884d8', '#82ca9d', '#ffc658', '#ff7300', '#00ff00', '#0088fe'];
                                  return (
                                    <Line 
                                      key={metric}
                                      type="monotone" 
                                      dataKey={metric} 
                                      stroke={colors[index % colors.length]} 
                                      name={metric.replace(/_/g, ' ')}
                                      strokeWidth={2}
                                      dot={false}
                                    />
                                  );
                                })
                              ) : (
                                <Line 
                                  type="monotone" 
                                  dataKey="value" 
                                  stroke="#8884d8" 
                                  name="Value"
                                  strokeWidth={2}
                                  dot={false}
                                />
                              )}
                            </LineChart>
                          </ResponsiveContainer>
                        </Box>
                      )}
                    </CardContent>
                  </Card>
                )}

                {/* Maintenance History */}
                {drawerMaintenance && drawerMaintenance.length > 0 && (
                  <Card>
                    <CardContent>
                      <Typography variant="h6" sx={{ mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
                        <SecurityIcon color="primary" />
                        Maintenance History
                      </Typography>
                      <List>
                        {drawerMaintenance.slice(0, 5).map((maintenance: any, index: number) => (
                          <React.Fragment key={index}>
                            <ListItem>
                              <ListItemText
                                primary={
                                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                    <Typography variant="subtitle1" sx={{ fontWeight: 'bold' }}>
                                      {maintenance.maintenance_type || 'Maintenance'}
                                    </Typography>
                                    <Chip 
                                      label={maintenance.priority || 'medium'} 
                                      size="small"
                                      color={maintenance.priority === 'high' ? 'error' : maintenance.priority === 'medium' ? 'warning' : 'default'}
                                    />
                                  </Box>
                                }
                                secondary={
                                  <Box>
                                    <Typography variant="body2" color="text.secondary">
                                      {maintenance.description || 'No description'}
                                    </Typography>
                                    <Typography variant="caption" color="text.secondary">
                                      {maintenance.performed_at 
                                        ? new Date(maintenance.performed_at).toLocaleString()
                                        : maintenance.scheduled_for
                                        ? `Scheduled: ${new Date(maintenance.scheduled_for).toLocaleString()}`
                                        : 'Date not available'}
                                    </Typography>
                                  </Box>
                                }
                              />
                            </ListItem>
                            {index < drawerMaintenance.length - 1 && <Divider />}
                          </React.Fragment>
                        ))}
                      </List>
                    </CardContent>
                  </Card>
                )}

                {/* Additional Metadata */}
                {drawerAsset.metadata && Object.keys(drawerAsset.metadata).length > 0 && (
                  <Card>
                    <CardContent>
                      <Typography variant="h6" sx={{ mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
                        <InfoIcon color="primary" />
                        Additional Information
                      </Typography>
                      <Grid container spacing={2}>
                        {Object.entries(drawerAsset.metadata)
                          .filter(([key]) => key !== 'manufacturing_year')
                          .map(([key, value]) => (
                            <Grid item xs={12} sm={6} key={key}>
                              <Box sx={{ p: 2, backgroundColor: 'grey.50', borderRadius: 1 }}>
                                <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase' }}>
                                  {key.replace(/_/g, ' ')}
                                </Typography>
                                <Typography variant="body1" sx={{ fontWeight: 'medium', mt: 0.5 }}>
                                  {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                                </Typography>
                              </Box>
                            </Grid>
                          ))}
                      </Grid>
                    </CardContent>
                  </Card>
                )}
              </Stack>
            ) : (
              <Alert severity="error">Failed to load asset details</Alert>
            )}
          </Box>
        </Box>
      </Drawer>
    </Box>
  );
};

export default EquipmentNew;
