/**
 * CopilotDrawer.tsx — Phase 15D Copilot ASK + ANALYZE + ACT panel.
 *
 * Right-side overlay drawer for operator questions, recommendations, and governed
 * action requests. ACT routes through GovernedActionOrchestrator — no inline
 * APPROVE/EXECUTE buttons here. Approval happens in the existing MAIW approval UI.
 *
 * Constraints:
 *   - No chain_of_thought / scratchpad / hidden_reasoning / reasoning_tokens
 *   - No inline APPROVE / EXECUTE / force-action buttons in this drawer
 *   - "No warehouse changes have been made." always visible before approval/execution
 *   - Severity comes from fact.severity ONLY — never re-derived from value text
 *   - skills_used is always [] for ASK/ANALYZE — not shown
 */

import React, { useState, useRef, useEffect, useCallback, KeyboardEvent } from 'react';
import { Box, Typography } from '@mui/material';
import { demoAPI, CopilotTurnResponse, CopilotRecommendation } from '../../../services/demoAPI';

// ── Color constants (MAIW dark terminal aesthetic) ─────────────────────────────

const SEVERITY_COLOR: Record<string, string> = {
  CRITICAL: '#F85149',
  HIGH:     '#F85149',
  MEDIUM:   '#D29922',
  LOW:      '#3FB950',
};

const PRIORITY_COLOR: Record<string, string> = {
  CRITICAL: '#F85149',
  HIGH:     '#F85149',
  MEDIUM:   '#D29922',
  LOW:      '#3FB950',
};

const DECISION_OUTCOME_COLOR: Record<string, string> = {
  REQUIRES_HUMAN_APPROVAL: '#D29922',
  APPROVED:                '#3FB950',
  REJECTED:                '#F85149',
  REQUIRES_FRESH_STATE:    '#D29922',
  STALE_STATE:             '#D29922',
  CLARIFICATION_REQUIRED:  '#58A6FF',
  NOT_IMPLEMENTED:         '#484F58',
  ERROR:                   '#F85149',
};

const MUTATION_STATE_COLOR: Record<string, string> = {
  NOT_ATTEMPTED: '#484F58',
  CONFIRMED:     '#3FB950',
  UNKNOWN:       '#D29922',
};

// ── Loading stage sequences ────────────────────────────────────────────────────

const LOADING_STAGES_ASK = [
  'READING WAREHOUSE STATE',
  'RESOLVING CONTEXT',
  'REASONING',
  'COMPLETE',
];

const LOADING_STAGES_ANALYZE = [
  'READING STATE',
  'RESOLVING CONTEXT',
  'ANALYZING',
  'COMPLETE',
];

const LOADING_STAGES_ACT = [
  'RESOLVING RECOMMENDATION',
  'READING CURRENT STATE',
  'VALIDATING',
  'PREPARING GOVERNED ACTION',
  'EVALUATING POLICY',
  'COMPLETE',
];

// ── Suggested prompts (shown after a turn completes) ──────────────────────────

const SUGGEST_AFTER_ASK     = ['What should we do?'];
const SUGGEST_AFTER_ANALYZE = ['Do it.'];

// ── Props ─────────────────────────────────────────────────────────────────────

interface CopilotDrawerProps {
  warehouseId: string;
  scenarioName: string;
  onClose: () => void;
}

// ── Sub-components ─────────────────────────────────────────────────────────────

interface CopilotAnswerProps {
  turn: CopilotTurnResponse;
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

function RecommendationCard({ rec, index }: { rec: CopilotRecommendation; index: number }) {
  const [open, setOpen] = useState(false);
  const priColor = PRIORITY_COLOR[rec.priority?.toUpperCase()] ?? '#484F58';

  return (
    <Box sx={{
      background: '#161B22',
      border: '1px solid #21262D',
      borderLeft: `3px solid ${priColor}88`,
      borderRadius: '4px',
      p: '10px',
    }}>
      {/* Header row */}
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: '6px' }}>
        <Typography sx={{
          fontFamily: 'monospace', fontSize: '0.58rem', color: '#484F58',
          textTransform: 'uppercase', letterSpacing: '0.1em',
        }}>
          RECOMMENDATION {index + 1}
        </Typography>
        <Box component="span" sx={{
          fontFamily: 'monospace', fontSize: '0.58rem', fontWeight: 700,
          color: priColor, border: `1px solid ${priColor}44`, borderRadius: '3px',
          px: '4px', py: '1px', textTransform: 'uppercase', letterSpacing: '0.08em',
        }}>
          {rec.priority}
        </Box>
      </Box>

      {/* Objective */}
      <Typography sx={{
        fontFamily: 'monospace', fontSize: '0.78rem', fontWeight: 600,
        color: '#C9D1D9', lineHeight: 1.4, mb: '6px',
      }}>
        {rec.objective}
      </Typography>

      {/* Why */}
      <Typography sx={{
        fontFamily: 'monospace', fontSize: '0.68rem', color: '#8B949E',
        lineHeight: 1.5, mb: '6px',
      }}>
        {rec.rationale}
      </Typography>

      {/* Capability row */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: '6px', mb: '3px' }}>
        <Typography sx={{
          fontFamily: 'monospace', fontSize: '0.55rem', color: '#484F58',
          textTransform: 'uppercase', letterSpacing: '0.08em', minWidth: '68px', flexShrink: 0,
        }}>
          CAPABILITY
        </Typography>
        <Box component="span" sx={{
          fontFamily: 'monospace', fontSize: '0.6rem', color: '#58A6FF',
          border: '1px solid #1F6FEB33', borderRadius: '3px',
          px: '4px', py: '1px', wordBreak: 'break-all',
        }}>
          {rec.capability}
        </Box>
      </Box>
      {/* Target row */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: '6px', mb: '4px' }}>
        <Typography sx={{
          fontFamily: 'monospace', fontSize: '0.55rem', color: '#484F58',
          textTransform: 'uppercase', letterSpacing: '0.08em', minWidth: '68px', flexShrink: 0,
        }}>
          TARGET
        </Typography>
        <Box component="span" sx={{
          fontFamily: 'monospace', fontSize: '0.6rem', color: '#3FB950',
          border: '1px solid #3FB95033', borderRadius: '3px',
          px: '4px', py: '1px',
        }}>
          {rec.target}
        </Box>
      </Box>

      {/* Expert details toggle */}
      <Box
        component="button"
        onClick={() => setOpen(o => !o)}
        sx={{
          background: 'transparent', border: 'none', cursor: 'pointer',
          fontFamily: 'monospace', fontSize: '0.58rem', color: '#30363D',
          p: 0, mt: '4px',
          '&:hover': { color: '#484F58' },
        }}
      >
        SOURCE {open ? '▾' : '▸'}
      </Box>
      {open && (
        <Box sx={{ mt: '4px', display: 'flex', flexDirection: 'column', gap: '2px' }}>
          {[
            ['Snapshot',   rec.snapshot_id?.slice(0, 8)],
            ['Trace',      rec.trace_id?.slice(0, 8)],
            ['Focus',      rec.focus_entity_id],
            ['Domain',     rec.domain],
            ['ID',         rec.recommendation_id],
          ].map(([label, val]) => val && (
            <Box key={String(label)} sx={{ display: 'flex', gap: '6px' }}>
              <Typography sx={{
                fontFamily: 'monospace', fontSize: '0.58rem', color: '#30363D',
                minWidth: '58px', flexShrink: 0,
              }}>
                {label}
              </Typography>
              <Typography sx={{
                fontFamily: 'monospace', fontSize: '0.58rem', color: '#484F58',
                wordBreak: 'break-all',
              }}>
                {String(val)}
              </Typography>
            </Box>
          ))}
        </Box>
      )}
    </Box>
  );
}

function CopilotActAnswer({ turn }: CopilotAnswerProps) {
  const [detailsOpen, setDetailsOpen] = useState(false);

  const outcome   = turn.act_decision_outcome ?? 'NOT_IMPLEMENTED';
  const mutState  = turn.act_mutation_state   ?? 'NOT_ATTEMPTED';
  const outColor  = DECISION_OUTCOME_COLOR[outcome]  ?? '#484F58';
  const mutColor  = MUTATION_STATE_COLOR[mutState]   ?? '#484F58';
  const safetyNote = turn.safety_note ?? 'No warehouse changes have been made.';
  const confirmed = mutState === 'CONFIRMED';

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>

      {/* Section header */}
      <Typography sx={{
        fontFamily: 'monospace', fontSize: '0.58rem', fontWeight: 700,
        color: '#484F58', letterSpacing: '0.12em', textTransform: 'uppercase',
        mb: '2px',
      }}>
        AI REQUEST
      </Typography>

      {/* Decision outcome badge */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: '6px', mb: '2px' }}>
        <Box component="span" data-testid="copilot-act-decision-outcome" sx={{
          fontFamily: 'monospace', fontSize: '0.6rem', fontWeight: 700,
          color: outColor, border: `1px solid ${outColor}44`, borderRadius: '3px',
          px: '5px', py: '1px', textTransform: 'uppercase', letterSpacing: '0.08em',
        }}>
          {outcome.replace(/_/g, ' ')}
        </Box>
        <Box component="span" data-testid="copilot-act-mutation-state" sx={{
          fontFamily: 'monospace', fontSize: '0.6rem', fontWeight: 700,
          color: mutColor, border: `1px solid ${mutColor}44`, borderRadius: '3px',
          px: '5px', py: '1px', textTransform: 'uppercase', letterSpacing: '0.08em',
        }}>
          {mutState.replace(/_/g, ' ')}
        </Box>
      </Box>

      {/* Answer text */}
      {turn.answer && (
        <Typography sx={{
          fontFamily: 'monospace', fontSize: '0.78rem', color: '#C9D1D9', lineHeight: 1.5,
        }}>
          {turn.answer}
        </Typography>
      )}

      {/* Safety note — always visible before approval/execution */}
      <Box
        data-testid="copilot-act-safety-note"
        sx={{
          background: confirmed ? '#0D1B0D' : '#1A1200',
          border: `1px solid ${confirmed ? '#3FB95044' : '#D2992244'}`,
          borderRadius: '4px',
          px: '10px', py: '7px',
        }}
      >
        <Typography sx={{
          fontFamily: 'monospace', fontSize: '0.7rem',
          color: confirmed ? '#3FB950' : '#D29922',
        }}>
          {confirmed ? '✓' : '⏳'} {safetyNote}
        </Typography>
      </Box>

      {/* Pending approval link — no inline APPROVE button */}
      {outcome === 'REQUIRES_HUMAN_APPROVAL' && turn.act_pending_approval_id && (
        <Box sx={{
          background: '#0D1117',
          border: '1px solid #D2992244',
          borderRadius: '4px',
          px: '10px', py: '7px',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <Typography sx={{
            fontFamily: 'monospace', fontSize: '0.68rem', color: '#D29922',
          }}>
            Pending review: {turn.act_pending_approval_id.slice(0, 12)}…
          </Typography>
          <Box
            component="button"
            data-testid="copilot-act-review-approval"
            onClick={() => console.log('[Copilot ACT] Review approval:', turn.act_pending_approval_id, turn)}
            sx={{
              background: 'transparent',
              border: '1px solid #D2992244',
              borderRadius: '3px',
              px: '6px', py: '2px',
              fontFamily: 'monospace', fontSize: '0.58rem',
              color: '#D29922', cursor: 'pointer', flexShrink: 0,
              '&:hover': { color: '#F0A400', borderColor: '#F0A40044' },
            }}
          >
            REVIEW APPROVAL
          </Box>
        </Box>
      )}

      {/* Violations */}
      {turn.act_violations && turn.act_violations.length > 0 && (
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          {turn.act_violations.map((v, i) => (
            <Typography key={i} sx={{
              fontFamily: 'monospace', fontSize: '0.68rem', color: '#F85149', lineHeight: 1.4,
            }}>
              ✗ [{v.code}] {v.message}
            </Typography>
          ))}
        </Box>
      )}

      {/* Governance details (collapsible) */}
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
          GOVERNANCE {detailsOpen ? '▾' : '▸'}
        </Box>
        {detailsOpen && (
          <Box sx={{
            mt: '4px', display: 'flex', flexDirection: 'column', gap: '3px',
            background: '#161B22', border: '1px solid #21262D',
            borderRadius: '4px', p: '8px',
          }}>
            {([
              ['Capability',    turn.act_recommendation_id ? turn.recommendations?.[0]?.capability : null],
              ['Proposal ID',   turn.act_proposal_id?.slice(0, 12)],
              ['Decision ID',   turn.act_decision_id?.slice(0, 12)],
              ['Pending ID',    turn.act_pending_approval_id?.slice(0, 12)],
              ['Execution ID',  turn.act_execution_id?.slice(0, 12)],
              ['Exec Status',   turn.act_execution_status],
              ['Snapshot S1',   turn.act_source_snapshot_id?.slice(0, 8)],
              ['Latency',       turn.latency_ms != null ? `${turn.latency_ms}ms` : null],
            ] as [string, string | null | undefined][]).map(([label, val]) => val != null && (
              <Box key={label} sx={{ display: 'flex', gap: '8px' }}>
                <Typography sx={{
                  fontFamily: 'monospace', fontSize: '0.62rem', color: '#484F58',
                  minWidth: '80px', flexShrink: 0,
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
          </Box>
        )}
      </Box>

      {/* Trace */}
      <Typography sx={{
        fontFamily: 'monospace', fontSize: '0.55rem', color: '#484F58',
        wordBreak: 'break-all',
      }}>
        trace: {turn.trace_id}
      </Typography>
    </Box>
  );
}

function CopilotAnswer({ turn }: CopilotAnswerProps) {
  const [detailsOpen, setDetailsOpen] = useState(false);

  const isAnalyze = turn.intent === 'analyze';
  const isInsufficient = turn.answerability === 'insufficient_evidence';
  const isPartial = turn.answerability === 'partial';
  const hasEvidence = turn.evidence && turn.evidence.length > 0 && !isInsufficient;
  const hasRecs = isAnalyze && turn.recommendations && turn.recommendations.length > 0;

  const answerLabel = isAnalyze ? 'ANALYSIS' : 'ANSWER';

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>

      {/* ── A. ANSWER / ANALYSIS section ──────────────────────────────────── */}
      <Box>
        <Typography sx={{
          fontFamily: 'monospace', fontSize: '0.58rem', fontWeight: 700,
          color: '#484F58', letterSpacing: '0.12em', textTransform: 'uppercase',
          mb: '4px',
        }}>
          {answerLabel}
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
            {/* severity badge for ANALYZE */}
            {isAnalyze && turn.severity && (
              <Box sx={{ mb: '6px' }}>
                <SeverityBadge severity={turn.severity} />
              </Box>
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
                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: '4px' }}>
                  <Typography sx={{
                    fontFamily: 'monospace', fontSize: '0.65rem', color: '#8B949E',
                    textTransform: 'uppercase', letterSpacing: '0.08em',
                  }}>
                    {fact.label}
                  </Typography>
                  {fact.severity && <SeverityBadge severity={fact.severity} />}
                </Box>
                <Typography sx={{
                  fontFamily: 'monospace', fontSize: '0.75rem', color: '#C9D1D9',
                  lineHeight: 1.4, mb: '4px',
                }}>
                  {fact.value}
                </Typography>
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

      {/* ── C. Recommendation cards (ANALYZE only) ────────────────────────── */}
      {hasRecs && (
        <Box>
          <Typography sx={{
            fontFamily: 'monospace', fontSize: '0.58rem', fontWeight: 700,
            color: '#484F58', letterSpacing: '0.12em', textTransform: 'uppercase',
            mb: '6px',
          }}>
            RECOMMENDED ACTIONS
          </Typography>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {turn.recommendations!.map((rec, i) => (
              <RecommendationCard key={rec.recommendation_id} rec={rec} index={i} />
            ))}
          </Box>
        </Box>
      )}

      {/* ── D. Safety note (ANALYZE only) ─────────────────────────────────── */}
      {isAnalyze && !isInsufficient && (
        <Box sx={{
          background: '#0D1B0D',
          border: '1px solid #3FB95044',
          borderRadius: '4px',
          px: '10px', py: '7px',
        }}>
          <Typography sx={{
            fontFamily: 'monospace', fontSize: '0.7rem', color: '#3FB950',
          }}>
            ✓ {turn.safety_note ?? 'No warehouse changes have been made.'}
          </Typography>
        </Box>
      )}

      {/* ── E. Graph neighborhood status ──────────────────────────────────── */}
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
            {turn.focus_entity_label ?? turn.neighborhood.focus_entity_label ?? 'No entity focus'} · {turn.neighborhood.entity_count} entities
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

      {/* ── F. Degraded banner ────────────────────────────────────────────── */}
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

      {/* ── G. Details panel (collapsible) ────────────────────────────────── */}
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
            {([
              ['Agent',        turn.agent],
              ['Model',        turn.model_id],
              ['Reasoning',    turn.reasoning_level],
              ['Routing',      turn.routing_rule],
              ['Preferred',    turn.requested_role],
              ['Selected',     turn.selected_role],
              ['Reason',       turn.routing_reason],
              ['Fallback',     turn.fallback_from ? `${turn.fallback_from} → ${turn.selected_role}` : null],
              ['Fallback why', turn.fallback_reason],
              ['Latency',      turn.latency_ms != null ? `${turn.latency_ms}ms` : null],
            ] as [string, string | null | undefined][]).map(([label, val]) => val != null && (
              <Box key={label} sx={{ display: 'flex', gap: '8px' }}>
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

      {/* ── H. Trace link ─────────────────────────────────────────────────── */}
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
export { CopilotAnswer, CopilotActAnswer };

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
  const [pendingIntent, setPendingIntent] = useState<'ask' | 'analyze' | 'act'>('ask');
  const [error, setError] = useState<string | null>(null);

  const threadRef = useRef<HTMLDivElement>(null);
  const stageTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const activeStages =
    pendingIntent === 'act'     ? LOADING_STAGES_ACT :
    pendingIntent === 'analyze' ? LOADING_STAGES_ANALYZE :
    LOADING_STAGES_ASK;

  // Cycle loading stage label while loading
  useEffect(() => {
    if (loading) {
      setLoadingStageIdx(0);
      stageTimerRef.current = setInterval(() => {
        setLoadingStageIdx(i => (i + 1) % (activeStages.length - 1));
      }, 800);
    } else {
      if (stageTimerRef.current) {
        clearInterval(stageTimerRef.current);
        stageTimerRef.current = null;
      }
      setLoadingStageIdx(activeStages.length - 1);
    }
    return () => {
      if (stageTimerRef.current) clearInterval(stageTimerRef.current);
    };
  }, [loading, activeStages.length]);

  // Auto-scroll to bottom on new content
  useEffect(() => {
    if (threadRef.current) {
      threadRef.current.scrollTop = threadRef.current.scrollHeight;
    }
  }, [turns, loading]);

  const handleSend = useCallback(async (msg?: string) => {
    const text = (msg ?? inputMessage).trim();
    if (!text || loading) return;

    // Detect intended intent client-side for loading stage label
    const looksLikeAct     = /\b(do it|proceed|execute|apply|allocate the|reprioritize|prepare (that|this|the) action|do (the )?(first|second|third|1st|2nd|#?1|#?2|one|that))\b/i.test(text);
    const looksLikeAnalyze = /\b(recommend|what should (we|i|you)|how should (we|i|you)|best action|what actions?)\b/i.test(text);
    setPendingIntent(looksLikeAct ? 'act' : looksLikeAnalyze ? 'analyze' : 'ask');

    const turnId = `turn-${Date.now()}`;
    setInputMessage('');
    setError(null);
    setLoading(true);

    setTurns(prev => [...prev, { id: turnId, question: text, response: null, error: null }]);

    try {
      const resp = await demoAPI.copilotAsk({
        message: text,
        conversation_id: conversationId,
        warehouse_id: warehouseId,
        scenario_name: scenarioName,
      });

      if (!conversationId) setConversationId(resp.conversation_id);

      setTurns(prev => prev.map(t =>
        t.id === turnId ? { ...t, response: resp } : t
      ));
    } catch (err: any) {
      const errMsg = err?.response?.data?.detail ?? err?.message ?? 'Request failed';
      setTurns(prev => prev.map(t =>
        t.id === turnId ? { ...t, error: String(errMsg) } : t
      ));
      setError(String(errMsg));
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

  // Determine if last completed turn was ASK or ANALYZE (for suggested prompts)
  const lastResponse = turns.length > 0 ? turns[turns.length - 1].response : null;
  const showAskSuggest     = !loading && lastResponse?.intent === 'ask' &&
    lastResponse?.answerability === 'answerable';
  const showAnalyzeSuggest = !loading && lastResponse?.intent === 'analyze' &&
    (lastResponse?.recommendations?.length ?? 0) > 0;

  return (
    <Box
      data-testid="copilot-drawer"
      role="complementary"
      aria-label="Copilot panel"
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
            ASK · ANALYZE · ACT
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
              Ask about warehouse state or request recommendations
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

            {/* Response */}
            <Box sx={{ maxWidth: '100%' }}>
              {turn.response ? (
                turn.response.intent === 'act'
                  ? <CopilotActAnswer turn={turn.response} />
                  : <CopilotAnswer turn={turn.response} />
              ) : turn.error ? (
                <Typography sx={{
                  fontFamily: 'monospace', fontSize: '0.72rem', color: '#F85149',
                }}>
                  ✗ {turn.error}
                </Typography>
              ) : (
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
                    {activeStages[loadingStageIdx]}
                  </Typography>
                </Box>
              )}
            </Box>
          </Box>
        ))}

        {/* Suggested prompt after ASK */}
        {showAskSuggest && (
          <Box sx={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
            {SUGGEST_AFTER_ASK.map(prompt => (
              <Box
                key={prompt}
                component="button"
                data-testid="copilot-suggested-prompt"
                onClick={() => handleSend(prompt)}
                sx={{
                  background: 'transparent',
                  border: '1px solid #21262D',
                  borderRadius: '4px',
                  px: '8px', py: '4px',
                  fontFamily: 'monospace', fontSize: '0.65rem',
                  color: '#484F58', cursor: 'pointer',
                  '&:hover': { color: '#58A6FF', borderColor: '#58A6FF44' },
                }}
              >
                {prompt}
              </Box>
            ))}
          </Box>
        )}

        {/* Suggested "Do it." after ANALYZE */}
        {showAnalyzeSuggest && (
          <Box sx={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
            {SUGGEST_AFTER_ANALYZE.map(prompt => (
              <Box
                key={prompt}
                component="button"
                data-testid="copilot-act-suggested-prompt"
                onClick={() => handleSend(prompt)}
                sx={{
                  background: 'transparent',
                  border: '1px solid #D2992244',
                  borderRadius: '4px',
                  px: '8px', py: '4px',
                  fontFamily: 'monospace', fontSize: '0.65rem',
                  color: '#D29922', cursor: 'pointer',
                  '&:hover': { color: '#F0A400', borderColor: '#F0A40044' },
                }}
              >
                {prompt}
              </Box>
            ))}
          </Box>
        )}

        {/* Global error */}
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
          placeholder="Ask or request recommendations…"
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
          onClick={() => handleSend()}
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
          {loading ? '…' : 'SEND'}
        </Box>
      </Box>
    </Box>
  );
}
