// SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0
/**
 * Model Gateway Lab — Phase 18F
 *
 * Read-only developer tool for inspecting evaluation artifacts from phases 18C, 18D, 18E.
 * No live inference. No governance mutations. View-only.
 */

import React, { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  Card,
  CardContent,
  Grid,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Alert,
  Divider,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Button,
  CircularProgress,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline';
import HelpOutlineIcon from '@mui/icons-material/HelpOutline';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import { useNavigate } from 'react-router-dom';
import { modelLabAPI, ModelLabRun, ModelLabCase, ModelStatus } from '../services/api';

// ── Colour constants ───────────────────────────────────────────────────────────
const GREEN = '#76B900';
const DARK_BG = '#0D1117';
const CARD_BORDER = '#21262D';
const RED = '#f85149';
const YELLOW = '#e3b341';
const DIM = '#8B949E';

// ── Small display primitives ──────────────────────────────────────────────────

function AvailableChip() {
  return (
    <Chip
      label="AVAILABLE"
      size="small"
      sx={{ backgroundColor: '#1a3a00', color: GREEN, border: `1px solid ${GREEN}` }}
    />
  );
}

function UnavailableChip() {
  return (
    <Chip
      label="UNAVAILABLE"
      size="small"
      sx={{ backgroundColor: '#2d0a00', color: RED, border: `1px solid ${RED}` }}
    />
  );
}

function NotTestedChip() {
  return (
    <Chip
      label="NOT TESTED"
      size="small"
      sx={{ backgroundColor: '#1a1a00', color: YELLOW, border: `1px solid ${YELLOW}` }}
    />
  );
}

function PassChip() {
  return <Chip label="PASS" size="small" color="success" variant="outlined" />;
}

function FailChip() {
  return <Chip label="FAIL" size="small" color="error" variant="outlined" />;
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <Typography
      variant="caption"
      sx={{ color: DIM, letterSpacing: '0.12em', textTransform: 'uppercase', fontWeight: 700 }}
    >
      {children}
    </Typography>
  );
}

function MonoText({ children }: { children: React.ReactNode }) {
  return (
    <Typography
      variant="body2"
      component="span"
      sx={{ fontFamily: 'monospace', fontSize: '0.82rem', color: '#C9D1D9' }}
    >
      {children}
    </Typography>
  );
}

// ── Methodology badge row ─────────────────────────────────────────────────────

function MethodologyBadges({ run }: { run: ModelLabRun | null }) {
  const leakWarning = run && !run.methodology_valid;
  const badges = [
    { label: 'PROMPT ISOLATED', warn: leakWarning },
    { label: 'FULL RESPONSE GRADED', warn: false },
    { label: 'FIXED CONTEXT', warn: false },
    { label: 'WARM-UP EXCLUDED', warn: false },
    { label: 'POLICY-AWARE', warn: false },
  ];

  return (
    <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mb: 2 }}>
      {badges.map((b) => (
        <Chip
          key={b.label}
          size="small"
          icon={b.warn ? <WarningAmberIcon sx={{ fontSize: '14px !important', color: `${YELLOW} !important` }} /> : undefined}
          label={b.label}
          sx={
            b.warn
              ? { backgroundColor: '#1a1400', color: YELLOW, border: `1px solid ${YELLOW}`, fontSize: '0.7rem' }
              : { backgroundColor: '#161b22', color: DIM, border: `1px solid #30363D`, fontSize: '0.7rem' }
          }
        />
      ))}
      {leakWarning && (
        <Chip
          size="small"
          icon={<WarningAmberIcon sx={{ fontSize: '14px !important', color: `${RED} !important` }} />}
          label="PROMPT METADATA LEAKAGE"
          sx={{ backgroundColor: '#2d0a00', color: RED, border: `1px solid ${RED}`, fontSize: '0.7rem' }}
        />
      )}
    </Box>
  );
}

// ── Model status panel ────────────────────────────────────────────────────────

function ModelStatusPanel({ models }: { models: ModelStatus[] }) {
  return (
    <Card sx={{ backgroundColor: DARK_BG, border: `1px solid ${CARD_BORDER}`, mb: 2 }}>
      <CardContent sx={{ pb: '12px !important' }}>
        <SectionLabel>Model Availability</SectionLabel>
        <Box sx={{ display: 'flex', gap: 2, mt: 1, flexWrap: 'wrap' }}>
          {models.map((m) => (
            <Box key={m.model} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <MonoText>{m.model}</MonoText>
              {m.status === 'AVAILABLE' ? (
                <AvailableChip />
              ) : (
                <>
                  <UnavailableChip />
                  <NotTestedChip />
                </>
              )}
              {m.note && (
                <Typography variant="caption" sx={{ color: YELLOW, fontStyle: 'italic' }}>
                  {m.note}
                </Typography>
              )}
            </Box>
          ))}
        </Box>
      </CardContent>
    </Card>
  );
}

// ── Policy filter pipeline ────────────────────────────────────────────────────

function PolicyPipeline({ caseData }: { caseData: ModelLabCase | null }) {
  const nodes = [
    { label: 'REGISTERED MODELS', sub: 'Super · Lightning · Nano' },
    { label: 'POLICY FILTER', sub: 'risk · reasoning · deployment' },
    { label: 'ELIGIBLE CANDIDATES', sub: caseData?.policy_eligibility || '—' },
    { label: 'RULE ROUTER', sub: 'deterministic strategy' },
    { label: 'SELECTED MODEL', sub: '—' },
  ];

  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0, flexWrap: 'wrap', py: 1 }}>
      {nodes.map((node, idx) => (
        <React.Fragment key={node.label}>
          <Box
            sx={{
              backgroundColor: '#161b22',
              border: `1px solid ${CARD_BORDER}`,
              borderRadius: 1,
              px: 1.5,
              py: 0.5,
              minWidth: 140,
            }}
          >
            <Typography variant="caption" sx={{ color: GREEN, fontWeight: 700, fontSize: '0.68rem', letterSpacing: '0.08em' }}>
              {node.label}
            </Typography>
            <Typography variant="caption" sx={{ color: DIM, display: 'block', fontSize: '0.65rem' }}>
              {node.sub}
            </Typography>
          </Box>
          {idx < nodes.length - 1 && (
            <Typography sx={{ color: GREEN, px: 0.5, fontSize: '1.1rem' }}>→</Typography>
          )}
        </React.Fragment>
      ))}
    </Box>
  );
}

// ── Section A: Evaluation Input ───────────────────────────────────────────────

function SectionEvalInput({ run, caseData }: { run: ModelLabRun | null; caseData: ModelLabCase | null }) {
  return (
    <Card sx={{ backgroundColor: DARK_BG, border: `1px solid ${CARD_BORDER}`, mb: 2 }}>
      <CardContent>
        <SectionLabel>A. Evaluation Input</SectionLabel>
        <Divider sx={{ borderColor: CARD_BORDER, my: 1 }} />
        <Grid container spacing={2}>
          <Grid item xs={12} sm={6}>
            <Box sx={{ mb: 1 }}>
              <SectionLabel>Dataset / Checksum</SectionLabel>
              <Box sx={{ mt: 0.5 }}>
                <MonoText>{run?.dataset_id || '—'}</MonoText>
                <br />
                <MonoText>{run?.checksum || '—'}</MonoText>
              </Box>
            </Box>
            <Box sx={{ mb: 1 }}>
              <SectionLabel>Task Family</SectionLabel>
              <Box sx={{ mt: 0.5 }}>
                <MonoText>{caseData?.task_family || '—'}</MonoText>
              </Box>
            </Box>
            <Box sx={{ mb: 1 }}>
              <SectionLabel>Risk / Reasoning</SectionLabel>
              <Box sx={{ mt: 0.5, display: 'flex', gap: 1 }}>
                <Chip label={caseData?.risk_level || '—'} size="small" sx={{ backgroundColor: '#161b22', color: '#C9D1D9', border: `1px solid ${CARD_BORDER}` }} />
                <Chip label={caseData?.reasoning_level || '—'} size="small" sx={{ backgroundColor: '#161b22', color: '#C9D1D9', border: `1px solid ${CARD_BORDER}` }} />
              </Box>
            </Box>
          </Grid>
          <Grid item xs={12} sm={6}>
            <SectionLabel>Prompt</SectionLabel>
            <Box
              sx={{
                mt: 0.5,
                backgroundColor: '#161b22',
                border: `1px solid ${CARD_BORDER}`,
                borderRadius: 1,
                p: 1.5,
                fontFamily: 'monospace',
                fontSize: '0.82rem',
                color: '#C9D1D9',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                maxHeight: 140,
                overflow: 'auto',
              }}
            >
              {caseData?.prompt || (caseData as any)?.case_prompt || 'Select a case to view prompt.'}
            </Box>
          </Grid>
        </Grid>
        <Box sx={{ mt: 1 }}>
          <SectionLabel>Policy Eligibility</SectionLabel>
          <Box sx={{ mt: 0.5 }}>
            <MonoText>{caseData?.policy_eligibility || caseData?.nano_policy_label || '—'}</MonoText>
          </Box>
        </Box>
      </CardContent>
    </Card>
  );
}

// ── Section B: Router Decision ────────────────────────────────────────────────

function SectionRouterDecision({ run }: { run: ModelLabRun | null }) {
  const gate = (run as any)?.decision_gate;
  return (
    <Card sx={{ backgroundColor: DARK_BG, border: `1px solid ${CARD_BORDER}`, mb: 2 }}>
      <CardContent>
        <SectionLabel>B. Router Decision</SectionLabel>
        <Divider sx={{ borderColor: CARD_BORDER, my: 1 }} />
        {gate ? (
          <Box>
            <Typography variant="body2" sx={{ color: '#C9D1D9', mb: 1 }}>
              <MonoText>{typeof gate === 'string' ? gate : JSON.stringify(gate, null, 2)}</MonoText>
            </Typography>
          </Box>
        ) : (
          <Typography variant="body2" sx={{ color: DIM }}>
            Routing decision data not available for this run.
          </Typography>
        )}
        <Box sx={{ mt: 2 }}>
          <SectionLabel>PolicyFilter Pipeline</SectionLabel>
          <Box sx={{ mt: 1, overflowX: 'auto' }}>
            <PolicyPipeline caseData={null} />
          </Box>
        </Box>
      </CardContent>
    </Card>
  );
}

// ── Section C: Model Comparison ───────────────────────────────────────────────

function SectionModelComparison({ caseData }: { caseData: ModelLabCase | null }) {
  const results = caseData?.model_results || [];
  const summaries = caseData?.model_results_summary || [];

  if (results.length === 0 && summaries.length === 0) {
    return (
      <Card sx={{ backgroundColor: DARK_BG, border: `1px solid ${CARD_BORDER}`, mb: 2 }}>
        <CardContent>
          <SectionLabel>C. Model Comparison</SectionLabel>
          <Divider sx={{ borderColor: CARD_BORDER, my: 1 }} />
          <Typography variant="body2" sx={{ color: DIM }}>
            No model results available for this case / run.
          </Typography>
        </CardContent>
      </Card>
    );
  }

  // Render summary table for 18C (model_results_summary)
  if (summaries.length > 0 && results.length === 0) {
    return (
      <Card sx={{ backgroundColor: DARK_BG, border: `1px solid ${CARD_BORDER}`, mb: 2 }}>
        <CardContent>
          <SectionLabel>C. Model Comparison</SectionLabel>
          <Divider sx={{ borderColor: CARD_BORDER, my: 1 }} />
          <TableContainer>
            <Table size="small" sx={{ '& td, & th': { borderColor: CARD_BORDER } }}>
              <TableHead>
                <TableRow>
                  <TableCell sx={{ color: DIM }}>Model</TableCell>
                  <TableCell sx={{ color: DIM }}>Score</TableCell>
                  <TableCell sx={{ color: DIM }}>Pass</TableCell>
                  <TableCell sx={{ color: DIM }}>Graders Passed</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {summaries.map((s, i) => (
                  <TableRow key={i}>
                    <TableCell><MonoText>{s.model_id?.split('/').pop() || s.model_id}</MonoText></TableCell>
                    <TableCell><MonoText>{s.quality_score ?? '—'}</MonoText></TableCell>
                    <TableCell>{s.quality_pass ? <PassChip /> : <FailChip />}</TableCell>
                    <TableCell><MonoText>{s.passed_graders ?? '—'} / {s.applicable_graders ?? '—'}</MonoText></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </CardContent>
      </Card>
    );
  }

  // Full model results table
  return (
    <Card sx={{ backgroundColor: DARK_BG, border: `1px solid ${CARD_BORDER}`, mb: 2 }}>
      <CardContent>
        <SectionLabel>C. Model Comparison</SectionLabel>
        <Divider sx={{ borderColor: CARD_BORDER, my: 1 }} />
        <TableContainer sx={{ overflowX: 'auto' }}>
          <Table size="small" sx={{ '& td, & th': { borderColor: CARD_BORDER } }}>
            <TableHead>
              <TableRow>
                <TableCell sx={{ color: DIM }}>Model</TableCell>
                <TableCell sx={{ color: DIM }}>Policy</TableCell>
                <TableCell sx={{ color: DIM }}>Acceptable</TableCell>
                <TableCell sx={{ color: DIM }}>Score</TableCell>
                <TableCell sx={{ color: DIM }}>Schema</TableCell>
                <TableCell sx={{ color: DIM }}>Grounding</TableCell>
                <TableCell sx={{ color: DIM }}>Capability</TableCell>
                <TableCell sx={{ color: DIM }}>Target</TableCell>
                <TableCell sx={{ color: DIM }}>Evidence</TableCell>
                <TableCell sx={{ color: DIM }}>Latency</TableCell>
                <TableCell sx={{ color: DIM }}>Status</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {results.map((r, i) => {
                const graders = r.quality?.graders || [];
                const byName = (name: string) => graders.find((g) => g.name === name);
                const schema = byName('schema_validity');
                const halluc = byName('hallucination');
                const cap = byName('capability_match');
                const target = byName('target_match');
                const evidence = byName('required_evidence');
                const critFail = [halluc, cap, target, schema].some((g) => g && !g.passed);
                return (
                  <TableRow key={i}>
                    <TableCell>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                        <MonoText>{r.model_id?.split('/').pop() || r.model_id}</MonoText>
                        {critFail && (
                          <Chip label="CRITICAL" size="small" sx={{ backgroundColor: '#2d0a00', color: RED, border: `1px solid ${RED}`, fontSize: '0.6rem', height: 18 }} />
                        )}
                      </Box>
                    </TableCell>
                    <TableCell>{r.policy_eligible ? <PassChip /> : <FailChip />}</TableCell>
                    <TableCell>{r.quality?.pass ? <PassChip /> : <FailChip />}</TableCell>
                    <TableCell><MonoText>{r.quality?.score ?? '—'}</MonoText></TableCell>
                    <TableCell>{schema ? (schema.passed ? <PassChip /> : <FailChip />) : <MonoText>—</MonoText>}</TableCell>
                    <TableCell>{halluc ? (halluc.passed ? <PassChip /> : <FailChip />) : <MonoText>—</MonoText>}</TableCell>
                    <TableCell>{cap ? (cap.passed ? <PassChip /> : <FailChip />) : <MonoText>—</MonoText>}</TableCell>
                    <TableCell>{target ? (target.passed ? <PassChip /> : <FailChip />) : <MonoText>—</MonoText>}</TableCell>
                    <TableCell>{evidence ? (evidence.passed ? <PassChip /> : <FailChip />) : <MonoText>—</MonoText>}</TableCell>
                    <TableCell><MonoText>{r.latency_ms != null ? `${r.latency_ms}ms` : '—'}</MonoText></TableCell>
                    <TableCell>{r.quality?.pass ? <PassChip /> : <FailChip />}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableContainer>
      </CardContent>
    </Card>
  );
}

// ── Section D: Response Inspector ─────────────────────────────────────────────

function SectionResponseInspector({ caseData }: { caseData: ModelLabCase | null }) {
  const results = caseData?.model_results || [];
  const [selectedModel, setSelectedModel] = useState(0);

  const result = results[selectedModel];

  return (
    <Card sx={{ backgroundColor: DARK_BG, border: `1px solid ${CARD_BORDER}`, mb: 2 }}>
      <CardContent>
        <SectionLabel>D. Response Inspector</SectionLabel>
        <Divider sx={{ borderColor: CARD_BORDER, my: 1 }} />
        {results.length === 0 ? (
          <Typography variant="body2" sx={{ color: DIM }}>
            No model responses available for this run / case.
          </Typography>
        ) : (
          <Box>
            {results.length > 1 && (
              <FormControl size="small" sx={{ mb: 2, minWidth: 200 }}>
                <InputLabel sx={{ color: DIM }}>Model</InputLabel>
                <Select
                  value={selectedModel}
                  label="Model"
                  onChange={(e) => setSelectedModel(Number(e.target.value))}
                  sx={{ color: '#C9D1D9', '.MuiOutlinedInput-notchedOutline': { borderColor: CARD_BORDER } }}
                >
                  {results.map((r, i) => (
                    <MenuItem key={i} value={i}>{r.model_id?.split('/').pop() || r.model_id}</MenuItem>
                  ))}
                </Select>
              </FormControl>
            )}

            {result && (
              <>
                {result.display_preview && (
                  <Box sx={{ mb: 1 }}>
                    <SectionLabel>Display Preview (≤300 chars)</SectionLabel>
                    <Box
                      sx={{
                        mt: 0.5,
                        backgroundColor: '#161b22',
                        border: `1px solid ${CARD_BORDER}`,
                        borderRadius: 1,
                        p: 1.5,
                        fontFamily: 'monospace',
                        fontSize: '0.82rem',
                        color: '#C9D1D9',
                        whiteSpace: 'pre-wrap',
                      }}
                    >
                      {result.display_preview}
                    </Box>
                  </Box>
                )}

                {result.raw_response && (
                  <Box sx={{ mb: 1 }}>
                    <SectionLabel>
                      Raw Response {result.raw_response_truncated ? `(truncated at 10,000 / ${result.raw_response_original_length} chars)` : ''}
                    </SectionLabel>
                    {result.raw_response_truncated && (
                      <Alert severity="info" sx={{ my: 0.5, py: 0, backgroundColor: '#0d1b26' }}>
                        Response truncated for display security. Full length: {result.raw_response_original_length?.toLocaleString()} chars.
                      </Alert>
                    )}
                    <Box
                      sx={{
                        mt: 0.5,
                        backgroundColor: '#161b22',
                        border: `1px solid ${CARD_BORDER}`,
                        borderRadius: 1,
                        p: 1.5,
                        fontFamily: 'monospace',
                        fontSize: '0.78rem',
                        color: '#C9D1D9',
                        whiteSpace: 'pre-wrap',
                        wordBreak: 'break-word',
                        maxHeight: 300,
                        overflow: 'auto',
                      }}
                    >
                      {result.raw_response}
                    </Box>
                  </Box>
                )}

                {/* Grader diagnostics */}
                {result.quality?.graders && result.quality.graders.length > 0 && (
                  <Accordion sx={{ backgroundColor: '#161b22', border: `1px solid ${CARD_BORDER}` }}>
                    <AccordionSummary expandIcon={<ExpandMoreIcon sx={{ color: DIM }} />}>
                      <SectionLabel>Grader Diagnostics ({result.quality.passed_graders}/{result.quality.applicable_graders} passed)</SectionLabel>
                    </AccordionSummary>
                    <AccordionDetails>
                      {result.quality.graders.map((g, gi) => (
                        <Box key={gi} sx={{ mb: 1.5, pb: 1.5, borderBottom: gi < result.quality!.graders.length - 1 ? `1px solid ${CARD_BORDER}` : 'none' }}>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                            <MonoText>{g.name}</MonoText>
                            {g.passed ? <PassChip /> : <FailChip />}
                          </Box>
                          <Typography variant="caption" sx={{ color: DIM }}>{g.reason}</Typography>
                          {g.evidence && g.evidence.length > 0 && (
                            <Box sx={{ mt: 0.5 }}>
                              {g.evidence.map((ev, ei) => (
                                <Typography key={ei} variant="caption" sx={{ color: '#C9D1D9', fontFamily: 'monospace', display: 'block', pl: 1 }}>
                                  • {ev}
                                </Typography>
                              ))}
                            </Box>
                          )}
                        </Box>
                      ))}
                    </AccordionDetails>
                  </Accordion>
                )}
              </>
            )}
          </Box>
        )}
      </CardContent>
    </Card>
  );
}

// ── Section E: Router Assessment ──────────────────────────────────────────────

function SectionRouterAssessment({ run }: { run: ModelLabRun | null }) {
  const verdicts = run?.verdicts;

  return (
    <Card sx={{ backgroundColor: DARK_BG, border: `1px solid ${CARD_BORDER}`, mb: 2 }}>
      <CardContent>
        <SectionLabel>E. Router Assessment</SectionLabel>
        <Divider sx={{ borderColor: CARD_BORDER, my: 1 }} />

        {verdicts ? (
          <Box>
            <Typography
              variant="body1"
              sx={{ color: '#C9D1D9', fontWeight: 600, mb: 1 }}
            >
              ROUTER ASSESSMENT
            </Typography>
            <Typography variant="body2" sx={{ color: DIM, mb: 2 }}>
              No measured production routing defect established.
            </Typography>

            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, mb: 2 }}>
              {Object.entries(verdicts).map(([key, value]) => (
                <Box key={key} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Typography
                    variant="caption"
                    sx={{ color: DIM, textTransform: 'uppercase', width: 80, flexShrink: 0 }}
                  >
                    {key}:
                  </Typography>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                    {value.toUpperCase().includes('UNAVAILABLE') && (
                      <HelpOutlineIcon sx={{ color: YELLOW, fontSize: 16 }} />
                    )}
                    {value.toUpperCase().includes('INCONCLUSIVE') && (
                      <HelpOutlineIcon sx={{ color: YELLOW, fontSize: 16 }} />
                    )}
                    {value.toUpperCase().includes('INSUFFICIENT') && (
                      <HelpOutlineIcon sx={{ color: YELLOW, fontSize: 16 }} />
                    )}
                    <MonoText>{value}</MonoText>
                  </Box>
                </Box>
              ))}
            </Box>

            <Alert
              severity="warning"
              icon={<HelpOutlineIcon />}
              sx={{ backgroundColor: '#1a1400', border: `1px solid ${YELLOW}`, color: YELLOW }}
            >
              <Typography variant="body2" sx={{ fontWeight: 700 }}>
                INSUFFICIENT EVIDENCE
              </Typography>
              <Typography variant="caption">
                Nano endpoint was unavailable (EOL 2026-09-01, operator disabled) during qualification.
                Lightning results remain inconclusive without warm-up-excluded N=5 repetitions.
                Current policy is preserved. Deterministic router retained.
              </Typography>
            </Alert>
          </Box>
        ) : (
          <Box>
            {run?.phase === '18C' && (
              <Alert severity="error" sx={{ backgroundColor: '#2d0a00', border: `1px solid ${RED}` }}>
                <Typography variant="body2" sx={{ color: RED, fontWeight: 700 }}>
                  LEGACY METHODOLOGY — PROMPT METADATA LEAKAGE
                </Typography>
                <Typography variant="caption" sx={{ color: '#C9D1D9' }}>
                  This run has methodology_valid=false. Results should not be used for routing decisions.
                  Leakage of case_id and metadata dict into model system prompt biased responses.
                </Typography>
              </Alert>
            )}
            {run?.phase === '18D' && (
              <Box>
                <Typography variant="body2" sx={{ color: DIM }}>
                  Decision gate from 18D:
                </Typography>
                <Box
                  sx={{
                    mt: 1,
                    backgroundColor: '#161b22',
                    border: `1px solid ${CARD_BORDER}`,
                    borderRadius: 1,
                    p: 1.5,
                    fontFamily: 'monospace',
                    fontSize: '0.82rem',
                    color: '#C9D1D9',
                    whiteSpace: 'pre-wrap',
                  }}
                >
                  {JSON.stringify((run as any)?.decision_gate, null, 2) || 'No decision gate recorded.'}
                </Box>
              </Box>
            )}
            {!run && (
              <Typography variant="body2" sx={{ color: DIM }}>
                Select a run to view router assessment.
              </Typography>
            )}
          </Box>
        )}
      </CardContent>
    </Card>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

const ModelGatewayLab: React.FC = () => {
  const navigate = useNavigate();

  const [runs, setRuns] = useState<ModelLabRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string>('18f');
  const [currentRun, setCurrentRun] = useState<ModelLabRun | null>(null);
  const [cases, setCases] = useState<ModelLabCase[]>([]);
  const [selectedCaseId, setSelectedCaseId] = useState<string>('');
  const [currentCase, setCurrentCase] = useState<ModelLabCase | null>(null);
  const [modelStatus, setModelStatus] = useState<ModelStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Load initial data
  useEffect(() => {
    let mounted = true;
    const load = async () => {
      try {
        setLoading(true);
        const [runsData, statusData] = await Promise.all([
          modelLabAPI.getRuns(),
          modelLabAPI.getModelStatus(),
        ]);
        if (!mounted) return;
        setRuns(runsData);
        setModelStatus(statusData);
        setError(null);
      } catch (e: any) {
        if (!mounted) return;
        setError(`Failed to load Model Lab data: ${e?.message || 'Unknown error'}`);
      } finally {
        if (mounted) setLoading(false);
      }
    };
    load();
    return () => { mounted = false; };
  }, []);

  // Load run detail when run selection changes
  useEffect(() => {
    if (!selectedRunId) return;
    let mounted = true;
    const load = async () => {
      try {
        const [runData, casesData] = await Promise.all([
          modelLabAPI.getRun(selectedRunId),
          modelLabAPI.getRunCases(selectedRunId),
        ]);
        if (!mounted) return;
        setCurrentRun(runData);
        setCases(casesData);
        setSelectedCaseId(casesData[0]?.case_id || '');
        setCurrentCase(null);
      } catch (e: any) {
        if (!mounted) return;
        setError(`Failed to load run ${selectedRunId}: ${e?.message || 'Unknown error'}`);
      }
    };
    load();
    return () => { mounted = false; };
  }, [selectedRunId]);

  // Load case detail when case selection changes
  useEffect(() => {
    if (!selectedRunId || !selectedCaseId) {
      setCurrentCase(null);
      return;
    }
    let mounted = true;
    const load = async () => {
      try {
        const caseData = await modelLabAPI.getRunCase(selectedRunId, selectedCaseId);
        if (!mounted) return;
        setCurrentCase(caseData);
      } catch {
        if (!mounted) return;
        // Case detail may not have full model results for all runs — use summary
        const summary = cases.find((c) => c.case_id === selectedCaseId) || null;
        setCurrentCase(summary);
      }
    };
    load();
    return () => { mounted = false; };
  }, [selectedRunId, selectedCaseId, cases]);

  const runLabel = (r: ModelLabRun) => {
    const prefix = r.phase === '18C' ? '18C — LEGACY METHODOLOGY' :
                   r.phase === '18D' ? '18D — CALIBRATED' :
                   r.phase === '18E' ? '18E — FINAL METHODOLOGY' : r.phase === '18F' ? '18F — CLEAN LIVE RUN' : r.phase;
    return prefix;
  };

  return (
    <Box sx={{ pb: 4 }}>
      {/* Header */}
      <Box sx={{ mb: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
          <Button
            startIcon={<ArrowBackIcon />}
            onClick={() => navigate('/models')}
            size="small"
            sx={{ color: DIM, borderColor: CARD_BORDER }}
            variant="outlined"
          >
            Models
          </Button>
        </Box>
        <Typography variant="h4" sx={{ fontWeight: 700, color: GREEN, letterSpacing: '-0.02em', fontFamily: 'monospace' }}>
          MODEL GATEWAY LAB
        </Typography>
        <Typography variant="body2" sx={{ color: DIM, mt: 0.5 }}>
          Read-only evaluation artifact inspector · Phase 18F · Workstream 3 verdict
        </Typography>
        <Alert severity="info" icon={false} sx={{ mt: 1, backgroundColor: '#0d1b26', border: `1px solid #30363D`, py: 0.5 }}>
          <Typography variant="caption" sx={{ color: DIM }}>
            VIEW ONLY — no live inference, no governance mutations, no routing policy changes
          </Typography>
        </Alert>
      </Box>

      {loading && (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, py: 4 }}>
          <CircularProgress size={20} sx={{ color: GREEN }} />
          <Typography variant="body2" sx={{ color: DIM }}>Loading evaluation artifacts…</Typography>
        </Box>
      )}

      {error && (
        <Alert severity="error" sx={{ mb: 2, backgroundColor: '#2d0a00', border: `1px solid ${RED}` }}>
          <Typography variant="body2">{error}</Typography>
          <Typography variant="caption" sx={{ color: DIM }}>
            Ensure the API server is running and artifacts exist at artifacts/phase18/.
          </Typography>
        </Alert>
      )}

      {!loading && !error && (
        <>
          {/* Model Status */}
          {modelStatus.length > 0 && <ModelStatusPanel models={modelStatus} />}

          {/* Run Selector */}
          <Card sx={{ backgroundColor: DARK_BG, border: `1px solid ${CARD_BORDER}`, mb: 2 }}>
            <CardContent sx={{ pb: '12px !important' }}>
              <Box sx={{ display: 'flex', gap: 2, alignItems: 'flex-start', flexWrap: 'wrap' }}>
                <FormControl size="small" sx={{ minWidth: 280 }}>
                  <InputLabel sx={{ color: DIM }}>Evaluation Run</InputLabel>
                  <Select
                    value={selectedRunId}
                    label="Evaluation Run"
                    onChange={(e) => setSelectedRunId(e.target.value)}
                    sx={{ color: '#C9D1D9', '.MuiOutlinedInput-notchedOutline': { borderColor: CARD_BORDER } }}
                    data-testid="run-selector"
                  >
                    {runs.map((r) => (
                      <MenuItem key={r.run_id} value={r.run_id} data-testid={`run-option-${r.run_id}`}>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                          {runLabel(r)}
                          {!r.methodology_valid && (
                            <WarningAmberIcon sx={{ color: YELLOW, fontSize: 16 }} />
                          )}
                        </Box>
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>

                {cases.length > 0 && (
                  <FormControl size="small" sx={{ minWidth: 280 }}>
                    <InputLabel sx={{ color: DIM }}>Case</InputLabel>
                    <Select
                      value={selectedCaseId}
                      label="Case"
                      onChange={(e) => setSelectedCaseId(e.target.value)}
                      sx={{ color: '#C9D1D9', '.MuiOutlinedInput-notchedOutline': { borderColor: CARD_BORDER } }}
                    >
                      {cases.map((c) => (
                        <MenuItem key={c.case_id} value={c.case_id}>
                          {c.label ? `[${c.label}] ` : ''}{c.case_id}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                )}
              </Box>

              {/* Methodology badges */}
              <Box sx={{ mt: 1.5 }}>
                <MethodologyBadges run={currentRun} />
              </Box>

              {/* Run description */}
              {currentRun && (
                <Typography variant="caption" sx={{ color: DIM }}>
                  {currentRun.description}
                </Typography>
              )}
            </CardContent>
          </Card>

          {/* Five sections */}
          <SectionEvalInput run={currentRun} caseData={currentCase} />
          <SectionRouterDecision run={currentRun} />
          <SectionModelComparison caseData={currentCase} />
          <SectionResponseInspector caseData={currentCase} />
          <SectionRouterAssessment run={currentRun} />
        </>
      )}
    </Box>
  );
};

export default ModelGatewayLab;
