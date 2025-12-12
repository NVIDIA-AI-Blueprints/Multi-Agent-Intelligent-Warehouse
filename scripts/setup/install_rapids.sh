#!/bin/bash
# Install RAPIDS cuML for GPU-accelerated forecasting
# This script installs RAPIDS via pip (conda recommended for production)

set -e

echo "🚀 Installing RAPIDS cuML for GPU-accelerated forecasting..."

# Check if NVIDIA GPU is available
if ! command -v nvidia-smi &> /dev/null; then
    echo "⚠️  NVIDIA GPU not detected. RAPIDS will not work without a GPU."
    echo "   Continuing with installation anyway (for testing)..."
else
    echo "✅ NVIDIA GPU detected"
    nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
fi

# Check Python version (RAPIDS requires Python 3.9-3.11)
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "📊 Python version: $PYTHON_VERSION"

if [[ $(echo "$PYTHON_VERSION < 3.9" | bc -l 2>/dev/null || echo "1") == "1" ]] || [[ $(echo "$PYTHON_VERSION > 3.11" | bc -l 2>/dev/null || echo "0") == "0" ]]; then
    echo "⚠️  Warning: RAPIDS works best with Python 3.9-3.11. Current: $PYTHON_VERSION"
fi

# Detect CUDA version
CUDA_VERSION=""
if command -v nvcc &> /dev/null; then
    CUDA_VERSION=$(nvcc --version | grep "release" | awk '{print $5}' | cut -d, -f1)
    echo "📊 CUDA version: $CUDA_VERSION"
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

# Upgrade pip
echo "⬆️  Upgrading pip..."
pip install --upgrade pip setuptools wheel

# Install RAPIDS cuML and cuDF
echo "📦 Installing RAPIDS cuML and cuDF for $RAPIDS_CUDA..."
echo "   This may take several minutes..."
echo "   Installing core packages: cudf and cuml (required for forecasting)"

# Install core RAPIDS packages required for forecasting
# Note: Only cudf and cuml are required. Other packages are optional.
pip install --extra-index-url=https://pypi.nvidia.com \
    cudf-${RAPIDS_CUDA} \
    cuml-${RAPIDS_CUDA}

# Optional: Install additional RAPIDS packages if needed
# Uncomment the lines below if you need these packages:
# pip install --extra-index-url=https://pypi.nvidia.com \
#     cugraph-${RAPIDS_CUDA} \
#     cuspatial-${RAPIDS_CUDA} \
#     cuproj-${RAPIDS_CUDA} \
#     cuxfilter-${RAPIDS_CUDA} \
#     cudf-pandas \
#     dask-cudf-${RAPIDS_CUDA} \
#     dask-cuda

echo "   ✅ Core RAPIDS packages installed (cudf, cuml)"

echo ""
echo "✅ RAPIDS installation complete!"
echo ""
echo "📝 Next steps:"
echo "   1. Verify installation: python -c 'import cudf, cuml; print(\"✅ RAPIDS installed successfully\")'"
echo "   2. Test GPU: python -c 'import cudf; df = cudf.DataFrame({\"a\": [1,2,3]}); print(df)'"
echo "   3. Run forecasting: python scripts/forecasting/rapids_gpu_forecasting.py"
echo ""
echo "🐳 Alternative: Use Docker with RAPIDS container:"
echo "   docker-compose -f deploy/compose/docker-compose.rapids.yml up"
echo ""
echo "📚 Documentation: https://docs.rapids.ai/"

