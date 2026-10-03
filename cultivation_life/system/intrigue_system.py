from __future__ import annotations
from functools import cached_property
from .intrigue.wiring import bind_intrigue
from .intrigue import governance as intrigue_governance
from .intrigue import guests as intrigue_guests
from .intrigue import presentation as intrigue_presentation
from .intrigue import recruitment as intrigue_recruitment
from .intrigue import resolutions as intrigue_resolutions
from .intrigue import runtime as intrigue_runtime
from .intrigue import state as intrigue_state



import random
from typing import Any

from ..content_registry import (
    WORLD_SYSTEMS,
)
from ..models import GameState, SectNpc, SectState


PLAYER_ID = "player"
PERSONALITY_LABELS = {
    "paranoid": "偏执",
    "fanatical": "狂热",
    "cautious": "谨慎",
    "smooth": "圆滑",
    "forceful": "强硬",
    "generous": "宽厚",
    "suspicious": "多疑",
    "greedy": "贪婪",
    "restrained": "克制",
    "warlike": "好战",
    "conservative": "保守",
    "open": "开放",
}
STYLE_LABELS = {
    "balance": "平衡型",
    "internal": "内政型",
    "diplomacy": "外交型",
    "military": "军事型",
}
RESOLUTION_LABELS = {
    "declare_war": "宣战",
    "make_peace": "停战",
    "form_alliance": "缔结联盟",
    "break_alliance": "解除联盟",
    "intervene_war": "介入战争",
    "mass_recruitment": "大规模招收成员",
    "relocate": "迁移主要驻地",
    "investment": "重大资源投资",
    "policy": "长期政策",
    "disciple_recruitment": "扩招徒弟",
}


def intrigue_rules() -> dict[str, Any]:
    value = WORLD_SYSTEMS.get("intrigue_dlc", {})
    return value if isinstance(value, dict) and value.get("enabled") else {}


def intrigue_content_available() -> bool:
    return bool(intrigue_rules())


class IntrigueSystemMixin:
    """Generic runtime hook for 《明争暗斗：合纵连横》.

    The rules live in the DLC's world.json overlay.  Without that document all
    methods become inert and existing faction behavior stays untouched.
    """

    def _intrigue_has_decision_authority(
        self, game: GameState, kind: str, faction_id: str, member_id: str = PLAYER_ID
    ) -> bool:
        threshold = self._intrigue_decision_threshold(kind)
        if member_id == PLAYER_ID:
            own_id = self._intrigue_player_faction_id(game, kind)
            realm_index, _ = self._actual_player_realm(game.player)
            entity = self._intrigue_entity(game, kind, faction_id)
            same_world = not entity or entity.world == game.player.world
            return bool(
                own_id == faction_id
                and same_world
                and game.player.alive
                and realm_index >= threshold
            )
        npc = self._intrigue_find_npc(game, member_id)
        return bool(
            npc
            and npc.alive
            and npc.realm_index >= threshold
            and not self._intrigue_is_imprisoned(game, npc.id)
        )

    @staticmethod
    def _intrigue_player_relation(
        game: GameState, npc_id: str
    ) -> dict[str, Any] | None:
        relations = [
            game.player.master,
            game.player.dao_companion,
            *game.player.dao_friends,
            *game.player.disciples,
        ]
        return next(
            (row for row in relations if row and str(row.get("id", "")) == npc_id),
            None,
        )

    @staticmethod
    def _intrigue_recruitment_config() -> dict[str, Any]:
        return dict(intrigue_rules().get("disciple_recruitment", {}))

    @staticmethod
    def _intrigue_enabled() -> bool:
        return intrigue_content_available()

    @staticmethod
    def _intrigue_state(game: GameState) -> dict[str, Any]:
        state = game.intrigue_state
        state.setdefault("schema_version", 1)
        state.setdefault("npcs", {})
        state.setdefault("factions", {})
        state.setdefault("resolutions", [])
        state.setdefault("npc_prisons", {})
        state.setdefault("pending_guest_invitation", None)
        state.setdefault("sequence", 0)
        state.setdefault("ai_cursor", 0)
        return state

    @staticmethod
    def _intrigue_key(kind: str, faction_id: str) -> str:
        return f"{kind}:{faction_id}"

    @cached_property
    def _intrigue_dependencies(self):
        return bind_intrigue(
            self,
            _get_PERSONALITY_LABELS=lambda: PERSONALITY_LABELS,
            _get_PLAYER_ID=lambda: PLAYER_ID,
            _get_RESOLUTION_LABELS=lambda: RESOLUTION_LABELS,
            _get_STYLE_LABELS=lambda: STYLE_LABELS,
            intrigue_rules=lambda *args, **kwargs: intrigue_rules(*args, **kwargs),
        )

    def _intrigue_auto_appoint_player(
        self,
        game: GameState,
        kind: str,
        faction_id: str,
        record: dict[str, Any],
        members: list[SectNpc],
    ) -> None:
        "Let cultivation order, rather than voting rights, drive ordinary offices.\n\n        The controller still occupies the first (leader) office.  Remaining\n        offices follow the faction's cultivation order, while guest offices\n        remain reserved for external retainers.  This makes a powerful member\n        eligible for office even when their realm is below the independent\n        decision-authority threshold.\n"
        return intrigue_governance._intrigue_auto_appoint_player(
            self._intrigue_dependencies.governance,
            game,
            kind,
            faction_id,
            record,
            members,
        )

    def _intrigue_is_imprisoned(self, game: GameState, npc_id: str) -> bool:
        return intrigue_governance._intrigue_is_imprisoned(
            self._intrigue_dependencies.governance, game, npc_id
        )

    def _intrigue_decision_threshold(self, kind: str) -> int:
        return intrigue_governance._intrigue_decision_threshold(
            self._intrigue_dependencies.governance, kind
        )

    def _intrigue_has_control(
        self, game: GameState, kind: str, faction_id: str
    ) -> bool:
        return intrigue_governance._intrigue_has_control(
            self._intrigue_dependencies.governance, game, kind, faction_id
        )

    def _intrigue_position_specs(self, kind: str) -> dict[str, dict[str, Any]]:
        return intrigue_governance._intrigue_position_specs(
            self._intrigue_dependencies.governance, kind
        )

    def _intrigue_faction_name(
        self, game: GameState, kind: str, faction_id: str
    ) -> str:
        return intrigue_governance._intrigue_faction_name(
            self._intrigue_dependencies.governance, game, kind, faction_id
        )

    def intrigue_personnel_action(
        self,
        game_id: str,
        kind: str,
        action: str,
        npc_id: str,
        position_id: str = "",
        years: int = 1,
        reason: str = "",
    ) -> dict[str, Any]:
        return intrigue_governance.intrigue_personnel_action(
            self._intrigue_dependencies.governance,
            game_id,
            kind,
            action,
            npc_id,
            position_id,
            years,
            reason,
        )

    def _intrigue_pressure_position_occupied(
        self, game: GameState, faction_id: str
    ) -> bool:
        "DLC pressure requires an actually occupied office, never a phantom rival."
        return intrigue_governance._intrigue_pressure_position_occupied(
            self._intrigue_dependencies.governance, game, faction_id
        )

    def _intrigue_can_invite_guest(
        self, game: GameState, npc_id: str, kind: str = "sect"
    ) -> bool:
        return intrigue_guests._intrigue_can_invite_guest(
            self._intrigue_dependencies.guests, game, npc_id, kind
        )

    def intrigue_guest_action(
        self, game_id: str, kind: str, action: str, npc_id: str = ""
    ) -> dict[str, Any]:
        return intrigue_guests.intrigue_guest_action(
            self._intrigue_dependencies.guests, game_id, kind, action, npc_id
        )

    def _intrigue_guest_npcs(
        self, game: GameState, kind: str, faction_id: str
    ) -> list[SectNpc]:
        return intrigue_guests._intrigue_guest_npcs(
            self._intrigue_dependencies.guests, game, kind, faction_id
        )

    def _intrigue_defensive_guest_ids(
        self, game: GameState, kind: str, faction_id: str, world: str
    ) -> list[str]:
        return intrigue_guests._intrigue_defensive_guest_ids(
            self._intrigue_dependencies.guests, game, kind, faction_id, world
        )

    def _intrigue_player_guest_side(
        self, game: GameState, war: dict[str, Any]
    ) -> str | None:
        return intrigue_guests._intrigue_player_guest_side(
            self._intrigue_dependencies.guests, game, war
        )

    def _intrigue_public_member(
        self, game: GameState, npc: SectNpc, record: dict[str, Any]
    ) -> dict[str, Any]:
        return intrigue_presentation._intrigue_public_member(
            self._intrigue_dependencies.presentation, game, npc, record
        )

    def _public_intrigue_recruitment(
        self, game: GameState, faction_id: str, record: dict[str, Any]
    ) -> dict[str, Any]:
        return intrigue_presentation._public_intrigue_recruitment(
            self._intrigue_dependencies.presentation, game, faction_id, record
        )

    def _public_guest_invitation(self, game: GameState) -> dict[str, Any] | None:
        return intrigue_presentation._public_guest_invitation(
            self._intrigue_dependencies.presentation, game
        )

    def _public_intrigue_system(self, game: GameState) -> dict[str, Any]:
        return intrigue_presentation._public_intrigue_system(
            self._intrigue_dependencies.presentation, game
        )

    def _intrigue_recruitment_realm_options(self, world: str) -> list[int]:
        return intrigue_recruitment._intrigue_recruitment_realm_options(
            self._intrigue_dependencies.recruitment, world
        )

    def _normalize_intrigue_recruitment_filters(
        self, game: GameState, filters: dict[str, Any] | None
    ) -> dict[str, Any]:
        return intrigue_recruitment._normalize_intrigue_recruitment_filters(
            self._intrigue_dependencies.recruitment, game, filters
        )

    def _intrigue_recruitment_filter_summary(self, filters: dict[str, Any]) -> str:
        return intrigue_recruitment._intrigue_recruitment_filter_summary(
            self._intrigue_dependencies.recruitment, filters
        )

    def _generate_intrigue_recruitment_session(
        self,
        game: GameState,
        faction_id: str,
        filters: dict[str, Any],
        rng: random.Random,
    ) -> dict[str, Any]:
        return intrigue_recruitment._generate_intrigue_recruitment_session(
            self._intrigue_dependencies.recruitment, game, faction_id, filters, rng
        )

    def intrigue_recruitment_action(
        self,
        game_id: str,
        action: str,
        filters: dict[str, Any] | None = None,
        candidate_ids: list[str] | None = None,
        player_vote: bool = True,
    ) -> dict[str, Any]:
        return intrigue_recruitment.intrigue_recruitment_action(
            self._intrigue_dependencies.recruitment,
            game_id,
            action,
            filters,
            candidate_ids,
            player_vote,
        )

    def _intrigue_vote_chance(
        self,
        game: GameState,
        npc: SectNpc,
        resolution_type: str,
        kind: str,
        faction_id: str,
        target_id: str,
        proposer_id: str,
    ) -> tuple[float, list[str]]:
        return intrigue_resolutions._intrigue_vote_chance(
            self._intrigue_dependencies.resolutions,
            game,
            npc,
            resolution_type,
            kind,
            faction_id,
            target_id,
            proposer_id,
        )

    def _intrigue_resolve(
        self,
        game: GameState,
        kind: str,
        faction_id: str,
        resolution_type: str,
        target_id: str,
        player_vote: bool | None,
        proposer_id: str,
        rng: random.Random,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return intrigue_resolutions._intrigue_resolve(
            self._intrigue_dependencies.resolutions,
            game,
            kind,
            faction_id,
            resolution_type,
            target_id,
            player_vote,
            proposer_id,
            rng,
            context,
        )

    def _intrigue_apply_resolution(
        self,
        game: GameState,
        record: dict[str, Any],
        resolution_type: str,
        target_id: str,
        rng: random.Random,
        *,
        context: dict[str, Any] | None = None,
    ) -> None:
        return intrigue_resolutions._intrigue_apply_resolution(
            self._intrigue_dependencies.resolutions,
            game,
            record,
            resolution_type,
            target_id,
            rng,
            context=context,
        )

    def intrigue_propose_resolution(
        self,
        game_id: str,
        kind: str,
        resolution_type: str,
        target_id: str = "",
        player_vote: bool = True,
    ) -> dict[str, Any]:
        return intrigue_resolutions.intrigue_propose_resolution(
            self._intrigue_dependencies.resolutions,
            game_id,
            kind,
            resolution_type,
            target_id,
            player_vote,
        )

    def _intrigue_record_player_prison(
        self, game: GameState, key: str, years: int
    ) -> None:
        return intrigue_runtime._intrigue_record_player_prison(
            self._intrigue_dependencies.runtime, game, key, years
        )

    def _intrigue_sync_player_prison(self, game: GameState) -> None:
        return intrigue_runtime._intrigue_sync_player_prison(
            self._intrigue_dependencies.runtime, game
        )

    def _advance_intrigue_unit(self, game: GameState, rng: random.Random) -> list[str]:
        return intrigue_runtime._advance_intrigue_unit(
            self._intrigue_dependencies.runtime, game, rng
        )

    def _intrigue_entity(
        self, game: GameState, kind: str, faction_id: str
    ) -> SectState | None:
        return intrigue_state._intrigue_entity(
            self._intrigue_dependencies.state, game, kind, faction_id
        )

    def _intrigue_find_npc(self, game: GameState, npc_id: str) -> SectNpc | None:
        return intrigue_state._intrigue_find_npc(
            self._intrigue_dependencies.state, game, npc_id
        )

    def _intrigue_members(
        self, game: GameState, kind: str, faction_id: str
    ) -> list[SectNpc]:
        return intrigue_state._intrigue_members(
            self._intrigue_dependencies.state, game, kind, faction_id
        )

    def _intrigue_player_faction_id(self, game: GameState, kind: str) -> str | None:
        return intrigue_state._intrigue_player_faction_id(
            self._intrigue_dependencies.state, game, kind
        )

    def _ensure_intrigue_personality(
        self, game: GameState, npc: SectNpc
    ) -> dict[str, Any]:
        return intrigue_state._ensure_intrigue_personality(
            self._intrigue_dependencies.state, game, npc
        )

    def _intrigue_governance_style(self, game: GameState, npc: SectNpc) -> str:
        return intrigue_state._intrigue_governance_style(
            self._intrigue_dependencies.state, game, npc
        )

    def _ensure_intrigue_faction(
        self, game: GameState, kind: str, faction_id: str
    ) -> dict[str, Any]:
        return intrigue_state._ensure_intrigue_faction(
            self._intrigue_dependencies.state, game, kind, faction_id
        )
