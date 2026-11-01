# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Document approve/reject must not report success it did not achieve.

Nothing records a document approval or rejection, and nothing integrates with a
WMS. The tools and the legacy router (still mounted by the legacy dev server,
``src/api/app.py``) must say so instead of answering "approved"/"rejected".
"""

from __future__ import annotations

import httpx
from fastapi import FastAPI

from src.api.agents.document.action_tools import DocumentActionTools
from src.api.routers import document as document_router


async def test_tools_approve_and_reject_report_not_implemented():
    tools = DocumentActionTools()

    approved = await tools.approve_document("no-such-document", "anyone")
    rejected = await tools.reject_document("no-such-document", "anyone", "x")

    for result in (approved, rejected):
        assert result["success"] is False
        assert result["error"] == "not_implemented"
        assert "not implemented" in result["message"]
        assert "approval_status" not in result
        assert "rejection_status" not in result
        assert "wms_integration_status" not in result


async def test_legacy_router_approve_and_reject_return_501():
    app = FastAPI()
    app.include_router(document_router.router)
    app.dependency_overrides[document_router.get_document_tools] = DocumentActionTools

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        r_approve = await client.post(
            "/api/v1/document/approve/no-such-document",
            data={"approver_id": "anyone"},
        )
        r_reject = await client.post(
            "/api/v1/document/reject/no-such-document",
            data={"rejector_id": "anyone", "rejection_reason": "x"},
        )

    for r in (r_approve, r_reject):
        assert r.status_code == 501, (r.status_code, r.text)
        assert "not implemented" in r.json()["detail"]
