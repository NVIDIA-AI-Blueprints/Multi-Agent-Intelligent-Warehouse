import React, { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  Grid,
  Card,
  CardContent,
  Button,
  Chip,
  LinearProgress,
  Alert,
  Tabs,
  Tab,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  Paper,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  CircularProgress,
  Snackbar,
} from '@mui/material';
import {
  CloudUpload as UploadIcon,
  Search as SearchIcon,
  Assessment as AnalyticsIcon,
  CheckCircle as ApprovedIcon,
  Warning as ReviewIcon,
  Error as RejectedIcon,
  Description as DocumentIcon,
  Visibility as ViewIcon,
  Download as DownloadIcon,
  CheckCircle,
  Close as CloseIcon,
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { documentAPI } from '../services/api';

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
      id={`document-tabpanel-${index}`}
      aria-labelledby={`document-tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ p: 3 }}>{children}</Box>}
    </div>
  );
}

interface DocumentProcessingStage {
  name: string;
  completed: boolean;
  current: boolean;
  description: string;
}

interface DocumentItem {
  id: string;
  filename: string;
  status: string;
  uploadTime: Date;
  progress: number;
  stages: DocumentProcessingStage[];
  qualityScore?: number;
  processingTime?: number;
  extractedData?: any;
  routingDecision?: string;
}

interface DocumentResults {
  document_id: string;
  extracted_data: any;
  confidence_scores: any;
  quality_score: number;
  routing_decision: string;
  processing_stages: string[];
}

interface AnalyticsData {
  metrics: {
    total_documents: number;
    processed_today: number;
    average_quality: number;
    auto_approved: number;
    success_rate: number;
  };
  trends: {
    daily_processing: number[];
    quality_trends: number[];
  };
  summary: string;
}

const DocumentExtraction: React.FC = () => {
  const [activeTab, setActiveTab] = useState(0);
  const [uploadedDocuments, setUploadedDocuments] = useState<DocumentItem[]>([]);
  const [processingDocuments, setProcessingDocuments] = useState<DocumentItem[]>([]);
  const [completedDocuments, setCompletedDocuments] = useState<DocumentItem[]>([]);
  const [analyticsData, setAnalyticsData] = useState<AnalyticsData | null>(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [isUploading, setIsUploading] = useState(false);
  const [selectedDocument, setSelectedDocument] = useState<DocumentItem | null>(null);
  const [resultsDialogOpen, setResultsDialogOpen] = useState(false);
  const [documentResults, setDocumentResults] = useState<DocumentResults | null>(null);
  const [snackbarOpen, setSnackbarOpen] = useState(false);
  const [snackbarMessage, setSnackbarMessage] = useState('');
  const navigate = useNavigate();

  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setActiveTab(newValue);
  };

  // Load analytics data when component mounts
  useEffect(() => {
    loadAnalyticsData();
  }, []);

  const loadAnalyticsData = async () => {
    try {
      const response = await documentAPI.getDocumentAnalytics();
      if (response.success) {
        setAnalyticsData(response.data);
      }
    } catch (error) {
      console.error('Failed to load analytics data:', error);
    }
  };

  const handleDocumentUpload = async (file: File) => {
    setIsUploading(true);
    setUploadProgress(0);
    
    try {
      // Simulate upload progress
      const progressInterval = setInterval(() => {
        setUploadProgress(prev => {
          if (prev >= 90) {
            clearInterval(progressInterval);
            return 90;
          }
          return prev + 10;
        });
      }, 200);

      // Create FormData for file upload
      const formData = new FormData();
      formData.append('file', file);
      formData.append('document_type', 'invoice'); // Default type
      formData.append('user_id', 'admin'); // Default user
      
      // Upload document to backend
      const response = await documentAPI.uploadDocument(formData);
      
      clearInterval(progressInterval);
      setUploadProgress(100);
      
      if (response.success) {
        const documentId = response.document_id;
        const newDocument: DocumentItem = {
          id: documentId,
          filename: file.name,
          status: 'processing',
          uploadTime: new Date(),
          progress: 0,
          stages: [
            { name: 'Preprocessing', completed: false, current: true, description: 'Document preprocessing with NeMo Retriever' },
            { name: 'OCR Extraction', completed: false, current: false, description: 'Intelligent OCR with NeMoRetriever-OCR-v1' },
            { name: 'LLM Processing', completed: false, current: false, description: 'Small LLM processing with Llama Nemotron Nano VL 8B' },
            { name: 'Validation', completed: false, current: false, description: 'Large LLM judge and validator' },
            { name: 'Routing', completed: false, current: false, description: 'Intelligent routing based on quality scores' },
          ]
        };
        
        setProcessingDocuments(prev => [...prev, newDocument]);
        setSnackbarMessage('Document uploaded successfully!');
        setSnackbarOpen(true);
        
        // Start monitoring processing status
        monitorDocumentProcessing(documentId);
        
      } else {
        throw new Error(response.message || 'Upload failed');
      }
      
    } catch (error) {
      console.error('Upload failed:', error);
      setSnackbarMessage(`Upload failed: ${error instanceof Error ? error.message : 'Unknown error'}`);
      setSnackbarOpen(true);
    } finally {
      setIsUploading(false);
      setUploadProgress(0);
    }
  };

  const monitorDocumentProcessing = async (documentId: string) => {
    const checkStatus = async () => {
      try {
        const statusResponse = await documentAPI.getDocumentStatus(documentId);
        if (statusResponse.success) {
          const status = statusResponse.data;
          
          setProcessingDocuments(prev => prev.map(doc => {
            if (doc.id === documentId) {
              const updatedDoc = {
                ...doc,
                progress: status.progress_percentage,
                stages: doc.stages.map((stage, index) => ({
                  ...stage,
                  completed: status.stages_completed.includes(stage.name),
                  current: stage.name === status.current_stage
                }))
              };
              
              // If processing is complete, move to completed documents
              if (status.status === 'completed') {
                setCompletedDocuments(prevCompleted => [...prevCompleted, {
                  ...updatedDoc,
                  status: 'completed',
                  progress: 100,
                  qualityScore: 4.2, // Mock quality score
                  processingTime: 45, // Mock processing time
                  routingDecision: 'Auto-Approved'
                }]);
                return null; // Remove from processing
              }
              
              return updatedDoc;
            }
            return doc;
          }).filter(doc => doc !== null) as DocumentItem[]);
          
          // Continue monitoring if not completed
          if (status.status !== 'completed' && status.status !== 'failed') {
            setTimeout(checkStatus, 2000); // Check every 2 seconds
          }
        }
      } catch (error) {
        console.error('Failed to check document status:', error);
      }
    };
    
    checkStatus();
  };

  const handleViewResults = async (document: DocumentItem) => {
    try {
      const response = await documentAPI.getDocumentResults(document.id);
      if (response.success) {
        setDocumentResults(response.data);
        setSelectedDocument(document);
        setResultsDialogOpen(true);
      } else {
        setSnackbarMessage('Failed to load document results');
        setSnackbarOpen(true);
      }
    } catch (error) {
      console.error('Failed to get document results:', error);
      setSnackbarMessage('Failed to load document results');
      setSnackbarOpen(true);
    }
  };

  const ProcessingPipelineCard = () => (
    <Card>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          NVIDIA NeMo Processing Pipeline
        </Typography>
        <List dense>
          {[
            { name: '1. Document Preprocessing', description: 'NeMo Retriever Extraction', color: 'primary' },
            { name: '2. Intelligent OCR', description: 'NeMoRetriever-OCR-v1 + Nemotron Parse', color: 'primary' },
            { name: '3. Small LLM Processing', description: 'Llama Nemotron Nano VL 8B', color: 'primary' },
            { name: '4. Embedding & Indexing', description: 'nv-embedqa-e5-v5', color: 'primary' },
            { name: '5. Large LLM Judge', description: 'Llama 3.1 Nemotron 70B', color: 'primary' },
            { name: '6. Intelligent Routing', description: 'Quality-based routing', color: 'primary' },
          ].map((stage, index) => (
            <ListItem key={index}>
              <ListItemIcon>
                <Chip label={stage.name.split('.')[0]} color={stage.color as any} size="small" />
              </ListItemIcon>
              <ListItemText 
                primary={stage.name}
                secondary={stage.description}
              />
            </ListItem>
          ))}
        </List>
      </CardContent>
    </Card>
  );

  const DocumentUploadCard = () => (
    <Card>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          Upload Documents
        </Typography>
        
        {isUploading && (
          <Box sx={{ mb: 2 }}>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              Uploading document... {uploadProgress}%
            </Typography>
            <LinearProgress variant="determinate" value={uploadProgress} />
          </Box>
        )}
        
        <Box
          sx={{
            border: '2px dashed #ccc',
            borderRadius: 2,
            p: 4,
            textAlign: 'center',
            cursor: isUploading ? 'not-allowed' : 'pointer',
            opacity: isUploading ? 0.6 : 1,
            '&:hover': {
              borderColor: isUploading ? '#ccc' : 'primary.main',
              backgroundColor: isUploading ? 'transparent' : 'action.hover',
            },
          }}
          onClick={() => {
            if (isUploading) return;
            
            // Create a mock file input
            const input = document.createElement('input');
            input.type = 'file';
            input.accept = '.pdf,.png,.jpg,.jpeg,.tiff,.bmp';
            input.onchange = (e) => {
              const file = (e.target as HTMLInputElement).files?.[0];
              if (file) {
                handleDocumentUpload(file);
              }
            };
            input.click();
          }}
        >
          <UploadIcon sx={{ fontSize: 48, color: 'text.secondary', mb: 2 }} />
          <Typography variant="h6" gutterBottom>
            {isUploading ? 'Uploading...' : 'Click to Upload Document'}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Supported formats: PDF, PNG, JPG, JPEG, TIFF, BMP
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Maximum file size: 50MB
          </Typography>
        </Box>
        
        <Alert severity="info" sx={{ mt: 2 }}>
          <Typography variant="body2">
            Documents are processed through NVIDIA's NeMo models for intelligent extraction, 
            validation, and routing. Processing typically takes 30-60 seconds.
          </Typography>
        </Alert>
      </CardContent>
    </Card>
  );

  const ProcessingStatusCard = ({ document }: { document: DocumentItem }) => (
    <Card>
      <CardContent>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <Typography variant="h6">{document.filename}</Typography>
          <Chip 
            label={document.status} 
            color={document.status === 'completed' ? 'success' : 'primary'} 
            size="small" 
          />
        </Box>
        
        <LinearProgress 
          variant="determinate" 
          value={document.progress} 
          sx={{ mb: 2 }} 
        />
        
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {document.progress}% Complete
        </Typography>
        
        <List dense>
          {document.stages.map((stage, index) => (
            <ListItem key={index}>
              <ListItemIcon>
                {stage.completed ? (
                  <CheckCircle color="success" />
                ) : stage.current ? (
                  <LinearProgress sx={{ width: 20, height: 20 }} />
                ) : (
                  <div style={{ width: 20, height: 20, borderRadius: '50%', backgroundColor: '#e0e0e0' }} />
                )}
              </ListItemIcon>
              <ListItemText 
                primary={stage.name}
                secondary={stage.description}
              />
            </ListItem>
          ))}
        </List>
      </CardContent>
    </Card>
  );

  const CompletedDocumentCard = ({ document }: { document: DocumentItem }) => (
    <Card>
      <CardContent>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <Typography variant="h6">{document.filename}</Typography>
          <Box>
            <Chip label="Completed" color="success" size="small" sx={{ mr: 1 }} />
            <Chip label={document.routingDecision || "Auto-Approved"} color="success" size="small" />
          </Box>
        </Box>
        
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Quality Score: {document.qualityScore || 4.2}/5.0 | Processing Time: {document.processingTime || 45}s
        </Typography>
        
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Button 
            size="small" 
            startIcon={<ViewIcon />}
            onClick={() => handleViewResults(document)}
          >
            View Results
          </Button>
          <Button size="small" startIcon={<DownloadIcon />}>
            Download
          </Button>
        </Box>
      </CardContent>
    </Card>
  );

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom>
        Document Extraction & Processing
      </Typography>
      <Typography variant="body1" color="text.secondary" sx={{ mb: 3 }}>
        Upload warehouse documents for intelligent extraction and processing using NVIDIA NeMo models
      </Typography>

      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <Tabs value={activeTab} onChange={handleTabChange} aria-label="document processing tabs">
          <Tab label="Upload Documents" icon={<UploadIcon />} />
          <Tab label="Processing Status" icon={<SearchIcon />} />
          <Tab label="Completed Documents" icon={<ApprovedIcon />} />
          <Tab label="Analytics" icon={<AnalyticsIcon />} />
        </Tabs>
      </Box>

      <TabPanel value={activeTab} index={0}>
        <Grid container spacing={3}>
          <Grid item xs={12} md={8}>
            <DocumentUploadCard />
          </Grid>
          
          <Grid item xs={12} md={4}>
            <ProcessingPipelineCard />
          </Grid>
        </Grid>
      </TabPanel>

      <TabPanel value={activeTab} index={1}>
        <Grid container spacing={3}>
          {processingDocuments.length === 0 ? (
            <Grid item xs={12}>
              <Paper sx={{ p: 4, textAlign: 'center' }}>
                <Typography variant="h6" color="text.secondary">
                  No documents currently processing
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Upload a document to see processing status
                </Typography>
              </Paper>
            </Grid>
          ) : (
            processingDocuments.map((doc) => (
              <Grid item xs={12} md={6} key={doc.id}>
                <ProcessingStatusCard document={doc} />
              </Grid>
            ))
          )}
        </Grid>
      </TabPanel>

      <TabPanel value={activeTab} index={2}>
        <Grid container spacing={3}>
          {completedDocuments.length === 0 ? (
            <Grid item xs={12}>
              <Paper sx={{ p: 4, textAlign: 'center' }}>
                <Typography variant="h6" color="text.secondary">
                  No completed documents
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Processed documents will appear here
                </Typography>
              </Paper>
            </Grid>
          ) : (
            completedDocuments.map((doc) => (
              <Grid item xs={12} md={6} key={doc.id}>
                <CompletedDocumentCard document={doc} />
              </Grid>
            ))
          )}
        </Grid>
      </TabPanel>

      <TabPanel value={activeTab} index={3}>
        <Grid container spacing={3}>
          <Grid item xs={12} md={4}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Processing Statistics
                </Typography>
                {analyticsData ? (
                  <List>
                    <ListItem>
                      <ListItemText primary="Total Documents" secondary={analyticsData.metrics.total_documents.toLocaleString()} />
                    </ListItem>
                    <ListItem>
                      <ListItemText primary="Processed Today" secondary={analyticsData.metrics.processed_today.toString()} />
                    </ListItem>
                    <ListItem>
                      <ListItemText primary="Average Quality" secondary={`${analyticsData.metrics.average_quality}/5.0`} />
                    </ListItem>
                    <ListItem>
                      <ListItemText primary="Auto-Approved" secondary={`${analyticsData.metrics.auto_approved}%`} />
                    </ListItem>
                    <ListItem>
                      <ListItemText primary="Success Rate" secondary={`${analyticsData.metrics.success_rate}%`} />
                    </ListItem>
                  </List>
                ) : (
                  <Box sx={{ display: 'flex', justifyContent: 'center', p: 2 }}>
                    <CircularProgress size={24} />
                  </Box>
                )}
              </CardContent>
            </Card>
          </Grid>
          
          <Grid item xs={12} md={8}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Quality Score Trends
                </Typography>
                {analyticsData ? (
                  <Box sx={{ height: 200, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Typography variant="body2" color="text.secondary">
                      Quality trend chart would be displayed here
                      <br />
                      Recent trend: {analyticsData.trends.quality_trends.slice(-5).join(', ')}
                    </Typography>
                  </Box>
                ) : (
                  <Box sx={{ height: 200, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <CircularProgress />
                  </Box>
                )}
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </TabPanel>

      {/* Results Dialog */}
      <Dialog 
        open={resultsDialogOpen} 
        onClose={() => setResultsDialogOpen(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Typography variant="h6">
              Document Results - {selectedDocument?.filename}
            </Typography>
            <Button
              onClick={() => setResultsDialogOpen(false)}
              startIcon={<CloseIcon />}
            >
              Close
            </Button>
          </Box>
        </DialogTitle>
        <DialogContent>
          {documentResults ? (
            <Box>
              <Typography variant="h6" gutterBottom>
                Extracted Data
              </Typography>
              <TableContainer component={Paper} sx={{ mb: 3 }}>
                <Table>
                  <TableHead>
                    <TableRow>
                      <TableCell><strong>Field</strong></TableCell>
                      <TableCell><strong>Value</strong></TableCell>
                      <TableCell><strong>Confidence</strong></TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {Object.entries(documentResults.extracted_data).map(([key, value]) => (
                      <TableRow key={key}>
                        <TableCell>{key.replace(/_/g, ' ').toUpperCase()}</TableCell>
                        <TableCell>{typeof value === 'object' ? JSON.stringify(value) : String(value)}</TableCell>
                        <TableCell>
                          {documentResults.confidence_scores[key] ? 
                            `${Math.round(documentResults.confidence_scores[key] * 100)}%` : 
                            'N/A'
                          }
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
              
              <Typography variant="h6" gutterBottom>
                Processing Summary
              </Typography>
              <List>
                <ListItem>
                  <ListItemText 
                    primary="Overall Quality Score" 
                    secondary={`${documentResults.quality_score}/5.0`} 
                  />
                </ListItem>
                <ListItem>
                  <ListItemText 
                    primary="Routing Decision" 
                    secondary={documentResults.routing_decision} 
                  />
                </ListItem>
                <ListItem>
                  <ListItemText 
                    primary="Processing Stages" 
                    secondary={documentResults.processing_stages.join(', ')} 
                  />
                </ListItem>
              </List>
            </Box>
          ) : (
            <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
              <CircularProgress />
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setResultsDialogOpen(false)}>
            Close
          </Button>
        </DialogActions>
      </Dialog>

      {/* Snackbar for notifications */}
      <Snackbar
        open={snackbarOpen}
        autoHideDuration={6000}
        onClose={() => setSnackbarOpen(false)}
        message={snackbarMessage}
      />
    </Box>
  );
};

export default DocumentExtraction;
