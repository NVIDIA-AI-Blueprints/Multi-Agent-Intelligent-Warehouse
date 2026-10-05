/**
 * DeploymentSecurity.tsx — Platform/Security persona surface (UX-1G Step 27–35).
 *
 * Shows the minimal deployment/security state required for a Platform or Security
 * Engineer to verify MAIW v2 reference deployment posture:
 *   - Deployment identity (SHA, qualification scope)
 *   - Version matrix (MAIW, NemoClaw, OpenShell, approved model)
 *   - Sandbox status and capability policy (READ allowed, WRITE denied)
 *   - Model policy (approved Nemotron 3/3.5, Llama-family rejected)
 *   - Network boundary (ModelGateway only, direct provider denied)
 *   - Auth state (inference endpoint, fail-closed)
 *   - Persistence status (ProcedureStateStore, GovernanceInbox)
 *   - Deployment readiness (from /api/v1/runtime/status)
 *
 * INVARIANTS enforced here:
 *   - Sandbox isolation ≠ Governance approval
 *   - Model availability ≠ Model eligibility
 *   - WRITE always shown as denied (never as allowed in sandbox)
 *   - Auth is shown as enabled — if development override detected, surface as WARNING
 *   - Qualification scope is "qualified reference deployment", NOT production HA
 *
 * This is NOT a full security admin console. It is a single-page read-only
 * deployment status surface. No secrets are displayed.
 */

import React from 'react';
import {
  Box,
  Typography,
  Grid,
  CircularProgress,
} from '@mui/material';
import {
  CheckCircle as OkIcon,
  Warning as WarnIcon,
  Block as DeniedIcon,
  Shield as PolicyIcon,
  Storage as PersistIcon,
  Token as ModelIcon,
} from '@mui/icons-material';
import { useRuntimeStatus } from '../hooks/useRuntimeStatus';

// ── Qualification metadata (from artifacts/deployment/reference_deployment_qualification.json) ──

const QUALIFICATION = {
  schema_version: '1.0',
  phase: '20C-C',
  title: 'MAIW v2 Reference Deployment Operationalization Qualification',
  qualification_timestamp: '2026-10-05T00:00:00Z',
  qualification_scope: 'qualified reference deployment — single-node, H100, development/demo use',
  maiw_sha: '1c8606a',
  nvidia_main_branch: 'nvidia/main',
  versions: {
    nemoclaw: '0.0.124',
    openshell: '0.0.116',
    python_min: '3.12',
  },
  approved_model: {
    model_id: 'nvidia/nemotron-3-super-120b-a12b',
    generation: 'Nemotron 3',
    approved_family: true,
    provider: 'integrate.api.nvidia.com/v1 (via MAIW ModelGateway)',
    qualified_latency_ms: 572.52,
  },
  policy: {
    approved_generations: ['nemotron-3', 'nemotron-3.5'],
    llama_family_rejected: true,
    qwen_rejected: true,
  },
  auth: {
    endpoint: 'POST /api/v1/inference',
    auth_header: 'X-Maiw-Internal-Token',
    fail_closed: true,
    allow_unauthenticated_in_reference: false,
  },
  sandbox: {
    mode: 'required',
    runtime: 'OpenShell (openshell 0.0.116)',
    allowed_capability_classes: ['READ', 'ANALYTICAL', 'PROPOSAL'],
    denied_capability_classes: ['WRITE', 'EMERGENCY_WRITE'],
    provider_credential_in_sandbox: false,
    warehouse_write_credential_in_sandbox: false,
    action_executor_in_sandbox: false,
  },
  network: {
    sandbox_to_modelgateway: 'allowed',
    sandbox_to_direct_provider: 'denied',
    note: 'Sandbox → MAIW ModelGateway: allowed. Sandbox → direct NIM/provider: denied.',
  },
  persistence: {
    procedure_state: {
      class: 'JsonFileProcedureStateStore',
      location: '/var/lib/maiw/procedures/',
      durability: 'single-node, atomic write, survives process restart',
      revision_control: 'optimistic concurrency (StaleRevisionError)',
    },
    governance_inbox: {
      class: 'JsonFileGovernanceInbox',
      location: '/var/lib/maiw/governance/governance_inbox.jsonl',
      durability: 'single-node, append-only JSONL, survives process restart',
    },
    ha_designation: 'NOT HA — qualified reference deployment only',
  },
};

// ── Section header ────────────────────────────────────────────────────────────

function SectionHeader({ icon, title, subtitle }: {
  icon?: React.ReactNode;
  title: string;
  subtitle?: string;
}) {
  return (
    <Box sx={{ mb: 1.5 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
        {icon && <Box sx={{ color: '#8B949E', display: 'flex' }}>{icon}</Box>}
        <Typography sx={{
          fontFamily: 'monospace', fontSize: '0.62rem', fontWeight: 700,
          color: '#8B949E', letterSpacing: '0.14em', textTransform: 'uppercase',
        }}>
          {title}
        </Typography>
      </Box>
      {subtitle && (
        <Typography sx={{ fontFamily: 'monospace', fontSize: '0.57rem', color: '#484F58', mt: '2px' }}>
          {subtitle}
        </Typography>
      )}
    </Box>
  );
}

// ── Security card ─────────────────────────────────────────────────────────────

type CardStatus = 'ok' | 'warn' | 'denied' | 'info';

function statusIcon(s: CardStatus, size = 16) {
  const sz = { fontSize: size };
  const m: Record<CardStatus, React.ReactNode> = {
    ok:     <OkIcon sx={{ ...sz, color: '#3FB950' }} />,
    warn:   <WarnIcon sx={{ ...sz, color: '#D29922' }} />,
    denied: <DeniedIcon sx={{ ...sz, color: '#F85149' }} />,
    info:   <OkIcon sx={{ ...sz, color: '#58A6FF' }} />,
  };
  return m[s];
}

function SecurityCard({
  title,
  status,
  detail,
  mono = true,
  testId,
}: {
  title: string;
  status: CardStatus;
  detail?: string;
  mono?: boolean;
  testId?: string;
}) {
  const borderColor: Record<CardStatus, string> = {
    ok:     '#3FB95033',
    warn:   '#D2992244',
    denied: '#F8514933',
    info:   '#58A6FF33',
  };
  return (
    <Box
      data-testid={testId}
      aria-label={`${title}: ${detail ?? status}`}
      sx={{
        backgroundColor: '#0D1117',
        border: `1px solid ${borderColor[status]}`,
        borderRadius: 1.5,
        p: 1.5,
        display: 'flex',
        alignItems: 'flex-start',
        gap: 1,
        height: '100%',
      }}
    >
      <Box sx={{ flexShrink: 0, mt: '1px' }}>{statusIcon(status)}</Box>
      <Box>
        <Typography sx={{ fontWeight: 700, fontSize: '0.8rem', color: '#C9D1D9', mb: '2px' }}>
          {title}
        </Typography>
        {detail && (
          <Typography sx={{
            fontSize: '0.68rem',
            color: '#8B949E',
            fontFamily: mono ? 'monospace' : 'inherit',
            wordBreak: 'break-all',
          }}>
            {detail}
          </Typography>
        )}
      </Box>
    </Box>
  );
}

// ── Policy row (capability allow/deny) ───────────────────────────────────────

function CapabilityRow({ name, allowed }: { name: string; allowed: boolean }) {
  const color = allowed ? '#3FB950' : '#F85149';
  const label = allowed ? 'ALLOWED' : 'DENIED';
  const dot = allowed ? <OkIcon sx={{ fontSize: 14, color }} /> : <DeniedIcon sx={{ fontSize: 14, color }} />;
  return (
    <Box
      data-testid={`capability-${name.toLowerCase().replace(/[^a-z0-9]/g, '-')}`}
      sx={{ display: 'flex', alignItems: 'center', gap: 1, py: 0.3 }}
    >
      {dot}
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.7rem', color: '#8B949E', flexGrow: 1 }}>
        {name}
      </Typography>
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', fontWeight: 700, color }}>
        {label}
      </Typography>
    </Box>
  );
}

// ── Model policy row ──────────────────────────────────────────────────────────

function ModelPolicyRow({ generation, approved }: { generation: string; approved: boolean }) {
  const color = approved ? '#3FB950' : '#F85149';
  const label = approved ? 'APPROVED' : 'REJECTED';
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, py: 0.3 }}>
      <ModelIcon sx={{ fontSize: 14, color }} />
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.7rem', color: '#8B949E', flexGrow: 1 }}>
        {generation}
      </Typography>
      <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', fontWeight: 700, color }}>
        {label}
      </Typography>
    </Box>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

const DeploymentSecurity: React.FC = () => {
  const { data: runtime, isLoading } = useRuntimeStatus();

  // Deployment readiness: READY only if runtime is initialized and healthy
  const isReady = runtime?.runtime_initialized === true
    && runtime?.model_gateway_available === true
    && runtime?.maiw_operational_status !== 'DEGRADED';
  const readinessLabel = isLoading
    ? 'LOADING'
    : !runtime?.runtime_initialized
    ? 'NOT READY'
    : isReady ? 'READY' : 'DEGRADED';
  const readinessColor = isLoading
    ? '#484F58'
    : !runtime?.runtime_initialized
    ? '#F85149'
    : isReady ? '#3FB950' : '#D29922';

  return (
    <Box sx={{ pb: 4 }}>
      {/* Page header */}
      <Box sx={{ mb: 3, display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
        <Box>
          <Typography variant="h4" sx={{ fontWeight: 700, color: 'text.primary', letterSpacing: '-0.02em' }}>
            Deployment Security
          </Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary', mt: 0.5 }}>
            Platform / Security Engineer view — runtime posture, model policy, sandbox isolation, auth state
          </Typography>
        </Box>
        {isLoading && <CircularProgress size={20} sx={{ mt: 0.5 }} />}
      </Box>

      {/* Qualification scope notice */}
      <Box
        data-testid="qualification-scope-notice"
        sx={{
          backgroundColor: '#161B22',
          border: '1px solid #30363D',
          borderRadius: 1.5,
          px: 2, py: 1.25,
          mb: 3,
          display: 'flex', alignItems: 'center', gap: 1,
        }}
      >
        <PolicyIcon sx={{ fontSize: 16, color: '#58A6FF', flexShrink: 0 }} />
        <Box>
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.68rem', color: '#C9D1D9', fontWeight: 700 }}>
            {QUALIFICATION.title}
          </Typography>
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.62rem', color: '#8B949E' }}>
            Scope: {QUALIFICATION.qualification_scope}
          </Typography>
        </Box>
      </Box>

      {/* Deployment readiness */}
      <Box sx={{ mb: 3 }}>
        <SectionHeader title="Deployment Readiness" />
        <Box
          data-testid="deployment-readiness"
          sx={{
            display: 'inline-flex', alignItems: 'center', gap: 0.75,
            px: 1.5, py: 0.75,
            backgroundColor: '#0D1117',
            border: `1px solid ${readinessColor}33`,
            borderRadius: 1,
          }}
        >
          <Box sx={{ width: 8, height: 8, borderRadius: '50%', backgroundColor: readinessColor }} />
          <Typography sx={{
            fontFamily: 'monospace', fontSize: '0.78rem', fontWeight: 700,
            color: readinessColor, letterSpacing: '0.08em',
          }}>
            {readinessLabel}
          </Typography>
          {readinessLabel === 'DEGRADED' && (
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#D29922', ml: 1 }}>
              — check System Health for failing component
            </Typography>
          )}
          {readinessLabel === 'NOT READY' && (
            <Typography sx={{ fontFamily: 'monospace', fontSize: '0.65rem', color: '#F85149', ml: 1 }}>
              — runtime not initialized
            </Typography>
          )}
        </Box>
      </Box>

      {/* Version matrix */}
      <Box sx={{ mb: 3 }}>
        <SectionHeader
          title="Version Matrix"
          subtitle="Qualified component versions for this reference deployment"
        />
        <Grid container spacing={1.5}>
          <Grid item xs={12} sm={6} md={3}>
            <SecurityCard
              testId="version-maiw-sha"
              title="MAIW SHA"
              status="ok"
              detail={QUALIFICATION.maiw_sha + ' (nvidia/main)'}
            />
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <SecurityCard
              testId="version-nemoclaw"
              title="NemoClaw"
              status="ok"
              detail={`v${QUALIFICATION.versions.nemoclaw}`}
            />
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <SecurityCard
              testId="version-openshell"
              title="OpenShell"
              status="ok"
              detail={`v${QUALIFICATION.versions.openshell}`}
            />
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <SecurityCard
              testId="version-approved-model"
              title="Selected Approved Model"
              status="ok"
              detail={`${QUALIFICATION.approved_model.model_id} (${QUALIFICATION.approved_model.generation})`}
            />
          </Grid>
        </Grid>
      </Box>

      {/* Sandbox status */}
      <Box sx={{ mb: 3 }}>
        <SectionHeader
          icon={<PolicyIcon sx={{ fontSize: 14 }} />}
          title="Sandbox Status"
          subtitle="OpenShell sandbox — capability policy enforced at boundary"
        />
        <Grid container spacing={1.5} sx={{ mb: 1.5 }}>
          <Grid item xs={12} sm={6} md={4}>
            <SecurityCard
              testId="sandbox-runtime"
              title="Runtime"
              status="ok"
              detail={QUALIFICATION.sandbox.runtime}
            />
          </Grid>
          <Grid item xs={12} sm={6} md={4}>
            <SecurityCard
              testId="sandbox-provider-cred"
              title="Provider Credential in Sandbox"
              status="ok"
              detail="Not present — credential never passed into sandbox"
            />
          </Grid>
          <Grid item xs={12} sm={6} md={4}>
            <SecurityCard
              testId="sandbox-executor"
              title="ActionExecutor in Sandbox"
              status="ok"
              detail="Not present — execution authority outside sandbox boundary"
            />
          </Grid>
        </Grid>
        <Box
          sx={{
            backgroundColor: '#161B22',
            border: '1px solid #21262D',
            borderRadius: 1.5,
            p: 1.5,
          }}
        >
          <Typography sx={{
            fontFamily: 'monospace', fontSize: '0.6rem', color: '#484F58',
            letterSpacing: '0.06em', textTransform: 'uppercase', mb: 0.75,
          }}>
            Effective Capability Policy
          </Typography>
          {QUALIFICATION.sandbox.allowed_capability_classes.map(c => (
            <CapabilityRow key={c} name={c} allowed={true} />
          ))}
          {QUALIFICATION.sandbox.denied_capability_classes.map(c => (
            <CapabilityRow key={c} name={c} allowed={false} />
          ))}
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#484F58', mt: 0.75 }}>
            Sandbox isolation ≠ governance approval. WRITE denial is enforced at the sandbox boundary, independent of the governance decision.
          </Typography>
        </Box>
      </Box>

      {/* Model policy */}
      <Box sx={{ mb: 3 }}>
        <SectionHeader
          icon={<ModelIcon sx={{ fontSize: 14 }} />}
          title="Model Policy"
          subtitle="Approved model-family policy — eligibility is family-scoped, not checkpoint-specific"
        />
        <Grid container spacing={1.5} sx={{ mb: 1.5 }}>
          <Grid item xs={12} sm={6} md={4}>
            <SecurityCard
              testId="model-policy-selected"
              title="Current Selected Model"
              status="ok"
              detail={QUALIFICATION.approved_model.model_id}
            />
          </Grid>
          <Grid item xs={12} sm={6} md={4}>
            <SecurityCard
              testId="model-policy-generation"
              title="Model Generation"
              status="ok"
              detail={`${QUALIFICATION.approved_model.generation} (approved)`}
            />
          </Grid>
          <Grid item xs={12} sm={6} md={4}>
            <SecurityCard
              testId="model-policy-latency"
              title="Qualified Latency"
              status="ok"
              detail={`${QUALIFICATION.approved_model.qualified_latency_ms} ms (reference)`}
            />
          </Grid>
        </Grid>
        <Box
          sx={{
            backgroundColor: '#161B22',
            border: '1px solid #21262D',
            borderRadius: 1.5,
            p: 1.5,
          }}
        >
          <Typography sx={{
            fontFamily: 'monospace', fontSize: '0.6rem', color: '#484F58',
            letterSpacing: '0.06em', textTransform: 'uppercase', mb: 0.75,
          }}>
            Approved Family Policy
          </Typography>
          <ModelPolicyRow generation="nemotron-3 (e.g. nemotron-3-super-120b-a12b)" approved={true} />
          <ModelPolicyRow generation="nemotron-3.5 (e.g. nemotron-3.5-lightning-30b-a3b)" approved={true} />
          <ModelPolicyRow generation="Llama-family (all variants)" approved={false} />
          <ModelPolicyRow generation="Qwen-family (all variants)" approved={false} />
          <Typography sx={{ fontFamily: 'monospace', fontSize: '0.58rem', color: '#484F58', mt: 0.75 }}>
            Model availability ≠ model eligibility. A model being reachable does not make it production-eligible.
          </Typography>
        </Box>
      </Box>

      {/* Network boundary */}
      <Box sx={{ mb: 3 }}>
        <SectionHeader
          title="Network Boundary"
          subtitle="Inference path: sandbox → MAIW ModelGateway → NIM provider"
        />
        <Grid container spacing={1.5}>
          <Grid item xs={12} sm={6}>
            <SecurityCard
              testId="network-sandbox-to-gateway"
              title="Sandbox → MAIW ModelGateway"
              status="ok"
              detail="Allowed — all inference routed through ModelGateway"
            />
          </Grid>
          <Grid item xs={12} sm={6}>
            <SecurityCard
              testId="network-sandbox-to-provider"
              title="Sandbox → Direct NIM / Provider"
              status="denied"
              detail="Denied — sandbox cannot call provider API directly"
            />
          </Grid>
        </Grid>
      </Box>

      {/* Auth state */}
      <Box sx={{ mb: 3 }}>
        <SectionHeader
          title="Auth State"
          subtitle="Inference endpoint authentication — fail-closed"
        />
        <Grid container spacing={1.5}>
          <Grid item xs={12} sm={6} md={3}>
            <SecurityCard
              testId="auth-endpoint"
              title="Inference Endpoint"
              status="ok"
              detail={QUALIFICATION.auth.endpoint}
            />
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <SecurityCard
              testId="auth-header"
              title="Auth Header"
              status="ok"
              detail={QUALIFICATION.auth.auth_header}
            />
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <SecurityCard
              testId="auth-fail-closed"
              title="Fail-Closed"
              status="ok"
              detail="Enabled — auth failure blocks inference"
            />
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <SecurityCard
              testId="auth-dev-override"
              title="Dev Unauthenticated Override"
              status={QUALIFICATION.auth.allow_unauthenticated_in_reference ? 'warn' : 'ok'}
              detail={QUALIFICATION.auth.allow_unauthenticated_in_reference
                ? 'ENABLED — development override active (WARNING)'
                : 'Disabled — reference profile requires auth'}
            />
          </Grid>
        </Grid>
      </Box>

      {/* Persistence status */}
      <Box sx={{ mb: 3 }}>
        <SectionHeader
          icon={<PersistIcon sx={{ fontSize: 14 }} />}
          title="Persistence Status"
          subtitle="Durable state stores — single-node, not HA"
        />
        <Grid container spacing={1.5}>
          <Grid item xs={12} sm={6}>
            <SecurityCard
              testId="persist-procedure-state"
              title="ProcedureStateStore"
              status="ok"
              detail={`${QUALIFICATION.persistence.procedure_state.class} · ${QUALIFICATION.persistence.procedure_state.location} · ${QUALIFICATION.persistence.procedure_state.durability}`}
            />
          </Grid>
          <Grid item xs={12} sm={6}>
            <SecurityCard
              testId="persist-governance-inbox"
              title="GovernanceInbox"
              status="ok"
              detail={`${QUALIFICATION.persistence.governance_inbox.class} · ${QUALIFICATION.persistence.governance_inbox.location} · ${QUALIFICATION.persistence.governance_inbox.durability}`}
            />
          </Grid>
          <Grid item xs={12}>
            <Box sx={{
              backgroundColor: '#0D1117',
              border: '1px solid #D2992233',
              borderRadius: 1.5,
              px: 1.5, py: 1,
              display: 'flex', alignItems: 'center', gap: 1,
            }}>
              <WarnIcon sx={{ fontSize: 16, color: '#D29922', flexShrink: 0 }} />
              <Typography sx={{ fontFamily: 'monospace', fontSize: '0.68rem', color: '#D29922' }}>
                {QUALIFICATION.persistence.ha_designation}
              </Typography>
            </Box>
          </Grid>
        </Grid>
      </Box>

      {/* Footer note */}
      <Typography
        variant="caption"
        sx={{ color: '#484F58', display: 'block', mt: 2, fontFamily: 'monospace' }}
      >
        Qualification phase: {QUALIFICATION.phase} · Timestamp: {QUALIFICATION.qualification_timestamp} ·
        This surface is not a full security admin console — use your SIEM/audit tooling for production monitoring.
      </Typography>
    </Box>
  );
};

export default DeploymentSecurity;
