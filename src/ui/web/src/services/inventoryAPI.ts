import axios from 'axios';

// Use relative URL to leverage proxy middleware
const API_BASE_URL = process.env.REACT_APP_API_URL || '/api/v1';

export interface InventoryItem {
  sku: string;
  name: string;
  quantity: number;
  location: string;
  reorder_point: number;
  updated_at: string;
}

export interface InventoryUpdate {
  name?: string;
  quantity?: number;
  location?: string;
  reorder_point?: number;
}

class InventoryAPI {
  private baseURL: string;

  constructor() {
    this.baseURL = `${API_BASE_URL}/inventory`;
  }

  async getAllItems(): Promise<InventoryItem[]> {
    try {
      const response = await axios.get(`${this.baseURL}/items`);
      return response.data;
    } catch (error) {
      // console.error('Error fetching inventory items:', error);
      throw error;
    }
  }

  /**
   * Validates and sanitizes path parameters to prevent SSRF attacks.
   * See CVE-2025-27152: https://github.com/axios/axios/security/advisories/GHSA-4w2v-q235-vp99
   */
  private validatePathParam(param: string, paramName: string = 'parameter'): string {
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
    // Use Unicode escape sequences to avoid control character literals in regex
    if (/[\u0000-\u001F\u007F-\u009F\u000A\u000D]/.test(param)) {
      throw new Error(`Invalid ${paramName}: control characters are not allowed`);
    }
    
    // Reject leading/trailing slashes
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

  async getItemBySku(sku: string): Promise<InventoryItem> {
    try {
      const safeSku = this.validatePathParam(sku, 'sku');
      const response = await axios.get(`${this.baseURL}/items/${safeSku}`);
      return response.data;
    } catch (error) {
      // console.error(`Error fetching inventory item ${sku}:`, error);
      throw error;
    }
  }

  async createItem(item: InventoryItem): Promise<InventoryItem> {
    try {
      const response = await axios.post(`${this.baseURL}/items`, item);
      return response.data;
    } catch (error) {
      // console.error('Error creating inventory item:', error);
      throw error;
    }
  }

  async updateItem(sku: string, update: InventoryUpdate): Promise<InventoryItem> {
    try {
      const safeSku = this.validatePathParam(sku, 'sku');
      const response = await axios.put(`${this.baseURL}/items/${safeSku}`, update);
      return response.data;
    } catch (error) {
      // console.error(`Error updating inventory item ${sku}:`, error);
      throw error;
    }
  }

  async getLowStockItems(): Promise<InventoryItem[]> {
    try {
      const allItems = await this.getAllItems();
      return allItems.filter(item => item.quantity < item.reorder_point);
    } catch (error) {
      // console.error('Error fetching low stock items:', error);
      throw error;
    }
  }

  async getItemsByBrand(brand: string): Promise<InventoryItem[]> {
    try {
      const allItems = await this.getAllItems();
      return allItems.filter(item => 
        item.sku.startsWith(brand.toUpperCase()) || 
        item.name.toLowerCase().includes(brand.toLowerCase())
      );
    } catch (error) {
      // console.error(`Error fetching items for brand ${brand}:`, error);
      throw error;
    }
  }
}

export const inventoryAPI = new InventoryAPI();
