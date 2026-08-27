import React from 'react';
import { Box, Typography } from '@mui/material';
import { RuntimeStatus } from '../../services/api';

type DomainStatus = 'HEALTHY' | 'DEGRADED' | 'CIRCUIT OPEN' | undefined;

const STATUS_COLOR: Record<string, string> = {
  HEALTHY: '#3FB950',
  DEGRADED: '#D29922',
  'CIRCUIT OPEN': '#F85149',
};

function StatusDot({ status }: { status: string | undefined }) {
  const color = status ? (STATUS_COLOR[status] ?? '#484F58') : '#30363D';
  return (
    <Box sx={{
      width: 5, height: 5, borderRadius: '50%', flexShrink: 0,
      backgroundColor: color,
      boxShadow: status === 'HEALTHY' ? `0 0 4px ${color}` : 'none',
    }} />
  );
}

function DomainHealthRow({ label, status }: { label: string; status: DomainStatus }) {
  const color = status ? (STATUS_COLOR[status] ?? '#484F58') : '#30363D';
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, py: 0.3 }}>
      <StatusDot status={status} />
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.7rem', color: '#8B949E', flexGrow: 1 }}>
        {label}
      </Typography>
      <Typography sx={{
        fontFamily: 'monospace', fontSize: '0.62rem', fontWeight: 700,
        color: status === 'CIRCUIT OPEN' ? color : (status ? color : '#30363D'),
      }}>
        {status ?? '—'}
      </Typography>
    </Box>
  );
}

interface Props {
  runtime: RuntimeStatus | undefined;
}

export default function ReliabilityPanel({ runtime }: Props) {
  const opStatus = runtime?.maiw_operational_status;
  const gwStatus = runtime?.model_gateway_status;
  const domainHealth = runtime?.domain_health;
  const circuitStates = runtime?.circuit_states;

  const nimState = circuitStates?.nim?.state;

  const opColor = opStatus === 'HEALTHY' ? '#3FB950' : opStatus === 'DEGRADED' ? '#D29922' : '#484F58';

  return (
    <Box>
      {/* Operational status header */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.75 }}>
        <Box sx={{
          display: 'inline-flex', alignItems: 'center', gap: 0.5,
          px: 0.75, py: 0.2,
          border: `1px solid ${opColor}44`,
          borderRadius: 0.5,
          backgroundColor: `${opColor}11`,
        }}>
          <Box sx={{ width: 5, height: 5, borderRadius: '50%', backgroundColor: opColor }} />
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', fontWeight: 700, color: opColor, letterSpacing: '0.08em' }}>
            {opStatus ?? 'UNKNOWN'}
          </Typography>
        </Box>
        {nimState && nimState !== 'CLOSED' && (
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#F85149' }}>
            NIM {nimState}
          </Typography>
        )}
        {gwStatus && gwStatus !== 'HEALTHY' && (
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.6rem', color: '#D29922' }}>
            GW: {gwStatus}
          </Typography>
        )}
      </Box>

      {/* Domain health grid */}
      {domainHealth ? (
        <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 12px' }}>
          <DomainHealthRow label="Equipment" status={domainHealth.equipment} />
          <DomainHealthRow label="Labor"     status={domainHealth.labor} />
          <DomainHealthRow label="Wave"      status={domainHealth.wave} />
          <DomainHealthRow label="Inventory" status={domainHealth.inventory} />
        </Box>
      ) : (
        <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 12px' }}>
          {(['Equipment', 'Labor', 'Wave', 'Inventory'] as const).map((d) => (
            <DomainHealthRow key={d} label={d} status={undefined} />
          ))}
        </Box>
      )}

      {/* Circuit state summary if any domain is not healthy */}
      {circuitStates?.domains && circuitStates.domains.some(d => d.state !== 'CLOSED') && (
        <Box sx={{ mt: 0.75, pt: 0.5, borderTop: '1px solid #1C2128' }}>
          {circuitStates.domains
            .filter(d => d.state !== 'CLOSED')
            .map(d => (
              <Box key={d.name} sx={{ display: 'flex', gap: 0.75, alignItems: 'center', py: 0.2 }}>
                <Box sx={{ width: 5, height: 5, borderRadius: '50%', backgroundColor: '#F85149', flexShrink: 0 }} />
                <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: '#F85149' }}>
                  {d.name.toUpperCase()} CIRCUIT {d.state}
                </Typography>
                <Typography sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#484F58' }}>
                  ({d.failure_count} failures)
                </Typography>
              </Box>
            ))}
        </Box>
      )}
    </Box>
  );
}
