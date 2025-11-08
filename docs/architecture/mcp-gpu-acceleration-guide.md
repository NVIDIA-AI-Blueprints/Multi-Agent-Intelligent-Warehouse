# GPU Acceleration with Milvus + cuVS - Implementation Guide

##  **Overview**

This guide covers the implementation of **GPU-accelerated vector search** using **Milvus with NVIDIA cuVS (CUDA Vector Search)** for our warehouse operational assistant system. This provides **dramatic performance improvements** for semantic search over warehouse documentation and operational procedures.

##  **Performance Benefits**

### **Quantified Improvements**
- **21x Speedup** in index building vs CPU
- **49x Higher QPS** for large batch queries
- **635M Vectors**: 56 minutes on 8x H100 GPUs vs 6.22 days on CPU
- **12.5x Cost-Performance** improvement after normalization
- **Sub-millisecond** query response times

### **Warehouse-Specific Benefits**
- **Real-time Document Search**: Instant access to SOPs, manuals, procedures
- **Batch Processing**: Efficient processing of multiple warehouse queries
- **High Concurrency**: Support for multiple warehouse operators simultaneously
- **Scalable Performance**: Linear scaling with additional GPUs

##  **Implementation Architecture**

### **1. GPU-Accelerated Milvus Configuration**

```python
@dataclass
class GPUMilvusConfig:
    # Basic Configuration
    host: str = "localhost"
    port: str = "19530"
    collection_name: str = "warehouse_docs_gpu"
    dimension: int = 1024  # NV-EmbedQA-E5-v5
    
    # GPU Configuration
    use_gpu: bool = True
    gpu_device_id: int = 0
    cuda_visible_devices: str = "0"
    
    # GPU Index Configuration
    index_type: str = "GPU_CAGRA"  # High-performance GPU index
    metric_type: str = "L2"
    
    # CAGRA Parameters (optimized for warehouse data)
    cagra_params: Dict[str, Any] = {
        "intermediate_graph_degree": 128,
        "graph_degree": 64,
        "build_algo": "IVF_PQ",
        "build_algo_params": {
            "pq_dim": 8,
            "nlist": 1024
        }
    }
```

### **2. GPU Index Types Available**

#### **GPU_CAGRA** (Recommended)
- **Best for**: High-performance, high-recall scenarios
- **Use Case**: Warehouse document search, procedure lookup
- **Performance**: Highest throughput and lowest latency
- **Memory**: Higher memory usage

#### **GPU_IVF_FLAT**
- **Best for**: Balanced performance and memory usage
- **Use Case**: General warehouse operations
- **Performance**: Good throughput, moderate latency
- **Memory**: Moderate memory usage

#### **GPU_IVF_PQ**
- **Best for**: Memory-constrained environments
- **Use Case**: Large-scale warehouse data
- **Performance**: Good throughput, higher latency
- **Memory**: Lower memory usage

## 🐳 **Docker Configuration**

### **GPU-Enabled Milvus Container**

```yaml
# docker-compose.gpu.yaml
services:
  milvus-gpu:
    image: milvusdb/milvus:v2.4.3-gpu
    container_name: wosa-milvus-gpu
    command: ["milvus", "run", "standalone"]
    environment:
      ETCD_ENDPOINTS: etcd:2379
      MINIO_ADDRESS: minio:9000
      MINIO_ACCESS_KEY: minioadmin
      MINIO_SECRET_KEY: minioadmin
      MINIO_USE_SSL: "false"
      # GPU Configuration
      CUDA_VISIBLE_DEVICES: "0"
      MILVUS_USE_GPU: "true"
      MILVUS_GPU_DEVICE_ID: "0"
    ports:
      - "19530:19530"   # gRPC
      - "9091:9091"     # HTTP
    volumes:
      - milvus_gpu_data:/var/lib/milvus
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    depends_on: [etcd, minio]
    restart: unless-stopped
```

### **Prerequisites**
- **NVIDIA Docker Runtime**: `nvidia-docker2` installed
- **CUDA Drivers**: Compatible NVIDIA drivers
- **GPU Memory**: Minimum 8GB VRAM recommended

##  **Implementation Steps**

### **Step 1: Environment Setup**

```bash
# Install NVIDIA Docker runtime
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list
sudo apt-get update && sudo apt-get install -y nvidia-docker2
sudo systemctl restart docker

# Verify GPU access
docker run --rm --gpus all nvidia/cuda:11.0-base nvidia-smi
```

### **Step 2: Deploy GPU-Accelerated Milvus**

```bash
# Start GPU-enabled Milvus
docker-compose -f docker-compose.gpu.yaml up -d milvus-gpu

# Verify GPU acceleration
docker logs wosa-milvus-gpu | grep -i gpu
```

### **Step 3: Update Application Configuration**

```python
# .env configuration
MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_USE_GPU=true
MILVUS_GPU_DEVICE_ID=0
CUDA_VISIBLE_DEVICES=0

# Collection configuration
MILVUS_COLLECTION_NAME=warehouse_docs_gpu
MILVUS_INDEX_TYPE=GPU_CAGRA
```

### **Step 4: Initialize GPU-Accelerated Retriever**

```python
from inventory_retriever.gpu_hybrid_retriever import get_gpu_hybrid_retriever

# Initialize GPU-accelerated retriever
retriever = await get_gpu_hybrid_retriever()

# Check GPU availability
stats = await retriever.get_performance_stats()
print(f"GPU Available: {stats['gpu_available']}")
print(f"Index Type: {stats['index_type']}")
```

##  **Performance Optimization**

### **1. Batch Processing**

```python
# Optimize for batch queries
context = GPUSearchContext(
    query="forklift maintenance procedures",
    search_type="hybrid",
    use_gpu=True,
    batch_size=10  # Process multiple queries together
)

# Batch search for multiple warehouse queries
queries = [
    "forklift maintenance procedures",
    "safety protocols for Zone A",
    "inventory counting guidelines",
    "equipment calibration steps"
]

results = await retriever.batch_search(queries, search_type="hybrid")
```

### **2. Index Optimization**

```python
# CAGRA parameters optimized for warehouse data
cagra_params = {
    "intermediate_graph_degree": 128,  # Higher for better recall
    "graph_degree": 64,               # Balanced performance
    "build_algo": "IVF_PQ",          # Memory efficient
    "build_algo_params": {
        "pq_dim": 8,                  # Product quantization dimension
        "nlist": 1024                 # Number of clusters
    }
}
```

### **3. Query Optimization**

```python
# Search parameters for GPU acceleration
search_params = {
    "metric_type": "L2",
    "params": {
        "itopk_size": 128,        # GPU-optimized parameter
        "max_iterations": 0       # No iteration limit
    }
}
```

##  **Use Cases in Warehouse Operations**

### **1. Real-Time Document Search**

```python
# Instant access to warehouse procedures
context = GPUSearchContext(
    query="How do I perform forklift pre-operation inspection?",
    search_type="documentation",
    use_gpu=True
)

result = await retriever.search(context)
# Sub-millisecond response for procedure lookup
```

### **2. Batch Safety Compliance**

```python
# Process multiple safety queries simultaneously
safety_queries = [
    "LOTO procedures for electrical equipment",
    "PPE requirements for chemical handling",
    "Emergency evacuation procedures",
    "Incident reporting protocols"
]

results = await retriever.batch_search(safety_queries, search_type="documentation")
# Process all safety queries in parallel with GPU acceleration
```

### **3. Equipment Maintenance Lookup**

```python
# High-performance equipment documentation search
context = GPUSearchContext(
    query="conveyor belt maintenance schedule",
    search_type="hybrid",
    use_gpu=True,
    limit=20
)

result = await retriever.search(context)
# Combines structured equipment data with documentation search
```

##  **Monitoring and Metrics**

### **1. Performance Monitoring**

```python
# Get GPU performance statistics
stats = await retriever.get_performance_stats()

print(f"GPU Available: {stats['gpu_available']}")
print(f"Collection Size: {stats['num_entities']}")
print(f"Index Type: {stats['index_type']}")
print(f"GPU Device: {stats['gpu_device_id']}")
```

### **2. Query Performance Tracking**

```python
# Track individual query performance
result = await retriever.search(context)

print(f"GPU Processing Time: {result.gpu_processing_time:.4f}s")
print(f"Total Processing Time: {result.total_processing_time:.4f}s")
print(f"GPU Acceleration Used: {result.gpu_acceleration_used}")
print(f"Results Found: {len(result.vector_results)}")
```

### **3. Batch Performance Metrics**

```python
# Monitor batch processing performance
start_time = time.time()
results = await retriever.batch_search(queries, search_type="hybrid")
total_time = time.time() - start_time

print(f"Batch Size: {len(queries)}")
print(f"Total Time: {total_time:.4f}s")
print(f"Average Time per Query: {total_time/len(queries):.4f}s")
print(f"Queries per Second: {len(queries)/total_time:.2f}")
```

## 🛠️ **Troubleshooting**

### **1. GPU Not Available**

```python
# Check GPU availability
import torch
print(f"CUDA Available: {torch.cuda.is_available()}")
print(f"CUDA Device Count: {torch.cuda.device_count()}")
print(f"Current Device: {torch.cuda.current_device()}")

# Check Milvus GPU support
stats = await retriever.get_performance_stats()
print(f"GPU Available in Milvus: {stats['gpu_available']}")
```

### **2. Performance Issues**

```python
# Monitor GPU memory usage
import nvidia_ml_py3 as nvml
nvml.nvmlInit()
handle = nvml.nvmlDeviceGetHandleByIndex(0)
info = nvml.nvmlDeviceGetMemoryInfo(handle)
print(f"GPU Memory Used: {info.used / 1024**3:.2f} GB")
print(f"GPU Memory Total: {info.total / 1024**3:.2f} GB")
```

### **3. Index Building Issues**

```python
# Check index status
collection = retriever.gpu_milvus_retriever.collection
indexes = collection.indexes
for index in indexes:
    print(f"Index: {index.params}")
    print(f"Index Status: {index.state}")
```

##  **Best Practices**

### **1. Query Optimization**
- Use **batch processing** for multiple queries
- Set appropriate **batch_size** based on GPU memory
- Use **filter expressions** to narrow search scope
- Implement **query caching** for repeated searches

### **2. Index Management**
- Use **GPU_CAGRA** for high-performance scenarios
- Use **GPU_IVF_PQ** for memory-constrained environments
- Monitor **index building time** and optimize parameters
- Implement **index versioning** for updates

### **3. Resource Management**
- Monitor **GPU memory usage** and set limits
- Use **connection pooling** for concurrent access
- Implement **fallback to CPU** when GPU unavailable
- Set appropriate **timeout values** for queries

##  **Deployment Considerations**

### **1. Production Deployment**
- Use **Kubernetes** with GPU node pools
- Implement **health checks** for GPU availability
- Set up **monitoring** with Prometheus/Grafana
- Configure **auto-scaling** based on GPU utilization

### **2. Cost Optimization**
- Use **spot instances** for non-critical workloads
- Implement **GPU sharing** for multiple applications
- Monitor **cost per query** and optimize accordingly
- Consider **hybrid CPU/GPU** deployment for cost efficiency

### **3. Security**
- Implement **GPU resource isolation**
- Use **encrypted connections** for data transfer
- Set up **access controls** for GPU resources
- Monitor **GPU usage** for security compliance

##  **Expected Performance Improvements**

### **For Warehouse Operations**
- **Document Search**: 10-50x faster response times
- **Batch Processing**: 20-100x higher throughput
- **Concurrent Users**: 5-10x more simultaneous users
- **Index Building**: 10-20x faster for large datasets

### **Scalability Benefits**
- **Linear Scaling**: Add GPUs for more performance
- **Memory Efficiency**: Better handling of large document collections
- **Real-time Updates**: Faster index updates for new documents
- **Global Deployment**: Consistent performance across regions

This GPU acceleration implementation provides **enterprise-grade performance** for warehouse operations while maintaining **cost efficiency** and **scalability**! 
