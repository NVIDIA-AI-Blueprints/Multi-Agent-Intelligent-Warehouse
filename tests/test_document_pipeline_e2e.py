"""
End-to-end test for document processing pipeline.
Tests the complete flow from upload to results retrieval.
"""

import asyncio
import httpx
import time
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_URL = "http://localhost:8001"
TEST_FILE = Path("data/sample/test_documents/test_invoice.png")


async def test_document_pipeline():
    """Test the complete document processing pipeline."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        logger.info("=" * 60)
        logger.info("Testing Document Processing Pipeline End-to-End")
        logger.info("=" * 60)

        # Step 1: Upload document
        logger.info("\n1. Uploading document...")
        if not TEST_FILE.exists():
            logger.error(f"Test file not found: {TEST_FILE}")
            logger.info("Creating a simple test file...")
            TEST_FILE.parent.mkdir(parents=True, exist_ok=True)
            # Create a simple test image
            from PIL import Image
            img = Image.new('RGB', (800, 600), color='white')
            img.save(TEST_FILE)
            logger.info(f"Created test file: {TEST_FILE}")

        try:
            with open(TEST_FILE, "rb") as f:
                files = {"file": (TEST_FILE.name, f, "image/png")}
                data = {
                    "document_type": "invoice",
                    "user_id": "test_user",
                }
                response = await client.post(
                    f"{BASE_URL}/api/v1/document/upload",
                    files=files,
                    data=data,
                )
                response.raise_for_status()
                upload_result = response.json()
                document_id = upload_result["document_id"]
                logger.info(f"✅ Document uploaded successfully. ID: {document_id}")
        except Exception as e:
            logger.error(f"❌ Upload failed: {e}")
            return False

        # Step 2: Monitor processing status
        logger.info("\n2. Monitoring processing status...")
        max_wait_time = 120  # 2 minutes max
        start_time = time.time()
        last_status = None

        while time.time() - start_time < max_wait_time:
            try:
                response = await client.get(
                    f"{BASE_URL}/api/v1/document/status/{document_id}"
                )
                response.raise_for_status()
                status_result = response.json()

                current_status = status_result["status"]
                progress = status_result["progress"]
                current_stage = status_result["current_stage"]

                # Log status changes
                if current_status != last_status:
                    logger.info(
                        f"   Status: {current_status} | Progress: {progress}% | Stage: {current_stage}"
                    )
                    last_status = current_status

                # Check if completed
                if current_status == "completed":
                    logger.info("✅ Processing completed!")
                    break
                elif current_status == "failed":
                    error_msg = status_result.get("error_message", "Unknown error")
                    logger.error(f"❌ Processing failed: {error_msg}")
                    return False

                # Wait before next check
                await asyncio.sleep(2)

            except Exception as e:
                logger.error(f"❌ Status check failed: {e}")
                await asyncio.sleep(2)
                continue

        if time.time() - start_time >= max_wait_time:
            logger.error("❌ Processing timed out")
            return False

        # Step 3: Get results
        logger.info("\n3. Retrieving processing results...")
        try:
            response = await client.get(
                f"{BASE_URL}/api/v1/document/results/{document_id}"
            )
            response.raise_for_status()
            results = response.json()

            # Check if results are mock data
            is_mock = results.get("processing_summary", {}).get("is_mock_data", False)
            if is_mock:
                reason = results.get("processing_summary", {}).get("reason", "unknown")
                logger.warning(f"⚠️  Results are mock data. Reason: {reason}")
            else:
                logger.info("✅ Retrieved actual processing results")

            # Log result summary
            extraction_results = results.get("extraction_results", [])
            logger.info(f"   Extraction stages: {len(extraction_results)}")
            for result in extraction_results:
                logger.info(f"   - {result.get('stage', 'unknown')}: ✅")

            quality_score = results.get("quality_score")
            if quality_score:
                overall_score = quality_score.get("overall_score", 0)
                logger.info(f"   Quality Score: {overall_score}/5.0")

            logger.info("✅ Results retrieved successfully")
            return True

        except Exception as e:
            logger.error(f"❌ Results retrieval failed: {e}")
            return False


async def main():
    """Run the end-to-end test."""
    try:
        # Test health endpoint first
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{BASE_URL}/api/v1/document/health")
            if response.status_code != 200:
                logger.error("❌ Document service is not healthy")
                return
            logger.info("✅ Document service is healthy")

        # Run the pipeline test
        success = await test_document_pipeline()

        logger.info("\n" + "=" * 60)
        if success:
            logger.info("✅ End-to-end test PASSED")
        else:
            logger.error("❌ End-to-end test FAILED")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"❌ Test failed with error: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())

