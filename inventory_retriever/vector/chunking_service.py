"""
Advanced Chunking Service for Vector Search Optimization

Implements intelligent text chunking with 512-token chunks, 64-token overlap,
metadata tracking, deduplication, and quality validation for optimal RAG performance.
"""

import logging
import hashlib
import re
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass
from datetime import datetime
import tiktoken

logger = logging.getLogger(__name__)

@dataclass
class ChunkMetadata:
    """Metadata for a text chunk."""
    chunk_id: str
    source_id: str
    source_type: str  # 'document', 'manual', 'sop', 'policy'
    chunk_index: int
    total_chunks: int
    token_count: int
    char_count: int
    start_position: int
    end_position: int
    created_at: datetime
    quality_score: float
    keywords: List[str]
    category: str
    section: Optional[str] = None
    page_number: Optional[int] = None

@dataclass
class Chunk:
    """A text chunk with metadata."""
    content: str
    metadata: ChunkMetadata
    embedding: Optional[List[float]] = None

class ChunkingService:
    """
    Advanced chunking service for vector search optimization.
    
    Features:
    - 512-token chunks with 64-token overlap
    - Intelligent sentence boundary detection
    - Metadata tracking for source attribution
    - Deduplication to avoid redundant information
    - Quality validation for content completeness
    - Configurable parameters for different content types
    """
    
    def __init__(
        self,
        chunk_size: int = 512,
        overlap_size: int = 64,
        min_chunk_size: int = 100,
        model_name: str = "gpt-3.5-turbo"
    ):
        self.chunk_size = chunk_size
        self.overlap_size = overlap_size
        self.min_chunk_size = min_chunk_size
        self.model_name = model_name
        
        # Initialize tokenizer
        try:
            self.tokenizer = tiktoken.encoding_for_model(model_name)
        except KeyError:
            # Fallback to cl100k_base encoding
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
        
        # Track processed chunks for deduplication
        self._processed_hashes: Set[str] = set()
        
        logger.info(f"ChunkingService initialized: chunk_size={chunk_size}, overlap={overlap_size}")
    
    def create_chunks(
        self,
        text: str,
        source_id: str,
        source_type: str = "document",
        category: str = "general",
        section: Optional[str] = None,
        page_number: Optional[int] = None
    ) -> List[Chunk]:
        """
        Create chunks from text with intelligent boundary detection.
        
        Args:
            text: Input text to chunk
            source_id: Unique identifier for the source document
            source_type: Type of source (document, manual, sop, policy)
            category: Content category for classification
            section: Optional section name
            page_number: Optional page number
            
        Returns:
            List of Chunk objects with metadata
        """
        try:
            # Clean and preprocess text
            cleaned_text = self._preprocess_text(text)
            
            # Split into sentences for better boundary detection
            sentences = self._split_into_sentences(cleaned_text)
            
            # Create chunks with overlap
            chunks = self._create_chunks_with_overlap(
                sentences, source_id, source_type, category, section, page_number
            )
            
            # Apply deduplication
            chunks = self._deduplicate_chunks(chunks)
            
            # Validate chunk quality
            chunks = self._validate_chunk_quality(chunks)
            
            logger.info(f"Created {len(chunks)} chunks from source {source_id}")
            return chunks
            
        except Exception as e:
            logger.error(f"Failed to create chunks: {e}")
            return []
    
    def _preprocess_text(self, text: str) -> str:
        """Clean and preprocess text for chunking."""
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove special characters that might interfere with chunking
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
        
        # Normalize line breaks
        text = re.sub(r'\n+', '\n', text)
        
        return text.strip()
    
    def _split_into_sentences(self, text: str) -> List[str]:
        """Split text into sentences for better chunking boundaries."""
        # Enhanced sentence splitting regex
        sentence_pattern = r'(?<=[.!?])\s+(?=[A-Z])|(?<=[.!?])\s*\n\s*(?=[A-Z])'
        sentences = re.split(sentence_pattern, text)
        
        # Filter out empty sentences
        sentences = [s.strip() for s in sentences if s.strip()]
        
        return sentences
    
    def _create_chunks_with_overlap(
        self,
        sentences: List[str],
        source_id: str,
        source_type: str,
        category: str,
        section: Optional[str],
        page_number: Optional[int]
    ) -> List[Chunk]:
        """Create chunks with overlap from sentences."""
        chunks = []
        current_chunk = []
        current_tokens = 0
        chunk_index = 0
        position = 0
        
        for i, sentence in enumerate(sentences):
            sentence_tokens = len(self.tokenizer.encode(sentence))
            
            # Check if adding this sentence would exceed chunk size
            if current_tokens + sentence_tokens > self.chunk_size and current_chunk:
                # Create chunk from current content
                chunk_content = ' '.join(current_chunk)
                chunk = self._create_chunk(
                    chunk_content, source_id, source_type, category,
                    section, page_number, chunk_index, position,
                    position + len(chunk_content)
                )
                chunks.append(chunk)
                
                # Start new chunk with overlap
                overlap_sentences = self._get_overlap_sentences(current_chunk)
                current_chunk = overlap_sentences + [sentence]
                current_tokens = sum(len(self.tokenizer.encode(s)) for s in current_chunk)
                chunk_index += 1
                position += len(chunk_content) - len(' '.join(overlap_sentences))
            else:
                current_chunk.append(sentence)
                current_tokens += sentence_tokens
        
        # Add final chunk if there's remaining content
        if current_chunk:
            chunk_content = ' '.join(current_chunk)
            chunk = self._create_chunk(
                chunk_content, source_id, source_type, category,
                section, page_number, chunk_index, position,
                position + len(chunk_content)
            )
            chunks.append(chunk)
        
        return chunks
    
    def _get_overlap_sentences(self, sentences: List[str]) -> List[str]:
        """Get sentences for overlap based on token count."""
        overlap_sentences = []
        overlap_tokens = 0
        
        # Start from the end and work backwards
        for sentence in reversed(sentences):
            sentence_tokens = len(self.tokenizer.encode(sentence))
            if overlap_tokens + sentence_tokens <= self.overlap_size:
                overlap_sentences.insert(0, sentence)
                overlap_tokens += sentence_tokens
            else:
                break
        
        return overlap_sentences
    
    def _create_chunk(
        self,
        content: str,
        source_id: str,
        source_type: str,
        category: str,
        section: Optional[str],
        page_number: Optional[int],
        chunk_index: int,
        start_position: int,
        end_position: int
    ) -> Chunk:
        """Create a Chunk object with metadata."""
        # Generate unique chunk ID
        chunk_id = self._generate_chunk_id(source_id, chunk_index, content)
        
        # Calculate token count
        token_count = len(self.tokenizer.encode(content))
        
        # Extract keywords
        keywords = self._extract_keywords(content)
        
        # Calculate quality score
        quality_score = self._calculate_quality_score(content, token_count)
        
        # Create metadata
        metadata = ChunkMetadata(
            chunk_id=chunk_id,
            source_id=source_id,
            source_type=source_type,
            chunk_index=chunk_index,
            total_chunks=0,  # Will be updated later
            token_count=token_count,
            char_count=len(content),
            start_position=start_position,
            end_position=end_position,
            created_at=datetime.now(),
            quality_score=quality_score,
            keywords=keywords,
            category=category,
            section=section,
            page_number=page_number
        )
        
        return Chunk(content=content, metadata=metadata)
    
    def _generate_chunk_id(self, source_id: str, chunk_index: int, content: str) -> str:
        """Generate unique chunk ID."""
        content_hash = hashlib.md5(content.encode()).hexdigest()[:8]
        return f"{source_id}_chunk_{chunk_index}_{content_hash}"
    
    def _extract_keywords(self, content: str) -> List[str]:
        """Extract keywords from content."""
        # Simple keyword extraction (can be enhanced with NLP libraries)
        words = re.findall(r'\b[a-zA-Z]{3,}\b', content.lower())
        
        # Remove common stop words
        stop_words = {
            'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with',
            'by', 'from', 'up', 'about', 'into', 'through', 'during', 'before',
            'after', 'above', 'below', 'between', 'among', 'is', 'are', 'was',
            'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does',
            'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must',
            'can', 'this', 'that', 'these', 'those', 'a', 'an', 'as', 'if',
            'when', 'where', 'why', 'how', 'all', 'any', 'both', 'each', 'few',
            'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only',
            'own', 'same', 'so', 'than', 'too', 'very', 'just', 'now'
        }
        
        keywords = [word for word in words if word not in stop_words]
        
        # Return top 10 most frequent keywords
        from collections import Counter
        return [word for word, count in Counter(keywords).most_common(10)]
    
    def _calculate_quality_score(self, content: str, token_count: int) -> float:
        """Calculate quality score for chunk content."""
        score = 1.0
        
        # Penalize very short chunks
        if token_count < self.min_chunk_size:
            score *= 0.5
        
        # Penalize chunks that are too long
        if token_count > int(self.chunk_size * 1.2):
            score *= 0.8
        
        # Reward chunks with good sentence structure
        sentences = self._split_into_sentences(content)
        if len(sentences) > 1:
            score *= 1.1
        
        # Reward chunks with diverse vocabulary
        unique_words = len(set(re.findall(r'\b[a-zA-Z]+\b', content.lower())))
        if unique_words > int(token_count * 0.3):
            score *= 1.1
        
        # Penalize chunks with excessive repetition
        words = re.findall(r'\b[a-zA-Z]+\b', content.lower())
        if words:
            from collections import Counter
            word_counts = Counter(words)
            most_common_count = word_counts.most_common(1)[0][1] if word_counts else 0
            if most_common_count > int(len(words) * 0.3):
                score *= 0.8
        
        return min(score, 1.0)
    
    def _deduplicate_chunks(self, chunks: List[Chunk]) -> List[Chunk]:
        """Remove duplicate chunks based on content similarity."""
        unique_chunks = []
        
        for chunk in chunks:
            # Create content hash for deduplication
            content_hash = hashlib.md5(chunk.content.encode()).hexdigest()
            
            if content_hash not in self._processed_hashes:
                unique_chunks.append(chunk)
                self._processed_hashes.add(content_hash)
            else:
                logger.debug(f"Skipping duplicate chunk: {chunk.metadata.chunk_id}")
        
        return unique_chunks
    
    def _validate_chunk_quality(self, chunks: List[Chunk]) -> List[Chunk]:
        """Validate and filter chunks based on quality criteria."""
        valid_chunks = []
        
        for chunk in chunks:
            # Check minimum quality score
            if chunk.metadata.quality_score < 0.3:
                logger.debug(f"Filtering low-quality chunk: {chunk.metadata.chunk_id}")
                continue
            
            # Check minimum token count
            if chunk.metadata.token_count < self.min_chunk_size:
                logger.debug(f"Filtering too-short chunk: {chunk.metadata.chunk_id}")
                continue
            
            # Check for meaningful content
            if len(chunk.content.strip()) < 50:
                logger.debug(f"Filtering too-short content chunk: {chunk.metadata.chunk_id}")
                continue
            
            valid_chunks.append(chunk)
        
        # Update total_chunks in metadata
        for i, chunk in enumerate(valid_chunks):
            chunk.metadata.total_chunks = len(valid_chunks)
            chunk.metadata.chunk_index = i
        
        logger.info(f"Validated {len(valid_chunks)} chunks out of {len(chunks)}")
        return valid_chunks
    
    def get_chunk_statistics(self, chunks: List[Chunk]) -> Dict[str, Any]:
        """Get statistics about a set of chunks."""
        if not chunks:
            return {}
        
        token_counts = [chunk.metadata.token_count for chunk in chunks]
        quality_scores = [chunk.metadata.quality_score for chunk in chunks]
        
        return {
            "total_chunks": len(chunks),
            "avg_tokens_per_chunk": sum(token_counts) / len(token_counts),
            "min_tokens": min(token_counts),
            "max_tokens": max(token_counts),
            "avg_quality_score": sum(quality_scores) / len(quality_scores),
            "min_quality_score": min(quality_scores),
            "max_quality_score": max(quality_scores),
            "sources": len(set(chunk.metadata.source_id for chunk in chunks)),
            "categories": len(set(chunk.metadata.category for chunk in chunks))
        }
