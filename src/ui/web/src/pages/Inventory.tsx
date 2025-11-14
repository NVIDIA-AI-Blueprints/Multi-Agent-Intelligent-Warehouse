import React, { useState, useEffect, useCallback } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  TextField,
  InputAdornment,
  Grid,
  Alert,
  CircularProgress,
  IconButton,
  Badge,
  Tabs,
  Tab,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
} from '@mui/material';
import {
  Search as SearchIcon,
  Inventory as InventoryIcon,
  Warning as WarningIcon,
  Refresh as RefreshIcon,
} from '@mui/icons-material';
import { inventoryAPI, InventoryItem } from '../services/inventoryAPI';

interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

function TabPanel(props: TabPanelProps) {
  const { children, value, index, ...other } = props;

  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`inventory-tabpanel-${index}`}
      aria-labelledby={`inventory-tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ p: 3 }}>{children}</Box>}
    </div>
  );
}

const InventoryPage: React.FC = () => {
  const [inventoryItems, setInventoryItems] = useState<InventoryItem[]>([]);
  const [filteredItems, setFilteredItems] = useState<InventoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [brandFilter, setBrandFilter] = useState('all');
  const [tabValue, setTabValue] = useState(0);
  const [brands, setBrands] = useState<string[]>(['all']);

  useEffect(() => {
    fetchInventoryItems();
  }, []);

  const filterItems = useCallback(() => {
    let filtered = inventoryItems;

    // Filter by search term
    if (searchTerm) {
      filtered = filtered.filter(item =>
        item.sku.toLowerCase().includes(searchTerm.toLowerCase()) ||
        item.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        item.location.toLowerCase().includes(searchTerm.toLowerCase())
      );
    }

    // Filter by brand
    if (brandFilter !== 'all') {
      filtered = filtered.filter(item => item.sku.startsWith(brandFilter));
    }

    setFilteredItems(filtered);
  }, [inventoryItems, searchTerm, brandFilter]);

  useEffect(() => {
    filterItems();
  }, [filterItems]);

  const fetchInventoryItems = async () => {
    try {
      setLoading(true);
      setError(null);
      const items = await inventoryAPI.getAllItems();
      setInventoryItems(items);
      
      // Dynamically extract brands from actual SKUs
      const uniqueBrands = new Set<string>(['all']);
      items.forEach(item => {
        // Extract brand prefix (first 3 characters of SKU)
        if (item.sku && item.sku.length >= 3) {
          const brandPrefix = item.sku.substring(0, 3).toUpperCase();
          uniqueBrands.add(brandPrefix);
        }
      });
      setBrands(Array.from(uniqueBrands).sort());
    } catch (err) {
      setError('Failed to fetch inventory items');
      // console.error('Error fetching inventory items:', err);
    } finally {
      setLoading(false);
    }
  };

  const getLowStockItems = () => {
    return inventoryItems.filter(item => item.quantity < item.reorder_point);
  };

  const getBrandItems = (brand: string) => {
    return inventoryItems.filter(item => item.sku.startsWith(brand));
  };

  const getStockStatus = (item: InventoryItem) => {
    if (item.quantity === 0) return { status: 'Out of Stock', color: 'error' as const };
    if (item.quantity < item.reorder_point) return { status: 'Low Stock', color: 'warning' as const };
    if (item.quantity < item.reorder_point * 1.5) return { status: 'Medium Stock', color: 'info' as const };
    return { status: 'In Stock', color: 'success' as const };
  };

  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="400px">
        <CircularProgress />
      </Box>
    );
  }

  if (error) {
    return (
      <Box p={3}>
        <Alert severity="error" action={
          <IconButton color="inherit" size="small" onClick={fetchInventoryItems}>
            <RefreshIcon />
          </IconButton>
        }>
          {error}
        </Alert>
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3 }}>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h4" component="h1" gutterBottom>
          <InventoryIcon sx={{ mr: 1, verticalAlign: 'middle' }} />
          Inventory Management
        </Typography>
        <IconButton onClick={fetchInventoryItems} color="primary">
          <RefreshIcon />
        </IconButton>
      </Box>

      {/* Summary Cards */}
      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>
                Total Products
              </Typography>
              <Typography variant="h4">
                {inventoryItems.length}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>
                Low Stock Items
              </Typography>
              <Typography variant="h4" color="warning.main">
                <Badge badgeContent={getLowStockItems().length} color="warning">
                  <WarningIcon />
                </Badge>
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>
                Total Value
              </Typography>
              <Typography variant="h4">
                N/A
              </Typography>
              <Typography variant="caption" color="text.secondary">
                Cost data not available
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>
                Brands
              </Typography>
              <Typography variant="h4">
                {brands.length - 1}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Filters */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Grid container spacing={2} alignItems="center">
            <Grid item xs={12} sm={6} md={4}>
              <TextField
                fullWidth
                placeholder="Search products..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                InputProps={{
                  startAdornment: (
                    <InputAdornment position="start">
                      <SearchIcon />
                    </InputAdornment>
                  ),
                }}
              />
            </Grid>
            <Grid item xs={12} sm={6} md={4}>
              <FormControl fullWidth>
                <InputLabel>Brand</InputLabel>
                <Select
                  value={brandFilter}
                  label="Brand"
                  onChange={(e) => setBrandFilter(e.target.value)}
                >
                  {brands.map((brand) => (
                    <MenuItem key={brand} value={brand}>
                      {brand === 'all' ? 'All Brands' : brand}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={12} md={4}>
              <Typography variant="body2" color="textSecondary">
                Showing {filteredItems.length} of {inventoryItems.length} products
              </Typography>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {/* Tabs */}
      <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
        <Tabs value={tabValue} onChange={handleTabChange} aria-label="inventory tabs">
          <Tab label="All Products" />
          <Tab 
            label={
              <Badge badgeContent={getLowStockItems().length} color="warning">
                Low Stock
              </Badge>
            } 
          />
          <Tab label="Lay's" />
          <Tab label="Doritos" />
          <Tab label="Cheetos" />
        </Tabs>
      </Box>

      {/* All Products Tab */}
      <TabPanel value={tabValue} index={0}>
        <InventoryTable items={filteredItems} />
      </TabPanel>

      {/* Low Stock Tab */}
      <TabPanel value={tabValue} index={1}>
        <InventoryTable items={getLowStockItems()} />
      </TabPanel>

      {/* Brand Tabs */}
      <TabPanel value={tabValue} index={2}>
        <InventoryTable items={getBrandItems('LAY')} />
      </TabPanel>

      <TabPanel value={tabValue} index={3}>
        <InventoryTable items={getBrandItems('DOR')} />
      </TabPanel>

      <TabPanel value={tabValue} index={4}>
        <InventoryTable items={getBrandItems('CHE')} />
      </TabPanel>
    </Box>
  );
};

interface InventoryTableProps {
  items: InventoryItem[];
}

const InventoryTable: React.FC<InventoryTableProps> = ({ items }) => {
  const getStockStatus = (item: InventoryItem) => {
    if (item.quantity === 0) return { status: 'Out of Stock', color: 'error' as const };
    if (item.quantity < item.reorder_point) return { status: 'Low Stock', color: 'warning' as const };
    if (item.quantity < item.reorder_point * 1.5) return { status: 'Medium Stock', color: 'info' as const };
    return { status: 'In Stock', color: 'success' as const };
  };

  if (items.length === 0) {
    return (
      <Alert severity="info">
        No inventory items found matching the current filters.
      </Alert>
    );
  }

  return (
    <TableContainer component={Paper}>
      <Table>
        <TableHead>
          <TableRow>
            <TableCell>SKU</TableCell>
            <TableCell>Product Name</TableCell>
            <TableCell>Quantity</TableCell>
            <TableCell>Location</TableCell>
            <TableCell>Reorder Point</TableCell>
            <TableCell>Status</TableCell>
            <TableCell>Last Updated</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {items.map((item) => {
            const stockStatus = getStockStatus(item);
            return (
              <TableRow key={item.sku} hover>
                <TableCell>
                  <Typography variant="body2" fontWeight="bold">
                    {item.sku}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Typography variant="body2">
                    {item.name}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Typography variant="body2" fontWeight="bold">
                    {item.quantity.toLocaleString()}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Typography variant="body2" color="textSecondary">
                    {item.location}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Typography variant="body2">
                    {item.reorder_point}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Chip
                    label={stockStatus.status}
                    color={stockStatus.color}
                    size="small"
                  />
                </TableCell>
                <TableCell>
                  <Typography variant="body2" color="textSecondary">
                    {new Date(item.updated_at).toLocaleDateString()}
                  </Typography>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </TableContainer>
  );
};


export default InventoryPage;
