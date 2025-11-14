import React, { useState } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Grid,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  Alert,
  CircularProgress,
  IconButton,
  Button,
  Tabs,
  Tab,
  LinearProgress,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  TextField,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Stepper,
  Step,
  StepLabel,
  StepContent,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  Divider,
} from '@mui/material';
import {
  TrendingUp as TrendingUpIcon,
  TrendingDown as TrendingDownIcon,
  TrendingFlat as TrendingFlatIcon,
  Refresh as RefreshIcon,
  Warning as WarningIcon,
  CheckCircle as CheckCircleIcon,
  Analytics as AnalyticsIcon,
  Inventory as InventoryIcon,
  Speed as SpeedIcon,
  PlayArrow as PlayIcon,
  Stop as StopIcon,
  Schedule as ScheduleIcon,
  History as HistoryIcon,
  Build as BuildIcon,
  Error as ErrorIcon,
  Info as InfoIcon,
  Assessment as AssessmentIcon,
  Memory as MemoryIcon,
  Storage as StorageIcon,
  Timeline as TimelineIcon,
  BarChart as BarChartIcon,
  PieChart as PieChartIcon,
  ShowChart as ShowChartIcon,
  Star as StarIcon,
  StarBorder as StarBorderIcon,
  ArrowUpward as ArrowUpwardIcon,
  ArrowDownward as ArrowDownwardIcon,
  Remove as RemoveIcon,
} from '@mui/icons-material';
import { useQuery } from 'react-query';
import { forecastingAPI } from '../services/forecastingAPI';
import { trainingAPI, TrainingRequest, TrainingStatus } from '../services/trainingAPI';

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
      id={`forecast-tabpanel-${index}`}
      aria-labelledby={`forecast-tab-${index}`}
      {...other}
    >
      {value === index && (
        <Box sx={{ p: 3 }}>
          {children}
        </Box>
      )}
    </div>
  );
}

const ForecastingPage: React.FC = () => {
  const [selectedTab, setSelectedTab] = useState(0);
  
  // Training state
  const [trainingType, setTrainingType] = useState<'basic' | 'advanced'>('advanced');
  const [scheduleDialogOpen, setScheduleDialogOpen] = useState(false);
  const [scheduleTime, setScheduleTime] = useState('');
  const [trainingDialogOpen, setTrainingDialogOpen] = useState(false);

  // Fetch forecasting data - use dashboard endpoint only for faster loading
  const { data: dashboardData, isLoading: dashboardLoading, refetch: refetchDashboard, error: dashboardError } = useQuery(
    'forecasting-dashboard',
    forecastingAPI.getDashboardSummary,
    { 
      refetchInterval: 300000, // Refetch every 5 minutes
      retry: 1,
      retryDelay: 200,
      staleTime: 30000, // Consider data fresh for 30 seconds
      cacheTime: 300000, // Keep in cache for 5 minutes
      refetchOnWindowFocus: false // Don't refetch when window gains focus
    }
  );

  // Fetch training status with polling when training is running
  const { data: trainingStatus, refetch: refetchTrainingStatus } = useQuery(
    'training-status',
    trainingAPI.getTrainingStatus,
    { 
      refetchInterval: 2000, // Poll every 2 seconds
      retry: 1,
      retryDelay: 200,
    }
  );

  // Fetch training history
  const { data: trainingHistory } = useQuery(
    'training-history',
    trainingAPI.getTrainingHistory,
    { 
      refetchInterval: 60000, // Refetch every minute
      retry: 1,
    }
  );

  const getTrendIcon = (trend: string) => {
    switch (trend) {
      case 'increasing':
        return <TrendingUpIcon color="success" />;
      case 'decreasing':
        return <TrendingDownIcon color="error" />;
      default:
        return <TrendingFlatIcon color="info" />;
    }
  };

  const getUrgencyColor = (urgency: string) => {
    switch (urgency) {
      case 'critical':
        return 'error';
      case 'high':
        return 'warning';
      case 'medium':
        return 'info';
      default:
        return 'success';
    }
  };

  const getAccuracyColor = (accuracy: number) => {
    if (accuracy >= 0.9) return 'success';
    if (accuracy >= 0.8) return 'info';
    if (accuracy >= 0.7) return 'warning';
    return 'error';
  };

  // Training functions
  const handleStartTraining = async () => {
    try {
      const request: TrainingRequest = {
        training_type: trainingType,
        force_retrain: true
      };
      await trainingAPI.startTraining(request);
      setTrainingDialogOpen(true);
      refetchTrainingStatus();
    } catch (error) {
      console.error('Failed to start training:', error);
    }
  };

  const handleStopTraining = async () => {
    try {
      await trainingAPI.stopTraining();
      refetchTrainingStatus();
    } catch (error) {
      console.error('Failed to stop training:', error);
    }
  };

  const handleScheduleTraining = async () => {
    try {
      const request: TrainingRequest = {
        training_type: trainingType,
        force_retrain: true,
        schedule_time: scheduleTime
      };
      await trainingAPI.scheduleTraining(request);
      setScheduleDialogOpen(false);
      setScheduleTime('');
    } catch (error) {
      console.error('Failed to schedule training:', error);
    }
  };

  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setSelectedTab(newValue);
  };

  // Show error if there are issues
  if (dashboardError) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="error" sx={{ mb: 2 }}>
          Error loading forecasting data: {dashboardError instanceof Error ? dashboardError.message : 'Unknown error'}
        </Alert>
        <Button onClick={() => {
          refetchDashboard();
        }} variant="contained">
          Retry
        </Button>
      </Box>
    );
  }

  if (dashboardLoading) {
    return (
      <Box sx={{ p: 3 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
          <Typography variant="h4" component="h1" gutterBottom>
            Demand Forecasting Dashboard
          </Typography>
          <CircularProgress size={24} />
        </Box>
        
        {/* Show skeleton loading for cards */}
        <Grid container spacing={3} sx={{ mb: 3 }}>
          {[1, 2, 3, 4].map((i) => (
            <Grid item xs={12} sm={6} md={3} key={i}>
              <Card>
                <CardContent>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                    <CircularProgress size={20} sx={{ mr: 1 }} />
                    <Typography variant="h6">Loading...</Typography>
                  </Box>
                  <Typography variant="h4" sx={{ mt: 1 }}>
                    --
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
        
        <Typography variant="body1" sx={{ textAlign: 'center', color: 'text.secondary' }}>
          Loading forecasting data... This may take a few seconds.
        </Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h4" component="h1" gutterBottom>
          Demand Forecasting Dashboard
        </Typography>
        <IconButton onClick={() => {
          refetchDashboard();
        }} color="primary">
          <RefreshIcon />
        </IconButton>
      </Box>

      {/* XGBoost Integration Summary */}
      <Alert severity="success" sx={{ mb: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
          <Typography variant="h6" sx={{ fontWeight: 'bold', mr: 1 }}>
            🚀 XGBoost Integration Complete!
          </Typography>
          <Chip label="NEW" color="primary" size="small" />
        </Box>
        <Typography variant="body2">
          Our demand forecasting system now includes <strong>XGBoost</strong> as part of our advanced ensemble model. 
          XGBoost provides enhanced accuracy with hyperparameter optimization and is now actively generating predictions 
          alongside Random Forest, Gradient Boosting, and other models.
        </Typography>
      </Alert>

      {/* Summary Cards */}
      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                <AnalyticsIcon color="primary" sx={{ mr: 1 }} />
                <Typography variant="h6" component="div">
                  Products Forecasted
                </Typography>
              </Box>
              <Typography variant="h4" component="div" sx={{ mt: 1 }}>
                {dashboardData?.forecast_summary?.total_skus || 0}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                <WarningIcon color="warning" sx={{ mr: 1 }} />
                <Typography variant="h6" component="div">
                  Reorder Alerts
                </Typography>
              </Box>
              <Typography variant="h4" component="div" sx={{ mt: 1 }}>
                {dashboardData?.reorder_recommendations?.filter((r: any) => 
                  r.urgency_level === 'HIGH' || r.urgency_level === 'CRITICAL'
                ).length || 0}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                <SpeedIcon color="info" sx={{ mr: 1 }} />
                <Typography variant="h6" component="div">
                  Avg Accuracy
                </Typography>
              </Box>
              <Typography variant="h4" component="div" sx={{ mt: 1 }}>
                {dashboardData?.model_performance ? 
                  `${(dashboardData.model_performance.reduce((acc: number, m: any) => acc + m.accuracy_score, 0) / dashboardData.model_performance.length * 100).toFixed(1)}%` 
                  : 'N/A'
                }
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                <InventoryIcon color="success" sx={{ mr: 1 }} />
                <Typography variant="h6" component="div">
                  Models Active
                </Typography>
              </Box>
              <Typography variant="h4" component="div" sx={{ mt: 1 }}>
                {dashboardData?.model_performance?.length || 0}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Tabs */}
      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <Tabs value={selectedTab} onChange={handleTabChange} aria-label="forecasting tabs">
          <Tab label="Forecast Summary" />
          <Tab label="Reorder Recommendations" />
          <Tab label="Model Performance" />
          <Tab label="Business Intelligence" />
          <Tab label="Training" />
        </Tabs>
      </Box>

      {/* Forecast Summary Tab */}
      <TabPanel value={selectedTab} index={0}>
        <Typography variant="h5" gutterBottom>
          Product Demand Forecasts
        </Typography>
        <TableContainer component={Paper}>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>SKU</TableCell>
                <TableCell>Avg Daily Demand</TableCell>
                <TableCell>Min Demand</TableCell>
                <TableCell>Max Demand</TableCell>
                <TableCell>Trend</TableCell>
                <TableCell>Forecast Date</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {dashboardData?.forecast_summary?.forecast_summary && Object.entries(dashboardData.forecast_summary.forecast_summary).map(([sku, data]: [string, any]) => (
                <TableRow key={sku}>
                  <TableCell>
                    <Typography variant="body2" fontWeight="bold">
                      {sku}
                    </Typography>
                  </TableCell>
                  <TableCell>{data.average_daily_demand.toFixed(1)}</TableCell>
                  <TableCell>{data.min_demand.toFixed(1)}</TableCell>
                  <TableCell>{data.max_demand.toFixed(1)}</TableCell>
                  <TableCell>
                    <Box sx={{ display: 'flex', alignItems: 'center' }}>
                      {getTrendIcon(data.trend)}
                      <Typography variant="body2" sx={{ ml: 1, textTransform: 'capitalize' }}>
                        {data.trend}
                      </Typography>
                    </Box>
                  </TableCell>
                  <TableCell>
                    {new Date(data.forecast_date).toLocaleDateString()}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </TabPanel>

      {/* Reorder Recommendations Tab */}
      <TabPanel value={selectedTab} index={1}>
        <Typography variant="h5" gutterBottom>
          Reorder Recommendations
        </Typography>
        {dashboardData?.reorder_recommendations && dashboardData.reorder_recommendations.length > 0 ? (
          <TableContainer component={Paper}>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>SKU</TableCell>
                  <TableCell>Current Stock</TableCell>
                  <TableCell>Recommended Order</TableCell>
                  <TableCell>Urgency</TableCell>
                  <TableCell>Reason</TableCell>
                  <TableCell>Confidence</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {dashboardData.reorder_recommendations.map((rec: any, index: number) => (
                  <TableRow key={index}>
                    <TableCell>
                      <Typography variant="body2" fontWeight="bold">
                        {rec.sku}
                      </Typography>
                    </TableCell>
                    <TableCell>{rec.current_stock}</TableCell>
                    <TableCell>{rec.recommended_order_quantity}</TableCell>
                    <TableCell>
                      <Chip 
                        label={rec.urgency_level} 
                        color={getUrgencyColor(rec.urgency_level.toLowerCase()) as any}
                        size="small"
                      />
                    </TableCell>
                    <TableCell>{rec.reason}</TableCell>
                    <TableCell>{(rec.confidence_score * 100).toFixed(1)}%</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        ) : (
          <Alert severity="info">
            No reorder recommendations available at this time.
          </Alert>
        )}
      </TabPanel>

      {/* Model Performance Tab */}
      <TabPanel value={selectedTab} index={2}>
        <Typography variant="h5" gutterBottom>
          Model Performance Metrics
        </Typography>
        
        {/* Model Comparison Cards */}
        <Grid container spacing={2} sx={{ mb: 3 }}>
          {dashboardData?.model_performance?.map((model: any, index: number) => (
            <Grid item xs={12} sm={6} md={4} key={index}>
              <Card sx={{ 
                border: model.model_name === 'XGBoost' ? '2px solid #1976d2' : '1px solid #e0e0e0',
                backgroundColor: model.model_name === 'XGBoost' ? '#f3f8ff' : 'white'
              }}>
                <CardContent>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                    <Typography variant="h6" component="div" sx={{ 
                      fontWeight: 'bold',
                      color: model.model_name === 'XGBoost' ? '#1976d2' : 'inherit'
                    }}>
                      {model.model_name}
                    </Typography>
                    {model.model_name === 'XGBoost' && (
                      <Chip 
                        label="NEW" 
                        size="small" 
                        color="primary" 
                        sx={{ ml: 1, fontSize: '0.7rem' }}
                      />
                    )}
                  </Box>
                  
                  <Box sx={{ mb: 2 }}>
                    <Typography variant="body2" color="text.secondary" gutterBottom>
                      Accuracy Score
                    </Typography>
                    <Box sx={{ display: 'flex', alignItems: 'center' }}>
                      <LinearProgress 
                        variant="determinate" 
                        value={model.accuracy_score * 100} 
                        color={getAccuracyColor(model.accuracy_score) as any}
                        sx={{ width: '100%', mr: 1, height: 8, borderRadius: 4 }}
                      />
                      <Typography variant="body2" fontWeight="bold">
                        {(model.accuracy_score * 100).toFixed(1)}%
                      </Typography>
                    </Box>
                  </Box>
                  
                  <Grid container spacing={1}>
                    <Grid item xs={6}>
                      <Typography variant="body2" color="text.secondary">
                        MAPE
                      </Typography>
                      <Typography variant="body2" fontWeight="bold">
                        {model.mape.toFixed(1)}%
                      </Typography>
                    </Grid>
                    <Grid item xs={6}>
                      <Typography variant="body2" color="text.secondary">
                        Drift Score
                      </Typography>
                      <Typography variant="body2" fontWeight="bold">
                        {model.drift_score.toFixed(2)}
                      </Typography>
                    </Grid>
                  </Grid>
                  
                  <Box sx={{ mt: 2, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <Chip
                      icon={model.status === 'HEALTHY' ? <CheckCircleIcon /> : <WarningIcon />}
                      label={model.status}
                      color={model.status === 'HEALTHY' ? 'success' : model.status === 'WARNING' ? 'warning' : 'error'}
                      size="small"
                    />
                    <Typography variant="caption" color="text.secondary">
                      {new Date(model.last_training_date).toLocaleDateString()}
                    </Typography>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
        
        {/* Detailed Model Performance Table */}
        <Typography variant="h6" gutterBottom sx={{ mt: 3 }}>
          Detailed Performance Metrics
        </Typography>
        {dashboardData?.model_performance && dashboardData.model_performance.length > 0 ? (
          <TableContainer component={Paper}>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Model Name</TableCell>
                  <TableCell>Accuracy</TableCell>
                  <TableCell>MAPE</TableCell>
                  <TableCell>Drift Score</TableCell>
                  <TableCell>Predictions</TableCell>
                  <TableCell>Last Trained</TableCell>
                  <TableCell>Status</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {dashboardData.model_performance.map((model: any, index: number) => (
                  <TableRow key={index} sx={{ 
                    backgroundColor: model.model_name === 'XGBoost' ? '#f8f9ff' : 'inherit'
                  }}>
                    <TableCell>
                      <Box sx={{ display: 'flex', alignItems: 'center' }}>
                        <Typography variant="body2" fontWeight="bold">
                          {model.model_name}
                        </Typography>
                        {model.model_name === 'XGBoost' && (
                          <Chip 
                            label="NEW" 
                            size="small" 
                            color="primary" 
                            sx={{ ml: 1, fontSize: '0.7rem' }}
                          />
                        )}
                      </Box>
                    </TableCell>
                    <TableCell>
                      <Box sx={{ display: 'flex', alignItems: 'center' }}>
                        <LinearProgress 
                          variant="determinate" 
                          value={model.accuracy_score * 100} 
                          color={getAccuracyColor(model.accuracy_score) as any}
                          sx={{ width: 100, mr: 1 }}
                        />
                        <Typography variant="body2">
                          {(model.accuracy_score * 100).toFixed(1)}%
                        </Typography>
                      </Box>
                    </TableCell>
                    <TableCell>{model.mape.toFixed(1)}%</TableCell>
                    <TableCell>{model.drift_score.toFixed(2)}</TableCell>
                    <TableCell>
                      <Typography variant="body2">
                        {model.prediction_count.toLocaleString()}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      {new Date(model.last_training_date).toLocaleDateString()}
                    </TableCell>
                    <TableCell>
                      <Chip 
                        icon={model.status === 'HEALTHY' ? <CheckCircleIcon /> : <WarningIcon />}
                        label={model.status} 
                        color={model.status === 'HEALTHY' ? 'success' : model.status === 'WARNING' ? 'warning' : 'error'}
                        size="small"
                      />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        ) : (
          <Alert severity="info">
            No model performance data available.
          </Alert>
        )}
      </TabPanel>

      {/* Business Intelligence Tab */}
      <TabPanel value={selectedTab} index={3}>
        <Typography variant="h5" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <AnalyticsIcon color="primary" />
          Enhanced Business Intelligence Dashboard
        </Typography>
        
        {dashboardData?.business_intelligence ? (
          <Box>
            {/* Key Performance Indicators */}
            <Grid container spacing={3} sx={{ mb: 3 }}>
              <Grid item xs={12} sm={6} md={3}>
                <Card sx={{ background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)', color: 'white' }}>
                  <CardContent>
                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <Box>
                        <Typography variant="h4" fontWeight="bold">
                          {dashboardData.business_intelligence.inventory_analytics?.total_skus || 0}
                        </Typography>
                        <Typography variant="body2" sx={{ opacity: 0.9 }}>
                          Total SKUs
                        </Typography>
                      </Box>
                      <InventoryIcon sx={{ fontSize: 40, opacity: 0.8 }} />
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
              
              <Grid item xs={12} sm={6} md={3}>
                <Card sx={{ background: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)', color: 'white' }}>
                  <CardContent>
                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <Box>
                        <Typography variant="h4" fontWeight="bold">
                          {dashboardData.business_intelligence.inventory_analytics?.total_quantity?.toLocaleString() || '0'}
                        </Typography>
                        <Typography variant="body2" sx={{ opacity: 0.9 }}>
                          Total Quantity
                        </Typography>
                      </Box>
                      <StorageIcon sx={{ fontSize: 40, opacity: 0.8 }} />
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
              
              <Grid item xs={12} sm={6} md={3}>
                <Card sx={{ background: 'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)', color: 'white' }}>
                  <CardContent>
                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <Box>
                        <Typography variant="h4" fontWeight="bold">
                          {dashboardData.business_intelligence.business_kpis?.forecast_coverage || 0}%
                        </Typography>
                        <Typography variant="body2" sx={{ opacity: 0.9 }}>
                          Forecast Coverage
                        </Typography>
                      </Box>
                      <AssessmentIcon sx={{ fontSize: 40, opacity: 0.8 }} />
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
              
              <Grid item xs={12} sm={6} md={3}>
                <Card sx={{ background: 'linear-gradient(135deg, #43e97b 0%, #38f9d7 100%)', color: 'white' }}>
                  <CardContent>
                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <Box>
                        <Typography variant="h4" fontWeight="bold">
                          {dashboardData.business_intelligence.model_analytics?.avg_accuracy || 0}%
                        </Typography>
                        <Typography variant="body2" sx={{ opacity: 0.9 }}>
                          Avg Accuracy
                        </Typography>
                      </Box>
                      <SpeedIcon sx={{ fontSize: 40, opacity: 0.8 }} />
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>

            {/* Risk Indicators */}
            <Grid container spacing={3} sx={{ mb: 3 }}>
              <Grid item xs={12} md={4}>
                <Card sx={{ border: '2px solid', borderColor: 'error.main' }}>
                  <CardContent>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
                      <WarningIcon color="error" />
                      <Typography variant="h6" color="error">
                        Stockout Risk
                      </Typography>
                    </Box>
                    <Typography variant="h3" color="error" fontWeight="bold">
                      {dashboardData.business_intelligence.business_kpis?.stockout_risk || 0}%
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {dashboardData.business_intelligence.inventory_analytics?.low_stock_items || 0} items below reorder point
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
              
              <Grid item xs={12} md={4}>
                <Card sx={{ border: '2px solid', borderColor: 'warning.main' }}>
                  <CardContent>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
                      <InfoIcon color="warning" />
                      <Typography variant="h6" color="warning.main">
                        Overstock Alert
                      </Typography>
                    </Box>
                    <Typography variant="h3" color="warning.main" fontWeight="bold">
                      {dashboardData.business_intelligence.business_kpis?.overstock_percentage || 0}%
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {dashboardData.business_intelligence.inventory_analytics?.overstock_items || 0} items overstocked
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
              
              <Grid item xs={12} md={4}>
                <Card sx={{ border: '2px solid', borderColor: 'info.main' }}>
                  <CardContent>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
                      <TimelineIcon color="info" />
                      <Typography variant="h6" color="info.main">
                        Demand Volatility
                      </Typography>
                    </Box>
                    <Typography variant="h3" color="info.main" fontWeight="bold">
                      {dashboardData.business_intelligence.business_kpis?.demand_volatility || 0}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Coefficient of variation
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>

            {/* Category Performance */}
            <Grid container spacing={3} sx={{ mb: 3 }}>
              <Grid item xs={12} md={6}>
                <Card>
                  <CardContent>
                    <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <BarChartIcon color="primary" />
                      Category Performance
                    </Typography>
                    <TableContainer>
                      <Table size="small">
                        <TableHead>
                          <TableRow>
                            <TableCell>Category</TableCell>
                            <TableCell align="right">SKUs</TableCell>
                            <TableCell align="right">Value</TableCell>
                            <TableCell align="right">Low Stock</TableCell>
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {dashboardData.business_intelligence.category_analytics?.slice(0, 5).map((category: any) => (
                            <TableRow key={category.category}>
                              <TableCell>
                                <Chip 
                                  label={category.category} 
                                  size="small" 
                                  color="primary" 
                                  variant="outlined"
                                />
                              </TableCell>
                              <TableCell align="right">{category.sku_count}</TableCell>
                              <TableCell align="right">${category.category_quantity?.toLocaleString()}</TableCell>
                              <TableCell align="right">
                                <Chip 
                                  label={category.low_stock_count} 
                                  size="small" 
                                  color={category.low_stock_count > 0 ? 'error' : 'success'}
                                />
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </TableContainer>
                  </CardContent>
                </Card>
              </Grid>
              
              <Grid item xs={12} md={6}>
                <Card>
                  <CardContent>
                    <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <ShowChartIcon color="primary" />
                      Forecast Trends
                    </Typography>
                    {dashboardData.business_intelligence.forecast_analytics ? (
                      <Box>
                        <Grid container spacing={2}>
                          <Grid item xs={4}>
                            <Box sx={{ textAlign: 'center', p: 2, bgcolor: 'success.light', borderRadius: 2 }}>
                              <ArrowUpwardIcon color="success" sx={{ fontSize: 30 }} />
                              <Typography variant="h4" color="success.dark" fontWeight="bold">
                                {dashboardData.business_intelligence.forecast_analytics.trending_up}
                              </Typography>
                              <Typography variant="body2">Trending Up</Typography>
                            </Box>
                          </Grid>
                          <Grid item xs={4}>
                            <Box sx={{ textAlign: 'center', p: 2, bgcolor: 'error.light', borderRadius: 2 }}>
                              <ArrowDownwardIcon color="error" sx={{ fontSize: 30 }} />
                              <Typography variant="h4" color="error.dark" fontWeight="bold">
                                {dashboardData.business_intelligence.forecast_analytics.trending_down}
                              </Typography>
                              <Typography variant="body2">Trending Down</Typography>
                            </Box>
                          </Grid>
                          <Grid item xs={4}>
                            <Box sx={{ textAlign: 'center', p: 2, bgcolor: 'info.light', borderRadius: 2 }}>
                              <RemoveIcon color="info" sx={{ fontSize: 30 }} />
                              <Typography variant="h4" color="info.dark" fontWeight="bold">
                                {dashboardData.business_intelligence.forecast_analytics.stable_trends}
                              </Typography>
                              <Typography variant="body2">Stable</Typography>
                            </Box>
                          </Grid>
                        </Grid>
                        <Typography variant="body2" color="text.secondary" sx={{ mt: 2, textAlign: 'center' }}>
                          Total Predicted Demand: {dashboardData.business_intelligence.forecast_analytics.total_predicted_demand?.toLocaleString()}
                        </Typography>
                      </Box>
                    ) : (
                      <Typography variant="body2" color="text.secondary">
                        Forecast analytics not available
                      </Typography>
                    )}
                  </CardContent>
                </Card>
              </Grid>
            </Grid>

            {/* Top & Bottom Performers */}
            <Grid container spacing={3} sx={{ mb: 3 }}>
              <Grid item xs={12} md={6}>
                <Card>
                  <CardContent>
                    <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <StarIcon color="primary" />
                      Top Performers
                    </Typography>
                    <TableContainer>
                      <Table size="small">
                        <TableHead>
                          <TableRow>
                            <TableCell>SKU</TableCell>
                            <TableCell align="right">Demand</TableCell>
                            <TableCell align="right">Avg Daily</TableCell>
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {dashboardData.business_intelligence.top_performers?.slice(0, 5).map((performer: any, index: number) => (
                            <TableRow key={performer.sku}>
                              <TableCell>
                                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                  <StarIcon color="primary" sx={{ fontSize: 16 }} />
                                  {performer.sku}
                                </Box>
                              </TableCell>
                              <TableCell align="right">{performer.total_demand?.toLocaleString()}</TableCell>
                              <TableCell align="right">{performer.avg_daily_demand?.toFixed(1)}</TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </TableContainer>
                  </CardContent>
                </Card>
              </Grid>
              
              <Grid item xs={12} md={6}>
                <Card>
                  <CardContent>
                    <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <StarBorderIcon color="secondary" />
                      Bottom Performers
                    </Typography>
                    <TableContainer>
                      <Table size="small">
                        <TableHead>
                          <TableRow>
                            <TableCell>SKU</TableCell>
                            <TableCell align="right">Demand</TableCell>
                            <TableCell align="right">Avg Daily</TableCell>
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {dashboardData.business_intelligence.bottom_performers?.slice(0, 5).map((performer: any, index: number) => (
                            <TableRow key={performer.sku}>
                              <TableCell>
                                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                  <StarBorderIcon color="secondary" sx={{ fontSize: 16 }} />
                                  {performer.sku}
                                </Box>
                              </TableCell>
                              <TableCell align="right">{performer.total_demand?.toLocaleString()}</TableCell>
                              <TableCell align="right">{performer.avg_daily_demand?.toFixed(1)}</TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </TableContainer>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>

            {/* Recommendations */}
            <Card sx={{ mb: 3 }}>
              <CardContent>
                <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <InfoIcon color="primary" />
                  AI Recommendations
                </Typography>
                <Grid container spacing={2}>
                  {dashboardData.business_intelligence.recommendations?.map((rec: any, index: number) => (
                    <Grid item xs={12} md={6} key={index}>
                      <Alert 
                        severity={rec.type === 'urgent' ? 'error' : rec.type === 'warning' ? 'warning' : 'info'}
                        sx={{ height: '100%' }}
                      >
                        <Typography variant="subtitle2" fontWeight="bold">
                          {rec.title}
                        </Typography>
                        <Typography variant="body2">
                          {rec.description}
                        </Typography>
                        <Typography variant="body2" sx={{ mt: 1, fontStyle: 'italic' }}>
                          💡 {rec.action}
                        </Typography>
                      </Alert>
                    </Grid>
                  ))}
                </Grid>
              </CardContent>
            </Card>

            {/* Model Performance Summary */}
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <MemoryIcon color="primary" />
                  Model Performance Analytics
                </Typography>
                <Grid container spacing={3}>
                  <Grid item xs={12} md={3}>
                    <Box sx={{ textAlign: 'center', p: 2 }}>
                      <Typography variant="h4" color="primary" fontWeight="bold">
                        {dashboardData.business_intelligence.model_analytics?.total_models || 0}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        Active Models
                      </Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={12} md={3}>
                    <Box sx={{ textAlign: 'center', p: 2 }}>
                      <Typography variant="h4" color="success.main" fontWeight="bold">
                        {dashboardData.business_intelligence.model_analytics?.models_above_80 || 0}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        High Accuracy (&gt;80%)
                      </Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={12} md={3}>
                    <Box sx={{ textAlign: 'center', p: 2 }}>
                      <Typography variant="h4" color="warning.main" fontWeight="bold">
                        {dashboardData.business_intelligence.model_analytics?.models_below_70 || 0}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        Low Accuracy (&lt;70%)
                      </Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={12} md={3}>
                    <Box sx={{ textAlign: 'center', p: 2 }}>
                      <Typography variant="h4" color="info.main" fontWeight="bold">
                        {dashboardData.business_intelligence.model_analytics?.best_model || 'N/A'}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        Best Model
                      </Typography>
                    </Box>
                  </Grid>
                </Grid>
              </CardContent>
            </Card>
          </Box>
        ) : (
          <Alert severity="info">
            Enhanced business intelligence data is being generated...
          </Alert>
        )}
      </TabPanel>

      {/* Training Tab */}
      <TabPanel value={selectedTab} index={4}>
        <Typography variant="h5" gutterBottom>
          Model Training & Management
        </Typography>
        
        {/* Training Controls */}
        <Grid container spacing={3} sx={{ mb: 3 }}>
          <Grid item xs={12} md={6}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Manual Training
                </Typography>
                <FormControl fullWidth sx={{ mb: 2 }}>
                  <InputLabel>Training Type</InputLabel>
                  <Select
                    value={trainingType}
                    label="Training Type"
                    onChange={(e) => setTrainingType(e.target.value as 'basic' | 'advanced')}
                  >
                    <MenuItem value="basic">Basic (Phase 1 & 2)</MenuItem>
                    <MenuItem value="advanced">Advanced (Phase 3)</MenuItem>
                  </Select>
                </FormControl>
                <Box sx={{ display: 'flex', gap: 2 }}>
                  <Button
                    variant="contained"
                    startIcon={<PlayIcon />}
                    onClick={handleStartTraining}
                    disabled={trainingStatus?.is_running}
                    color="primary"
                  >
                    Start Training
                  </Button>
                  <Button
                    variant="outlined"
                    startIcon={<StopIcon />}
                    onClick={handleStopTraining}
                    disabled={!trainingStatus?.is_running}
                    color="error"
                  >
                    Stop Training
                  </Button>
                </Box>
              </CardContent>
            </Card>
          </Grid>
          
          <Grid item xs={12} md={6}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Scheduled Training
                </Typography>
                <TextField
                  fullWidth
                  label="Schedule Time"
                  type="datetime-local"
                  value={scheduleTime}
                  onChange={(e) => setScheduleTime(e.target.value)}
                  InputLabelProps={{ shrink: true }}
                  sx={{ mb: 2 }}
                />
                <Button
                  variant="outlined"
                  startIcon={<ScheduleIcon />}
                  onClick={() => setScheduleDialogOpen(true)}
                  fullWidth
                >
                  Schedule Training
                </Button>
              </CardContent>
            </Card>
          </Grid>
        </Grid>

        {/* Training Status */}
        {trainingStatus && (
          <Card sx={{ mb: 3 }}>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Training Status
              </Typography>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <Chip
                  icon={trainingStatus.is_running ? <BuildIcon /> : <CheckCircleIcon />}
                  label={trainingStatus.is_running ? 'Training in Progress' : 'Idle'}
                  color={trainingStatus.is_running ? 'primary' : 'default'}
                  sx={{ mr: 2 }}
                />
                {trainingStatus.is_running && (
                  <Typography variant="body2" color="text.secondary">
                    {trainingStatus.current_step}
                  </Typography>
                )}
              </Box>
              
              {trainingStatus.is_running && (
                <Box sx={{ mb: 2 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                    <Typography variant="body2" sx={{ mr: 2 }}>
                      Progress: {trainingStatus.progress}%
                    </Typography>
                    {trainingStatus.estimated_completion && (
                      <Typography variant="body2" color="text.secondary">
                        ETA: {new Date(trainingStatus.estimated_completion).toLocaleTimeString()}
                      </Typography>
                    )}
                  </Box>
                  <LinearProgress 
                    variant="determinate" 
                    value={trainingStatus.progress} 
                    sx={{ height: 8, borderRadius: 4 }}
                  />
                </Box>
              )}
              
              {trainingStatus.error && (
                <Alert severity="error" sx={{ mt: 2 }}>
                  {trainingStatus.error}
                </Alert>
              )}
            </CardContent>
          </Card>
        )}

        {/* Training Logs */}
        {trainingStatus?.logs && trainingStatus.logs.length > 0 && (
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Training Logs
              </Typography>
              <Box sx={{ 
                maxHeight: 300, 
                overflow: 'auto', 
                backgroundColor: '#f5f5f5', 
                p: 2, 
                borderRadius: 1,
                fontFamily: 'monospace',
                fontSize: '0.875rem'
              }}>
                {trainingStatus.logs.map((log, index) => (
                  <Typography key={index} variant="body2" sx={{ mb: 0.5 }}>
                    {log}
                  </Typography>
                ))}
              </Box>
            </CardContent>
          </Card>
        )}

        {/* Training History */}
        {trainingHistory && (
          <Card sx={{ mt: 3 }}>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Training History
              </Typography>
              <TableContainer>
                <Table>
                  <TableHead>
                    <TableRow>
                      <TableCell>Training ID</TableCell>
                      <TableCell>Type</TableCell>
                      <TableCell>Start Time</TableCell>
                      <TableCell>Duration</TableCell>
                      <TableCell>Status</TableCell>
                      <TableCell>Models Trained</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {trainingHistory.training_sessions.map((session) => (
                      <TableRow key={session.id}>
                        <TableCell>{session.id}</TableCell>
                        <TableCell>
                          <Chip 
                            label={session.type} 
                            size="small" 
                            color={session.type === 'advanced' ? 'primary' : 'default'}
                          />
                        </TableCell>
                        <TableCell>
                          {new Date(session.start_time).toLocaleString()}
                        </TableCell>
                        <TableCell>{session.duration_minutes} min</TableCell>
                        <TableCell>
                          <Chip 
                            label={session.status} 
                            size="small" 
                            color={session.status === 'completed' ? 'success' : 'default'}
                          />
                        </TableCell>
                        <TableCell>{session.models_trained}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </CardContent>
          </Card>
        )}
      </TabPanel>

      {/* Schedule Training Dialog */}
      <Dialog open={scheduleDialogOpen} onClose={() => setScheduleDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Schedule Training</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Schedule {trainingType} training for a specific time. The training will run automatically at the scheduled time.
          </Typography>
          <TextField
            fullWidth
            label="Schedule Time"
            type="datetime-local"
            value={scheduleTime}
            onChange={(e) => setScheduleTime(e.target.value)}
            InputLabelProps={{ shrink: true }}
            sx={{ mb: 2 }}
          />
          <FormControl fullWidth>
            <InputLabel>Training Type</InputLabel>
            <Select
              value={trainingType}
              label="Training Type"
              onChange={(e) => setTrainingType(e.target.value as 'basic' | 'advanced')}
            >
              <MenuItem value="basic">Basic (Phase 1 & 2) - 5-10 minutes</MenuItem>
              <MenuItem value="advanced">Advanced (Phase 3) - 10-20 minutes</MenuItem>
            </Select>
          </FormControl>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setScheduleDialogOpen(false)}>Cancel</Button>
          <Button 
            onClick={handleScheduleTraining} 
            variant="contained"
            disabled={!scheduleTime}
          >
            Schedule Training
          </Button>
        </DialogActions>
      </Dialog>

      {/* Training Progress Dialog */}
      <Dialog open={trainingDialogOpen} onClose={() => setTrainingDialogOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>Training in Progress</DialogTitle>
        <DialogContent>
          {trainingStatus?.is_running ? (
            <Box>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <CircularProgress size={24} sx={{ mr: 2 }} />
                <Typography variant="h6">
                  {trainingStatus.current_step}
                </Typography>
              </Box>
              <LinearProgress 
                variant="determinate" 
                value={trainingStatus.progress} 
                sx={{ height: 8, borderRadius: 4, mb: 2 }}
              />
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                Progress: {trainingStatus.progress}%
                {trainingStatus.estimated_completion && (
                  <> • ETA: {new Date(trainingStatus.estimated_completion).toLocaleTimeString()}</>
                )}
              </Typography>
              <Box sx={{ 
                maxHeight: 200, 
                overflow: 'auto', 
                backgroundColor: '#f5f5f5', 
                p: 2, 
                borderRadius: 1,
                fontFamily: 'monospace',
                fontSize: '0.875rem'
              }}>
                {trainingStatus.logs.slice(-10).map((log, index) => (
                  <Typography key={index} variant="body2" sx={{ mb: 0.5 }}>
                    {log}
                  </Typography>
                ))}
              </Box>
            </Box>
          ) : (
            <Box sx={{ textAlign: 'center', py: 4 }}>
              <CheckCircleIcon color="success" sx={{ fontSize: 48, mb: 2 }} />
              <Typography variant="h6" gutterBottom>
                Training Completed!
              </Typography>
              <Typography variant="body2" color="text.secondary">
                The models have been successfully trained and are ready for use.
              </Typography>
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setTrainingDialogOpen(false)}>
            {trainingStatus?.is_running ? 'Minimize' : 'Close'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default ForecastingPage;
