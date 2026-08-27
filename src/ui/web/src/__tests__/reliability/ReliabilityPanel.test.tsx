import React from 'react';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import { ThemeProvider } from '@mui/material/styles';
import { nvidiaTheme } from '../../theme/nvidiaTheme';
import ReliabilityPanel from '../../components/reliability/ReliabilityPanel';
import { RuntimeStatus } from '../../services/api';

function wrap(runtime: RuntimeStatus | undefined) {
  return render(
    <ThemeProvider theme={nvidiaTheme}>
      <ReliabilityPanel runtime={runtime} />
    </ThemeProvider>
  );
}

const healthy: RuntimeStatus = {
  runtime_initialized: true,
  model_gateway_available: true,
  decision_engine_available: true,
  state_provider_available: true,
  inventory_mcp_configured: true,
  equipment_mcp_configured: true,
  labor_mcp_configured: true,
  wave_mcp_configured: true,
  equipment_agent_available: true,
  operations_agent_available: true,
  safety_agent_available: true,
  equipment_executor_available: true,
  labor_executor_available: true,
  wave_executor_available: true,
  maiw_operational_status: 'HEALTHY',
  model_gateway_status: 'HEALTHY',
  domain_health: {
    equipment: 'HEALTHY',
    labor: 'HEALTHY',
    wave: 'HEALTHY',
    inventory: 'HEALTHY',
  },
  circuit_states: {
    nim: { state: 'CLOSED', failure_count: 0, success_count: 10, last_failure_at: null },
    domains: [
      { name: 'equipment', state: 'CLOSED', failure_count: 0, success_count: 5, last_failure_at: null },
      { name: 'labor', state: 'CLOSED', failure_count: 0, success_count: 5, last_failure_at: null },
    ],
  },
};

describe('ReliabilityPanel', () => {
  it('renders without crashing when runtime is undefined', () => {
    wrap(undefined);
    expect(screen.getByText('Equipment')).toBeInTheDocument();
  });

  it('shows HEALTHY operational status', () => {
    wrap(healthy);
    // MAIW op status + 4 domain rows all show HEALTHY
    expect(screen.getAllByText('HEALTHY').length).toBeGreaterThanOrEqual(1);
  });

  it('shows all four domains', () => {
    wrap(healthy);
    expect(screen.getByText('Equipment')).toBeInTheDocument();
    expect(screen.getByText('Labor')).toBeInTheDocument();
    expect(screen.getByText('Wave')).toBeInTheDocument();
    expect(screen.getByText('Inventory')).toBeInTheDocument();
  });

  it('shows domain health values', () => {
    wrap(healthy);
    const healthyLabels = screen.getAllByText('HEALTHY');
    // MAIW op status + 4 domains = at least 5 HEALTHY labels
    expect(healthyLabels.length).toBeGreaterThanOrEqual(4);
  });

  it('shows CIRCUIT OPEN for tripped labor domain', () => {
    const degraded: RuntimeStatus = {
      ...healthy,
      maiw_operational_status: 'DEGRADED',
      domain_health: {
        equipment: 'HEALTHY',
        labor: 'CIRCUIT OPEN',
        wave: 'HEALTHY',
        inventory: 'HEALTHY',
      },
      circuit_states: {
        nim: { state: 'CLOSED', failure_count: 0, success_count: 0, last_failure_at: null },
        domains: [
          { name: 'labor', state: 'OPEN', failure_count: 5, success_count: 0, last_failure_at: null },
        ],
      },
    };
    wrap(degraded);
    expect(screen.getByText('CIRCUIT OPEN')).toBeInTheDocument();
  });

  it('shows circuit trip detail for open domain', () => {
    const degraded: RuntimeStatus = {
      ...healthy,
      domain_health: { equipment: 'HEALTHY', labor: 'CIRCUIT OPEN', wave: 'HEALTHY', inventory: 'HEALTHY' },
      circuit_states: {
        nim: { state: 'CLOSED', failure_count: 0, success_count: 0, last_failure_at: null },
        domains: [
          { name: 'labor', state: 'OPEN', failure_count: 7, success_count: 0, last_failure_at: null },
        ],
      },
    };
    wrap(degraded);
    expect(screen.getByText(/7 failures/i)).toBeInTheDocument();
  });
});
