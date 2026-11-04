// SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
// http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import { createTheme } from '@mui/material/styles';

/**
 * NVIDIA Professional Dark Theme
 * Formal, sleek, and professional design system matching NVIDIA's brand guidelines
 */
export const nvidiaTheme = createTheme({
  palette: {
    mode: 'dark',
    primary: {
      main: '#76B900', // NVIDIA Green - Primary brand color
      light: '#8FD600', // Lighter green for hover states
      dark: '#5A8A00', // Darker green for active states
      contrastText: '#000000', // Black text on green for maximum contrast
    },
    secondary: {
      main: '#00D9FF', // NVIDIA Cyan - Secondary accent
      light: '#33E1FF',
      dark: '#00A8CC',
      contrastText: '#000000',
    },
    background: {
      default: '#0A0E13', // Very dark background (almost black)
      paper: '#151920', // Card/surface background
    },
    text: {
      primary: '#E6EDF3', // Primary text - high contrast
      secondary: '#8B949E', // Secondary text - medium contrast
      disabled: '#484F58', // Disabled text
    },
    divider: '#21262D', // Subtle dividers
    error: {
      main: '#F85149',
      light: '#FF6B6B',
      dark: '#D32F2F',
    },
    warning: {
      main: '#D29922',
      light: '#E3A341',
      dark: '#B8860B',
    },
    info: {
      main: '#58A6FF',
      light: '#79C0FF',
      dark: '#1F6FEB',
    },
    success: {
      main: '#3FB950', // Success green (different from primary)
      light: '#56D364',
      dark: '#2EA043',
    },
    grey: {
      50: '#F0F6FC',
      100: '#C9D1D9',
      200: '#B1BAC4',
      300: '#8B949E',
      400: '#6E7681',
      500: '#484F58',
      600: '#30363D',
      700: '#21262D',
      800: '#161B22',
      900: '#0D1117',
    },
  },
  typography: {
    fontFamily: '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", "Roboto", "Helvetica Neue", "Arial", sans-serif',
    h1: {
      fontWeight: 700,
      fontSize: '2.5rem',
      lineHeight: 1.2,
      letterSpacing: '-0.02em',
      color: '#E6EDF3',
    },
    h2: {
      fontWeight: 600,
      fontSize: '2rem',
      lineHeight: 1.3,
      letterSpacing: '-0.01em',
      color: '#E6EDF3',
    },
    h3: {
      fontWeight: 600,
      fontSize: '1.75rem',
      lineHeight: 1.4,
      letterSpacing: '-0.01em',
      color: '#E6EDF3',
    },
    h4: {
      fontWeight: 600,
      fontSize: '1.5rem',
      lineHeight: 1.4,
      color: '#E6EDF3',
    },
    h5: {
      fontWeight: 600,
      fontSize: '1.25rem',
      lineHeight: 1.5,
      color: '#E6EDF3',
    },
    h6: {
      fontWeight: 600,
      fontSize: '1.125rem',
      lineHeight: 1.5,
      color: '#E6EDF3',
    },
    subtitle1: {
      fontSize: '1rem',
      lineHeight: 1.6,
      fontWeight: 500,
      color: '#E6EDF3',
    },
    subtitle2: {
      fontSize: '0.875rem',
      lineHeight: 1.5,
      fontWeight: 500,
      color: '#8B949E',
    },
    body1: {
      fontSize: '0.9375rem',
      lineHeight: 1.6,
      color: '#E6EDF3',
    },
    body2: {
      fontSize: '0.875rem',
      lineHeight: 1.5,
      color: '#8B949E',
    },
    button: {
      fontWeight: 600,
      textTransform: 'none',
      letterSpacing: '0.01em',
      fontSize: '0.9375rem',
    },
    caption: {
      fontSize: '0.75rem',
      lineHeight: 1.4,
      color: '#8B949E',
    },
    overline: {
      fontSize: '0.75rem',
      lineHeight: 1.4,
      fontWeight: 600,
      textTransform: 'uppercase',
      letterSpacing: '0.05em',
      color: '#8B949E',
    },
  },
  shape: {
    borderRadius: 8,
  },
  shadows: [
    'none',
    '0 1px 3px rgba(0, 0, 0, 0.3), 0 1px 2px rgba(0, 0, 0, 0.4)',
    '0 2px 6px rgba(0, 0, 0, 0.3), 0 2px 4px rgba(0, 0, 0, 0.4)',
    '0 4px 12px rgba(0, 0, 0, 0.3), 0 4px 8px rgba(0, 0, 0, 0.4)',
    '0 8px 24px rgba(0, 0, 0, 0.3), 0 8px 16px rgba(0, 0, 0, 0.4)',
    '0 12px 36px rgba(0, 0, 0, 0.3), 0 12px 24px rgba(0, 0, 0, 0.4)',
    '0 16px 48px rgba(0, 0, 0, 0.3), 0 16px 32px rgba(0, 0, 0, 0.4)',
    '0 20px 60px rgba(0, 0, 0, 0.3), 0 20px 40px rgba(0, 0, 0, 0.4)',
    '0 24px 72px rgba(0, 0, 0, 0.3), 0 24px 48px rgba(0, 0, 0, 0.4)',
    '0 28px 84px rgba(0, 0, 0, 0.3), 0 28px 56px rgba(0, 0, 0, 0.4)',
    '0 32px 96px rgba(0, 0, 0, 0.3), 0 32px 64px rgba(0, 0, 0, 0.4)',
    '0 36px 108px rgba(0, 0, 0, 0.3), 0 36px 72px rgba(0, 0, 0, 0.4)',
    '0 40px 120px rgba(0, 0, 0, 0.3), 0 40px 80px rgba(0, 0, 0, 0.4)',
    '0 44px 132px rgba(0, 0, 0, 0.3), 0 44px 88px rgba(0, 0, 0, 0.4)',
    '0 48px 144px rgba(0, 0, 0, 0.3), 0 48px 96px rgba(0, 0, 0, 0.4)',
    '0 52px 156px rgba(0, 0, 0, 0.3), 0 52px 104px rgba(0, 0, 0, 0.4)',
    '0 56px 168px rgba(0, 0, 0, 0.3), 0 56px 112px rgba(0, 0, 0, 0.4)',
    '0 60px 180px rgba(0, 0, 0, 0.3), 0 60px 120px rgba(0, 0, 0, 0.4)',
    '0 64px 192px rgba(0, 0, 0, 0.3), 0 64px 128px rgba(0, 0, 0, 0.4)',
    '0 68px 204px rgba(0, 0, 0, 0.3), 0 68px 136px rgba(0, 0, 0, 0.4)',
    '0 72px 216px rgba(0, 0, 0, 0.3), 0 72px 144px rgba(0, 0, 0, 0.4)',
    '0 76px 228px rgba(0, 0, 0, 0.3), 0 76px 152px rgba(0, 0, 0, 0.4)',
    '0 80px 240px rgba(0, 0, 0, 0.3), 0 80px 160px rgba(0, 0, 0, 0.4)',
    '0 84px 252px rgba(0, 0, 0, 0.3), 0 84px 168px rgba(0, 0, 0, 0.4)',
    '0 88px 264px rgba(0, 0, 0, 0.3), 0 88px 176px rgba(0, 0, 0, 0.4)',
  ] as any,
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        // UI text is sized in rem; 125% (20px with the browser default) scales
        // all of it. The smallest labels are 0.6rem (12px).
        html: {
          fontSize: '125%',
        },
        body: {
          backgroundColor: '#0A0E13',
          color: '#E6EDF3',
          fontFamily: '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", "Roboto", "Helvetica Neue", "Arial", sans-serif',
          WebkitFontSmoothing: 'antialiased',
          MozOsxFontSmoothing: 'grayscale',
        },
        '*': {
          scrollbarWidth: 'thin',
          scrollbarColor: '#30363D #0A0E13',
        },
        '*::-webkit-scrollbar': {
          width: '8px',
          height: '8px',
        },
        '*::-webkit-scrollbar-track': {
          background: '#0A0E13',
        },
        '*::-webkit-scrollbar-thumb': {
          background: '#30363D',
          borderRadius: '4px',
          '&:hover': {
            background: '#484F58',
          },
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          backgroundColor: '#151920',
          border: '1px solid #21262D',
          borderRadius: 12,
          boxShadow: '0 2px 8px rgba(0, 0, 0, 0.3), 0 1px 4px rgba(0, 0, 0, 0.4)',
          transition: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
          '&:hover': {
            borderColor: '#30363D',
            boxShadow: '0 4px 16px rgba(0, 0, 0, 0.4), 0 2px 8px rgba(0, 0, 0, 0.5)',
            transform: 'translateY(-2px)',
          },
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: 8,
          padding: '10px 20px',
          fontWeight: 600,
          textTransform: 'none',
          fontSize: '0.9375rem',
          transition: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
          '&.MuiButton-containedPrimary': {
            backgroundColor: '#76B900',
            color: '#000000',
            boxShadow: '0 2px 8px rgba(118, 185, 0, 0.3)',
            '&:hover': {
              backgroundColor: '#8FD600',
              boxShadow: '0 4px 12px rgba(118, 185, 0, 0.4)',
              transform: 'translateY(-1px)',
            },
            '&:active': {
              transform: 'translateY(0)',
              boxShadow: '0 2px 4px rgba(118, 185, 0, 0.3)',
            },
            '&:disabled': {
              backgroundColor: '#30363D',
              color: '#484F58',
            },
          },
          '&.MuiButton-outlined': {
            borderColor: '#30363D',
            color: '#E6EDF3',
            '&:hover': {
              borderColor: '#76B900',
              backgroundColor: 'rgba(118, 185, 0, 0.1)',
            },
          },
          '&.MuiButton-text': {
            color: '#E6EDF3',
            '&:hover': {
              backgroundColor: 'rgba(118, 185, 0, 0.1)',
            },
          },
        },
      },
    },
    MuiAppBar: {
      styleOverrides: {
        root: {
          backgroundColor: '#151920',
          borderBottom: '1px solid #21262D',
          boxShadow: '0 1px 3px rgba(0, 0, 0, 0.3)',
          backdropFilter: 'blur(10px)',
        },
      },
    },
    MuiDrawer: {
      styleOverrides: {
        paper: {
          backgroundColor: '#151920',
          borderRight: '1px solid #21262D',
          boxShadow: '2px 0 8px rgba(0, 0, 0, 0.3)',
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: {
          backgroundColor: '#1C2128',
          border: '1px solid #30363D',
          color: '#E6EDF3',
          fontWeight: 500,
          fontSize: '0.8125rem',
          height: '28px',
          '&.MuiChip-colorPrimary': {
            backgroundColor: 'rgba(118, 185, 0, 0.15)',
            borderColor: '#76B900',
            color: '#76B900',
          },
          '&.MuiChip-colorSuccess': {
            backgroundColor: 'rgba(63, 185, 80, 0.15)',
            borderColor: '#3FB950',
            color: '#3FB950',
          },
          '&.MuiChip-colorError': {
            backgroundColor: 'rgba(248, 81, 73, 0.15)',
            borderColor: '#F85149',
            color: '#F85149',
          },
        },
      },
    },
    MuiTextField: {
      styleOverrides: {
        root: {
          '& .MuiOutlinedInput-root': {
            backgroundColor: '#0A0E13',
            borderRadius: 8,
            transition: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
            '& fieldset': {
              borderColor: '#30363D',
              borderWidth: '1px',
            },
            '&:hover fieldset': {
              borderColor: '#484F58',
            },
            '&.Mui-focused fieldset': {
              borderColor: '#76B900',
              borderWidth: '2px',
            },
            '&.Mui-focused': {
              backgroundColor: '#0D1117',
            },
            '& input': {
              color: '#E6EDF3',
              '&::placeholder': {
                color: '#6E7681',
                opacity: 1,
              },
            },
          },
          '& .MuiInputLabel-root': {
            color: '#8B949E',
            '&.Mui-focused': {
              color: '#76B900',
            },
          },
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundColor: '#151920',
          border: '1px solid #21262D',
          borderRadius: 12,
        },
        elevation1: {
          boxShadow: '0 2px 8px rgba(0, 0, 0, 0.3), 0 1px 4px rgba(0, 0, 0, 0.4)',
        },
        elevation2: {
          boxShadow: '0 4px 16px rgba(0, 0, 0, 0.3), 0 2px 8px rgba(0, 0, 0, 0.4)',
        },
        elevation3: {
          boxShadow: '0 8px 24px rgba(0, 0, 0, 0.3), 0 4px 12px rgba(0, 0, 0, 0.4)',
        },
      },
    },
    MuiDialog: {
      styleOverrides: {
        paper: {
          backgroundColor: '#1C2128', // Elevated surface color
          border: '1px solid #30363D',
          borderRadius: 16,
          boxShadow: '0 8px 32px rgba(0, 0, 0, 0.5)',
        },
      },
    },
    MuiDialogTitle: {
      styleOverrides: {
        root: {
          borderBottom: '1px solid #21262D',
          padding: '20px 24px',
          color: '#E6EDF3',
          fontWeight: 600,
        },
      },
    },
    MuiDialogContent: {
      styleOverrides: {
        root: {
          padding: '24px',
          color: '#E6EDF3',
        },
      },
    },
    MuiTabs: {
      styleOverrides: {
        root: {
          borderBottom: '1px solid #21262D',
        },
        indicator: {
          backgroundColor: '#76B900',
          height: '3px',
        },
      },
    },
    MuiTab: {
      styleOverrides: {
        root: {
          color: '#8B949E',
          fontWeight: 500,
          textTransform: 'none',
          fontSize: '0.9375rem',
          minHeight: '48px',
          '&.Mui-selected': {
            color: '#76B900',
            fontWeight: 600,
          },
          '&:hover': {
            color: '#E6EDF3',
            backgroundColor: 'rgba(118, 185, 0, 0.05)',
          },
        },
      },
    },
    MuiListItem: {
      styleOverrides: {
        root: {
          borderRadius: 8,
          margin: '2px 8px',
          '&.Mui-selected': {
            backgroundColor: 'rgba(118, 185, 0, 0.15)',
            color: '#76B900',
            '&:hover': {
              backgroundColor: 'rgba(118, 185, 0, 0.2)',
            },
            '& .MuiListItemIcon-root': {
              color: '#76B900',
            },
          },
          '&:hover': {
            backgroundColor: 'rgba(118, 185, 0, 0.08)',
          },
        },
      },
    },
    MuiListItemIcon: {
      styleOverrides: {
        root: {
          color: '#8B949E',
          minWidth: '40px',
        },
      },
    },
    MuiLinearProgress: {
      styleOverrides: {
        root: {
          backgroundColor: '#21262D',
          borderRadius: 4,
          height: 8,
        },
        bar: {
          borderRadius: 4,
          backgroundColor: '#76B900',
        },
      },
    },
    MuiCircularProgress: {
      styleOverrides: {
        root: {
          color: '#76B900',
        },
      },
    },
    MuiAlert: {
      styleOverrides: {
        root: {
          borderRadius: 8,
          border: '1px solid',
        },
        standardSuccess: {
          backgroundColor: 'rgba(63, 185, 80, 0.15)',
          borderColor: '#3FB950',
          color: '#3FB950',
        },
        standardError: {
          backgroundColor: 'rgba(248, 81, 73, 0.15)',
          borderColor: '#F85149',
          color: '#F85149',
        },
        standardWarning: {
          backgroundColor: 'rgba(210, 153, 34, 0.15)',
          borderColor: '#D29922',
          color: '#D29922',
        },
        standardInfo: {
          backgroundColor: 'rgba(88, 166, 255, 0.15)',
          borderColor: '#58A6FF',
          color: '#58A6FF',
        },
      },
    },
    MuiTable: {
      styleOverrides: {
        root: {
          backgroundColor: '#151920',
        },
      },
    },
    MuiTableHead: {
      styleOverrides: {
        root: {
          backgroundColor: '#1C2128',
          '& .MuiTableCell-head': {
            color: '#8B949E',
            fontWeight: 600,
            fontSize: '0.8125rem',
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
            borderBottom: '1px solid #21262D',
          },
        },
      },
    },
    MuiTableCell: {
      styleOverrides: {
        root: {
          borderBottom: '1px solid #21262D',
          color: '#E6EDF3',
        },
      },
    },
    MuiTableRow: {
      styleOverrides: {
        root: {
          '&:hover': {
            backgroundColor: 'rgba(118, 185, 0, 0.05)',
          },
          '&.Mui-selected': {
            backgroundColor: 'rgba(118, 185, 0, 0.1)',
            '&:hover': {
              backgroundColor: 'rgba(118, 185, 0, 0.15)',
            },
          },
        },
      },
    },
    MuiTooltip: {
      styleOverrides: {
        tooltip: {
          backgroundColor: '#1C2128',
          color: '#E6EDF3',
          border: '1px solid #30363D',
          borderRadius: 8,
          fontSize: '0.8125rem',
          padding: '8px 12px',
          boxShadow: '0 4px 12px rgba(0, 0, 0, 0.4)',
        },
        arrow: {
          color: '#1C2128',
          '&::before': {
            border: '1px solid #30363D',
          },
        },
      },
    },
    MuiMenu: {
      styleOverrides: {
        paper: {
          backgroundColor: '#1C2128',
          border: '1px solid #30363D',
          borderRadius: 8,
          boxShadow: '0 8px 24px rgba(0, 0, 0, 0.4)',
          marginTop: '4px',
        },
      },
    },
    MuiMenuItem: {
      styleOverrides: {
        root: {
          color: '#E6EDF3',
          fontSize: '0.9375rem',
          padding: '10px 16px',
          '&:hover': {
            backgroundColor: 'rgba(118, 185, 0, 0.1)',
          },
          '&.Mui-selected': {
            backgroundColor: 'rgba(118, 185, 0, 0.15)',
            color: '#76B900',
            '&:hover': {
              backgroundColor: 'rgba(118, 185, 0, 0.2)',
            },
          },
        },
      },
    },
    MuiIconButton: {
      styleOverrides: {
        root: {
          color: '#8B949E',
          transition: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
          '&:hover': {
            backgroundColor: 'rgba(118, 185, 0, 0.1)',
            color: '#76B900',
          },
        },
      },
    },
    MuiAvatar: {
      styleOverrides: {
        root: {
          backgroundColor: '#30363D',
          color: '#E6EDF3',
        },
      },
    },
  },
});

