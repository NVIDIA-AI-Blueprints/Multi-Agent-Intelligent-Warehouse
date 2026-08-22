import React, { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  Card,
  CardContent,
  Grid,
  TextField,
  Button,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Chip,
  Alert,
  Divider,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  CircularProgress,
} from '@mui/material';
import {
  ExpandMore as ExpandIcon,
  CheckCircle as ApprovedIcon,
  Cancel as RejectedIcon,
  Person as HumanIcon,
  Refresh as StaleIcon,
  PlayArrow as ExecuteIcon,
  DeleteOutline as ClearIcon,
} from '@mui/icons-material';
import { format } from 'date-fns';
import { equipmentAPI } from '../services/api';

const STORAGE_KEY = 'maiw_decision_history';

interface DecisionRecord {
  id: string;
  action: string;
  request: Record<string, any>;
  result: any;
  timestamp: string;
}

type DecisionStatus = 'approved' | 'rejected' | 'requires_human_approval' | 'requires_fresh_state';

const STATUS_CONFIG: Record<DecisionStatus, { label: string; color: 'success' | 'error' | 'warning' | 'info'; icon: React.ReactNode }> = {
  approved: { label: 'Approved & Executed', color: 'success', icon: <ApprovedIcon sx={{ fontSize: 16 }} /> },
  rejected: { label: 'Rejected', color: 'error', icon: <RejectedIcon sx={{ fontSize: 16 }} /> },
  requires_human_approval: { label: 'Pending Approval', color: 'warning', icon: <HumanIcon sx={{ fontSize: 16 }} /> },
  requires_fresh_state: { label: 'Blocked — Stale State', color: 'info', icon: <StaleIcon sx={{ fontSize: 16 }} /> },
};

function getDecisionStatus(result: any): DecisionStatus | null {
  if (!result) return null;
  const status = result.decision?.status ?? result.decision_result?.status ?? result.status;
  if (status && status in STATUS_CONFIG) return status as DecisionStatus;
  if (result.success === true) return 'approved';
  if (result.success === false) return 'rejected';
  return null;
}

function DecisionStatusBadge({ status }: { status: DecisionStatus | null }) {
  if (!status) return null;
  const cfg = STATUS_CONFIG[status];
  return (
    <Chip
      icon={cfg.icon as any}
      label={cfg.label}
      color={cfg.color}
      variant="outlined"
      sx={{ fontWeight: 600 }}
    />
  );
}

function DecisionCard({ record, onDelete }: { record: DecisionRecord; onDelete: (id: string) => void }) {
  const status = getDecisionStatus(record.result);
  const cfg = status ? STATUS_CONFIG[status] : null;

  return (
    <Accordion
      sx={{
        backgroundColor: 'background.paper',
        border: '1px solid',
        borderColor: cfg ? `${cfg.color}.main` : 'divider',
        '&:before': { display: 'none' },
        mb: 1,
      }}
    >
      <AccordionSummary expandIcon={<ExpandIcon />}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, width: '100%', mr: 1 }}>
          <Box sx={{ flexGrow: 1 }}>
            <Typography variant="body2" sx={{ fontWeight: 600, fontFamily: 'monospace' }}>
              {record.action.toUpperCase()} · {record.request.asset_id ?? '?'}
            </Typography>
            <Typography variant="caption" sx={{ color: 'text.secondary' }}>
              {format(new Date(record.timestamp), 'HH:mm:ss')}
            </Typography>
          </Box>
          <DecisionStatusBadge status={status} />
        </Box>
      </AccordionSummary>
      <AccordionDetails sx={{ pt: 0 }}>
        <Divider sx={{ mb: 2 }} />
        <Grid container spacing={2}>
          <Grid item xs={12} md={6}>
            <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Request
            </Typography>
            <Box
              component="pre"
              sx={{ fontFamily: 'monospace', fontSize: '0.75rem', color: '#8B949E', backgroundColor: '#0D1117', p: 1.5, borderRadius: 1, mt: 0.5, overflow: 'auto' }}
            >
              {JSON.stringify(record.request, null, 2)}
            </Box>
          </Grid>
          <Grid item xs={12} md={6}>
            <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Decision Result
            </Typography>
            <Box
              component="pre"
              sx={{ fontFamily: 'monospace', fontSize: '0.75rem', color: '#8B949E', backgroundColor: '#0D1117', p: 1.5, borderRadius: 1, mt: 0.5, overflow: 'auto' }}
            >
              {JSON.stringify(record.result, null, 2)}
            </Box>
          </Grid>
        </Grid>
        {status === 'requires_human_approval' && (
          <Alert severity="info" sx={{ mt: 2 }}>
            Approval submission is not yet available. This record is read-only.
          </Alert>
        )}
        <Box sx={{ mt: 1, display: 'flex', justifyContent: 'flex-end' }}>
          <Button
            size="small"
            startIcon={<ClearIcon />}
            onClick={() => onDelete(record.id)}
            sx={{ color: 'text.secondary' }}
          >
            Remove
          </Button>
        </Box>
      </AccordionDetails>
    </Accordion>
  );
}

const DecisionCenter: React.FC = () => {
  const [history, setHistory] = useState<DecisionRecord[]>([]);
  const [action, setAction] = useState<string>('assign');
  const [assetId, setAssetId] = useState('');
  const [assignee, setAssignee] = useState('');
  const [notes, setNotes] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    try {
      const stored = sessionStorage.getItem(STORAGE_KEY);
      if (stored) setHistory(JSON.parse(stored));
    } catch {
      // ignore
    }
  }, []);

  const persistHistory = (records: DecisionRecord[]) => {
    setHistory(records);
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(records.slice(0, 50)));
    } catch {
      // ignore
    }
  };

  const handleExecute = async () => {
    if (!assetId.trim()) {
      setError('Asset ID is required');
      return;
    }
    setLoading(true);
    setError(null);
    let request: Record<string, any> = {};
    let result: any;
    try {
      if (action === 'assign') {
        if (!assignee.trim()) throw new Error('Assignee is required for assign action');
        const assignReq = { asset_id: assetId.trim(), assignee: assignee.trim(), notes: notes || undefined };
        request = assignReq;
        result = await equipmentAPI.assignAsset(assignReq);
      } else if (action === 'release') {
        const releaseReq = { asset_id: assetId.trim(), released_by: assignee.trim() || 'operator', notes: notes || undefined };
        request = releaseReq;
        result = await equipmentAPI.releaseAsset(releaseReq);
      } else if (action === 'maintenance') {
        const maintReq = {
          asset_id: assetId.trim(),
          maintenance_type: 'scheduled',
          description: notes || 'Scheduled maintenance',
          scheduled_by: assignee.trim() || 'operator',
          scheduled_for: new Date(Date.now() + 86400000).toISOString(),
        };
        request = maintReq;
        result = await equipmentAPI.scheduleMaintenance(maintReq);
      }
    } catch (err: any) {
      result = { error: err?.response?.data ?? err?.message ?? 'Request failed' };
    }
    const record: DecisionRecord = {
      id: `${Date.now()}`,
      action,
      request,
      result,
      timestamp: new Date().toISOString(),
    };
    persistHistory([record, ...history]);
    setLoading(false);
  };

  const handleDelete = (id: string) => {
    persistHistory(history.filter((r) => r.id !== id));
  };

  const handleClearAll = () => {
    persistHistory([]);
    sessionStorage.removeItem(STORAGE_KEY);
  };

  return (
    <Box sx={{ pb: 4 }}>
      <Box sx={{ mb: 3 }}>
        <Typography variant="h4" sx={{ fontWeight: 700, color: 'text.primary', letterSpacing: '-0.02em' }}>
          Decision Center
        </Typography>
        <Typography variant="body2" sx={{ color: 'text.secondary', mt: 0.5 }}>
          Trigger an equipment action and observe the full AI decision lifecycle
        </Typography>
      </Box>

      {/* Pipeline diagram */}
      <Card sx={{ backgroundColor: '#0D1117', border: '1px solid #21262D', mb: 3 }}>
        <CardContent sx={{ py: 1.5 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, overflowX: 'auto' }}>
            {[
              { step: 'OBSERVE', desc: 'State snapshot' },
              { step: 'REASON', desc: 'Nemotron assessment' },
              { step: 'PROPOSE', desc: 'ActionProposal' },
              { step: 'DECIDE', desc: 'DecisionEngine' },
              { step: 'EXECUTE', desc: 'ActionExecutor → MCP' },
            ].map(({ step, desc }, i, arr) => (
              <React.Fragment key={step}>
                <Box sx={{ textAlign: 'center', minWidth: 80 }}>
                  <Typography variant="caption" sx={{ fontFamily: 'monospace', fontWeight: 700, color: '#76B900', fontSize: '0.7rem', letterSpacing: '0.06em' }}>
                    {step}
                  </Typography>
                  <Typography variant="caption" sx={{ display: 'block', color: '#484F58', fontSize: '0.6rem' }}>
                    {desc}
                  </Typography>
                </Box>
                {i < arr.length - 1 && <Typography sx={{ color: '#484F58', fontFamily: 'monospace', fontSize: '0.8rem' }}>→</Typography>}
              </React.Fragment>
            ))}
          </Box>
        </CardContent>
      </Card>

      {/* Action form */}
      <Card sx={{ backgroundColor: 'background.paper', mb: 3 }}>
        <CardContent>
          <Typography variant="subtitle2" sx={{ color: 'text.secondary', mb: 2, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase', fontSize: '0.7rem' }}>
            Trigger Equipment Action
          </Typography>
          <Grid container spacing={2}>
            <Grid item xs={12} sm={3}>
              <FormControl fullWidth size="small">
                <InputLabel>Action</InputLabel>
                <Select value={action} onChange={(e) => setAction(e.target.value)} label="Action">
                  <MenuItem value="assign">Assign</MenuItem>
                  <MenuItem value="release">Release</MenuItem>
                  <MenuItem value="maintenance">Maintenance</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={3}>
              <TextField
                fullWidth
                size="small"
                label="Asset ID"
                value={assetId}
                onChange={(e) => setAssetId(e.target.value)}
                placeholder="e.g. asset-001"
              />
            </Grid>
            <Grid item xs={12} sm={3}>
              <TextField
                fullWidth
                size="small"
                label={action === 'assign' ? 'Assignee *' : 'Operator'}
                value={assignee}
                onChange={(e) => setAssignee(e.target.value)}
                placeholder="username"
              />
            </Grid>
            <Grid item xs={12} sm={3}>
              <TextField
                fullWidth
                size="small"
                label="Notes"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="optional"
              />
            </Grid>
          </Grid>
          {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
          <Box sx={{ mt: 2, display: 'flex', gap: 1 }}>
            <Button
              variant="contained"
              startIcon={loading ? <CircularProgress size={16} color="inherit" /> : <ExecuteIcon />}
              onClick={handleExecute}
              disabled={loading}
            >
              {loading ? 'Processing…' : 'Submit to Decision Pipeline'}
            </Button>
          </Box>
        </CardContent>
      </Card>

      {/* Decision status legend */}
      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mb: 2 }}>
        {(Object.entries(STATUS_CONFIG) as [DecisionStatus, typeof STATUS_CONFIG[DecisionStatus]][]).map(([key, cfg]) => (
          <Chip
            key={key}
            icon={cfg.icon as any}
            label={cfg.label}
            color={cfg.color}
            size="small"
            variant="outlined"
            sx={{ opacity: 0.75 }}
          />
        ))}
      </Box>

      {/* History */}
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1.5 }}>
        <Typography variant="subtitle2" sx={{ color: 'text.secondary', fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase', fontSize: '0.7rem' }}>
          Session History ({history.length})
        </Typography>
        {history.length > 0 && (
          <Button size="small" onClick={handleClearAll} sx={{ color: 'text.secondary', fontSize: '0.75rem' }}>
            Clear all
          </Button>
        )}
      </Box>
      {history.length === 0 ? (
        <Alert severity="info">
          No decisions in this session. Submit an equipment action above to see the decision lifecycle.
        </Alert>
      ) : (
        history.map((record) => (
          <DecisionCard key={record.id} record={record} onDelete={handleDelete} />
        ))
      )}
    </Box>
  );
};

export default DecisionCenter;
