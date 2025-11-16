# Changelog

All notable changes to this project will be documented in this file.

## Warehouse Operational Assistant 0.1.0 (16 Nov 2025)

### New Features

- **NVIDIA NeMo Pipeline Integration**: Full 5-stage document processing pipeline
  - Stage 1: Document Preprocessing with NeMo Retriever
  - Stage 2: OCR Extraction with NeMoRetriever-OCR-v1
  - Stage 3: Small LLM Processing with Llama Nemotron Nano VL 8B
  - Stage 4: Large LLM Judge validation with Llama 3.1 Nemotron 70B
  - Stage 5: Intelligent Routing based on quality scores
- **Forecasting Agent**: MCP-enabled forecasting agent with demand prediction, reorder recommendations, and model performance monitoring
- **MCP Forecasting Adapter**: Adapter system for integrating forecasting tools into MCP framework
- **Persistent File Storage**: Document uploads stored in `data/uploads/` directory for re-processing capability
- **Test Scripts**: Comprehensive test scripts for document processing, equipment endpoints, and chat functionality

### Improvements

- **Document Processing**: Removed local processing fallback, now exclusively uses NVIDIA NeMo pipeline
- **Error Handling**: Enhanced error messages indicating NeMo pipeline status (processing, completed, failed)
- **JSON Serialization**: Automatic conversion of PIL Images to metadata for proper storage
- **File Management**: Files preserved after processing for potential re-processing and debugging
- **UI Feedback**: Added mock data warnings in document results dialog
- **Dependency Management**: Added Pillow and PyMuPDF to requirements.txt for document processing
- **Git Configuration**: Updated .gitignore to exclude uploaded files and cache directories
- **NeMo Guardrails**: Enhanced compliance violation detection with additional pattern matching (100% test coverage)

### Bug Fixes

- **File Persistence**: Fixed issue where uploaded files were deleted from temporary directories
- **JSON Serialization Error**: Fixed "Object of type PngImageFile is not JSON serializable" error
- **Mock Data Fallback**: Removed incorrect local processing fallback that returned mock data
- **Document Results**: Fixed issue where document results showed default/mock data instead of actual NeMo pipeline results
- **Missing Dependencies**: Added PyMuPDF (fitz) for PDF processing in local processor
- **Status Tracking**: Improved document status tracking to properly indicate NeMo pipeline progress

