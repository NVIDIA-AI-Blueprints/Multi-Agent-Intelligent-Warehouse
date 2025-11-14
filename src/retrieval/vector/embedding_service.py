"""
Embedding Service for Warehouse Operations

Provides text embedding capabilities for semantic search over
warehouse documentation and operational procedures using NVIDIA NIM.
"""

import logging
from typing import List, Optional, Dict, Any
import numpy as np
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class EmbeddingService:
    """
    Embedding service for generating vector representations of text using NVIDIA NIM.
    
    Uses NV-EmbedQA-E5-v5 model for high-quality embeddings optimized for Q&A tasks.
    """
    
    def __init__(self, model_name: str = "nvidia/nv-embedqa-e5-v5", dimension: int = 1024):
        self.model_name = model_name
        self.dimension = dimension
        self._initialized = False
        self.nim_client = None
    
    async def initialize(self) -> None:
        """Initialize the embedding service with NVIDIA NIM client."""
        try:
            # Import here to avoid circular imports
            from src.api.services.llm.nim_client import get_nim_client
            
            # Initialize NIM client
            self.nim_client = await get_nim_client()
            
            # Test the connection with a simple embedding
            test_embedding = await self._generate_embedding_with_nim("test")
            if len(test_embedding) != self.dimension:
                raise ValueError(f"Expected embedding dimension {self.dimension}, got {len(test_embedding)}")
            
            self._initialized = True
            logger.info(f"Embedding service initialized with NVIDIA NIM model: {self.model_name}")
            
        except Exception as e:
            logger.error(f"Failed to initialize embedding service: {e}")
            raise
    
    async def _generate_embedding_with_nim(self, text: str, input_type: str = "query") -> List[float]:
        """Generate embedding using NVIDIA NIM client."""
        try:
            if not self.nim_client:
                raise RuntimeError("NIM client not initialized")
            
            response = await self.nim_client.generate_embeddings(
                texts=[text],
                model=self.model_name,
                input_type=input_type
            )
            
            if not response.embeddings or len(response.embeddings) == 0:
                raise ValueError("No embeddings returned from NIM client")
            
            return response.embeddings[0]
            
        except Exception as e:
            logger.error(f"Failed to generate embedding with NIM: {e}")
            raise
    
    async def generate_embedding(self, text: str, input_type: str = "query") -> List[float]:
        """
        Generate embedding for a single text using NVIDIA NIM.
        
        Args:
            text: Input text to embed
            input_type: Type of input ("query" or "passage")
            
        Returns:
            List of float values representing the embedding
        """
        try:
            if not self._initialized:
                await self.initialize()
            
            # Generate embedding using NVIDIA NIM
            embedding = await self._generate_embedding_with_nim(text, input_type)
            
            logger.debug(f"Generated embedding for text: {text[:50]}... (dim: {len(embedding)})")
            return embedding
            
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            raise
    
    async def generate_embeddings(self, texts: List[str], input_type: str = "query") -> List[List[float]]:
        """
        Generate embeddings for multiple texts using NVIDIA NIM.
        
        Args:
            texts: List of input texts to embed
            input_type: Type of input ("query" or "passage")
            
        Returns:
            List of embeddings
        """
        try:
            if not self._initialized:
                await self.initialize()
            
            if not self.nim_client:
                raise RuntimeError("NIM client not initialized")
            
            # Use batch processing for better performance
            response = await self.nim_client.generate_embeddings(
                texts=texts,
                model=self.model_name,
                input_type=input_type
            )
            
            if not response.embeddings or len(response.embeddings) != len(texts):
                raise ValueError(f"Expected {len(texts)} embeddings, got {len(response.embeddings) if response.embeddings else 0}")
            
            logger.info(f"Generated {len(response.embeddings)} embeddings using NVIDIA NIM")
            return response.embeddings
            
        except Exception as e:
            logger.error(f"Failed to generate embeddings: {e}")
            raise
    
    async def similarity(self, embedding1: List[float], embedding2: List[float]) -> float:
        """
        Calculate cosine similarity between two embeddings.
        
        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector
            
        Returns:
            Cosine similarity score between -1 and 1
        """
        try:
            # Convert to numpy arrays
            vec1 = np.array(embedding1)
            vec2 = np.array(embedding2)
            
            # Calculate cosine similarity
            dot_product = np.dot(vec1, vec2)
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)
            
            if norm1 == 0 or norm2 == 0:
                return 0.0
            
            similarity = dot_product / (norm1 * norm2)
            return float(similarity)
            
        except Exception as e:
            logger.error(f"Failed to calculate similarity: {e}")
            return 0.0
    
    def get_dimension(self) -> int:
        """Get the embedding dimension."""
        return self.dimension
    
    def get_model_name(self) -> str:
        """Get the model name."""
        return self.model_name

# Global embedding service instance
_embedding_service: Optional[EmbeddingService] = None

async def get_embedding_service() -> EmbeddingService:
    """Get or create the global embedding service instance."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService(model_name="nvidia/nv-embedqa-e5-v5", dimension=1024)
        await _embedding_service.initialize()
    return _embedding_service
