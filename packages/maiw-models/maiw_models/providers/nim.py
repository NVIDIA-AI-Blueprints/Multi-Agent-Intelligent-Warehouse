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
NVIDIA NIM provider for ModelGateway.

Wraps the existing NIMClient rather than reimplementing transport,
retry, or timeout logic.  Translates ModelRequest → NIMClient call,
translates provider errors → typed ModelGateway errors.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from maiw_mcp.deadline import RequestDeadlineExceeded

from maiw_models.providers.nim_client import LLMResponse, NIMClient

from ..errors import ModelResponseError, ModelTimeout, ModelUnavailable
from ..models import ModelCapability, ModelRequest, ReasoningLevel

logger = logging.getLogger(__name__)


class NIMProvider:
    """
    Calls NVIDIA NIM on behalf of ModelGateway.

    The provider:
    - selects the concrete model_id from the route decision
    - translates ReasoningLevel → enable_thinking flag for Nemotron models
    - normalises provider errors into typed ModelGateway exceptions
    - does NOT own retry logic (NIMClient handles that)
    """

    def __init__(self, nim_client: NIMClient) -> None:
        self._nim_client = nim_client

    async def call(
        self,
        *,
        model_id: str,
        request: ModelRequest,
        capability: ModelCapability,
    ) -> LLMResponse:
        """
        Invoke NIM with the resolved model and return a raw LLMResponse.

        Raises:
            ModelTimeout     – when NIMClient raises TimeoutException
            ModelUnavailable – when NIMClient raises ConnectionError (endpoint down)
            ModelResponseError – for other provider errors
        """
        enable_thinking = request.reasoning == ReasoningLevel.HIGH
        try:
            return await self._nim_client.generate_response(
                messages=request.messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                stream=request.stream,
                enable_thinking=enable_thinking,
                model_override=model_id,
                deadline=request.deadline,
            )
        except RequestDeadlineExceeded:
            raise  # parent deadline exhaustion — not a ModelTimeout
        except (httpx.TimeoutException, asyncio.TimeoutError) as exc:
            raise ModelTimeout(
                f"NIM model {model_id} timed out: {exc}",
                model_id=model_id,
            ) from exc
        except ConnectionError as exc:
            raise ModelUnavailable(
                f"NIM model {model_id} unreachable: {exc}",
                model_id=model_id,
            ) from exc
        except Exception as exc:
            raise ModelResponseError(
                f"NIM model {model_id} returned an unexpected error: {exc}",
                model_id=model_id,
            ) from exc
