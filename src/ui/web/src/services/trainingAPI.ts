import axios from 'axios';

// Use relative URL to leverage proxy middleware
const API_BASE_URL = process.env.REACT_APP_API_URL || '/api/v1';

// Create axios instance with proper timeout settings
const api = axios.create({
  timeout: 10000, // 10 second timeout
  headers: {
    'Content-Type': 'application/json',
  },
});

// Interfaces
export interface TrainingRequest {
  training_type: 'basic' | 'advanced';
  force_retrain: boolean;
  schedule_time?: string;
}

export interface TrainingResponse {
  success: boolean;
  message: string;
  training_id?: string;
  estimated_duration?: string;
}

export interface TrainingStatus {
  is_running: boolean;
  progress: number;
  current_step: string;
  start_time?: string;
  end_time?: string;
  status: 'idle' | 'running' | 'completed' | 'failed' | 'stopped';
  error?: string;
  logs: string[];
  estimated_completion?: string;
}

export interface TrainingHistory {
  training_sessions: Array<{
    id: string;
    type: string;
    start_time: string;
    end_time: string;
    status: string;
    duration_minutes: number;
    models_trained: number;
    accuracy_improvement: number;
  }>;
}

export interface TrainingLogs {
  logs: string[];
  total_lines: number;
}

// Training API functions
export const trainingAPI = {
  async startTraining(request: TrainingRequest): Promise<TrainingResponse> {
    try {
      const response = await api.post(`${API_BASE_URL}/training/start`, request);
      return response.data;
    } catch (error) {
      console.error('Error starting training:', error);
      throw error;
    }
  },

  async getTrainingStatus(): Promise<TrainingStatus> {
    try {
      const response = await api.get(`${API_BASE_URL}/training/status`);
      return response.data;
    } catch (error) {
      console.error('Error getting training status:', error);
      throw error;
    }
  },

  async stopTraining(): Promise<{ success: boolean; message: string }> {
    try {
      const response = await api.post(`${API_BASE_URL}/training/stop`);
      return response.data;
    } catch (error) {
      console.error('Error stopping training:', error);
      throw error;
    }
  },

  async getTrainingHistory(): Promise<TrainingHistory> {
    try {
      const response = await api.get(`${API_BASE_URL}/training/history`);
      return response.data;
    } catch (error) {
      console.error('Error getting training history:', error);
      throw error;
    }
  },

  async scheduleTraining(request: TrainingRequest): Promise<{ success: boolean; message: string; scheduled_time: string }> {
    try {
      const response = await api.post(`${API_BASE_URL}/training/schedule`, request);
      return response.data;
    } catch (error) {
      console.error('Error scheduling training:', error);
      throw error;
    }
  },

  async getTrainingLogs(): Promise<TrainingLogs> {
    try {
      const response = await api.get(`${API_BASE_URL}/training/logs`);
      return response.data;
    } catch (error) {
      console.error('Error getting training logs:', error);
      throw error;
    }
  }
};
