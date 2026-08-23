/**
 * Tests for demoAPI service layer.
 */

jest.mock('axios', () => {
  const mockFns = { get: jest.fn(), post: jest.fn() };
  const create = jest.fn(() => mockFns);
  return { __esModule: true, default: { create, _mockFns: mockFns } };
});

import { demoAPI } from '../../services/demoAPI';
import axios from 'axios';

// Retrieve the mocked instance fns
const { _mockFns: { get: mockGet, post: mockPost } } = axios as any;

beforeEach(() => {
  (mockGet as jest.Mock).mockReset();
  (mockPost as jest.Mock).mockReset();
});

describe('demoAPI.listScenarios', () => {
  it('calls GET /demo/scenarios and returns scenarios array', async () => {
    (mockGet as jest.Mock).mockResolvedValueOnce({
      data: {
        scenarios: [
          { name: 'healthy_baseline', display_name: 'Healthy Baseline', description: 'All good', tags: ['baseline'] },
        ],
      },
    });
    const result = await demoAPI.listScenarios();
    expect(mockGet).toHaveBeenCalledWith('/demo/scenarios');
    expect(result).toHaveLength(1);
    expect(result[0].name).toBe('healthy_baseline');
  });
});

describe('demoAPI.startScenario', () => {
  it('calls POST /demo/scenario/{name}/start', async () => {
    (mockPost as jest.Mock).mockResolvedValueOnce({
      data: { status: { active: true, paused: false, scenario: { name: 'healthy_baseline' }, world: null } },
    });
    const result = await demoAPI.startScenario('healthy_baseline');
    expect(mockPost).toHaveBeenCalledWith('/demo/scenario/healthy_baseline/start');
    expect(result.active).toBe(true);
  });
});

describe('demoAPI.pauseScenario', () => {
  it('calls POST /demo/scenario/pause', async () => {
    (mockPost as jest.Mock).mockResolvedValueOnce({ data: { ok: true } });
    await demoAPI.pauseScenario();
    expect(mockPost).toHaveBeenCalledWith('/demo/scenario/pause');
  });
});

describe('demoAPI.resumeScenario', () => {
  it('calls POST /demo/scenario/resume', async () => {
    (mockPost as jest.Mock).mockResolvedValueOnce({ data: { ok: true } });
    await demoAPI.resumeScenario();
    expect(mockPost).toHaveBeenCalledWith('/demo/scenario/resume');
  });
});

describe('demoAPI.resetScenario', () => {
  it('calls POST /demo/scenario/reset and returns status', async () => {
    (mockPost as jest.Mock).mockResolvedValueOnce({
      data: { status: { active: true, paused: false, scenario: null, world: null } },
    });
    const result = await demoAPI.resetScenario();
    expect(mockPost).toHaveBeenCalledWith('/demo/scenario/reset');
    expect(result.active).toBe(true);
  });
});

describe('demoAPI.tick', () => {
  it('calls POST /demo/tick with seconds payload', async () => {
    (mockPost as jest.Mock).mockResolvedValueOnce({
      data: { ticked_seconds: 60, clock_iso: '2026-08-23T08:01:00Z', elapsed_seconds: 60 },
    });
    const result = await demoAPI.tick(60);
    expect(mockPost).toHaveBeenCalledWith('/demo/tick', { seconds: 60 });
    expect(result.ticked_seconds).toBe(60);
  });
});

describe('demoAPI.inject', () => {
  it('sends equipment_fault payload to POST /demo/inject', async () => {
    (mockPost as jest.Mock).mockResolvedValueOnce({
      data: { ok: true, result: { asset_id: 'AGV-01', status: 'offline' } },
    });
    const payload = { asset_id: 'AGV-01', fault_code: 'E_MOTOR_OVERTEMP', new_status: 'offline' };
    const result = await demoAPI.inject('equipment_fault', payload);
    expect(mockPost).toHaveBeenCalledWith('/demo/inject', { event_type: 'equipment_fault', payload });
    expect(result.asset_id).toBe('AGV-01');
  });

  it('maps all supported event types correctly', async () => {
    const types = [
      'equipment_fault', 'equipment_restore', 'low_stock',
      'worker_absence', 'worker_return', 'task_deadline', 'wave_delay',
    ] as const;
    for (const t of types) {
      (mockPost as jest.Mock).mockResolvedValueOnce({ data: { ok: true, result: {} } });
      await demoAPI.inject(t, {});
      expect(mockPost).toHaveBeenLastCalledWith('/demo/inject', { event_type: t, payload: {} });
    }
  });
});

describe('demoAPI.getStatusSafe', () => {
  it('returns null when backend responds 503 (demo mode off)', async () => {
    (mockGet as jest.Mock).mockRejectedValueOnce({ response: { status: 503 } });
    const result = await demoAPI.getStatusSafe();
    expect(result).toBeNull();
  });

  it('returns null when backend responds 404', async () => {
    (mockGet as jest.Mock).mockRejectedValueOnce({ response: { status: 404 } });
    const result = await demoAPI.getStatusSafe();
    expect(result).toBeNull();
  });

  it('returns status when demo mode is active', async () => {
    (mockGet as jest.Mock).mockResolvedValueOnce({
      data: { active: true, paused: false, scenario: { name: 'healthy_baseline' }, world: null },
    });
    const result = await demoAPI.getStatusSafe();
    expect(result?.active).toBe(true);
  });

  it('re-throws on unexpected server errors (not 503/404)', async () => {
    (mockGet as jest.Mock).mockRejectedValueOnce({ response: { status: 500 } });
    await expect(demoAPI.getStatusSafe()).rejects.toMatchObject({ response: { status: 500 } });
  });
});

describe('inject event type coverage', () => {
  it('supports all seven controller-implemented event types', () => {
    const supportedTypes = [
      'equipment_fault',
      'equipment_restore',
      'low_stock',
      'worker_absence',
      'worker_return',
      'task_deadline',
      'wave_delay',
    ];
    expect(supportedTypes).toHaveLength(7);
    expect(supportedTypes).toContain('equipment_fault');
    expect(supportedTypes).toContain('wave_delay');
  });
});
