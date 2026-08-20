# DEPRECATED compatibility shim — use maiw_skills.inventory directly. Remove by Phase 9.
from maiw_skills.inventory.lookup import (  # noqa: F401
    InventoryLookupSkill,
    get_inventory_skill,
    reset_inventory_skill,
)
