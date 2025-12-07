"""
NVIDIA NIM Client for Warehouse Operations

Provides integration with NVIDIA NIM services for LLM and embedding operations.
"""

import logging
import httpx
import json
import asyncio
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


@dataclass
class NIMConfig:
    """NVIDIA NIM configuration."""

    llm_api_key: str = os.getenv("NVIDIA_API_KEY", "")
    llm_base_url: str = os.getenv("LLM_NIM_URL", "https://integrate.api.nvidia.com/v1")
    embedding_api_key: str = os.getenv("NVIDIA_API_KEY", "")
    embedding_base_url: str = os.getenv(
        "EMBEDDING_NIM_URL", "https://integrate.api.nvidia.com/v1"
    )
    llm_model: str = os.getenv("LLM_MODEL", "nvidia/llama-3.3-nemotron-super-49b-v1.5")
    embedding_model: str = "nvidia/nv-embedqa-e5-v5"
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

    def __init__(self, config: Optional[NIMConfig] = None):
        self.config = config or NIMConfig()
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

                return LLMResponse(
                    content=data["choices"][0]["message"]["content"],
                    usage=data.get("usage", {}),
                    model=data.get("model", self.config.llm_model),
                    finish_reason=data["choices"][0].get("finish_reason", "stop"),
                )

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
                    raise

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


async def get_nim_client() -> NIMClient:
    """Get or create the global NIM client instance."""
    global _nim_client
    if _nim_client is None:
        _nim_client = NIMClient()
    return _nim_client


async def close_nim_client() -> None:
    """Close the global NIM client instance."""
    global _nim_client
    if _nim_client:
        await _nim_client.close()
        _nim_client = None
