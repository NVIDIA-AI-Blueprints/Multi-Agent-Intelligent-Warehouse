# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
The dead document-extraction code is gone (#270).

``DocumentExtractionAgent`` (``document_extraction_agent.py``) had no caller:
the shipped upload route runs its own five-stage pipeline (preprocessing, OCR,
small-LLM extraction, large-LLM judge, routing). Its error path also used
``RoutingAction.SEND_TO_HUMAN_REVIEW``, which does not exist, so any exception
would have raised ``AttributeError`` inside the ``except`` block.

Removing it left six modules with no caller (layout detection, Nemotron Parse,
entity extraction, embedding and indexing, quality scoring, workflow manager);
``local_processor.py`` and ``models/extraction_models.py`` had none already.
They are removed too, and the upload response, the MCP document agent and the
UI no longer advertise an "Embedding & Indexing" stage that never ran.
``NEMO_PARSE_URL`` is no longer documented, since nothing reads it.
"""

from __future__ import annotations

import ast
import importlib.util
import re
from pathlib import Path

import pytest

from src.api.agents.document.models.document_models import RoutingAction

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCUMENT_PKG = "src.api.agents.document"

REMOVED_MODULES = [
    "document_extraction_agent",
    "preprocessing.layout_detection",
    "ocr.nemotron_parse",
    "processing.entity_extractor",
    "processing.embedding_indexing",
    "processing.local_processor",
    "validation.quality_scorer",
    "routing.workflow_manager",
    "models.extraction_models",
]


@pytest.mark.parametrize("module", REMOVED_MODULES)
def test_removed_module_is_gone(module):
    assert importlib.util.find_spec(f"{DOCUMENT_PKG}.{module}") is None


def test_every_routing_action_reference_is_a_real_member():
    members = set(RoutingAction.__members__)
    offenders = []
    for root in ("src", "apps"):
        for path in (REPO_ROOT / root).rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="replace")
            for name in re.findall(r"RoutingAction\.([A-Za-z_]+)", text):
                if name not in members and not name.startswith("_"):
                    offenders.append(f"{path.relative_to(REPO_ROOT)}: {name}")
    assert offenders == []


def _list_literal_after(path: Path, key: str) -> list[str]:
    """The string list literal assigned to ``key`` in a dict literal."""
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values):
                if isinstance(k, ast.Constant) and k.value == key:
                    if isinstance(v, ast.List):
                        return [
                            e.value if isinstance(e, ast.Constant) else ast.unparse(e)
                            for e in v.elts
                        ]
    raise AssertionError(f"{key} list not found in {path}")


@pytest.mark.parametrize(
    "path, key",
    [
        ("src/api/agents/document/action_tools.py", "processing_stages"),
        ("src/api/agents/document/mcp_document_agent.py", "processing_pipeline"),
    ],
)
def test_advertised_pipeline_matches_the_five_shipped_stages(path, key):
    stages = _list_literal_after(REPO_ROOT / path, key)
    assert len(stages) == 5, stages
    assert not any("Embedding" in s for s in stages), stages


def test_ui_lists_five_stages_and_no_nemotron_parse():
    for page in ("DocumentExtraction.tsx", "Documentation.tsx"):
        text = (REPO_ROOT / "src/ui/web/src/pages" / page).read_text()
        assert "Embedding & Indexing" not in text, page
        assert "Nemotron Parse" not in text, page
        assert "6-stage" not in text and "6 Stages" not in text, page


def test_nemo_parse_settings_are_not_documented():
    for name in (".env.example", "DEPLOYMENT.md"):
        assert "NEMO_PARSE" not in (REPO_ROOT / name).read_text(), name
