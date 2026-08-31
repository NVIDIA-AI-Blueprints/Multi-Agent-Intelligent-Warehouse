/**
 * useTraceReplay.ts — Terminal-style progressive reveal animation for Phase 13E.1.
 *
 * State machine: REPLAYING → LIVE
 * The canonical DeveloperTrace is NEVER modified — this hook only controls visibility.
 *
 * Engine design: self-scheduling via recursive setTimeout so jest.runAllTimers()
 * can drive the entire sequence in tests without needing inter-render re-scheduling.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { DeveloperTraceEvent } from './developerTraceTypes';

// ── Constants ──────────────────────────────────────────────────────────────────

const CHAR_INTERVAL_MS = 12;
const EVENT_DELAY_MS = 100;
const CHUNK_SIZE = 3;
const LONG_TEXT_THRESHOLD = 40;
const MAX_PRIMARY_TEXT = 80;

// ── Types ──────────────────────────────────────────────────────────────────────

export type ReplayMode = 'REPLAYING' | 'LIVE' | 'COMPLETE';

export interface TraceReplayState {
  mode: ReplayMode;
  visibleEvents: DeveloperTraceEvent[];
  activeEventIndex: number;
  activeCharCount: number;
  skipReplay: () => void;
  startReplay: () => void;
}

export interface UseTraceReplayOptions {
  charIntervalMs?: number;
  eventDelayMs?: number;
  reducedMotion?: boolean;
}

// ── Helper ─────────────────────────────────────────────────────────────────────

export function getPrimaryText(event: DeveloperTraceEvent): string {
  if (event.isGap) return '─── WAITING FOR OPERATOR ───';
  if (event.isExecutionBoundary) return 'EXECUTION BOUNDARY';

  const base = event.label + (event.detail ? ' — ' + event.detail.slice(0, 60) : '');
  if (base.length > MAX_PRIMARY_TEXT) {
    return base.slice(0, MAX_PRIMARY_TEXT - 1) + '…';
  }
  return base;
}

// ── Hook ───────────────────────────────────────────────────────────────────────

export function useTraceReplay(
  events: DeveloperTraceEvent[],
  options: UseTraceReplayOptions = {},
): TraceReplayState {
  const {
    charIntervalMs = CHAR_INTERVAL_MS,
    eventDelayMs = EVENT_DELAY_MS,
    reducedMotion = false,
  } = options;

  // ── Displayed state (drives rendering) ──────────────────────────────────────
  const [mode, setMode] = useState<ReplayMode>(() => {
    if (reducedMotion || events.length === 0) return 'LIVE';
    return 'REPLAYING';
  });
  const [visibleEvents, setVisibleEvents] = useState<DeveloperTraceEvent[]>(() => {
    if (reducedMotion || events.length === 0) return [...events];
    return [];
  });
  const [activeEventIndex, setActiveEventIndex] = useState<number>(() => {
    if (reducedMotion || events.length === 0) return -1;
    return 0;
  });
  const [activeCharCount, setActiveCharCount] = useState(0);

  // ── Engine refs (never trigger re-renders) ────────────────────────────────
  const mountedRef = useRef(true);
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([]);

  // Mirror of current engine position (avoids stale closures in self-scheduling)
  const engineRef = useRef({
    eventIndex: reducedMotion || events.length === 0 ? -1 : 0,
    charCount: 0,
    mode: (reducedMotion || events.length === 0 ? 'LIVE' : 'REPLAYING') as ReplayMode,
    visibleCount: reducedMotion ? events.length : 0,
  });

  // Keep a ref to the latest events array so the engine can read it without
  // the self-scheduling closure going stale.
  const eventsRef = useRef(events);
  eventsRef.current = events;

  const prevEventsLengthRef = useRef(events.length);

  const clearAllTimers = useCallback(() => {
    timersRef.current.forEach(clearTimeout);
    timersRef.current = [];
  }, []);

  const schedule = useCallback(
    (fn: () => void, ms: number) => {
      const id = setTimeout(() => {
        if (!mountedRef.current) return;
        fn();
      }, ms);
      timersRef.current.push(id);
    },
    [],
  );

  // ── Self-scheduling engine ─────────────────────────────────────────────────

  const tick = useCallback(
    function tick() {
      const eng = engineRef.current;
      const evs = eventsRef.current;

      if (eng.mode !== 'REPLAYING') return;
      if (eng.eventIndex < 0 || eng.eventIndex >= evs.length) {
        // Done
        eng.mode = 'LIVE';
        setMode('LIVE');
        setActiveEventIndex(-1);
        setActiveCharCount(0);
        prevEventsLengthRef.current = evs.length;
        return;
      }

      const currentEvent = evs[eng.eventIndex];
      const primaryText = getPrimaryText(currentEvent);
      const totalLen = primaryText.length;
      const chunkSize = totalLen > LONG_TEXT_THRESHOLD ? CHUNK_SIZE : 1;

      if (eng.charCount < totalLen) {
        // Reveal next chunk of chars
        const next = Math.min(eng.charCount + chunkSize, totalLen);
        eng.charCount = next;
        setActiveCharCount(next);
        schedule(tick, charIntervalMs);
      } else {
        // All chars revealed — wait then advance event
        schedule(() => {
          const ev = eventsRef.current[eng.eventIndex];
          eng.visibleCount += 1;
          setVisibleEvents((prev) => [...prev, ev]);

          eng.eventIndex += 1;
          eng.charCount = 0;
          setActiveCharCount(0);

          if (eng.eventIndex >= eventsRef.current.length) {
            eng.mode = 'LIVE';
            setMode('LIVE');
            setActiveEventIndex(-1);
            prevEventsLengthRef.current = eventsRef.current.length;
          } else {
            setActiveEventIndex(eng.eventIndex);
            schedule(tick, charIntervalMs);
          }
        }, eventDelayMs);
      }
    },
    [charIntervalMs, eventDelayMs, schedule],
  );

  // ── Start engine on mount (unless reducedMotion or empty) ────────────────

  useEffect(() => {
    mountedRef.current = true;
    if (reducedMotion || events.length === 0) return;
    // Kick off the engine
    schedule(tick, charIntervalMs);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // intentional empty deps — engine starts once

  // ── Reduced-motion: immediate skip ───────────────────────────────────────

  useEffect(() => {
    if (reducedMotion && events.length > 0) {
      setVisibleEvents([...events]);
      setMode('LIVE');
      setActiveEventIndex(-1);
      setActiveCharCount(0);
      engineRef.current.mode = 'LIVE';
      engineRef.current.eventIndex = -1;
      engineRef.current.charCount = 0;
      engineRef.current.visibleCount = events.length;
      prevEventsLengthRef.current = events.length;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reducedMotion]);

  // ── Live mode: handle new events appended after replay ───────────────────

  useEffect(() => {
    if (reducedMotion) return;
    const eng = engineRef.current;
    if (eng.mode !== 'LIVE') return;

    const prevLen = prevEventsLengthRef.current;
    const currLen = events.length;
    if (currLen <= prevLen) {
      prevEventsLengthRef.current = currLen;
      return;
    }

    const newEvents = events.slice(prevLen);
    prevEventsLengthRef.current = currLen;

    newEvents.forEach((ev, i) => {
      schedule(() => {
        setVisibleEvents((prev) => [...prev, ev]);
      }, eventDelayMs * (i + 1));
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [events]);

  // ── Public API ────────────────────────────────────────────────────────────

  const skipReplay = useCallback(() => {
    clearAllTimers();
    const evs = eventsRef.current;
    engineRef.current = { eventIndex: -1, charCount: 0, mode: 'LIVE', visibleCount: evs.length };
    prevEventsLengthRef.current = evs.length;
    setVisibleEvents([...evs]);
    setMode('LIVE');
    setActiveEventIndex(-1);
    setActiveCharCount(0);
  }, [clearAllTimers]);

  const startReplay = useCallback(() => {
    clearAllTimers();
    const evs = eventsRef.current;
    if (evs.length === 0) {
      engineRef.current = { eventIndex: -1, charCount: 0, mode: 'LIVE', visibleCount: 0 };
      prevEventsLengthRef.current = 0;
      setMode('LIVE');
      setActiveEventIndex(-1);
      setActiveCharCount(0);
      setVisibleEvents([]);
    } else {
      engineRef.current = { eventIndex: 0, charCount: 0, mode: 'REPLAYING', visibleCount: 0 };
      prevEventsLengthRef.current = 0;
      setVisibleEvents([]);
      setActiveCharCount(0);
      setMode('REPLAYING');
      setActiveEventIndex(0);
      schedule(tick, charIntervalMs);
    }
  }, [clearAllTimers, tick, charIntervalMs]);

  // ── Cleanup on unmount ────────────────────────────────────────────────────

  useEffect(() => {
    return () => {
      mountedRef.current = false;
      clearAllTimers();
    };
  }, [clearAllTimers]);

  return {
    mode,
    visibleEvents,
    activeEventIndex,
    activeCharCount,
    skipReplay,
    startReplay,
  };
}
