from __future__ import annotations

import copy
import random
import uuid
from typing import Any

# Moved methods still use this module's globals; retain the imports below.

from ..content_registry import (
    FACTION_SYSTEMS, PATH_NAMES, RACE_DEFINITIONS, REALMS, ROOT_DEFINITIONS,
    WORLD_SYSTEMS,
)
from ..models import GameState, HistoryRecord, SectNpc, SectState
from .npc_system import attitude_label
from ..rules import expected_combat_power
from ..runtime import decode_rng, encode_rng, now_iso
from ..world_state import race_pair


PLAYER_ID = "player"
PERSONALITY_LABELS = {
    "paranoid": "偏执", "fanatical": "狂热", "cautious": "谨慎", "smooth": "圆滑",
    "forceful": "强硬", "generous": "宽厚", "suspicious": "多疑", "greedy": "贪婪",
    "restrained": "克制", "warlike": "好战", "conservative": "保守", "open": "开放",
}
STYLE_LABELS = {
    "balance": "平衡型", "internal": "内政型", "diplomacy": "外交型", "military": "军事型",
}
RESOLUTION_LABELS = {
    "declare_war": "宣战", "make_peace": "停战", "form_alliance": "缔结联盟",
    "break_alliance": "解除联盟", "intervene_war": "介入战争",
    "mass_recruitment": "大规模招收成员", "relocate": "迁移主要驻地",
    "investment": "重大资源投资", "policy": "长期政策",
    "disciple_recruitment": "扩招徒弟",
}


def intrigue_rules() -> dict[str, Any]:
    value = WORLD_SYSTEMS.get("intrigue_dlc", {})
    return value if isinstance(value, dict) and value.get("enabled") else {}


def intrigue_content_available() -> bool:
    return bool(intrigue_rules())


from ._assembly import include_system_methods as _include_system_methods
from .intrigue.state import IntrigueStateMethods
from .intrigue.governance import IntrigueGovernanceMethods
from .intrigue.guests import IntrigueGuestMethods
from .intrigue.recruitment import IntrigueRecruitmentMethods
from .intrigue.resolutions import IntrigueResolutionMethods
from .intrigue.runtime import IntrigueRuntimeMethods
from .intrigue.presentation import IntriguePresentationMethods


@_include_system_methods(
    IntrigueStateMethods,
    IntrigueGovernanceMethods,
    IntrigueGuestMethods,
    IntrigueRecruitmentMethods,
    IntrigueResolutionMethods,
    IntrigueRuntimeMethods,
    IntriguePresentationMethods,
    namespace=globals(),
)
class IntrigueSystemMixin:
    """Generic runtime hook for 《明争暗斗：合纵连横》.

    The rules live in the DLC's world.json overlay.  Without that document all
    methods become inert and existing faction behavior stays untouched.
    """

    def _intrigue_has_decision_authority(self, game: GameState, kind: str, faction_id: str, member_id: str = PLAYER_ID) -> bool:
        threshold = self._intrigue_decision_threshold(kind)
        if member_id == PLAYER_ID:
            own_id = self._intrigue_player_faction_id(game, kind)
            realm_index, _ = self._actual_player_realm(game.player)
            entity = self._intrigue_entity(game, kind, faction_id)
            same_world = not entity or entity.world == game.player.world
            return bool(own_id == faction_id and same_world and game.player.alive and realm_index >= threshold)
        npc = self._intrigue_find_npc(game, member_id)
        return bool(npc and npc.alive and npc.realm_index >= threshold and not self._intrigue_is_imprisoned(game, npc.id))
