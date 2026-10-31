# Multi-Agent-Intelligent-Warehouse - React Frontend

A modern React-based web interface for the Multi-Agent-Intelligent-Warehouse, built with Material-UI and TypeScript.

## Overview

- Default route: `/demo` (the MAIW v2 demo shell, including Copilot)
- Backend: the v2 API on port 8001, reached through the dev-server proxy (`src/setupProxy.js`)

## Features

- **Copilot** - ASK / ANALYZE / ACT / OBSERVE_OUTCOME through `POST /api/v1/copilot/turn` in the `/demo` shell
- **Legacy Chat Interface** (`/chat`) - calls `POST /api/v1/chat`, which the v2 API does not mount (works only against the legacy dev server `src/api/app.py`)
- **Dashboard** - Overview of warehouse operations and KPIs
- **Inventory Management** - View and manage inventory items
- **Operations Management** - Task assignment and workforce management
- **Safety & Compliance** - Incident reporting and policy management
- **Analytics** - Data visualization and reporting
- **MCP Testing** - Dynamic tool discovery and execution testing interface

## Technology Stack

- **React 19.2.3** - Modern React with hooks (latest stable with security patches)
- **TypeScript** - Type-safe development
- **Material-UI (MUI)** - Modern component library
- **React Query** - Data fetching and caching
- **React Router** - Client-side routing
- **Recharts** - Data visualization
- **Axios** - HTTP client

## Getting Started

### Prerequisites

- Node.js 20 (`.nvmrc`; minimum 18.17.0) and npm >= 9
- Backend API running on port 8001

### Installation

```bash
cd src/ui/web
npm install
```

### Development

```bash
npm start
```

The app will open at http://localhost:3001, bound to 127.0.0.1 by default
(override with `HOST` / `PORT`; see DEPLOYMENT.md before exposing it).

### Build for Production

```bash
npm run build
```

## API Integration

The frontend connects to the Multi-Agent-Intelligent-Warehouse API running on port 8001. Make sure the backend is running before starting the frontend.
The dev server proxies `/api` to `MAIW_API_PROXY_TARGET` (default `http://localhost:8001`; see `src/setupProxy.js`).

### Environment Variables

Create a `.env` file in the `src/ui/web` directory (`cp .env.example .env`).
`REACT_APP_API_URL` must stay relative so the proxy can forward requests:

```env
REACT_APP_API_URL=/api/v1
PORT=3001
```

Or set the port directly in the start command:
```bash
PORT=3001 npm start
```

## Project Structure

```
src/
├── components/          # Reusable components
│   ├── Layout.tsx      # Main layout with navigation
│   ├── VersionFooter.tsx # Version information footer
│   └── chat/           # Chat interface components
├── pages/              # Page components
│   ├── Dashboard.tsx   # Main dashboard
│   ├── ChatInterfaceNew.tsx # AI chat interface
│   ├── EquipmentNew.tsx # Equipment management
│   ├── Operations.tsx  # Operations management
│   ├── Safety.tsx      # Safety & compliance
│   └── Analytics.tsx   # Analytics dashboard
├── services/           # API services
│   ├── api.ts         # API client and types
│   └── version.ts     # Version API service
├── contexts/          # React contexts
│   └── AuthContext.tsx # Authentication context
├── App.tsx            # Main app component
└── index.tsx          # App entry point
```

## Features Overview

### Chat Interface (legacy)
- Requires the legacy `POST /api/v1/chat` (not mounted by the v2 API); use Copilot in `/demo` instead
- Real-time conversation with AI agents
- Intent classification and routing
- Structured responses with recommendations
- Session management and context

### Dashboard
- System status monitoring
- Key performance indicators
- Low stock alerts
- Recent tasks and incidents

### Equipment Management
- View all equipment assets
- Equipment assignments and tracking
- Maintenance schedule management
- Real-time telemetry monitoring
- Equipment status tracking

### Operations Management
- Task assignment and tracking
- Workforce status monitoring
- Shift management
- Performance metrics

### Safety & Compliance
- Incident reporting
- Safety policy management
- Compliance tracking
- Risk assessment

### Analytics
- Data visualization with charts
- Performance trends
- Key metrics dashboard
- Custom reporting

## Development Notes

- The app uses React Query for efficient data fetching and caching
- Material-UI provides a consistent design system
- TypeScript ensures type safety across the application
- The layout is responsive and works on desktop and mobile devices
- All API calls are centralized in the services layer

## Contributing

1. Follow the existing code style and patterns
2. Add TypeScript types for all new components and functions
3. Use Material-UI components for consistency
4. Test all new features thoroughly
5. Update documentation as needed
