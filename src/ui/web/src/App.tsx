import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { Box } from '@mui/material';
import { AuthProvider } from './contexts/AuthContext';
import Layout from './components/Layout';
import ChatInterfaceNew from './pages/ChatInterfaceNew';
import Equipment from './pages/EquipmentNew';
import Forecasting from './pages/Forecasting';
import Operations from './pages/Operations';
import Safety from './pages/Safety';
import Analytics from './pages/Analytics';
import Documentation from './pages/Documentation';
import DocumentExtraction from './pages/DocumentExtraction';
import MCPIntegrationGuide from './pages/MCPIntegrationGuide';
import APIReference from './pages/APIReference';
import DeploymentGuide from './pages/DeploymentGuide';
import ArchitectureDiagrams from './pages/ArchitectureDiagrams';
import MCPTest from './pages/MCPTest';
import VersionFooter from './components/VersionFooter';
import CommandCenter from './pages/CommandCenter';
import DemoShell from './pages/DemoShell';
import WarehouseStatePage from './pages/WarehouseStatePage';
import DecisionCenter from './pages/DecisionCenter';
import ModelGateway from './pages/ModelGateway';
import CapabilityPlane from './pages/CapabilityPlane';
import ActivityFeed from './pages/ActivityFeed';
import SystemHealth from './pages/SystemHealth';

function App() {
  return (
    <AuthProvider>
      <Box sx={{ display: 'flex', minHeight: '100vh', width: '100%' }}>
        <Routes>
          <Route
            path="/*"
            element={
              <Layout>
                <Routes>
                  <Route path="/command" element={<CommandCenter />} />
                  <Route path="/demo" element={<DemoShell />} />
                  <Route path="/state" element={<WarehouseStatePage />} />
                  <Route path="/decisions" element={<DecisionCenter />} />
                  <Route path="/models" element={<ModelGateway />} />
                  <Route path="/capabilities" element={<CapabilityPlane />} />
                  <Route path="/activity" element={<ActivityFeed />} />
                  <Route path="/health" element={<SystemHealth />} />
                  <Route path="/chat" element={<ChatInterfaceNew />} />
                  <Route path="/equipment" element={<Equipment />} />
                  <Route path="/forecasting" element={<Forecasting />} />
                  <Route path="/operations" element={<Operations />} />
                  <Route path="/safety" element={<Safety />} />
                  <Route path="/documents" element={<DocumentExtraction />} />
                  <Route path="/analytics" element={<Analytics />} />
                  <Route path="/documentation" element={<Documentation />} />
                  <Route path="/documentation/mcp-integration" element={<MCPIntegrationGuide />} />
                  <Route path="/documentation/api-reference" element={<APIReference />} />
                  <Route path="/documentation/deployment" element={<DeploymentGuide />} />
                  <Route path="/documentation/architecture" element={<ArchitectureDiagrams />} />
                  <Route path="/mcp-test" element={<MCPTest />} />
                  <Route path="/" element={<Navigate to="/demo" replace />} />
                  <Route path="/login" element={<Navigate to="/demo" replace />} />
                  <Route path="*" element={<Navigate to="/demo" replace />} />
                </Routes>
              </Layout>
            }
          />
        </Routes>
        <VersionFooter />
      </Box>
    </AuthProvider>
  );
}

export default App;
