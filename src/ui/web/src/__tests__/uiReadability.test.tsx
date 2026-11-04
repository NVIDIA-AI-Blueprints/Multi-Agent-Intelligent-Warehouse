/**
 * Readable text and scrollable pages across the whole UI.
 *
 * - The theme sets the root font size to 125%, and every UI font size is in
 *   rem, so text scales together; no rem size is below 0.6rem (12px at 125%)
 *   and none is a fixed px value that would ignore the root size.
 * - The shell's page area scrolls (overflow: auto). It used overflow: hidden,
 *   so pages without their own scroll container (Deployment, Models,
 *   Capabilities, System Health) could not show anything below the window.
 * - In MUI sx, `width: 1` is 100%, not 1px: as a divider it pushed the Activity
 *   filters off-screen.
 */

import fs from 'fs';
import path from 'path';
import React from 'react';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import { ThemeProvider } from '@mui/material/styles';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { nvidiaTheme } from '../theme/nvidiaTheme';
import Layout from '../components/Layout';

jest.mock('../hooks/useDemoStatus', () => ({
  useDemoStatus: () => ({ status: null, isLoading: false, isDemoMode: true, refetch: jest.fn() }),
}));

const SRC = path.resolve(__dirname, '..');

function sourceFiles(dir: string): string[] {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) {
      return e.name === '__tests__' ? [] : sourceFiles(p);
    }
    return /\.(ts|tsx)$/.test(e.name) ? [p] : [];
  });
}

function offending(pattern: RegExp): string[] {
  return sourceFiles(SRC).flatMap((file) =>
    fs.readFileSync(file, 'utf8').split('\n').flatMap((line, i) =>
      pattern.test(line) ? [`${path.relative(SRC, file)}:${i + 1}: ${line.trim()}`] : [],
    ),
  );
}

describe('font sizes', () => {
  it('sets the root font size to 125%', () => {
    const overrides = (nvidiaTheme.components?.MuiCssBaseline?.styleOverrides ?? {}) as Record<string, any>;
    expect(overrides.html?.fontSize).toBe('125%');
  });

  it('has no rem font size below 0.6rem', () => {
    expect(offending(/['"]0\.[0-5]\d*rem['"]/)).toEqual([]);
  });

  it('has no px font sizes', () => {
    expect(offending(/fontSize: *['"]\d+(\.\d+)?px['"]/)).toEqual([]);
  });
});

describe('scrolling', () => {
  it('lets the page area scroll', () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MemoryRouter>
        <QueryClientProvider client={qc}>
          <ThemeProvider theme={nvidiaTheme}>
            <Layout><div>page</div></Layout>
          </ThemeProvider>
        </QueryClientProvider>
      </MemoryRouter>,
    );
    const content = screen.getByTestId('layout-content');
    expect(content).toHaveStyle({ overflow: 'auto', minHeight: '0' });
    expect(content).toHaveTextContent('page');
  });

  it('has no sx `width: 1` (100%) used as a divider', () => {
    expect(offending(/sx=\{\{ *width: 1, *height:/)).toEqual([]);
  });
});
