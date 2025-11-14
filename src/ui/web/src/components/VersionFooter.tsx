/**
 * Version Footer Component
 * 
 * Displays version information in the bottom-right corner of the application.
 * Shows version, git SHA, and build time information.
 */

import React, { useState, useEffect } from 'react';
import { 
  Box, 
  Typography, 
  Chip, 
  Tooltip, 
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableRow,
  Paper
} from '@mui/material';
import { 
  Info as InfoIcon,
  Close as CloseIcon 
} from '@mui/icons-material';
import { 
  versionAPI, 
  VersionInfo, 
  DetailedVersionInfo
} from '../services/version';

interface VersionFooterProps {
  /** Whether to show the version footer */
  show?: boolean;
  /** Position of the footer */
  position?: 'bottom-right' | 'bottom-left' | 'top-right' | 'top-left';
  /** Whether to show detailed version info on click */
  showDetails?: boolean;
}

export const VersionFooter: React.FC<VersionFooterProps> = ({
  show = true,
  position = 'bottom-right',
  showDetails = true
}) => {
  const [versionInfo, setVersionInfo] = useState<VersionInfo | null>(null);
  const [detailedInfo, setDetailedInfo] = useState<DetailedVersionInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [detailsOpen, setDetailsOpen] = useState(false);

  useEffect(() => {
    const fetchVersionInfo = async () => {
      try {
        setLoading(true);
        const info = await versionAPI.getVersion();
        setVersionInfo(info);
        setError(null);
      } catch (err) {
        console.error('Failed to fetch version info:', err);
        setError('Failed to load version info');
      } finally {
        setLoading(false);
      }
    };

    fetchVersionInfo();
  }, []);

  const handleDetailsClick = async () => {
    if (!showDetails) return;
    
    try {
      const detailed = await versionAPI.getDetailedVersion();
      setDetailedInfo(detailed);
      setDetailsOpen(true);
    } catch (err) {
      console.error('Failed to fetch detailed version info:', err);
    }
  };

  const getPositionStyles = () => {
    const baseStyles = {
      position: 'fixed' as const,
      zIndex: 1000,
      p: 1,
      backgroundColor: 'rgba(0, 0, 0, 0.8)',
      borderRadius: '4px',
      backdropFilter: 'blur(4px)',
      border: '1px solid rgba(255, 255, 255, 0.1)'
    };

    switch (position) {
      case 'bottom-right':
        return { ...baseStyles, bottom: 0, right: 0, borderRadius: '4px 0 0 0' };
      case 'bottom-left':
        return { ...baseStyles, bottom: 0, left: 0, borderRadius: '0 4px 0 0' };
      case 'top-right':
        return { ...baseStyles, top: 0, right: 0, borderRadius: '0 0 0 4px' };
      case 'top-left':
        return { ...baseStyles, top: 0, left: 0, borderRadius: '0 0 4px 0' };
      default:
        return { ...baseStyles, bottom: 0, right: 0, borderRadius: '4px 0 0 0' };
    }
  };

  if (!show || loading) {
    return null;
  }

  if (error || !versionInfo) {
    return (
      <Box sx={getPositionStyles()}>
        <Typography variant="caption" sx={{ color: '#ff6b6b', fontSize: '10px' }}>
          Version: Error
        </Typography>
      </Box>
    );
  }

  return (
    <>
      <Box sx={getPositionStyles()}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Typography variant="caption" sx={{ color: '#ffffff', fontSize: '10px' }}>
            v{versionInfo.version}
          </Typography>
          
          <Tooltip title={`Git SHA: ${versionInfo.git_sha}`}>
            <Chip 
              label={versionInfo.git_sha} 
              size="small" 
              sx={{ 
                backgroundColor: '#333', 
                color: '#fff', 
                fontSize: '10px',
                height: '16px',
                '& .MuiChip-label': {
                  px: 0.5
                }
              }} 
            />
          </Tooltip>

          {showDetails && (
            <Tooltip title="View detailed version info">
              <IconButton
                size="small"
                onClick={handleDetailsClick}
                sx={{ 
                  color: '#ffffff', 
                  p: 0.25,
                  '&:hover': {
                    backgroundColor: 'rgba(255, 255, 255, 0.1)'
                  }
                }}
              >
                <InfoIcon sx={{ fontSize: '12px' }} />
              </IconButton>
            </Tooltip>
          )}
        </Box>
      </Box>

      {/* Detailed Version Dialog */}
      <Dialog 
        open={detailsOpen} 
        onClose={() => setDetailsOpen(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Typography variant="h6">Version Information</Typography>
            <IconButton onClick={() => setDetailsOpen(false)} size="small">
              <CloseIcon />
            </IconButton>
          </Box>
        </DialogTitle>
        
        <DialogContent>
          {detailedInfo && (
            <TableContainer component={Paper} variant="outlined">
              <Table size="small">
                <TableBody>
                  <TableRow>
                    <TableCell><strong>Version</strong></TableCell>
                    <TableCell>{detailedInfo.version}</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell><strong>Git SHA</strong></TableCell>
                    <TableCell>{detailedInfo.git_sha}</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell><strong>Git Branch</strong></TableCell>
                    <TableCell>{detailedInfo.git_branch}</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell><strong>Build Time</strong></TableCell>
                    <TableCell>{new Date(detailedInfo.build_time).toLocaleString()}</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell><strong>Commit Count</strong></TableCell>
                    <TableCell>{detailedInfo.commit_count}</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell><strong>Environment</strong></TableCell>
                    <TableCell>
                      <Chip 
                        label={detailedInfo.environment} 
                        size="small"
                        color={detailedInfo.environment.toLowerCase().includes('prod') ? 'success' : 'default'}
                      />
                    </TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell><strong>Docker Image</strong></TableCell>
                    <TableCell>{detailedInfo.docker_image}</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell><strong>Build Host</strong></TableCell>
                    <TableCell>{detailedInfo.build_host}</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell><strong>Build User</strong></TableCell>
                    <TableCell>{detailedInfo.build_user}</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell><strong>Python Version</strong></TableCell>
                    <TableCell>{detailedInfo.python_version}</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </DialogContent>
        
        <DialogActions>
          <Button onClick={() => setDetailsOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>
    </>
  );
};

export default VersionFooter;
