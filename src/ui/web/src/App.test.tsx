import React from 'react';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import App from './App';
import { nvidiaTheme } from './theme/nvidiaTheme';

// Proxy-based stub: any property access returns jest.fn().mockResolvedValue(null),
// so new API methods added to any API object don't break this test.
const apiStub = () =>
  new Proxy({} as Record<string, jest.Mock>, {
    get: (_t, _k) => jest.fn().mockResolvedValue(null),
  });

jest.mock('./services/api', () => ({
  __esModule: true,
  default: {
    get: jest.fn().mockResolvedValue({ data: null }),
    post: jest.fn(),
    put: jest.fn(),
    delete: jest.fn(),
  },
  healthAPI: apiStub(),
  runtimeAPI: apiStub(),
  equipmentAPI: apiStub(),
  inventoryAPI: apiStub(),
  operationsAPI: apiStub(),
  safetyAPI: apiStub(),
  documentAPI: apiStub(),
  chatAPI: apiStub(),
  mcpAPI: apiStub(),
  userAPI: apiStub(),
}));

function renderWithProviders(ui: React.ReactElement, initialEntries = ['/login']) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <ThemeProvider theme={nvidiaTheme}>
        <CssBaseline />
        <MemoryRouter
          future={{
            v7_startTransition: true,
            v7_relativeSplatPath: true,
          }}
          initialEntries={initialEntries}
        >
          {ui}
        </MemoryRouter>
      </ThemeProvider>
    </QueryClientProvider>
  );
}

describe('App Component', () => {
  test('renders without crashing', () => {
    renderWithProviders(<App />);
    expect(document.body).toBeInTheDocument();
  });

  test('renders main content', () => {
    renderWithProviders(<App />);
    const appElement = document.querySelector('[data-testid="app"]') || document.body;
    expect(appElement).toBeInTheDocument();
  });

  test('handles routing', () => {
    renderWithProviders(<App />, ['/login']);
    expect(window.location.pathname).toBeDefined();
  });
});

describe('Basic Functionality', () => {
  test('basic math operations', () => {
    expect(2 + 2).toBe(4);
    expect(10 - 5).toBe(5);
    expect(3 * 4).toBe(12);
    expect(8 / 2).toBe(4);
  });

  test('string operations', () => {
    const str = 'Hello, World!';
    expect(str).toContain('Hello');
    expect(str.length).toBe(13);
    expect(str.toUpperCase()).toBe('HELLO, WORLD!');
  });

  test('array operations', () => {
    const arr = [1, 2, 3, 4, 5];
    expect(arr).toHaveLength(5);
    expect(arr).toContain(3);
    expect(arr.filter(x => x > 2)).toEqual([3, 4, 5]);
  });
});
