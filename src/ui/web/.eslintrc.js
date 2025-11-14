module.exports = {
  extends: [
    'react-app',
    'react-app/jest'
  ],
  rules: {
    // Basic rules for code quality
    'no-unused-vars': 'warn',
    'no-console': 'warn',
    'no-debugger': 'warn',
    'no-alert': 'warn',
    
    // React specific rules
    'react/prop-types': 'off', // We use TypeScript
    'react/react-in-jsx-scope': 'off', // Not needed in React 17+
    'react-hooks/exhaustive-deps': 'warn',
    
    // TypeScript rules
    '@typescript-eslint/no-unused-vars': 'warn',
    '@typescript-eslint/no-explicit-any': 'warn',
    '@typescript-eslint/explicit-function-return-type': 'off',
    '@typescript-eslint/explicit-module-boundary-types': 'off',
    
    // Import rules
    'import/order': 'warn',
    'import/no-unresolved': 'off', // TypeScript handles this
    
    // General code style
    'prefer-const': 'warn',
    'no-var': 'error',
    'eqeqeq': 'warn',
    'curly': 'warn',
  },
  settings: {
    react: {
      version: 'detect',
    },
  },
  env: {
    browser: true,
    es2021: true,
    node: true,
    jest: true,
  },
  parserOptions: {
    ecmaFeatures: {
      jsx: true,
    },
    ecmaVersion: 12,
    sourceType: 'module',
  },
  ignorePatterns: [
    'build/',
    'dist/',
    'node_modules/',
    '*.config.js',
    'public/',
  ],
};
