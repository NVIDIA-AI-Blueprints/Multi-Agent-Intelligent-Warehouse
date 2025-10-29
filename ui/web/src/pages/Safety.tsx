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
  FormControl,
  InputLabel,
  Select,
  MenuItem,
} from '@mui/material';
import { DataGrid, GridColDef } from '@mui/x-data-grid';
import { Report as ReportIcon } from '@mui/icons-material';
import { useQuery, useMutation, useQueryClient } from 'react-query';
import { safetyAPI, SafetyIncident, userAPI, User } from '../services/api';

const Safety: React.FC = () => {
  const [open, setOpen] = useState(false);
  const [selectedIncident, setSelectedIncident] = useState<SafetyIncident | null>(null);
  const [formData, setFormData] = useState<Partial<SafetyIncident>>({});
  const queryClient = useQueryClient();

  const { data: incidents, isLoading, error } = useQuery(
    'incidents',
    safetyAPI.getIncidents
  );

  const { data: policies } = useQuery(
    'policies',
    safetyAPI.getPolicies
  );

  const { data: users } = useQuery(
    'users',
    userAPI.getUsers
  );

  const reportMutation = useMutation(safetyAPI.reportIncident, {
    onSuccess: () => {
      queryClient.invalidateQueries('incidents');
      setOpen(false);
      setFormData({});
    },
  });

  const handleOpen = (incident?: SafetyIncident) => {
    if (incident) {
      setSelectedIncident(incident);
      setFormData(incident);
    } else {
      setSelectedIncident(null);
      setFormData({});
    }
    setOpen(true);
  };

  const handleClose = () => {
    setOpen(false);
    setSelectedIncident(null);
    setFormData({});
  };

  const handleSubmit = () => {
    if (formData.severity && formData.description && formData.reported_by) {
      reportMutation.mutate(formData as Omit<SafetyIncident, 'id' | 'occurred_at'>);
    }
  };

  const columns: GridColDef[] = [
    { field: 'id', headerName: 'ID', width: 80 },
    {
      field: 'severity',
      headerName: 'Severity',
      width: 120,
      renderCell: (params) => {
        const severity = params.value;
        const color = severity === 'high' ? 'error' : 
                     severity === 'medium' ? 'warning' : 'info';
        return <Chip label={severity} color={color} size="small" />;
      },
    },
    { field: 'description', headerName: 'Description', width: 300 },
    { field: 'reported_by', headerName: 'Reported By', width: 150 },
    {
      field: 'occurred_at',
      headerName: 'Occurred At',
      width: 150,
      renderCell: (params) => new Date(params.value).toLocaleDateString(),
    },
  ];

  if (error) {
    return (
      <Box>
        <Typography variant="h4" gutterBottom>
          Safety & Compliance
        </Typography>
        <Alert severity="error">
          Failed to load safety data. Please try again.
        </Alert>
      </Box>
    );
  }

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h4">
          Safety & Compliance
        </Typography>
        <Button
          variant="contained"
          startIcon={<ReportIcon />}
          onClick={() => handleOpen()}
        >
          Report Incident
        </Button>
      </Box>

      {/* Safety Policies */}
      {policies && (
        <Paper sx={{ p: 2, mb: 3 }}>
          <Typography variant="h6" gutterBottom>
            Safety Policies
          </Typography>
          <Grid container spacing={2}>
            {policies.map((policy: any) => (
              <Grid item xs={12} md={6} key={policy.id}>
                <Box sx={{ p: 2, border: 1, borderColor: 'divider', borderRadius: 1 }}>
                  <Typography variant="subtitle1">{policy.name}</Typography>
                  <Typography variant="body2" color="text.secondary">
                    {policy.summary}
                  </Typography>
                  <Chip
                    label={policy.status}
                    color={policy.status === 'Active' ? 'success' : 'default'}
                    size="small"
                    sx={{ mt: 1 }}
                  />
                </Box>
              </Grid>
            ))}
          </Grid>
        </Paper>
      )}

      {/* Incidents Management */}
      <Paper sx={{ height: 600, width: '100%' }}>
        <DataGrid
          rows={incidents || []}
          columns={columns}
          loading={isLoading}
          pageSize={10}
          rowsPerPageOptions={[10, 25, 50]}
          disableSelectionOnClick
        />
      </Paper>

      <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
        <DialogTitle>
          {selectedIncident ? 'Edit Incident' : 'Report New Incident'}
        </DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12}>
              <FormControl fullWidth>
                <InputLabel>Severity</InputLabel>
                <Select
                  value={formData.severity || ''}
                  onChange={(e) => setFormData({ ...formData, severity: e.target.value })}
                  label="Severity"
                  required
                >
                  <MenuItem value="low">Low</MenuItem>
                  <MenuItem value="medium">Medium</MenuItem>
                  <MenuItem value="high">High</MenuItem>
                  <MenuItem value="critical">Critical</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="Description"
                multiline
                rows={4}
                value={formData.description || ''}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                required
              />
            </Grid>
            <Grid item xs={12}>
              <FormControl fullWidth>
                <InputLabel>Reported By</InputLabel>
                <Select
                  value={formData.reported_by || ''}
                  onChange={(e) => setFormData({ ...formData, reported_by: e.target.value })}
                  label="Reported By"
                  required
                >
                  {users && users.length > 0 ? (
                    users.map((user: User) => (
                      <MenuItem key={user.id} value={user.full_name || user.username}>
                        {user.full_name || user.username} ({user.role})
                      </MenuItem>
                    ))
                  ) : (
                    <MenuItem value="">No users available</MenuItem>
                  )}
                </Select>
              </FormControl>
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleClose}>Cancel</Button>
          <Button
            onClick={handleSubmit}
            variant="contained"
            disabled={reportMutation.isLoading}
          >
            {selectedIncident ? 'Update' : 'Report'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default Safety;
