# Warehouse Operational Assistant - React Frontend

A modern React-based web interface for the Warehouse Operational Assistant, built with Material-UI and TypeScript.

##  Current Status - All Issues Fixed + MCP Integration Complete

**Recent Fixes Applied:**
-  **MessageBubble Component**: Fixed syntax error (missing opening brace)
-  **ChatInterfaceNew Component**: Fixed "event is undefined" runtime error
-  **Equipment Assignments**: Backend endpoint working (no more 404 errors)
-  **Build Process**: React app compiles successfully without errors
-  **ESLint**: All warnings cleaned up (0 warnings)
-  **MCP Integration**: Complete MCP framework integration with dynamic tool discovery
-  **MCP Testing Navigation**: Added MCP Testing link to left sidebar navigation
-  **API Port Configuration**: Updated to use port 8002 for backend communication

**System Status**: Fully functional with MCP integration ready for production use.

## Features

- **Real-time Chat Interface** - Interactive chat with AI agents
- **Dashboard** - Overview of warehouse operations and KPIs
- **Inventory Management** - View and manage inventory items
- **Operations Management** - Task assignment and workforce management
- **Safety & Compliance** - Incident reporting and policy management
- **Analytics** - Data visualization and reporting
- **MCP Testing** - Dynamic tool discovery and execution testing interface

## Technology Stack

- **React 18** - Modern React with hooks
- **TypeScript** - Type-safe development
- **Material-UI (MUI)** - Modern component library
- **React Query** - Data fetching and caching
- **React Router** - Client-side routing
- **Recharts** - Data visualization
- **Axios** - HTTP client

## Getting Started

### Prerequisites

- Node.js 16+ and npm
- Backend API running on port 8001

### Installation

```bash
cd ui/web
npm install
```

### Development

```bash
npm start
```

The app will open at http://localhost:3001

### Build for Production

```bash
npm run build
```

## API Integration

The frontend connects to the Warehouse Operational Assistant API running on port 8001. Make sure the backend is running before starting the frontend.

### Environment Variables

Create a `.env` file in the `ui/web` directory:

```env
REACT_APP_API_URL=http://localhost:8001
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

### Chat Interface
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
