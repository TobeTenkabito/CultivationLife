"""Operations required by the NPC contact adapter, independent of GameEngine."""
from dataclasses import dataclass
from typing import Any, Callable
from ..ports import SavePort


@dataclass(frozen=True, slots=True)
class NpcContactDependencies:
    _adjust_person_affinity: Callable[..., Any]
    _find_npc: Callable[..., Any]
    _load: Callable[..., Any]
    _promote_cached_npc: Callable[..., Any]
    _sage_affinity_gain: Callable[..., Any]
    assert_buddhist_operation_allowed: Callable[..., Any]
    begin_relationship_capture: Callable[..., Any]
    manage_concubine: Callable[..., Any]
    manage_dao_companion: Callable[..., Any]
    manage_dao_friend: Callable[..., Any]
    manage_known_relationship: Callable[..., Any]
    manage_party: Callable[..., Any]
    present: Callable[..., Any]
    relationship_violence: Callable[..., Any]
    _get_store: Callable[[], SavePort]

    @property
    def store(self) -> SavePort:
        return self._get_store()
