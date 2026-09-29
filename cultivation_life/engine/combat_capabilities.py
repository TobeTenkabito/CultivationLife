"""Game-state adapter for the pure voisinage engine.

Only this boundary locates persistent owners and writes resource ledgers back.
Cached strangers, family dictionaries and normal NPCs retain one authoritative
record; a temporary SectNpc returned by a presentation helper is never written.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..models import GameState
from ..rules import max_mp
from ..system.combat.contracts import Combatant, ResourceSupply, voisinage_definitions, resolve_source
from ..system.doctrine.provider import battle_sources, conversion_state
from ..system.combat.voisinages import VoisinageBattle
from ..system.combat.npc_lifecycle import NpcResourceBinding, prepare
from ..system.combat_system import BattleUnit, PlayerCombatSystem


def persistent_owner(game: GameState, key: str) -> Any | None:
    return persistent_owners(game, {key}).get(key)


def persistent_owners(game: GameState, keys: set[str]) -> dict[str, Any]:
    """One bounded lookup per battle, not a full-world scan per participant.

    No persistent index: recruitment, death and cache promotion cannot leave
    stale pointers. Precedence matches the authoritative family record.
    """
    pending, found = set(keys), {}

    def collect(key, owner):
        if key in pending:
            found[key] = owner
            pending.remove(key)

    collect("player", game.player)
    if game.family and pending:
        for npc in game.family.npcs:
            collect(npc.id, npc)
    for group in (game.world_npcs, game.notable_npcs):
        for key in tuple(pending):
            if key in group:
                collect(key, group[key])
    for sect in game.sects.values():
        if not pending:
            break
        for npc in sect.npcs:
            collect(npc.id, npc)
    if pending:
        for row in game.encounter_npc_cache:
            collect(row.get("id"), row["npc"])
    if pending:
        for group in (game.player.offspring, game.player.puppets):
            for row in group:
                collect(row.get("id"), row)
    if pending:
        for row in (game.player.master, game.player.dao_companion, *game.player.dao_friends,
                    *game.player.disciples, *game.player.concubines):
            if row:
                collect(row.get("id"), row)
    return found


@dataclass
class CapabilityBinding:
    battle: VoisinageBattle
    owners: dict[str, Any]
    resources: dict[str, NpcResourceBinding]

    def commit(self, updates: list[dict[str, Any]], *, lethal: bool = False) -> None:
        for update in updates:
            owner = self.owners.get(update["id"])
            if owner is None:
                continue
            if update["resource_link"] == "legacy_mp":
                # Linked resource costs are authoritative, including voisinage-only
                # rounds and stories which normally waive conventional MP loss.
                owner.mp = update["current"]
                continue
            if update['id'] == 'player' and owner.transcendence is None:
                from ..system.immortal_aperture import available, commit_energy
                if available(owner):
                    commit_energy(owner, update['current'])
                    continue
            state = owner.get("transcendence") if isinstance(owner, dict) else owner.transcendence
            if update["id"] in self.resources:
                self.resources[update["id"]].commit(update["current"])
            elif state is not None:
                state["current"] = update["current"]
            if update["id"] == "player":
                continue
            wounds = min(4, int((1 - update["vitality"]) * 4))
            if isinstance(owner, dict):
                owner["wounds"] = max(int(owner.get("wounds", 0)), wounds)
                if lethal and update["vitality"] <= 0 and not update["suppressed"]:
                    owner.update(alive=False, death_reason="仙域斗法中陨落")
            else:
                owner.wounds = max(owner.wounds, wounds)
                if lethal and update["vitality"] <= 0 and not update["suppressed"]:
                    owner.alive, owner.death_reason = False, "仙域斗法中陨落"


def bind_capabilities(game: GameState, player_units: list[BattleUnit], target: dict[str, Any],
                      config: Mapping[str, Any]) -> CapabilityBinding:
    definitions = voisinage_definitions(config)
    owners: dict[str, Any] = {}
    resources: dict[str, NpcResourceBinding] = {}
    combatants: list[Combatant] = []
    raw_enemies = target.get("members") or [target]
    ephemeral = {str(row.get("npc_id") or f"enemy-{index}"): row for index, row in enumerate(raw_enemies)}
    ephemeral.update({str(row.get("npc_id") or f"story-ally-{index}"): row
                      for index, row in enumerate(target.get("player_allies", []))})
    rosters = (("player", player_units), ("enemy", PlayerCombatSystem._enemy_units(target)))
    persistent = persistent_owners(game, {unit.id for _, units in rosters for unit in units})
    sources = battle_sources(game, {**ephemeral, **persistent})
    for side, units in rosters:
        for unit in units:
            owner = persistent.get(unit.id)
            if owner is None:
                owner = ephemeral.get(unit.id)
            state = owner.get("transcendence") if isinstance(owner, dict) else getattr(owner, "transcendence", None)
            # Absence means legacy content, for players and NPCs alike. The
            # conversion/attainment provider explicitly opts actors into this
            # schema; realm alone must not fabricate resource mastery.
            if unit.id != "player" and state and state.get("resource_link") == "legacy_mp":
                raise ValueError("Only the player currently owns a legacy MP pool")
            if unit.id != "player" and state is not None:
                resources[unit.id] = prepare(owner, game.player.age, config)
                state = resources[unit.id].state
                from ..system.immortal_aperture import lower_world
                if lower_world(game.player) and sources.get(unit.id):
                    ledger = owner.get('transcendence') if isinstance(owner, dict) else owner.transcendence
                    imitation = ledger.setdefault('imitation', dict(capacity=60, current=20, conversion=1,
                        resource_link='independent', force_tier=1, ward_tier=1, attack_cost=0, ward_cost=0))
                    resources[unit.id] = NpcResourceBinding(dict(imitation), imitation)
                    state = resources[unit.id].state
            elif (unit.id == "player" and state is None and game.player.realm_index >= 9
                  and game.player.immortal_power_converted):
                # Existing conversion is an explicit fact; realm alone grants
                # nothing. Use the one MP pool and never fabricate attainment.
                state = config.get("converted_player_state")
            if unit.id == "player" and game.player.transcendence is None:
                state = conversion_state(game.player) or state
            if unit.id == 'player' and state is not None:
                from ..system.immortal_cultivation import golden_light
                state = {**state, 'ward_tier': 2 if golden_light(game.player) else 1}
            capabilities = resolve_source(
                state, definitions, sources.get(unit.id),
                linked_current=game.player.mp if unit.id == "player" else 0,
                linked_capacity=max_mp(game.player) if unit.id == "player" else 0,
            )
            combatants.append(Combatant(unit.id, unit.name, side, unit.power, capabilities, unit.integrity))
            if owner is not None:
                owners[unit.id] = owner
    supplies = tuple(ResourceSupply(**row) for row in target.get("resource_supplies", []))
    return CapabilityBinding(VoisinageBattle(combatants, contest_ratio=float(config.get("contest_ratio", 1.25)),
                                         supplies=supplies), owners, resources)
