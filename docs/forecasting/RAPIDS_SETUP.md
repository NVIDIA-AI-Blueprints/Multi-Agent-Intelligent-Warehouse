# RAPIDS GPU Setup Guide

This guide explains how to set up NVIDIA RAPIDS cuML for GPU-accelerated demand forecasting.

## Prerequisites

### Hardware Requirements
- **NVIDIA GPU** with CUDA Compute Capability 7.0+ (Volta, Turing, Ampere, Ada, Hopper)
- **16GB+ GPU memory** (recommended for large datasets)
- **32GB+ system RAM** (recommended)
- **CUDA 11.2+ or 12.0+** installed

### Software Requirements
- **Python 3.11** for the MAIW virtual environment (MAIW requires Python >= 3.11; the RAPIDS 24.02 conda/container examples below use Python 3.10 and run the forecasting script standalone)
- **NVIDIA GPU drivers** (latest recommended)
- **CUDA Toolkit** (11.2+ or 12.0+)

## Installation Methods

### Method 1: Pip Installation (Recommended for Virtual Environments)

This is the easiest method for development environments:

```bash
# Activate your virtual environment
source .venv/bin/activate

# Run the installation script
./scripts/setup/install_rapids.sh
```

Or manually:

```bash
# Upgrade pip
pip install --upgrade pip setuptools wheel

# Install RAPIDS from NVIDIA PyPI
pip install --extra-index-url=https://pypi.nvidia.com \
    cudf-cu12 \
    cuml-cu12 \
    cugraph-cu12 \
    cuspatial-cu12 \
    cuproj-cu12 \
    cusignal-cu12 \
    cuxfilter-cu12 \
    cudf-pandas \
    dask-cudf-cu12 \
    dask-cuda
```

**Note:** Replace `cu12` with `cu11` if you have CUDA 11.x installed.

### Method 2: Conda Installation (Recommended for Production)

Conda is the recommended method for production deployments:

```bash
# Create a new conda environment with RAPIDS
conda create -n rapids-env -c rapidsai -c conda-forge -c nvidia \
    rapids=24.02 python=3.10 cudatoolkit=12.0

# Activate the environment
conda activate rapids-env

# Install additional dependencies
pip install asyncpg psycopg2-binary redis
```

### Method 3: Docker (Recommended for Isolation)

Build the image from `Dockerfile.rapids` at the repository root and run it. (`deploy/compose/docker-compose.rapids.yml` is not currently usable: its build context and command path are wrong.)

```bash
# Build and run RAPIDS container (from the repository root)
docker build -f Dockerfile.rapids -t warehouse-rapids .
docker run --gpus all -it warehouse-rapids
```

## Verification

### 1. Check GPU Availability

```bash
nvidia-smi
```

You should see your GPU listed with driver and CUDA version.

### 2. Test RAPIDS Installation

```python
# Test cuDF (GPU DataFrames)
python -c "import cudf; df = cudf.DataFrame({'a': [1,2,3], 'b': [4,5,6]}); print(df); print('✅ cuDF working')"

# Test cuML (GPU Machine Learning)
python -c "import cuml; from cuml.ensemble import RandomForestRegressor; print('✅ cuML working')"

# Test GPU memory
python -c "import cudf; import cupy as cp; print(f'GPU Memory: {cp.get_default_memory_pool().get_limit() / 1e9:.2f} GB')"
```

### 3. Test Forecasting Script

```bash
# Run the RAPIDS forecasting script
python scripts/forecasting/rapids_gpu_forecasting.py
```

You should see:
```
✅ RAPIDS cuML detected - GPU acceleration enabled
```

## Usage

### Running GPU-Accelerated Forecasting

The forecasting system automatically detects RAPIDS and uses GPU acceleration when available:

```python
from scripts.forecasting.rapids_gpu_forecasting import RAPIDSForecastingAgent

# Initialize agent (will use GPU if RAPIDS is available)
agent = RAPIDSForecastingAgent()

# Run forecasting for all SKUs (connects to the database itself)
forecast = await agent.run_batch_forecast()
```

### Via API / UI

Training is **not exposed by the release API**: `apps/api/maiw_api/app.py` mounts only the GET routes of the legacy training and forecasting routers, so `POST /api/v1/training/start` (and the Forecasting page's "Start Training" button, which calls it) returns 404/405. Run the forecasting script directly instead:

```bash
python scripts/forecasting/rapids_gpu_forecasting.py
```

## Performance Benefits

GPU acceleration provides significant performance improvements:

- **Training Speed**: 10-100x faster than CPU for large datasets
- **Batch Processing**: Process multiple SKUs in parallel
- **Memory Efficiency**: Better memory utilization for large feature sets
- **Scalability**: Handle larger datasets that would be impractical on CPU

### Example Performance

| Dataset Size | CPU Time | GPU Time | Speedup |
|-------------|----------|----------|---------|
| 1,000 rows   | 2.5s     | 0.8s     | 3.1x    |
| 10,000 rows  | 25s      | 1.2s     | 20.8x   |
| 100,000 rows | 250s     | 3.5s     | 71.4x   |

## Troubleshooting

### Issue: "RAPIDS cuML not available - checking for XGBoost GPU support..."

**Causes:**
1. RAPIDS not installed
2. CUDA not available
3. GPU not detected

**Solutions:**
```bash
# Check GPU
nvidia-smi

# Check CUDA
nvcc --version

# Reinstall RAPIDS
./scripts/setup/install_rapids.sh
```

### Issue: "CUDA out of memory"

**Causes:**
- Dataset too large for GPU memory
- Multiple processes using GPU

**Solutions:**
1. Reduce `lookback_days`, `n_estimators` or `max_depth` in configuration
2. Process SKUs in smaller batches
3. Use CPU fallback for very large datasets
4. Free GPU memory: `python -c "import cupy; cupy.get_default_memory_pool().free_all_blocks()"`

### Issue: "Driver/library version mismatch"

**Causes:**
- NVIDIA driver and CUDA library versions don't match

**Solutions:**
```bash
# Restart NVIDIA driver
sudo systemctl restart nvidia-persistenced

# Or reboot the system
sudo reboot
```

### Issue: Import errors

**Causes:**
- Wrong CUDA version package installed
- Missing dependencies

**Solutions:**
```bash
# Uninstall and reinstall with correct CUDA version
pip uninstall cudf cuml
pip install --extra-index-url=https://pypi.nvidia.com cudf-cu12 cuml-cu12
```

## Configuration

### Environment Variables

GPU use is detected automatically (RAPIDS cuML, else XGBoost CUDA, else CPU); there is no `USE_GPU` switch. To pick a GPU:

```bash
# CUDA device ID
CUDA_VISIBLE_DEVICES=0
```

### Code Configuration

`RAPIDSForecastingAgent(config)` **replaces** the defaults, so pass every key (defaults from `_get_default_config()` in `scripts/forecasting/rapids_gpu_forecasting.py`):

```python
config = {
    "lookback_days": 180,
    "forecast_days": 30,
    "test_size": 0.2,
    "random_state": 42,
    "n_estimators": 100,
    "max_depth": 10,
    "min_samples_split": 5,
    "min_samples_leaf": 2,
    "max_features": "sqrt",
}
```

## Best Practices

1. **Use Conda for Production**: More stable and better dependency management
2. **Monitor GPU Memory**: Use `nvidia-smi` to monitor usage
3. **Batch Processing**: Process multiple SKUs in batches for better GPU utilization
4. **Fallback to CPU**: Always have CPU fallback for systems without GPU
5. **Memory Management**: Free GPU memory between batches if processing large datasets

## Additional Resources

- [RAPIDS Documentation](https://docs.rapids.ai/)
- [cuML User Guide](https://docs.rapids.ai/api/cuml/stable/)
- [NVIDIA RAPIDS GitHub](https://github.com/rapidsai)
- [CUDA Installation Guide](https://docs.nvidia.com/cuda/cuda-installation-guide-linux/)

## Support

For issues specific to RAPIDS:
- [RAPIDS GitHub Issues](https://github.com/rapidsai/cuml/issues)
- [RAPIDS Community Forum](https://rapids.ai/community.html)

