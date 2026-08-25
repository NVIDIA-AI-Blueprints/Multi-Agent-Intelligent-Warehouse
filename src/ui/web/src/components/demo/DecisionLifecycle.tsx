/**
 * DecisionLifecycle — visualizes the OBSERVE → REASON → PROPOSE → DECIDE → EXECUTE pipeline.
 *
 * Reads the latest decision from sessionStorage (maiw_decision_history).
 * Shows real telemetry fields only — no fabricated text.
 */

import React from 'react';
import { Box, Typography } from '@mui/material';

const DECISION_STORAGE = 'maiw_decision_history';

interface DecisionRecord {
  id: string;
  action: string;
  request: Record<string, any>;
  result: any;
  timestamp: string;
}

function getStatus(r: DecisionRecord): string {
  const s = r.result?.decision?.status ?? r.result?.decision_result?.status ?? r.result?.status;
  if (s) return s as string;
  if (r.result?.success === true) return 'approved';
  if (r.result?.success === false) return 'rejected';
  if (r.result?.error) return 'error';
  return 'unknown';
}

const STATUS_COLOR: Record<string, string> = {
  approved: '#3FB950',
  rejected: '#F85149',
  requires_human_approval: '#D29922',
  requires_fresh_state: '#58A6FF',
  error: '#F85149',
  unknown: '#484F58',
};

const STATUS_LABEL: Record<string, string> = {
  approved: 'EXECUTED',
  rejected: 'REJECTED',
  requires_human_approval: 'REQUIRES HUMAN APPROVAL',
  requires_fresh_state: 'BLOCKED — STALE STATE',
  error: 'ERROR',
  unknown: '—',
};

interface PipelineNodeProps {
  step: string;
  label: string;
  color: string;
  detail?: string;
  dim?: boolean;
}

function PipelineNode({ step, label, color, detail, dim }: PipelineNodeProps) {
  return (
    <Box sx={{
      display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 0.25,
      opacity: dim ? 0.3 : 1,
      minWidth: 64,
    }}>
      <Box sx={{
        width: 8, height: 8, borderRadius: '50%',
        backgroundColor: dim ? '#21262D' : color,
        boxShadow: dim ? 'none' : `0 0 6px ${color}`,
      }} />
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.55rem', color: dim ? '#21262D' : '#484F58', letterSpacing: '0.06em' }}>
        {step}
      </Typography>
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', fontWeight: 700, color: dim ? '#21262D' : color, textAlign: 'center' }}>
        {label}
      </Typography>
      {detail && !dim && (
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#6E7681', textAlign: 'center', maxWidth: 80, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {detail}
        </Typography>
      )}
    </Box>
  );
}

function Arrow({ dim }: { dim?: boolean }) {
  return (
    <Typography sx={{ fontFamily: 'monospace', fontSize: '0.75rem', color: dim ? '#21262D' : '#30363D', alignSelf: 'center', flexShrink: 0 }}>
      →
    </Typography>
  );
}

const DecisionLifecycle: React.FC = () => {
  const [latest, setLatest] = React.useState<DecisionRecord | null>(null);

  React.useEffect(() => {
    const read = () => {
      try {
        const arr: DecisionRecord[] = JSON.parse(sessionStorage.getItem(DECISION_STORAGE) ?? '[]');
        setLatest(arr[0] ?? null);
      } catch { setLatest(null); }
    };
    read();
    const id = setInterval(read, 2000);
    return () => clearInterval(id);
  }, []);

  const status = latest ? getStatus(latest) : null;
  const statusColor = status ? (STATUS_COLOR[status] ?? '#484F58') : '#484F58';
  const statusLabel = status ? (STATUS_LABEL[status] ?? '—') : null;

  // Extract fields from nested result paths
  const agent = latest?.result?.agent ?? latest?.result?.decision?.agent ?? null;
  const model = latest?.result?.model ?? latest?.result?.decision?.model ?? null;
  const proposalId = latest?.result?.proposal?.proposal_id ?? latest?.result?.proposal_id ?? null;
  const decisionId = latest?.result?.decision?.result_id ?? latest?.result?.decision_id ?? null;
  const execResult = latest?.result?.execution ?? null;
  const isBlocked = status === 'requires_fresh_state' || status === 'requires_human_approval';
  const isExecuted = status === 'approved';

  const noDecision = !latest;

  return (
    <Box sx={{
      backgroundColor: '#0D1117',
      border: '1px solid #1C2128',
      borderRadius: 1,
    }}>
      <Box sx={{ px: 1.5, py: 0.75, borderBottom: '1px solid #1C2128', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Typography sx={{ fontFamily: 'monospace', fontWeight: 700, fontSize: '0.6rem', color: '#8B949E', letterSpacing: '0.1em' }}>
          DECISION LIFECYCLE
        </Typography>
        {status && (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
            <Box sx={{ width: 5, height: 5, borderRadius: '50%', backgroundColor: statusColor }} />
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', fontWeight: 700, color: statusColor }}>
              {statusLabel}
            </Typography>
          </Box>
        )}
      </Box>
      <Box sx={{ px: 1.5, py: 1, display: 'flex', alignItems: 'flex-start', gap: 0.5 }}>
        <PipelineNode step="01" label="OBSERVE" color="#58A6FF"
          detail={latest?.request?.asset_id ?? latest?.request?.zone ?? undefined}
          dim={noDecision} />
        <Arrow dim={noDecision} />
        <PipelineNode step="02" label="REASON" color="#58A6FF"
          detail={agent ?? model ?? undefined}
          dim={noDecision} />
        <Arrow dim={noDecision} />
        <PipelineNode step="03" label="PROPOSE" color="#D29922"
          detail={latest ? latest.action.toUpperCase() : undefined}
          dim={noDecision} />
        <Arrow dim={noDecision} />
        <PipelineNode step="04" label="DECIDE" color={statusColor}
          detail={decisionId ? `d:${decisionId.slice(0, 8)}` : undefined}
          dim={noDecision} />
        <Arrow dim={noDecision} />
        <PipelineNode step="05" label="EXECUTE" color={isExecuted ? '#3FB950' : isBlocked ? '#484F58' : '#30363D'}
          detail={isExecuted ? 'MCP WRITE' : isBlocked ? 'BLOCKED' : undefined}
          dim={noDecision || isBlocked} />
        <Arrow dim={noDecision || !isExecuted} />
        <PipelineNode step="06" label="OBSERVE" color={isExecuted ? '#3FB950' : '#30363D'}
          detail={isExecuted ? 'OUTCOME' : undefined}
          dim={noDecision || !isExecuted} />
      </Box>

      {noDecision && (
        <Box sx={{ px: 1.5, pb: 0.75 }}>
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#21262D' }}>
            No decisions this session — use Decisions view to trigger equipment actions.
          </Typography>
        </Box>
      )}

      {/* Safety outcomes — must be visually distinct */}
      {status === 'requires_fresh_state' && (
        <Box sx={{ mx: 1.5, mb: 0.75, px: 1, py: 0.5, border: '1px solid #58A6FF', borderRadius: 0.5, backgroundColor: '#58A6FF10' }}>
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#58A6FF', fontWeight: 700 }}>
            ◌ REQUIRES_FRESH_STATE — execution blocked. Snapshot stale; re-observe before retry.
          </Typography>
        </Box>
      )}
      {status === 'requires_human_approval' && (
        <Box sx={{ mx: 1.5, mb: 0.75, px: 1, py: 0.5, border: '1px solid #D29922', borderRadius: 0.5, backgroundColor: '#D2992210' }}>
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#D29922', fontWeight: 700 }}>
            ● REQUIRES_HUMAN_APPROVAL — action proposed; no execution until operator approves.
          </Typography>
        </Box>
      )}
      {status === 'rejected' && (
        <Box sx={{ mx: 1.5, mb: 0.75, px: 1, py: 0.5, border: '1px solid #F85149', borderRadius: 0.5, backgroundColor: '#F8514910' }}>
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#F85149', fontWeight: 700 }}>
            ✕ REJECTED — decision engine rejected proposal. executed=false.
          </Typography>
        </Box>
      )}
    </Box>
  );
};

export default DecisionLifecycle;
