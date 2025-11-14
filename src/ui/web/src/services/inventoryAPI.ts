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

  async getItemBySku(sku: string): Promise<InventoryItem> {
    try {
      const response = await axios.get(`${this.baseURL}/items/${sku}`);
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
      const response = await axios.put(`${this.baseURL}/items/${sku}`, update);
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
