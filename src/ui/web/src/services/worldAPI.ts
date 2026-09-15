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

// ── Phase 17C: Graph inspection types ────────────────────────────────────────

export interface GraphSearchResultDTO {
  entity_id: string;
  entity_type: string;
  label: string;
  match_type: string;  // EXACT_ID | EXACT_ATTRIBUTE | ENTITY_TYPE | PREFIX_ID | NAME_MATCH
}

export interface GraphSearchResponse {
  query: string;
  results: GraphSearchResultDTO[];
}

export interface GraphNodeDTO {
  entity_id: string;
  entity_type: string;
  label: string;
  attributes_summary: Record<string, string | number | boolean | null>;
  scenario_affected: boolean;
  scenario_severity: string | null;
  bfs_depth: number;  // 0=focus, 1=direct, 2=two-hop
}

export interface GraphEdgeDTO {
  edge_id: string;
  source_id: string;
  target_id: string;
  relationship_type: string;
  valid_from: string | null;
  valid_to: string | null;
  temporal: boolean;
  active: boolean;
}

export interface GraphEntityDetailResponse {
  entity_id: string;
  entity_type: string;
  label: string;
  attributes: Record<string, string | number | boolean | null>;
  incoming_count: number;
  outgoing_count: number;
  scenario_affected: boolean;
  scenario_severity: string | null;
  direct_relationships: GraphEdgeDTO[];
}

export interface GraphNeighborhoodResponse {
  focus_entity: GraphNodeDTO;
  nodes: GraphNodeDTO[];
  edges: GraphEdgeDTO[];
  depth: number;
  entity_count: number;
  relationship_count: number;
  truncated: boolean;
  truncated_from: number | null;
  relationship_summary: Record<string, string[]>;
  dataset_id: string;
  warehouse_id: string;
}

// ── Phase 17D: LIVE world types ───────────────────────────────────────────────

export interface ChangedFieldDTO {
  field: string;
  before_value: string | number | boolean | null;
  after_value: string | number | boolean | null;
}

export interface ChangedEntityDTO {
  entity_id: string;
  entity_type: string;  // "worker" | "task"
  label: string;
  changed_fields: ChangedFieldDTO[];
  note: string;
}

export interface LiveSummaryDTO {
  workers: number;
  idle_workers: number;
  equipment: number;
  available_equipment: number;
  tasks: number;
  pending_tasks: number;
  in_progress_tasks: number;
}

export interface LastExecutionDTO {
  execution_id: string | null;
  trace_id: string | null;
  outcome: string;  // EXECUTED | FAILED | UNKNOWN | REJECTED | PENDING
  pre_kpi: Record<string, number> | null;
  post_kpi: Record<string, number> | null;
  kpi_delta: Record<string, number> | null;
}

export interface WorldLiveResponse {
  warehouse_id: string;
  dataset_id: string;
  base_checksum: string | null;
  scenario_id: string | null;
  scenario_active: boolean;
  runtime_status: string;   // IDLE | ACTIVE | PAUSED
  world_clock: string | null;
  summary: LiveSummaryDTO;
  changed_entities: ChangedEntityDTO[];
  last_execution: LastExecutionDTO | null;
}

// ── Phase 17F: Paginated entity browser ──────────────────────────────────────

export interface EntityBrowserItemDTO {
  entity_id: string;
  entity_type: string;
  label: string;
  key_state: Record<string, string | number | boolean | null>;
}

export interface EntityPageResponse {
  items: EntityBrowserItemDTO[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
  entity_type_filter: string | null;
}

// ── Phase 17F: Context snapshot list ─────────────────────────────────────────

export interface ContextSnapshotListItemDTO {
  context_snapshot_id: string;
  turn_id: string;
  trace_id: string;
  focus_entity_id: string;
  focus_entity_type: string;
  focus_label: string;
  entity_count: number;
  captured_at: string;
  truncated: boolean;
}

export interface ContextSnapshotListResponse {
  snapshots: ContextSnapshotListItemDTO[];
  total: number;
  store_note: string;
}

// Context passed from Copilot to WORLD graph
export interface GraphFocusContext {
  entityId: string;
  entityLabel: string | null;
  turnId: string;
  traceId: string;
  entityCount: number | null;
}

// ── Phase 17E: Operational Context Snapshot ───────────────────────────────────

export interface ContextSnapshotNode {
  entity_id: string;
  entity_type: string;
  label: string;
  attributes: Record<string, unknown>;
}

export interface ContextSnapshotEdge {
  source_id: string;
  target_id: string;
  relationship_type: string;
  valid_from: string | null;
  valid_to: string | null;
}

export interface OperationalContextSnapshotResponse {
  context_snapshot_id: string;
  conversation_id: string;
  turn_id: string;
  trace_id: string;
  warehouse_id: string;
  dataset_id: string;
  datapack_checksum: string;
  warehouse_state_snapshot_id: string | null;
  focus_entity_id: string;
  focus_entity_type: string;
  focus_label: string;
  depth: number;
  truncated: boolean;
  nodes: ContextSnapshotNode[];
  edges: ContextSnapshotEdge[];
  entity_count: number;
  relationship_count: number;
  relationship_summary: Record<string, string[]>;
  captured_at: string;
  store_note: string;
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

async function searchGraph(q: string, limit = 10): Promise<GraphSearchResponse> {
  const r = await http.get('/world/graph/search', { params: { q, limit } });
  return r.data as GraphSearchResponse;
}

async function getGraphEntity(entityId: string): Promise<GraphEntityDetailResponse> {
  const r = await http.get(`/world/graph/entity/${encodeURIComponent(entityId)}`);
  return r.data as GraphEntityDetailResponse;
}

async function getGraphNeighbors(
  entityId: string,
  depth = 1,
  maxEntities = 50,
  maxRelationships = 100,
): Promise<GraphNeighborhoodResponse> {
  const r = await http.get(`/world/graph/neighbors/${encodeURIComponent(entityId)}`, {
    params: { depth, max_entities: maxEntities, max_relationships: maxRelationships },
  });
  return r.data as GraphNeighborhoodResponse;
}

async function getLive(): Promise<WorldLiveResponse> {
  const r = await http.get('/world/live');
  return r.data as WorldLiveResponse;
}

// Phase 17E: historical operational context snapshot
async function getContextByTurn(turnId: string): Promise<OperationalContextSnapshotResponse> {
  const r = await http.get(`/world/context/by-turn/${encodeURIComponent(turnId)}`);
  return r.data as OperationalContextSnapshotResponse;
}

// Phase 17F: paginated entity browser
async function getEntities(
  entityType?: string,
  limit = 20,
  offset = 0,
): Promise<EntityPageResponse> {
  const params: Record<string, string | number> = { limit, offset };
  if (entityType) params.entity_type = entityType;
  const r = await http.get('/world/graph/entities', { params });
  return r.data as EntityPageResponse;
}

// Phase 17F: context snapshot list
async function getContextSnapshots(): Promise<ContextSnapshotListResponse> {
  const r = await http.get('/world/context/snapshots');
  return r.data as ContextSnapshotListResponse;
}

export const worldAPI = {
  getConfig,
  getSummary,
  getChanges,
  searchGraph,
  getGraphEntity,
  getGraphNeighbors,
  getLive,
  getContextByTurn,      // Phase 17E
  getEntities,           // Phase 17F
  getContextSnapshots,   // Phase 17F
};
