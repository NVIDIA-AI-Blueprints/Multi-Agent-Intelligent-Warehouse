/**
 * semanticZoom.ts — zoom-level classifier for the Story/Trace Decision Graph (Phase 13C.1).
 *
 * Thresholds:
 *   < 0.6   → OVERVIEW  (lane summaries only, no individual cards)
 *   0.6–1.0 → STANDARD  (key semantic cards, skills collapsed)
 *   > 1.0   → DETAIL    (all nodes, IDs visible, full metadata)
 */

export type SemanticZoomLevel = 'OVERVIEW' | 'STANDARD' | 'DETAIL';

/**
 * Map a numeric zoom scale to a semantic zoom level.
 * Pure function — no side effects, easily unit-testable.
 */
export function getSemanticZoomLevel(scale: number): SemanticZoomLevel {
  if (scale < 0.6) return 'OVERVIEW';
  if (scale <= 1.0) return 'STANDARD';
  return 'DETAIL';
}
