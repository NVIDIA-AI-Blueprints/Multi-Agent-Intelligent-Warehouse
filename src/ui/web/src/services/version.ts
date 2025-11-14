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
      const response = await api.get('/version');
      return response.data;
    } catch (error) {
      console.error('Failed to fetch version info:', error);
      throw new Error('Failed to fetch version information');
    }
  },

  /**
   * Get detailed version information for debugging
   */
  getDetailedVersion: async (): Promise<DetailedVersionInfo> => {
    try {
      const response = await api.get('/version/detailed');
      return response.data;
    } catch (error) {
      console.error('Failed to fetch detailed version info:', error);
      throw new Error('Failed to fetch detailed version information');
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
