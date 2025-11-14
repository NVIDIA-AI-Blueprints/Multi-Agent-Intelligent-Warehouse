#!/usr/bin/env python3
"""
GPU Milvus Performance Benchmark

Benchmarks GPU-accelerated Milvus vs CPU-only Milvus for warehouse operations.
Provides detailed performance metrics and comparison analysis.
"""

import asyncio
import time
import logging
import numpy as np
from typing import List, Dict, Any
import json
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from src.retrieval.vector.gpu_milvus_retriever import GPUMilvusRetriever, GPUMilvusConfig
from src.retrieval.vector.milvus_retriever import MilvusRetriever, MilvusConfig
from src.retrieval.vector.embedding_service import EmbeddingService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MilvusBenchmark:
    """Benchmark GPU vs CPU Milvus performance."""
    
    def __init__(self):
        self.embedding_service = None
        self.gpu_retriever = None
        self.cpu_retriever = None
        self.test_queries = [
            "forklift maintenance procedures",
            "safety protocols for Zone A",
            "inventory counting guidelines",
            "equipment calibration steps",
            "emergency evacuation procedures",
            "PPE requirements for chemical handling",
            "LOTO procedures for electrical equipment",
            "incident reporting protocols",
            "quality control checklists",
            "warehouse layout optimization"
        ]
        self.test_documents = self._generate_test_documents()
    
    def _generate_test_documents(self) -> List[Dict[str, Any]]:
        """Generate test documents for benchmarking."""
        documents = []
        for i in range(1000):  # 1000 test documents
            doc = {
                "id": f"doc_{i:04d}",
                "content": f"Warehouse document {i}: This is a test document for benchmarking GPU vs CPU performance. "
                          f"Document contains information about warehouse operations, safety procedures, "
                          f"equipment maintenance, and operational guidelines. "
                          f"Category: {['safety', 'maintenance', 'operations', 'inventory'][i % 4]}. "
                          f"Priority: {i % 5 + 1}.",
                "doc_type": "procedure",
                "category": ["safety", "maintenance", "operations", "inventory"][i % 4],
                "created_at": "2024-01-01",
                "priority": i % 5 + 1,
                "access_count": 0
            }
            documents.append(doc)
        return documents
    
    async def initialize(self):
        """Initialize benchmark components."""
        try:
            # Initialize embedding service
            self.embedding_service = EmbeddingService()
            await self.embedding_service.initialize()
            
            # Initialize GPU retriever
            gpu_config = GPUMilvusConfig(
                collection_name="benchmark_gpu",
                use_gpu=True
            )
            self.gpu_retriever = GPUMilvusRetriever(gpu_config)
            await self.gpu_retriever.connect()
            await self.gpu_retriever.create_collection()
            await self.gpu_retriever.load_collection()
            
            # Initialize CPU retriever
            cpu_config = MilvusConfig(
                collection_name="benchmark_cpu"
            )
            self.cpu_retriever = MilvusRetriever(cpu_config)
            await self.cpu_retriever.connect()
            await self.cpu_retriever.create_collection()
            await self.cpu_retriever.load_collection()
            
            logger.info("Benchmark components initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize benchmark: {e}")
            raise
    
    async def prepare_test_data(self):
        """Prepare test data for both GPU and CPU retrievers."""
        try:
            # Generate embeddings for test documents
            logger.info("Generating embeddings for test documents...")
            for doc in self.test_documents:
                embedding = await self.embedding_service.generate_embedding(doc["content"])
                doc["embedding"] = embedding
            
            # Insert data into GPU retriever
            logger.info("Inserting data into GPU retriever...")
            await self.gpu_retriever.insert_documents_batch(self.test_documents, batch_size=100)
            
            # Insert data into CPU retriever
            logger.info("Inserting data into CPU retriever...")
            await self.cpu_retriever.insert_documents(self.test_documents)
            
            logger.info("Test data preparation completed")
            
        except Exception as e:
            logger.error(f"Failed to prepare test data: {e}")
            raise
    
    async def benchmark_single_queries(self) -> Dict[str, Any]:
        """Benchmark single query performance."""
        logger.info("Benchmarking single query performance...")
        
        gpu_times = []
        cpu_times = []
        gpu_results = []
        cpu_results = []
        
        for query in self.test_queries:
            # Generate query embedding
            query_embedding = await self.embedding_service.generate_embedding(query)
            
            # GPU search
            start_time = time.time()
            gpu_result = await self.gpu_retriever.search_similar_gpu(
                query_embedding=query_embedding,
                top_k=10
            )
            gpu_time = time.time() - start_time
            gpu_times.append(gpu_time)
            gpu_results.append(len(gpu_result))
            
            # CPU search
            start_time = time.time()
            cpu_result = await self.cpu_retriever.search_similar(
                query_embedding=query_embedding,
                top_k=10
            )
            cpu_time = time.time() - start_time
            cpu_times.append(cpu_time)
            cpu_results.append(len(cpu_result))
        
        return {
            "gpu_times": gpu_times,
            "cpu_times": cpu_times,
            "gpu_results": gpu_results,
            "cpu_results": cpu_results,
            "gpu_avg_time": np.mean(gpu_times),
            "cpu_avg_time": np.mean(cpu_times),
            "gpu_std_time": np.std(gpu_times),
            "cpu_std_time": np.std(cpu_times),
            "speedup": np.mean(cpu_times) / np.mean(gpu_times) if np.mean(gpu_times) > 0 else 0
        }
    
    async def benchmark_batch_queries(self) -> Dict[str, Any]:
        """Benchmark batch query performance."""
        logger.info("Benchmarking batch query performance...")
        
        # Generate query embeddings
        query_embeddings = []
        for query in self.test_queries:
            embedding = await self.embedding_service.generate_embedding(query)
            query_embeddings.append(embedding)
        
        # GPU batch search
        start_time = time.time()
        gpu_batch_results = await self.gpu_retriever.batch_search_gpu(
            query_embeddings=query_embeddings,
            top_k=10
        )
        gpu_batch_time = time.time() - start_time
        
        # CPU individual searches (simulate batch)
        start_time = time.time()
        cpu_batch_results = []
        for embedding in query_embeddings:
            result = await self.cpu_retriever.search_similar(
                query_embedding=embedding,
                top_k=10
            )
            cpu_batch_results.append(result)
        cpu_batch_time = time.time() - start_time
        
        return {
            "gpu_batch_time": gpu_batch_time,
            "cpu_batch_time": cpu_batch_time,
            "gpu_batch_speedup": cpu_batch_time / gpu_batch_time if gpu_batch_time > 0 else 0,
            "queries_per_second_gpu": len(query_embeddings) / gpu_batch_time,
            "queries_per_second_cpu": len(query_embeddings) / cpu_batch_time
        }
    
    async def benchmark_index_building(self) -> Dict[str, Any]:
        """Benchmark index building performance."""
        logger.info("Benchmarking index building performance...")
        
        # This would require rebuilding indexes, which is complex in this context
        # For now, we'll return placeholder data
        return {
            "gpu_index_build_time": 0.0,  # Would need actual measurement
            "cpu_index_build_time": 0.0,  # Would need actual measurement
            "index_build_speedup": 0.0
        }
    
    async def benchmark_memory_usage(self) -> Dict[str, Any]:
        """Benchmark memory usage."""
        try:
            import psutil
            import torch
            
            # Get system memory usage
            system_memory = psutil.virtual_memory()
            
            # Get GPU memory usage if available
            gpu_memory = None
            if torch.cuda.is_available():
                gpu_memory = {
                    "total": torch.cuda.get_device_properties(0).total_memory,
                    "allocated": torch.cuda.memory_allocated(0),
                    "cached": torch.cuda.memory_reserved(0)
                }
            
            return {
                "system_memory": {
                    "total": system_memory.total,
                    "available": system_memory.available,
                    "used": system_memory.used,
                    "percentage": system_memory.percent
                },
                "gpu_memory": gpu_memory
            }
            
        except ImportError:
            logger.warning("psutil or torch not available for memory monitoring")
            return {}
    
    async def run_benchmark(self) -> Dict[str, Any]:
        """Run complete benchmark suite."""
        logger.info("Starting Milvus GPU vs CPU benchmark...")
        
        try:
            await self.initialize()
            await self.prepare_test_data()
            
            # Run benchmarks
            single_query_results = await self.benchmark_single_queries()
            batch_query_results = await self.benchmark_batch_queries()
            index_build_results = await self.benchmark_index_building()
            memory_results = await self.benchmark_memory_usage()
            
            # Compile results
            benchmark_results = {
                "timestamp": time.time(),
                "test_queries": len(self.test_queries),
                "test_documents": len(self.test_documents),
                "single_query": single_query_results,
                "batch_query": batch_query_results,
                "index_building": index_build_results,
                "memory_usage": memory_results,
                "gpu_available": self.gpu_retriever._gpu_available if self.gpu_retriever else False
            }
            
            return benchmark_results
            
        except Exception as e:
            logger.error(f"Benchmark failed: {e}")
            raise
        finally:
            # Cleanup
            if self.gpu_retriever:
                await self.gpu_retriever.disconnect()
            if self.cpu_retriever:
                await self.cpu_retriever.disconnect()
    
    def print_results(self, results: Dict[str, Any]):
        """Print benchmark results in a formatted way."""
        print("\n" + "="*80)
        print("MILVUS GPU vs CPU BENCHMARK RESULTS")
        print("="*80)
        
        print(f"\nTest Configuration:")
        print(f"  Queries: {results['test_queries']}")
        print(f"  Documents: {results['test_documents']}")
        print(f"  GPU Available: {results['gpu_available']}")
        
        print(f"\nSingle Query Performance:")
        single = results['single_query']
        print(f"  GPU Average Time: {single['gpu_avg_time']:.4f}s ± {single['gpu_std_time']:.4f}s")
        print(f"  CPU Average Time: {single['cpu_avg_time']:.4f}s ± {single['cpu_std_time']:.4f}s")
        print(f"  Speedup: {single['speedup']:.2f}x")
        
        print(f"\nBatch Query Performance:")
        batch = results['batch_query']
        print(f"  GPU Batch Time: {batch['gpu_batch_time']:.4f}s")
        print(f"  CPU Batch Time: {batch['cpu_batch_time']:.4f}s")
        print(f"  Batch Speedup: {batch['gpu_batch_speedup']:.2f}x")
        print(f"  GPU QPS: {batch['queries_per_second_gpu']:.2f}")
        print(f"  CPU QPS: {batch['queries_per_second_cpu']:.2f}")
        
        if results['memory_usage']:
            memory = results['memory_usage']
            print(f"\nMemory Usage:")
            if 'system_memory' in memory:
                sys_mem = memory['system_memory']
                print(f"  System Memory: {sys_mem['used']/1024**3:.2f}GB / {sys_mem['total']/1024**3:.2f}GB ({sys_mem['percentage']:.1f}%)")
            if 'gpu_memory' in memory and memory['gpu_memory']:
                gpu_mem = memory['gpu_memory']
                print(f"  GPU Memory: {gpu_mem['allocated']/1024**3:.2f}GB / {gpu_mem['total']/1024**3:.2f}GB")
        
        print("\n" + "="*80)

async def main():
    """Main benchmark execution."""
    benchmark = MilvusBenchmark()
    
    try:
        results = await benchmark.run_benchmark()
        benchmark.print_results(results)
        
        # Save results to file
        results_file = project_root / "benchmark_results.json"
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"\nResults saved to: {results_file}")
        
    except Exception as e:
        logger.error(f"Benchmark execution failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
