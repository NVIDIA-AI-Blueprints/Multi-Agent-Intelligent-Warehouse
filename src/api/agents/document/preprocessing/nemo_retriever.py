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
        # v2.0.1 (audit P1-05): preprocessing is local (PDF → page images). It
        # makes no model call; there is no provider URL or API key here.
        self.timeout = 60

    async def initialize(self):
        """Nothing to initialize: preprocessing is local."""
        return None

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
        Page-element (layout) detection.

        v2.0.1 (audit P1-05): the v2.0.0 implementation sent a text-only chat
        request to a provider directly (outside ModelGateway) and then returned
        hard-coded elements — or mock elements on any failure. No approved
        Nemotron 3 / 3.5 layout model exists, so layout detection is reported
        honestly as not performed. Nothing downstream depends on these
        elements for correctness (OCR runs per page image).
        """
        return {
            "elements": [],
            "confidence": None,
            "model_used": None,
            "layout_detection": "not_performed",
            "reason": "no approved layout-detection model; layout is not inferred",
        }

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
