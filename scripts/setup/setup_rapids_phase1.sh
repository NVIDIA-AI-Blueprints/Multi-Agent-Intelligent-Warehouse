#!/bin/bash
# Phase 1: RAPIDS Container Setup Script

echo "🚀 Phase 1: Setting up NVIDIA RAPIDS Container Environment"

# Check if NVIDIA drivers are installed
if ! command -v nvidia-smi &> /dev/null; then
    echo "❌ NVIDIA drivers not found. Please install NVIDIA drivers first."
    exit 1
fi

echo "✅ NVIDIA drivers detected:"
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader,nounits

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker not found. Please install Docker first."
    exit 1
fi

echo "✅ Docker detected:"
docker --version

# Check if NVIDIA Container Toolkit is installed
if ! docker run --rm --gpus all nvidia/cuda:11.8-base-ubuntu20.04 nvidia-smi &> /dev/null; then
    echo "⚠️  NVIDIA Container Toolkit not detected. Installing..."
    
    # Install NVIDIA Container Toolkit
    distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
    curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
    curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list
    
    sudo apt-get update && sudo apt-get install -y nvidia-docker2
    sudo systemctl restart docker
    
    echo "✅ NVIDIA Container Toolkit installed"
else
    echo "✅ NVIDIA Container Toolkit detected"
fi

# Pull RAPIDS container
echo "📦 Pulling NVIDIA RAPIDS container..."
docker pull nvcr.io/nvidia/rapidsai/rapidsai:24.02-cuda12.0-runtime-ubuntu22.04-py3.10

# Test RAPIDS container
echo "🧪 Testing RAPIDS container..."
docker run --rm --gpus all \
  nvcr.io/nvidia/rapidsai/rapidsai:24.02-cuda12.0-runtime-ubuntu22.04-py3.10 \
  python -c "import cudf, cuml; print('✅ RAPIDS cuML and cuDF working!')"

# Create project directory in container
echo "📁 Setting up project directory..."
docker run --rm --gpus all \
  -v $(pwd):/app \
  nvcr.io/nvidia/rapidsai/rapidsai:24.02-cuda12.0-runtime-ubuntu22.04-py3.10 \
  bash -c "cd /app && pip install asyncpg psycopg2-binary xgboost"

echo "🎉 Phase 1 Complete! RAPIDS environment is ready."
echo ""
echo "🚀 Next steps:"
echo "1. Run Phase 2: python scripts/phase1_phase2_forecasting_agent.py"
echo "2. Test with RAPIDS: docker run --gpus all -v \$(pwd):/app nvcr.io/nvidia/rapidsai/rapidsai:24.02-cuda12.0-runtime-ubuntu22.04-py3.10 python /app/scripts/phase1_phase2_forecasting_agent.py"
