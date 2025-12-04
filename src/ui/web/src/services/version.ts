/**
 * Version Service for Frontend
 * 
 * This service provides version information from the backend API
 * and displays it in the UI components.
 */

import api from './api';

export interface VersionInfo {
  status: string;
  version: string;
  git_sha: string;
  build_time: string;
  environment: string;
}

export interface DetailedVersionInfo {
  status: string;
  version: string;
  git_sha: string;
  git_branch: string;
  build_time: string;
  commit_count: number;
  python_version: string;
  environment: string;
  docker_image: string;
  build_host: string;
  build_user: string;
}

export const versionAPI = {
  /**
   * Get basic version information
   */
  getVersion: async (): Promise<VersionInfo> => {
    try {
      // Use a short timeout for version endpoint (2 seconds) since it's non-critical
      const response = await api.get('/version', { timeout: 2000 });
      return response.data;
    } catch (error: any) {
      // Silently handle version endpoint failures - it's non-critical
      // Don't log errors for version endpoint - it's expected to fail if backend is unavailable or slow
      // Return fallback version info instead of throwing
      // This prevents the UI from breaking if the version endpoint is unavailable
      return {
        status: 'ok',
        version: '0.0.0-dev',
        git_sha: 'unknown',
        build_time: new Date().toISOString(),
        environment: process.env.NODE_ENV || 'development',
      };
    }
  },

  /**
   * Get detailed version information for debugging
   */
  getDetailedVersion: async (): Promise<DetailedVersionInfo> => {
    try {
      const response = await api.get('/version/detailed');
      return response.data;
    } catch (error: any) {
      // Silently handle version endpoint failures - it's non-critical
      // Don't log errors for version endpoint - it's expected to fail if backend is unavailable
      // Return fallback detailed version info instead of throwing
      return {
        status: 'ok',
        version: '0.0.0-dev',
        git_sha: 'unknown',
        git_branch: 'unknown',
        build_time: new Date().toISOString(),
        commit_count: 0,
        python_version: 'unknown',
        environment: process.env.NODE_ENV || 'development',
        docker_image: 'unknown',
        build_host: 'unknown',
        build_user: 'unknown',
      };
    }
  },

  /**
   * Get health status with version info
   */
  getHealth: async (): Promise<any> => {
    try {
      const response = await api.get('/health');
      return response.data;
    } catch (error) {
      console.error('Failed to fetch health info:', error);
      throw new Error('Failed to fetch health information');
    }
  }
};

/**
 * Format version string for display
 */
export const formatVersion = (versionInfo: VersionInfo): string => {
  return `${versionInfo.version} (${versionInfo.git_sha})`;
};

/**
 * Get short version string (without git SHA)
 */
export const getShortVersion = (versionInfo: VersionInfo): string => {
  return versionInfo.version.split('-')[0]; // Remove pre-release info
};

/**
 * Check if running in development environment
 */
export const isDevelopment = (versionInfo: VersionInfo): boolean => {
  return versionInfo.environment.toLowerCase().includes('dev');
};

/**
 * Check if running in production environment
 */
export const isProduction = (versionInfo: VersionInfo): boolean => {
  return versionInfo.environment.toLowerCase().includes('prod');
};
