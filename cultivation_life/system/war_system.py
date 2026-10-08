from __future__ import annotations
from functools import cached_property
from .war.wiring import bind_war
from .war import state as war_state
from .war import presentation as war_presentation
from .war import power as war_power
from .war import peace as war_peace
from .war import lifecycle as war_lifecycle
from .war import diplomacy as war_diplomacy
from .war import combat as war_combat
from .war import actions as war_actions

from .semantic_events import emit

import copy
import random
import uuid
from typing import Any

from ..content_registry import ITEM_CATALOG, MARKET_GOODS, RACE_DEFINITIONS, REALMS, WORLD_SYSTEMS
from .formation_system import formation_config
from ..models import GameState, HistoryRecord, SectNpc
from .npc_system import npc_team_combat_power
from .combat.npc_battle import resolve_npc_engagement
from .doctrine.provider import battle_sources
from ..rules import add_item, remove_item
from ..runtime import decode_rng, encode_rng, now_iso
from ..world_state import RELATION_LABELS, race_pair
from .faction_geography import war_site, can_enter_faction


WAR_TERM_DEFS = {
    "economic_rights": ("接管当地产业与市税", 55),
    "execute": ("处死指定修士", 30),
    "alliance": ("确立同盟", 18),
    "vassal": ("迫使对方依附", 55),
    "change_relation": ("迫使对方改变外交关系", 25),
    "stones": ("上供大量灵石", 20),
    "supplies": ("缴纳丹药与装备", 25),
    "dissolve": ("解散对方势力", 70),
    "annex": ("合并对方势力", 90),
    "white_peace": ("无条件和平", 0),
}


def _war_sect(game, power_id):
    return game.family if game.family and game.family.id == power_id else game.sects.get(power_id)


def _war_rules() -> dict[str, Any]:
    return WORLD_SYSTEMS.get("war_system", {})


def _war_formation_metric_score(profile: dict[str, Any], side: str) -> float:
    metrics = {
        key: max(0.0, min(1.0, float(value) / 100.0))
        for key, value in profile.get("metrics", {}).items()
    }
    weights = (
        {"kill": .34, "focus": .20, "change": .18, "cycle": .14, "balance": .08, "growth": .06}
        if side == "attacker"
        else {"growth": .28, "balance": .26, "cycle": .16, "focus": .12, "change": .10, "kill": .08}
    )
    return sum(metrics.get(key, 0.0) * weight for key, weight in weights.items())


def _war_formation_text(contexts: dict[str, dict[str, Any]]) -> str:
    labels = {"attacker": "攻方", "defender": "守方"}
    details = []
    for side in ("attacker", "defender"):
        row = contexts[side]
        if not row.get("active"):
            details.append(f"{labels[side]}无统御阵势")
            continue
        conditions = f"，条件：{'、'.join(row['conditions'])}" if row.get("conditions") else ""
        details.append(
            f"{labels[side]}“{row['name']}”完整度 {float(row['integrity']):.0%}，"
            f"战役修正 {(float(row['modifier']) - 1.0):+.1%}{conditions}"
        )
    return "阵势权重：" + "；".join(details) + "。"


def _war_defeat_probabilities(realm_index: int) -> tuple[float, float]:
    highness = max(0.0, min(1.0, realm_index / max(1, len(REALMS) - 1)))
    return max(0.04, 0.34 - highness * 0.28), min(0.82, 0.30 + highness * 0.48)


def bind_war_compatibility(host):
    return bind_war(
        host,
        _get_WAR_TERM_DEFS=lambda: WAR_TERM_DEFS,
        decode_rng=lambda *args, **kwargs: decode_rng(*args, **kwargs),
    )


class WarSystemMixin:
    """行动单位制战争的兼容适配器。"""

    @cached_property
    def _war_dependencies(self):
        return bind_war_compatibility(self)

    def _maybe_map_war_encounter(self, game, rng):
        return war_actions._maybe_map_war_encounter(self._war_dependencies.actions, game, rng)

    @staticmethod
    def _war_sect(game, power_id):
        return _war_sect(game, power_id)

    def _war_player_identity(self, game, war):
        return war_state._war_player_identity(self._war_dependencies.state, game, war)

    @staticmethod
    def _war_rules() -> dict[str, Any]:
        return _war_rules()

    def _war_relation(self, game: GameState, kind: str, first: str, second: str) -> dict[str, Any]:
        return war_state._war_relation(self._war_dependencies.state, game, kind, first, second)

    def _active_war(self, game: GameState, kind: str, first: str, second: str) -> dict[str, Any] | None:
        return war_state._active_war(self._war_dependencies.state, game, kind, first, second)

    def _war_world(self, game: GameState, kind: str, side_id: str) -> str:
        return war_state._war_world(self._war_dependencies.state, game, kind, side_id)

    def _war_side_name(self, game: GameState, kind: str, side_id: str) -> str:
        return war_state._war_side_name(self._war_dependencies.state, game, kind, side_id)

    def _war_side_members(self, game: GameState, kind: str, side_id: str, world: str) -> list[SectNpc]:
        return war_state._war_side_members(self._war_dependencies.state, game, kind, side_id, world)

    def _ensure_war_shape(self, game: GameState, war: dict[str, Any]) -> bool:
        return war_state._ensure_war_shape(self._war_dependencies.state, game, war)

    def _coalition_ids(self, war: dict[str, Any], side: str) -> list[str]:
        return war_state._coalition_ids(self._war_dependencies.state, war, side)

    def _participant_side(self, war: dict[str, Any], power_id: str | None) -> str | None:
        return war_state._participant_side(self._war_dependencies.state, war, power_id)

    def _power_exists_in_world(self, game: GameState, kind: str, power_id: str, world: str) -> bool:
        return war_state._power_exists_in_world(self._war_dependencies.state, game, kind, power_id, world)

    def _allied_powers(self, game: GameState, war: dict[str, Any], side: str) -> list[dict[str, Any]]:
        return war_diplomacy._allied_powers(self._war_dependencies.diplomacy, game, war, side)

    def _add_war_participant(self, game: GameState, war: dict[str, Any], side: str, power_id: str, caller_id: str) -> None:
        return war_diplomacy._add_war_participant(self._war_dependencies.diplomacy, game, war, side, power_id, caller_id)

    def _call_war_allies(self, game: GameState, war: dict[str, Any], side: str, rng: random.Random,
                         *, ally_id: str = "", limit: int | None = None) -> list[str]:
        return war_diplomacy._call_war_allies(self._war_dependencies.diplomacy, game, war, side, rng, ally_id=ally_id, limit=limit)

    def _player_war_side(self, game: GameState, war: dict[str, Any]) -> str | None:
        return war_diplomacy._player_war_side(self._war_dependencies.diplomacy, game, war)

    def _player_has_war_voice(self, game: GameState, war: dict[str, Any]) -> bool:
        return war_diplomacy._player_has_war_voice(self._war_dependencies.diplomacy, game, war)

    def _start_war(self, game: GameState, kind: str, attacker: str, defender: str, *, initiated_by_player=False, prepare_supplies=True) -> dict[str, Any]:
        return war_diplomacy._start_war(self._war_dependencies.diplomacy, game, kind, attacker, defender, initiated_by_player=initiated_by_player, prepare_supplies=prepare_supplies)

    def _ensure_wars(self, game: GameState) -> bool:
        return war_state._ensure_wars(self._war_dependencies.state, game)

    def _append_war_log(self, game: GameState, war: dict[str, Any], title: str, text: str) -> None:
        return war_state._append_war_log(self._war_dependencies.state, game, war, title, text)

    def _war_npc(self, game: GameState, npc_id: str) -> SectNpc | None:
        return war_state._war_npc(self._war_dependencies.state, game, npc_id)

    def _available_warriors(self, game: GameState, war: dict[str, Any], side: str, power_id: str = "") -> list[SectNpc]:
        return war_state._available_warriors(self._war_dependencies.state, game, war, side, power_id)

    def _war_total_power(
        self, game: GameState, war: dict[str, Any], side: str, *, include_player: bool = True,
    ) -> float:
        return war_power._war_total_power(self._war_dependencies.power, game, war, side, include_player=include_player)

    @staticmethod
    def _war_formation_metric_score(profile: dict[str, Any], side: str) -> float:
        return _war_formation_metric_score(profile, side)

    def _war_side_formation(self, game: GameState, war: dict[str, Any], side: str) -> dict[str, Any]:
        return war_power._war_side_formation(self._war_dependencies.power, game, war, side)

    def _war_formation_modifier(
        self, own: dict[str, Any], opponent: dict[str, Any], side: str,
    ) -> float:
        return war_power._war_formation_modifier(self._war_dependencies.power, own, opponent, side)

    def _war_formation_contexts(self, game: GameState, war: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return war_power._war_formation_contexts(self._war_dependencies.power, game, war)

    @staticmethod
    def _war_formation_text(contexts: dict[str, dict[str, Any]]) -> str:
        return _war_formation_text(contexts)

    def _war_power_profile(
        self, game: GameState, war: dict[str, Any], side: str, *, include_player: bool = True,
    ) -> dict[str, float | int]:
        return war_power._war_power_profile(self._war_dependencies.power, game, war, side, include_player=include_player)

    def _war_entity_power(self, game: GameState, war: dict[str, Any], side: str, power_id: str) -> float:
        return war_power._war_entity_power(self._war_dependencies.power, game, war, side, power_id)

    def _resolve_abstract_defeat(self, game: GameState, war: dict[str, Any], loser: str, rng: random.Random) -> str:
        return war_combat._resolve_abstract_defeat(self._war_dependencies.combat, game, war, loser, rng)

    @staticmethod
    def _war_defeat_probabilities(realm_index: int) -> tuple[float, float]:
        return _war_defeat_probabilities(realm_index)

    def _shift_war_morale(self, war: dict[str, Any], loser: str, loss: float, gain: float, *, attacker_kill: bool = False) -> None:
        return war_combat._shift_war_morale(self._war_dependencies.combat, war, loser, loss, gain, attacker_kill=attacker_kill)

    def _resolve_field_attack(
        self, game: GameState, war: dict[str, Any], attacking: str, rng: random.Random,
        formation_contexts: dict[str, dict[str, Any]] | None = None,
    ) -> str:
        return war_combat._resolve_field_attack(self._war_dependencies.combat, game, war, attacking, rng, formation_contexts)

    def _resolve_player_war_round(
        self, game: GameState, war: dict[str, Any], side: str, rng: random.Random,
    ) -> None:
        return war_combat._resolve_player_war_round(self._war_dependencies.combat, game, war, side, rng)

    def _finish_war_by_morale(self, game: GameState, war: dict[str, Any]) -> bool:
        return war_lifecycle._finish_war_by_morale(self._war_dependencies.lifecycle, game, war)

    def war_action(self, game_id: str, war_id: str, action: str, *, ally_id: str = "") -> dict[str, Any]:
        return war_actions.war_action(self._war_dependencies.actions, game_id, war_id, action, ally_id=ally_id)

    def _resolve_war_vanguard(self, game: GameState, pending: dict[str, Any], mode: str, rng: random.Random) -> tuple[str, str]:
        return war_combat._resolve_war_vanguard(self._war_dependencies.combat, game, pending, mode, rng)

    def _advance_wars_unit(self, game: GameState, rng: random.Random) -> list[str]:
        return war_lifecycle._advance_wars_unit(self._war_dependencies.lifecycle, game, rng)

    def _generate_ai_peace_offer(self, game: GameState, war: dict[str, Any], proposer: str) -> dict[str, Any]:
        return war_peace._generate_ai_peace_offer(self._war_dependencies.peace, game, war, proposer)

    def _conclude_war_bundle(self, game: GameState, war: dict[str, Any], demands: list[dict[str, Any]],
                             beneficiary: str, *, automatic: bool = False) -> str:
        return war_peace._conclude_war_bundle(self._war_dependencies.peace, game, war, demands, beneficiary, automatic=automatic)

    def _conclude_war(self, game: GameState, war: dict[str, Any], term: str, beneficiary: str, *, automatic: bool = False,
                      target_id: str = "", target_power_id: str = "", third_party_id: str = "",
                      third_status: str = "neutral", finalize: bool = True) -> str:
        return war_peace._conclude_war(self._war_dependencies.peace, game, war, term, beneficiary, automatic=automatic, target_id=target_id, target_power_id=target_power_id, third_party_id=third_party_id, third_status=third_status, finalize=finalize)

    def war_peace(self, game_id: str, war_id: str, term: str, *, target_id: str = "", target_power_id: str = "",
                  third_party_id: str = "", third_status: str = "neutral", concede: bool = False) -> dict[str, Any]:
        return war_peace.war_peace(self._war_dependencies.peace, game_id, war_id, term, target_id=target_id, target_power_id=target_power_id, third_party_id=third_party_id, third_status=third_status, concede=concede)

    def _public_war_system(self, game: GameState) -> dict[str, Any]:
        return war_presentation._public_war_system(self._war_dependencies.presentation, game)
