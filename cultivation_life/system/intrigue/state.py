from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import random
    from typing import Any
    from ...models import GameState, SectNpc, SectState
    from ..intrigue_system import intrigue_rules, intrigue_content_available
    from .. import intrigue_system as _source
    PLAYER_ID = _source.PLAYER_ID
    PERSONALITY_LABELS = _source.PERSONALITY_LABELS
    STYLE_LABELS = _source.STYLE_LABELS


class IntrigueStateMethods:
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

    def _intrigue_entity(self, game: GameState, kind: str, faction_id: str) -> SectState | None:
        if kind == "sect":
            return game.sects.get(faction_id)
        if kind == "family" and game.family and game.family.id == faction_id:
            return game.family
        return None

    def _intrigue_find_npc(self, game: GameState, npc_id: str) -> SectNpc | None:
        if game.family:
            member = next((row for row in game.family.npcs if row.id == npc_id), None)
            if member:
                return member
        return self._find_npc(game, npc_id)

    def _intrigue_members(self, game: GameState, kind: str, faction_id: str) -> list[SectNpc]:
        if kind == "sect":
            entity = game.sects.get(faction_id)
            return self._sect_members(game, entity) if entity and not entity.extinct else []
        if kind == "family":
            return list(game.family.npcs) if game.family and game.family.id == faction_id and not game.family.extinct else []
        if kind == "race":
            return [npc for npc in self._all_world_npcs(game) if npc.race == faction_id and npc.world == game.player.world]
        return []

    def _intrigue_player_faction_id(self, game: GameState, kind: str) -> str | None:
        if kind == "sect":
            return game.player.faction_id
        if kind == "family":
            return (
                game.family.id
                if game.family and not game.family.extinct and game.family.world == game.player.world
                else None
            )
        if kind == "race":
            return self._player_allegiance_race(game.player)
        return None

    def _ensure_intrigue_personality(self, game: GameState, npc: SectNpc) -> dict[str, Any]:
        state = self._intrigue_state(game)
        existing = state["npcs"].get(npc.id)
        if isinstance(existing, dict) and existing.get("primary") in PERSONALITY_LABELS:
            return existing
        rng = random.Random(f"intrigue-personality:{game.seed}:{npc.id}")
        keys = list(PERSONALITY_LABELS)
        primary = rng.choice(keys)
        secondary = rng.choice([key for key in keys if key != primary]) if rng.random() < 0.22 else None
        record = {"primary": primary, "secondary": secondary, "governance_style": None}
        state["npcs"][npc.id] = record
        return record

    def _intrigue_governance_style(self, game: GameState, npc: SectNpc) -> str:
        record = self._ensure_intrigue_personality(game, npc)
        if record.get("governance_style") in STYLE_LABELS:
            return str(record["governance_style"])
        weights = {"balance": 25.0, "internal": 25.0, "diplomacy": 25.0, "military": 25.0}
        shifts = {
            "paranoid": {"balance": 10, "military": 8, "diplomacy": -8},
            "fanatical": {"military": 16, "balance": -6},
            "cautious": {"balance": 14, "military": -10},
            "smooth": {"diplomacy": 16, "military": -6},
            "forceful": {"military": 14, "internal": 4},
            "generous": {"internal": 10, "diplomacy": 8},
            "suspicious": {"balance": 10, "diplomacy": -8},
            "greedy": {"internal": 12, "military": 5},
            "restrained": {"balance": 13, "military": -8},
            "warlike": {"military": 22, "diplomacy": -10},
            "conservative": {"internal": 10, "balance": 10, "military": -5},
            "open": {"diplomacy": 13, "internal": 7},
        }
        for trait in (record.get("primary"), record.get("secondary")):
            for style, change in shifts.get(str(trait), {}).items():
                weights[style] = max(1.0, weights[style] + change)
        rng = random.Random(f"intrigue-style:{game.seed}:{npc.id}")
        record["governance_style"] = rng.choices(list(weights), weights=list(weights.values()), k=1)[0]
        return str(record["governance_style"])

    def _ensure_intrigue_faction(self, game: GameState, kind: str, faction_id: str) -> dict[str, Any]:
        state = self._intrigue_state(game)
        key = self._intrigue_key(kind, faction_id)
        record = state["factions"].setdefault(key, {
            "kind": kind, "id": faction_id, "controller_id": None, "positions": {},
            "guests": [], "prison": [], "member_contribution": {}, "unrest": 0.0,
            "fear": 0.0, "resources": 0, "policy": "balance",
        })
        record.setdefault("positions", {})
        record.setdefault("guests", [])
        record.setdefault("prison", [])
        record.setdefault("member_contribution", {})
        members = [npc for npc in self._intrigue_members(game, kind, faction_id) if npc.alive]
        for npc in members:
            self._ensure_intrigue_personality(game, npc)
        if kind == "race":
            record["controller_id"] = None
            return record
        entity = self._intrigue_entity(game, kind, faction_id)
        controller = str(record.get("controller_id") or "")
        valid_npc_ids = {npc.id for npc in members}
        player_controls = bool(
            entity and entity.world == game.player.world
            and entity.founded_by_player and entity.founder_player_id == game.id and game.player.alive
        )
        player_is_member = self._intrigue_player_faction_id(game, kind) == faction_id and game.player.alive
        player_realm, player_layer = self._actual_player_realm(game.player)
        npc_first = max(((npc.realm_index, npc.layer) for npc in members), default=(-1, -1))
        if player_is_member and (player_realm, player_layer) >= npc_first:
            player_controls = True
        if player_controls:
            controller = PLAYER_ID
        elif controller == PLAYER_ID or controller not in valid_npc_ids:
            controller = max(members, key=lambda row: (row.realm_index, row.layer, -row.age)).id if members else ""
        record["controller_id"] = controller or None
        position_ids = list(intrigue_rules().get("positions", {}).get(kind, {}))
        leader_id = position_ids[0] if position_ids else ""
        if leader_id:
            record["positions"][leader_id] = controller or None
        if not record.get("positions_initialized"):
            if controller != PLAYER_ID:
                claimed = {controller}
                ordered = sorted(members, key=lambda row: (-row.realm_index, -row.layer, row.age, row.id))
                for position_id, spec in self._intrigue_position_specs(kind).items():
                    if position_id == leader_id or position_id in {"guest_elder", "guest_retainer"}:
                        continue
                    candidate = next((npc for npc in ordered if npc.id not in claimed and npc.realm_index >= int(spec.get("minimum_realm", 0))), None)
                    if candidate:
                        record["positions"][position_id] = candidate.id
                        claimed.add(candidate.id)
            record["positions_initialized"] = True
        self._intrigue_auto_appoint_player(game, kind, faction_id, record, members)
        if controller and controller != PLAYER_ID:
            ruler = next((npc for npc in members if npc.id == controller), None)
            if ruler:
                record["policy"] = self._intrigue_governance_style(game, ruler)
        return record
