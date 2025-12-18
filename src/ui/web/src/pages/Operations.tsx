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
import { } from '@mui/icons-material';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { operationsAPI, Task, userAPI, User } from '../services/api';

const Operations: React.FC = () => {
  const [open, setOpen] = useState(false);
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [formData, setFormData] = useState<Partial<Task>>({});
  const queryClient = useQueryClient();

  const { data: tasks, isLoading, error } = useQuery({
    queryKey: ['tasks'],
    queryFn: operationsAPI.getTasks
  });

  const { data: workforceStatus } = useQuery({
    queryKey: ['workforce'],
    queryFn: operationsAPI.getWorkforceStatus
  });

  const { data: users } = useQuery({
    queryKey: ['users'],
    queryFn: userAPI.getUsers
  });

  const assignMutation = useMutation({
    mutationFn: ({ taskId, assignee }: { taskId: number; assignee: string }) =>
      operationsAPI.assignTask(taskId, assignee),
      onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
        setOpen(false);
        setSelectedTask(null);
        setFormData({});
    }
  });

  const handleOpen = (task?: Task) => {
    if (task) {
      setSelectedTask(task);
      setFormData(task);
    } else {
      setSelectedTask(null);
      setFormData({});
    }
    setOpen(true);
  };

  const handleClose = () => {
    setOpen(false);
    setSelectedTask(null);
    setFormData({});
  };

  const handleSubmit = () => {
    if (selectedTask && formData.assignee) {
      assignMutation.mutate({ taskId: selectedTask.id, assignee: formData.assignee });
    }
  };

  const columns: GridColDef[] = [
    { field: 'id', headerName: 'ID', width: 80 },
    { field: 'kind', headerName: 'Task Type', width: 150 },
    {
      field: 'status',
      headerName: 'Status',
      width: 120,
      renderCell: (params) => {
        const status = params.value;
        const color = status === 'completed' ? 'success' : 
                     status === 'in_progress' ? 'info' : 'warning';
        return <Chip label={status} color={color} size="small" />;
      },
    },
    { field: 'assignee', headerName: 'Assignee', width: 150 },
    {
      field: 'created_at',
      headerName: 'Created',
      width: 150,
      renderCell: (params) => new Date(params.value).toLocaleDateString(),
    },
    {
      field: 'actions',
      headerName: 'Actions',
      width: 120,
      renderCell: (params) => (
        <Button
          size="small"
          onClick={() => handleOpen(params.row)}
        >
          Assign
        </Button>
      ),
    },
  ];

  if (error) {
    return (
      <Box>
        <Typography variant="h4" gutterBottom>
          Operations Management
        </Typography>
        <Alert severity="error">
          Failed to load operations data. Please try again.
        </Alert>
      </Box>
    );
  }

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Operations Management
      </Typography>

      {/* Workforce Status */}
      {workforceStatus && (
        <Paper sx={{ p: 3, mb: 3 }}>
          <Typography variant="h6" gutterBottom>
            Workforce Status
          </Typography>
          <Grid container spacing={3}>
            <Grid item xs={12} sm={6} md={3}>
              <Box sx={{ 
                p: 2, 
                border: 1, 
                borderColor: 'divider', 
                borderRadius: 2,
                textAlign: 'center',
                backgroundColor: 'primary.light',
                color: 'primary.contrastText'
              }}>
                <Typography variant="h4" sx={{ fontWeight: 'bold' }}>
                  {workforceStatus.total_workers}
                </Typography>
                <Typography variant="body2">
                  Total Workers
                </Typography>
              </Box>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Box sx={{ 
                p: 2, 
                border: 1, 
                borderColor: 'divider', 
                borderRadius: 2,
                textAlign: 'center',
                backgroundColor: 'success.light',
                color: 'success.contrastText'
              }}>
                <Typography variant="h4" sx={{ fontWeight: 'bold' }}>
                  {workforceStatus.active_workers}
                </Typography>
                <Typography variant="body2">
                  Active Workers
                </Typography>
              </Box>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Box sx={{ 
                p: 2, 
                border: 1, 
                borderColor: 'divider', 
                borderRadius: 2,
                textAlign: 'center',
                backgroundColor: 'info.light',
                color: 'info.contrastText'
              }}>
                <Typography variant="h4" sx={{ fontWeight: 'bold' }}>
                  {workforceStatus.available_workers}
                </Typography>
                <Typography variant="body2">
                  Available Workers
                </Typography>
              </Box>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Box sx={{ 
                p: 2, 
                border: 1, 
                borderColor: 'divider', 
                borderRadius: 2,
                textAlign: 'center',
                backgroundColor: 'warning.light',
                color: 'warning.contrastText'
              }}>
                <Typography variant="h4" sx={{ fontWeight: 'bold' }}>
                  {workforceStatus.tasks_in_progress}
                </Typography>
                <Typography variant="body2">
                  Tasks in Progress
                </Typography>
              </Box>
            </Grid>
            <Grid item xs={12} sm={6} md={6}>
              <Box sx={{ 
                p: 2, 
                border: 1, 
                borderColor: 'divider', 
                borderRadius: 2,
                textAlign: 'center',
                backgroundColor: 'secondary.light',
                color: 'secondary.contrastText'
              }}>
                <Typography variant="h4" sx={{ fontWeight: 'bold' }}>
                  {workforceStatus.tasks_pending}
                </Typography>
                <Typography variant="body2">
                  Pending Tasks
                </Typography>
              </Box>
            </Grid>
            <Grid item xs={12} sm={6} md={6}>
              <Box sx={{ 
                p: 2, 
                border: 1, 
                borderColor: 'divider', 
                borderRadius: 2,
                textAlign: 'center',
                backgroundColor: 'grey.200',
                color: 'text.primary'
              }}>
                <Typography variant="h4" sx={{ fontWeight: 'bold' }}>
                  {Math.round((workforceStatus.active_workers / workforceStatus.total_workers) * 100)}%
                </Typography>
                <Typography variant="body2">
                  Workforce Utilization
                </Typography>
              </Box>
            </Grid>
          </Grid>
        </Paper>
      )}

      {/* Tasks Management */}
      <Paper sx={{ height: 600, width: '100%' }}>
        <DataGrid
          rows={tasks || []}
          columns={columns}
          loading={isLoading}
          initialState={{
            pagination: {
              paginationModel: { pageSize: 10 },
            },
          }}
          pageSizeOptions={[10, 25, 50]}
          disableRowSelectionOnClick
        />
      </Paper>

      <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
        <DialogTitle>
          {selectedTask ? 'Assign Task' : 'Create New Task'}
        </DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="Task Type"
                value={formData.kind || ''}
                onChange={(e) => setFormData({ ...formData, kind: e.target.value })}
                disabled={!!selectedTask}
                required
              />
            </Grid>
            <Grid item xs={12}>
              <FormControl fullWidth>
                <InputLabel>Assignee</InputLabel>
                <Select
                  value={formData.assignee || ''}
                  onChange={(e) => setFormData({ ...formData, assignee: e.target.value })}
                  label="Assignee"
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
            <Grid item xs={12}>
              <FormControl fullWidth>
                <InputLabel>Status</InputLabel>
                <Select
                  value={formData.status || ''}
                  onChange={(e) => setFormData({ ...formData, status: e.target.value })}
                  label="Status"
                >
                  <MenuItem value="pending">Pending</MenuItem>
                  <MenuItem value="in_progress">In Progress</MenuItem>
                  <MenuItem value="completed">Completed</MenuItem>
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
            disabled={assignMutation.isPending}
          >
            {selectedTask ? 'Assign' : 'Create'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default Operations;
