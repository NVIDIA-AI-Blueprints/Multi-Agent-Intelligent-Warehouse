# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Production composition root for SOP state predicates.

Each domain owns and registers its own predicates at import of that domain's
package (``maiw_agents.equipment``, ``maiw_agents.wave``). That is the right
ownership boundary, but on its own it makes predicate availability a function of
*which agent a process happened to construct*: a runtime that never touches the
wave agent would still reach Proof SOP A's terminal STATE_PREDICATE step and get
``unknown predicate``. That is exactly the failure this module exists to remove.

``register_all_domain_predicates()`` is the single production call that makes
every domain's predicates available regardless of which agents are wired up. It
is not a registry — there is exactly one registry, ``sop_engine.validators``'
``_PREDICATES`` — and it is not a test bootstrap. It is the import-side
composition root, the predicate equivalent of an application wiring its routers.

Adding a domain means adding one import here and a ``predicates.py`` to that
domain package. Nothing in ``sop_engine`` changes, and nothing here knows what a
forklift or a carrier cutoff is; the domain semantics stay in the domains.
"""

from __future__ import annotations

from typing import Any, Callable

from .sop_engine.validators import get_registered_predicates

__all__ = [
    "PredicateFn",
    "PREDICATE_DOMAIN_MODULES",
    "register_all_domain_predicates",
    "production_predicates",
]

# The registry contract, spelled once: a predicate reads authoritative state and
# its declared args, and answers yes or no. Nothing else.
PredicateFn = Callable[[dict[str, Any], dict[str, Any]], bool]


# Import paths of the domain packages that own SOP state predicates. Importing
# the package runs its ``register_*_predicates()`` call.
PREDICATE_DOMAIN_MODULES = (
    "maiw_agents.equipment.predicates",
    "maiw_agents.inventory.predicates",
    "maiw_agents.wave.predicates",
)


def register_all_domain_predicates() -> None:
    """
    Register every domain's SOP state predicates with the SOP Engine.

    Idempotent: each domain's registration rebinds the same names to the same
    functions, so calling this repeatedly (or after a domain package has already
    been imported) is a no-op. Safe to call at application startup.
    """
    from importlib import import_module

    for module_path in PREDICATE_DOMAIN_MODULES:
        import_module(module_path)


def production_predicates() -> dict[str, PredicateFn]:
    """
    Return the predicate registry exactly as production runtime sees it.

    This is the function a SOP-to-registry conformance check should use: it
    performs the production registration and then reports what is resolvable.
    No monkeypatching, no fixture registration, no manual dict insertion.
    """
    register_all_domain_predicates()
    return get_registered_predicates()
