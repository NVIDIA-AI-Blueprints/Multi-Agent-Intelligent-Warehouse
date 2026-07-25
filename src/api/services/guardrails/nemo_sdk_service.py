# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
NeMo Guardrails SDK Service Wrapper

Provides integration with NVIDIA NeMo Guardrails SDK using Colang configuration.
This is the new implementation that will replace the pattern-based approach.
"""

import logging
import time
from typing import Dict, Any, Optional, List
from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Try to import NeMo Guardrails SDK
try:
    from nemoguardrails import LLMRails, RailsConfig
    from nemoguardrails.llm.types import Task
    NEMO_SDK_AVAILABLE = True
except ImportError as e:
    NEMO_SDK_AVAILABLE = False
    logger.warning(f"NeMo Guardrails SDK not available: {e}")


class NeMoGuardrailsSDKService:
    """
    NeMo Guardrails SDK Service using Colang configuration.
    
    This service uses the official NeMo Guardrails SDK with Colang-based
    programmable guardrails for intelligent safety validation.
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the NeMo Guardrails SDK service.
        
        Args:
            config_path: Path to the guardrails configuration directory.
                        Defaults to data/config/guardrails/
        """
        if not NEMO_SDK_AVAILABLE:
            raise ImportError(
                "NeMo Guardrails SDK is not installed. "
                "Install it with: pip install nemoguardrails"
            )

        # Determine config path
        if config_path is None:
            # Default to data/config/guardrails/
            project_root = Path(__file__).resolve().parents[4]
            config_path = project_root / "data" / "config" / "guardrails"
        else:
            config_path = Path(config_path)

        if not config_path.exists():
            raise FileNotFoundError(
                f"Guardrails configuration directory not found: {config_path}"
            )

        self.config_path = config_path
        self.rails: Optional[LLMRails] = None
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the NeMo Guardrails SDK with configuration."""
        if self._initialized:
            return

        try:
            logger.info(f"Initializing NeMo Guardrails SDK from: {self.config_path}")

            # Load RailsConfig from the config directory
            config = RailsConfig.from_path(str(self.config_path))

            # Initialize LLMRails
            self.rails = LLMRails(config)

            # Initialize the rails (async operation)
            await self.rails.initialize()

            self._initialized = True
            logger.info("NeMo Guardrails SDK initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize NeMo Guardrails SDK: {e}")
            raise

    async def check_input_safety(
        self, user_input: str, context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Check if user input is safe using NeMo Guardrails SDK.
        
        Args:
            user_input: The user input to check
            context: Optional context dictionary
            
        Returns:
            Dictionary with safety check results:
            {
                "is_safe": bool,
                "violations": List[str] or None,
                "confidence": float,
                "response": str or None,
                "method_used": "sdk"
            }
        """
        if not self._initialized:
            await self.initialize()

        start_time = time.time()

        try:
            # Use NeMo Guardrails to check input
            # The SDK will automatically apply input rails defined in Colang
            result = await self.rails.generate_async(
                messages=[{"role": "user", "content": user_input}]
            )

            # Check if the response indicates a violation was detected
            # If input rails trigger, the response will be a refusal message
            response_text = result.content if hasattr(result, "content") else str(result)

            # Determine if input was blocked by checking for refusal patterns
            is_safe = not self._is_refusal_response(response_text)
            violations = None if is_safe else [f"Input blocked by guardrails: {response_text[:100]}"]

            processing_time = time.time() - start_time

            return {
                "is_safe": is_safe,
                "violations": violations,
                "confidence": 0.95 if is_safe else 0.9,
                "response": response_text if not is_safe else None,
                "processing_time": processing_time,
                "method_used": "sdk",
            }

        except Exception as e:
            logger.error(f"Error in SDK input safety check: {e}")
            processing_time = time.time() - start_time
            # On error, default to safe (fail open) but log the error
            return {
                "is_safe": True,
                "violations": None,
                "confidence": 0.5,
                "response": None,
                "processing_time": processing_time,
                "method_used": "sdk",
            }

    async def check_output_safety(
        self, response: str, context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Check if AI response is safe using NeMo Guardrails SDK.
        
        Args:
            response: The AI response to check
            context: Optional context dictionary
            
        Returns:
            Dictionary with safety check results:
            {
                "is_safe": bool,
                "violations": List[str] or None,
                "confidence": float,
                "response": str or None,
                "method_used": "sdk"
            }
        """
        if not self._initialized:
            await self.initialize()

        start_time = time.time()

        try:
            # Use NeMo Guardrails to check output
            # The SDK will automatically apply output rails defined in Colang
            # We simulate a conversation to trigger output rails
            result = await self.rails.generate_async(
                messages=[
                    {"role": "user", "content": "test"},
                    {"role": "assistant", "content": response}
                ]
            )

            # Check if output rails modified the response
            result_text = result.content if hasattr(result, "content") else str(result)
            
            # If output was modified, it means a violation was detected
            is_safe = result_text == response or not self._is_refusal_response(result_text)
            violations = None if is_safe else [f"Output blocked by guardrails: {result_text[:100]}"]

            processing_time = time.time() - start_time

            return {
                "is_safe": is_safe,
                "violations": violations,
                "confidence": 0.95 if is_safe else 0.9,
                "response": result_text if not is_safe else None,
                "processing_time": processing_time,
                "method_used": "sdk",
            }

        except Exception as e:
            logger.error(f"Error in SDK output safety check: {e}")
            processing_time = time.time() - start_time
            # On error, default to safe (fail open) but log the error
            return {
                "is_safe": True,
                "violations": None,
                "confidence": 0.5,
                "response": None,
                "processing_time": processing_time,
                "method_used": "sdk",
            }

    def _is_refusal_response(self, response: str) -> bool:
        """
        Check if a response indicates a refusal/violation was detected.
        
        Args:
            response: The response text to check
            
        Returns:
            True if the response indicates a refusal/violation
        """
        refusal_indicators = [
            "cannot",
            "cannot provide",
            "cannot ignore",
            "safety is our top priority",
            "security-sensitive",
            "compliance",
            "specialized in warehouse",
        ]
        
        response_lower = response.lower()
        return any(indicator in response_lower for indicator in refusal_indicators)

    async def close(self) -> None:
        """Close the NeMo Guardrails SDK service."""
        if self.rails:
            # Clean up resources if needed
            pass
        self._initialized = False
