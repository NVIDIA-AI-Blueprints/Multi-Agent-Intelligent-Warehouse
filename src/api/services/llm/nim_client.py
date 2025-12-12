"""
NVIDIA NIM Client for Warehouse Operations

Provides integration with NVIDIA NIM services for LLM and embedding operations.
"""

import logging
import httpx
import json
import asyncio
import hashlib
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


@dataclass
class NIMConfig:
    """NVIDIA NIM configuration."""

    llm_api_key: str = os.getenv("NVIDIA_API_KEY", "")
    llm_base_url: str = os.getenv("LLM_NIM_URL", "https://integrate.api.nvidia.com/v1")
    embedding_api_key: str = os.getenv("EMBEDDING_API_KEY") or os.getenv("NVIDIA_API_KEY", "")
    embedding_base_url: str = os.getenv(
        "EMBEDDING_NIM_URL", "https://integrate.api.nvidia.com/v1"
    )
    llm_model: str = os.getenv("LLM_MODEL", "nvcf:nvidia/llama-3.3-nemotron-super-49b-v1:dep-36is50clLXA5mF69NPgpmw1HJKs")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "nvidia/nv-embedqa-e5-v5")
    timeout: int = int(os.getenv("LLM_CLIENT_TIMEOUT", "120"))  # Increased from 60s to 120s to prevent premature timeouts
    # LLM generation parameters (configurable via environment variables)
    default_temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.1"))
    default_max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "2000"))
    default_top_p: float = float(os.getenv("LLM_TOP_P", "1.0"))
    default_frequency_penalty: float = float(os.getenv("LLM_FREQUENCY_PENALTY", "0.0"))
    default_presence_penalty: float = float(os.getenv("LLM_PRESENCE_PENALTY", "0.0"))


@dataclass
class LLMResponse:
    """LLM response structure."""

    content: str
    usage: Dict[str, int]
    model: str
    finish_reason: str


@dataclass
class EmbeddingResponse:
    """Embedding response structure."""

    embeddings: List[List[float]]
    usage: Dict[str, int]
    model: str


class NIMClient:
    """
    NVIDIA NIM client for LLM and embedding operations.

    Provides async access to NVIDIA's inference microservices for
    warehouse operational intelligence.
    """

    def __init__(self, config: Optional[NIMConfig] = None, enable_cache: bool = True, cache_ttl: int = 300):
        self.config = config or NIMConfig()
        self.enable_cache = enable_cache
        self.cache_ttl = cache_ttl  # Default 5 minutes
        self._response_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_lock = asyncio.Lock()
        self._cache_stats = {"hits": 0, "misses": 0}
        
        # Validate configuration
        self._validate_config()
        
        self.llm_client = httpx.AsyncClient(
            base_url=self.config.llm_base_url,
            timeout=self.config.timeout,
            headers={
                "Authorization": f"Bearer {self.config.llm_api_key}",
                "Content-Type": "application/json",
            },
        )
        self.embedding_client = httpx.AsyncClient(
            base_url=self.config.embedding_base_url,
            timeout=self.config.timeout,
            headers={
                "Authorization": f"Bearer {self.config.embedding_api_key}",
                "Content-Type": "application/json",
            },
        )
    
    def _validate_config(self) -> None:
        """Validate NIM configuration and log warnings for common issues."""
        # Check for common misconfigurations
        if not self.config.llm_api_key or not self.config.llm_api_key.strip():
            logger.warning(
                "NVIDIA_API_KEY is not set or is empty. LLM requests will fail with authentication errors."
            )
        
        # Validate URL format
        if not self.config.llm_base_url.startswith(("http://", "https://")):
            logger.error(
                f"Invalid LLM_NIM_URL format: {self.config.llm_base_url}\n"
                f"   URL must start with http:// or https://"
            )
        
        # Log configuration (without exposing API key)
        # Note: api.brev.dev is valid for certain models (e.g., 49B), 
        # while integrate.api.nvidia.com is used for other NIM endpoints
        logger.info(
            f"NIM Client configured: base_url={self.config.llm_base_url}, "
            f"model={self.config.llm_model}, "
            f"api_key_set={bool(self.config.llm_api_key and self.config.llm_api_key.strip())}, "
            f"timeout={self.config.timeout}s"
        )

    def _normalize_content_for_cache(self, content: str) -> str:
        """Normalize content to improve cache hit rates by removing variable data."""
        import re
        # Remove timestamps (various formats)
        content = re.sub(r'\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}:\d{2}[.\d]*Z?', '', content)
        # Remove task IDs and similar patterns (e.g., TASK_PICK_20251207_121327)
        content = re.sub(r'TASK_[A-Z_]+_\d{8}_\d{6}', 'TASK_ID', content)
        # Remove UUIDs
        content = re.sub(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', 'UUID', content, flags=re.IGNORECASE)
        # Remove specific dates in various formats
        content = re.sub(r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b', 'DATE', content)
        # Normalize whitespace
        content = ' '.join(content.split())
        return content.strip()
    
    def _generate_cache_key(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        top_p: float,
        frequency_penalty: float,
        presence_penalty: float,
    ) -> str:
        """Generate a cache key from LLM request parameters."""
        # Normalize messages for cache key generation
        # Extract only the essential content, ignoring timestamps and other variable data
        normalized_messages = []
        for msg in messages:
            # Only include role and content, normalize content
            content = msg.get("content", "").strip()
            # Normalize content to remove variable data (timestamps, IDs, etc.)
            normalized_content = self._normalize_content_for_cache(content)
            
            normalized_messages.append({
                "role": msg.get("role", "user"),
                "content": normalized_content
            })
        
        # Create cache key from normalized parameters
        # Only include parameters that affect the response
        cache_data = {
            "messages": normalized_messages,
            "temperature": round(temperature, 2),  # Round to avoid float precision issues
            "max_tokens": max_tokens,
            "top_p": round(top_p, 2),
            "frequency_penalty": round(frequency_penalty, 2),
            "presence_penalty": round(presence_penalty, 2),
            "model": self.config.llm_model,
        }
        
        cache_string = json.dumps(cache_data, sort_keys=True)
        cache_key = hashlib.sha256(cache_string.encode()).hexdigest()
        return cache_key
    
    async def _get_cached_response(self, cache_key: str) -> Optional[LLMResponse]:
        """Get cached response if available and not expired."""
        if not self.enable_cache:
            return None
        
        async with self._cache_lock:
            if cache_key not in self._response_cache:
                return None
            
            cached_item = self._response_cache[cache_key]
            expires_at = cached_item.get("expires_at")
            
            # Check if expired
            if expires_at and datetime.now(timezone.utc) > expires_at:
                del self._response_cache[cache_key]
                logger.debug(f"Cache entry expired for key: {cache_key[:16]}...")
                return None
            
            self._cache_stats["hits"] += 1
            logger.info(f"✅ Cache hit for LLM request (key: {cache_key[:16]}...)")
            return cached_item.get("response")
    
    async def _cache_response(self, cache_key: str, response: LLMResponse) -> None:
        """Cache LLM response."""
        if not self.enable_cache:
            return
        
        async with self._cache_lock:
            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(seconds=self.cache_ttl)
            
            self._response_cache[cache_key] = {
                "response": response,
                "expires_at": expires_at,
                "cached_at": now,
            }
            
            logger.debug(f"Cached LLM response (key: {cache_key[:16]}..., TTL: {self.cache_ttl}s)")
    
    async def clear_cache(self) -> None:
        """Clear all cached responses."""
        async with self._cache_lock:
            self._response_cache.clear()
            logger.info("LLM response cache cleared")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_requests = self._cache_stats["hits"] + self._cache_stats["misses"]
        hit_rate = (self._cache_stats["hits"] / total_requests * 100) if total_requests > 0 else 0
        
        return {
            "hits": self._cache_stats["hits"],
            "misses": self._cache_stats["misses"],
            "total_requests": total_requests,
            "hit_rate_percent": round(hit_rate, 2),
            "cached_entries": len(self._response_cache),
            "cache_enabled": self.enable_cache,
        }
    
    async def close(self):
        """Close HTTP clients."""
        await self.llm_client.aclose()
        await self.embedding_client.aclose()

    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
        frequency_penalty: Optional[float] = None,
        presence_penalty: Optional[float] = None,
        stream: bool = False,
        max_retries: int = 3,
    ) -> LLMResponse:
        """
        Generate response using NVIDIA NIM LLM with retry logic.

        Args:
            messages: List of message dictionaries with 'role' and 'content'
            temperature: Sampling temperature (0.0 to 2.0). If None, uses config default.
            max_tokens: Maximum tokens to generate. If None, uses config default.
            top_p: Nucleus sampling parameter (0.0 to 1.0). If None, uses config default.
            frequency_penalty: Frequency penalty (-2.0 to 2.0). If None, uses config default.
            presence_penalty: Presence penalty (-2.0 to 2.0). If None, uses config default.
            stream: Whether to stream the response
            max_retries: Maximum number of retry attempts

        Returns:
            LLMResponse with generated content
        """
        # Use config defaults if parameters are not provided
        temperature = temperature if temperature is not None else self.config.default_temperature
        max_tokens = max_tokens if max_tokens is not None else self.config.default_max_tokens
        top_p = top_p if top_p is not None else self.config.default_top_p
        frequency_penalty = frequency_penalty if frequency_penalty is not None else self.config.default_frequency_penalty
        presence_penalty = presence_penalty if presence_penalty is not None else self.config.default_presence_penalty
        
        # Check cache first (skip for streaming)
        if not stream and self.enable_cache:
            cache_key = self._generate_cache_key(
                messages, temperature, max_tokens, top_p, frequency_penalty, presence_penalty
            )
            cached_response = await self._get_cached_response(cache_key)
            if cached_response:
                return cached_response
            else:
                self._cache_stats["misses"] += 1
        
        payload = {
            "model": self.config.llm_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        
        # Add optional parameters if they differ from defaults
        if top_p != 1.0:
            payload["top_p"] = top_p
        if frequency_penalty != 0.0:
            payload["frequency_penalty"] = frequency_penalty
        if presence_penalty != 0.0:
            payload["presence_penalty"] = presence_penalty

        last_exception = None

        for attempt in range(max_retries):
            try:
                logger.info(f"LLM generation attempt {attempt + 1}/{max_retries}")
                response = await self.llm_client.post("/chat/completions", json=payload)
                response.raise_for_status()

                data = response.json()

                llm_response = LLMResponse(
                    content=data["choices"][0]["message"]["content"],
                    usage=data.get("usage", {}),
                    model=data.get("model", self.config.llm_model),
                    finish_reason=data["choices"][0].get("finish_reason", "stop"),
                )
                
                # Cache the response (skip for streaming)
                if not stream and self.enable_cache:
                    cache_key = self._generate_cache_key(
                        messages, temperature, max_tokens, top_p, frequency_penalty, presence_penalty
                    )
                    await self._cache_response(cache_key, llm_response)
                
                return llm_response

            except (httpx.TimeoutException, asyncio.TimeoutError) as e:
                last_exception = e
                logger.error(
                    f"⏱️ LLM TIMEOUT: Generation attempt {attempt + 1}/{max_retries} timed out after {self.config.timeout}s | "
                    f"Model: {self.config.llm_model} | "
                    f"Max tokens: {max_tokens} | "
                    f"Temperature: {temperature}"
                )
                if attempt < max_retries - 1:
                    # Wait before retry (exponential backoff)
                    wait_time = 2**attempt
                    logger.info(f"Retrying in {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(
                        f"LLM generation failed after {max_retries} attempts due to timeout: {e}"
                    )
                    raise
            except httpx.HTTPStatusError as e:
                last_exception = e
                status_code = e.response.status_code
                error_detail = str(e)
                
                # Log detailed error information
                logger.warning(
                    f"LLM generation attempt {attempt + 1} failed: HTTP {status_code} - {error_detail}"
                )
                
                # Don't retry on client errors (4xx) except 429 (rate limit)
                if status_code == 404:
                    logger.error(
                        f"LLM endpoint not found (404). Check LLM_NIM_URL configuration. "
                        f"Current URL: {self.config.llm_base_url}"
                    )
                    # Don't retry 404 errors - configuration issue
                    raise ConnectionError(
                        f"LLM service endpoint not found. Please check the LLM service configuration."
                    ) from e
                elif status_code == 401 or status_code == 403:
                    logger.error(
                        f"LLM authentication failed ({status_code}). Check NVIDIA_API_KEY configuration."
                    )
                    # Don't retry auth errors
                    raise ConnectionError(
                        f"LLM service authentication failed. Please check API key configuration."
                    ) from e
                elif status_code == 429:
                    # Rate limit - retry with backoff
                    if attempt < max_retries - 1:
                        wait_time = 2**attempt
                        logger.info(f"Rate limited. Retrying in {wait_time} seconds...")
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(f"LLM generation failed after {max_retries} attempts due to rate limiting")
                        raise ConnectionError(
                            "LLM service is currently rate-limited. Please try again in a moment."
                        ) from e
                elif 400 <= status_code < 500:
                    # Other client errors - don't retry
                    logger.error(f"LLM client error ({status_code}): {error_detail}")
                    raise ConnectionError(
                        "LLM service request failed. Please check your request and try again."
                    ) from e
                else:
                    # Server errors (5xx) - retry
                    if attempt < max_retries - 1:
                        wait_time = 2**attempt
                        logger.info(f"Server error ({status_code}). Retrying in {wait_time} seconds...")
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(f"LLM generation failed after {max_retries} attempts: {error_detail}")
                        raise ConnectionError(
                            "LLM service is temporarily unavailable. Please try again later."
                        ) from e
            except httpx.RequestError as e:
                last_exception = e
                logger.warning(f"LLM generation attempt {attempt + 1} failed: Request error - {e}")
                if attempt < max_retries - 1:
                    # Wait before retry (exponential backoff)
                    wait_time = 2**attempt
                    logger.info(f"Retrying in {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(
                        f"LLM generation failed after {max_retries} attempts: {e}"
                    )
                    raise ConnectionError(
                        "Unable to connect to LLM service. Please check your network connection and service configuration."
                    ) from e
            except Exception as e:
                last_exception = e
                logger.warning(f"LLM generation attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    # Wait before retry (exponential backoff)
                    wait_time = 2**attempt
                    logger.info(f"Retrying in {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(
                        f"LLM generation failed after {max_retries} attempts: {e}"
                    )
                    raise ConnectionError(
                        "LLM service error occurred. Please try again or contact support if the issue persists."
                    ) from e

    async def generate_embeddings(
        self, texts: List[str], model: Optional[str] = None, input_type: str = "query"
    ) -> EmbeddingResponse:
        """
        Generate embeddings using NVIDIA NIM embedding service.

        Args:
            texts: List of texts to embed
            model: Embedding model to use (optional)
            input_type: Type of input ("query" or "passage")

        Returns:
            EmbeddingResponse with embeddings
        """
        try:
            payload = {
                "model": model or self.config.embedding_model,
                "input": texts,
                "input_type": input_type,
            }

            response = await self.embedding_client.post("/embeddings", json=payload)
            response.raise_for_status()

            data = response.json()

            return EmbeddingResponse(
                embeddings=[item["embedding"] for item in data["data"]],
                usage=data.get("usage", {}),
                model=data.get("model", self.config.embedding_model),
            )

        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            raise

    async def health_check(self) -> Dict[str, bool]:
        """
        Check health of NVIDIA NIM services.

        Returns:
            Dictionary with service health status
        """
        try:
            # Test LLM service
            llm_healthy = False
            try:
                test_response = await self.generate_response(
                    [{"role": "user", "content": "Hello"}], max_tokens=10
                )
                llm_healthy = bool(test_response.content)
            except Exception:
                pass

            # Test embedding service
            embedding_healthy = False
            try:
                test_embeddings = await self.generate_embeddings(["test"])
                embedding_healthy = bool(test_embeddings.embeddings)
            except Exception:
                pass

            return {
                "llm_service": llm_healthy,
                "embedding_service": embedding_healthy,
                "overall": llm_healthy and embedding_healthy,
            }

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {"llm_service": False, "embedding_service": False, "overall": False}


# Global NIM client instance
_nim_client: Optional[NIMClient] = None


async def get_nim_client(enable_cache: bool = True, cache_ttl: int = 300) -> NIMClient:
    """Get or create the global NIM client instance."""
    global _nim_client
    if _nim_client is None:
        # Enable caching by default for better performance
        cache_enabled = os.getenv("LLM_CACHE_ENABLED", "true").lower() == "true"
        cache_ttl_seconds = int(os.getenv("LLM_CACHE_TTL_SECONDS", str(cache_ttl)))
        _nim_client = NIMClient(enable_cache=cache_enabled and enable_cache, cache_ttl=cache_ttl_seconds)
        logger.info(f"NIM Client initialized with caching: {cache_enabled and enable_cache} (TTL: {cache_ttl_seconds}s)")
    return _nim_client


async def close_nim_client() -> None:
    """Close the global NIM client instance."""
    global _nim_client
    if _nim_client:
        await _nim_client.close()
        _nim_client = None
