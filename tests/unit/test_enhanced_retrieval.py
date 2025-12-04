#!/usr/bin/env python3
"""
Test script for Enhanced Vector Search Optimization

Demonstrates the new chunking service and enhanced retrieval capabilities
with 512-token chunks, 64-token overlap, and optimized retrieval.
"""

import asyncio
import logging
import sys
import pytest
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.retrieval.vector.chunking_service import ChunkingService, Chunk
from src.retrieval.vector.enhanced_retriever import EnhancedVectorRetriever, RetrievalConfig
from src.retrieval.vector.embedding_service import EmbeddingService
from src.retrieval.vector.milvus_retriever import MilvusRetriever, MilvusConfig
from src.retrieval.enhanced_hybrid_retriever import EnhancedHybridRetriever, SearchContext

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Sample warehouse documents for testing
SAMPLE_DOCUMENTS = [
    {
        "content": """
        Forklift Safety Procedures
        
        Before operating any forklift, operators must complete a pre-operation inspection checklist.
        This includes checking the hydraulic system, brakes, steering, and load backrest.
        All operators must be certified and wear appropriate PPE including hard hats and safety shoes.
        
        When operating the forklift, maintain a safe speed and always look in the direction of travel.
        Never exceed the rated capacity of the forklift and ensure loads are properly secured.
        Use the horn when approaching intersections and always yield to pedestrians.
        
        After operation, park the forklift in designated areas with the forks lowered and parking brake engaged.
        Report any mechanical issues immediately to the maintenance department.
        """,
        "category": "safety",
        "section": "equipment_operations"
    },
    {
        "content": """
        Inventory Management Best Practices
        
        Regular cycle counting is essential for maintaining accurate inventory records.
        Conduct cycle counts on a rotating basis, focusing on high-value and fast-moving items.
        Use barcode scanners to ensure accurate data entry and reduce human error.
        
        Implement ABC analysis to categorize items based on their value and usage frequency.
        Class A items require the most attention and should be counted monthly.
        Class B items should be counted quarterly, and Class C items annually.
        
        Maintain proper storage conditions for all inventory items.
        Store hazardous materials in designated areas with appropriate safety signage.
        Keep accurate records of all inventory movements and adjustments.
        """,
        "category": "inventory",
        "section": "management"
    },
    {
        "content": """
        Equipment Maintenance Schedule
        
        All warehouse equipment requires regular maintenance to ensure optimal performance and safety.
        Forklifts should be serviced every 250 hours of operation or monthly, whichever comes first.
        Conveyor systems need weekly inspections and monthly deep cleaning.
        
        Battery-powered equipment requires daily charging and weekly water level checks.
        Replace batteries every 18-24 months depending on usage patterns.
        Keep detailed maintenance logs for all equipment including dates, services performed, and parts replaced.
        
        Schedule preventive maintenance during low-activity periods to minimize operational disruption.
        Train maintenance staff on proper procedures and safety protocols.
        Maintain an inventory of critical spare parts for quick repairs.
        """,
        "category": "maintenance",
        "section": "equipment_care"
    }
]

@pytest.mark.asyncio
async def test_chunking_service():
    """Test the enhanced chunking service."""
    logger.info("Testing Chunking Service...")
    
    # Initialize chunking service
    chunking_service = ChunkingService(
        chunk_size=512,
        overlap_size=64,
        min_chunk_size=100
    )
    
    # Test chunking with sample documents
    all_chunks = []
    for i, doc in enumerate(SAMPLE_DOCUMENTS):
        chunks = chunking_service.create_chunks(
            text=doc["content"],
            source_id=f"doc_{i+1}",
            source_type="manual",
            category=doc["category"],
            section=doc["section"]
        )
        all_chunks.extend(chunks)
        logger.info(f"Document {i+1}: Created {len(chunks)} chunks")
    
    # Display chunk statistics
    stats = chunking_service.get_chunk_statistics(all_chunks)
    logger.info(f"Chunk Statistics: {stats}")
    
    # Display sample chunks
    for i, chunk in enumerate(all_chunks[:3]):  # Show first 3 chunks
        logger.info(f"Chunk {i+1}:")
        logger.info(f"  ID: {chunk.metadata.chunk_id}")
        logger.info(f"  Tokens: {chunk.metadata.token_count}")
        logger.info(f"  Quality: {chunk.metadata.quality_score:.2f}")
        logger.info(f"  Keywords: {chunk.metadata.keywords[:5]}")
        logger.info(f"  Content: {chunk.content[:100]}...")
        logger.info("")
    
    return all_chunks

@pytest.mark.asyncio
async def test_enhanced_retrieval():
    """Test the enhanced retrieval system."""
    logger.info("Testing Enhanced Retrieval...")
    
    embedding_service = None
    milvus_retriever = None
    enhanced_retriever = None
    
    try:
        # Initialize components
        embedding_service = EmbeddingService()
        await embedding_service.initialize()
        
        milvus_config = MilvusConfig()
        milvus_retriever = MilvusRetriever(milvus_config)
        
        # Initialize enhanced retriever
        retrieval_config = RetrievalConfig(
            initial_top_k=12,
            final_top_k=6,
            min_similarity_threshold=0.3,
            min_relevance_threshold=0.35,
            evidence_threshold=0.35,
            min_sources=2
        )
        
        enhanced_retriever = EnhancedVectorRetriever(
            milvus_retriever=milvus_retriever,
            embedding_service=embedding_service,
            config=retrieval_config
        )
        
        # Test queries
        test_queries = [
            "What are the forklift safety procedures?",
            "How should I maintain warehouse equipment?",
            "What is the cycle counting process?",
            "ATPs for SKU123",
            "equipment status for forklift-001"
        ]
        
        for query in test_queries:
            logger.info(f"Testing query: '{query}'")
            
            # Perform search
            results, metadata = await enhanced_retriever.search(query)
            
            logger.info(f"  Results: {len(results)}")
            logger.info(f"  Evidence Score: {metadata.get('avg_evidence_score', 0):.3f}")
            logger.info(f"  Confidence: {metadata.get('confidence_level', 'unknown')}")
            logger.info(f"  Sources: {metadata.get('unique_sources', 0)}")
            logger.info(f"  Categories: {metadata.get('unique_categories', 0)}")
            
            # Check if clarification is needed
            if enhanced_retriever.should_ask_clarifying_question(metadata):
                clarifying_question = enhanced_retriever.generate_clarifying_question(query, metadata)
                logger.info(f"  Clarifying Question: {clarifying_question}")
            
            logger.info("")
    finally:
        # Cleanup
        if embedding_service and hasattr(embedding_service, 'close'):
            try:
                await embedding_service.close()
            except Exception as e:
                logger.warning(f"Error closing embedding service: {e}")
        if milvus_retriever and hasattr(milvus_retriever, 'close'):
            try:
                await milvus_retriever.close()
            except Exception as e:
                logger.warning(f"Error closing milvus retriever: {e}")

@pytest.mark.asyncio
async def test_hybrid_retrieval():
    """Test the enhanced hybrid retrieval system."""
    logger.info("Testing Enhanced Hybrid Retrieval...")
    
    embedding_service = None
    milvus_retriever = None
    hybrid_retriever = None
    
    try:
        # Initialize components
        embedding_service = EmbeddingService()
        await embedding_service.initialize()
        
        milvus_config = MilvusConfig()
        milvus_retriever = MilvusRetriever(milvus_config)
        
        # Initialize hybrid retriever
        hybrid_retriever = EnhancedHybridRetriever(
            milvus_retriever=milvus_retriever,
            embedding_service=embedding_service
        )
        
        # Test different query types
        test_contexts = [
            SearchContext(
                query="What are the forklift safety procedures?",
                search_type="hybrid",
                limit=6
            ),
            SearchContext(
                query="ATPs for SKU123",
                search_type="sql",
                limit=6
            ),
            SearchContext(
                query="How should I maintain warehouse equipment?",
                search_type="vector",
                limit=6
            )
        ]
        
        for context in test_contexts:
            logger.info(f"Testing {context.search_type} query: '{context.query}'")
            
            # Perform search
            response = await hybrid_retriever.search(context)
            
            logger.info(f"  Search Type: {response.search_type}")
            logger.info(f"  Results: {response.total_results}")
            logger.info(f"  Evidence Score: {response.evidence_score:.3f}")
            logger.info(f"  Confidence: {response.confidence_level}")
            logger.info(f"  Sources: {response.sources}")
            logger.info(f"  Categories: {response.categories}")
            logger.info(f"  Requires Clarification: {response.requires_clarification}")
            
            if response.clarifying_question:
                logger.info(f"  Clarifying Question: {response.clarifying_question}")
            
            logger.info("")
    finally:
        # Cleanup
        if embedding_service and hasattr(embedding_service, 'close'):
            try:
                await embedding_service.close()
            except Exception as e:
                logger.warning(f"Error closing embedding service: {e}")
        if milvus_retriever and hasattr(milvus_retriever, 'close'):
            try:
                await milvus_retriever.close()
            except Exception as e:
                logger.warning(f"Error closing milvus retriever: {e}")

async def main():
    """Main test function."""
    logger.info("Starting Enhanced Vector Search Optimization Tests")
    logger.info("=" * 60)
    
    try:
        # Test chunking service
        chunks = await test_chunking_service()
        logger.info("✅ Chunking Service Test Completed")
        
        # Test enhanced retrieval
        await test_enhanced_retrieval()
        logger.info("✅ Enhanced Retrieval Test Completed")
        
        # Test hybrid retrieval
        await test_hybrid_retrieval()
        logger.info("✅ Hybrid Retrieval Test Completed")
        
        logger.info("=" * 60)
        logger.info("🎉 All tests completed successfully!")
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
