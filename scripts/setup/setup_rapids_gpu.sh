#!/bin/bash
# Setup script for RAPIDS GPU acceleration

echo "🚀 Setting up RAPIDS GPU acceleration for demand forecasting..."

# Check if NVIDIA GPU is available
if ! command -v nvidia-smi &> /dev/null; then
    echo "❌ NVIDIA GPU not detected. Please ensure NVIDIA drivers are installed."
    exit 1
fi

echo "✅ NVIDIA GPU detected"

# Check CUDA version
CUDA_VERSION=$(nvidia-smi | grep "CUDA Version" | awk '{print $9}' | cut -d. -f1,2)
echo "📊 CUDA Version: $CUDA_VERSION"

# Install RAPIDS cuML (this is a simplified version - in production you'd use conda)
echo "📦 Installing RAPIDS cuML dependencies..."

# For now, we'll use the CPU fallback but prepare for GPU
pip install --upgrade pip
pip install cudf-cu12 cuml-cu12 --extra-index-url=https://pypi.nvidia.com

echo "✅ RAPIDS setup complete!"
echo "🎯 To use GPU acceleration:"
echo "   1. Run: docker-compose -f docker-compose.rapids.yml up"
echo "   2. Or use the RAPIDS training script directly"
echo "   3. Check GPU usage with: nvidia-smi"
