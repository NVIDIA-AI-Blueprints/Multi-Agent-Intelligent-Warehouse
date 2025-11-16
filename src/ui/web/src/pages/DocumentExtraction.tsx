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
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
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
  is_mock_data?: boolean;  // Indicates if results are mock/default data
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
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [filePreview, setFilePreview] = useState<string | null>(null);
  const navigate = useNavigate();

  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setActiveTab(newValue);
  };

  const createFilePreview = (file: File): Promise<string> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      
      if (file.type.startsWith('image/')) {
        reader.onload = (e) => {
          resolve(e.target?.result as string);
        };
        reader.onerror = reject;
        reader.readAsDataURL(file);
      } else if (file.type === 'application/pdf') {
        // For PDFs, we'll show a PDF icon with file info
        resolve('pdf');
      } else {
        // For other file types, show a generic document icon
        resolve('document');
      }
    });
  };

  // Load analytics data when component mounts
  useEffect(() => {
    loadAnalyticsData();
  }, []);

  const loadAnalyticsData = async () => {
    try {
      const response = await documentAPI.getDocumentAnalytics();
      setAnalyticsData(response);
    } catch (error) {
      console.error('Failed to load analytics data:', error);
    }
  };

  const handleDocumentUpload = async (file: File) => {
    console.log('Starting document upload for:', file.name);
    setIsUploading(true);
    setUploadProgress(0);
    
    try {
      // Simulate upload progress
      const progressInterval = setInterval(() => {
        setUploadProgress(prev => {
          console.log('Upload progress:', prev + 10);
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
      console.log('Upload response:', response);
      
      clearInterval(progressInterval);
      setUploadProgress(100);
      
      if (response.document_id) {
        const documentId = response.document_id;
        console.log('Document uploaded successfully with ID:', documentId);
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
        
        console.log('Starting to monitor document processing for:', documentId);
        // Start monitoring processing status
        monitorDocumentProcessing(documentId);
        
        // Clear preview after successful upload
        setSelectedFile(null);
        setFilePreview(null);
        
      } else {
        throw new Error(response.message || 'Upload failed');
      }
      
    } catch (error) {
      console.error('Upload failed:', error);
      let errorMessage = 'Upload failed';
      
      if (error instanceof Error) {
        if (error.message.includes('Unsupported file type')) {
          errorMessage = 'Unsupported file type. Please upload PDF, PNG, JPG, JPEG, TIFF, or BMP files only.';
        } else {
          errorMessage = error.message;
        }
      }
      
      setSnackbarMessage(errorMessage);
      setSnackbarOpen(true);
    } finally {
      setIsUploading(false);
      setUploadProgress(0);
    }
  };

  const monitorDocumentProcessing = async (documentId: string) => {
    console.log('monitorDocumentProcessing called for:', documentId);
    const checkStatus = async () => {
      try {
        console.log('Checking status for document:', documentId);
        const statusResponse = await documentAPI.getDocumentStatus(documentId);
        const status = statusResponse;
        
        setProcessingDocuments(prev => prev.map(doc => {
          if (doc.id === documentId) {
            // Create a mapping from backend stage names to frontend stage names
            const stageMapping: { [key: string]: string } = {
              'preprocessing': 'Preprocessing',
              'ocr_extraction': 'OCR Extraction',
              'llm_processing': 'LLM Processing',
              'validation': 'Validation',
              'routing': 'Routing'
            };
            
            console.log('Backend status:', status);
            console.log('Backend stages:', status.stages);
            
            const updatedDoc = {
              ...doc,
              progress: status.progress,
              stages: doc.stages.map((stage) => {
                // Find the corresponding backend stage by matching the stage name
                const backendStage = status.stages.find((bs: any) => 
                  stageMapping[bs.stage_name] === stage.name
                );
                console.log(`Mapping stage "${stage.name}" to backend stage:`, backendStage);
                return {
                  ...stage,
                  completed: backendStage?.status === 'completed',
                  current: backendStage?.status === 'processing'
                };
              })
            };
            
            // If processing is complete, move to completed documents
            if (status.status === 'completed') {
              setCompletedDocuments(prevCompleted => {
                // Check if document already exists in completed documents
                const exists = prevCompleted.some(doc => doc.id === documentId);
                if (exists) {
                  return prevCompleted; // Don't add duplicate
                }
                
                return [...prevCompleted, {
                  ...updatedDoc,
                  status: 'completed',
                  progress: 100,
                  // Quality score and processing time will be loaded from API when viewing results
                  routingDecision: 'Auto-Approved'
                }];
              });
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
      } catch (error) {
        console.error('Failed to check document status:', error);
      }
    };
    
    checkStatus();
  };

  const handleViewResults = async (document: DocumentItem) => {
    try {
      const response = await documentAPI.getDocumentResults(document.id);
      
      // Check if this is mock data
      const isMockData = response.processing_summary?.is_mock_data === true;
      
      if (isMockData) {
        console.warn('⚠️ Document results contain mock/default data. The document may not have been fully processed or the original file is no longer available.');
      }
      
      // Transform the API response to match frontend expectations
      const transformedResults: DocumentResults = {
        document_id: response.document_id,
        extracted_data: {},
        confidence_scores: {},
        quality_score: response.quality_score?.overall_score || response.processing_summary?.quality_score || 0,
        routing_decision: response.routing_decision?.routing_action || 'unknown',
        processing_stages: response.extraction_results?.map((result: any) => result.stage) || [],
        is_mock_data: isMockData,  // Track if this is mock data
      };
      
      // Update document with actual quality score and processing time from API
      setCompletedDocuments(prevCompleted => 
        prevCompleted.map(doc => 
          doc.id === document.id 
            ? {
                ...doc,
                qualityScore: transformedResults.quality_score,
                processingTime: response.processing_summary?.total_processing_time ? 
                  Math.round(response.processing_summary.total_processing_time / 1000) : undefined
              }
            : doc
        )
      );
      
      // Flatten extraction results into extracted_data and collect models
      const allModels: string[] = [];
      if (response.extraction_results && Array.isArray(response.extraction_results)) {
        response.extraction_results.forEach((result: any) => {
          // Collect model information
          if (result.model_used) {
            allModels.push(result.model_used);
          }
          
          if (result.processed_data) {
            // For LLM processing stage, extract structured_data
            if (result.stage === 'llm_processing' && result.processed_data.structured_data) {
              const structuredData = result.processed_data.structured_data;
              // Extract fields from structured_data
              if (structuredData.extracted_fields) {
                Object.assign(transformedResults.extracted_data, structuredData.extracted_fields);
              }
              // Also store the full structured_data for reference
              transformedResults.extracted_data.structured_data = structuredData;
            } else {
              // For other stages (OCR, etc.), merge processed_data directly
              Object.assign(transformedResults.extracted_data, result.processed_data);
            }
            
            // Map confidence scores to individual fields
            if (result.confidence_score !== undefined) {
              // For each field in processed_data, assign the same confidence score
              Object.keys(result.processed_data).forEach(fieldKey => {
                transformedResults.confidence_scores[fieldKey] = result.confidence_score;
              });
            }
          }
        });
        
        // Store all models used in processing_metadata
        if (allModels.length > 0) {
          transformedResults.extracted_data.processing_metadata = {
            ...transformedResults.extracted_data.processing_metadata,
            models_used: allModels.join(', '),
            model_count: allModels.length,
          };
        }
      }
      
      // Store extraction results for reference
      transformedResults.extracted_data.extraction_results = response.extraction_results;
      
      setDocumentResults(transformedResults);
      setSelectedDocument(document);
      setResultsDialogOpen(true);
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
            input.onchange = async (e) => {
              const file = (e.target as HTMLInputElement).files?.[0];
              if (file) {
                // Validate file type before upload
                const allowedTypes = ['.pdf', '.png', '.jpg', '.jpeg', '.tiff', '.bmp'];
                const fileExtension = '.' + file.name.split('.').pop()?.toLowerCase();
                
                if (!allowedTypes.includes(fileExtension)) {
                  setSnackbarMessage('Unsupported file type. Please upload PDF, PNG, JPG, JPEG, TIFF, or BMP files only.');
                  setSnackbarOpen(true);
                  return;
                }
                
                // Create preview
                try {
                  const preview = await createFilePreview(file);
                  setSelectedFile(file);
                  setFilePreview(preview);
                } catch (error) {
                  console.error('Failed to create preview:', error);
                  setSelectedFile(file);
                  setFilePreview('document');
                }
              }
            };
            input.click();
          }}
        >
          {selectedFile && filePreview ? (
            <Box>
              {filePreview === 'pdf' ? (
                <Box sx={{ mb: 2 }}>
                  <DocumentIcon sx={{ fontSize: 64, color: 'error.main', mb: 1 }} />
                  <Typography variant="h6" gutterBottom>
                    {selectedFile.name}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    PDF Document • {(selectedFile.size / 1024 / 1024).toFixed(2)} MB
                  </Typography>
                </Box>
              ) : filePreview === 'document' ? (
                <Box sx={{ mb: 2 }}>
                  <DocumentIcon sx={{ fontSize: 64, color: 'text.secondary', mb: 1 }} />
                  <Typography variant="h6" gutterBottom>
                    {selectedFile.name}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Document • {(selectedFile.size / 1024 / 1024).toFixed(2)} MB
                  </Typography>
                </Box>
              ) : (
                <Box sx={{ mb: 2 }}>
                  <img 
                    src={filePreview} 
                    alt="Preview" 
                    style={{ 
                      maxWidth: '300px', 
                      maxHeight: '200px', 
                      borderRadius: '8px',
                      border: '1px solid #ddd'
                    }} 
                  />
                  <Typography variant="h6" gutterBottom sx={{ mt: 1 }}>
                    {selectedFile.name}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {(selectedFile.size / 1024 / 1024).toFixed(2)} MB
                  </Typography>
                </Box>
              )}
              
              <Box sx={{ display: 'flex', gap: 2, justifyContent: 'center', mt: 2 }}>
                <Button 
                  variant="contained" 
                  onClick={(e) => {
                    e.stopPropagation();
                    if (selectedFile) {
                      handleDocumentUpload(selectedFile);
                    }
                  }}
                  disabled={isUploading}
                >
                  Upload Document
                </Button>
                <Button 
                  variant="outlined" 
                  onClick={(e) => {
                    e.stopPropagation();
                    setSelectedFile(null);
                    setFilePreview(null);
                  }}
                  disabled={isUploading}
                >
                  Cancel
                </Button>
              </Box>
            </Box>
          ) : (
            <Box>
              <UploadIcon sx={{ fontSize: 48, color: 'text.secondary', mb: 2 }} />
              <Typography variant="h6" gutterBottom>
                {isUploading ? 'Uploading...' : 'Click to Select Document'}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Supported formats: PDF, PNG, JPG, JPEG, TIFF, BMP
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Maximum file size: 50MB
              </Typography>
            </Box>
          )}
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
                  <CheckCircle color="success" sx={{ fontSize: 20 }} />
                ) : stage.current ? (
                  <CircularProgress size={20} color="primary" />
                ) : (
                  <div style={{ 
                    width: 20, 
                    height: 20, 
                    borderRadius: '50%', 
                    backgroundColor: '#e0e0e0',
                    border: '2px solid #ccc'
                  }} />
                )}
              </ListItemIcon>
              <ListItemText 
                primary={
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Typography variant="body2" sx={{ 
                      fontWeight: stage.current ? 'bold' : 'normal',
                      color: stage.completed ? 'success.main' : stage.current ? 'primary.main' : 'text.secondary'
                    }}>
                      {stage.name}
                    </Typography>
                    {stage.current && (
                      <Chip label="Processing" size="small" color="primary" />
                    )}
                    {stage.completed && (
                      <Chip label="Complete" size="small" color="success" />
                    )}
                  </Box>
                }
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
          Quality Score: {document.qualityScore ? `${document.qualityScore}/5.0` : 'N/A'} | 
          Processing Time: {document.processingTime ? `${document.processingTime}s` : 'N/A'}
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
                  <Box sx={{ height: 300 }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart
                        data={analyticsData.trends.quality_trends.map((score, index) => ({
                          day: `Day ${index + 1}`,
                          quality: score,
                        }))}
                        margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
                      >
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis 
                          dataKey="day" 
                          tick={{ fontSize: 12 }}
                        />
                        <YAxis 
                          domain={[0, 5]}
                          tick={{ fontSize: 12 }}
                          label={{ value: 'Quality Score', angle: -90, position: 'insideLeft' }}
                        />
                        <Tooltip 
                          formatter={(value: number) => [`${value.toFixed(2)}/5.0`, 'Quality Score']}
                          labelFormatter={(label) => `${label}`}
                        />
                        <Line 
                          type="monotone" 
                          dataKey="quality" 
                          stroke="#1976d2" 
                          strokeWidth={2}
                          dot={{ fill: '#1976d2', strokeWidth: 2, r: 4 }}
                          activeDot={{ r: 6, stroke: '#1976d2', strokeWidth: 2 }}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </Box>
                ) : (
                  <Box sx={{ height: 200, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <CircularProgress />
                  </Box>
                )}
              </CardContent>
            </Card>
          </Grid>
          
          <Grid item xs={12}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Processing Volume Trends
                </Typography>
                {analyticsData ? (
                  <Box sx={{ height: 300 }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart
                        data={analyticsData.trends.daily_processing.map((count, index) => ({
                          day: `Day ${index + 1}`,
                          documents: count,
                        }))}
                        margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
                      >
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis 
                          dataKey="day" 
                          tick={{ fontSize: 12 }}
                        />
                        <YAxis 
                          tick={{ fontSize: 12 }}
                          label={{ value: 'Documents Processed', angle: -90, position: 'insideLeft' }}
                        />
                        <Tooltip 
                          formatter={(value: number) => [`${value}`, 'Documents']}
                          labelFormatter={(label) => `${label}`}
                        />
                        <Line 
                          type="monotone" 
                          dataKey="documents" 
                          stroke="#4caf50" 
                          strokeWidth={2}
                          dot={{ fill: '#4caf50', strokeWidth: 2, r: 4 }}
                          activeDot={{ r: 6, stroke: '#4caf50', strokeWidth: 2 }}
                        />
                      </LineChart>
                    </ResponsiveContainer>
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
              {/* Mock Data Warning */}
              {documentResults.is_mock_data && (
                <Alert severity="warning" sx={{ mb: 3 }}>
                  <Typography variant="body2">
                    <strong>⚠️ Mock Data Warning:</strong> This document is showing default/mock data because the original file is no longer available or processing results were not stored. 
                    The displayed information may not reflect the actual uploaded document.
                  </Typography>
                </Alert>
              )}
              {/* Document Overview */}
              <Card sx={{ mb: 3, bgcolor: 'primary.50' }}>
                <CardContent>
                  <Typography variant="h6" gutterBottom color="primary">
                    📄 Document Overview
                  </Typography>
                  <Grid container spacing={2}>
                    <Grid item xs={12} sm={6}>
                      <Typography variant="body2" color="text.secondary">
                        <strong>Document Type:</strong> {documentResults.extracted_data?.document_type || 'Unknown'}
                      </Typography>
                    </Grid>
                    <Grid item xs={12} sm={6}>
                      <Typography variant="body2" color="text.secondary">
                        <strong>Total Pages:</strong> {documentResults.extracted_data?.total_pages || 'N/A'}
                      </Typography>
                    </Grid>
                    <Grid item xs={12} sm={6}>
                      <Typography variant="body2" color="text.secondary">
                        <strong>Quality Score:</strong> 
                        <Chip 
                          label={`${documentResults.quality_score}/5.0`} 
                          color={documentResults.quality_score >= 4 ? 'success' : documentResults.quality_score >= 3 ? 'warning' : 'error'}
                          size="small"
                          sx={{ ml: 1 }}
                        />
                      </Typography>
                    </Grid>
                    <Grid item xs={12} sm={6}>
                      <Typography variant="body2" color="text.secondary">
                        <strong>Routing Decision:</strong> 
                        <Chip 
                          label={documentResults.routing_decision} 
                          color={documentResults.routing_decision === 'auto_approve' ? 'success' : documentResults.routing_decision === 'flag_review' ? 'warning' : 'error'}
                          size="small"
                          sx={{ ml: 1 }}
                        />
                      </Typography>
                    </Grid>
                  </Grid>
                </CardContent>
              </Card>

              {/* Show extracted data if available */}
              {documentResults.extracted_data && Object.keys(documentResults.extracted_data).length > 0 ? (
                <>
                  {/* Invoice Details */}
                  {documentResults.extracted_data.document_type === 'invoice' && (() => {
                    // Extract invoice fields from structured_data or directly from extracted_data
                    const structuredData = documentResults.extracted_data.structured_data;
                    const extractedFields = structuredData?.extracted_fields || documentResults.extracted_data.extracted_fields || {};
                    
                    // Helper function to get field value with fallback
                    // Handles both nested structure {field: {value: "...", confidence: 0.9}} and flat structure {field: "..."}
                    const getField = (fieldName: string, altNames: string[] = []) => {
                      const names = [fieldName, ...altNames];
                      for (const name of names) {
                        // Try exact match first
                        let fieldData = extractedFields[name] || 
                                      extractedFields[name.toLowerCase()] || 
                                      extractedFields[name.replace(/_/g, ' ')] ||
                                      extractedFields[name.replace(/\s+/g, '_')];
                        
                        if (fieldData) {
                          // If it's a nested object with 'value' key, extract the value
                          if (typeof fieldData === 'object' && fieldData !== null && 'value' in fieldData) {
                            const value = fieldData.value;
                            if (value && value !== 'N/A' && value !== '') {
                              return value;
                            }
                          }
                          // If it's a string or number directly
                          else if (typeof fieldData === 'string' || typeof fieldData === 'number') {
                            if (fieldData !== 'N/A' && fieldData !== '') {
                              return String(fieldData);
                            }
                          }
                        }
                      }
                      return 'N/A';
                    };
                    
                    return (
                      <Card sx={{ mb: 3 }}>
                        <CardContent>
                          <Typography variant="h6" gutterBottom>
                            💰 Invoice Details
                          </Typography>
                          <Grid container spacing={2}>
                            <Grid item xs={12} sm={6}>
                              <Box sx={{ p: 2, bgcolor: 'grey.50', borderRadius: 1 }}>
                                <Typography variant="subtitle2" color="text.secondary">
                                  Invoice Information
                                </Typography>
                                <Typography variant="body2">
                                  <strong>Invoice Number:</strong> {getField('invoice_number', ['invoiceNumber', 'invoice_no', 'invoice_id'])}
                                </Typography>
                                <Typography variant="body2">
                                  <strong>Order Number:</strong> {getField('order_number', ['orderNumber', 'order_no', 'po_number', 'purchase_order'])}
                                </Typography>
                                <Typography variant="body2">
                                  <strong>Invoice Date:</strong> {getField('invoice_date', ['date', 'invoiceDate', 'issue_date'])}
                                </Typography>
                                <Typography variant="body2">
                                  <strong>Due Date:</strong> {getField('due_date', ['dueDate', 'payment_due_date', 'payment_date'])}
                                </Typography>
                              </Box>
                            </Grid>
                            <Grid item xs={12} sm={6}>
                              <Box sx={{ p: 2, bgcolor: 'grey.50', borderRadius: 1 }}>
                                <Typography variant="subtitle2" color="text.secondary">
                                  Financial Information
                                </Typography>
                                <Typography variant="body2">
                                  <strong>Service:</strong> {getField('service', ['service_description', 'description', 'item_description'])}
                                </Typography>
                                <Typography variant="body2">
                                  <strong>Rate/Price:</strong> {getField('rate', ['price', 'unit_price', 'rate_per_unit'])}
                                </Typography>
                                <Typography variant="body2">
                                  <strong>Sub Total:</strong> {getField('subtotal', ['sub_total', 'subtotal_amount', 'amount_before_tax'])}
                                </Typography>
                                <Typography variant="body2">
                                  <strong>Tax:</strong> {getField('tax', ['tax_amount', 'tax_total', 'vat', 'gst'])}
                                </Typography>
                                <Typography variant="body2" sx={{ fontWeight: 'bold', color: 'primary.main' }}>
                                  <strong>Total:</strong> {getField('total', ['total_amount', 'grand_total', 'amount_due', 'total_due'])}
                                </Typography>
                              </Box>
                            </Grid>
                          </Grid>
                        </CardContent>
                      </Card>
                    );
                  })()}

                  {/* Extracted Text */}
                  {documentResults.extracted_data.extracted_text && (
                    <Card sx={{ mb: 3 }}>
                      <CardContent>
                        <Typography variant="h6" gutterBottom>
                          📝 Extracted Text
                        </Typography>
                        <Box sx={{ 
                          p: 2, 
                          bgcolor: 'grey.50', 
                          borderRadius: 1, 
                          maxHeight: 300, 
                          overflow: 'auto',
                          border: '1px solid',
                          borderColor: 'grey.300'
                        }}>
                          <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', fontFamily: 'monospace' }}>
                            {documentResults.extracted_data.extracted_text}
                          </Typography>
                        </Box>
                        <Box sx={{ mt: 1, display: 'flex', alignItems: 'center' }}>
                          <Typography variant="caption" color="text.secondary">
                            Confidence: 
                          </Typography>
                          <Chip 
                            label={`${Math.round((documentResults.confidence_scores?.extracted_text || 0) * 100)}%`}
                            color={documentResults.confidence_scores?.extracted_text >= 0.8 ? 'success' : documentResults.confidence_scores?.extracted_text >= 0.6 ? 'warning' : 'error'}
                            size="small"
                            sx={{ ml: 1 }}
                          />
                        </Box>
                      </CardContent>
                    </Card>
                  )}

                  {/* Quality Assessment */}
                  {documentResults.extracted_data.quality_assessment && (
                    <Card sx={{ mb: 3 }}>
                      <CardContent>
                        <Typography variant="h6" gutterBottom>
                          🎯 Quality Assessment
                        </Typography>
                        <Grid container spacing={2}>
                          {(() => {
                            try {
                              const qualityData = typeof documentResults.extracted_data.quality_assessment === 'string' 
                                ? JSON.parse(documentResults.extracted_data.quality_assessment)
                                : documentResults.extracted_data.quality_assessment;
                              
                              return Object.entries(qualityData).map(([key, value]) => (
                                <Grid item xs={12} sm={4} key={key}>
                                  <Box sx={{ textAlign: 'center', p: 2, bgcolor: 'grey.50', borderRadius: 1 }}>
                                    <Typography variant="subtitle2" color="text.secondary">
                                      {key.replace(/_/g, ' ').toUpperCase()}
                                    </Typography>
                                    <Typography variant="h6" color="primary">
                                      {Math.round(Number(value) * 100)}%
                                    </Typography>
                                  </Box>
                                </Grid>
                              ));
                            } catch (error) {
                              console.error('Error parsing quality assessment:', error);
                              return (
                                <Grid item xs={12}>
                                  <Typography variant="body2" color="error">
                                    Error displaying quality assessment data
                                  </Typography>
                                </Grid>
                              );
                            }
                          })()}
                        </Grid>
                      </CardContent>
                    </Card>
                  )}

                  {/* Processing Information */}
                  {(() => {
                    // Collect all models from extraction_results
                    const allModels: string[] = [];
                    const processingInfo: Record<string, any> = {};
                    
                    if (documentResults.extracted_data.extraction_results && Array.isArray(documentResults.extracted_data.extraction_results)) {
                      documentResults.extracted_data.extraction_results.forEach((result: any) => {
                        if (result.model_used && !allModels.includes(result.model_used)) {
                          allModels.push(result.model_used);
                        }
                        if (result.stage && result.processing_time_ms) {
                          processingInfo[`${result.stage}_time`] = `${(result.processing_time_ms / 1000).toFixed(2)}s`;
                        }
                      });
                    }
                    
                    // Also check processing_metadata if available
                    let metadata: any = {};
                    if (documentResults.extracted_data.processing_metadata) {
                      try {
                        metadata = typeof documentResults.extracted_data.processing_metadata === 'string' 
                          ? JSON.parse(documentResults.extracted_data.processing_metadata)
                          : documentResults.extracted_data.processing_metadata;
                      } catch (e) {
                        console.error('Error parsing processing metadata:', e);
                      }
                    }
                    
                    // Combine all processing information
                    const combinedInfo = {
                      ...metadata,
                      models_used: allModels.length > 0 ? allModels.join(', ') : metadata.model_used || 'N/A',
                      model_count: allModels.length || 1,
                      timestamp: metadata.timestamp || new Date().toISOString(),
                      multimodal: metadata.multimodal !== undefined ? String(metadata.multimodal) : 'false',
                      ...processingInfo,
                    };
                    
                    if (Object.keys(combinedInfo).length > 0) {
                      return (
                        <Card sx={{ mb: 3 }}>
                          <CardContent>
                            <Typography variant="h6" gutterBottom>
                              ⚙️ Processing Information
                            </Typography>
                            <Grid container spacing={2}>
                              {Object.entries(combinedInfo).map(([key, value]) => (
                                <Grid item xs={12} sm={6} key={key}>
                                  <Typography variant="body2">
                                    <strong>{key.replace(/_/g, ' ').toUpperCase()}:</strong> {String(value)}
                                  </Typography>
                                </Grid>
                              ))}
                            </Grid>
                          </CardContent>
                        </Card>
                      );
                    }
                    return null;
                  })()}

                  {/* Raw Data Table */}
                  <Card sx={{ mb: 3 }}>
                    <CardContent>
                      <Typography variant="h6" gutterBottom>
                        🔍 All Extracted Data
                      </Typography>
                      <TableContainer component={Paper} sx={{ maxHeight: 400 }}>
                        <Table size="small">
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
                                <TableCell>
                                  <Typography variant="body2" sx={{ 
                                    maxWidth: 300, 
                                    overflow: 'hidden', 
                                    textOverflow: 'ellipsis',
                                    whiteSpace: 'nowrap'
                                  }}>
                                    {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                                  </Typography>
                                </TableCell>
                                <TableCell>
                                  <Chip 
                                    label={`${Math.round((documentResults.confidence_scores?.[key] || 0) * 100)}%`}
                                    color={documentResults.confidence_scores?.[key] >= 0.8 ? 'success' : documentResults.confidence_scores?.[key] >= 0.6 ? 'warning' : 'error'}
                                    size="small"
                                  />
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </TableContainer>
                    </CardContent>
                  </Card>
                </>
              ) : (
                <Card sx={{ mb: 3 }}>
                  <CardContent>
                    <Typography variant="h6" gutterBottom color="warning.main">
                      ⚠️ No Extracted Data Available
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      The document processing may not have completed successfully or the data structure is different than expected.
                    </Typography>
                  </CardContent>
                </Card>
              )}

              {/* Processing Stages */}
              <Card sx={{ mb: 3 }}>
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    🔄 Processing Stages
                  </Typography>
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                    {documentResults.processing_stages?.map((stage, index) => (
                      <Chip 
                        key={stage}
                        label={`${index + 1}. ${stage.replace(/_/g, ' ').toUpperCase()}`}
                        color="primary"
                        variant="outlined"
                      />
                    )) || <Typography variant="body2" color="text.secondary">No processing stages available</Typography>}
                  </Box>
                </CardContent>
              </Card>
            </Box>
          ) : (
            <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', p: 4 }}>
              <Typography variant="h6" color="text.secondary" gutterBottom>
                No Results Available
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Document processing may still be in progress or failed to complete.
              </Typography>
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
