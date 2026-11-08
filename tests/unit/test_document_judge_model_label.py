# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Document results name the judge model that actually answered.

The Large LLM Judge goes through ModelGateway at HIGH reasoning, which routes
to Nemotron 3 Ultra by default; hosted Nemotron 3 Super is disabled. The
judge records the model that answered (``JudgeEvaluation.judge_model``), but
``DocumentActionTools`` overwrote it with the fixed label
"Nemotron 3 Super 120B" in the stored quality score and the validation-stage
result, and the upload response, the MCP document agent and the UI named
Super too. Now the stored result keeps the judge's own model, and the fixed
label, used only when the judge reported none, names the route.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.api.agents.document.action_tools import DocumentActionTools
from src.api.agents.document.validation.large_llm_judge import JudgeEvaluation

REPO_ROOT = Path(__file__).resolve().parents[2]
ULTRA = "nvidia/nemotron-3-ultra-550b-a55b"


def _evaluation(judge_model: str) -> JudgeEvaluation:
    return JudgeEvaluation(
        overall_score=0.9,
        decision="APPROVE",
        completeness={"score": 0.9},
        accuracy={"score": 0.9},
        compliance={"score": 0.9},
        quality={"score": 0.9},
        issues_found=[],
        confidence=0.8,
        reasoning="ok",
        judge_model=judge_model,
    )


def _tools() -> DocumentActionTools:
    # The conversion helpers need no services.
    return DocumentActionTools.__new__(DocumentActionTools)


def test_fallback_label_names_the_route_not_a_model():
    assert DocumentActionTools.MODEL_LARGE_JUDGE == "ModelGateway (HIGH reasoning)"
    assert "Super" not in DocumentActionTools.MODEL_LARGE_JUDGE


@pytest.mark.parametrize(
    "validation, expected",
    [
        (_evaluation(ULTRA), ULTRA),
        (_evaluation(""), "ModelGateway (HIGH reasoning)"),
        ({"judge_model": ULTRA}, ULTRA),
        ({"overall_score": 0.5}, "ModelGateway (HIGH reasoning)"),
        (None, "ModelGateway (HIGH reasoning)"),
    ],
)
def test_judge_model_of_prefers_the_reported_model(validation, expected):
    assert DocumentActionTools._judge_model_of(validation) == expected


def test_quality_score_keeps_the_judges_model():
    score = _tools()._create_quality_score_from_validation(_evaluation(ULTRA))
    assert score.judge_model == ULTRA


def test_quality_score_from_dict_keeps_the_judges_model():
    score = _tools()._create_quality_score_from_validation(
        {
            "overall_score": 0.7,
            "decision": "REVIEW",
            "confidence": 0.6,
            "reasoning": "x",
            "judge_model": ULTRA,
        }
    )
    assert score.judge_model == ULTRA


def test_no_document_surface_names_super_as_the_judge():
    for path in (
        "src/api/agents/document/action_tools.py",
        "src/api/agents/document/mcp_document_agent.py",
        "src/ui/web/src/pages/DocumentExtraction.tsx",
        "src/ui/web/src/pages/Documentation.tsx",
        "src/ui/web/src/pages/ArchitectureDiagrams.tsx",
    ):
        assert "Super 120B" not in (REPO_ROOT / path).read_text(), path
