/**
 * useCopilotConversation — owns Copilot conversation state above the drawer.
 *
 * Lifting state here (rather than keeping it in CopilotDrawer local state)
 * ensures the conversation survives across drawer open/close cycles,
 * including the REVIEW APPROVAL → APPROVE & EXECUTE → RETURN TO COPILOT path.
 */

import { useState, useCallback, Dispatch, SetStateAction } from 'react';
import { CopilotTurnResponse } from '../services/demoAPI';

// ── Shared turn types ─────────────────────────────────────────────────────────

export interface CopilotSystemCard {
  decision: 'APPROVED' | 'REJECTED' | string;
  execution: string;
  action: string;
}

export interface TurnEntry {
  id: string;
  question: string;
  response: CopilotTurnResponse | null;
  error: string | null;
  /** Present on system-notification entries injected by RETURN TO COPILOT. */
  systemCard?: CopilotSystemCard | null;
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export interface UseCopilotConversationReturn {
  conversationId: string | null;
  setConversationId: (id: string | null) => void;
  turns: TurnEntry[];
  setTurns: Dispatch<SetStateAction<TurnEntry[]>>;
  conversationError: string | null;
  setConversationError: (e: string | null) => void;
  addSystemCard: (card: CopilotSystemCard) => void;
  reset: () => void;
}

export function useCopilotConversation(): UseCopilotConversationReturn {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [turns, setTurns] = useState<TurnEntry[]>([]);
  const [conversationError, setConversationError] = useState<string | null>(null);

  const addSystemCard = useCallback((card: CopilotSystemCard) => {
    setTurns(prev => [
      ...prev,
      {
        id: `system-${Date.now()}`,
        question: '__system__',
        response: null,
        error: null,
        systemCard: card,
      },
    ]);
  }, []);

  const reset = useCallback(() => {
    setConversationId(null);
    setTurns([]);
    setConversationError(null);
  }, []);

  return {
    conversationId,
    setConversationId,
    turns,
    setTurns,
    conversationError,
    setConversationError,
    addSystemCard,
    reset,
  };
}
