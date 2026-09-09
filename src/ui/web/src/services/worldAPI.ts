import axios from 'axios';

const API_BASE = '/api/v1';

const http = axios.create({ baseURL: API_BASE, timeout: 15000, allowAbsoluteUrls: false } as any);

// ── Types ─────────────────────────────────────────────────────────────────────

export interface WorldWarehouseConfig {
  warehouse_id: string;
  dataset_id: string;
  seed: number;
}

export interface WorldLayoutConfig {
  zone_count: number;
  location_count: number;
  dock_door_count: number;
}

export interface WorldWorkforceConfig {
  workers_per_shift: number;
  shift_count: number;
  total_workers: number;
  skills: string[];
}

export interface WorldEquipmentConfig {
  agv_count: number;
  forklift_count: number;
  conveyor_count: number;
  total: number;
}

export interface WorldCommerceConfig {
  sku_count: number;
  low_stock_pct: number;
  daily_order_count: number;
  lines_per_order_mean: number;
}

export interface WorldOperationsConfig {
  active_wave_count: number;
  task_count: number;
  strategy: string;
}

export interface WorldGenerationMeta {
  schema_version: string;
  generator_version: string;
  pack_format: string;
  semantic_checksum: string | null;
  total_entities: number;
  total_edges: number;
  total_events: number;
  graph_available: boolean;
}

export interface WorldConfigResponse {
  warehouse: WorldWarehouseConfig;
  layout: WorldLayoutConfig;
  workforce: WorldWorkforceConfig;
  equipment: WorldEquipmentConfig;
  commerce: WorldCommerceConfig;
  operations: WorldOperationsConfig;
  generation: WorldGenerationMeta;
}

export interface DataPackMeta {
  dataset_id: string;
  warehouse_id: string;
  seed: number;
  schema_version: string;
  semantic_checksum: string | null;
  total_entities: number;
  total_edges: number;
  total_events: number;
  pack_format: string;
  generator_version: string;
  immutable: boolean;
  loaded: boolean;
}

export interface GraphCounts {
  entity_counts: Record<string, number>;
  relationship_counts: Record<string, number>;
  total_entities: number;
  total_relationships: number;
  event_count: number;
  available: boolean;
}

export interface ScenarioSummaryData {
  scenario_id: string | null;
  name: string | null;
  severity: string | null;
  active: boolean;
}

export interface RuntimeSummaryData {
  status: string;
  elapsed_seconds: number | null;
  clock_iso: string | null;
}

export interface WorldSummaryResponse {
  datapack: DataPackMeta;
  graph: GraphCounts;
  scenario: ScenarioSummaryData;
  runtime: RuntimeSummaryData;
}

export interface OverlayEventDTO {
  event_id: string;
  event_type: string;
  entity_id: string;
  entity_type: string;
  entity_label: string;
  sim_time_offset_seconds: number;
  before_state: string | null;
  after_state: string | null;
  label: string;
  payload: Record<string, string | number | boolean | null>;
}

export interface AffectedEntityDTO {
  entity_id: string;
  entity_type: string;
  entity_label: string;
  disruption_type: string;
  before_state: string | null;
  after_state: string | null;
  severity: string | null;
}

export interface WorldChangesResponse {
  warehouse_id: string;
  dataset_id: string;
  scenario_id: string | null;
  scenario_name: string | null;
  scenario_active: boolean;
  scenario_severity: string;
  base_checksum: string | null;
  world_clock_seconds: number;
  overlay_event_count: number;
  affected_entity_count: number;
  events: OverlayEventDTO[];
  affected_entities: AffectedEntityDTO[];
}

// ── API methods ───────────────────────────────────────────────────────────────

async function getConfig(): Promise<WorldConfigResponse> {
  const r = await http.get('/world/config');
  return r.data as WorldConfigResponse;
}

async function getSummary(): Promise<WorldSummaryResponse> {
  const r = await http.get('/world/summary');
  return r.data as WorldSummaryResponse;
}

async function getChanges(): Promise<WorldChangesResponse> {
  const r = await http.get('/world/changes');
  return r.data as WorldChangesResponse;
}

export const worldAPI = {
  getConfig,
  getSummary,
  getChanges,
};
