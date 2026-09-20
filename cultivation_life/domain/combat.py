from __future__ import annotations

import copy
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
    progression = 1.0 + 0.08 * (layer - 1)
    technique_bonus = hp_bonus = mp_bonus = 0.0
    support_id = practice.get("support_technique_id")
    if support_id and str(support_id) in definitions.techniques:
        support = definitions.techniques[str(support_id)]
        hp_bonus += support.hp_bonus * support.scale
        mp_bonus += support.mp_bonus * support.scale
    qi_experience = dict(cultivation.get("qi_experience", {}))
    body = state.entities.get(entity_id, "cultivation.body") or {}
    from .cultivation import _qi_level

    for combat_id in map(str, practice.get("combat_technique_ids", [])):
        technique = definitions.techniques.get(combat_id)
        if technique is None:
            continue
        required = int(technique.combat_requirement_level)
        if required > 0 and not any(
            _qi_level(definitions, qi_experience.get(source, 0.0)) >= required
            for source in technique.sources
        ):
            continue
        if (
            technique.requires_immortal_power
            and not bool(cultivation.get("immortal_power_converted"))
        ):
            continue
        if int(body.get("layer", 0)) < int(technique.required_body_training):
            continue
        technique_bonus += technique.combat_bonus * technique.scale
    item_combat, item_hp, item_mp = _item_bonuses(state, definitions, entity_id)
    faction_combat, faction_hp, faction_mp = _faction_benefits(state, entity_id)
    artifact = artifact_static_bonuses(state, definitions, entity_id)
    from .demonic import demonic_combat_contributions

    puppet_contribution = demonic_combat_contributions(
        state, definitions, entity_id
    )
    hp_ratio = max(0.0, min(1.0, float(condition["hp_ratio"])))
    mp_ratio = max(0.0, min(1.0, float(condition["mp_ratio"])))
    status = 0.35 + 0.40 * hp_ratio + 0.25 * mp_ratio
    opportunity_required = round(
        realm.opportunity_base * (1 + 0.12 * (layer - 1))
    )
    opportunity_progress = min(
        1.5,
        float(cultivation.get("opportunity", 0))
        / max(1.0, float(opportunity_required)),
    )
    power = max(
        1.0,
        realm.base_power * progression * status
        + realm.base_power * opportunity_progress * 0.15
        + technique_bonus + item_combat + faction_combat
        + int(body.get("layer", 0)) * 8
        + float(artifact["combat_power"])
        + float(puppet_contribution["intrinsic"]),
    )
    hp_reference = float(
        100 + int(math.sqrt(realm.base_power) * 16) + layer * 8
        + int(body.get("layer", 0)) * 12
        + float(cultivation.get("intrinsic_hp_bonus", 0))
    )
    mp_reference = float(
        40 + int(math.sqrt(realm.base_power) * 20) + layer * 11
        + float(cultivation.get("intrinsic_mp_bonus", 0))
    )
    intrinsic_hp = hp_reference
    intrinsic_mp = mp_reference
    hp_carry = mp_carry = 1.0
    ghost_details: dict[str, Any] | None = None
    if state.entities.get(entity_id, "dlc.ghost.soul") is not None:
        from .ghost import ghost_combat_modifiers

        ghost_details = ghost_combat_modifiers(
            state, definitions, entity_id
        )
        soul = state.entities.require(entity_id, "dlc.ghost.soul")
        hp_reference = max(1.0, float(soul.get(
            "intrinsic_hp_reference", hp_reference
        )))
        mp_reference = max(1.0, float(soul.get(
            "intrinsic_mp_reference", mp_reference
        )))
        intrinsic_hp = max(0.0, float(soul.get("intrinsic_hp", hp_reference)))
        intrinsic_mp = max(0.0, float(soul.get("intrinsic_mp", mp_reference)))
        hp_carry = float(ghost_details["hp_multiplier"])
        mp_carry = float(ghost_details["mp_multiplier"])
    max_hp = intrinsic_hp + (
        hp_reference * hp_bonus + item_hp + faction_hp
        + float(artifact["max_hp"])
        + float((ghost_details or {}).get("external_hp", 0))
    ) * hp_carry
    max_mp = intrinsic_mp + (
        mp_reference * mp_bonus + item_mp + faction_mp
        + float(artifact["max_mp"])
        + float((ghost_details or {}).get("external_mp", 0))
    ) * mp_carry
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
    from .advanced_cultivation import active_transformation_profile

    transformation = active_transformation_profile(
        state, definitions, entity_id
    )
    for stat, factor in dict(
        transformation["stat_multipliers"]
    ).items():
        if stat in stats:
            stats[stat] *= float(factor)
    for stat, factor in dict(artifact["player_multipliers"]).items():
        stats[stat] *= float(factor)
    if ghost_details is not None:
        for stat, factor in dict(ghost_details["stats"]).items():
            stats[stat] *= float(factor)
    monster_details: dict[str, Any] | None = None
    if state.entities.get(entity_id, "dlc.monster.bloodline") is not None:
        from .monster import monster_combat_profile

        monster_details = monster_combat_profile(state, definitions, entity_id)
        if monster_details is not None:
            for stat, factor in dict(monster_details["stat_multipliers"]).items():
                stats[stat] *= float(factor)
    return {
        "entity_id": entity_id,
        "name": str(identity["name"]),
        "alive": bool(life["alive"]),
        "realm_id": realm.id,
        "realm_index": definitions.realm_index(realm.id),
        "layer": layer,
        "path": cultivation["path"],
        "power": round(power, 1),
        "max_hp": round(max_hp),
        "max_mp": round(max_mp),
        "hp_ratio": float(condition["hp_ratio"]),
        "mp_ratio": float(condition["mp_ratio"]),
        "stats": {key: round(value, 4) for key, value in stats.items()},
        "enemy_multipliers": dict(artifact["enemy_multipliers"]),
        "artifact_traits": list(dict.fromkeys(artifact["traits"])),
        "transformation_traits": list(
            dict.fromkeys(transformation["traits"])
        ),
        "transformation_contribution": transformation,
        "puppet_contribution": puppet_contribution,
        "ghost_contribution": ghost_details,
        "monster_contribution": monster_details,
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
    transformation_traits = set(attacker.get("transformation_traits", []))
    if "damage_bonus_5" in transformation_traits:
        offense *= 1.05
    if (
        "higher_realm_damage_10" in transformation_traits
        and int(attacker.get("realm_index", 0))
        < int(defender.get("realm_index", 0))
    ):
        offense *= 1.10
    defense = float(defender["stats"]["guard"]) * 0.78 + float(defender["stats"]["sense"]) * 0.22
    ratio = max(0.05, offense / max(1.0, defense))
    mana_factor = 0.72 + 0.28 * max(0.0, min(1.0, attacker_mp_ratio))
    morale_factor = max(0.5, min(1.5, float(attacker.get("morale", 50.0)) / 50.0))
    fraction = max(0.035, min(0.34, 0.115 * math.sqrt(ratio) * mana_factor * morale_factor))
    return (
        float(defender["max_hp"])
        * fraction
        * context.rng.uniform(0.88, 1.12)
        * float(attacker.get("court_damage_multiplier", 1.0))
    )


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
        if attacker_location.get("world_id") == "celestial":
            from .celestial import CELESTIAL_COURT, court_law_active

            court_ids = context.state.entities.with_component(CELESTIAL_COURT)
            court = (
                context.state.entities.require(court_ids[0], CELESTIAL_COURT)
                if court_ids else {}
            )
            martial = 1.10 if court_law_active(context.state, "martial_gods") else 1.0
            wanted = set(map(str, court.get("wanted_ids", [])))
            attacker["court_damage_multiplier"] = martial * (
                1.10 if command.target_id in wanted else 1.0
            )
            target["court_damage_multiplier"] = martial * (
                1.10 if command.attacker_id in wanted else 1.0
            )
            if court_law_active(context.state, "universal_protection"):
                if command.attacker_id not in wanted:
                    court.setdefault("wanted_ids", []).append(command.attacker_id)
                    context.state.entities.put(court_ids[0], CELESTIAL_COURT, court)
            if court_law_active(context.state, "immortal_slaughter"):
                from .story import STORY_STATE

                story = context.state.entities.get(command.attacker_id, STORY_STATE)
                if story is not None:
                    attributes = dict(story.get("attributes", {}))
                    attributes["karma"] = max(0.0, float(attributes.get("karma", 0)) - 10)
                    story["attributes"] = attributes
                    context.state.entities.put(command.attacker_id, STORY_STATE, story)
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
        morale = {command.attacker_id: 50.0, command.target_id: 50.0}
        participants = (
            (command.attacker_id, command.target_id),
            (command.target_id, command.attacker_id),
        )
        for owner_id, enemy_id in participants:
            owner_snapshot = (
                attacker if owner_id == command.attacker_id else target
            )
            enemy_snapshot = (
                target if enemy_id == command.target_id else attacker
            )
            owner_traits = set(
                owner_snapshot.get("transformation_traits", [])
            )
            if (
                "dragon_pressure" in owner_traits
                and int(owner_snapshot["realm_index"])
                >= int(enemy_snapshot["realm_index"])
            ):
                morale[enemy_id] = min(morale[enemy_id], 42.5)
            if "first_round_full_state" in owner_traits:
                hp[owner_id] = float(owner_snapshot["max_hp"])
        base_snapshots = {
            command.attacker_id: attacker,
            command.target_id: target,
        }
        defeat_prevented: set[str] = set()
        rounds: list[dict[str, Any]] = []
        for round_number in range(1, 13):
            from .monster import evaluate_custom_lineage

            round_snapshots = {
                entity_id: copy.deepcopy(snapshot)
                for entity_id, snapshot in base_snapshots.items()
            }
            lineage_events: list[dict[str, Any]] = []
            terrain_id = str(command.terrain or terrain["id"])
            for owner_id, enemy_id in participants:
                owner_snapshot = base_snapshots[owner_id]
                enemy_snapshot = base_snapshots[enemy_id]
                result = evaluate_custom_lineage(
                    context.state, definitions, owner_id,
                    phase="round_start", round_no=round_number,
                    terrain=terrain_id,
                    owner_state=max(0.0, hp[owner_id] / float(owner_snapshot["max_hp"])),
                    enemy_state=max(0.0, hp[enemy_id] / float(enemy_snapshot["max_hp"])),
                    owner_morale=morale[owner_id], enemy_morale=morale[enemy_id],
                )
                _apply_context_multipliers(
                    round_snapshots[owner_id],
                    dict(result["owner_stat_multipliers"]),
                )
                _apply_context_multipliers(
                    round_snapshots[enemy_id],
                    dict(result["enemy_stat_multipliers"]),
                )
                hp[owner_id] = min(
                    float(owner_snapshot["max_hp"]),
                    hp[owner_id] + float(result["owner_state_delta"]) * float(owner_snapshot["max_hp"]),
                )
                hp[enemy_id] = min(
                    float(enemy_snapshot["max_hp"]),
                    hp[enemy_id] + float(result["enemy_state_delta"]) * float(enemy_snapshot["max_hp"]),
                )
                morale[owner_id] = max(
                    0.0, min(100.0, morale[owner_id] + float(result["owner_morale_delta"]))
                )
                morale[enemy_id] = max(
                    0.0, min(100.0, morale[enemy_id] + float(result["enemy_morale_delta"]))
                )
                lineage_events.extend(result["events"])
            for owner_id, enemy_id in participants:
                owner_traits = set(
                    base_snapshots[owner_id].get(
                        "transformation_traits", []
                    )
                )
                if "morale_drain_5" in owner_traits:
                    morale[enemy_id] = max(0.0, morale[enemy_id] - 5.0)
                if "steadfast" in owner_traits:
                    morale[owner_id] = max(25.0, morale[owner_id])
                if round_number >= 4 and "round4_regen_10" in owner_traits:
                    hp[owner_id] = min(
                        float(base_snapshots[owner_id]["max_hp"]),
                        hp[owner_id]
                        + float(base_snapshots[owner_id]["max_hp"]) * 0.10,
                    )
            for entity_id, snapshot in round_snapshots.items():
                snapshot["morale"] = morale[entity_id]
            exchanges: list[dict[str, Any]] = []
            attacker_initiative = (
                float(round_snapshots[command.attacker_id]["stats"]["mobility"])
                + float(round_snapshots[command.attacker_id]["stats"]["sense"])
            )
            target_initiative = (
                float(round_snapshots[command.target_id]["stats"]["mobility"])
                + float(round_snapshots[command.target_id]["stats"]["sense"])
            )
            if round_number == 1 and terrain["name"] in {
                "寻常地势", "水域", "荒漠",
            }:
                if "airborne" in attacker.get("transformation_traits", []):
                    attacker_initiative *= 1.08
                if "airborne" in target.get("transformation_traits", []):
                    target_initiative *= 1.08
            attacker_pressure = (
                "dragon_pressure" in attacker.get("transformation_traits", [])
                and int(attacker["realm_index"]) >= int(target["realm_index"])
                and round_number <= 2
            )
            target_pressure = (
                "dragon_pressure" in target.get("transformation_traits", [])
                and int(target["realm_index"]) >= int(attacker["realm_index"])
                and round_number <= 2
            )
            first_id = (
                command.attacker_id
                if attacker_pressure or (
                    not target_pressure
                    and attacker_initiative >= target_initiative
                )
                else command.target_id
            )
            second_id = (
                command.target_id
                if first_id == command.attacker_id
                else command.attacker_id
            )
            round_order = (
                (first_id, round_snapshots[first_id]),
                (second_id, round_snapshots[second_id]),
            )
            for acting, acting_snapshot in round_order:
                defending = command.target_id if acting == command.attacker_id else command.attacker_id
                defending_snapshot = round_snapshots[defending]
                if hp[acting] <= 0 or hp[defending] <= 0:
                    continue
                dealt = min(hp[defending], _damage(
                    context, acting_snapshot, defending_snapshot, mp[acting], round_number
                ))
                hp[defending] -= dealt
                defending_traits = set(
                    defending_snapshot.get("transformation_traits", [])
                )
                if (
                    hp[defending] <= 0
                    and "prevent_defeat_once" in defending_traits
                    and defending not in defeat_prevented
                ):
                    hp[defending] = max(
                        1.0, float(defending_snapshot["max_hp"]) * 0.15
                    )
                    defeat_prevented.add(defending)
                mp[acting] = max(0.0, mp[acting] - 0.045)
                exchanges.append({
                    "attacker_id": acting,
                    "defender_id": defending,
                    "damage": round(dealt, 4),
                    "defender_hp_ratio": round(
                        hp[defending] / float(defending_snapshot["max_hp"]), 6
                    ),
                })
            for owner_id, enemy_id in participants:
                owner_snapshot = base_snapshots[owner_id]
                enemy_snapshot = base_snapshots[enemy_id]
                result = evaluate_custom_lineage(
                    context.state, definitions, owner_id,
                    phase="round_end", round_no=round_number,
                    terrain=terrain_id,
                    owner_state=max(0.0, hp[owner_id] / float(owner_snapshot["max_hp"])),
                    enemy_state=max(0.0, hp[enemy_id] / float(enemy_snapshot["max_hp"])),
                    owner_morale=morale[owner_id], enemy_morale=morale[enemy_id],
                )
                hp[owner_id] = min(
                    float(owner_snapshot["max_hp"]),
                    hp[owner_id] + float(result["owner_state_delta"]) * float(owner_snapshot["max_hp"]),
                )
                hp[enemy_id] = min(
                    float(enemy_snapshot["max_hp"]),
                    hp[enemy_id] + float(result["enemy_state_delta"]) * float(enemy_snapshot["max_hp"]),
                )
                morale[owner_id] = max(
                    0.0, min(100.0, morale[owner_id] + float(result["owner_morale_delta"]))
                )
                morale[enemy_id] = max(
                    0.0, min(100.0, morale[enemy_id] + float(result["enemy_morale_delta"]))
                )
                lineage_events.extend(result["events"])
            rounds.append({
                "round": round_number,
                "initiative": (
                    "attacker" if round_order[0][0] == command.attacker_id
                    else "target"
                ),
                "exchanges": exchanges,
                "lineage_events": lineage_events,
                "morale": dict(morale),
                # A combat report is persisted gameplay data, not merely a log of
                # attacks.  Keep the complete post-round state so every client can
                # render the historical battle without trying to reconstruct it
                # from the current character condition (which may have changed).
                "hp": {
                    entity_id: round(max(0.0, value), 4)
                    for entity_id, value in hp.items()
                },
                "hp_ratios": {
                    entity_id: round(
                        max(0.0, value)
                        / max(1.0, float(base_snapshots[entity_id]["max_hp"])),
                        6,
                    )
                    for entity_id, value in hp.items()
                },
                "mp_ratios": {
                    entity_id: round(max(0.0, min(1.0, value)), 6)
                    for entity_id, value in mp.items()
                },
            })
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
            "final_morale": dict(morale),
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
