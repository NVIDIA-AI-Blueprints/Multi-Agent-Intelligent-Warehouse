# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
InMemoryCopilotStore — process-local conversation state.

Scope mirrors InMemoryApprovalStore: single process, no persistence.
Callers receive this limitation via CopilotTurnResponse.store_note.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from .models import CopilotConversation, CopilotTurn


class InMemoryCopilotStore:
    def __init__(self) -> None:
        self._conversations: dict[str, CopilotConversation] = {}

    def create_conversation(
        self,
        warehouse_id: str,
        scenario_name: str,
    ) -> CopilotConversation:
        conv = CopilotConversation(
            conversation_id=str(uuid.uuid4()),
            warehouse_id=warehouse_id,
            scenario_name=scenario_name,
        )
        self._conversations[conv.conversation_id] = conv
        return conv

    def get_conversation(self, conversation_id: str) -> CopilotConversation | None:
        return self._conversations.get(conversation_id)

    def get_or_create(
        self,
        conversation_id: str | None,
        warehouse_id: str,
        scenario_name: str,
    ) -> CopilotConversation:
        if conversation_id and conversation_id in self._conversations:
            return self._conversations[conversation_id]
        conv = self.create_conversation(warehouse_id, scenario_name)
        return conv

    def add_turn(self, turn: CopilotTurn) -> None:
        conv = self._conversations.get(turn.conversation_id)
        if conv is not None:
            conv.add_turn(turn)

    def reset(self) -> None:
        self._conversations.clear()
