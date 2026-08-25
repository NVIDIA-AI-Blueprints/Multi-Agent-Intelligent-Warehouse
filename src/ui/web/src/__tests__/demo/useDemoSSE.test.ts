/**
 * Tests for useDemoSSE hook.
 * Uses a mock EventSource.
 */

import { renderHook, act } from '@testing-library/react';
import { useDemoSSE } from '../../hooks/useDemoSSE';

// ── Mock EventSource ──────────────────────────────────────────────────────────

type Handler = (e: any) => void;

class MockEventSource {
  static instances: MockEventSource[] = [];
  url: string;
  onopen: Handler | null = null;
  onmessage: Handler | null = null;
  onerror: Handler | null = null;
  closed = false;

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  close() { this.closed = true; }

  // helpers for tests
  simulateOpen() { this.onopen?.({} as Event); }
  simulateMessage(data: string) { this.onmessage?.({ data } as MessageEvent); }
  simulateError() { this.onerror?.({} as Event); }
}

beforeAll(() => {
  (global as any).EventSource = MockEventSource;
});

beforeEach(() => {
  MockEventSource.instances = [];
});

afterAll(() => {
  delete (global as any).EventSource;
});

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('useDemoSSE', () => {
  it('does not create EventSource when disabled', () => {
    renderHook(() => useDemoSSE(false));
    expect(MockEventSource.instances).toHaveLength(0);
  });

  it('creates EventSource when enabled', () => {
    renderHook(() => useDemoSSE(true));
    expect(MockEventSource.instances).toHaveLength(1);
    expect(MockEventSource.instances[0].url).toBe('/api/v1/events/stream');
  });

  it('sets connected=true on open', () => {
    const { result } = renderHook(() => useDemoSSE(true));
    expect(result.current.connected).toBe(false);
    act(() => { MockEventSource.instances[0].simulateOpen(); });
    expect(result.current.connected).toBe(true);
  });

  it('parses incoming JSON events', () => {
    const { result } = renderHook(() => useDemoSSE(true));
    const event = {
      id: 'evt-1', ts: '2026-08-23T08:00:00Z',
      category: 'STATE', message: 'scenario:start', detail: null,
      asset_id: null, task_id: null, worker_id: null,
    };
    act(() => { MockEventSource.instances[0].simulateMessage(JSON.stringify(event)); });
    expect(result.current.events).toHaveLength(1);
    expect(result.current.events[0].category).toBe('STATE');
    expect(result.current.events[0].message).toBe('scenario:start');
  });

  it('ignores non-JSON messages (keepalive comments)', () => {
    const { result } = renderHook(() => useDemoSSE(true));
    act(() => { MockEventSource.instances[0].simulateMessage(': keepalive'); });
    expect(result.current.events).toHaveLength(0);
  });

  it('sets error on SSE error event', () => {
    const { result } = renderHook(() => useDemoSSE(true));
    act(() => {
      MockEventSource.instances[0].simulateOpen();
      MockEventSource.instances[0].simulateError();
    });
    expect(result.current.connected).toBe(false);
    expect(result.current.error).not.toBeNull();
  });

  it('clear() empties events', () => {
    const { result } = renderHook(() => useDemoSSE(true));
    const event = { id: 'e1', ts: '2026-08-23T08:00:00Z', category: 'TICK', message: 'tick', detail: null, asset_id: null, task_id: null, worker_id: null };
    act(() => { MockEventSource.instances[0].simulateMessage(JSON.stringify(event)); });
    expect(result.current.events).toHaveLength(1);
    act(() => { result.current.clear(); });
    expect(result.current.events).toHaveLength(0);
  });

  it('closes EventSource on unmount', () => {
    const { unmount } = renderHook(() => useDemoSSE(true));
    const es = MockEventSource.instances[0];
    unmount();
    expect(es.closed).toBe(true);
  });

  it('caps events at MAX_EVENTS (200)', () => {
    const { result } = renderHook(() => useDemoSSE(true));
    act(() => {
      for (let i = 0; i < 250; i++) {
        const ev = { id: `e-${i}`, ts: '2026-08-23T08:00:00Z', category: 'TICK', message: `tick-${i}`, detail: null, asset_id: null, task_id: null, worker_id: null };
        MockEventSource.instances[0].simulateMessage(JSON.stringify(ev));
      }
    });
    expect(result.current.events.length).toBeLessThanOrEqual(200);
  });
});
