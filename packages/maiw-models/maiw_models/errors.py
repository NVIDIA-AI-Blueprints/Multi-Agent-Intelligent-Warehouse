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

    def __init__(
        self, message: str, model_id: str | None = None, timeout_s: float | None = None
    ) -> None:
        super().__init__(message, model_id)
        self.timeout_s = timeout_s


class ModelConfigurationError(ModelGatewayError):
    """Raised when the registry or provider has an invalid configuration."""


class ModelResponseError(ModelGatewayError):
    """Raised when the provider returns an unexpected or malformed response."""


class StructuredOutputError(ModelGatewayError):
    """Raised when structured output parsing fails after the model responded."""


class ModelPolicyViolation(ModelGatewayError):
    """
    Raised BEFORE provider dispatch when the physical model bound to the
    selected role is not an approved MAIW deployment (v2.0.1 round 2).

    ``reason`` is machine-readable: ``UNAPPROVED_MODEL_ID`` (the physical model
    ID is not in the approved deployment table), ``ROLE_MISMATCH`` (the ID is
    approved, but for a different role), ``UNAPPROVED_GENERATION`` or
    ``EMPTY_MODEL_ID``.  No provider call is ever made when this is raised.
    """

    code = "MODEL_POLICY_VIOLATION"

    def __init__(
        self,
        message: str,
        model_id: str | None = None,
        role: str | None = None,
        reason: str = "UNAPPROVED_MODEL_ID",
    ) -> None:
        super().__init__(message, model_id)
        self.role = role
        self.reason = reason


class ModelIdentityMismatch(ModelGatewayError):
    """
    Raised AFTER the provider answered when the model identity the provider
    reports differs from the approved physical model that was dispatched.

    The response is discarded — it is never returned as an approved result and
    never relabelled with the requested model ID.
    """

    code = "MODEL_IDENTITY_MISMATCH"

    def __init__(
        self,
        message: str,
        model_id: str | None = None,
        reported_model_id: str | None = None,
        role: str | None = None,
    ) -> None:
        super().__init__(message, model_id)
        self.reported_model_id = reported_model_id
        self.role = role


class ModelIdentityUnverifiable(ModelGatewayError):
    """
    Raised AFTER the provider answered when its response carries no usable
    model identity — the ``model`` field is missing, empty / whitespace, or not
    a string (v2.0.1 round 3; third re-audit N-1).

    Fail closed: an answer whose physical model cannot be verified against the
    approved deployment that was dispatched is discarded, exactly like a
    mismatch.  ``reason`` is ``MISSING`` or ``MALFORMED``.
    """

    code = "MODEL_IDENTITY_UNVERIFIABLE"

    def __init__(
        self,
        message: str,
        model_id: str | None = None,
        role: str | None = None,
        reason: str = "MISSING",
    ) -> None:
        super().__init__(message, model_id)
        self.role = role
        self.reason = reason
