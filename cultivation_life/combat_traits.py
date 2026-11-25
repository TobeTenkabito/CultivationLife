from __future__ import annotations
from .definition_data import definition as _content_definition

from typing import Final


# These identifiers belong to the transformation system.  Other progression
# systems must register their own traits instead of borrowing transformation
# names such as Phoenix rebirth or Asura battle intent.
COMBAT_TRAIT_REGISTRY: Final[dict[str, dict[str, str]]] = _content_definition(__name__, "COMBAT_TRAIT_REGISTRY")


def public_combat_trait(trait_id: str) -> dict[str, str]:
    definition = COMBAT_TRAIT_REGISTRY.get(trait_id, {"name": trait_id, "description": ""})
    return {"id": trait_id, **definition}
