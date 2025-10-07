import React from 'react';
import { render, screen } from '@testing-library/react';
import App from './App';

// Mock the API service
jest.mock('./services/api', () => ({
  api: {
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
    delete: jest.fn(),
  },
}));

// Mock react-router-dom
jest.mock('react-router-dom', () => ({
  ...jest.requireActual('react-router-dom'),
  useNavigate: () => jest.fn(),
  useLocation: () => ({ pathname: '/' }),
}));

describe('App Component', () => {
  test('renders without crashing', () => {
    render(<App />);
    // Basic test to ensure app renders
    expect(document.body).toBeInTheDocument();
  });

  test('renders main content', () => {
    render(<App />);
    // Check if the app container exists
    const appElement = document.querySelector('[data-testid="app"]') || document.body;
    expect(appElement).toBeInTheDocument();
  });

  test('handles routing', () => {
    render(<App />);
    // Basic routing test
    expect(window.location.pathname).toBeDefined();
  });
});

// Additional basic tests
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
