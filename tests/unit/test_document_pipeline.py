#!/usr/bin/env python3
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
Comprehensive test script for the Document Extraction Pipeline.
Tests each stage individually to verify NVIDIA API integration.
"""

import asyncio
import os
import sys
import logging
from pathlib import Path
import json
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Import test utilities
from tests.unit.test_utils import get_test_file_path
from tests.unit.test_config import TEST_INVOICE_CANDIDATES

# Import pipeline components
from src.api.agents.document.preprocessing.nemo_retriever import (
    NeMoRetrieverPreprocessor,
)
from src.api.agents.document.ocr.nemo_ocr import NeMoOCRService
from src.api.agents.document.processing.small_llm_processor import SmallLLMProcessor
from src.api.agents.document.validation.large_llm_judge import LargeLLMJudge
from src.api.agents.document.routing.intelligent_router import IntelligentRouter

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)
logger = logging.getLogger(__name__)


class DocumentPipelineTester:
    """Test each stage of the document extraction pipeline."""

    def __init__(self):
        # Find test file in common locations
        test_file = get_test_file_path("test_invoice.png", TEST_INVOICE_CANDIDATES)
        if not test_file:
            raise FileNotFoundError(
                f"Test file 'test_invoice.png' not found. Tried: {TEST_INVOICE_CANDIDATES}"
            )
        self.test_file_path = str(test_file)
        self.results = {}

    async def test_stage1_preprocessing(self):
        """Test Stage 1: NeMo Retriever Preprocessing"""
        logger.info("=" * 60)
        logger.info("TESTING STAGE 1: NeMo Retriever Preprocessing")
        logger.info("=" * 60)

        try:
            preprocessor = NeMoRetrieverPreprocessor()
            await preprocessor.initialize()

            logger.info(f"API Key available: {bool(preprocessor.api_key)}")
            logger.info(f"Base URL: {preprocessor.base_url}")

            if not os.path.exists(self.test_file_path):
                logger.error(f"Test file not found: {self.test_file_path}")
                return False

            result = await preprocessor.process_document(self.test_file_path)

            logger.info("✅ Stage 1 Results:")
            logger.info(f"  - Images extracted: {len(result.get('images', []))}")
            logger.info(
                f"  - Pages processed: {len(result.get('processed_pages', []))}"
            )
            logger.info(f"  - Layout detection: {result.get('layout_detection', {})}")
            logger.info(f"  - Model used: {result.get('model_used', 'unknown')}")

            self.results["stage1"] = result
            return True

        except Exception as e:
            logger.error(f"❌ Stage 1 failed: {e}")
            return False

    async def test_stage2_ocr(self):
        """Test Stage 2: NeMo OCR Service"""
        logger.info("=" * 60)
        logger.info("TESTING STAGE 2: NeMo OCR Service")
        logger.info("=" * 60)

        try:
            ocr_service = NeMoOCRService()
            await ocr_service.initialize()

            logger.info(f"API Key available: {bool(ocr_service.api_key)}")
            logger.info(f"Base URL: {ocr_service.base_url}")

            # Use images from stage 1 preprocessing
            images = self.results.get("stage1", {}).get("images", [])
            layout_result = self.results.get("stage1", {}).get("layout_detection", {})

            if not images:
                logger.error("No images available from preprocessing stage")
                return False

            result = await ocr_service.extract_text(images, layout_result)

            logger.info("✅ Stage 2 Results:")
            logger.info(f"  - Text extracted: {len(result.get('text', ''))} characters")
            logger.info(f"  - Pages processed: {result.get('total_pages', 0)}")
            logger.info(f"  - Confidence: {result.get('confidence', 0.0):.2f}")
            logger.info(f"  - Model used: {result.get('model_used', 'unknown')}")
            logger.info(f"  - Layout enhanced: {result.get('layout_enhanced', False)}")

            self.results["stage2"] = result
            return True

        except Exception as e:
            logger.error(f"❌ Stage 2 failed: {e}")
            return False

    async def test_stage3_small_llm(self):
        """Test Stage 3: Small LLM Processing"""
        logger.info("=" * 60)
        logger.info("TESTING STAGE 3: Small LLM Processing")
        logger.info("=" * 60)

        try:
            llm_processor = SmallLLMProcessor()
            await llm_processor.initialize()

            logger.info(f"API Key available: {bool(llm_processor.api_key)}")
            logger.info(f"Base URL: {llm_processor.base_url}")

            # Use mock data from previous stages if available
            images = self.results.get("stage1", {}).get("images", [])
            ocr_text = self.results.get("stage2", {}).get(
                "text", "Sample invoice text for testing"
            )

            result = await llm_processor.process_document(images, ocr_text, "invoice")

            logger.info("✅ Stage 3 Results:")
            logger.info(f"  - Structured data: {bool(result.get('structured_data'))}")
            logger.info(f"  - Confidence: {result.get('confidence', 0.0):.2f}")
            logger.info(f"  - Model used: {result.get('model_used', 'unknown')}")
            logger.info(
                f"  - Processing time: {result.get('processing_timestamp', 'unknown')}"
            )

            self.results["stage3"] = result
            return True

        except Exception as e:
            logger.error(f"❌ Stage 3 failed: {e}")
            return False

    async def test_stage4_large_llm(self):
        """Test Stage 4: Large LLM Judge Validation"""
        logger.info("=" * 60)
        logger.info("TESTING STAGE 4: Large LLM Judge Validation")
        logger.info("=" * 60)

        try:
            judge = LargeLLMJudge()
            await judge.initialize()

            logger.info(f"API Key available: {bool(judge.api_key)}")
            logger.info(f"Base URL: {judge.base_url}")

            # Use data from previous stages
            structured_data = self.results.get("stage3", {}).get("structured_data", {})
            entities = self.results.get("stage3", {}).get("entities", {})

            result = await judge.evaluate_document(structured_data, entities, "invoice")

            logger.info("✅ Stage 4 Results:")
            logger.info(
                f"  - Overall score: {result.overall_score if hasattr(result, 'overall_score') else 'N/A'}"
            )
            logger.info(
                f"  - Decision: {result.decision if hasattr(result, 'decision') else 'N/A'}"
            )
            logger.info(
                f"  - Confidence: {result.confidence if hasattr(result, 'confidence') else 'N/A'}"
            )
            logger.info(
                f"  - Model used: {result.judge_model if hasattr(result, 'judge_model') else 'unknown'}"
            )

            self.results["stage4"] = result
            return True

        except Exception as e:
            logger.error(f"❌ Stage 4 failed: {e}")
            return False

    async def test_stage5_router(self):
        """Test Stage 5: Intelligent Router"""
        logger.info("=" * 60)
        logger.info("TESTING STAGE 5: Intelligent Router")
        logger.info("=" * 60)

        try:
            router = IntelligentRouter()
            await router.initialize()

            # Use data from previous stages
            quality_scores = self.results.get("stage4", {})
            extraction_results = self.results.get("stage3", {})

            result = await router.route_document(
                quality_scores, extraction_results, "invoice"
            )

            logger.info("✅ Stage 5 Results:")
            logger.info(
                f"  - Routing action: {result.routing_action if hasattr(result, 'routing_action') else 'N/A'}"
            )
            logger.info(
                f"  - WMS integration: {result.wms_integration_status if hasattr(result, 'wms_integration_status') else 'N/A'}"
            )
            logger.info(
                f"  - Human review required: {result.human_review_required if hasattr(result, 'human_review_required') else 'N/A'}"
            )

            self.results["stage5"] = result
            return True

        except Exception as e:
            logger.error(f"❌ Stage 5 failed: {e}")
            return False

    async def test_full_pipeline(self):
        """Test the complete pipeline integration"""
        logger.info("=" * 60)
        logger.info("TESTING FULL PIPELINE INTEGRATION")
        logger.info("=" * 60)

        stages = [
            ("Stage 1: Preprocessing", self.test_stage1_preprocessing),
            ("Stage 2: OCR", self.test_stage2_ocr),
            ("Stage 3: Small LLM", self.test_stage3_small_llm),
            ("Stage 4: Large LLM Judge", self.test_stage4_large_llm),
            ("Stage 5: Router", self.test_stage5_router),
        ]

        results = {}
        for stage_name, test_func in stages:
            logger.info(f"\n🔄 Running {stage_name}...")
            success = await test_func()
            results[stage_name] = success

            if not success:
                logger.error(f"❌ {stage_name} failed - stopping pipeline test")
                break

        # Summary
        logger.info("\n" + "=" * 60)
        logger.info("PIPELINE TEST SUMMARY")
        logger.info("=" * 60)

        for stage_name, success in results.items():
            status = "✅ PASS" if success else "❌ FAIL"
            logger.info(f"{status} {stage_name}")

        total_passed = sum(results.values())
        total_stages = len(results)
        logger.info(f"\nOverall: {total_passed}/{total_stages} stages passed")

        return results

    def save_results(self):
        """Save test results to file"""
        try:
            results_file = (
                f"pipeline_test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )

            # Convert any non-serializable objects
            serializable_results = {}
            for key, value in self.results.items():
                if hasattr(value, "__dict__"):
                    serializable_results[key] = value.__dict__
                else:
                    serializable_results[key] = value

            with open(results_file, "w") as f:
                json.dump(serializable_results, f, indent=2, default=str)

            logger.info(f"📄 Test results saved to: {results_file}")

        except Exception as e:
            logger.error(f"Failed to save results: {e}")


async def main():
    """Main test function"""
    logger.info("🚀 Starting Document Extraction Pipeline Test")
    logger.info("Test file: test_invoice.png")
    logger.info(f"Environment: {os.getenv('ENVIRONMENT', 'development')}")

    # Check environment variables
    env_vars = [
        "NEMO_RETRIEVER_API_KEY",
        "NEMO_OCR_API_KEY",
        "LLAMA_NANO_VL_API_KEY",
        "NVIDIA_API_KEY",
    ]

    logger.info("\n🔑 Environment Variables Check:")
    for var in env_vars:
        value = os.getenv(var, "NOT_SET")
        status = "✅" if value != "NOT_SET" else "❌"
        logger.info(
            f"  {status} {var}: {value[:20] + '...' if value != 'NOT_SET' else 'NOT_SET'}"
        )

    tester = DocumentPipelineTester()

    try:
        # Run full pipeline test
        results = await tester.test_full_pipeline()

        # Save results
        tester.save_results()

        # Final status
        if all(results.values()):
            logger.info("\n🎉 ALL TESTS PASSED! Pipeline is working correctly.")
        else:
            logger.info("\n⚠️  SOME TESTS FAILED. Check the logs above for details.")

    except Exception as e:
        logger.error(f"💥 Test execution failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
