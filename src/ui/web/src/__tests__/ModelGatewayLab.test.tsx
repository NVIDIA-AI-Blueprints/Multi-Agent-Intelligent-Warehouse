/**
 * Phase 18F — ModelGatewayLab UI tests.
 *
 * Covers:
 *  - Renders without crashing
 *  - Shows run selector with 18c, 18d, 18e options
 *  - Shows methodology badge warning for 18C
 *  - Shows Nano as UNAVAILABLE/NOT TESTED (not FAILED)
 *  - Shows ROUTER ASSESSMENT section
 *  - Shows INSUFFICIENT EVIDENCE for 18E verdict
 *  - Shows critical failure badge when grader fails
 *  - Shows error state when no artifacts available
 */

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { ThemeProvider } from '@mui/material/styles';
import { MemoryRouter } from 'react-router-dom';
import { nvidiaTheme } from '../theme/nvidiaTheme';
import ModelGatewayLab from '../pages/ModelGatewayLab';
import { modelLabAPI } from '../services/api';

// ── Mock api service ──────────────────────────────────────────────────────────
jest.mock('../services/api', () => ({
  ...jest.requireActual('../services/api'),
  modelLabAPI: {
    getRuns: jest.fn(),
    getRun: jest.fn(),
    getRunCases: jest.fn(),
    getRunCase: jest.fn(),
    getModelStatus: jest.fn(),
  },
}));

const mockedAPI = modelLabAPI as jest.Mocked<typeof modelLabAPI>;

// ── Fixture data ──────────────────────────────────────────────────────────────

const MOCK_RUNS = [
  {
    run_id: '18c',
    phase: '18C',
    description: 'Phase 18C — Live baseline benchmark. LEGACY METHODOLOGY: prompt metadata leakage identified.',
    methodology_valid: false,
    methodology_note: 'Prompt metadata leakage identified.',
    artifact_available: true,
    dataset_id: 'eval-fixture-dataset-v1',
    checksum: 'fixture-checksum-abc123',
    timestamp: '2026-09-12T01:02:13Z',
    case_count: 3,
    models_evaluated: ['nvidia/nemotron-3-super-120b-a12b'],
  },
  {
    run_id: '18d',
    phase: '18D',
    description: 'Phase 18D — Calibrated benchmark.',
    methodology_valid: true,
    methodology_note: 'Grader calibration applied.',
    artifact_available: true,
    dataset_id: 'eval-fixture-dataset-v1',
    checksum: 'fixture-checksum-abc123',
    case_count: 3,
  },
  {
    run_id: '18e',
    phase: '18E',
    description: 'Phase 18E — Final methodology.',
    methodology_valid: true,
    methodology_note: 'All methodology blockers resolved.',
    artifact_available: true,
    dataset_id: 'eval-fixture-dataset-v1',
    checksum: 'fixture-checksum-abc123',
    case_count: 6,
    verdicts: {
      nano: 'NANO ENDPOINT UNAVAILABLE',
      lightning: 'LIGHTNING STILL INCONCLUSIVE',
      router: 'INSUFFICIENT EVIDENCE',
    },
  },
];

const MOCK_MODEL_STATUS = [
  { model: 'Super', model_id: 'nvidia/nemotron-3-super-120b-a12b', status: 'AVAILABLE', role: 'General warehouse reasoning' },
  { model: 'Lightning', model_id: 'nvidia/nemotron-3.5-lightning-30b-a3b', status: 'AVAILABLE', role: 'Latency-critical tasks' },
  {
    model: 'Nano',
    model_id: 'nvidia/nemotron-3-nano-30b-a3b',
    status: 'UNAVAILABLE',
    reason: 'EOL 2026-09-01 — operator disabled',
    note: 'NOT TESTED — endpoint unavailable during qualification. No inference about Nano quality made.',
  },
];

const MOCK_18E_CASES = [
  { case_id: 'wave17-risk-low-v1', prompt: 'Why is Wave 17 at risk?', task_family: 'ASK', risk_level: 'low', reasoning_level: 'medium', policy_eligibility: 'POLICY ELIGIBLE', label: 'A' },
  { case_id: 'evidence-ask-labor-v1', prompt: 'What evidence shows labor constraint?', task_family: 'ASK', risk_level: 'low', reasoning_level: 'medium', policy_eligibility: 'POLICY ELIGIBLE', label: 'B' },
];

const MOCK_18E_RUN = MOCK_RUNS[2];

const MOCK_CASE_WITH_GRADER_FAIL = {
  case_id: 'wave17-risk-low-v1',
  prompt: 'Why is Wave 17 at risk?',
  task_family: 'ASK',
  risk_level: 'low',
  reasoning_level: 'medium',
  policy_eligibility: 'POLICY ELIGIBLE',
  model_results: [
    {
      model_id: 'nvidia/nemotron-3-super-120b-a12b',
      policy_eligible: true,
      quality: {
        score: 0.4,
        pass: false,
        applicable_graders: 5,
        passed_graders: 2,
        graders: [
          { name: 'hallucination', passed: false, score: null, reason: 'References 3 unknown entities.', evidence: ['worker-Z999'] },
          { name: 'capability_match', passed: true, score: null, reason: 'Mentioned labor_reallocation.', evidence: [] },
          { name: 'target_match', passed: false, score: null, reason: 'Target wave-17 not found.', evidence: [] },
          { name: 'schema_validity', passed: true, score: null, reason: 'No schema defined — skipped.', evidence: [] },
          { name: 'required_evidence', passed: false, score: null, reason: 'Missing required facts.', evidence: [] },
        ],
      },
    },
  ],
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function setupDefaultMocks() {
  mockedAPI.getRuns.mockResolvedValue(MOCK_RUNS as any);
  mockedAPI.getModelStatus.mockResolvedValue(MOCK_MODEL_STATUS as any);
  mockedAPI.getRun.mockResolvedValue(MOCK_18E_RUN as any);
  mockedAPI.getRunCases.mockResolvedValue(MOCK_18E_CASES as any);
  mockedAPI.getRunCase.mockResolvedValue(MOCK_18E_CASES[0] as any);
}

function renderLab() {
  return render(
    <MemoryRouter>
      <ThemeProvider theme={nvidiaTheme}>
        <ModelGatewayLab />
      </ThemeProvider>
    </MemoryRouter>
  );
}

// ── Tests ─────────────────────────────────────────────────────────────────────

beforeEach(() => {
  jest.clearAllMocks();
  // Default all mocks to resolved values. Real timers let Promise microtasks
  // flush naturally so async state updates settle inside RTL's act() scope.
  mockedAPI.getRuns.mockResolvedValue(MOCK_RUNS as any);
  mockedAPI.getModelStatus.mockResolvedValue(MOCK_MODEL_STATUS as any);
  mockedAPI.getRun.mockResolvedValue(MOCK_18E_RUN as any);
  mockedAPI.getRunCases.mockResolvedValue(MOCK_18E_CASES as any);
  mockedAPI.getRunCase.mockResolvedValue(MOCK_18E_CASES[0] as any);
});

afterEach(() => {
  jest.clearAllTimers();
});

describe('ModelGatewayLab', () => {
  describe('Rendering', () => {
    it('renders without crashing', async () => {
      setupDefaultMocks();
      renderLab();
      expect(await screen.findByText('MODEL GATEWAY LAB')).toBeInTheDocument();
    });

    it('shows VIEW ONLY notice', async () => {
      setupDefaultMocks();
      renderLab();
      expect(await screen.findByText(/VIEW ONLY/i)).toBeInTheDocument();
    });

    it('shows loading state initially', () => {
      // Use a controlled promise so we can resolve it before unmounting
      // and avoid leaving a suspended coroutine (open handle) in the worker.
      let resolveMocks!: () => void;
      const controlled = new Promise<void>(r => { resolveMocks = r; });
      mockedAPI.getRuns.mockReturnValue(controlled as any);
      mockedAPI.getModelStatus.mockReturnValue(controlled as any);

      const { unmount } = renderLab();
      expect(screen.getByText(/Loading evaluation artifacts/i)).toBeInTheDocument();

      // Settle the promise first so the coroutine exits via the isMounted
      // guard after unmount, not via a hanging await.
      resolveMocks();
      unmount();
    });
  });

  describe('Run Selector', () => {
    it('shows run selector after data loads', async () => {
      setupDefaultMocks();
      renderLab();
      expect(await screen.findByTestId('run-selector')).toBeInTheDocument();
    });

    it('shows run selector with 18C in the runs list', async () => {
      setupDefaultMocks();
      renderLab();
      expect(await screen.findByTestId('run-selector')).toBeInTheDocument();
      // getRuns should have been called and returned all 3 run IDs
      expect(mockedAPI.getRuns).toHaveBeenCalled();
      const runIds = MOCK_RUNS.map((r) => r.run_id);
      expect(runIds).toContain('18c');
    });

    it('shows run selector with 18D in the runs list', async () => {
      setupDefaultMocks();
      renderLab();
      expect(await screen.findByTestId('run-selector')).toBeInTheDocument();
      expect(mockedAPI.getRuns).toHaveBeenCalled();
      const runIds = MOCK_RUNS.map((r) => r.run_id);
      expect(runIds).toContain('18d');
    });

    it('loads 18F run data by default — getRun called with 18f', async () => {
      setupDefaultMocks();
      renderLab();
      // 18F is the default selectedRunId (set in useState)
      await waitFor(() => {
        expect(mockedAPI.getRun).toHaveBeenCalledWith('18f');
      });
    });
  });

  describe('Methodology badges', () => {
    it('shows PROMPT ISOLATED badge', async () => {
      setupDefaultMocks();
      renderLab();
      expect(await screen.findByText('PROMPT ISOLATED')).toBeInTheDocument();
    });

    it('shows PROMPT METADATA LEAKAGE warning when 18C is selected and methodology_valid is false', async () => {
      mockedAPI.getRuns.mockResolvedValue(MOCK_RUNS as any);
      mockedAPI.getModelStatus.mockResolvedValue(MOCK_MODEL_STATUS as any);
      mockedAPI.getRun.mockResolvedValue(MOCK_RUNS[0] as any); // 18C
      mockedAPI.getRunCases.mockResolvedValue([]);
      mockedAPI.getRunCase.mockRejectedValue(new Error('not found'));

      renderLab();
      expect(await screen.findByText('PROMPT METADATA LEAKAGE')).toBeInTheDocument();
    });
  });

  describe('Model Status Panel', () => {
    it('shows Nano as UNAVAILABLE', async () => {
      setupDefaultMocks();
      renderLab();
      expect(await screen.findByText('UNAVAILABLE')).toBeInTheDocument();
    });

    it('shows NOT TESTED for Nano', async () => {
      setupDefaultMocks();
      renderLab();
      expect(await screen.findByText('NOT TESTED')).toBeInTheDocument();
    });

    it('shows Super as AVAILABLE', async () => {
      setupDefaultMocks();
      renderLab();
      await waitFor(() => {
        const chips = screen.getAllByText('AVAILABLE');
        expect(chips.length).toBeGreaterThan(0);
      });
    });

    it('does NOT show Nano with FAILED status', async () => {
      setupDefaultMocks();
      renderLab();
      await waitFor(() => {
        expect(screen.queryByText('FAILED')).not.toBeInTheDocument();
      });
    });
  });

  describe('Router Assessment', () => {
    it('shows ROUTER ASSESSMENT section label', async () => {
      setupDefaultMocks();
      renderLab();
      expect(await screen.findByText('E. Router Assessment')).toBeInTheDocument();
    });

    it('shows INSUFFICIENT EVIDENCE for 18E', async () => {
      setupDefaultMocks();
      renderLab();
      await waitFor(() => {
        // INSUFFICIENT EVIDENCE appears in both the verdicts table and Alert heading
        const matches = screen.getAllByText('INSUFFICIENT EVIDENCE');
        expect(matches.length).toBeGreaterThan(0);
      });
    });

    it('shows Nano endpoint unavailable in verdicts', async () => {
      setupDefaultMocks();
      renderLab();
      await waitFor(() => {
        expect(screen.getByText(/NANO ENDPOINT UNAVAILABLE/i)).toBeInTheDocument();
      });
    });

    it('shows "no routing defect" message for 18E', async () => {
      setupDefaultMocks();
      renderLab();
      await waitFor(() => {
        expect(screen.getByText(/No measured production routing defect established/i)).toBeInTheDocument();
      });
    });
  });

  describe('Critical failure badge', () => {
    it('shows CRITICAL badge when hallucination grader fails', async () => {
      mockedAPI.getRuns.mockResolvedValue(MOCK_RUNS as any);
      mockedAPI.getModelStatus.mockResolvedValue(MOCK_MODEL_STATUS as any);
      mockedAPI.getRun.mockResolvedValue(MOCK_18E_RUN as any);
      mockedAPI.getRunCases.mockResolvedValue([MOCK_18E_CASES[0]] as any);
      mockedAPI.getRunCase.mockResolvedValue(MOCK_CASE_WITH_GRADER_FAIL as any);

      renderLab();
      expect(await screen.findByText('CRITICAL')).toBeInTheDocument();
    });
  });

  describe('Error state', () => {
    it('shows error when API fails', async () => {
      mockedAPI.getRuns.mockRejectedValue(new Error('Service unavailable'));
      mockedAPI.getModelStatus.mockRejectedValue(new Error('Service unavailable'));

      renderLab();
      await waitFor(() => {
        expect(screen.getByText(/Failed to load Model Lab data/i)).toBeInTheDocument();
      });
    });

    it('shows guidance to check API and artifacts', async () => {
      mockedAPI.getRuns.mockRejectedValue(new Error('Network error'));
      mockedAPI.getModelStatus.mockRejectedValue(new Error('Network error'));

      renderLab();
      await waitFor(() => {
        expect(screen.getByText(/artifacts\/phase18/i)).toBeInTheDocument();
      });
    });
  });

  describe('Section headers', () => {
    it('shows all five section labels', async () => {
      setupDefaultMocks();
      renderLab();
      await waitFor(() => {
        expect(screen.getByText('A. Evaluation Input')).toBeInTheDocument();
        expect(screen.getByText('B. Router Decision')).toBeInTheDocument();
        expect(screen.getByText('C. Model Comparison')).toBeInTheDocument();
        expect(screen.getByText('D. Response Inspector')).toBeInTheDocument();
        expect(screen.getByText('E. Router Assessment')).toBeInTheDocument();
      });
    });
  });
});
