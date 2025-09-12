import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { Box } from '@mui/material';
import { AuthProvider } from './contexts/AuthContext';
import ProtectedRoute from './components/ProtectedRoute';
import Layout from './components/Layout';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import ChatInterface from './pages/ChatInterface';
import ChatInterfaceNew from './pages/ChatInterfaceNew';
import Equipment from './pages/EquipmentNew';
import Operations from './pages/Operations';
import Safety from './pages/Safety';
import Analytics from './pages/Analytics';
import VersionFooter from './components/VersionFooter';

function App() {
  return (
    <AuthProvider>
      <Box sx={{ display: 'flex', minHeight: '100vh' }}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            path="/*"
            element={
              <ProtectedRoute>
                <Layout>
                  <Routes>
                    <Route path="/" element={<Dashboard />} />
                    <Route path="/chat" element={<ChatInterfaceNew />} />
                    <Route path="/equipment" element={<Equipment />} />
                    <Route path="/operations" element={<Operations />} />
                    <Route path="/safety" element={<Safety />} />
                    <Route path="/analytics" element={<Analytics />} />
                    <Route path="*" element={<Navigate to="/" replace />} />
                  </Routes>
                </Layout>
              </ProtectedRoute>
            }
          />
        </Routes>
        <VersionFooter />
      </Box>
    </AuthProvider>
  );
}

export default App;
