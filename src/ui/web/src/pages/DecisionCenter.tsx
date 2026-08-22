import React, { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  TextField,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  CircularProgress,
  Alert,
} from '@mui/material';
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

type DecisionStatus = 'approved' | 'rejected' | 'requires_human_approval' | 'requires_fresh_state' | 'error' | 'unknown';

const STATUS_LABEL: Record<DecisionStatus, string> = {
  approved: 'EXECUTED',
  rejected: 'REJECTED',
  requires_human_approval: 'APPROVAL',
  requires_fresh_state: 'BLOCKED',
  error: 'ERROR',
  unknown: '—',
};
const STATUS_COLOR: Record<DecisionStatus, string> = {
  approved: '#3FB950',
  rejected: '#F85149',
  requires_human_approval: '#D29922',
  requires_fresh_state: '#58A6FF',
  error: '#F85149',
  unknown: '#484F58',
};
const RISK_LABEL: Record<string, string> = {
  assign: 'LOW',
  release: 'LOW',
  maintenance: 'MEDIUM',
};
const RISK_COLOR: Record<string, string> = {
  LOW: '#3FB950',
  MEDIUM: '#D29922',
  HIGH: '#F85149',
};

function getDecisionStatus(result: any): DecisionStatus {
  if (!result) return 'unknown';
  const status = result.decision?.status ?? result.decision_result?.status ?? result.status;
  if (status === 'approved' || status === 'rejected' || status === 'requires_human_approval' || status === 'requires_fresh_state') return status;
  if (result.success === true) return 'approved';
  if (result.success === false) return 'rejected';
  if (result.error) return 'error';
  return 'unknown';
}

function Col({ children, w, color, mono }: { children: React.ReactNode; w?: number | string; color?: string; mono?: boolean }) {
  return (
    <Typography sx={{
      fontFamily: mono !== false ? 'monospace' : 'inherit',
      fontSize: '0.73rem',
      color: color ?? '#8B949E',
      width: w,
      flexShrink: 0,
      overflow: 'hidden',
      textOverflow: 'ellipsis',
      whiteSpace: 'nowrap',
    }}>
      {children}
    </Typography>
  );
}

// ── Reasoning chain drill-down ─────────────────────────────────────────────

function ChainNode({ label, color, children }: { label: string; color: string; children: React.ReactNode }) {
  return (
    <Box sx={{ mb: 1.5 }}>
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color, fontWeight: 700, letterSpacing: '0.1em', mb: 0.5 }}>
        {label}
      </Typography>
      <Box sx={{ pl: 1.5, borderLeft: `2px solid ${color}20` }}>
        {children}
      </Box>
    </Box>
  );
}

function CodeBlock({ data }: { data: any }) {
  return (
    <Box component="pre" sx={{
      fontFamily: 'monospace', fontSize: '0.68rem', color: '#6E7681',
      backgroundColor: '#080C10', p: 1, borderRadius: 1,
      overflow: 'auto', maxHeight: 120, m: 0,
    }}>
      {JSON.stringify(data, null, 2)}
    </Box>
  );
}

function ReasoningChain({ record, onClose }: { record: DecisionRecord; onClose: () => void }) {
  const status = getDecisionStatus(record.result);
  const r = record.result;

  const reasoning = r?.decision?.reasoning ?? r?.decision_result?.reasoning ?? r?.reasoning;
  const proposal = r?.proposal ?? r?.decision?.proposal ?? record.request;
  const executionResult = r?.execution ?? r?.execution_result;

  return (
    <Box sx={{ backgroundColor: '#080C10', border: '1px solid #1C2128', borderRadius: 1, p: 2, mt: 1.5 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2, pb: 1, borderBottom: '1px solid #1C2128' }}>
        <Typography sx={{ fontFamily: 'monospace', fontWeight: 700, fontSize: '0.75rem', color: '#E6EDF3', letterSpacing: '0.06em' }}>
          {record.action.toUpperCase()} — REASONING CHAIN
        </Typography>
        <Box
          onClick={onClose}
          sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#484F58', cursor: 'pointer', '&:hover': { color: '#8B949E' } }}
        >
          [CLOSE ✕]
        </Box>
      </Box>

      <ChainNode label="WAREHOUSE STATE" color="#58A6FF">
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.7rem', color: '#6E7681' }}>
          Asset: {record.request.asset_id ?? '—'} · Action triggered at {format(new Date(record.timestamp), 'HH:mm:ss')}
        </Typography>
        <CodeBlock data={record.request} />
      </ChainNode>

      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, mb: 1.5, ml: 0.5 }}>
        <Box sx={{ width: 1, height: 16, backgroundColor: '#1C2128' }} />
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#30363D' }}>↓</Typography>
      </Box>

      <ChainNode label="AGENT → MODEL GATEWAY" color="#76B900">
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.7rem', color: '#6E7681' }}>
          {reasoning ? `Reasoning: ${typeof reasoning === 'string' ? reasoning : JSON.stringify(reasoning)}` : 'Decision pipeline evaluated request'}
        </Typography>
      </ChainNode>

      <ChainNode label="PROPOSAL" color="#D29922">
        <CodeBlock data={proposal} />
      </ChainNode>

      <ChainNode label="DECISION" color={STATUS_COLOR[status]}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
          <Box sx={{ width: 7, height: 7, borderRadius: '50%', backgroundColor: STATUS_COLOR[status], boxShadow: `0 0 5px ${STATUS_COLOR[status]}` }} />
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.73rem', fontWeight: 700, color: STATUS_COLOR[status] }}>
            {STATUS_LABEL[status]}
          </Typography>
        </Box>
        {status === 'requires_human_approval' && (
          <Alert severity="warning" sx={{ mt: 0.75, py: 0.25, fontSize: '0.72rem', fontFamily: 'monospace', backgroundColor: 'rgba(210,153,34,0.08)', border: '1px solid rgba(210,153,34,0.2)', color: '#D29922', '& .MuiAlert-icon': { color: '#D29922' } }}>
            This action requires explicit human approval before execution.
          </Alert>
        )}
      </ChainNode>

      <ChainNode label="EXECUTION → MCP" color={status === 'approved' ? '#3FB950' : '#484F58'}>
        {executionResult ? (
          <CodeBlock data={executionResult} />
        ) : (
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.7rem', color: '#30363D' }}>
            {status === 'approved' ? 'Executed via MCP domain server' : 'Execution blocked — see decision above'}
          </Typography>
        )}
      </ChainNode>
    </Box>
  );
}

// ── main ───────────────────────────────────────────────────────────────────

const DecisionCenter: React.FC = () => {
  const [history, setHistory] = useState<DecisionRecord[]>([]);
  const [action, setAction] = useState('assign');
  const [assetId, setAssetId] = useState('');
  const [assignee, setAssignee] = useState('');
  const [notes, setNotes] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    try {
      const stored = sessionStorage.getItem(STORAGE_KEY);
      if (stored) setHistory(JSON.parse(stored));
    } catch {}
  }, []);

  const persistHistory = (records: DecisionRecord[]) => {
    setHistory(records);
    try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify(records.slice(0, 50))); } catch {}
  };

  const handleExecute = async () => {
    if (!assetId.trim()) { setError('Asset ID is required'); return; }
    setLoading(true);
    setError(null);
    let request: Record<string, any> = {};
    let result: any;
    try {
      if (action === 'assign') {
        if (!assignee.trim()) throw new Error('Assignee is required for assign action');
        const req = { asset_id: assetId.trim(), assignee: assignee.trim(), notes: notes || undefined };
        request = req;
        result = await equipmentAPI.assignAsset(req);
      } else if (action === 'release') {
        const req = { asset_id: assetId.trim(), released_by: assignee.trim() || 'operator', notes: notes || undefined };
        request = req;
        result = await equipmentAPI.releaseAsset(req);
      } else if (action === 'maintenance') {
        const req = {
          asset_id: assetId.trim(),
          maintenance_type: 'scheduled',
          description: notes || 'Scheduled maintenance',
          scheduled_by: assignee.trim() || 'operator',
          scheduled_for: new Date(Date.now() + 86400000).toISOString(),
        };
        request = req;
        result = await equipmentAPI.scheduleMaintenance(req);
      }
    } catch (err: any) {
      result = { error: err?.response?.data ?? err?.message ?? 'Request failed' };
    }
    const record: DecisionRecord = { id: `${Date.now()}`, action, request, result, timestamp: new Date().toISOString() };
    const next = [record, ...history];
    persistHistory(next);
    setExpanded(record.id);
    setLoading(false);
  };

  const panelSx = {
    backgroundColor: '#0D1117',
    border: '1px solid #1C2128',
    borderRadius: 1,
    overflow: 'hidden',
  };

  const headerSx = {
    px: 1.5, py: 0.75,
    borderBottom: '1px solid #1C2128',
    backgroundColor: '#080C10',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden', p: 1.5, gap: 1.5 }}>

      {/* Pipeline strip */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, flexShrink: 0 }}>
        {['OBSERVE', 'REASON', 'PROPOSE', 'DECIDE', 'EXECUTE'].map((step, i, arr) => (
          <React.Fragment key={step}>
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.67rem', fontWeight: 700, color: '#484F58', letterSpacing: '0.08em' }}>
              {step}
            </Typography>
            {i < arr.length - 1 && (
              <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#21262D' }}>→</Typography>
            )}
          </React.Fragment>
        ))}
        <Box sx={{ flexGrow: 1 }} />
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.63rem', color: '#30363D' }}>
          {history.length} in session
        </Typography>
        {history.length > 0 && (
          <Box
            onClick={() => { persistHistory([]); sessionStorage.removeItem(STORAGE_KEY); }}
            sx={{ fontFamily: 'monospace', fontSize: '0.63rem', color: '#484F58', cursor: 'pointer', '&:hover': { color: '#8B949E' } }}
          >
            [CLEAR]
          </Box>
        )}
      </Box>

      {/* Form */}
      <Box sx={{ ...panelSx, flexShrink: 0 }}>
        <Box sx={headerSx}>
          <Typography sx={{ fontFamily: 'monospace', fontWeight: 700, fontSize: '0.65rem', color: '#8B949E', letterSpacing: '0.1em' }}>
            SUBMIT ACTION TO DECISION PIPELINE
          </Typography>
        </Box>
        <Box sx={{ p: 1.5, display: 'flex', gap: 1.5, flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <FormControl size="small" sx={{ minWidth: 130 }}>
            <InputLabel sx={{ fontFamily: 'monospace', fontSize: '0.75rem' }}>Action</InputLabel>
            <Select value={action} onChange={(e) => setAction(e.target.value)} label="Action" sx={{ fontFamily: 'monospace', fontSize: '0.75rem' }}>
              <MenuItem value="assign" sx={{ fontFamily: 'monospace', fontSize: '0.75rem' }}>assign</MenuItem>
              <MenuItem value="release" sx={{ fontFamily: 'monospace', fontSize: '0.75rem' }}>release</MenuItem>
              <MenuItem value="maintenance" sx={{ fontFamily: 'monospace', fontSize: '0.75rem' }}>maintenance</MenuItem>
            </Select>
          </FormControl>
          <TextField
            size="small"
            label="Asset ID"
            value={assetId}
            onChange={(e) => setAssetId(e.target.value)}
            placeholder="e.g. asset-001"
            InputProps={{ sx: { fontFamily: 'monospace', fontSize: '0.75rem' } }}
            InputLabelProps={{ sx: { fontFamily: 'monospace', fontSize: '0.75rem' } }}
            sx={{ width: 140 }}
          />
          <TextField
            size="small"
            label={action === 'assign' ? 'Assignee *' : 'Operator'}
            value={assignee}
            onChange={(e) => setAssignee(e.target.value)}
            placeholder="username"
            InputProps={{ sx: { fontFamily: 'monospace', fontSize: '0.75rem' } }}
            InputLabelProps={{ sx: { fontFamily: 'monospace', fontSize: '0.75rem' } }}
            sx={{ width: 140 }}
          />
          <TextField
            size="small"
            label="Notes"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="optional"
            InputProps={{ sx: { fontFamily: 'monospace', fontSize: '0.75rem' } }}
            InputLabelProps={{ sx: { fontFamily: 'monospace', fontSize: '0.75rem' } }}
            sx={{ width: 160 }}
          />
          <Box
            onClick={loading ? undefined : handleExecute}
            sx={{
              px: 1.5, py: 0.75,
              border: `1px solid ${loading ? '#21262D' : '#30363D'}`,
              borderRadius: 1, cursor: loading ? 'default' : 'pointer',
              display: 'flex', alignItems: 'center', gap: 0.75,
              '&:hover': { borderColor: loading ? '#21262D' : '#76B900', backgroundColor: loading ? 'transparent' : 'rgba(118,185,0,0.04)' },
            }}
          >
            {loading ? <CircularProgress size={12} sx={{ color: '#484F58' }} /> : null}
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.72rem', fontWeight: 700, color: loading ? '#30363D' : '#76B900', letterSpacing: '0.06em' }}>
              {loading ? 'PROCESSING…' : '[SUBMIT →]'}
            </Typography>
          </Box>
        </Box>
        {error && (
          <Box sx={{ px: 1.5, pb: 1 }}>
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.72rem', color: '#F85149' }}>✕ {error}</Typography>
          </Box>
        )}
      </Box>

      {/* Operations queue table */}
      <Box sx={{ ...panelSx, flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <Box sx={headerSx}>
          <Typography sx={{ fontFamily: 'monospace', fontWeight: 700, fontSize: '0.65rem', color: '#8B949E', letterSpacing: '0.1em' }}>
            OPERATIONS QUEUE
          </Typography>
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#30363D' }}>
            click row for reasoning chain
          </Typography>
        </Box>

        {/* Table header */}
        <Box sx={{ display: 'flex', gap: 2, px: 1.5, py: 0.6, borderBottom: '1px solid #1C2128', backgroundColor: '#080C10', flexShrink: 0 }}>
          <Col w={70} color="#484F58">TIME</Col>
          <Col w={180} color="#484F58">ACTION</Col>
          <Col w={70} color="#484F58">RISK</Col>
          <Col color="#484F58">DECISION</Col>
        </Box>

        {/* Rows */}
        <Box sx={{ flex: 1, overflow: 'auto', '&::-webkit-scrollbar': { width: 3 }, '&::-webkit-scrollbar-thumb': { background: '#21262D' } }}>
          {history.length === 0 ? (
            <Box sx={{ p: 2 }}>
              <Typography sx={{ fontFamily: 'monospace', fontSize: '0.73rem', color: '#30363D' }}>
                — no actions in session — submit an equipment action above —
              </Typography>
            </Box>
          ) : (
            history.map((record) => {
              const status = getDecisionStatus(record.result);
              const risk = RISK_LABEL[record.action] ?? 'MEDIUM';
              const isOpen = expanded === record.id;
              return (
                <Box key={record.id}>
                  <Box
                    onClick={() => setExpanded(isOpen ? null : record.id)}
                    sx={{
                      display: 'flex', gap: 2, px: 1.5, py: 0.75,
                      borderBottom: '1px solid #0D1117',
                      cursor: 'pointer',
                      backgroundColor: isOpen ? 'rgba(88,166,255,0.04)' : 'transparent',
                      '&:hover': { backgroundColor: 'rgba(255,255,255,0.02)' },
                    }}
                  >
                    <Col w={70} color="#484F58">{format(new Date(record.timestamp), 'HH:mm:ss')}</Col>
                    <Box sx={{ width: 180, flexShrink: 0 }}>
                      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.73rem', color: '#C9D1D9', fontWeight: 700 }}>
                        {record.action.toUpperCase()}
                      </Typography>
                      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#484F58' }}>
                        {record.request.asset_id ?? '—'}
                      </Typography>
                    </Box>
                    <Box sx={{ width: 70, flexShrink: 0, display: 'flex', alignItems: 'center' }}>
                      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.68rem', fontWeight: 700, color: RISK_COLOR[risk] ?? '#484F58' }}>
                        {risk}
                      </Typography>
                    </Box>
                    <Box sx={{ flexGrow: 1, display: 'flex', alignItems: 'center', gap: 1 }}>
                      <Box sx={{ width: 6, height: 6, borderRadius: '50%', backgroundColor: STATUS_COLOR[status], boxShadow: status === 'approved' ? `0 0 4px ${STATUS_COLOR[status]}` : 'none', flexShrink: 0 }} />
                      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.73rem', fontWeight: 700, color: STATUS_COLOR[status] }}>
                        {STATUS_LABEL[status]}
                      </Typography>
                    </Box>
                    <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: isOpen ? '#58A6FF' : '#30363D' }}>
                      {isOpen ? '▼' : '▶'}
                    </Typography>
                  </Box>
                  {isOpen && (
                    <Box sx={{ px: 1.5, pb: 1.5 }}>
                      <ReasoningChain record={record} onClose={() => setExpanded(null)} />
                    </Box>
                  )}
                </Box>
              );
            })
          )}
        </Box>
      </Box>
    </Box>
  );
};

export default DecisionCenter;
