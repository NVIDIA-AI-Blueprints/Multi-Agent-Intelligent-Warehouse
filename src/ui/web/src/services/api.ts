import axios from 'axios';

// Use relative URL to leverage proxy middleware
// Force relative path - never use absolute URLs in development
let API_BASE_URL = process.env.REACT_APP_API_URL || '/api/v1';

// Ensure we never use absolute URLs that would bypass the proxy
if (API_BASE_URL.startsWith('http://') || API_BASE_URL.startsWith('https://')) {
  console.warn('API_BASE_URL should be relative for proxy to work. Using /api/v1 instead.');
  API_BASE_URL = '/api/v1';
}

/**
 * Validates and sanitizes path parameters to prevent SSRF attacks.
 * 
 * This function ensures that user-controlled path parameters:
 * - Do not contain absolute URLs (http://, https://)
 * - Do not contain path traversal sequences (../, ..\\)
 * - Do not contain control characters or newlines
 * - Are safe to use in URL paths
 * 
 * @param param - The path parameter to validate
 * @param paramName - Name of the parameter for error messages
 * @returns Sanitized parameter safe for use in URLs
 * @throws Error if parameter contains unsafe content
 * 
 * @example
 * const safeId = validatePathParam(userId, 'user_id');
 * api.get(`/users/${safeId}`);
 */
export function validatePathParam(param: string, paramName: string = 'parameter'): string {
  if (!param || typeof param !== 'string') {
    throw new Error(`Invalid ${paramName}: must be a non-empty string`);
  }
  
  // Reject absolute URLs (SSRF prevention)
  if (param.startsWith('http://') || param.startsWith('https://') || param.startsWith('//')) {
    throw new Error(`Invalid ${paramName}: absolute URLs are not allowed`);
  }
  
  // Reject path traversal sequences
  if (param.includes('../') || param.includes('..\\') || param.includes('..%2F') || param.includes('..%5C')) {
    throw new Error(`Invalid ${paramName}: path traversal sequences are not allowed`);
  }
  
  // Reject control characters and newlines
  // Use character code checking instead of regex to avoid linting issues
  // Checks for: control chars (0x00-0x1F), DEL (0x7F), extended control (0x80-0x9F), LF (0x0A), CR (0x0D)
  for (let i = 0; i < param.length; i++) {
    const code = param.charCodeAt(i);
    // Check for control characters, DEL, extended control, newline, carriage return
    if ((code >= 0x00 && code <= 0x1F) || code === 0x7F || (code >= 0x80 && code <= 0x9F) || code === 0x0A || code === 0x0D) {
      throw new Error(`Invalid ${paramName}: control characters are not allowed`);
    }
  }
  
  // Reject leading/trailing slashes that could affect path resolution
  // Use string methods instead of regex to prevent ReDoS vulnerabilities
  // This approach is O(n) with no backtracking risk, safe for any input length
  let sanitized = param.trim();
  
  // Remove leading slashes - O(n) operation, no backtracking
  let startIdx = 0;
  while (startIdx < sanitized.length && sanitized[startIdx] === '/') {
    startIdx++;
  }
  sanitized = sanitized.substring(startIdx);
  
  // Remove trailing slashes - O(n) operation, no backtracking
  let endIdx = sanitized.length;
  while (endIdx > 0 && sanitized[endIdx - 1] === '/') {
    endIdx--;
  }
  sanitized = sanitized.substring(0, endIdx);
  
  if (!sanitized) {
    throw new Error(`Invalid ${paramName}: cannot be empty after sanitization`);
  }
  
  return sanitized;
}

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60000, // Increased to 60 seconds for complex reasoning
  headers: {
    'Content-Type': 'application/json',
  },
  // Security: Prevent SSRF attacks by disallowing absolute URLs
  // This prevents user-controlled URLs from bypassing baseURL and making requests to arbitrary hosts
  // See CVE-2025-27152: https://github.com/axios/axios/security/advisories/GHSA-4w2v-q235-vp99
  allowAbsoluteUrls: false,
});

// Log API configuration in development to help debug proxy issues
if (process.env.NODE_ENV === 'development') {
  console.log('[API Config] baseURL:', API_BASE_URL);
  console.log('[API Config] Using proxy middleware for /api/* requests');
}

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
    const status = error.response?.status;
    const url = error.config?.url || '';
    
    // Suppress error logging for version endpoint - it's non-critical
    // Still reject the promise so calling code can handle it, but don't log
    const isVersionEndpoint = url.includes('/version');
    
    // 403 (Forbidden) = authenticated but not authorized - never redirect to login
    if (status === 403) {
      // Let the component handle permission errors gracefully
      if (!isVersionEndpoint) {
        console.error('API Error:', error.response?.status, error.response?.data);
      }
      return Promise.reject(error);
    }
    
    // 401 (Unauthorized) handling - only redirect if token is truly invalid
    if (status === 401) {
      // Don't redirect for endpoints that handle their own auth errors gracefully
      const isOptionalEndpoint = url.includes('/auth/users') || url.includes('/auth/me') || url.includes('/login');
      
      // Check if request had auth token - if yes, token is likely invalid/expired
      const hasAuthHeader = error.config?.headers?.Authorization;
      const token = localStorage.getItem('auth_token');
      
      // Only redirect if:
      // 1. We have a token in localStorage (user thinks they're logged in)
      // 2. Request included auth header (token was sent)
      // 3. It's not an optional endpoint that handles its own errors
      // 4. We're not already on login page
      if (token && hasAuthHeader && !isOptionalEndpoint && window.location.pathname !== '/login') {
        // Token exists but request failed with 401 - token is invalid/expired
        localStorage.removeItem('auth_token');
        localStorage.removeItem('user_info');
        window.location.href = '/login';
      }
      // For /auth/me, /auth/users, and /login, let the calling component handle the error gracefully
      // For other cases (no token, optional endpoints), let component handle it
      
      // Log 401 errors for non-version endpoints (login errors should be handled by login component)
      if (!isVersionEndpoint && !url.includes('/login')) {
        console.error('API Error:', error.response?.status, error.response?.data);
      }
      return Promise.reject(error);
    }
    
    // For other errors (network errors, etc.), log them normally (but not for version endpoint)
    if (!isVersionEndpoint) {
      if (error.response) {
        // Server responded with error status
        console.error('API Error:', error.response.status, error.response.data);
      } else if (error.request) {
        // Request made but no response received - network error
        console.error('API Network Error:', error.message);
      } else {
        // Something else happened
        console.error('API Error:', error.message);
      }
    }
    
    return Promise.reject(error);
  }
);

export interface ChatRequest {
  message: string;
  session_id?: string;
  context?: Record<string, any>;
  enable_reasoning?: boolean;
  reasoning_types?: string[];
}

export interface ReasoningStep {
  step_id: string;
  step_type: string;
  description: string;
  reasoning: string;
  confidence: number;
}

export interface ReasoningChain {
  chain_id: string;
  query: string;
  reasoning_type: string;
  steps: ReasoningStep[];
  final_conclusion: string;
  overall_confidence: number;
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
  reasoning_chain?: ReasoningChain;
  reasoning_steps?: ReasoningStep[];
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
    const response = await api.get('/mcp/status');
    return response.data;
  },
  
  getTools: async (): Promise<any> => {
    const response = await api.get('/mcp/tools');
    return response.data;
  },
  
  searchTools: async (query: string): Promise<any> => {
    const response = await api.post(`/mcp/tools/search?query=${encodeURIComponent(query)}`);
    return response.data;
  },
  
  executeTool: async (tool_id: string, parameters: any = {}): Promise<any> => {
    const response = await api.post(`/mcp/tools/execute?tool_id=${encodeURIComponent(tool_id)}`, parameters);
    return response.data;
  },
  
  testWorkflow: async (message: string, session_id: string = 'test'): Promise<any> => {
    const response = await api.post(`/mcp/test-workflow?message=${encodeURIComponent(message)}&session_id=${encodeURIComponent(session_id)}`);
    return response.data;
  },
  
  getAgents: async (): Promise<any> => {
    const response = await api.get('/mcp/agents');
    return response.data;
  },
  
  refreshDiscovery: async (): Promise<any> => {
    const response = await api.post('/mcp/discovery/refresh');
    return response.data;
  }
};

export const chatAPI = {
  sendMessage: async (request: ChatRequest): Promise<ChatResponse> => {
    // Use longer timeout when reasoning is enabled (reasoning takes longer)
    // Also detect complex queries that need even more time
    const messageLower = request.message.toLowerCase();
    const isComplexQuery = messageLower.includes('analyze') || 
                          messageLower.includes('relationship') || 
                          messageLower.includes('between') ||
                          messageLower.includes('compare') ||
                          messageLower.includes('evaluate') ||
                          messageLower.includes('correlation') ||
                          messageLower.includes('impact') ||
                          messageLower.includes('effect') ||
                          request.message.split(' ').length > 15;
    
    let timeout = 60000; // Default 60s
    if (request.enable_reasoning) {
      timeout = isComplexQuery ? 240000 : 120000; // 240s (4min) for complex reasoning, 120s for regular reasoning
    } else if (isComplexQuery) {
      timeout = 120000; // 120s for complex queries without reasoning
    }
    
    // Log timeout for debugging
    if (process.env.NODE_ENV === 'development') {
      console.log(`[ChatAPI] Query timeout: ${timeout}ms, Complex: ${isComplexQuery}, Reasoning: ${request.enable_reasoning}`);
    }
    
    const response = await api.post('/chat', request, { timeout });
    return response.data;
  },
};

export const equipmentAPI = {
  getAsset: async (asset_id: string): Promise<EquipmentAsset> => {
    const safeId = validatePathParam(asset_id, 'asset_id');
    const response = await api.get(`/equipment/${safeId}`);
    return response.data;
  },
  
  getAllAssets: async (): Promise<EquipmentAsset[]> => {
    const response = await api.get('/equipment');
    return response.data;
  },
  
  getAssetStatus: async (asset_id: string): Promise<any> => {
    const safeId = validatePathParam(asset_id, 'asset_id');
    const response = await api.get(`/equipment/${safeId}/status`);
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
    const response = await api.post('/equipment/assign', data);
    return response.data;
  },
  
  releaseAsset: async (data: {
    asset_id: string;
    released_by: string;
    notes?: string;
  }): Promise<any> => {
    const response = await api.post('/equipment/release', data);
    return response.data;
  },
  
  getTelemetry: async (asset_id: string, metric?: string, hours_back?: number): Promise<any[]> => {
    const safeId = validatePathParam(asset_id, 'asset_id');
    const params = new URLSearchParams();
    if (metric) params.append('metric', metric);
    if (hours_back) params.append('hours_back', hours_back.toString());
    
    const response = await api.get(`/equipment/${safeId}/telemetry?${params}`);
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
    const response = await api.post('/equipment/maintenance', data);
    return response.data;
  },
  
  getMaintenanceSchedule: async (asset_id?: string, maintenance_type?: string, days_ahead?: number): Promise<any[]> => {
    const params = new URLSearchParams();
    if (asset_id) params.append('asset_id', asset_id);
    if (maintenance_type) params.append('maintenance_type', maintenance_type);
    if (days_ahead) params.append('days_ahead', days_ahead.toString());
    
    const response = await api.get(`/equipment/maintenance/schedule?${params}`);
    return response.data;
  },
  
  getAssignments: async (asset_id?: string, assignee?: string, active_only?: boolean): Promise<any[]> => {
    const params = new URLSearchParams();
    if (asset_id) params.append('asset_id', asset_id);
    if (assignee) params.append('assignee', assignee);
    if (active_only) params.append('active_only', active_only.toString());
    
    const response = await api.get(`/equipment/assignments?${params}`);
    return response.data;
  },
};

// Keep old equipmentAPI for inventory items (if needed)
export const inventoryAPI = {
  getItem: async (sku: string): Promise<InventoryItem> => {
    const safeSku = validatePathParam(sku, 'sku');
    const response = await api.get(`/inventory/${safeSku}`);
    return response.data;
  },
  
  getAllItems: async (): Promise<InventoryItem[]> => {
    const response = await api.get('/inventory');
    return response.data;
  },
  
  createItem: async (data: Omit<InventoryItem, 'updated_at'>): Promise<InventoryItem> => {
    const response = await api.post('/inventory', data);
    return response.data;
  },
  
  updateItem: async (sku: string, data: Partial<InventoryItem>): Promise<InventoryItem> => {
    const safeSku = validatePathParam(sku, 'sku');
    const response = await api.put(`/inventory/${safeSku}`, data);
    return response.data;
  },
  
  deleteItem: async (sku: string): Promise<void> => {
    const safeSku = validatePathParam(sku, 'sku');
    await api.delete(`/inventory/${safeSku}`);
  },
};

export const operationsAPI = {
  getTasks: async (): Promise<Task[]> => {
    const response = await api.get('/operations/tasks');
    return response.data;
  },
  
  getWorkforceStatus: async (): Promise<any> => {
    const response = await api.get('/operations/workforce');
    return response.data;
  },
  
  assignTask: async (taskId: number, assignee: string): Promise<Task> => {
    const response = await api.post(`/operations/tasks/${taskId}/assign`, {
      assignee,
    });
    return response.data;
  },
};

export const safetyAPI = {
  getIncidents: async (): Promise<SafetyIncident[]> => {
    const response = await api.get('/safety/incidents');
    return response.data;
  },
  
  reportIncident: async (data: Omit<SafetyIncident, 'id' | 'occurred_at'>): Promise<SafetyIncident> => {
    const response = await api.post('/safety/incidents', data);
    return response.data;
  },
  
  getPolicies: async (): Promise<any[]> => {
    const response = await api.get('/safety/policies');
    return response.data;
  },
};

export const documentAPI = {
  uploadDocument: async (formData: FormData): Promise<any> => {
    const response = await api.post('/document/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },
  
  getDocumentStatus: async (documentId: string): Promise<any> => {
    const safeId = validatePathParam(documentId, 'documentId');
    const response = await api.get(`/document/status/${safeId}`);
    return response.data;
  },
  
  getDocumentResults: async (documentId: string): Promise<any> => {
    const safeId = validatePathParam(documentId, 'documentId');
    const response = await api.get(`/document/results/${safeId}`);
    return response.data;
  },
  
  getDocumentAnalytics: async (): Promise<any> => {
    const response = await api.get('/document/analytics');
    return response.data;
  },
  
  searchDocuments: async (query: string, filters?: any): Promise<any> => {
    const response = await api.post('/document/search', { query, filters });
    return response.data;
  },
  
  approveDocument: async (documentId: string, approverId: string, notes?: string): Promise<any> => {
    const safeId = validatePathParam(documentId, 'documentId');
    const response = await api.post(`/document/approve/${safeId}`, {
      approver_id: approverId,
      approval_notes: notes,
    });
    return response.data;
  },
  
  rejectDocument: async (documentId: string, rejectorId: string, reason: string, suggestions?: string[]): Promise<any> => {
    const safeId = validatePathParam(documentId, 'documentId');
    const response = await api.post(`/document/reject/${safeId}`, {
      rejector_id: rejectorId,
      rejection_reason: reason,
      suggestions: suggestions || [],
    });
    return response.data;
  },
};

export const healthAPI = {
  check: async (): Promise<{ ok: boolean }> => {
    const response = await api.get('/health/simple');
    return response.data;
  },
};

export interface User {
  id: number;
  username: string;
  email: string;
  full_name: string;
  role: string;
  status: string;
}

export const userAPI = {
  getUsers: async (): Promise<User[]> => {
    try {
      const response = await api.get('/auth/users');
      return response.data;
    } catch (error) {
      // If not admin or endpoint doesn't exist, return empty array
      console.warn('Could not fetch users:', error);
      return [];
    }
  },
};

export default api;
