import { useEffect, useRef, useCallback, useState } from 'react';

export interface SSEEvent {
  id: string;
  ts: string;
  category: string;
  message: string;
  detail: string | null;
  asset_id: string | null;
  task_id: string | null;
  worker_id: string | null;
  sim_time_seconds?: number;
  /** Present on reliability/reconciliation events */
  execution_id?: string;
  domain?: string;
}

/** Safely parse detail as JSON object; returns null if not an object.
 *  Handles both string (prod) and object (test mocks passed via `as any`). */
export function parseEventDetail(ev: SSEEvent): Record<string, any> | null {
  if (!ev.detail) return null;
  // In tests, detail may be passed as an object directly (via `as any`)
  if (typeof ev.detail !== 'string') return ev.detail as unknown as Record<string, any>;
  try {
    const parsed = JSON.parse(ev.detail);
    return parsed && typeof parsed === 'object' ? parsed : null;
  } catch {
    return null;
  }
}

export interface DemoSSEState {
  events: SSEEvent[];
  connected: boolean;
  error: string | null;
  clear: () => void;
}

const MAX_EVENTS = 200;
const SSE_URL = '/api/v1/events/stream';

export function useDemoSSE(enabled: boolean): DemoSSEState {
  const [events, setEvents] = useState<SSEEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);

  const clear = useCallback(() => setEvents([]), []);

  useEffect(() => {
    if (!enabled) {
      if (esRef.current) {
        esRef.current.close();
        esRef.current = null;
        setConnected(false);
      }
      return;
    }

    // Avoid double-open in StrictMode
    if (esRef.current) return;

    const es = new EventSource(SSE_URL);
    esRef.current = es;

    es.onopen = () => {
      setConnected(true);
      setError(null);
    };

    es.onmessage = (e: MessageEvent) => {
      try {
        const payload = JSON.parse(e.data) as SSEEvent;
        setEvents(prev => [payload, ...prev].slice(0, MAX_EVENTS));
      } catch {
        // non-JSON keepalive or comment — ignore
      }
    };

    es.onerror = () => {
      setConnected(false);
      setError('SSE connection lost — will retry');
      // EventSource retries automatically; don't close manually
    };

    return () => {
      es.close();
      esRef.current = null;
      setConnected(false);
    };
  }, [enabled]);

  return { events, connected, error, clear };
}
