/**
 * Operator feedback for POST /demo/inject.
 *
 * Equipment fault/restore injections omit asset_id: the backend resolves the
 * target from the ACTIVE demo world (DataPack or YAML fallback) and returns
 * the asset it used, so the UI needs no warehouse-topology knowledge.
 * Targeting failures come back as typed errors:
 *   404 ASSET_NOT_IN_ACTIVE_WORLD · 409 NO_ELIGIBLE_ASSET
 *   body: { error: true, code, message, status_code, ... }
 */

type Obj = Record<string, unknown>;

const asObj = (v: unknown): Obj | null => (v && typeof v === 'object' ? (v as Obj) : null);

/** "Targeted agv-000" when the inject result names an asset, else null. */
export function describeInjectTarget(result: unknown): string | null {
  const assetId = asObj(result)?.asset_id;
  return typeof assetId === 'string' && assetId ? `Targeted ${assetId}` : null;
}

/** Human-readable message for a failed demo API call (typed or legacy body). */
export function describeInjectError(e: unknown): string {
  const err = asObj(e);
  const data = asObj(asObj(err?.response)?.data);
  if (typeof data?.code === 'string' && typeof data?.message === 'string') {
    return `${data.code}: ${data.message}`;
  }
  const detail = data?.detail;
  if (typeof detail === 'string') {
    return detail;
  }
  const detailMessage = asObj(detail)?.message;
  if (typeof detailMessage === 'string') {
    return detailMessage;
  }
  return typeof err?.message === 'string' ? err.message : 'unknown';
}
