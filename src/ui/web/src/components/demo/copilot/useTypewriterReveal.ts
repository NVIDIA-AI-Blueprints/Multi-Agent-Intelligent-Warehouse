/**
 * useTypewriterReveal — terminal-style progressive text reveal.
 *
 * Rules:
 *   - Keyed by `turnKey` (turn_id): animation plays once per unique key.
 *   - Respects prefers-reduced-motion: renders immediately when reduced.
 *   - Timers are cleaned up on unmount, key change, and skip.
 *   - Governance badges (safety state) must appear immediately — pass them
 *     outside TerminalTypewriter so they are never delayed.
 */

import { useState, useEffect, useRef, useCallback } from 'react';

export type TypewriterState = 'idle' | 'typing' | 'complete' | 'skipped';

export interface TypewriterOptions {
  /** Characters per tick for the first 80 chars (true char-by-char) */
  charSpeed?: number;     // default 15ms
  /** Characters per tick beyond the first 80 */
  burstSize?: number;     // default 3
  /** Extra pause at sentence-ending punctuation (ms) */
  punctuationPause?: number; // default 50
  /** Extra pause at paragraph boundaries (\n\n) (ms) */
  paragraphPause?: number;   // default 80
  /** Whether to show the block cursor during typing */
  cursor?: boolean;
}

export interface TypewriterResult {
  displayText: string;
  isTyping: boolean;
  isComplete: boolean;
  skip: () => void;
}

// Completed keys across the session — prevents replay after rerenders
const _completedKeys = new Set<string>();

function prefersReducedMotion(): boolean {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
}

export function useTypewriterReveal(
  fullText: string,
  turnKey: string,
  options: TypewriterOptions = {},
): TypewriterResult {
  const {
    charSpeed = 15,
    burstSize = 3,
    punctuationPause = 50,
    paragraphPause = 80,
  } = options;

  const alreadyDone = _completedKeys.has(turnKey);
  const reduced = prefersReducedMotion();

  const [displayText, setDisplayText] = useState<string>(
    alreadyDone || reduced ? fullText : '',
  );
  const [state, setState] = useState<TypewriterState>(
    alreadyDone || reduced ? 'complete' : 'idle',
  );

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const posRef = useRef<number>(alreadyDone || reduced ? fullText.length : 0);
  const activeKeyRef = useRef<string>(turnKey);

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const finish = useCallback((text: string, key: string) => {
    clearTimer();
    setDisplayText(text);
    setState('complete');
    _completedKeys.add(key);
  }, [clearTimer]);

  const skip = useCallback(() => {
    if (state === 'typing') {
      finish(fullText, turnKey);
      setState('skipped');
    }
  }, [state, fullText, turnKey, finish]);

  useEffect(() => {
    // Key changed — reset for new turn
    if (activeKeyRef.current !== turnKey) {
      clearTimer();
      activeKeyRef.current = turnKey;
      posRef.current = 0;

      if (_completedKeys.has(turnKey) || prefersReducedMotion()) {
        setDisplayText(fullText);
        setState('complete');
        return;
      }
      setDisplayText('');
      setState('idle');
    }
  }, [turnKey, fullText, clearTimer]);

  useEffect(() => {
    if (!fullText || alreadyDone || reduced) { return; }
    if (state === 'complete' || state === 'skipped') { return; }

    setState('typing');

    function tick() {
      const pos = posRef.current;
      if (pos >= fullText.length) {
        finish(fullText, turnKey);
        return;
      }

      // Burst size: 1 for first 80 chars, burstSize beyond
      const advance = pos < 80 ? 1 : burstSize;
      const nextPos = Math.min(pos + advance, fullText.length);
      const chunk = fullText.slice(0, nextPos);
      posRef.current = nextPos;
      setDisplayText(chunk);

      // Delay for next tick
      const ch = fullText[nextPos - 1] ?? '';
      const nextCh = fullText[nextPos] ?? '';
      let delay = charSpeed;

      if (nextPos >= fullText.length) {
        finish(fullText, turnKey);
        return;
      }

      // Paragraph boundary
      if (ch === '\n' && nextCh === '\n') {
        delay = paragraphPause;
      }
      // Sentence-ending punctuation
      else if ('.!?'.includes(ch) && (nextCh === ' ' || nextCh === '\n')) {
        delay = punctuationPause;
      }
      // Comma pause
      else if (ch === ',' && nextCh === ' ') {
        delay = Math.round(charSpeed * 1.5);
      }

      timerRef.current = setTimeout(tick, delay);
    }

    timerRef.current = setTimeout(tick, charSpeed);

    return clearTimer;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fullText, turnKey, state === 'idle']);

  return {
    displayText,
    isTyping: state === 'typing',
    isComplete: state === 'complete' || state === 'skipped',
    skip,
  };
}
