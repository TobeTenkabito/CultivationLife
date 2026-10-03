"""Game-state adapter for the pure voisinage engine.

Only this boundary locates persistent owners and writes resource ledgers back.
Cached strangers, family dictionaries and normal NPCs retain one authoritative
record; a temporary SectNpc returned by a presentation helper is never written.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping

from ..models import GameState
from ..rules import max_mp, max_hp
from .combat.contracts import Combatant, ResourceSupply, VoisinageSeal, voisinage_definitions, resolve_source
from .doctrine.provider import battle_sources, conversion_state
from .combat.voisinages import VoisinageBattle
from .combat.npc_lifecycle import NpcResourceBinding, prepare, commit_condition
from .combat_system import BattleUnit, PlayerCombatSystem


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
                from .immortal_aperture import available, commit_energy
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
            commit_condition(owner, update, lethal=lethal)


def bind_capabilities(game: GameState, player_units: list[BattleUnit], target: dict[str, Any],
                      config: Mapping[str, Any]) -> CapabilityBinding:
    definitions = voisinage_definitions(config)
    for key, definition in voisinage_definitions({"voisinages": target.get("voisinages", [])}).items():
        if key in definitions:
            raise ValueError(f"Duplicate battle voisinage: {key}")
        definitions[key] = definition
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
                source = sources.get(unit.id)
                imitation = bool(source and any(d.id.startswith('spirit:') for d in source.voisinages))
                resources[unit.id] = prepare(owner, game.player.age, config, imitation=imitation)
                state = resources[unit.id].state
            elif (unit.id == "player" and state is None and game.player.realm_index >= 9
                  and game.player.immortal_power_converted):
                # Existing conversion is an explicit fact; realm alone grants
                # nothing. Use the one MP pool and never fabricate attainment.
                state = config.get("converted_player_state")
            if unit.id == "player" and game.player.transcendence is None:
                state = conversion_state(game.player) or state
            capabilities = resolve_source(
                state, definitions, sources.get(unit.id),
                linked_current=game.player.mp if unit.id == "player" else 0,
                linked_capacity=max_mp(game.player) if unit.id == "player" else 0,
            )
            if unit.id == "player" and target.get("player_interventions"):
                capabilities = replace(capabilities, interventions=(
                    *capabilities.interventions, *target["player_interventions"]))
            from .cultivation_ranks import npc_golden_light
            from .immortal_cultivation import golden_light
            from .asura import active as asura_active
            ward = (golden_light(game.player) or (asura_active(game.player) and game.player.asura_cultivation.get('body_level', 0) >= 20)) if unit.id == 'player' else npc_golden_light(owner)
            capabilities = replace(capabilities, ward_tier=2 if ward else 1, ward_cost=0)
            from .cultivation_ranks import rank_for
            from .combat.npc_lifecycle import read
            if unit.id == 'player':
                from .immortal_aperture import true_realm, investment_multiplier
                from .combat_plan import effective_plan
                plan = effective_plan(game.player)
                multiplier = investment_multiplier(game.player)
                rank = rank_for(true_realm(game.player), int((game.player.sealed_cultivation or {}).get('layer', game.player.layer)))
                if plan['manual']:
                    capabilities = replace(capabilities, stance=plan['stance'], investment=plan['investment'],
                        protect_ids=tuple(u.id for u in player_units if u.id != 'player'))
            else:
                realm, layer = read(owner, 'realm_index', unit.realm_index), read(owner, 'layer', read(owner, 'target_layer', 1))
                rank = rank_for(read(owner, 'true_realm_index', realm), layer)
                multiplier = 1 + .5 * max(0, (realm - 9) * 3 + (layer - 1) // 3)
                if game.player.world != 'celestial':
                    multiplier = 1
            limit = max((d.max_investment for d in capabilities.voisinages), default=0) * multiplier
            capabilities = replace(capabilities, investment_limit=limit)
            combatants.append(Combatant(unit.id, unit.name, side, unit.power, capabilities, unit.integrity, rank,
                min(1, max(0, game.player.hp / max(1, max_hp(game.player))))
                if unit.id == "player" else min(1, max(.01, 1 - .15 * read(owner, "wounds", 0)))))
            if owner is not None:
                owners[unit.id] = owner
    supplies = tuple(ResourceSupply(**row) for row in target.get("resource_supplies", []))
    seals = tuple(VoisinageSeal(**row) for row in target.get("voisinage_seals", []))
    return CapabilityBinding(VoisinageBattle(combatants, contest_ratio=float(config.get("contest_ratio", 1.25)),
                                         supplies=supplies, seals=seals), owners, resources)
