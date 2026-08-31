/**
 * phase13E_replay.test.tsx — 12 tests for useTraceReplay hook (Phase 13E.1)
 *
 * Uses fake timers throughout. Tests verify the state machine, charCount,
 * skipReplay, startReplay, live mode, reducedMotion, and special event types.
 */

import React from 'react';
import { render, act, renderHook } from '@testing-library/react';
import { useTraceReplay, getPrimaryText, TraceReplayState } from '../../components/demo/developer-trace/useTraceReplay';
import { DeveloperTraceEvent } from '../../components/demo/developer-trace/developerTraceTypes';

// ── Helpers ────────────────────────────────────────────────────────────────────

function makeEvent(overrides: Partial<DeveloperTraceEvent> = {}): DeveloperTraceEvent {
  return {
    id: Math.random().toString(36).slice(2),
    category: 'AGENT',
    label: 'Test event',
    actorSource: 'LIVE',
    timingSource: 'NOT_INSTRUMENTED',
    ...overrides,
  };
}

afterEach(() => {
  jest.useRealTimers();
});

// ── Tests ──────────────────────────────────────────────────────────────────────

test('1. opens in REPLAYING state with 0 visible events', () => {
  jest.useFakeTimers();
  const events = [makeEvent({ label: 'Hello' }), makeEvent({ label: 'World' })];

  const { result } = renderHook(() =>
    useTraceReplay(events, { charIntervalMs: 12, eventDelayMs: 100 }),
  );

  expect(result.current.mode).toBe('REPLAYING');
  expect(result.current.visibleEvents).toHaveLength(0);
  expect(result.current.activeEventIndex).toBe(0);
});

test('2. after one charInterval tick: activeCharCount increments', () => {
  jest.useFakeTimers();
  const events = [makeEvent({ label: 'Hi' })];

  const { result } = renderHook(() =>
    useTraceReplay(events, { charIntervalMs: 12, eventDelayMs: 100 }),
  );

  expect(result.current.activeCharCount).toBe(0);

  act(() => {
    jest.advanceTimersByTime(12);
  });

  expect(result.current.activeCharCount).toBeGreaterThan(0);
});

test('3. after full primary text typed: event moves to visibleEvents after eventDelayMs', () => {
  jest.useFakeTimers();
  const events = [makeEvent({ label: 'Hi' })];
  const primaryTextLen = getPrimaryText(events[0]).length;

  const { result } = renderHook(() =>
    useTraceReplay(events, { charIntervalMs: 12, eventDelayMs: 100 }),
  );

  // Advance enough to type all chars
  act(() => {
    jest.advanceTimersByTime(12 * (primaryTextLen + 5));
  });

  // Still at 0 visible (waiting eventDelay)
  // Actually we need to also advance by eventDelayMs
  act(() => {
    jest.advanceTimersByTime(100);
  });

  expect(result.current.visibleEvents).toHaveLength(1);
});

test('4. after all events processed: mode becomes LIVE', () => {
  jest.useFakeTimers();
  const events = [makeEvent({ label: 'A' }), makeEvent({ label: 'B' })];

  const { result } = renderHook(() =>
    useTraceReplay(events, { charIntervalMs: 1, eventDelayMs: 1 }),
  );

  act(() => {
    jest.runAllTimers();
  });

  expect(result.current.mode).toBe('LIVE');
  expect(result.current.visibleEvents).toHaveLength(2);
  expect(result.current.activeEventIndex).toBe(-1);
});

test('5. skipReplay() immediately sets all events visible + mode LIVE', () => {
  jest.useFakeTimers();
  const events = [makeEvent({ label: 'A' }), makeEvent({ label: 'B' }), makeEvent({ label: 'C' })];

  const { result } = renderHook(() =>
    useTraceReplay(events, { charIntervalMs: 12, eventDelayMs: 100 }),
  );

  expect(result.current.mode).toBe('REPLAYING');

  act(() => {
    result.current.skipReplay();
  });

  expect(result.current.mode).toBe('LIVE');
  expect(result.current.visibleEvents).toHaveLength(3);
  expect(result.current.activeEventIndex).toBe(-1);
});

test('6. skipReplay() does not call any fetch/XHR', () => {
  jest.useFakeTimers();
  const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue({} as Response);
  const events = [makeEvent({ label: 'A' })];

  const { result } = renderHook(() =>
    useTraceReplay(events, { charIntervalMs: 12, eventDelayMs: 100 }),
  );

  act(() => {
    result.current.skipReplay();
  });

  expect(fetchSpy).not.toHaveBeenCalled();
  fetchSpy.mockRestore();
});

test('7. startReplay() resets visibleEvents to [] and mode to REPLAYING', () => {
  jest.useFakeTimers();
  const events = [makeEvent({ label: 'A' }), makeEvent({ label: 'B' })];

  const { result } = renderHook(() =>
    useTraceReplay(events, { charIntervalMs: 1, eventDelayMs: 1 }),
  );

  // Complete replay first
  act(() => {
    jest.runAllTimers();
  });

  expect(result.current.mode).toBe('LIVE');

  act(() => {
    result.current.startReplay();
  });

  expect(result.current.mode).toBe('REPLAYING');
  expect(result.current.visibleEvents).toHaveLength(0);
  expect(result.current.activeEventIndex).toBe(0);
});

test('8. new event appended in LIVE mode: appends with delay, does not replay historical events', () => {
  jest.useFakeTimers();
  const initialEvents = [makeEvent({ label: 'A' })];

  const { result, rerender } = renderHook(
    ({ evs }: { evs: DeveloperTraceEvent[] }) =>
      useTraceReplay(evs, { charIntervalMs: 1, eventDelayMs: 10 }),
    { initialProps: { evs: initialEvents } },
  );

  // Complete replay
  act(() => {
    jest.runAllTimers();
  });

  expect(result.current.mode).toBe('LIVE');
  expect(result.current.visibleEvents).toHaveLength(1);

  // Append a new event
  const newEvent = makeEvent({ label: 'B' });
  const nextEvents = [...initialEvents, newEvent];

  rerender({ evs: nextEvents });

  // Before delay
  expect(result.current.visibleEvents).toHaveLength(1);

  act(() => {
    jest.advanceTimersByTime(15);
  });

  expect(result.current.visibleEvents).toHaveLength(2);
  expect(result.current.visibleEvents[1]).toBe(newEvent);
  // Mode stays LIVE
  expect(result.current.mode).toBe('LIVE');
});

test('9. reduced motion: all events immediately visible, mode LIVE, no timers', () => {
  jest.useFakeTimers();
  const events = [makeEvent({ label: 'A' }), makeEvent({ label: 'B' }), makeEvent({ label: 'C' })];

  const { result } = renderHook(() =>
    useTraceReplay(events, { reducedMotion: true }),
  );

  // No timers needed
  expect(result.current.visibleEvents).toHaveLength(3);
  expect(result.current.mode).toBe('LIVE');
  expect(result.current.activeEventIndex).toBe(-1);
});

test('10. unmount: no pending timer callbacks fire after unmount (no act() warnings)', () => {
  jest.useFakeTimers();
  const events = [makeEvent({ label: 'Long label that takes time to type out' })];
  const consoleSpy = jest.spyOn(console, 'error');

  const { unmount } = renderHook(() =>
    useTraceReplay(events, { charIntervalMs: 12, eventDelayMs: 100 }),
  );

  // Unmount before any timers fire
  unmount();

  // Drain all timers — should not cause act() warnings
  act(() => {
    jest.runAllTimers();
  });

  // No React "act()" warning should have been logged
  const actWarnings = consoleSpy.mock.calls.filter(
    (args) => typeof args[0] === 'string' && args[0].includes('act('),
  );
  expect(actWarnings).toHaveLength(0);
  consoleSpy.mockRestore();
});

test('11. gap event (isGap): primary text is "─── WAITING FOR OPERATOR ───"', () => {
  const gapEvent = makeEvent({ isGap: true, label: 'something else' });
  expect(getPrimaryText(gapEvent)).toBe('─── WAITING FOR OPERATOR ───');
});

test('12. execution boundary: primary text is "EXECUTION BOUNDARY"', () => {
  const boundaryEvent = makeEvent({ isExecutionBoundary: true, label: 'should be ignored' });
  expect(getPrimaryText(boundaryEvent)).toBe('EXECUTION BOUNDARY');
});
