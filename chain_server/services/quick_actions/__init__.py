"""
Quick Actions Services Package

This package provides intelligent quick actions and suggestions for
the warehouse operational assistant.
"""

from .smart_quick_actions import (
    SmartQuickActionsService,
    QuickAction,
    ActionContext,
    ActionType,
    ActionPriority,
    get_smart_quick_actions_service,
)

__all__ = [
    "SmartQuickActionsService",
    "QuickAction",
    "ActionContext",
    "ActionType",
    "ActionPriority",
    "get_smart_quick_actions_service",
]
