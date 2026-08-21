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

"""Typed error hierarchy for ModelGateway — no raw provider exceptions cross agent boundaries."""

from __future__ import annotations


class ModelGatewayError(Exception):
    """Base class for all ModelGateway errors."""

    def __init__(self, message: str, model_id: str | None = None) -> None:
        super().__init__(message)
        self.model_id = model_id


class ModelUnavailable(ModelGatewayError):
    """Raised when no enabled model can serve the request (all disabled or unreachable)."""


class ModelTimeout(ModelGatewayError):
    """Raised when the model provider did not respond within the deadline."""

    def __init__(self, message: str, model_id: str | None = None, timeout_s: float | None = None) -> None:
        super().__init__(message, model_id)
        self.timeout_s = timeout_s


class ModelConfigurationError(ModelGatewayError):
    """Raised when the registry or provider has an invalid configuration."""


class ModelResponseError(ModelGatewayError):
    """Raised when the provider returns an unexpected or malformed response."""


class StructuredOutputError(ModelGatewayError):
    """Raised when structured output parsing fails after the model responded."""
