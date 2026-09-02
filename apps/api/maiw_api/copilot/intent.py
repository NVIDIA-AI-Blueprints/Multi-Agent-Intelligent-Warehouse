# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Deterministic Copilot intent classification.

Classifies operator messages into ASK / ANALYZE / ACT without an LLM call.
Pattern matching is ordered: ACT markers first (explicit commands), then
ANALYZE markers (recommendation requests), then default to ASK.

ACT is detected but not executed in Phase 15C — the caller returns a safe
"governed action handling is not yet available" response.
"""

from __future__ import annotations

import re

from .models import CopilotIntent

# ── ACT markers — explicit operational commands ───────────────────────────────
# Match whole-word or start-of-phrase to avoid false positives like "movement".
_ACT_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b(do it|execute|confirm|apply|approve|commit)\b", re.IGNORECASE),
    re.compile(r"\b(allocate|reassign|move|reprioritize|reprioritise|dispatch|cancel)\b", re.IGNORECASE),
    re.compile(r"\b(make it happen|go ahead|proceed with)\b", re.IGNORECASE),
    re.compile(r"\bproceed\b", re.IGNORECASE),
    re.compile(r"\bprepare (that|this|the) action\b", re.IGNORECASE),
]

# ── ANALYZE markers — recommendation-oriented questions ───────────────────────
_ANALYZE_PATTERNS: list[re.Pattern] = [
    re.compile(r"\bwhat should (we|i|you)\b", re.IGNORECASE),
    re.compile(r"\bwhat (do|would|can) (we|i|you) (do|recommend|suggest)\b", re.IGNORECASE),
    re.compile(r"\b(recommend|recommendations?)\b", re.IGNORECASE),
    re.compile(r"\bhow should (we|i|you)\b", re.IGNORECASE),
    re.compile(r"\bhow (can|could|do) (we|i|you)\b", re.IGNORECASE),
    re.compile(r"\bbest (action|response|approach|course)\b", re.IGNORECASE),
    re.compile(r"\b(protect|mitigate|address|fix|resolve|handle) (this|the|wave|risk)\b", re.IGNORECASE),
    re.compile(r"\bwhat('s| is) (our|the) (best|next|recommended)\b", re.IGNORECASE),
    re.compile(r"\bwhat (action|step|option)s?\b", re.IGNORECASE),
    re.compile(r"\breduce (the )?risk\b", re.IGNORECASE),
    re.compile(r"\bimprove (the )?(situation|status|wave|throughput)\b", re.IGNORECASE),
    re.compile(r"\bwhat (are|would be) (our|the|my) (best |)options\b", re.IGNORECASE),
]


def classify(message: str) -> CopilotIntent:
    """
    Classify a single operator message into ASK / ANALYZE / ACT.

    Order of precedence:
    1. ACT markers (explicit operational commands)
    2. ANALYZE markers (recommendation-oriented questions)
    3. Default: ASK (explanation / status / "why" / "what happened")
    """
    for pattern in _ACT_PATTERNS:
        if pattern.search(message):
            return CopilotIntent.ACT

    for pattern in _ANALYZE_PATTERNS:
        if pattern.search(message):
            return CopilotIntent.ANALYZE

    return CopilotIntent.ASK
