import axios from 'axios';

// Reuse the same relative base to go through the proxy
const API_BASE = '/api/v1';

const http = axios.create({ baseURL: API_BASE, timeout: 15000, allowAbsoluteUrls: false } as any);

// ── Types ─────────────────────────────────────────────────────────────────────

export interface ScenarioMeta {
  name: string;
  display_name: string;
  description: string;
  tags: string[];
}

export interface DemoWorldSummary {
  warehouse_id: string;
  clock_iso: string;
  elapsed_seconds: number;
  equipment: { total: number; available: number; assigned: number; maintenance: number; offline: number };
  workers: { total: number; active: number; inactive: number };
  tasks: { total: number; pending: number; in_progress: number; completed: number };
  inventory: { total_skus: number; low_stock: number };
}

export interface PendingApproval {
  pending_id: string;
  proposal_id: string;
  decision_id: string;
  trace_id: string;
  capability: string;
  target: string;
  domain: string;
  risk_level: string;
  objective: string;
  rationale: string;
  priority: 'critical' | 'high' | 'medium' | 'low';
  queued_at: string;
}

export interface DemoStatus {
  active: boolean;
  paused: boolean;
  scenario: ScenarioMeta | null;
  world: DemoWorldSummary | null;
  current_kpis: KPISnapshot | null;
  kpi_history: KPISnapshot[];
  pending_approvals: PendingApproval[];
}

export type InjectEventType =
  | 'equipment_fault'
  | 'equipment_restore'
  | 'low_stock'
  | 'worker_absence'
  | 'worker_return'
  | 'task_deadline'
  | 'wave_delay';

export interface RecommendedAction {
  domain: 'equipment' | 'labor' | 'wave' | 'inventory';
  capability: string;
  target: string;
  objective: string;
  rationale: string;
  priority: 'critical' | 'high' | 'medium' | 'low';
  subtype: string | null;
}

export interface AnalysisAssessment {
  snapshot_id: string;
  warehouse_id: string;
  assessed_at: string;
  summary: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  domains_affected: string[];
  facts_observed: string[];
  recommendations: RecommendedAction[];
  model_id: string;
  routing_rule: string;
  routing_reason: string;
  latency_ms: number;
}

export interface LifecycleRecord {
  phase: 'OBSERVE' | 'REASON' | 'SKILL' | 'PROPOSE' | 'DECIDE' | 'EXECUTE' | 'OBSERVE_OUTCOME';
  [key: string]: any;
}

export interface KPISnapshot {
  sim_time_seconds: number;
  clock_iso: string;
  // EXACT metrics
  equipment_total: number;
  equipment_operational_pct: number;
  labor_total: number;
  labor_availability_pct: number;
  labor_utilization_pct: number;
  pending_backlog: number;
  wave_risk_score: number;
  wave_risk_level: 'none' | 'low' | 'medium' | 'high' | 'critical';
  low_stock_count: number;
  state_freshness_seconds: number | null;
  // SIMULATION-DERIVED PROXY metrics
  service_risk_index: number;
  capacity_throughput_proxy: number;
  // EXACT WITHIN SIMULATION — new in Increment 2
  wave_completion_pct: number;        // completed wave tasks / total wave tasks * 100
  simulated_throughput: number;       // work units completed in last 3600 sim-seconds
  // SIMULATION-DERIVED — new in Increment 2
  projected_service_level: number;    // fraction of deadline tasks projected on-time (0-100)
  time_to_recovery_seconds: number | null;  // null until recovery conditions met
}

export interface KPIDelta {
  equipment_operational_pct: number;
  labor_availability_pct: number;
  labor_utilization_pct: number;
  pending_backlog: number;
  wave_risk_score: number;
  low_stock_count: number;
  service_risk_index: number;
  capacity_throughput_proxy: number;
  wave_completion_pct: number;
  simulated_throughput: number;
  projected_service_level: number;
}

export interface KPITiming {
  time_to_detect_ms: number | null;
  time_to_decision_ms: number;
  time_to_execution_ms: number;
}

export interface AnalysisResult {
  ok: boolean;
  trace_id: string;
  assessment: AnalysisAssessment;
  proposal_results: Array<{ status: string; capability: string; [key: string]: any }>;
  lifecycle: LifecycleRecord[];
  pre_kpis?: KPISnapshot;
  post_kpis?: KPISnapshot;
  kpi_delta?: KPIDelta;
  timing?: KPITiming;
}

// ── Phase 15B Copilot types ───────────────────────────────────────────────────

export interface CopilotEvidenceFact {
  label: string;
  value: string;
  severity: string | null;  // "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | null — from backend, not derived
}

export interface CopilotNeighborhood {
  focus_entity_id: string | null;
  focus_entity_label: string | null;
  entity_count: number;
  relationship_summary: Record<string, string[]>;
  graph_available: boolean;
}

export interface CopilotRecommendation {
  recommendation_id: string;
  domain: string;
  capability: string;
  target: string;
  objective: string;
  rationale: string;
  priority: string;
  subtype: string | null;
  focus_entity_id: string | null;
  snapshot_id: string;
  trace_id: string;
  conversation_id: string;
  turn_id: string;
}


export interface CopilotTurnResponse {
  conversation_id: string;
  turn_id: string;
  trace_id: string;
  intent: string;                    // "ask" | "analyze" | "act"
  status: string;                    // "complete" | "degraded" | "error" | "not_implemented"
  answer: string | null;
  // ASK fields
  evidence: CopilotEvidenceFact[] | null;
  neighborhood: CopilotNeighborhood | null;
  agent: string | null;
  skills_used: string[] | null;
  skills_available: string[] | null;
  model_id: string | null;
  reasoning_level: string | null;
  routing_rule: string | null;
  routing_reason: string | null;
  requested_role: string | null;
  selected_role: string | null;
  fallback_from: string | null;
  fallback_reason: string | null;
  latency_ms: number | null;
  degraded: boolean;
  degradation_reason: string | null;
  answerability: string;             // "answerable" | "insufficient_evidence" | "partial"
  missing_context: string[];
  timing: Record<string, number>;
  // ANALYZE fields
  summary: string | null;
  severity: string | null;
  recommendations: CopilotRecommendation[] | null;
  focus_entity_id: string | null;
  focus_entity_label: string | null;
  safety_note: string | null;
  related_artifacts: Record<string, unknown>;
  store_note: string;
  // ACT fields (present only when intent === 'act')
  act_recommendation_id?: string | null;
  act_decision_outcome?: string | null;
  act_proposal_id?: string | null;
  act_decision_id?: string | null;
  act_pending_approval_id?: string | null;
  act_approval_required?: boolean;
  act_execution_status?: string | null;
  act_execution_id?: string | null;
  act_mutation_state?: string | null;   // "NOT_ATTEMPTED" | "CONFIRMED" | "UNKNOWN"
  act_violations?: Array<{ code: string; message: string }>;
  act_source_snapshot_id?: string | null;
  // OBSERVE_OUTCOME fields (present only when intent === 'observe_outcome')
  observe_execution_confirmed?: boolean;
  observe_operational_improved?: boolean;
  observe_operational_summary?: string | null;
  observe_pre_metrics?: Record<string, number | string | null>;
  observe_post_metrics?: Record<string, number | string | null>;
  observe_kpi_delta?: Record<string, number | string>;
  observe_act_decision_outcome?: string | null;
  observe_act_pending_approval_id?: string | null;
}

export interface CopilotTurnRequest {
  message: string;
  conversation_id?: string | null;
  warehouse_id?: string;
  scenario_name?: string;
}

// ── Scenario listing ──────────────────────────────────────────────────────────

async function listScenarios(): Promise<ScenarioMeta[]> {
  const r = await http.get('/demo/scenarios');
  return r.data.scenarios as ScenarioMeta[];
}

// ── Lifecycle ─────────────────────────────────────────────────────────────────

async function startScenario(name: string): Promise<DemoStatus> {
  const r = await http.post(`/demo/scenario/${encodeURIComponent(name)}/start`);
  return r.data.status as DemoStatus;
}

async function pauseScenario(): Promise<void> {
  await http.post('/demo/scenario/pause');
}

async function resumeScenario(): Promise<void> {
  await http.post('/demo/scenario/resume');
}

async function resetScenario(): Promise<DemoStatus> {
  const r = await http.post('/demo/scenario/reset');
  return r.data.status as DemoStatus;
}

// ── Clock ─────────────────────────────────────────────────────────────────────

async function tick(seconds: number = 60): Promise<{ ticked_seconds: number; clock_iso: string; elapsed_seconds: number }> {
  const r = await http.post('/demo/tick', { seconds });
  return r.data;
}

// ── Inject ────────────────────────────────────────────────────────────────────

async function inject(event_type: InjectEventType, payload: Record<string, any>): Promise<any> {
  const r = await http.post('/demo/inject', { event_type, payload });
  return r.data.result;
}

// ── Status ────────────────────────────────────────────────────────────────────

async function getStatus(): Promise<DemoStatus> {
  const r = await http.get('/demo/status');
  return r.data as DemoStatus;
}

// ── MAIW Analysis ─────────────────────────────────────────────────────────────

async function analyze(): Promise<AnalysisResult> {
  const r = await http.post('/demo/analyze', undefined, { timeout: 120_000 });
  return r.data as AnalysisResult;
}

// ── Approval governance ───────────────────────────────────────────────────────

async function approvePending(pending_id: string, approved_by: string = 'operator'): Promise<any> {
  const r = await http.post('/demo/approve', { pending_id, approved_by });
  return r.data;
}

async function rejectPending(pending_id: string, approved_by: string = 'operator'): Promise<any> {
  const r = await http.post('/demo/reject', { pending_id, approved_by });
  return r.data;
}

// ── Reconciliation ────────────────────────────────────────────────────────────

export interface ReconcileResult {
  ok: boolean;
  execution_id: string;
  domain: string;
  reconciliation_id: string;
  reconciliation_outcome: 'confirmed_executed' | 'confirmed_not_executed' | 'indeterminate';
  effective_status: string;
  proposal_id: string | null;
  decision_id: string | null;
  approval_id: string | null;
  trace_id: string;
  error: string | null;
}

async function reconcile(
  execution_id: string,
  domain: string,
  trace_id?: string,
): Promise<ReconcileResult> {
  const r = await http.post('/demo/reconcile', { execution_id, domain, trace_id });
  return r.data as ReconcileResult;
}

// ── Counterfactual ────────────────────────────────────────────────────────────

export interface CounterfactualKPI {
  sim_time_seconds: number | null;
  pending_backlog: number | null;
  wave_risk_score: number | null;
  wave_risk_level: string | null;
  wave_completion_pct: number | null;
  simulated_throughput: number | null;
  projected_service_level: number | null;
  labor_availability_pct: number | null;
  labor_utilization_pct: number | null;
}

export interface CounterfactualTick {
  tick: number;
  elapsed_seconds: number;
  kpis: CounterfactualKPI;
  recovery_detected?: boolean;
  maiw_cycle?: number;
}

export interface CounterfactualRun {
  run_type: 'control' | 'maiw';
  t0_kpis: CounterfactualKPI;
  final_kpis: CounterfactualKPI;
  trajectory: CounterfactualTick[];
  recovery: {
    detected_at_tick: number;
    sim_time_seconds: number;
    time_to_recovery_secs: number;
    wave_risk_level: string;
    wave_risk_score: number;
    pending_backlog: number;
    wave_completion_pct: number;
  } | null;
  peak_backlog: number;
  peak_wave_risk_score: number;
  backlog_auc: number;
  wave_risk_auc: number;
  maiw_cycles?: Array<{ cycle: number; severity?: string; model_id?: string; approvals: any[] }>;
}

export interface CounterfactualResult {
  evaluated_at: string;
  scenario: string;
  horizon_seconds: number;
  tick_seconds: number;
  label: string;
  control: CounterfactualRun;
  maiw: CounterfactualRun;
  comparison: {
    control_recovery_seconds: number | null;
    maiw_recovery_seconds: number | null;
    recovery_delta_seconds: number | null;
    control_never_recovered: boolean;
    peak_backlog_control: number;
    peak_backlog_maiw: number;
    backlog_auc_control: number;
    backlog_auc_maiw: number;
    backlog_auc_reduction_pct: number | null;
    wave_risk_auc_control: number;
    wave_risk_auc_maiw: number;
    wave_risk_auc_reduction_pct: number | null;
    at_horizon: Record<string, Record<string, { control: number | null; maiw: number | null }>>;
  };
  eval_duration_secs: number;
}

async function getCounterfactualResult(): Promise<CounterfactualResult> {
  const r = await http.get('/demo/counterfactual/result');
  return r.data as CounterfactualResult;
}

// ── Copilot turn (ASK + ANALYZE; intent classified server-side) ───────────────

async function copilotAsk(req: CopilotTurnRequest): Promise<CopilotTurnResponse> {
  const r = await http.post('/copilot/turn', req, { timeout: 120_000 });
  return r.data;
}

/** Alias — copilotTurn makes intent-routing explicit at the call site. */
const copilotTurn = copilotAsk;


// Returns null if demo mode is not active (503)
async function getStatusSafe(): Promise<DemoStatus | null> {
  try {
    return await getStatus();
  } catch (e: any) {
    if (e?.response?.status === 503 || e?.response?.status === 404) return null;
    throw e;
  }
}

export const demoAPI = {
  listScenarios,
  startScenario,
  pauseScenario,
  resumeScenario,
  resetScenario,
  tick,
  inject,
  getStatus,
  getStatusSafe,
  analyze,
  approvePending,
  rejectPending,
  reconcile,
  getCounterfactualResult,
  copilotAsk,
  copilotTurn,
};
