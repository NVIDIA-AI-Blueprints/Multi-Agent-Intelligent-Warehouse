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
import { TabPanel } from '../components/common';

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
  processing_summary?: {
    extracted_fields?: Record<string, any>;
    confidence_scores?: Record<string, number>;
    total_processing_time?: number;
    stages_completed?: string[];
    is_mock_data?: boolean;
  };
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
  const [loadingResults, setLoadingResults] = useState(false);
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
      console.log('Analytics data loaded:', response);
      
      // Ensure trends arrays exist and have data
      if (response && response.trends) {
        // Ensure daily_processing has at least 7 items
        if (!response.trends.daily_processing || response.trends.daily_processing.length === 0) {
          response.trends.daily_processing = [0, 0, 0, 0, 0, 0, 0];
        } else if (response.trends.daily_processing.length < 7) {
          // Pad to 7 items
          while (response.trends.daily_processing.length < 7) {
            response.trends.daily_processing.push(0);
          }
        }
        
        // Ensure quality_trends has at least 7 items
        if (!response.trends.quality_trends || response.trends.quality_trends.length === 0) {
          response.trends.quality_trends = [3.8, 4.0, 4.2, 4.1, 4.3, 4.0, 4.2]; // Sample data for visualization
        } else if (response.trends.quality_trends.length < 7) {
          // Pad to 7 items with average or last value
          const avg = response.trends.quality_trends.reduce((a: number, b: number) => a + b, 0) / response.trends.quality_trends.length || 4.0;
          while (response.trends.quality_trends.length < 7) {
            response.trends.quality_trends.push(avg);
          }
        }
      }
      
      setAnalyticsData(response);
    } catch (error) {
      console.error('Failed to load analytics data:', error);
      // Set default data structure on error so charts can still render
      setAnalyticsData({
        metrics: {
          total_documents: 0,
          processed_today: 0,
          average_quality: 0,
          auto_approved: 0,
          success_rate: 0,
        },
        trends: {
          daily_processing: [0, 0, 0, 0, 0, 0, 0],
          quality_trends: [0, 0, 0, 0, 0, 0, 0],
        },
        summary: 'Failed to load analytics data',
      });
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
        
        setProcessingDocuments(prev => {
          const updated = prev.map(doc => {
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
              
              // Determine which stages are completed and which is current
              const stageStatuses = doc.stages.map((stage) => {
                // Find the corresponding backend stage by matching the stage name
                const backendStage = status.stages?.find((bs: any) => 
                  stageMapping[bs.stage_name] === stage.name
                );
                console.log(`Mapping stage "${stage.name}" to backend stage:`, backendStage);
                return {
                  ...stage,
                  completed: backendStage?.status === 'completed',
                  isProcessing: backendStage?.status === 'processing'
                };
              });

              // Find the first stage that is processing
              const processingIndex = stageStatuses.findIndex(s => s.isProcessing);
              
              // If no stage is processing, find the first incomplete stage (it should be current)
              // Only if there are incomplete stages
              const firstIncompleteIndex = stageStatuses.findIndex(s => !s.completed);
              const currentIndex = processingIndex >= 0 
                ? processingIndex 
                : (firstIncompleteIndex >= 0 ? firstIncompleteIndex : -1);

              // Update stages with proper current/completed flags
              const updatedStages = stageStatuses.map((stage, index) => ({
                ...stage,
                // Mark as current only if it's the current index and not completed
                current: currentIndex >= 0 && index === currentIndex && !stage.completed,
                completed: stage.completed
              }));

              const updatedDoc = {
                ...doc,
                status: status.status || doc.status,  // Update document status
                progress: status.progress || 0,
                stages: updatedStages
              };
              
              console.log(`Updated document ${documentId}: status=${updatedDoc.status}, progress=${updatedDoc.progress}%`);
              
              // If processing is complete, move to completed documents
              if (status.status === 'completed') {
                // Use setTimeout to avoid state update during render
                setTimeout(() => {
                  setCompletedDocuments(prevCompleted => {
                    // Check if document already exists in completed documents
                    const exists = prevCompleted.some(d => d.id === documentId);
                    if (exists) {
                      // Update existing document with latest status
                      return prevCompleted.map(d => 
                        d.id === documentId 
                          ? { ...d, ...updatedDoc, status: 'completed', progress: 100 }
                          : d
                      );
                    }
                    
                    // Add new completed document with all required fields
                    return [...prevCompleted, {
                      ...updatedDoc,
                      id: documentId,
                      filename: updatedDoc.filename || doc.filename || 'Unknown',
                      status: 'completed',
                      progress: 100,
                      routingDecision: 'Auto-Approved',
                      // Preserve stages for display
                      stages: updatedDoc.stages || doc.stages || []
                    }];
                  });
                }, 0);
                return null; // Remove from processing
              }
              
              return updatedDoc;
            }
            return doc;
          });
          
          // Filter out null values (completed documents)
          return updated.filter(doc => doc !== null) as DocumentItem[];
        });
        
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
      // Clear previous results and set selected document first
      setDocumentResults(null);
      setSelectedDocument(document);
      setResultsDialogOpen(true);
      setLoadingResults(true);
      
      // Fetch fresh results for this specific document (add timestamp to prevent caching)
      const response = await documentAPI.getDocumentResults(document.id);
      
      // Check if this is mock data
      const isMockData = response.processing_summary?.is_mock_data === true;
      
      if (isMockData) {
        console.warn('⚠️ Document results contain mock/default data. The document may not have been fully processed or the original file is no longer available.');
      }
      
      // Extract quality_score and routing_decision properly
      let qualityScore = 0;
      if (response.quality_score) {
        if (typeof response.quality_score === 'object') {
          // Handle Pydantic model or plain object
          qualityScore = (response.quality_score as any).overall_score || 
                        (response.quality_score as any).quality_score || 
                        (typeof (response.quality_score as any).overall_score === 'number' ? (response.quality_score as any).overall_score : 0);
        } else if (typeof response.quality_score === 'number') {
          qualityScore = response.quality_score;
        }
      }
      
      // Fallback: Try to extract from validation stage in extraction_results
      if (qualityScore === 0 && response.extraction_results && Array.isArray(response.extraction_results)) {
        const validationStage = response.extraction_results.find((r: any) => r.stage === 'validation');
        if (validationStage && validationStage.processed_data) {
          const processedData = validationStage.processed_data;
          if (processedData.overall_score !== undefined) {
            qualityScore = processedData.overall_score;
          } else if (processedData.quality_score !== undefined) {
            qualityScore = processedData.quality_score;
          }
        }
      }
      
      let routingDecision = 'unknown';
      if (response.routing_decision) {
        if (typeof response.routing_decision === 'object') {
          // Handle Pydantic model or plain object
          const action = (response.routing_decision as any).routing_action;
          if (action) {
            routingDecision = typeof action === 'string' ? action : (action as any).value || String(action);
          }
        } else if (typeof response.routing_decision === 'string') {
          routingDecision = response.routing_decision;
        }
      }
      
      // Fallback: Try to extract from routing stage in extraction_results
      if (routingDecision === 'unknown' && response.extraction_results && Array.isArray(response.extraction_results)) {
        const routingStage = response.extraction_results.find((r: any) => r.stage === 'routing');
        if (routingStage) {
          // Check processed_data first
          if (routingStage.processed_data) {
            const processedData = routingStage.processed_data;
            if (processedData.routing_action) {
              routingDecision = typeof processedData.routing_action === 'string' 
                ? processedData.routing_action 
                : String(processedData.routing_action);
            }
          }
          // Also check raw_data
          if (routingDecision === 'unknown' && routingStage.raw_data) {
            const rawData = routingStage.raw_data;
            if (rawData.routing_action) {
              routingDecision = typeof rawData.routing_action === 'string' 
                ? rawData.routing_action 
                : String(rawData.routing_action);
            }
          }
        }
      }
      
      // Debug logging
      if (routingDecision === 'unknown') {
        console.log('Routing Decision Debug:', {
          response_routing_decision: response.routing_decision,
          extraction_results: response.extraction_results?.map((r: any) => ({ stage: r.stage, has_processed_data: !!r.processed_data })),
        });
      }
      
      // Transform the API response to match frontend expectations
      const transformedResults: DocumentResults = {
        document_id: response.document_id,
        extracted_data: {},
        confidence_scores: {},
        quality_score: qualityScore || response.processing_summary?.quality_score || 0,
        routing_decision: routingDecision || 'unknown',
        processing_stages: response.extraction_results?.map((result: any) => result.stage) || [],
        is_mock_data: isMockData,  // Track if this is mock data
        processing_summary: response.processing_summary || {
          extracted_fields: response.extracted_fields,
          confidence_scores: response.confidence_scores,
          total_processing_time: response.processing_summary?.total_processing_time,
          stages_completed: response.extraction_results?.map((result: any) => result.stage) || [],
          is_mock_data: isMockData,
        },
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
      
      // Use extracted_fields from backend if available (new format from Phase 1)
      // Check both response.extracted_fields and response.processing_summary.extracted_fields
      const extractedFields = response.extracted_fields || response.processing_summary?.extracted_fields;
      const confidenceScores = response.confidence_scores || response.processing_summary?.confidence_scores;
      
      // Debug: Log what we received from backend
      console.log('🔍 Backend Response Debug:', {
        has_extracted_fields: !!extractedFields,
        extracted_fields_keys: extractedFields ? Object.keys(extractedFields) : [],
        extracted_fields_sample: extractedFields ? {
          invoice_number: extractedFields.invoice_number,
          order_number: extractedFields.order_number,
          invoice_date: extractedFields.invoice_date,
        } : null,
        has_processing_summary: !!response.processing_summary,
        processing_summary_extracted_fields: response.processing_summary?.extracted_fields,
        has_confidence_scores: !!confidenceScores,
      });
      
      if (extractedFields && typeof extractedFields === 'object' && Object.keys(extractedFields).length > 0) {
        // Backend already extracted and flattened the fields
        // Handle both flat values and nested {value: "...", confidence: 0.8} structures
        Object.entries(extractedFields).forEach(([key, value]) => {
          if (value && typeof value === 'object' && !Array.isArray(value) && 'value' in value) {
            // Nested structure: extract the value
            transformedResults.extracted_data[key] = (value as any).value;
            if ((value as any).confidence !== undefined) {
              transformedResults.confidence_scores[key] = (value as any).confidence;
            }
          } else {
            // Flat value
            transformedResults.extracted_data[key] = value;
          }
        });
        // Use confidence_scores from backend if available
        if (confidenceScores && typeof confidenceScores === 'object') {
          Object.assign(transformedResults.confidence_scores, confidenceScores);
        }
      } else {
        // Fallback: Flatten extraction results into extracted_data and collect models
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
                // Extract fields from structured_data - handle nested value structure
                if (structuredData.extracted_fields) {
                  Object.entries(structuredData.extracted_fields).forEach(([key, value]: [string, any]) => {
                    if (value && typeof value === 'object' && 'value' in value) {
                      transformedResults.extracted_data[key] = value.value;
                      if (value.confidence !== undefined) {
                        transformedResults.confidence_scores[key] = value.confidence;
                      }
                    } else {
                      transformedResults.extracted_data[key] = value;
                    }
                  });
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
                  if (!transformedResults.confidence_scores[fieldKey]) {
                    transformedResults.confidence_scores[fieldKey] = result.confidence_score;
                  }
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
      }
      
      // Store extraction results for reference
      transformedResults.extracted_data.extraction_results = response.extraction_results;
      
      setDocumentResults(transformedResults);
      setLoadingResults(false);
    } catch (error) {
      console.error('Failed to get document results:', error);
      setLoadingResults(false);
      setSnackbarMessage('Failed to load document results');
      setSnackbarOpen(true);
    }
  };

  const ProcessingPipelineCard = () => (
    <Card
      sx={{
        backgroundColor: '#161B22',
        border: '1px solid #30363D',
        height: '100%',
      }}
    >
      <CardContent>
        <Typography 
          variant="h6" 
          gutterBottom
          sx={{
            fontWeight: 600,
            fontSize: '1.125rem',
            color: '#E6EDF3',
            mb: 2,
          }}
        >
          NVIDIA NeMo Processing Pipeline
        </Typography>
        <List dense>
          {[
            { name: '1. Document Preprocessing', description: 'NeMo Retriever Extraction', color: 'primary' },
            { name: '2. Intelligent OCR', description: 'NeMoRetriever-OCR-v1 + Nemotron Parse', color: 'primary' },
            { name: '3. Small LLM Processing', description: 'Llama Nemotron Nano VL 8B', color: 'primary' },
            { name: '4. Embedding & Indexing', description: 'nv-embedqa-e5-v5', color: 'primary' },
            { name: '5. Large LLM Judge', description: 'Llama 3.3 Nemotron Super 49B', color: 'primary' },
            { name: '6. Intelligent Routing', description: 'Quality-based routing', color: 'primary' },
          ].map((stage, index) => (
            <ListItem key={index} sx={{ py: 0.5 }}>
              <ListItemIcon sx={{ minWidth: 40 }}>
                <Chip 
                  label={stage.name.split('.')[0]} 
                  size="small"
                  sx={{
                    backgroundColor: '#76B900',
                    color: '#000000',
                    fontWeight: 600,
                    fontSize: '0.75rem',
                    minWidth: 32,
                  }}
                />
              </ListItemIcon>
              <ListItemText 
                primary={
                  <Typography
                    variant="body2"
                    sx={{
                      color: '#E6EDF3',
                      fontSize: '0.875rem',
                      fontWeight: 500,
                    }}
                  >
                    {stage.name}
                  </Typography>
                }
                secondary={
                  <Typography
                    variant="body2"
                    sx={{
                      color: '#8B949E',
                      fontSize: '0.8125rem',
                      mt: 0.25,
                    }}
                  >
                    {stage.description}
                  </Typography>
                }
              />
            </ListItem>
          ))}
        </List>
      </CardContent>
    </Card>
  );

  const DocumentUploadCard = () => (
    <Card
      sx={{
        backgroundColor: '#161B22',
        border: '1px solid #30363D',
      }}
    >
      <CardContent>
        <Typography 
          variant="h6" 
          gutterBottom
          sx={{
            fontWeight: 600,
            fontSize: '1.125rem',
            color: '#E6EDF3',
            mb: 2,
          }}
        >
          Upload Documents
        </Typography>
        
        {isUploading && (
          <Box sx={{ mb: 2 }}>
            <Typography 
              variant="body2" 
              sx={{ 
                mb: 1,
                color: '#8B949E',
                fontSize: '0.875rem',
              }}
            >
              Uploading document... {uploadProgress}%
            </Typography>
            <LinearProgress 
              variant="determinate" 
              value={uploadProgress}
              sx={{
                height: 8,
                borderRadius: 4,
                backgroundColor: '#21262D',
                '& .MuiLinearProgress-bar': {
                  backgroundColor: '#76B900',
                },
              }}
            />
          </Box>
        )}
        
        <Box
          sx={{
            border: '2px dashed #30363D',
            borderRadius: 2,
            p: 4,
            textAlign: 'center',
            cursor: isUploading ? 'not-allowed' : 'pointer',
            opacity: isUploading ? 0.6 : 1,
            backgroundColor: '#0D1117',
            transition: 'all 0.2s ease-in-out',
            '&:hover': {
              borderColor: isUploading ? '#30363D' : '#76B900',
              backgroundColor: isUploading ? '#0D1117' : 'rgba(118, 185, 0, 0.05)',
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
                  sx={{
                    backgroundColor: '#76B900',
                    color: '#000000',
                    fontWeight: 500,
                    textTransform: 'none',
                    px: 3,
                    '&:hover': {
                      backgroundColor: '#8FD600',
                    },
                    '&:disabled': {
                      backgroundColor: '#21262D',
                      color: '#8B949E',
                    },
                  }}
                >
                  {isUploading ? 'Uploading...' : 'Upload Document'}
                </Button>
                <Button 
                  variant="outlined" 
                  onClick={(e) => {
                    e.stopPropagation();
                    setSelectedFile(null);
                    setFilePreview(null);
                  }}
                  disabled={isUploading}
                  sx={{
                    borderColor: '#30363D',
                    color: '#E6EDF3',
                    textTransform: 'none',
                    px: 3,
                    '&:hover': {
                      borderColor: '#76B900',
                      backgroundColor: 'rgba(118, 185, 0, 0.1)',
                    },
                    '&:disabled': {
                      borderColor: '#21262D',
                      color: '#8B949E',
                    },
                  }}
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
        
        <Alert 
          severity="info" 
          sx={{ 
            mt: 2,
            backgroundColor: '#161B22',
            border: '1px solid #30363D',
            '& .MuiAlert-icon': {
              color: '#58A6FF',
            },
            '& .MuiAlert-message': {
              color: '#E6EDF3',
            },
          }}
        >
          <Typography variant="body2" sx={{ fontSize: '0.875rem' }}>
            Documents are processed through NVIDIA's NeMo models for intelligent extraction, 
            validation, and routing. Processing typically takes 30-60 seconds.
          </Typography>
        </Alert>
      </CardContent>
    </Card>
  );

  const ProcessingStatusCard = ({ document }: { document: DocumentItem }) => (
    <Card
      sx={{
        backgroundColor: '#161B22',
        border: '1px solid #30363D',
        transition: 'all 0.2s ease-in-out',
        '&:hover': {
          borderColor: '#76B900',
          boxShadow: '0 4px 12px rgba(118, 185, 0, 0.15)',
        },
      }}
    >
      <CardContent>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <Typography 
            variant="h6"
            sx={{
              fontWeight: 600,
              fontSize: '1.125rem',
              color: '#E6EDF3',
            }}
          >
            {document.filename}
          </Typography>
          <Chip 
            label={document.status} 
            size="small"
            sx={{
              backgroundColor: document.status === 'completed' ? '#3FB950' : '#76B900',
              color: '#000000',
              fontWeight: 600,
              fontSize: '0.75rem',
            }}
          />
        </Box>
        
        <LinearProgress 
          variant="determinate" 
          value={document.progress}
          sx={{ 
            mb: 2,
            height: 8,
            borderRadius: 4,
            backgroundColor: '#21262D',
            '& .MuiLinearProgress-bar': {
              backgroundColor: '#76B900',
            },
          }}
        />
        
        <Typography 
          variant="body2" 
          sx={{ 
            mb: 2,
            color: '#8B949E',
            fontSize: '0.875rem',
          }}
        >
          {document.progress}% Complete
        </Typography>
        
        <List dense>
          {document.stages.map((stage, index) => (
            <ListItem key={index}>
              <ListItemIcon>
                {stage.completed ? (
                  <CheckCircle sx={{ fontSize: 20, color: '#3FB950' }} />
                ) : stage.current ? (
                  <CircularProgress size={20} sx={{ color: '#76B900' }} />
                ) : (
                  <Box
                    sx={{
                      width: 20,
                      height: 20,
                      borderRadius: '50%',
                      backgroundColor: '#21262D',
                      border: '2px solid #30363D',
                    }}
                  />
                )}
              </ListItemIcon>
              <ListItemText 
                primary={
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Typography 
                      variant="body2" 
                      sx={{ 
                        fontWeight: stage.current ? 600 : 400,
                        color: stage.completed ? '#3FB950' : stage.current ? '#76B900' : '#8B949E',
                        fontSize: '0.875rem',
                      }}
                    >
                      {stage.name}
                    </Typography>
                    {stage.current && (
                      <Chip 
                        label="Processing" 
                        size="small"
                        sx={{
                          backgroundColor: '#76B900',
                          color: '#000000',
                          fontWeight: 600,
                          fontSize: '0.625rem',
                          height: 20,
                        }}
                      />
                    )}
                    {stage.completed && (
                      <Chip 
                        label="Complete" 
                        size="small"
                        sx={{
                          backgroundColor: '#3FB950',
                          color: '#000000',
                          fontWeight: 600,
                          fontSize: '0.625rem',
                          height: 20,
                        }}
                      />
                    )}
                  </Box>
                }
                secondary={
                  <Typography
                    variant="body2"
                    sx={{
                      color: '#8B949E',
                      fontSize: '0.8125rem',
                      mt: 0.5,
                    }}
                  >
                    {stage.description}
                  </Typography>
                }
              />
            </ListItem>
          ))}
        </List>
      </CardContent>
    </Card>
  );

  const CompletedDocumentCard = ({ document }: { document: DocumentItem }) => {
    const qualityScore = document.qualityScore || 0;
    const qualityPercentage = (qualityScore / 5.0) * 100;
    
    return (
      <Card
        sx={{
          backgroundColor: '#161B22',
          border: '1px solid #30363D',
          transition: 'all 0.2s ease-in-out',
          '&:hover': {
            borderColor: '#76B900',
            boxShadow: '0 4px 12px rgba(118, 185, 0, 0.15)',
          },
        }}
      >
        <CardContent>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
            <Typography 
              variant="h6"
              sx={{
                fontWeight: 600,
                fontSize: '1.125rem',
                color: '#E6EDF3',
              }}
            >
              {document.filename}
            </Typography>
            <Box sx={{ display: 'flex', gap: 1 }}>
              <Chip 
                label="Completed" 
                size="small"
                sx={{
                  backgroundColor: '#3FB950',
                  color: '#000000',
                  fontWeight: 600,
                  fontSize: '0.75rem',
                }}
              />
              <Chip 
                label={document.routingDecision || "Auto-Approved"} 
                size="small"
                sx={{
                  backgroundColor: '#76B900',
                  color: '#000000',
                  fontWeight: 600,
                  fontSize: '0.75rem',
                }}
              />
            </Box>
          </Box>
          
          <Box sx={{ mb: 2 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 1 }}>
              <Typography 
                variant="body2" 
                sx={{ 
                  color: '#8B949E',
                  fontSize: '0.875rem',
                }}
              >
                Quality Score:
              </Typography>
              <Box
                sx={{
                  position: 'relative',
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: 56,
                  height: 56,
                }}
              >
                <CircularProgress
                  variant="determinate"
                  value={qualityPercentage}
                  size={56}
                  thickness={4}
                  sx={{
                    color: qualityPercentage >= 80 ? '#3FB950' : qualityPercentage >= 60 ? '#76B900' : '#D29922',
                    position: 'absolute',
                  }}
                />
                <Box
                  sx={{
                    top: 0,
                    left: 0,
                    bottom: 0,
                    right: 0,
                    position: 'absolute',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  <Typography
                    variant="caption"
                    component="div"
                    sx={{
                      fontWeight: 600,
                      fontSize: '0.75rem',
                      color: '#E6EDF3',
                    }}
                  >
                    {qualityPercentage.toFixed(0)}%
                  </Typography>
                </Box>
              </Box>
              <Typography 
                variant="body2" 
                sx={{ 
                  color: '#8B949E',
                  fontSize: '0.875rem',
                }}
              >
                {document.qualityScore ? `${document.qualityScore}/5.0` : 'N/A'}
              </Typography>
            </Box>
            <Typography 
              variant="body2" 
              sx={{ 
                color: '#8B949E',
                fontSize: '0.875rem',
              }}
            >
              Processing Time: {document.processingTime ? `${document.processingTime}s` : 'N/A'}
            </Typography>
          </Box>
          
          <Box sx={{ display: 'flex', gap: 1 }}>
            <Button 
              size="small" 
              startIcon={<ViewIcon />}
              onClick={() => handleViewResults(document)}
              variant="contained"
              sx={{
                backgroundColor: '#76B900',
                color: '#000000',
                fontWeight: 500,
                textTransform: 'none',
                '&:hover': {
                  backgroundColor: '#8FD600',
                },
              }}
            >
              View Results
            </Button>
            <Button 
              size="small" 
              startIcon={<DownloadIcon />}
              variant="outlined"
              sx={{
                borderColor: '#30363D',
                color: '#E6EDF3',
                textTransform: 'none',
                '&:hover': {
                  borderColor: '#76B900',
                  backgroundColor: 'rgba(118, 185, 0, 0.1)',
                },
              }}
            >
              Download
            </Button>
          </Box>
        </CardContent>
      </Card>
    );
  };

  return (
    <Box sx={{ p: 0 }}>
      <Box sx={{ mb: 4 }}>
        <Typography 
          variant="h4" 
          gutterBottom
          sx={{
            fontWeight: 600,
            fontSize: '2rem',
            color: '#E6EDF3',
            mb: 1,
          }}
        >
          Document Extraction & Processing
        </Typography>
        <Typography 
          variant="body1" 
          sx={{ 
            mb: 3,
            color: '#8B949E',
            fontSize: '0.9375rem',
          }}
        >
          Upload warehouse documents for intelligent extraction and processing using NVIDIA NeMo models
        </Typography>
      </Box>

      <Box sx={{ borderBottom: '1px solid #30363D', mb: 3 }}>
        <Tabs 
          value={activeTab} 
          onChange={handleTabChange} 
          aria-label="document processing tabs"
          sx={{
            '& .MuiTab-root': {
              color: '#8B949E',
              textTransform: 'none',
              fontWeight: 500,
              fontSize: '0.9375rem',
              minHeight: 48,
              '&.Mui-selected': {
                color: '#76B900',
              },
            },
            '& .MuiTabs-indicator': {
              backgroundColor: '#76B900',
            },
          }}
        >
          <Tab label="Upload Documents" icon={<UploadIcon />} iconPosition="start" />
          <Tab label="Processing Status" icon={<SearchIcon />} iconPosition="start" />
          <Tab label="Completed Documents" icon={<ApprovedIcon />} iconPosition="start" />
          <Tab label="Analytics" icon={<AnalyticsIcon />} iconPosition="start" />
        </Tabs>
      </Box>

      <TabPanel value={activeTab} index={0} idPrefix="document">
        <Grid container spacing={3}>
          <Grid item xs={12} md={8}>
            <DocumentUploadCard />
          </Grid>
          
          <Grid item xs={12} md={4}>
            <ProcessingPipelineCard />
          </Grid>
        </Grid>
      </TabPanel>

      <TabPanel value={activeTab} index={1} idPrefix="document">
        <Grid container spacing={3}>
          {processingDocuments.length === 0 ? (
            <Grid item xs={12}>
              <Paper 
                sx={{ 
                  p: 4, 
                  textAlign: 'center',
                  backgroundColor: '#161B22',
                  border: '1px solid #30363D',
                }}
              >
                <Typography 
                  variant="h6" 
                  sx={{
                    color: '#8B949E',
                    fontWeight: 500,
                    mb: 1,
                  }}
                >
                  No documents currently processing
                </Typography>
                <Typography 
                  variant="body2" 
                  sx={{
                    color: '#8B949E',
                    fontSize: '0.875rem',
                  }}
                >
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

      <TabPanel value={activeTab} index={2} idPrefix="document">
        <Grid container spacing={3}>
          {completedDocuments.length === 0 ? (
            <Grid item xs={12}>
              <Paper 
                sx={{ 
                  p: 4, 
                  textAlign: 'center',
                  backgroundColor: '#161B22',
                  border: '1px solid #30363D',
                }}
              >
                <Typography 
                  variant="h6" 
                  sx={{
                    color: '#8B949E',
                    fontWeight: 500,
                    mb: 1,
                  }}
                >
                  No completed documents
                </Typography>
                <Typography 
                  variant="body2" 
                  sx={{
                    color: '#8B949E',
                    fontSize: '0.875rem',
                  }}
                >
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

      <TabPanel value={activeTab} index={3} idPrefix="document">
        <Grid container spacing={3}>
          <Grid item xs={12} md={4}>
            <Card
              sx={{
                backgroundColor: '#161B22',
                border: '1px solid #30363D',
              }}
            >
              <CardContent>
                <Typography 
                  variant="h6" 
                  gutterBottom
                  sx={{
                    fontWeight: 600,
                    fontSize: '1.125rem',
                    color: '#E6EDF3',
                    mb: 2,
                  }}
                >
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
            <Card
              sx={{
                backgroundColor: '#161B22',
                border: '1px solid #30363D',
              }}
            >
              <CardContent>
                <Typography 
                  variant="h6" 
                  gutterBottom
                  sx={{
                    fontWeight: 600,
                    fontSize: '1.125rem',
                    color: '#E6EDF3',
                    mb: 2,
                  }}
                >
                  Quality Score Trends
                </Typography>
                {analyticsData && analyticsData.trends && analyticsData.trends.quality_trends ? (
                  analyticsData.trends.quality_trends.length > 0 ? (
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
                    <Box sx={{ height: 200, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 2 }}>
                      <Typography variant="body2" color="text.secondary">
                        No quality score data available yet
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        Process documents to see quality trends
                      </Typography>
                    </Box>
                  )
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
                {analyticsData && analyticsData.trends && analyticsData.trends.daily_processing ? (
                  analyticsData.trends.daily_processing.length > 0 ? (
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
                            stroke="#76B900" 
                            strokeWidth={2}
                            dot={{ fill: '#76B900', strokeWidth: 2, r: 4 }}
                            activeDot={{ r: 6, stroke: '#76B900', strokeWidth: 2 }}
                          />
                        </LineChart>
                      </ResponsiveContainer>
                    </Box>
                  ) : (
                    <Box sx={{ height: 200, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 2 }}>
                      <Typography variant="body2" color="text.secondary">
                        No processing volume data available yet
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        Process documents to see volume trends
                      </Typography>
                    </Box>
                  )
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
        PaperProps={{
          sx: {
            backgroundColor: '#161B22',
            border: '1px solid #30363D',
          },
        }}
      >
        <DialogTitle
          sx={{
            backgroundColor: '#161B22',
            borderBottom: '1px solid #30363D',
            pb: 2,
          }}
        >
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Typography 
              variant="h6"
              sx={{
                fontWeight: 600,
                fontSize: '1.25rem',
                color: '#E6EDF3',
              }}
            >
              Document Results - {selectedDocument?.filename}
            </Typography>
            <Button
              onClick={() => setResultsDialogOpen(false)}
              startIcon={<CloseIcon />}
              sx={{
                color: '#8B949E',
                textTransform: 'none',
                '&:hover': {
                  backgroundColor: '#21262D',
                  color: '#E6EDF3',
                },
              }}
            >
              Close
            </Button>
          </Box>
        </DialogTitle>
        <DialogContent
          sx={{
            backgroundColor: '#0D1117',
            pt: 3,
          }}
        >
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
                      <Typography 
                        variant="body2"
                        sx={{
                          color: '#8B949E',
                          fontSize: '0.875rem',
                        }}
                      >
                        <strong style={{ color: '#E6EDF3' }}>Quality Score:</strong>{' '}
                        <Chip 
                          label={`${documentResults.quality_score}/5.0`}
                          size="small"
                          sx={{ 
                            ml: 1,
                            backgroundColor: documentResults.quality_score >= 4 ? '#3FB950' : documentResults.quality_score >= 3 ? '#76B900' : '#D29922',
                            color: '#000000',
                            fontWeight: 600,
                            fontSize: '0.75rem',
                          }}
                        />
                      </Typography>
                    </Grid>
                    <Grid item xs={12} sm={6}>
                      <Typography 
                        variant="body2"
                        sx={{
                          color: '#8B949E',
                          fontSize: '0.875rem',
                        }}
                      >
                        <strong style={{ color: '#E6EDF3' }}>Routing Decision:</strong>{' '}
                        <Chip 
                          label={documentResults.routing_decision}
                          size="small"
                          sx={{ 
                            ml: 1,
                            backgroundColor: documentResults.routing_decision === 'auto_approve' ? '#3FB950' : documentResults.routing_decision === 'flag_review' ? '#76B900' : '#F85149',
                            color: '#000000',
                            fontWeight: 600,
                            fontSize: '0.75rem',
                          }}
                        />
                      </Typography>
                    </Grid>
                  </Grid>
                </CardContent>
              </Card>

              {/* Show loading state */}
              {loadingResults ? (
                <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '200px' }}>
                  <CircularProgress />
                  <Typography variant="body2" sx={{ ml: 2 }}>Loading document results...</Typography>
                </Box>
              ) : documentResults && documentResults.extracted_data && Object.keys(documentResults.extracted_data).length > 0 ? (
                <>
                  {/* Extracted Text */}
                  {(documentResults.extracted_data.extracted_text || documentResults.extracted_data.text) && (
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
                            {documentResults.extracted_data.extracted_text || documentResults.extracted_data.text}
                          </Typography>
                        </Box>
                        <Box sx={{ mt: 1, display: 'flex', alignItems: 'center' }}>
                          <Typography variant="caption" color="text.secondary">
                            Confidence: 
                          </Typography>
                          <Chip 
                            label={`${Math.round((documentResults.confidence_scores?.extracted_text || documentResults.confidence_scores?.text || 0) * 100)}%`}
                            color={(documentResults.confidence_scores?.extracted_text || documentResults.confidence_scores?.text || 0) >= 0.8 ? 'success' : (documentResults.confidence_scores?.extracted_text || documentResults.confidence_scores?.text || 0) >= 0.6 ? 'warning' : 'error'}
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
                    
                    // Also check quality_score for judge_model
                    if (documentResults.extracted_data.quality_score && documentResults.extracted_data.quality_score.judge_model) {
                      const judgeModel = documentResults.extracted_data.quality_score.judge_model;
                      if (!allModels.includes(judgeModel)) {
                        allModels.push(judgeModel);
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
                                  <Typography 
                                    variant="body2"
                                    sx={{
                                      fontSize: '0.875rem',
                                    }}
                                  >
                                    <strong style={{ color: '#E6EDF3' }}>
                                      {key.replace(/_/g, ' ').toUpperCase()}:
                                    </strong>{' '}
                                    <span style={{ color: '#8B949E' }}>{String(value)}</span>
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

                  {/* Raw Data Table - Filtered to show only relevant extracted fields */}
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
                            {(() => {
                              // Filter out internal processing fields
                              const internalFields = [
                                'extraction_results',
                                'processing_metadata',
                                'quality_assessment',
                                'quality_score',
                                'routing_decision',
                                'images',
                                'processed_pages',
                                'page_results',
                                'words',
                                'elements',
                                'layout_enhanced',
                                'processing_timestamp',
                                'ocr_text',
                                'multimodal_processed',
                                'raw_entities',
                                'raw_response',
                                'judge_evaluation',
                                'metadata',
                              ];
                              
                              // Get structured fields from llm_processing if available
                              const structuredData = documentResults.extracted_data.structured_data;
                              const extractedFields = structuredData?.extracted_fields || documentResults.extracted_data.extracted_fields || {};
                              
                              // Combine all relevant fields
                              const relevantFields: Record<string, any> = {};
                              
                              // Add extracted fields from structured_data - these are the most important
                              Object.entries(extractedFields).forEach(([key, value]) => {
                                if (value && typeof value === 'object' && value !== null && !Array.isArray(value)) {
                                  // Handle nested structure: {value: "...", confidence: 0.8, source: "ocr"}
                                  if ('value' in value) {
                                    const valueObj = value as { value: any; confidence?: number };
                                    relevantFields[key] = valueObj.value;
                                    // Store confidence if available
                                    if (valueObj.confidence !== undefined && !documentResults.confidence_scores[key]) {
                                      documentResults.confidence_scores[key] = valueObj.confidence;
                                    }
                                  } else {
                                    // If it's an object but no 'value' key, use the whole object
                                    relevantFields[key] = value;
                                  }
                                } else if (value !== null && value !== undefined && value !== '') {
                                  relevantFields[key] = value;
                                }
                              });
                              
                              // Add other relevant fields (excluding internal ones) - but prioritize extracted_fields
                              Object.entries(documentResults.extracted_data).forEach(([key, value]) => {
                                // Skip if already in relevantFields (from extracted_fields)
                                if (relevantFields[key] !== undefined) {
                                  return;
                                }
                                
                                if (!internalFields.includes(key) && 
                                    key !== 'structured_data' && 
                                    key !== 'extracted_fields' &&
                                    value !== null && 
                                    value !== undefined &&
                                    value !== '') {
                                  // Skip if it's a complex object that's already handled
                                  if (typeof value === 'object' && !Array.isArray(value) && Object.keys(value).length > 10) {
                                    return; // Skip large nested objects
                                  }
                                  // Only add simple fields or arrays
                                  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean' || Array.isArray(value)) {
                                    relevantFields[key] = value;
                                  }
                                }
                              });
                              
                              // Sort fields for better display
                              const sortedFields = Object.entries(relevantFields).sort(([a], [b]) => {
                                // Put invoice-related fields first
                                const invoiceFields = ['invoice_number', 'order_number', 'invoice_date', 'due_date', 'total', 'subtotal', 'tax', 'service', 'rate'];
                                const aIndex = invoiceFields.indexOf(a);
                                const bIndex = invoiceFields.indexOf(b);
                                if (aIndex !== -1 && bIndex !== -1) return aIndex - bIndex;
                                if (aIndex !== -1) return -1;
                                if (bIndex !== -1) return 1;
                                return a.localeCompare(b);
                              });
                              
                              if (sortedFields.length === 0) {
                                return (
                                  <TableRow>
                                    <TableCell colSpan={3} align="center">
                                      <Typography variant="body2" color="text.secondary">
                                        No extracted fields available. The document may still be processing.
                                      </Typography>
                                    </TableCell>
                                  </TableRow>
                                );
                              }
                              
                              return sortedFields.map(([key, value]) => {
                                // Format value for display
                                let displayValue: string;
                                if (typeof value === 'object' && value !== null) {
                                  if (Array.isArray(value)) {
                                    displayValue = value.length > 0 ? `[${value.length} items]` : '[]';
                                  } else if ('value' in value && typeof value.value !== 'object') {
                                    displayValue = String(value.value);
                                  } else {
                                    displayValue = JSON.stringify(value).substring(0, 200);
                                    if (JSON.stringify(value).length > 200) displayValue += '...';
                                  }
                                } else {
                                  displayValue = String(value);
                                }
                                
                                // Get confidence score
                                const confidence = documentResults.confidence_scores?.[key] || 
                                                 (typeof value === 'object' && value !== null && 'confidence' in value ? value.confidence : 0);
                                
                                return (
                                  <TableRow key={key}>
                                    <TableCell>
                                      <Typography variant="body2" sx={{ fontWeight: 500 }}>
                                        {key.replace(/_/g, ' ').toUpperCase()}
                                      </Typography>
                                    </TableCell>
                                    <TableCell>
                                      <Typography 
                                        variant="body2" 
                                        sx={{ 
                                          maxWidth: 400, 
                                          overflow: 'hidden', 
                                          textOverflow: 'ellipsis',
                                          whiteSpace: 'nowrap',
                                          fontFamily: displayValue.length > 50 ? 'monospace' : 'inherit',
                                          fontSize: displayValue.length > 50 ? '0.75rem' : '0.875rem',
                                        }}
                                        title={displayValue}
                                      >
                                        {displayValue}
                                      </Typography>
                                    </TableCell>
                                    <TableCell>
                                      <Chip 
                                        label={`${Math.round(confidence * 100)}%`}
                                        color={confidence >= 0.8 ? 'success' : confidence >= 0.6 ? 'warning' : 'error'}
                                        size="small"
                                      />
                                    </TableCell>
                                  </TableRow>
                                );
                              });
                            })()}
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
