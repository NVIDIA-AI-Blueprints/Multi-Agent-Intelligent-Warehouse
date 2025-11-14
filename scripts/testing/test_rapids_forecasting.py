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

from scripts.rapids_forecasting_agent import RAPIDSForecastingAgent, ForecastingConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_forecasting_agent():
    """Test the RAPIDS forecasting agent"""
    logger.info("🧪 Testing RAPIDS Forecasting Agent...")
    
    # Test configuration
    config = ForecastingConfig(
        prediction_horizon_days=7,  # Short horizon for testing
        lookback_days=30,           # Reduced lookback for testing
        min_training_samples=10     # Lower threshold for testing
    )
    
    # Initialize agent
    agent = RAPIDSForecastingAgent(config)
    
    try:
        # Test with a single SKU
        test_sku = "LAY001"
        logger.info(f"📊 Testing forecast for {test_sku}")
        
        forecast = await agent.forecast_demand(test_sku, horizon_days=7)
        
        # Validate results
        assert len(forecast.predictions) == 7, "Should have 7 days of predictions"
        assert len(forecast.confidence_intervals) == 7, "Should have 7 confidence intervals"
        assert all(pred >= 0 for pred in forecast.predictions), "Predictions should be non-negative"
        
        logger.info("✅ Single SKU forecast test passed")
        logger.info(f"📈 Sample predictions: {forecast.predictions[:3]}")
        logger.info(f"🔍 Top features: {list(forecast.feature_importance.keys())[:3]}")
        
        # Test batch forecasting
        test_skus = ["LAY001", "LAY002", "DOR001"]
        logger.info(f"📊 Testing batch forecast for {len(test_skus)} SKUs")
        
        batch_forecasts = await agent.batch_forecast(test_skus, horizon_days=7)
        
        assert len(batch_forecasts) == len(test_skus), "Should have forecasts for all SKUs"
        
        logger.info("✅ Batch forecast test passed")
        
        # Show results summary
        logger.info("📊 Test Results Summary:")
        for sku, forecast in batch_forecasts.items():
            avg_pred = sum(forecast.predictions) / len(forecast.predictions)
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
