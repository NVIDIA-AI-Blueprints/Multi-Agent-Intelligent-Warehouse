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

export interface ForecastData {
  sku: string;
  forecast: {
    predictions: number[];
    confidence_intervals: number[][];
    feature_importance: Record<string, number>;
    forecast_date: string;
    horizon_days: number;
  };
}

export interface ForecastSummary {
  forecast_summary: Record<string, {
    average_daily_demand: number;
    min_demand: number;
    max_demand: number;
    trend: string;
    forecast_date: string;
  }>;
  total_skus: number;
  generated_at: string;
}

export interface ReorderRecommendation {
  sku: string;
  current_stock: number;
  recommended_order_quantity: number;
  urgency: 'low' | 'medium' | 'high' | 'critical';
  reason: string;
  estimated_cost: number;
}

export interface ModelPerformance {
  model_name: string;
  accuracy_score: number;
  mae: number;
  rmse: number;
  last_trained: string;
}

// Direct API functions instead of class-based approach
export const forecastingAPI = {
  async getDashboardSummary(): Promise<any> {
    try {
      const url = `${API_BASE_URL}/forecasting/dashboard`;
      console.log('Forecasting API - Making request to:', url);
      const response = await api.get(url);
      console.log('Forecasting API - Response received:', response.status);
      return response.data;
    } catch (error) {
      console.error('Forecasting API - Dashboard call failed:', error);
      throw error;
    }
  },

  async getHealth(): Promise<any> {
    try {
      const response = await api.get(`${API_BASE_URL}/forecasting/health`);
      return response.data;
    } catch (error) {
      throw error;
    }
  },

  async getRealTimeForecast(sku: string, horizonDays: number = 30): Promise<any> {
    try {
      const response = await api.post(`${API_BASE_URL}/forecasting/real-time`, {
        sku,
        horizon_days: horizonDays
      });
      return response.data;
    } catch (error) {
      throw error;
    }
  },

  async getReorderRecommendations(): Promise<any[]> {
    try {
      const response = await api.get(`${API_BASE_URL}/forecasting/reorder-recommendations`);
      // Backend returns {recommendations: [...], ...}, extract the array
      return response.data.recommendations || response.data || [];
    } catch (error) {
      throw error;
    }
  },

  async getModelPerformance(): Promise<any[]> {
    try {
      const response = await api.get(`${API_BASE_URL}/forecasting/model-performance`);
      // Backend returns {model_metrics: [...], ...}, extract the array
      return response.data.model_metrics || response.data || [];
    } catch (error) {
      throw error;
    }
  },

  async getBusinessIntelligenceSummary(): Promise<any> {
    try {
      const response = await api.get(`${API_BASE_URL}/forecasting/business-intelligence`);
      return response.data;
    } catch (error) {
      throw error;
    }
  },

  // Basic forecasting endpoints (from inventory router)
  async getDemandForecast(sku: string, horizonDays: number = 30): Promise<ForecastData> {
    try {
      const response = await api.get(`${API_BASE_URL}/inventory/forecast/demand`, {
        params: { sku, horizon_days: horizonDays }
      });
      return response.data;
    } catch (error) {
      throw error;
    }
  },

  async getForecastSummary(): Promise<ForecastSummary> {
    try {
      const response = await api.get(`${API_BASE_URL}/inventory/forecast/summary`);
      return response.data;
    } catch (error) {
      throw error;
    }
  }
};
