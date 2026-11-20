/**
 * Pure helpers for the RELIABILITY page (CommandCenter).
 *
 * In Demo Mode the legacy equipment, task and workforce routes read PostgreSQL,
 * which Demo Mode does not run, so they fail. The operational risks then come
 * from the simulation's KPIs instead.
 */

import type { KPISnapshot } from '../services/demoAPI';

export interface RiskItem {
  icon: '⚠' | '✓';
  text: string;
  color: string;
}

const WARN = '#D29922';
const CRITICAL = '#F85149';
const OK = '#3FB950';

/** Below this labor availability (percent) the page lists labor as a risk. */
export const LABOR_AVAILABILITY_RISK_PCT = 95;

/** Operational risks from the Demo Mode KPIs, most severe first. */
export function deriveDemoRisks(kpis: KPISnapshot, pendingApprovals: number): RiskItem[] {
  const risks: RiskItem[] = [];
  const level = kpis.wave_risk_level;
  if (level === 'critical' || level === 'high') {
    risks.push({ icon: '⚠', text: `Wave risk ${level.toUpperCase()}`, color: CRITICAL });
  } else if (level === 'medium') {
    risks.push({ icon: '⚠', text: 'Wave risk MEDIUM', color: WARN });
  }
  if (pendingApprovals > 0) {
    risks.push({
      icon: '⚠',
      text: `${pendingApprovals} action${pendingApprovals > 1 ? 's' : ''} awaiting human approval`,
      color: WARN,
    });
  }
  if (kpis.equipment_operational_pct < 100) {
    risks.push({
      icon: '⚠',
      text: `Equipment ${Math.round(kpis.equipment_operational_pct)}% operational`,
      color: WARN,
    });
  }
  if (kpis.labor_availability_pct < LABOR_AVAILABILITY_RISK_PCT) {
    risks.push({
      icon: '⚠',
      text: `Labor availability ${kpis.labor_availability_pct.toFixed(1)}%`,
      color: WARN,
    });
  }
  if (kpis.pending_backlog > 3) {
    risks.push({ icon: '⚠', text: `${kpis.pending_backlog} tasks pending — operations backlog`, color: WARN });
  }
  if (kpis.low_stock_count > 0) {
    risks.push({
      icon: '⚠',
      text: `${kpis.low_stock_count} SKU${kpis.low_stock_count > 1 ? 's' : ''} low on stock`,
      color: WARN,
    });
  }
  if (risks.length === 0) {
    risks.push({ icon: '✓', text: 'No active operational risks detected', color: OK });
  }
  return risks;
}

/** Placeholder for an empty risks panel: still loading, or the data source failed. */
export function emptyRisksText(sourceFailed: boolean): string {
  return sourceFailed ? '— state data unavailable —' : '— loading state data —';
}

export const MODEL_ROLES = ['Lightning', 'Nano', 'Super', 'Ultra'] as const;
export type ModelRole = (typeof MODEL_ROLES)[number];

/** The model role a model ID belongs to, or null if it matches none. */
export function getModelRole(modelId: string): ModelRole | null {
  const lower = modelId.toLowerCase();
  if (lower.includes('super')) {
    return 'Super';
  }
  if (lower.includes('ultra')) {
    return 'Ultra';
  }
  if (lower.includes('nano')) {
    return 'Nano';
  }
  if (lower.includes('lightning')) {
    return 'Lightning';
  }
  return null;
}
