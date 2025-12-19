#!/bin/bash
# Setup script for RAPIDS GPU acceleration

echo "🚀 Setting up RAPIDS GPU acceleration for demand forecasting..."

# Check if NVIDIA GPU is available
if ! command -v nvidia-smi &> /dev/null; then
    echo "❌ NVIDIA GPU not detected. Please ensure NVIDIA drivers are installed."
    exit 1
fi

echo "✅ NVIDIA GPU detected"
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader

# Detect CUDA version (same logic as install_rapids.sh)
CUDA_VERSION=""
if command -v nvcc &> /dev/null; then
    CUDA_VERSION=$(nvcc --version | grep "release" | awk '{print $5}' | cut -d, -f1)
    echo "📊 CUDA version (from nvcc): $CUDA_VERSION"
elif command -v nvidia-smi &> /dev/null; then
    CUDA_VERSION=$(nvidia-smi | grep "CUDA Version" | awk '{print $9}' | cut -d. -f1,2 || echo "")
    if [ -n "$CUDA_VERSION" ]; then
        echo "📊 CUDA version (from driver): $CUDA_VERSION"
    fi
fi

# Determine which RAPIDS package to install based on CUDA version
if [ -z "$CUDA_VERSION" ]; then
    echo "⚠️  CUDA version not detected. Installing for CUDA 12.x (default)..."
    RAPIDS_CUDA="cu12"
elif [[ "$CUDA_VERSION" == 12.* ]] || [[ "$CUDA_VERSION" == "12" ]]; then
    echo "✅ Detected CUDA 12.x - installing RAPIDS for CUDA 12"
    RAPIDS_CUDA="cu12"
elif [[ "$CUDA_VERSION" == 11.* ]] || [[ "$CUDA_VERSION" == "11" ]]; then
    echo "✅ Detected CUDA 11.x - installing RAPIDS for CUDA 11"
    RAPIDS_CUDA="cu11"
else
    echo "⚠️  Unsupported CUDA version: $CUDA_VERSION. Installing for CUDA 12.x..."
    RAPIDS_CUDA="cu12"
fi

# Install RAPIDS cuML (this is a simplified version - in production you'd use conda)
echo "📦 Installing RAPIDS cuML dependencies for $RAPIDS_CUDA..."

# Upgrade pip
pip install --upgrade pip setuptools wheel

# Install RAPIDS packages with detected CUDA version
pip install --extra-index-url=https://pypi.nvidia.com \
    cudf-${RAPIDS_CUDA} \
    cuml-${RAPIDS_CUDA}

echo "✅ RAPIDS setup complete!"
echo "🎯 To use GPU acceleration:"
echo "   1. Run: docker compose -f docker-compose.rapids.yml up"
echo "   2. Or use the RAPIDS training script directly"
echo "   3. Check GPU usage with: nvidia-smi"
