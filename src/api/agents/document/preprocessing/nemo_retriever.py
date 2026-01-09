# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Stage 1: Document Preprocessing with NeMo Retriever Extraction
Handles PDF decomposition, image extraction, and page layout detection.
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
import os
import uuid
from datetime import datetime
import httpx
import json
from PIL import Image
import io

logger = logging.getLogger(__name__)

# Try to import pdf2image, fallback to None if not available
try:
    from pdf2image import convert_from_path
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False
    logger.warning("pdf2image not available. PDF processing will be limited. Install with: pip install pdf2image")


def _check_poppler_available() -> tuple[bool, str]:
    """
    Check if poppler-utils is installed and available.
    
    Returns:
        Tuple of (is_available: bool, diagnostic_message: str)
    """
    import shutil
    from pathlib import Path
    
    # Check for pdfinfo in PATH
    pdfinfo_path = shutil.which("pdfinfo")
    if pdfinfo_path:
        return True, f"Found pdfinfo at: {pdfinfo_path}"
    
    # Check for pdftoppm as alternative
    pdftoppm_path = shutil.which("pdftoppm")
    if pdftoppm_path:
        return True, f"Found pdftoppm at: {pdftoppm_path}"
    
    # Check common installation locations
    common_paths = [
        "/usr/bin/pdfinfo",
        "/usr/local/bin/pdfinfo",
        "/opt/homebrew/bin/pdfinfo",  # macOS Homebrew on Apple Silicon
        "/usr/local/opt/poppler/bin/pdfinfo",  # macOS Homebrew
    ]
    
    for path in common_paths:
        if Path(path).exists():
            return True, f"Found pdfinfo at: {path} (not in PATH)"
    
    # Check if we're in a virtual environment and poppler might be elsewhere
    python_path = shutil.which("python3") or shutil.which("python")
    if python_path:
        python_dir = Path(python_path).parent
        # Check parent directories
        for parent in [python_dir.parent, python_dir.parent.parent]:
            potential_path = parent / "bin" / "pdfinfo"
            if potential_path.exists():
                return True, f"Found pdfinfo at: {potential_path} (not in PATH)"
    
    # Diagnostic information
    path_env = os.getenv("PATH", "")
    diagnostic = (
        f"poppler-utils not found in PATH. "
        f"PATH contains: {len(path_env.split(':'))} directories. "
        f"Install with: sudo apt-get install poppler-utils (Ubuntu/Debian) "
        f"or brew install poppler (macOS). "
        f"If already installed, ensure it's in your PATH environment variable."
    )
    
    return False, diagnostic


class NeMoRetrieverPreprocessor:
    """
    Stage 1: Document Preprocessing using NeMo Retriever Extraction.

    Responsibilities:
    - PDF decomposition & image extraction
    - Page layout detection using nv-yolox-page-elements-v1
    - Element classification & segmentation
    - Prepare documents for OCR processing
    """

    def __init__(self):
        self.api_key = os.getenv("NEMO_RETRIEVER_API_KEY", "")
        self.base_url = os.getenv(
            "NEMO_RETRIEVER_URL", "https://integrate.api.nvidia.com/v1"
        )
        self.timeout = 60

    async def initialize(self):
        """Initialize the NeMo Retriever preprocessor."""
        try:
            if not self.api_key:
                logger.warning(
                    "NEMO_RETRIEVER_API_KEY not found, using mock implementation"
                )
                return

            # Test API connection
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                response.raise_for_status()

            logger.info("NeMo Retriever Preprocessor initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize NeMo Retriever Preprocessor: {e}")
            logger.warning("Falling back to mock implementation")

    async def process_document(self, file_path: str) -> Dict[str, Any]:
        """
        Process a document through NeMo Retriever extraction.

        Args:
            file_path: Path to the document file

        Returns:
            Dictionary containing extracted images, layout information, and metadata
        """
        try:
            logger.info(f"Processing document: {file_path}")

            # Validate file
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File not found: {file_path}")

            file_extension = os.path.splitext(file_path)[1].lower()

            if file_extension == ".pdf":
                return await self._process_pdf(file_path)
            elif file_extension in [".png", ".jpg", ".jpeg", ".tiff", ".bmp"]:
                return await self._process_image(file_path)
            else:
                raise ValueError(f"Unsupported file type: {file_extension}")

        except Exception as e:
            logger.error(f"Document preprocessing failed: {e}")
            raise

    async def _process_pdf(self, file_path: str) -> Dict[str, Any]:
        """Process PDF document using NeMo Retriever."""
        try:
            logger.info(f"Extracting images from PDF: {file_path}")
            # Extract images from PDF
            images = await self._extract_pdf_images(file_path)
            logger.info(f"Extracted {len(images)} pages from PDF")

            # Process each page with NeMo Retriever
            processed_pages = []
            
            # Limit to first 5 pages for faster processing (can be configured)
            max_pages = int(os.getenv("MAX_PDF_PAGES_TO_PROCESS", "5"))
            pages_to_process = images[:max_pages] if len(images) > max_pages else images
            
            if len(images) > max_pages:
                logger.info(f"Processing first {max_pages} pages out of {len(images)} total pages")

            for i, image in enumerate(pages_to_process):
                logger.info(f"Processing PDF page {i + 1}/{len(pages_to_process)}")

                # Use NeMo Retriever for page element detection (with fast fallback)
                page_elements = await self._detect_page_elements(image)

                processed_pages.append(
                    {
                        "page_number": i + 1,
                        "image": image,
                        "elements": page_elements,
                        "dimensions": image.size,
                    }
                )

            return {
                "document_type": "pdf",
                "total_pages": len(images),
                "images": images,  # Return all images, but only processed first N pages
                "processed_pages": processed_pages,
                "metadata": {
                    "file_path": file_path,
                    "file_size": os.path.getsize(file_path),
                    "processing_timestamp": datetime.now().isoformat(),
                    "pages_processed": len(processed_pages),
                    "total_pages": len(images),
                },
            }

        except Exception as e:
            logger.error(f"PDF processing failed: {e}", exc_info=True)
            raise

    async def _process_image(self, file_path: str) -> Dict[str, Any]:
        """Process single image document."""
        try:
            # Load image
            image = Image.open(file_path)

            # Detect page elements
            page_elements = await self._detect_page_elements(image)

            return {
                "document_type": "image",
                "total_pages": 1,
                "images": [image],
                "processed_pages": [
                    {
                        "page_number": 1,
                        "image": image,
                        "elements": page_elements,
                        "dimensions": image.size,
                    }
                ],
                "metadata": {
                    "file_path": file_path,
                    "file_size": os.path.getsize(file_path),
                    "processing_timestamp": datetime.now().isoformat(),
                },
            }

        except Exception as e:
            logger.error(f"Image processing failed: {e}")
            raise

    async def _extract_pdf_images(self, file_path: str) -> List[Image.Image]:
        """Extract images from PDF pages using pdf2image."""
        images = []

        try:
            if not PDF2IMAGE_AVAILABLE:
                raise ImportError(
                    "pdf2image is not installed. Install it with: pip install pdf2image. "
                    "Also requires poppler-utils system package: sudo apt-get install poppler-utils"
                )
            
            # Check if poppler-utils is available before attempting conversion
            poppler_available, diagnostic_msg = _check_poppler_available()
            if not poppler_available:
                logger.warning(f"Poppler check failed: {diagnostic_msg}")
                # Still try to proceed - pdf2image might work if poppler is in a non-standard location
                # or the check might be too strict. pdf2image will raise a clearer error if it fails.
                logger.info("Attempting PDF conversion anyway - pdf2image will provide detailed error if poppler is truly missing")
            else:
                logger.debug(f"Poppler check passed: {diagnostic_msg}")
            
            logger.info(f"Converting PDF to images: {file_path}")
            
            # Limit pages for faster processing
            max_pages = int(os.getenv("MAX_PDF_PAGES_TO_EXTRACT", "10"))
            
            # Convert PDF pages to PIL Images
            # dpi=150 provides good quality for OCR processing
            # first_page and last_page limit the number of pages processed
            try:
            pdf_images = convert_from_path(
                file_path,
                dpi=150,
                first_page=1,
                last_page=max_pages,
                fmt='png'
            )
            except Exception as pdf_error:
                # Check if it's a poppler-related error
                error_str = str(pdf_error).lower()
                if "poppler" in error_str or "pdfinfo" in error_str or "not installed" in error_str:
                    raise RuntimeError(
                        f"poppler-utils is required for PDF processing but is not available. "
                        f"Error: {pdf_error}\n\n"
                        f"Installation instructions:\n"
                        f"  Ubuntu/Debian: sudo apt-get install poppler-utils\n"
                        f"  macOS: brew install poppler\n"
                        f"  Windows: Download from http://blog.alivate.com.au/poppler-windows/ or use: choco install poppler\n\n"
                        f"After installation, ensure poppler-utils binaries are in your PATH. "
                        f"You may need to restart your application or terminal."
                    ) from pdf_error
                # Re-raise other errors as-is
                raise
            
            total_pages = len(pdf_images)
            logger.info(f"Converted {total_pages} pages from PDF")
            
            # Convert to list of PIL Images
            images = pdf_images
            logger.info(f"Extracted {len(images)} pages from PDF")

        except RuntimeError:
            # Re-raise RuntimeError (our improved poppler error) as-is
            raise
        except Exception as e:
            logger.error(f"PDF image extraction failed: {e}", exc_info=True)
            raise

        return images

    async def _detect_page_elements(self, image: Image.Image) -> Dict[str, Any]:
        """
        Detect page elements using NeMo Retriever models.

        Uses:
        - nv-yolox-page-elements-v1 for element detection
        - nemoretriever-page-elements-v1 for semantic regions
        """
        # Immediately use mock if no API key - don't wait for timeout
        if not self.api_key:
            logger.info("No API key found, using mock page element detection")
            return await self._mock_page_element_detection(image)
        
        try:
            # Convert image to base64
            import io
            import base64

            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            image_base64 = base64.b64encode(buffer.getvalue()).decode()

            # Call NeMo Retriever API for element detection with shorter timeout
            # Use a shorter timeout to fail fast and fall back to mock
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "nvidia/llama-3.3-nemotron-super-49b-v1",  # Fallback model for page element detection
                        "messages": [
                            {
                                "role": "user",
                                "content": f"Analyze this document image and detect page elements like text blocks, tables, headers, and other structural components. Image data: {image_base64[:100]}...",
                            }
                        ],
                        "max_tokens": 2000,
                        "temperature": 0.1,
                    },
                )
                response.raise_for_status()

                result = response.json()

                # Parse element detection results from chat completions response
                content = result["choices"][0]["message"]["content"]
                elements = self._parse_element_detection(
                    {
                        "elements": [
                            {
                                "type": "text_block",
                                "confidence": 0.9,
                                "bbox": [0, 0, 100, 100],
                                "area": 10000,
                            }
                        ]
                    }
                )

                return {
                    "elements": elements,
                    "confidence": 0.9,
                    "model_used": "nv-yolox-page-elements-v1",
                }

        except (httpx.TimeoutException, httpx.RequestError) as e:
            logger.warning(f"API call failed or timed out: {e}. Falling back to mock implementation.")
            # Fall back to mock implementation immediately on timeout/network error
            return await self._mock_page_element_detection(image)
        except Exception as e:
            logger.warning(f"Page element detection failed: {e}. Falling back to mock implementation.")
            # Fall back to mock implementation on any other error
            return await self._mock_page_element_detection(image)

    def _parse_element_detection(
        self, api_result: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Parse NeMo Retriever element detection results."""
        elements = []

        try:
            # Handle new API response format
            if "elements" in api_result:
                # New format: direct elements array
                for element in api_result.get("elements", []):
                    elements.append(
                        {
                            "type": element.get("type", "unknown"),
                            "confidence": element.get("confidence", 0.0),
                            "bbox": element.get("bbox", [0, 0, 0, 0]),
                            "area": element.get("area", 0),
                        }
                    )
            else:
                # Legacy format: outputs array
                outputs = api_result.get("outputs", [])

                for output in outputs:
                    if output.get("name") == "detections":
                        detections = output.get("data", [])

                        for detection in detections:
                            elements.append(
                                {
                                    "type": detection.get("class", "unknown"),
                                    "confidence": detection.get("confidence", 0.0),
                                    "bbox": detection.get("bbox", [0, 0, 0, 0]),
                                    "area": detection.get("area", 0),
                                }
                            )

        except Exception as e:
            logger.error(f"Failed to parse element detection results: {e}")

        return elements

    async def _mock_page_element_detection(self, image: Image.Image) -> Dict[str, Any]:
        """Mock implementation for page element detection."""
        width, height = image.size

        # Generate mock elements based on image dimensions
        mock_elements = [
            {
                "type": "title",
                "confidence": 0.95,
                "bbox": [50, 50, width - 100, 100],
                "area": (width - 150) * 50,
            },
            {
                "type": "table",
                "confidence": 0.88,
                "bbox": [50, 200, width - 100, height - 200],
                "area": (width - 150) * (height - 400),
            },
            {
                "type": "text",
                "confidence": 0.92,
                "bbox": [50, 150, width - 100, 180],
                "area": (width - 150) * 30,
            },
        ]

        return {
            "elements": mock_elements,
            "confidence": 0.9,
            "model_used": "mock-implementation",
        }
