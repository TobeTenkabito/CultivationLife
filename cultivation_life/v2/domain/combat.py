from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .character import IDENTITY, LIFE
from .artifacts import artifact_static_bonuses
from .cultivation import CULTIVATION, PRACTICE
from .definitions import GameDefinitions
from .economy import INVENTORY
from .world import LOCATION
from ..kernel.bus import CommandBus, SimulationContext
from ..kernel.model import EventEnvelope, EventScope, WorldState


CONDITION = "combat.condition"
REPORT = "combat.report"
PRISONER = "combat_prisoner"
STAT_KEYS = ("might", "guard", "mobility", "sense", "sustain", "breach")


@dataclass(frozen=True, slots=True)
class ResolveCombat:
    attacker_id: str
    target_id: str
    objective: str = "duel"
    terrain: str = ""


@dataclass(frozen=True, slots=True)
class RestoreCombatCondition:
    actor_id: str
    hp_ratio: float = 1.0
    mp_ratio: float = 1.0
    reason: str = "recovery"


PATH_FACTORS: dict[str, dict[str, float]] = {
    "dao": {},
    "demonic": {"might": 1.12, "guard": 0.94, "sustain": 1.10},
    "ghost": {"might": 0.96, "mobility": 0.94, "sense": 1.22, "sustain": 1.08},
    "monster": {"might": 1.06, "guard": 1.16, "sense": 0.86, "sustain": 1.18},
    "buddhist": {"might": 0.92, "guard": 1.18, "sense": 1.10, "sustain": 1.12},
    "confucian": {"might": 0.96, "sense": 1.14, "breach": 1.12},
}


def _terrain_profile(location_id: str, override: str = "") -> dict[str, Any]:
    terrain = override.strip() or location_id
    lowered = terrain.lower()
    profile: dict[str, Any] = {
        "id": terrain or "neutral",
        "name": "寻常地势",
        "attacker": {},
        "defender": {},
    }
    rules = (
        (("mountain", "peak", "ridge", "shan"), "山岭", {"mobility": 0.94}, {"guard": 1.08, "sense": 1.04}),
        (("cave", "grotto", "crypt"), "洞窟", {"mobility": 0.91}, {"guard": 1.05, "sense": 1.08}),
        (("forest", "wood", "grove"), "密林", {"sense": 0.95}, {"mobility": 1.05, "sense": 1.04}),
        (("city", "sect", "palace", "court"), "城池禁制", {"breach": 0.95}, {"guard": 1.10, "sustain": 1.05}),
        (("sea", "river", "lake", "water"), "水域", {"mobility": 0.96}, {"sustain": 1.04}),
        (("desert", "waste", "ash"), "荒漠", {"sustain": 0.94}, {"sense": 1.03}),
    )
    for needles, name, attacker, defender in rules:
        if any(needle in lowered for needle in needles):
            profile.update(name=name, attacker=attacker, defender=defender)
            break
    return profile


def _apply_context_multipliers(
    snapshot: dict[str, Any], multipliers: dict[str, float],
) -> None:
    for stat, multiplier in multipliers.items():
        if stat in snapshot["stats"]:
            snapshot["stats"][stat] *= float(multiplier)


def _formation_summary(state: WorldState, entity_id: str) -> dict[str, Any] | None:
    formation = state.entities.get(entity_id, "formation.nine_palace") or {}
    active = formation.get("active")
    if not isinstance(active, dict):
        return None
    return {
        "id": active.get("id"),
        "name": active.get("name", "九宫阵"),
        "integrity": active.get("integrity", active.get("durability", 1.0)),
    }


def _on_character_created(context: SimulationContext, event: EventEnvelope) -> None:
    context.state.entities.put(
        str(event.payload["entity_id"]), CONDITION,
        {"hp_ratio": 1.0, "mp_ratio": 1.0},
    )


def _item_bonuses(state: WorldState, definitions: GameDefinitions, entity_id: str):
    inventory = state.entities.require(entity_id, INVENTORY)
    combat = hp = mp = 0.0
    for item_id, quantity in dict(inventory.get("items", {})).items():
        definition = definitions.items[item_id]
        combat += definition.combat_bonus * int(quantity)
        hp += definition.hp_bonus * int(quantity)
        mp += definition.mp_bonus * int(quantity)
    return combat, hp, mp


def _faction_benefits(state: WorldState, entity_id: str) -> tuple[float, float, float]:
    benefits = {"combat": 0.0, "hp": 0.0, "mp": 0.0}
    for membership in state.relations.find(
        source_id=entity_id, kind="faction_membership", active_only=False
    ):
        for key, value in dict(membership.metadata.get("permanent_benefits", {})).items():
            if key in benefits:
                benefits[key] += float(value)
    return benefits["combat"], benefits["hp"], benefits["mp"]


def combat_snapshot(
    state: WorldState, definitions: GameDefinitions, entity_id: str,
) -> dict[str, Any]:
    identity = state.entities.require(entity_id, IDENTITY)
    life = state.entities.require(entity_id, LIFE)
    cultivation = state.entities.require(entity_id, CULTIVATION)
    practice = state.entities.require(entity_id, PRACTICE)
    condition = state.entities.require(entity_id, CONDITION)
    realm = definitions.realm(str(cultivation["realm_id"]))
    layer = int(cultivation["layer"])
    progression = 1.0 + 0.12 * (layer - 1)
    technique_bonus = hp_bonus = mp_bonus = 0.0
    main_id = practice.get("main_technique_id")
    if main_id:
        technique = definitions.techniques[str(main_id)]
        technique_bonus += technique.combat_bonus
        hp_bonus += technique.hp_bonus
        mp_bonus += technique.mp_bonus
    item_combat, item_hp, item_mp = _item_bonuses(state, definitions, entity_id)
    faction_combat, faction_hp, faction_mp = _faction_benefits(state, entity_id)
    artifact = artifact_static_bonuses(state, definitions, entity_id)
    from .demonic import demonic_combat_contributions

    puppet_contribution = demonic_combat_contributions(
        state, definitions, entity_id
    )
    power = max(
        1.0,
        realm.base_power * progression + technique_bonus + item_combat + faction_combat
        + float(artifact["combat_power"])
        + float(puppet_contribution["intrinsic"]),
    )
    max_hp = (
        max(10.0, 100.0 + math.sqrt(power) * 18.0)
        * max(0.1, 1 + hp_bonus + item_hp)
        + faction_hp
        + float(cultivation.get("intrinsic_hp_bonus", 0))
        + float(artifact["max_hp"])
    )
    max_mp = (
        max(10.0, 80.0 + math.sqrt(power) * 15.0)
        * max(0.1, 1 + mp_bonus + item_mp)
        + faction_mp
        + float(cultivation.get("intrinsic_mp_bonus", 0))
        + float(artifact["max_mp"])
    )
    stats = {
        "might": power * 1.02,
        "guard": power * 0.98,
        "mobility": power,
        "sense": power,
        "sustain": power,
        "breach": power * 0.96,
    }
    for stat, factor in PATH_FACTORS.get(str(cultivation["path"]), {}).items():
        stats[stat] *= factor
    for stat, factor in dict(artifact["player_multipliers"]).items():
        stats[stat] *= float(factor)
    return {
        "entity_id": entity_id,
        "name": str(identity["name"]),
        "alive": bool(life["alive"]),
        "realm_id": realm.id,
        "realm_index": definitions.realm_index(realm.id),
        "layer": layer,
        "path": cultivation["path"],
        "power": round(power, 4),
        "max_hp": round(max_hp, 4),
        "max_mp": round(max_mp, 4),
        "hp_ratio": float(condition["hp_ratio"]),
        "mp_ratio": float(condition["mp_ratio"]),
        "stats": {key: round(value, 4) for key, value in stats.items()},
        "enemy_multipliers": dict(artifact["enemy_multipliers"]),
        "artifact_traits": list(dict.fromkeys(artifact["traits"])),
        "puppet_contribution": puppet_contribution,
        "tribulation_reduction": float(artifact["tribulation_reduction"]),
    }


def _damage(
    context: SimulationContext, attacker: dict[str, Any], defender: dict[str, Any],
    attacker_mp_ratio: float, round_number: int,
) -> float:
    offense = float(attacker["stats"]["might"]) * 0.68 + float(attacker["stats"]["breach"]) * 0.32
    if "even_round_might_40" in attacker.get("artifact_traits", []) and round_number % 2 == 0:
        offense *= 1.4
    if "odd_round_enemy_might_down_40" in defender.get("artifact_traits", []) and round_number % 2 == 1:
        offense *= 0.6
    defense = float(defender["stats"]["guard"]) * 0.78 + float(defender["stats"]["sense"]) * 0.22
    ratio = max(0.05, offense / max(1.0, defense))
    mana_factor = 0.72 + 0.28 * max(0.0, min(1.0, attacker_mp_ratio))
    fraction = max(0.035, min(0.34, 0.115 * math.sqrt(ratio) * mana_factor))
    return float(defender["max_hp"]) * fraction * context.rng.uniform(0.88, 1.12)


def _resolve_handler(definitions: GameDefinitions):
    def handler(context: SimulationContext, command: object) -> None:
        if not isinstance(command, ResolveCombat):
            raise TypeError("命令类型错误")
        if command.attacker_id != context.state.controlled_entity_id:
            raise ValueError("玩家只能以当前角色发起战斗")
        if command.attacker_id == command.target_id:
            raise ValueError("不能与自己战斗")
        if command.objective not in {"duel", "kill", "capture"}:
            raise ValueError("未知战斗目标")
        for entity_id in (command.attacker_id, command.target_id):
            if not context.state.entities.exists(entity_id):
                raise ValueError("战斗参与者不存在")
            if not bool(context.state.entities.require(entity_id, LIFE).get("alive")):
                raise ValueError("死亡角色无法参与战斗")
        attacker_location = context.state.entities.require(command.attacker_id, LOCATION)
        target_location = context.state.entities.require(command.target_id, LOCATION)
        if attacker_location != target_location:
            raise ValueError("战斗参与者必须位于同一地点")

        from .party import party_combat_snapshot

        attacker = party_combat_snapshot(
            context.state, definitions, command.attacker_id
        )
        target = party_combat_snapshot(
            context.state, definitions, command.target_id
        )
        terrain = _terrain_profile(
            str(attacker_location.get("location_id", "")), command.terrain
        )
        _apply_context_multipliers(attacker, dict(terrain["attacker"]))
        _apply_context_multipliers(target, dict(terrain["defender"]))
        for snapshot, opposing in ((attacker, target), (target, attacker)):
            if "player_debuff_immunity" in snapshot.get("artifact_traits", []):
                continue
            for stat, multiplier in dict(opposing.get("enemy_multipliers", {})).items():
                snapshot["stats"][stat] *= float(multiplier)
        hp = {
            command.attacker_id: attacker["max_hp"] * attacker["hp_ratio"],
            command.target_id: target["max_hp"] * target["hp_ratio"],
        }
        mp = {
            command.attacker_id: float(attacker["mp_ratio"]),
            command.target_id: float(target["mp_ratio"]),
        }
        first_attacker = (
            attacker["stats"]["mobility"] + attacker["stats"]["sense"]
            >= target["stats"]["mobility"] + target["stats"]["sense"]
        )
        order = (
            ((command.attacker_id, attacker), (command.target_id, target))
            if first_attacker else
            ((command.target_id, target), (command.attacker_id, attacker))
        )
        rounds: list[dict[str, Any]] = []
        for round_number in range(1, 13):
            exchanges: list[dict[str, Any]] = []
            for acting, acting_snapshot in order:
                defending = command.target_id if acting == command.attacker_id else command.attacker_id
                defending_snapshot = target if defending == command.target_id else attacker
                if hp[acting] <= 0 or hp[defending] <= 0:
                    continue
                dealt = min(hp[defending], _damage(
                    context, acting_snapshot, defending_snapshot, mp[acting], round_number
                ))
                hp[defending] -= dealt
                mp[acting] = max(0.0, mp[acting] - 0.045)
                exchanges.append({
                    "attacker_id": acting,
                    "defender_id": defending,
                    "damage": round(dealt, 4),
                    "defender_hp_ratio": round(
                        hp[defending] / float(defending_snapshot["max_hp"]), 6
                    ),
                })
            rounds.append({"round": round_number, "exchanges": exchanges})
            if hp[command.attacker_id] <= 0 or hp[command.target_id] <= 0:
                break

        if hp[command.target_id] <= 0:
            outcome = "victory"
            loser_id = command.target_id
        elif hp[command.attacker_id] <= 0:
            outcome = "defeat"
            loser_id = command.attacker_id
        else:
            attacker_ratio = hp[command.attacker_id] / float(attacker["max_hp"])
            target_ratio = hp[command.target_id] / float(target["max_hp"])
            outcome = "victory" if attacker_ratio > target_ratio + 0.05 else "defeat" if target_ratio > attacker_ratio + 0.05 else "stalemate"
            loser_id = command.target_id if outcome == "victory" else command.attacker_id if outcome == "defeat" else None

        lethal = command.objective == "kill"
        for entity_id, snapshot in ((command.attacker_id, attacker), (command.target_id, target)):
            hp_ratio = max(0.0, min(1.0, hp[entity_id] / float(snapshot["max_hp"])))
            if entity_id == loser_id and not lethal:
                hp_ratio = max(0.1, hp_ratio)
            context.state.entities.put(entity_id, CONDITION, {
                "hp_ratio": hp_ratio,
                "mp_ratio": max(0.0, min(1.0, mp[entity_id])),
            })

        captured = False
        if command.objective == "capture" and outcome == "victory":
            held_by = context.state.relations.find(target_id=command.target_id, kind=PRISONER)
            if held_by and held_by[0].source_id != command.attacker_id:
                raise ValueError("目标已被其他人拘押")
            existing = context.state.relations.find(
                source_id=command.attacker_id, target_id=command.target_id, kind=PRISONER
            )
            if not existing:
                edge = context.state.relations.add(
                    source_id=command.attacker_id,
                    target_id=command.target_id,
                    kind=PRISONER,
                    created_year=context.state.clock.year,
                    metadata={"status": "confined"},
                )
                context.emit(
                    "combat.prisoner.captured",
                    source="combat",
                    scope=EventScope.entity(command.attacker_id),
                    payload=edge.to_dict(),
                )
            captured = True

        report_id = context.state.entities.create("combat")
        report = {
            "attacker_id": command.attacker_id,
            "target_id": command.target_id,
            "objective": command.objective,
            "outcome": outcome,
            "rounds": rounds,
            "captured": captured,
            "started_year": context.state.clock.year,
            "ended_year": context.state.clock.year,
            "attacker": attacker,
            "target": target,
            "terrain": terrain,
            "formations": {
                command.attacker_id: _formation_summary(
                    context.state, command.attacker_id
                ),
                command.target_id: _formation_summary(
                    context.state, command.target_id
                ),
            },
            "final_hp_ratios": {
                command.attacker_id: context.state.entities.require(command.attacker_id, CONDITION)["hp_ratio"],
                command.target_id: context.state.entities.require(command.target_id, CONDITION)["hp_ratio"],
            },
        }
        context.state.entities.put(report_id, REPORT, report)
        context.emit(
            "combat.resolved",
            source="combat",
            scope=EventScope.entity(command.attacker_id),
            payload={"report_id": report_id, **{key: report[key] for key in ("attacker_id", "target_id", "objective", "outcome", "captured")}},
        )
        if lethal and loser_id is not None:
            context.emit(
                "character.lethal_hazard",
                source="combat",
                scope=EventScope.entity(loser_id),
                payload={"entity_id": loser_id, "reason": "战斗身亡"},
            )

    return handler


def resolve_combat(
    context: SimulationContext,
    definitions: GameDefinitions,
    *,
    attacker_id: str,
    target_id: str,
    objective: str = "duel",
    terrain: str = "",
) -> None:
    """Resolve combat inside another domain's transaction.

    Governance and story commands use this entry point so combat remains the
    sole owner of conditions, reports, captures and lethal hazards.
    """
    _resolve_handler(definitions)(
        context, ResolveCombat(attacker_id, target_id, objective, terrain)
    )


def _aggregate_team_snapshot(
    state: WorldState,
    definitions: GameDefinitions,
    member_ids: list[str],
) -> dict[str, Any]:
    snapshots = [
        combat_snapshot(state, definitions, entity_id)
        for entity_id in member_ids
        if state.entities.exists(entity_id)
        and bool(state.entities.require(entity_id, LIFE).get("alive"))
    ]
    snapshots.sort(key=lambda row: float(row["power"]), reverse=True)
    snapshots = snapshots[:3]
    if not snapshots:
        return {"power": 0.0, "members": []}
    coefficient = 0.5 if len(snapshots) == 2 else 0.25 if len(snapshots) >= 3 else 0.0
    power = float(snapshots[0]["power"]) + sum(
        float(row["power"]) for row in snapshots[1:]
    ) * coefficient
    return {
        "power": round(power, 4),
        "members": snapshots,
        "coefficient": coefficient,
    }


def resolve_team_combat(
    context: SimulationContext,
    definitions: GameDefinitions,
    *,
    attacker_id: str,
    target_ids: list[str],
    terrain: str = "",
    source: str = "combat",
) -> dict[str, Any]:
    """Resolve a non-lethal player-party versus canonical NPC team engagement."""
    if attacker_id != context.state.controlled_entity_id:
        raise ValueError("只有当前角色可以率队参战")
    from .party import party_combat_snapshot

    attacker = party_combat_snapshot(context.state, definitions, attacker_id)
    target = _aggregate_team_snapshot(context.state, definitions, target_ids)
    if not target["members"]:
        raise ValueError("敌方队伍已经无人可以出战")
    location = context.state.entities.require(attacker_id, LOCATION)
    profile = _terrain_profile(str(location.get("location_id", "")), terrain)
    attacker_multiplier = sum(map(float, profile["attacker"].values()))
    defender_multiplier = sum(map(float, profile["defender"].values()))
    attacker_power = float(attacker["power"]) * (
        attacker_multiplier / len(profile["attacker"])
        if profile["attacker"] else 1.0
    )
    target_power = float(target["power"]) * (
        defender_multiplier / len(profile["defender"])
        if profile["defender"] else 1.0
    )
    chance = max(
        0.05,
        min(0.95, 0.5 + 0.34 * math.log2(max(0.125, attacker_power / max(1.0, target_power)))),
    )
    outcome = "victory" if context.rng.random() < chance else "defeat"
    condition = context.state.entities.require(attacker_id, CONDITION)
    hp_loss = context.rng.uniform(0.06, 0.18) if outcome == "victory" else context.rng.uniform(0.18, 0.42)
    mp_loss = context.rng.uniform(0.05, 0.16) if outcome == "victory" else context.rng.uniform(0.12, 0.30)
    condition["hp_ratio"] = max(0.10, float(condition["hp_ratio"]) - hp_loss)
    condition["mp_ratio"] = max(0.0, float(condition["mp_ratio"]) - mp_loss)
    context.state.entities.put(attacker_id, CONDITION, condition)
    report_id = context.state.entities.create("combat")
    report = {
        "mode": "team",
        "attacker_id": attacker_id,
        "target_id": str(target["members"][0]["entity_id"]),
        "target_ids": [str(row["entity_id"]) for row in target["members"]],
        "objective": "repel",
        "outcome": outcome,
        "rounds": [],
        "captured": False,
        "started_year": context.state.clock.year,
        "ended_year": context.state.clock.year,
        "attacker": attacker,
        "target": target,
        "terrain": profile,
        "formations": {
            attacker_id: _formation_summary(context.state, attacker_id),
            **{
                str(row["entity_id"]): _formation_summary(
                    context.state, str(row["entity_id"])
                )
                for row in target["members"]
            },
        },
        "success_chance": round(chance, 6),
        "final_hp_ratios": {attacker_id: condition["hp_ratio"]},
    }
    context.state.entities.put(report_id, REPORT, report)
    context.emit(
        "combat.resolved",
        source=source,
        scope=EventScope.entity(attacker_id),
        payload={
            "report_id": report_id,
            "attacker_id": attacker_id,
            "target_id": report["target_id"],
            "objective": "repel",
            "outcome": outcome,
            "captured": False,
        },
    )
    return {"report_id": report_id, **report}


def _restore(context: SimulationContext, command: object) -> None:
    if not isinstance(command, RestoreCombatCondition):
        raise TypeError("命令类型错误")
    if not bool(context.state.entities.require(command.actor_id, LIFE).get("alive")):
        raise ValueError("死亡角色无法恢复")
    if not 0 <= command.hp_ratio <= 1 or not 0 <= command.mp_ratio <= 1:
        raise ValueError("恢复比例必须位于0到1之间")
    before = context.state.entities.require(command.actor_id, CONDITION)
    after = {
        "hp_ratio": max(float(before["hp_ratio"]), command.hp_ratio),
        "mp_ratio": max(float(before["mp_ratio"]), command.mp_ratio),
    }
    context.state.entities.put(command.actor_id, CONDITION, after)
    context.emit(
        "combat.condition.restored",
        source="combat",
        scope=EventScope.entity(command.actor_id),
        payload={"entity_id": command.actor_id, "before": before, "after": after, "reason": command.reason},
    )


def _on_action_completed(context: SimulationContext, event: EventEnvelope) -> None:
    if event.payload.get("action") != "rest":
        return
    actor_id = str(event.payload["actor_id"])
    condition = context.state.entities.require(actor_id, CONDITION)
    condition["hp_ratio"] = min(1.0, float(condition["hp_ratio"]) + 0.35)
    condition["mp_ratio"] = min(1.0, float(condition["mp_ratio"]) + 0.45)
    context.state.entities.put(actor_id, CONDITION, condition)


def _on_character_died(context: SimulationContext, event: EventEnvelope) -> None:
    entity_id = str(event.payload["entity_id"])
    condition = context.state.entities.get(entity_id, CONDITION)
    if condition is not None:
        condition["hp_ratio"] = 0.0
        context.state.entities.put(entity_id, CONDITION, condition)
    demonic_state = context.state.entities.get(entity_id, "demonic.state") or {}
    preserve_captives = bool(
        entity_id == context.state.controlled_entity_id
        and demonic_state.get("pending_post_battle_possession")
    )
    for edge in context.state.relations.involving(entity_id, kind=PRISONER):
        if preserve_captives and edge.source_id == entity_id:
            continue
        ended = context.state.relations.end(
            edge.relation_id, ended_year=context.state.clock.year
        )
        metadata = dict(ended.metadata)
        metadata["end_reason"] = "related_character_died"
        context.state.relations.replace_metadata(edge.relation_id, metadata)
        context.emit(
            "combat.prisoner.released",
            source="combat",
            scope=EventScope.entity(edge.target_id),
            payload={
                "relation_id": edge.relation_id,
                "captor_id": edge.source_id,
                "prisoner_id": edge.target_id,
                "reason": "related_character_died",
            },
        )


def _on_permanent_world_transition(context: SimulationContext, event: EventEnvelope) -> None:
    actor_id = str(event.payload["actor_id"])
    released: list[str] = []
    for edge in list(context.state.relations.involving(actor_id, kind=PRISONER)):
        ended = context.state.relations.end(edge.relation_id, ended_year=context.state.clock.year)
        metadata = dict(ended.metadata)
        metadata["end_reason"] = "permanent_world_transition"
        context.state.relations.replace_metadata(ended.relation_id, metadata)
        released.append(edge.relation_id)
    context.emit(
        "world.transition.acknowledged",
        source="combat",
        scope=EventScope.entity(actor_id),
        payload={
            "transaction_id": event.payload["transaction_id"],
            "actor_id": actor_id, "domain": "combat", "released_ids": released,
        },
    )


def combat_invariants(state: WorldState) -> list[str]:
    errors: list[str] = []
    for entity_id in state.entities.with_component(IDENTITY):
        condition = state.entities.get(entity_id, CONDITION)
        if condition is None:
            errors.append(f"角色 {entity_id} 缺少战斗状态")
            continue
        for key in ("hp_ratio", "mp_ratio"):
            value = float(condition.get(key, -1))
            if not 0 <= value <= 1:
                errors.append(f"角色 {entity_id} 战斗状态 {key} 非法")
    for report_id in state.entities.with_component(REPORT):
        report = state.entities.require(report_id, REPORT)
        for key in ("attacker_id", "target_id"):
            if state.entities.get(str(report.get(key, "")), IDENTITY) is None:
                errors.append(f"战报 {report_id} 引用非角色实体")
    prisoner_counts: dict[str, int] = {}
    for edge in state.relations.find(kind=PRISONER):
        if (
            state.entities.get(edge.source_id, IDENTITY) is None
            or state.entities.get(edge.target_id, IDENTITY) is None
        ):
            errors.append(f"俘虏关系端点不是角色：{edge.relation_id}")
        prisoner_counts[edge.target_id] = prisoner_counts.get(edge.target_id, 0) + 1
    if any(count > 1 for count in prisoner_counts.values()):
        errors.append("同一角色同时被多人拘押")
    return errors


def _on_story_condition_changed(context: SimulationContext, event: EventEnvelope) -> None:
    entity_id = str(event.payload["entity_id"])
    kind = str(event.payload["kind"])
    amount = float(event.payload["amount"])
    condition = context.state.entities.require(entity_id, CONDITION)
    if kind == "damage":
        condition["hp_ratio"] = max(0.0, float(condition["hp_ratio"]) - amount)
    elif kind in {"heal", "restore_hp"}:
        condition["hp_ratio"] = min(1.0, max(0.0, float(condition["hp_ratio"]) + amount))
    elif kind == "restore_mp":
        condition["mp_ratio"] = min(1.0, max(0.0, float(condition["mp_ratio"]) + amount))
    else:
        raise ValueError("未知剧情战斗资源效果")
    context.state.entities.put(entity_id, CONDITION, condition)
    if kind == "damage" and float(condition["hp_ratio"]) <= 0:
        context.emit(
            "character.lethal_hazard",
            source="combat",
            scope=EventScope.entity(entity_id),
            payload={"entity_id": entity_id, "reason": str(event.payload["reason"])},
        )


def _on_condition_drain_requested(context: SimulationContext, event: EventEnvelope) -> None:
    entity_id = str(event.payload["entity_id"])
    condition = context.state.entities.require(entity_id, CONDITION)
    condition["hp_ratio"] = max(
        0.01, float(condition["hp_ratio"]) - max(0.0, float(event.payload["hp_ratio"]))
    )
    condition["mp_ratio"] = max(
        0.0, float(condition["mp_ratio"]) - max(0.0, float(event.payload["mp_ratio"]))
    )
    context.state.entities.put(entity_id, CONDITION, condition)


def _on_condition_reset_requested(context: SimulationContext, event: EventEnvelope) -> None:
    entity_id = str(event.payload["entity_id"])
    condition = context.state.entities.require(entity_id, CONDITION)
    condition["hp_ratio"] = max(0.0, min(1.0, float(event.payload["hp_ratio"])))
    condition["mp_ratio"] = max(0.0, min(1.0, float(event.payload["mp_ratio"])))
    context.state.entities.put(entity_id, CONDITION, condition)


def register_combat_domain(bus: CommandBus, definitions: GameDefinitions) -> None:
    bus.register(ResolveCombat, _resolve_handler(definitions))
    bus.register(RestoreCombatCondition, _restore)
    bus.event_bus.register("character.created", _on_character_created)
    bus.event_bus.register("cultivation.action.completed", _on_action_completed)
    bus.event_bus.register("character.died", _on_character_died)
    bus.event_bus.register(
        "story.effect.combat_condition.changed", _on_story_condition_changed
    )
    bus.event_bus.register("world.permanent_transition.requested", _on_permanent_world_transition)
    bus.event_bus.register("combat.condition.drain.requested", _on_condition_drain_requested)
    bus.event_bus.register("combat.condition.reset.requested", _on_condition_reset_requested)


def combat_view(state: Any, definitions: GameDefinitions, entity_id: str | None = None):
    actor_id = entity_id or state.controlled_entity_id
    if actor_id is None:
        raise ValueError("游戏尚未初始化")
    latest = None
    for report_id in state.entities.with_component(REPORT):
        report = state.entities.require(report_id, REPORT)
        if actor_id in {report.get("attacker_id"), report.get("target_id")}:
            latest = {"id": report_id, **report}
    return {"snapshot": combat_snapshot(state, definitions, actor_id), "last_report": latest}
