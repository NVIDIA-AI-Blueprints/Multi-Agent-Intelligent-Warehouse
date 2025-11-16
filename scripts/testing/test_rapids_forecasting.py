#!/usr/bin/env python3
"""
RAPIDS Forecasting Agent Test Script

Tests the GPU-accelerated demand forecasting agent with sample data.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from scripts.forecasting.rapids_gpu_forecasting import RAPIDSForecastingAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_forecasting_agent():
    """Test the RAPIDS forecasting agent"""
    logger.info("🧪 Testing RAPIDS Forecasting Agent...")
    
    # Initialize agent (uses default config)
    agent = RAPIDSForecastingAgent()
    
    try:
        # Test batch forecasting (rapids_gpu_forecasting uses run_batch_forecast method)
        test_skus = ["LAY001", "LAY002", "DOR001"]
        logger.info(f"📊 Testing batch forecast for {len(test_skus)} SKUs")
        
        # Note: run_batch_forecast() doesn't take skus parameter, it gets all SKUs from DB
        # For testing, we'll just run it and check if it works
        result = await agent.run_batch_forecast()
        
        # Validate results
        assert 'forecasts' in result, "Result should contain forecasts"
        assert result['successful_forecasts'] > 0, "Should have at least one successful forecast"
        
        logger.info("✅ Batch forecast test passed")
        
        # Show results summary
        logger.info("📊 Test Results Summary:")
        for sku, forecast_data in result['forecasts'].items():
            if isinstance(forecast_data, dict) and 'predictions' in forecast_data:
                predictions = forecast_data['predictions']
                avg_pred = sum(predictions) / len(predictions) if predictions else 0
                logger.info(f"   • {sku}: {avg_pred:.1f} avg daily demand")
        
        logger.info("🎉 All tests passed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        return False

async def test_gpu_availability():
    """Test GPU availability and RAPIDS installation"""
    logger.info("🔍 Testing GPU availability...")
    
    try:
        import cudf
        import cuml
        logger.info("✅ RAPIDS cuML and cuDF available")
        
        # Test GPU memory
        import cupy as cp
        mempool = cp.get_default_memory_pool()
        logger.info(f"🔧 GPU memory pool: {mempool.used_bytes() / 1024**3:.2f} GB used")
        
        # Test basic cuDF operation
        df = cudf.DataFrame({'test': [1, 2, 3, 4, 5]})
        result = df['test'].sum()
        logger.info(f"✅ cuDF test passed: sum = {result}")
        
        return True
        
    except ImportError as e:
        logger.warning(f"⚠️  RAPIDS not available: {e}")
        logger.info("💡 Running in CPU mode - install RAPIDS for GPU acceleration")
        return False
    except Exception as e:
        logger.error(f"❌ GPU test failed: {e}")
        return False

async def main():
    """Main test function"""
    logger.info("🚀 Starting RAPIDS Forecasting Agent Tests...")
    
    # Test GPU availability
    gpu_available = await test_gpu_availability()
    
    if not gpu_available:
        logger.info("⚠️  Continuing with CPU fallback mode...")
    
    # Test forecasting agent
    success = await test_forecasting_agent()
    
    if success:
        logger.info("🎉 All tests completed successfully!")
        logger.info("🚀 Ready to deploy RAPIDS forecasting agent!")
    else:
        logger.error("❌ Tests failed - check configuration and dependencies")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
