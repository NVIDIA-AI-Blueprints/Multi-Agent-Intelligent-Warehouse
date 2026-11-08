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
Prometheus metrics for the MAIW API.

The API exports HTTP request counts and latency, labelled by route template,
and ``warehouse_system_info`` with the release version. ``GET /api/v1/metrics``
serves them. The business metrics (``warehouse_*`` tasks, safety, equipment and
so on) were removed in #277: nothing in the shipped app ever set them.
"""

import logging
import os

from fastapi import Request, Response
from fastapi.responses import PlainTextResponse
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Histogram,
    Info,
    generate_latest,
)

logger = logging.getLogger(__name__)

http_requests_total = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "endpoint", "status"]
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
)

system_info = Info("warehouse_system_info", "MAIW API release information")

# Label for requests that matched no route. Using the raw path instead would
# create one Prometheus series per distinct URL.
UNMATCHED_ENDPOINT = "unmatched"

# Mutated in place: set once system_info has been filled.
_system_info_state = {"set": False}


def endpoint_label(request: Request) -> str:
    """The route template a request matched, e.g. ``/api/v1/procedures/{procedure_id}``.

    Labelling by raw path would create a new series for every distinct ID in a
    URL. Requests that matched no route (404s) share one fixed label.
    """
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) and path else UNMATCHED_ENDPOINT


def _ensure_system_info() -> None:
    """Fill ``warehouse_system_info`` from the version service, once."""
    if _system_info_state["set"]:
        return
    try:
        from src.api.services.version import version_service

        info = version_service.get_version_info()
        version = str(info.get("version") or "unknown")
        git_sha = str(info.get("git_sha") or "unknown")
        environment = str(info.get("environment") or "unknown")
    except Exception:
        logger.warning("Release version not available for metrics", exc_info=True)
        version, git_sha = "unknown", "unknown"
        environment = os.getenv("ENVIRONMENT", "development")
    system_info.info(
        {
            "version": version,
            "git_sha": git_sha,
            "service": "maiw-api",
            "environment": environment,
        }
    )
    _system_info_state["set"] = True


def get_metrics_response() -> PlainTextResponse:
    """Generate the Prometheus metrics response."""
    _ensure_system_info()
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def record_request_metrics(request: Request, response: Response, duration: float):
    """Record one HTTP request: count by method, route template and status,
    and latency by method and route template."""
    endpoint = endpoint_label(request)
    http_requests_total.labels(
        method=request.method, endpoint=endpoint, status=str(response.status_code)
    ).inc()
    http_request_duration_seconds.labels(
        method=request.method, endpoint=endpoint
    ).observe(duration)
