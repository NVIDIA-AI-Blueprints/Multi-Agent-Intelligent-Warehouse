# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Canonical route-mounting policy for the shipped MAIW app (v2.0.1).

Why this module exists
----------------------
The v2.0.0 independent audit (P1-01) found that ``maiw_api.app:app`` mounted
legacy ``src.api.routers`` wholesale — including ``POST /api/v1/chat``, whose
LLM-driven legacy agent wrote to the warehouse database (``assign_equipment``)
with no DecisionEngine, no approval and no ActionExecutor, unauthenticated.
It also mounted unauthenticated legacy write routes (inventory/WMS/IoT/ERP
CRUD, DB migration/rollback, training subprocess start).

The shipped app therefore mounts legacy routers through one of two views:

``read_only_view(router)``
    Only GET/HEAD routes of the router are mounted. Every POST/PUT/PATCH/DELETE
    route of the legacy router is dropped from the shipped composition. The
    legacy code stays in the tree (it is still used by the dev-only
    ``src/api/app.py``) but is not reachable from the release entrypoint.

``curated_view(router, allow_mutations=...)``
    All read-only routes plus an explicit, reviewed set of non-GET routes.
    Used only where a non-GET route is required and has been classified as
    non-operational (e.g. document upload, which performs bounded inference
    through ModelGateway and records document-workflow state only).

There is deliberately no "mount everything" helper. A new mutating route on a
legacy router does not become reachable from the shipped app until it is added
to an allowlist here — and the canonical route-inventory test
(``tests/api/test_canonical_shipped_app.py``) fails until it is classified.
"""

from __future__ import annotations

from collections.abc import Iterable

from fastapi import APIRouter
from fastapi.routing import APIRoute

#: HTTP methods that cannot change server-side state by contract.
READ_ONLY_METHODS: frozenset[str] = frozenset({"GET", "HEAD", "OPTIONS"})


def _is_read_only(route: APIRoute) -> bool:
    return set(route.methods or ()) <= READ_ONLY_METHODS


def read_only_view(router: APIRouter) -> APIRouter:
    """Return a router containing only the read-only (GET/HEAD) routes."""
    view = APIRouter()
    for route in router.routes:
        if isinstance(route, APIRoute) and _is_read_only(route):
            view.routes.append(route)
    return view


def curated_view(
    router: APIRouter,
    *,
    allow_mutations: Iterable[tuple[str, str]],
) -> APIRouter:
    """
    Return a router with all read-only routes plus the allowlisted mutations.

    ``allow_mutations`` is a set of ``(METHOD, full_path)`` pairs. A route with
    several methods is mounted only if *every* non-read-only method is listed.
    """
    allowed = {(m.upper(), p) for m, p in allow_mutations}
    view = APIRouter()
    for route in router.routes:
        if not isinstance(route, APIRoute):
            continue
        if _is_read_only(route):
            view.routes.append(route)
            continue
        mutating = set(route.methods or ()) - READ_ONLY_METHODS
        if all((m, route.path) in allowed for m in mutating):
            view.routes.append(route)
    return view


def iter_mounted_routes(container: object, _prefix: str = ""):
    """
    Yield ``(method, path, endpoint)`` for every HTTP route reachable from an
    app or router.

    Version-tolerant: older FastAPI copies included routes into ``app.routes``
    as ``APIRoute``; newer FastAPI keeps a lazy ``_IncludedRouter`` wrapper with
    an ``original_router``. Both shapes are walked so the canonical
    route-inventory test cannot pass vacuously on either.
    """
    from starlette.routing import Mount, Route

    for route in getattr(container, "routes", []) or []:
        if isinstance(route, APIRoute) or isinstance(route, Route):
            for method in sorted(route.methods or ()):
                yield method, _prefix + route.path, route.endpoint
        elif hasattr(route, "original_router"):
            ctx = getattr(route, "include_context", None)
            prefix = getattr(ctx, "prefix", "") or ""
            yield from iter_mounted_routes(route.original_router, _prefix + prefix)
        elif isinstance(route, Mount):
            yield from iter_mounted_routes(route, _prefix + route.path)


__all__ = [
    "READ_ONLY_METHODS",
    "read_only_view",
    "curated_view",
    "iter_mounted_routes",
]
