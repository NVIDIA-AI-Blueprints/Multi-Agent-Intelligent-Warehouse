/**
 * v2.0.1 round 3 — the UI never holds the operator write credential and must
 * not fail silently when a governed equipment write is denied.
 */
import { describeOperationalWriteError } from '../../services/api';

const err = (status: number, data: Record<string, unknown>) => ({
  response: { status, data },
});

describe('describeOperationalWriteError', () => {
  it('explains a missing operator write credential (403)', () => {
    const msg = describeOperationalWriteError(
      err(403, { code: 'OPERATOR_WRITE_CREDENTIAL_REQUIRED', message: 'x' })
    );
    expect(msg).toMatch(/operator write credential/i);
  });

  it('explains disabled or not-offered governed writes (503)', () => {
    expect(
      describeOperationalWriteError(err(503, { code: 'OPERATOR_WRITE_AUTH_NOT_CONFIGURED' }))
    ).toMatch(/disabled/i);
    expect(
      describeOperationalWriteError(err(503, { code: 'GOVERNED_WRITES_NOT_OFFERED' }))
    ).toMatch(/does not offer/i);
  });

  it('explains an unresolved (UNKNOWN) earlier write (409)', () => {
    expect(
      describeOperationalWriteError(err(409, { code: 'RECONCILIATION_REQUIRED' }))
    ).toMatch(/reconciled/i);
  });

  it('falls back to the server message, then the error message', () => {
    expect(describeOperationalWriteError(err(500, { message: 'boom' }))).toBe('boom');
    expect(describeOperationalWriteError(new Error('net down'))).toBe('net down');
  });
});
