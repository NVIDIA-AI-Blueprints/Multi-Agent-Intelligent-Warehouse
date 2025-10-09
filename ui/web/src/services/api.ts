import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8002';

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60000, // Increased to 60 seconds for complex reasoning
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor
api.interceptors.request.use(
  (config) => {
    // Add auth token if available
    const token = localStorage.getItem('auth_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Handle unauthorized access
      localStorage.removeItem('auth_token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export interface ChatRequest {
  message: string;
  session_id?: string;
  context?: Record<string, any>;
}

export interface ChatResponse {
  reply: string;
  route: string;
  intent: string;
  session_id: string;
  context?: Record<string, any>;
  structured_data?: Record<string, any>;
  recommendations?: string[];
  confidence?: number;
}

export interface EquipmentAsset {
  asset_id: string;
  type: string;
  model?: string;
  zone?: string;
  status: string;
  owner_user?: string;
  next_pm_due?: string;
  last_maintenance?: string;
  created_at: string;
  updated_at: string;
  metadata: Record<string, any>;
}

// Keep old interface for inventory items
export interface InventoryItem {
  sku: string;
  name: string;
  quantity: number;
  location: string;
  reorder_point: number;
  updated_at: string;
}

export interface Task {
  id: number;
  kind: string;
  status: string;
  assignee: string;
  payload: Record<string, any>;
  created_at: string;
  updated_at: string;
}

export interface SafetyIncident {
  id: number;
  severity: string;
  description: string;
  reported_by: string;
  occurred_at: string;
}

export const mcpAPI = {
  getStatus: async (): Promise<any> => {
    const response = await api.get('/api/v1/mcp/status');
    return response.data;
  },
  
  getTools: async (): Promise<any> => {
    const response = await api.get('/api/v1/mcp/tools');
    return response.data;
  },
  
  searchTools: async (query: string): Promise<any> => {
    const response = await api.post('/api/v1/mcp/tools/search', { query });
    return response.data;
  },
  
  executeTool: async (tool_id: string, parameters: any = {}): Promise<any> => {
    const response = await api.post('/api/v1/mcp/tools/execute', {
      tool_id,
      parameters
    });
    return response.data;
  },
  
  testWorkflow: async (message: string, session_id: string = 'test'): Promise<any> => {
    const response = await api.post('/api/v1/mcp/test-workflow', {
      message,
      session_id
    });
    return response.data;
  },
  
  getAgents: async (): Promise<any> => {
    const response = await api.get('/api/v1/mcp/agents');
    return response.data;
  },
  
  refreshDiscovery: async (): Promise<any> => {
    const response = await api.post('/api/v1/mcp/discovery/refresh');
    return response.data;
  }
};

export const chatAPI = {
  sendMessage: async (request: ChatRequest): Promise<ChatResponse> => {
    const response = await api.post('/api/v1/chat', request);
    return response.data;
  },
};

export const equipmentAPI = {
  getAsset: async (asset_id: string): Promise<EquipmentAsset> => {
    const response = await api.get(`/api/v1/equipment/${asset_id}`);
    return response.data;
  },
  
  getAllAssets: async (): Promise<EquipmentAsset[]> => {
    const response = await api.get('/api/v1/equipment');
    return response.data;
  },
  
  getAssetStatus: async (asset_id: string): Promise<any> => {
    const response = await api.get(`/api/v1/equipment/${asset_id}/status`);
    return response.data;
  },
  
  assignAsset: async (data: {
    asset_id: string;
    assignee: string;
    assignment_type?: string;
    task_id?: string;
    duration_hours?: number;
    notes?: string;
  }): Promise<any> => {
    const response = await api.post('/api/v1/equipment/assign', data);
    return response.data;
  },
  
  releaseAsset: async (data: {
    asset_id: string;
    released_by: string;
    notes?: string;
  }): Promise<any> => {
    const response = await api.post('/api/v1/equipment/release', data);
    return response.data;
  },
  
  getTelemetry: async (asset_id: string, metric?: string, hours_back?: number): Promise<any[]> => {
    const params = new URLSearchParams();
    if (metric) params.append('metric', metric);
    if (hours_back) params.append('hours_back', hours_back.toString());
    
    const response = await api.get(`/api/v1/equipment/${asset_id}/telemetry?${params}`);
    return response.data;
  },
  
  scheduleMaintenance: async (data: {
    asset_id: string;
    maintenance_type: string;
    description: string;
    scheduled_by: string;
    scheduled_for: string;
    estimated_duration_minutes?: number;
    priority?: string;
  }): Promise<any> => {
    const response = await api.post('/api/v1/equipment/maintenance', data);
    return response.data;
  },
  
  getMaintenanceSchedule: async (asset_id?: string, maintenance_type?: string, days_ahead?: number): Promise<any[]> => {
    const params = new URLSearchParams();
    if (asset_id) params.append('asset_id', asset_id);
    if (maintenance_type) params.append('maintenance_type', maintenance_type);
    if (days_ahead) params.append('days_ahead', days_ahead.toString());
    
    const response = await api.get(`/api/v1/equipment/maintenance/schedule?${params}`);
    return response.data;
  },
  
  getAssignments: async (asset_id?: string, assignee?: string, active_only?: boolean): Promise<any[]> => {
    const params = new URLSearchParams();
    if (asset_id) params.append('asset_id', asset_id);
    if (assignee) params.append('assignee', assignee);
    if (active_only) params.append('active_only', active_only.toString());
    
    const response = await api.get(`/api/v1/equipment/assignments?${params}`);
    return response.data;
  },
};

// Keep old equipmentAPI for inventory items (if needed)
export const inventoryAPI = {
  getItem: async (sku: string): Promise<InventoryItem> => {
    const response = await api.get(`/api/v1/inventory/${sku}`);
    return response.data;
  },
  
  getAllItems: async (): Promise<InventoryItem[]> => {
    const response = await api.get('/api/v1/inventory');
    return response.data;
  },
  
  createItem: async (data: Omit<InventoryItem, 'updated_at'>): Promise<InventoryItem> => {
    const response = await api.post('/api/v1/inventory', data);
    return response.data;
  },
  
  updateItem: async (sku: string, data: Partial<InventoryItem>): Promise<InventoryItem> => {
    const response = await api.put(`/api/v1/inventory/${sku}`, data);
    return response.data;
  },
  
  deleteItem: async (sku: string): Promise<void> => {
    await api.delete(`/api/v1/inventory/${sku}`);
  },
};

export const operationsAPI = {
  getTasks: async (): Promise<Task[]> => {
    const response = await api.get('/api/v1/operations/tasks');
    return response.data;
  },
  
  getWorkforceStatus: async (): Promise<any> => {
    const response = await api.get('/api/v1/operations/workforce');
    return response.data;
  },
  
  assignTask: async (taskId: number, assignee: string): Promise<Task> => {
    const response = await api.post(`/api/v1/operations/tasks/${taskId}/assign`, {
      assignee,
    });
    return response.data;
  },
};

export const safetyAPI = {
  getIncidents: async (): Promise<SafetyIncident[]> => {
    const response = await api.get('/api/v1/safety/incidents');
    return response.data;
  },
  
  reportIncident: async (data: Omit<SafetyIncident, 'id' | 'occurred_at'>): Promise<SafetyIncident> => {
    const response = await api.post('/api/v1/safety/incidents', data);
    return response.data;
  },
  
  getPolicies: async (): Promise<any[]> => {
    const response = await api.get('/api/v1/safety/policies');
    return response.data;
  },
};

export const documentAPI = {
  uploadDocument: async (formData: FormData): Promise<any> => {
    const response = await api.post('/api/v1/document/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },
  
  getDocumentStatus: async (documentId: string): Promise<any> => {
    const response = await api.get(`/api/v1/document/status/${documentId}`);
    return response.data;
  },
  
  getDocumentResults: async (documentId: string): Promise<any> => {
    const response = await api.get(`/api/v1/document/results/${documentId}`);
    return response.data;
  },
  
  getDocumentAnalytics: async (): Promise<any> => {
    const response = await api.get('/api/v1/document/analytics');
    return response.data;
  },
  
  searchDocuments: async (query: string, filters?: any): Promise<any> => {
    const response = await api.post('/api/v1/document/search', { query, filters });
    return response.data;
  },
  
  approveDocument: async (documentId: string, approverId: string, notes?: string): Promise<any> => {
    const response = await api.post(`/api/v1/document/approve/${documentId}`, {
      approver_id: approverId,
      approval_notes: notes,
    });
    return response.data;
  },
  
  rejectDocument: async (documentId: string, rejectorId: string, reason: string, suggestions?: string[]): Promise<any> => {
    const response = await api.post(`/api/v1/document/reject/${documentId}`, {
      rejector_id: rejectorId,
      rejection_reason: reason,
      suggestions: suggestions || [],
    });
    return response.data;
  },
};

export const healthAPI = {
  check: async (): Promise<{ ok: boolean }> => {
    const response = await api.get('/api/v1/health/simple');
    return response.data;
  },
};

export default api;
