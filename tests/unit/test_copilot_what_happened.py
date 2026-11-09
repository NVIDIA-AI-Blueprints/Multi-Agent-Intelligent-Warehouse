# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
"What happened …" questions: outcome of the last action, or warehouse state (#287).

The OBSERVE_OUTCOME patterns included the bare phrase ``what happened``, and
they are checked before every other intent. So "What happened to the carrier
cutoff?" was classified OBSERVE_OUTCOME: with no action yet in the
conversation the Copilot answered "I have not performed any governed action
in this conversation yet", and after one it reported that action's outcome,
never the cutoff. A "what happened" question is now an outcome question only
when it stands alone or points at the action.
"""

from __future__ import annotations

import pytest

from maiw_api.copilot.intent import classify
from maiw_api.copilot.models import CopilotIntent

ABOUT_STATE = [
    "What happened to the carrier cutoff?",
    "what happened to wave 17?",
    "What happened to forklift FL-03 this morning?",
    "What happened with the inbound trucks?",
    "Why did wave 17 slip, and what happened to Maria's tasks?",
]

ABOUT_THE_ACTION = [
    "What happened?",
    "what happened",
    "OK, what happened?",
    "So what has happened?",
    "What happened next?",
    "What happened since?",
    "What happened as a result?",
    "What happened with it?",
    "What happened to that?",
    "What happened after the reassignment?",
    "What happened with the action?",
    "What happened to my request?",
    "What happened after I approved it?",
    "What happened once we executed it?",
    # Unchanged outcome markers.
    "Did it work?",
    "Did that help?",
    "What was the outcome?",
    "Show me the result",
    "Any improvement?",
]


@pytest.mark.parametrize("message", ABOUT_STATE)
def test_what_happened_to_warehouse_state_is_not_an_outcome_question(message):
    assert classify(message) == CopilotIntent.ASK


@pytest.mark.parametrize("message", ABOUT_THE_ACTION)
def test_questions_about_the_last_action_are_outcome_questions(message):
    assert classify(message) == CopilotIntent.OBSERVE_OUTCOME
