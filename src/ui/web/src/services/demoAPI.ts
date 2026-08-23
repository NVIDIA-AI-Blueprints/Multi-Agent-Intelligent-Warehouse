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

export interface DemoStatus {
  active: boolean;
  paused: boolean;
  scenario: ScenarioMeta | null;
  world: DemoWorldSummary | null;
}

export type InjectEventType =
  | 'equipment_fault'
  | 'equipment_restore'
  | 'low_stock'
  | 'worker_absence'
  | 'worker_return'
  | 'task_deadline'
  | 'wave_delay';

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
};
