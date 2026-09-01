/**
 * CopilotDrawer.tsx — Phase 15B Copilot ASK panel.
 *
 * Right-side overlay drawer for operator questions about warehouse state.
 * ASK mode only — no action proposals, no APPROVE/EXECUTE buttons.
 *
 * Constraints:
 *   - No chain_of_thought / scratchpad / hidden_reasoning / reasoning_tokens
 *   - No APPROVE / EXECUTE / DO IT / ActionProposal buttons
 *   - Severity comes from fact.severity ONLY — never re-derived from value text
 *   - skills_used is always [] for ASK — "skills used: none" is not shown
 */

import React, { useState, useRef, useEffect, useCallback, KeyboardEvent } from 'react';
import { Box, Typography } from '@mui/material';
import { demoAPI, CopilotTurnResponse } from '../../../services/demoAPI';

// ── Color constants (MAIW dark terminal aesthetic) ─────────────────────────────

const SEVERITY_COLOR: Record<string, string> = {
  CRITICAL: '#F85149',
  HIGH:     '#F85149',
  MEDIUM:   '#D29922',
  LOW:      '#3FB950',
};

// ── Loading stages (cycle while request in-flight) ─────────────────────────────

const LOADING_STAGES = [
  'READING WAREHOUSE STATE',
  'RESOLVING CONTEXT',
  'REASONING',
  'COMPLETE',
];

// ── Props ─────────────────────────────────────────────────────────────────────

interface CopilotDrawerProps {
  warehouseId: string;
  scenarioName: string;
  onClose: () => void;
}

// ── CopilotAnswer sub-component ────────────────────────────────────────────────

interface CopilotAnswerProps {
  turn: CopilotTurnResponse;
  onViewTrace?: () => void;
}

function SeverityBadge({ severity }: { severity: string }) {
  const color = SEVERITY_COLOR[severity?.toUpperCase()] ?? '#484F58';
  return (
    <Box component="span" sx={{
      fontFamily: 'monospace', fontSize: '0.6rem', fontWeight: 700,
      color, border: `1px solid ${color}44`, borderRadius: '3px',
      px: '4px', py: '1px', textTransform: 'uppercase', letterSpacing: '0.08em',
      flexShrink: 0,
    }}>
      {severity}
    </Box>
  );
}

function CopilotAnswer({ turn, onViewTrace }: CopilotAnswerProps) {
  const [detailsOpen, setDetailsOpen] = useState(false);

  const isInsufficient = turn.answerability === 'insufficient_evidence';
  const isPartial = turn.answerability === 'partial';
  const hasEvidence = turn.evidence && turn.evidence.length > 0 && !isInsufficient;

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>

      {/* ── A. ANSWER section ──────────────────────────────────────────────── */}
      <Box>
        <Typography sx={{
          fontFamily: 'monospace', fontSize: '0.58rem', fontWeight: 700,
          color: '#484F58', letterSpacing: '0.12em', textTransform: 'uppercase',
          mb: '4px',
        }}>
          ANSWER
        </Typography>

        {isInsufficient ? (
          <Box>
            <Typography sx={{
              fontFamily: 'monospace', fontSize: '0.72rem', fontWeight: 700,
              color: '#D29922', letterSpacing: '0.06em', mb: '4px',
            }}>
              STATE UNAVAILABLE
            </Typography>
            <Typography sx={{
              fontFamily: 'monospace', fontSize: '0.75rem', color: '#D29922', lineHeight: 1.5,
            }}>
              {turn.degradation_reason ?? 'Warehouse state could not be assembled.'}
            </Typography>
          </Box>
        ) : (
          <Box>
            {isPartial && turn.missing_context.length > 0 && (
              <Typography sx={{
                fontFamily: 'monospace', fontSize: '0.7rem', color: '#D29922',
                mb: '4px', lineHeight: 1.4,
              }}>
                ⚠ PARTIAL — missing: {turn.missing_context.join(', ')}
              </Typography>
            )}
            {turn.answer && (
              <Typography sx={{
                fontFamily: 'monospace', fontSize: '0.8rem', color: '#C9D1D9', lineHeight: 1.5,
              }}>
                {turn.answer}
              </Typography>
            )}
          </Box>
        )}
      </Box>

      {/* ── B. Evidence cards ─────────────────────────────────────────────── */}
      {hasEvidence && (
        <Box>
          <Typography sx={{
            fontFamily: 'monospace', fontSize: '0.58rem', fontWeight: 700,
            color: '#484F58', letterSpacing: '0.12em', textTransform: 'uppercase',
            mb: '6px',
          }}>
            EVIDENCE
          </Typography>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {turn.evidence!.map((fact, idx) => (
              <Box key={idx} sx={{
                background: '#161B22',
                border: '1px solid #21262D',
                borderRadius: '4px',
                p: '8px',
              }}>
                {/* Label row */}
                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: '4px' }}>
                  <Typography sx={{
                    fontFamily: 'monospace', fontSize: '0.65rem', color: '#8B949E',
                    textTransform: 'uppercase', letterSpacing: '0.08em',
                  }}>
                    {fact.label}
                  </Typography>
                  {/* severity comes from fact.severity only — never re-derived */}
                  {fact.severity && <SeverityBadge severity={fact.severity} />}
                </Box>
                {/* Value */}
                <Typography sx={{
                  fontFamily: 'monospace', fontSize: '0.75rem', color: '#C9D1D9',
                  lineHeight: 1.4, mb: '4px',
                }}>
                  {fact.value}
                </Typography>
                {/* Source badge */}
                <Box sx={{ display: 'flex', justifyContent: 'flex-end' }}>
                  <Box component="span" sx={{
                    fontFamily: 'monospace', fontSize: '0.58rem', color: '#3FB950',
                    border: '1px solid #3FB95044', borderRadius: '3px',
                    px: '4px', py: '1px', letterSpacing: '0.06em',
                  }}>
                    STATE
                  </Box>
                </Box>
              </Box>
            ))}
          </Box>
        </Box>
      )}

      {/* ── C. Graph neighborhood status ─────────────────────────────────── */}
      {turn.neighborhood && (
        <Box>
          <Typography sx={{
            fontFamily: 'monospace', fontSize: '0.58rem', fontWeight: 700,
            color: '#484F58', letterSpacing: '0.12em', textTransform: 'uppercase',
            mb: '4px',
          }}>
            CONTEXT
          </Typography>
          <Typography sx={{
            fontFamily: 'monospace', fontSize: '0.7rem', color: '#8B949E',
          }}>
            {turn.neighborhood.focus_entity_label ?? 'No entity focus'} · {turn.neighborhood.entity_count} entities
          </Typography>
          {!turn.neighborhood.graph_available && (
            <Typography sx={{
              fontFamily: 'monospace', fontSize: '0.7rem', color: '#D29922', mt: '3px',
            }}>
              ⚠ Operational Graph context unavailable
            </Typography>
          )}
        </Box>
      )}

      {/* ── Degraded banner ───────────────────────────────────────────────── */}
      {turn.degraded && !isInsufficient && (
        <Box sx={{
          background: '#1A1200',
          border: '1px solid #D2992244',
          borderRadius: '4px',
          px: '8px', py: '5px',
        }}>
          <Typography sx={{
            fontFamily: 'monospace', fontSize: '0.68rem', color: '#D29922',
          }}>
            ⚠ DEGRADED: {turn.degradation_reason}
          </Typography>
        </Box>
      )}

      {/* ── D. Metadata footer (collapsible) ─────────────────────────────── */}
      <Box>
        <Box
          component="button"
          onClick={() => setDetailsOpen(o => !o)}
          sx={{
            background: 'transparent', border: 'none', cursor: 'pointer',
            fontFamily: 'monospace', fontSize: '0.62rem', color: '#484F58',
            p: 0, textAlign: 'left',
            '&:hover': { color: '#8B949E' },
          }}
        >
          DETAILS {detailsOpen ? '▾' : '▸'}
        </Box>
        {detailsOpen && (
          <Box sx={{
            mt: '4px', display: 'flex', flexDirection: 'column', gap: '3px',
            background: '#161B22', border: '1px solid #21262D',
            borderRadius: '4px', p: '8px',
          }}>
            {[
              ['Agent',     turn.agent],
              ['Model',     turn.model_id],
              ['Reasoning', turn.reasoning_level],
              ['Routing',   turn.routing_rule],
              ['Reason',    turn.routing_reason],
              ['Latency',   turn.latency_ms != null ? `${turn.latency_ms}ms` : null],
            ].map(([label, val]) => val != null && (
              <Box key={String(label)} sx={{ display: 'flex', gap: '8px' }}>
                <Typography sx={{
                  fontFamily: 'monospace', fontSize: '0.62rem', color: '#484F58',
                  minWidth: '70px', flexShrink: 0,
                }}>
                  {label}
                </Typography>
                <Typography sx={{
                  fontFamily: 'monospace', fontSize: '0.62rem', color: '#8B949E',
                  wordBreak: 'break-word',
                }}>
                  {String(val)}
                </Typography>
              </Box>
            ))}
            {turn.skills_available && turn.skills_available.length > 0 && (
              <Box sx={{ display: 'flex', gap: '8px' }}>
                <Typography sx={{
                  fontFamily: 'monospace', fontSize: '0.62rem', color: '#484F58',
                  minWidth: '70px', flexShrink: 0,
                }}>
                  Skills
                </Typography>
                <Typography sx={{
                  fontFamily: 'monospace', fontSize: '0.62rem', color: '#8B949E',
                  wordBreak: 'break-word',
                }}>
                  {turn.skills_available.join(', ')}
                </Typography>
              </Box>
            )}
          </Box>
        )}
      </Box>

      {/* ── E. Trace link ────────────────────────────────────────────────── */}
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mt: '2px' }}>
        <Typography sx={{
          fontFamily: 'monospace', fontSize: '0.55rem', color: '#484F58',
          wordBreak: 'break-all', flexGrow: 1, mr: 1,
        }}>
          trace: {turn.trace_id}
        </Typography>
        <Box
          component="button"
          data-testid="copilot-view-trace"
          onClick={() => console.log('[Copilot] View trace:', turn.trace_id, turn)}
          sx={{
            background: 'transparent',
            border: '1px solid #21262D',
            borderRadius: '3px',
            px: '6px', py: '2px',
            fontFamily: 'monospace', fontSize: '0.58rem',
            color: '#484F58', cursor: 'pointer', flexShrink: 0,
            '&:hover': { color: '#58A6FF', borderColor: '#58A6FF44' },
          }}
        >
          VIEW TRACE
        </Box>
      </Box>

    </Box>
  );
}

// Export for direct testing of the rendering logic
export { CopilotAnswer };

// ── Turn entry in conversation thread ─────────────────────────────────────────

interface TurnEntry {
  id: string;
  question: string;
  response: CopilotTurnResponse | null;
  error: string | null;
}

// ── CopilotDrawer ─────────────────────────────────────────────────────────────

export default function CopilotDrawer({ warehouseId, scenarioName, onClose }: CopilotDrawerProps) {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [turns, setTurns] = useState<TurnEntry[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadingStageIdx, setLoadingStageIdx] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const threadRef = useRef<HTMLDivElement>(null);
  const stageTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Cycle loading stage label while loading
  useEffect(() => {
    if (loading) {
      setLoadingStageIdx(0);
      stageTimerRef.current = setInterval(() => {
        setLoadingStageIdx(i => (i + 1) % (LOADING_STAGES.length - 1)); // cycle 0–2 while loading
      }, 800);
    } else {
      if (stageTimerRef.current) {
        clearInterval(stageTimerRef.current);
        stageTimerRef.current = null;
      }
      setLoadingStageIdx(LOADING_STAGES.length - 1); // show COMPLETE briefly
    }
    return () => {
      if (stageTimerRef.current) clearInterval(stageTimerRef.current);
    };
  }, [loading]);

  // Auto-scroll to bottom on new content
  useEffect(() => {
    if (threadRef.current) {
      threadRef.current.scrollTop = threadRef.current.scrollHeight;
    }
  }, [turns, loading]);

  const handleSend = useCallback(async () => {
    const msg = inputMessage.trim();
    if (!msg || loading) return;

    const turnId = `turn-${Date.now()}`;
    setInputMessage('');
    setError(null);
    setLoading(true);

    // Add pending turn entry
    setTurns(prev => [...prev, { id: turnId, question: msg, response: null, error: null }]);

    try {
      const resp = await demoAPI.copilotAsk({
        message: msg,
        conversation_id: conversationId,
        warehouse_id: warehouseId,
        scenario_name: scenarioName,
      });

      // Persist conversation_id across turns
      if (!conversationId) setConversationId(resp.conversation_id);

      setTurns(prev => prev.map(t =>
        t.id === turnId ? { ...t, response: resp } : t
      ));
    } catch (err: any) {
      const msg2 = err?.response?.data?.detail ?? err?.message ?? 'Request failed';
      setTurns(prev => prev.map(t =>
        t.id === turnId ? { ...t, error: String(msg2) } : t
      ));
      setError(String(msg2));
    } finally {
      setLoading(false);
    }
  }, [inputMessage, loading, conversationId, warehouseId, scenarioName]);

  const handleKeyDown = useCallback((e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }, [handleSend]);

  return (
    <Box
      data-testid="copilot-drawer"
      role="complementary"
      aria-label="Copilot ASK panel"
      sx={{
        position: 'fixed',
        top: 0, right: 0,
        width: '360px',
        height: '100vh',
        zIndex: 1300,
        display: 'flex',
        flexDirection: 'column',
        background: '#0D1117',
        border: '1px solid #21262D',
        borderRight: 'none',
        fontFamily: 'monospace',
      }}
    >
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <Box sx={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        px: '14px', py: '10px',
        borderBottom: '1px solid #21262D',
        flexShrink: 0,
      }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Typography sx={{
            fontFamily: 'monospace', fontSize: '0.72rem', fontWeight: 700,
            color: '#58A6FF', letterSpacing: '0.12em', textTransform: 'uppercase',
          }}>
            COPILOT
          </Typography>
          <Box component="span" sx={{
            fontFamily: 'monospace', fontSize: '0.52rem', color: '#58A6FF',
            border: '1px solid #1F6FEB44', borderRadius: '3px',
            px: '4px', py: '0px', lineHeight: 1.6,
          }}>
            ASK
          </Box>
        </Box>
        <Box
          component="button"
          onClick={onClose}
          aria-label="Close Copilot panel"
          sx={{
            background: 'transparent', border: 'none', cursor: 'pointer',
            fontFamily: 'monospace', fontSize: '1rem', color: '#484F58', lineHeight: 1,
            px: '4px', py: '2px',
            '&:hover': { color: '#C9D1D9' },
          }}
        >
          ×
        </Box>
      </Box>

      {/* ── Conversation thread ─────────────────────────────────────────────── */}
      <Box
        ref={threadRef}
        sx={{
          flexGrow: 1,
          overflowY: 'auto',
          px: '14px',
          py: '12px',
          display: 'flex',
          flexDirection: 'column',
          gap: '16px',
          '&::-webkit-scrollbar': { width: '4px' },
          '&::-webkit-scrollbar-track': { background: '#0D1117' },
          '&::-webkit-scrollbar-thumb': { background: '#21262D', borderRadius: '2px' },
        }}
      >
        {/* Empty state */}
        {turns.length === 0 && !loading && (
          <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', mt: '60px', gap: 1 }}>
            <Typography sx={{
              fontFamily: 'monospace', fontSize: '0.65rem', color: '#30363D',
              textAlign: 'center', letterSpacing: '0.06em',
            }}>
              Ask about warehouse state
            </Typography>
            <Typography sx={{
              fontFamily: 'monospace', fontSize: '0.58rem', color: '#21262D',
              textAlign: 'center',
            }}>
              Labor availability · Equipment status · Wave risk · Inventory
            </Typography>
          </Box>
        )}

        {/* Turns */}
        {turns.map((turn) => (
          <Box key={turn.id} sx={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {/* User bubble */}
            <Box sx={{ display: 'flex', justifyContent: 'flex-end' }}>
              <Box sx={{
                background: '#161B22',
                border: '1px solid #21262D',
                borderRadius: '6px',
                px: '10px', py: '7px',
                maxWidth: '85%',
              }}>
                <Typography sx={{
                  fontFamily: 'monospace', fontSize: '0.75rem', color: '#C9D1D9',
                  lineHeight: 1.4,
                }}>
                  {turn.question}
                </Typography>
              </Box>
            </Box>

            {/* ASK response */}
            <Box sx={{ maxWidth: '100%' }}>
              {turn.response ? (
                <CopilotAnswer turn={turn.response} />
              ) : turn.error ? (
                <Typography sx={{
                  fontFamily: 'monospace', fontSize: '0.72rem', color: '#F85149',
                }}>
                  ✗ {turn.error}
                </Typography>
              ) : (
                /* Loading state for this pending turn */
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Box sx={{
                    width: 6, height: 6, borderRadius: '50%',
                    background: '#58A6FF',
                    animation: 'pulse 1s ease-in-out infinite',
                    '@keyframes pulse': {
                      '0%, 100%': { opacity: 0.3 },
                      '50%': { opacity: 1 },
                    },
                  }} />
                  <Typography sx={{
                    fontFamily: 'monospace', fontSize: '0.65rem', color: '#58A6FF',
                    letterSpacing: '0.08em',
                  }}>
                    {LOADING_STAGES[loadingStageIdx]}
                  </Typography>
                </Box>
              )}
            </Box>
          </Box>
        ))}

        {/* Global error (unexpected failure) */}
        {error && turns.length === 0 && (
          <Typography sx={{
            fontFamily: 'monospace', fontSize: '0.7rem', color: '#F85149',
          }}>
            ✗ {error}
          </Typography>
        )}
      </Box>

      {/* ── Input area ─────────────────────────────────────────────────────────── */}
      <Box sx={{
        flexShrink: 0,
        borderTop: '1px solid #21262D',
        px: '12px', py: '10px',
        display: 'flex', gap: '8px',
        background: '#0D1117',
      }}>
        <Box
          component="input"
          data-testid="copilot-input"
          value={inputMessage}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => setInputMessage(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about warehouse state…"
          disabled={loading}
          aria-label="Copilot question input"
          sx={{
            flexGrow: 1,
            background: '#161B22',
            border: '1px solid #21262D',
            borderRadius: '4px',
            px: '10px', py: '7px',
            fontFamily: 'monospace', fontSize: '0.75rem',
            color: '#C9D1D9',
            outline: 'none',
            '&::placeholder': { color: '#484F58' },
            '&:focus': { borderColor: '#30363D' },
            '&:disabled': { opacity: 0.5, cursor: 'not-allowed' },
          }}
        />
        <Box
          component="button"
          data-testid="copilot-send"
          onClick={handleSend}
          disabled={loading || !inputMessage.trim()}
          aria-label="Send question"
          sx={{
            background: loading || !inputMessage.trim() ? 'transparent' : '#1C2128',
            border: '1px solid #21262D',
            borderRadius: '4px',
            px: '12px',
            fontFamily: 'monospace', fontSize: '0.65rem',
            color: loading || !inputMessage.trim() ? '#484F58' : '#58A6FF',
            cursor: loading || !inputMessage.trim() ? 'not-allowed' : 'pointer',
            flexShrink: 0,
            '&:hover:not(:disabled)': { borderColor: '#30363D' },
          }}
        >
          {loading ? '…' : 'ASK'}
        </Box>
      </Box>
    </Box>
  );
}
