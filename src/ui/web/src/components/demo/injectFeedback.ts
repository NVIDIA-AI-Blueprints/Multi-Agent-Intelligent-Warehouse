/**
 * Operator feedback for POST /demo/inject, plus error text for any demo API call.
 *
 * Injections omit their target (asset_id, worker_id, sku, task_id): the
 * backend resolves it from the ACTIVE demo world (DataPack or YAML fallback)
 * and returns the one it used, so the UI needs no warehouse-topology knowledge.
 * Targeting failures come back as typed errors:
 *   404 ASSET_NOT_IN_ACTIVE_WORLD · 409 NO_ELIGIBLE_ASSET (and WORKER_, SKU_, TASK_)
 *   body: { error: true, code, message, status_code, ... }
 */

type Obj = Record<string, unknown>;

const asObj = (v: unknown): Obj | null => (v && typeof v === 'object' ? (v as Obj) : null);

const TARGET_KEYS = ['asset_id', 'worker_id', 'sku', 'task_id'] as const;

/** "Targeted agv-000" when the inject result names its target, else null. */
export function describeInjectTarget(result: unknown): string | null {
  const obj = asObj(result);
  for (const key of TARGET_KEYS) {
    const id = obj?.[key];
    if (typeof id === 'string' && id) return `Targeted ${id}`;
  }
  return null;
}

/** "CODE: message" from { code | error, message } when both are strings. */
function codedMessage(o: Obj | null): string | null {
  const code = typeof o?.code === 'string' ? o.code : o?.error;
  return typeof code === 'string' && typeof o?.message === 'string' ? `${code}: ${o.message}` : null;
}

/**
 * Human-readable message for a failed demo API call. Bodies seen from the API:
 *   typed       { error: true, code, message }
 *   origin 403  { error: 'CROSS_ORIGIN_REQUEST_FORBIDDEN', message }
 *   dict detail { error: true, message: { error: 'MODEL UNAVAILABLE', message } }
 *   plain       { error: true, message }
 *   legacy      { detail } | { detail: { message } }
 */
export function describeDemoApiError(e: unknown): string {
  const err = asObj(e);
  const data = asObj(asObj(err?.response)?.data);
  const coded = codedMessage(data) ?? codedMessage(asObj(data?.message));
  if (coded) {
    return coded;
  }
  if (typeof data?.message === 'string') {
    return data.message;
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

export const describeInjectError = describeDemoApiError;
