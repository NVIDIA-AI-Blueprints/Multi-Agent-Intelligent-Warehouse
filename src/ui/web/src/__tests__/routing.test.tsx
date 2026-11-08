/**
 * Route table and router behaviour on React Router v7 (#264).
 *
 * Every page module is replaced by a stub that renders its name, and Layout by
 * a wrapper that shows the current location, so these tests exercise only
 * App's route table and the router:
 *   1. every deep link renders its page;
 *   2. `/`, `/login` and unknown paths redirect to `/demo` (replace, no extra
 *      history entry);
 *   3. query strings survive a deep link (the MCP test panel reads `?tab=`);
 *   4. useNavigate from inside the layout moves between pages;
 *   5. navigate() refuses backslash and protocol-relative targets instead of
 *      leaving the app (GHSA-wrjc-x8rr-h8h6, fixed in react-router 7.18.0).
 */
import React from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { BrowserRouter, MemoryRouter, useLocation, useNavigate } from 'react-router';
import App from '../App';

jest.mock('../components/Layout', () => {
  const { useLocation, useNavigate, useNavigationType } = jest.requireActual('react-router');
  function MockLayout({ children }: { children: React.ReactNode }) {
    const location = useLocation();
    const navigate = useNavigate();
    const navigationType = useNavigationType();
    return (
      <div>
        <span data-testid="location">{location.pathname + location.search}</span>
        <span data-testid="navigation-type">{navigationType}</span>
        <button onClick={() => navigate('/models/lab')}>to-lab</button>
        {children}
      </div>
    );
  }
  return { __esModule: true, default: MockLayout };
});

jest.mock('../components/VersionFooter', () => ({ __esModule: true, default: () => null }));

const stub = (name: string) => ({
  __esModule: true,
  default: () => <div data-testid="page">{name}</div>,
});
jest.mock('../pages/CommandCenter', () => stub('CommandCenter'));
jest.mock('../pages/DemoShell', () => stub('DemoShell'));
jest.mock('../pages/WarehouseStatePage', () => stub('WarehouseStatePage'));
jest.mock('../pages/DecisionCenter', () => stub('DecisionCenter'));
jest.mock('../pages/ModelGateway', () => stub('ModelGateway'));
jest.mock('../pages/ModelGatewayLab', () => stub('ModelGatewayLab'));
jest.mock('../components/world/WorldShell', () => stub('WorldShell'));
jest.mock('../pages/CapabilityPlane', () => stub('CapabilityPlane'));
jest.mock('../pages/ActivityFeed', () => stub('ActivityFeed'));
jest.mock('../pages/SystemHealth', () => stub('SystemHealth'));
jest.mock('../pages/DeploymentSecurity', () => stub('DeploymentSecurity'));
jest.mock('../pages/ChatInterfaceNew', () => stub('ChatInterfaceNew'));
jest.mock('../pages/EquipmentNew', () => stub('EquipmentNew'));
jest.mock('../pages/Forecasting', () => stub('Forecasting'));
jest.mock('../pages/Operations', () => stub('Operations'));
jest.mock('../pages/Safety', () => stub('Safety'));
jest.mock('../pages/DocumentExtraction', () => stub('DocumentExtraction'));
jest.mock('../pages/Analytics', () => stub('Analytics'));
jest.mock('../pages/Documentation', () => stub('Documentation'));
jest.mock('../pages/MCPIntegrationGuide', () => stub('MCPIntegrationGuide'));
jest.mock('../pages/APIReference', () => stub('APIReference'));
jest.mock('../pages/DeploymentGuide', () => stub('DeploymentGuide'));
jest.mock('../pages/ArchitectureDiagrams', () => stub('ArchitectureDiagrams'));
jest.mock('../pages/MCPTest', () => stub('MCPTest'));

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

const page = () => screen.getByTestId('page').textContent;
const location = () => screen.getByTestId('location').textContent;

describe('route table deep links', () => {
  test.each([
    ['/command', 'CommandCenter'],
    ['/demo', 'DemoShell'],
    ['/state', 'WarehouseStatePage'],
    ['/decisions', 'DecisionCenter'],
    ['/models', 'ModelGateway'],
    ['/models/lab', 'ModelGatewayLab'],
    ['/world', 'WorldShell'],
    ['/capabilities', 'CapabilityPlane'],
    ['/activity', 'ActivityFeed'],
    ['/health', 'SystemHealth'],
    ['/deployment', 'DeploymentSecurity'],
    ['/chat', 'ChatInterfaceNew'],
    ['/equipment', 'EquipmentNew'],
    ['/forecasting', 'Forecasting'],
    ['/operations', 'Operations'],
    ['/safety', 'Safety'],
    ['/documents', 'DocumentExtraction'],
    ['/analytics', 'Analytics'],
    ['/documentation', 'Documentation'],
    ['/documentation/mcp-integration', 'MCPIntegrationGuide'],
    ['/documentation/api-reference', 'APIReference'],
    ['/documentation/deployment', 'DeploymentGuide'],
    ['/documentation/architecture', 'ArchitectureDiagrams'],
    ['/mcp-test', 'MCPTest'],
  ])('%s renders %s', (path, name) => {
    renderAt(path);
    expect(page()).toBe(name);
    expect(location()).toBe(path);
  });

  test('a trailing slash still matches its route', () => {
    renderAt('/documentation/architecture/');
    expect(page()).toBe('ArchitectureDiagrams');
  });
});

describe('redirects', () => {
  test.each(['/', '/login', '/no-such-page', '/documentation/no-such-guide', '/models/lab/extra'])(
    '%s redirects to /demo with replace',
    (path) => {
      renderAt(path);
      expect(page()).toBe('DemoShell');
      expect(location()).toBe('/demo');
      expect(screen.getByTestId('navigation-type').textContent).toBe('REPLACE');
    },
  );
});

describe('query strings and in-app navigation', () => {
  test('a deep link keeps its query string', () => {
    renderAt('/mcp-test?tab=2&message=hello');
    expect(page()).toBe('MCPTest');
    expect(location()).toBe('/mcp-test?tab=2&message=hello');
  });

  test('useNavigate inside the layout moves to another page', () => {
    renderAt('/models');
    expect(page()).toBe('ModelGateway');
    act(() => {
      fireEvent.click(screen.getByText('to-lab'));
    });
    expect(page()).toBe('ModelGatewayLab');
    expect(location()).toBe('/models/lab');
  });
});

describe('navigate() does not leave the app (GHSA-wrjc-x8rr-h8h6)', () => {
  function Probe({ to, onError }: { to: string; onError: (e: unknown) => void }) {
    const navigate = useNavigate();
    const loc = useLocation();
    return (
      <>
        <span data-testid="probe-location">{loc.pathname}</span>
        <button
          onClick={() => {
            try {
              navigate(to);
            } catch (e) {
              onError(e);
            }
          }}
        >
          go
        </button>
      </>
    );
  }

  test.each(['/\\evil.example', '\\\\evil.example', '\\/evil.example', '/\\/evil.example', '//evil.example'])(
    'navigate(%j) is refused and the browser stays on the app origin',
    (target) => {
      window.history.replaceState(null, '', '/demo');
      const onError = jest.fn();
      render(
        <BrowserRouter>
          <Probe to={target} onError={onError} />
        </BrowserRouter>,
      );
      act(() => {
        fireEvent.click(screen.getByText('go'));
      });
      expect(onError).toHaveBeenCalledTimes(1);
      expect(String(onError.mock.calls[0][0])).toMatch(/External navigation is not allowed/);
      expect(window.location.origin).toBe('http://localhost');
      expect(window.location.pathname).toBe('/demo');
      expect(screen.getByTestId('probe-location').textContent).toBe('/demo');
    },
  );
});
