from __future__ import annotations

import random
import uuid
from typing import Any
from ...content_registry import PATH_NAMES, REALMS, RACE_DEFINITIONS, RACE_SYSTEMS, WORLD_SYSTEMS
from ...models import GameState, HistoryRecord, Player, SectNpc
from ...system.npc_system import npc_team_combat_power
from ...rules import expected_combat_power, has_item
from ...world_state import choose_weighted_race, push_fifo_cache
from ..dependencies import EncounterDependencies


def _generate_cultivator_target(
    deps: EncounterDependencies, player: Player, target_name: str, settings: dict[str, Any], rng: random.Random,
    game: GameState | None = None, forced_race: str | None = None,
    use_player_concealment: bool = False,
) -> dict[str, Any]:
    offsets = settings.get("realm_offsets", [[0, 1.0]])
    offset = int(rng.choices([entry[0] for entry in offsets], weights=[entry[1] for entry in offsets], k=1)[0])
    anchor_realm = player.realm_index
    concealment = player.cultivation_concealment if use_player_concealment else None
    if concealment:
        bias = float(WORLD_SYSTEMS.get("secret_arts", {}).get("concealed_enemy_bias", 0.82))
        if rng.random() < max(0.0, min(1.0, bias)):
            anchor_realm = int(concealment["realm_index"])
    target_realm_index = max(1, min(deps._world_realm_cap(player.world), anchor_realm + offset))
    target_layer = rng.randint(1, REALMS[target_realm_index].layers)
    expected = expected_combat_power(target_realm_index, target_layer)
    mean = expected * float(settings.get("expectation_multiplier", 1.0))
    sigma = expected * float(settings.get("power_sigma", 0.16))
    lower, upper = settings.get("power_bounds", [0.55, 1.5])
    sampled = rng.gauss(mean, sigma)
    target_power = max(expected * float(lower), min(expected * float(upper), sampled))
    shell = SectNpc("encounter", target_name, "", target_realm_index, target_layer, 0, 1)
    npc_rules = WORLD_SYSTEMS.get("secret_arts", {})
    if target_realm_index >= 2 and rng.random() < float(npc_rules.get("npc_concealment_chance", 0.18)):
        maximum_drop = min(target_realm_index, max(1, int(npc_rules.get("npc_max_realm_drop", 3))))
        shell.concealed_realm_index = max(0, target_realm_index - rng.randint(1, maximum_drop))
        shell.concealed_layer = rng.randint(1, REALMS[shell.concealed_realm_index].layers)
    perception = deps._npc_cultivation_perception(game, shell, True) if game else None
    visible = (
        perception["realm_name"] != "无法看清" if perception
        else target_realm_index <= player.realm_index + 1
    )
    target_race = forced_race or "human"
    if deps._world_supports(player.world, "races"):
        race_pool = [race_id for race_id, definition in RACE_DEFINITIONS.items() if player.world in definition.get("worlds", [])]
        target_race = forced_race or choose_weighted_race(
            race_pool, deps._player_allegiance_race(player), game.race_relations if game else {}, rng,
        )
        target_name = f"{RACE_DEFINITIONS[target_race]['name']}{target_name}"
    target = {
        "target_name": target_name,
        "target_power": round(max(1.0, target_power), 1),
        "primary_power": round(max(1.0, target_power), 1),
        "target_expected_power": round(expected, 1),
        "target_realm_index": target_realm_index,
        "target_layer": target_layer,
        "target_realm_visible": visible,
        "target_realm_display": (
            perception["realm_name"] if perception
            else deps._npc_realm_name(shell) if visible else "无法看清"
        ),
        "target_power_display": (
            perception["display_power"] if perception and perception["display_power"] is not None
            else round(max(1.0, target_power), 1)
        ),
        "npc_concealed_realm_index": shell.concealed_realm_index,
        "npc_concealed_layer": shell.concealed_layer,
        "combat_type": "cultivator",
        "race": target_race,
        "race_name": RACE_DEFINITIONS[target_race]["name"],
        "race_description": RACE_DEFINITIONS[target_race]["description"],
        "world": player.world,
    }
    return deps._add_enemy_party(target, settings, rng)


def _encounter_person_name(race_id: str, rng: random.Random) -> str:
    surnames = ["顾", "叶", "陆", "楚", "白", "谢", "云", "林", "闻", "景", "苍", "月"]
    given = ["玄", "宁", "川", "微", "岳", "霜", "澄", "昭", "离", "砚", "烬", "渊"]
    base = rng.choice(surnames) + rng.choice(given)
    return base if race_id == "human" else f"{RACE_DEFINITIONS.get(race_id, {'name': race_id})['name']}·{base}"


def _cache_encounter_target(deps: EncounterDependencies, game: GameState, target: dict[str, Any], rng: random.Random) -> None:
    """Stage disposable strangers; promote only repeat/important characters."""
    if target.get("combat_type") != "cultivator":
        return
    cache_limit = int(RACE_SYSTEMS.get("diplomacy", {}).get("encounter_cache_limit", 36))
    for index, member in enumerate(target.get("members", [])):
        if member.get("npc_id"):
            continue
        realm_index = int(member["realm_index"])
        layer = int(member["layer"])
        race_id = str(member.get("race", target.get("race", "human")))
        age_ranges = {
            1: (18, 95), 2: (55, 190), 3: (170, 470), 4: (420, 1350),
            5: (1000, 2900), 6: (2500, 9000), 7: (7000, 24000), 8: (15000, 90000),
        }
        age = rng.randint(*age_ranges.get(realm_index, (18, 70)))
        span = REALMS[realm_index].lifespan
        lifespan = max(age + 1, rng.randint(*span)) if span else None
        npc_id = f"encounter_{game.player.world}_{uuid.uuid4().hex[:12]}"
        name = deps._encounter_person_name(race_id, rng)
        npc = SectNpc(
            npc_id, name, str(target.get("target_name", "偶遇修士")) if index == 0 else "同行修士",
            realm_index, layer, age, lifespan,
            spirit_root=deps._random_npc_root(realm_index, rng), path=rng.choice(list(PATH_NAMES)),
            race=race_id, world=game.player.world, affinity=rng.uniform(-18, 12),
        )
        if index == 0 and target.get("npc_concealed_realm_index") is not None:
            npc.concealed_realm_index = int(target["npc_concealed_realm_index"])
            npc.concealed_layer = int(target.get("npc_concealed_layer") or 1)
        npc.lifespan = deps._scale_npc_lifespan(npc.lifespan, npc.path, npc.age)
        npc.treasure_item_id = deps._select_npc_treasure(npc, rng)
        base_power = max(1.0, deps._npc_power(npc))
        npc.combat_factor = max(0.1, float(member["power"]) / base_power)
        member.update(
            name=name, npc_id=npc_id, treasure_item_id=npc.treasure_item_id, path=npc.path,
            age=npc.age, lifespan=npc.lifespan, spirit_root=npc.spirit_root,
            gender=npc.gender,
        )
        entry = {
            "id": npc_id, "npc": npc.to_dict(), "combat_power": float(member["power"]),
            "seen_count": 1, "first_seen_age": game.player.age, "last_seen_age": game.player.age,
        }
        push_fifo_cache(game.encounter_npc_cache, entry, cache_limit)
        if deps._would_enter_spirit_ranking(game, npc, float(member["power"])):
            deps._promote_cached_npc(game, npc_id, "天榜战力")
    if target.get("members"):
        primary = target["members"][0]
        target.update(
            target_name=primary["name"], npc_id=primary.get("npc_id"),
            treasure_item_id=primary.get("treasure_item_id"), primary_power=primary["power"],
        )


def _would_enter_spirit_ranking(deps: EncounterDependencies, game: GameState, npc: SectNpc, power: float) -> bool:
    ranking_world = npc.world
    if not deps._world_supports(ranking_world, "ranking"):
        return False
    keys = [
        (entry.realm_index, entry.layer, deps._npc_power(entry))
        for entry in [
            *game.world_npcs.values(), *game.notable_npcs.values(),
            *(member for sect in game.sects.values() if sect.world == ranking_world for member in sect.npcs),
        ]
        if entry.alive and entry.world == ranking_world
    ]
    keys.append((game.player.realm_index, game.player.layer, deps._player_intrinsic_combat_power(game.player)))
    keys.sort(reverse=True)
    cutoff = keys[19] if len(keys) >= 20 else (-1, -1, -1.0)
    return (npc.realm_index, npc.layer, power) > cutoff


def _promote_cached_npc(deps: EncounterDependencies, game: GameState, npc_id: str, reason: str) -> SectNpc | None:
    entry = next((row for row in game.encounter_npc_cache if row.get("id") == npc_id), None)
    if not entry:
        return game.notable_npcs.get(npc_id)
    npc = SectNpc.from_dict(entry["npc"])
    npc.age += max(0, game.player.age - int(entry.get("last_seen_age", game.player.age)))
    game.notable_npcs[npc.id] = npc
    game.encounter_npc_cache = [row for row in game.encounter_npc_cache if row.get("id") != npc_id]
    game.history.append(HistoryRecord(
        "SYS_NPC_PROMOTED", 1, game.player.age, "人物留名", reason, "promoted",
        f"曾经偶遇的{npc.title}{npc.name}因{reason}不再只是过客，其后续命数将持续演算。",
        {"npc_id": npc.id, "reason": reason}, ["system", "npc", "world_state"],
    ))
    return npc


def _add_enemy_party(
    deps: EncounterDependencies, target: dict[str, Any], settings: dict[str, Any], rng: random.Random,
) -> dict[str, Any]:
    members = [{
        "name": target["target_name"], "power": float(target.get("primary_power", target["target_power"])),
        "display_power": float(target.get(
            "target_power_display", target.get("primary_power", target["target_power"]),
        )),
        "realm_index": int(target["target_realm_index"]), "layer": int(target["target_layer"]),
        "npc_id": target.get("npc_id"), "faction_id": target.get("faction_id"), "path": target.get("path", "dao"),
        "race": target.get("race", "human"), "treasure_item_id": target.get("treasure_item_id"),
        "notorious": bool(target.get("notorious", False)), "notoriety": int(target.get("notoriety", 0)),
    }]
    if rng.random() < float(WORLD_SYSTEMS["faction_conflict"]["npc_team_chance"]):
        total = rng.randint(2, 3)
        realm_cap = deps._world_realm_cap(str(target.get("world", "human")))
        for index in range(1, total):
            realm_index = max(1, min(realm_cap, int(target["target_realm_index"]) + rng.choice([-1, 0, 0, 1])))
            layer = rng.randint(1, REALMS[realm_index].layers)
            expected = expected_combat_power(realm_index, layer)
            members.append({
                "name": f"同行修士{index}", "power": round(max(1.0, rng.gauss(expected, expected * 0.12)), 1),
                "realm_index": realm_index, "layer": layer, "npc_id": None,
                "faction_id": target.get("faction_id"), "race": target.get("race", "human"),
                "path": target.get("path", "dao"),
                "treasure_item_id": None,
            })
    target["members"] = members
    target["target_power"] = npc_team_combat_power(member["power"] for member in members)
    target["target_power_display"] = npc_team_combat_power(
        member.get("display_power", member["power"]) for member in members
    )
    return target


def _maybe_probability_story_event(deps: EncounterDependencies, game: GameState, rng: random.Random) -> bool:
    for event in deps.events:
        if "probability_gate" not in event.get("tags", []) or event["id"] == "EVT_XIANG_NODE_001":
            continue
        world_tags = {tag for tag in event.get("tags", []) if tag.startswith("world:")}
        if world_tags and f"world:{game.player.world}" not in world_tags:
            continue
        event_id = event["id"]
        if any(record.event_id == event_id for record in game.history):
            continue
        if not deps._condition(event.get("conditions", {}), game):
            continue
        if deps._roll_escalating_event(game, event, rng):
            return True
    return False


def _maybe_artifact_synthesis(deps: EncounterDependencies, game: GameState, rng: random.Random) -> bool:
    event = deps.events_by_id["EVT_FIVE_POLES_CRAFT_001"]
    if has_item(game.player, "yuanhe_five_poles_mountain"):
        return False
    if any(record.event_id == event["id"] and record.age == game.player.age for record in game.history[-2:]):
        return False
    if not deps._condition(event["conditions"], game):
        return False
    game.pending_event = deps._instantiate_event(event, game, rng)
    return True


def _maybe_xiang_node_event(deps: EncounterDependencies, game: GameState, rng: random.Random) -> bool:
    event = deps.events_by_id["EVT_XIANG_NODE_001"]
    if any(record.event_id == event["id"] for record in game.history):
        return False
    if has_item(game.player, "spirit_node_info") or not deps._condition(event["conditions"], game):
        return False
    return deps._roll_escalating_event(game, event, rng)


def _roll_escalating_event(deps: EncounterDependencies, game: GameState, event: dict[str, Any], rng: random.Random) -> bool:
    trigger = event["trigger"]
    milestone = str(trigger["milestone"])
    game.player.milestones.setdefault(milestone, game.player.age)
    attempts = int(game.story_trigger_attempts.get(milestone, 0))
    increment = float(trigger.get("unit_increment", trigger.get("annual_increment", 0)))
    chance = min(1.0, float(trigger["base_chance"]) + attempts * increment)
    if rng.random() >= chance:
        game.story_trigger_attempts[milestone] = attempts + 1
        return False
    game.pending_event = deps._instantiate_event(event, game, rng)
    game.pending_event["body"] += f"（本行动单位触发概率 {chance:.0%}）"
    return True


def _maybe_faction_event(deps: EncounterDependencies, game: GameState, rng: random.Random) -> bool:
    faction_id = game.player.faction_id
    if (
        not faction_id
        or faction_id not in game.sects
        or game.sects[faction_id].extinct
        or deps._faction_meta(game, faction_id).get("world", "human") != game.player.world
        or rng.random() >= 0.30
    ):
        return False
    candidates: list[tuple[dict[str, Any], float]] = []
    for event in deps.events:
        tags = event.get("tags", [])
        world_tags = [tag for tag in tags if tag.startswith("world:")]
        if (
            int(WORLD_SYSTEMS.get("world_profiles", {}).get(game.player.world, {}).get("tier", 1)) >= 3
            and f"world:{game.player.world}" not in world_tags
        ):
            continue
        if world_tags and f"world:{game.player.world}" not in world_tags:
            continue
        if "faction" not in tags or "faction_join" in tags:
            continue
        if "revenge" in tags and not deps._revenge_ready(game, "faction", str(event["id"])):
            continue
        if deps._intrigue_enabled() and any(
            marker in f"{event.get('title', '')}{event.get('body', '')}"
            for marker in ("争位", "夺位", "排挤", "竞争")
        ) and not deps._intrigue_pressure_position_occupied(game, faction_id):
            # With the DLC, political rivals must occupy a scarce office;
            # an empty seat never invents an imaginary competitor.
            continue
        if "faction_unique" in tags and f"faction:{faction_id}" not in tags:
            continue
        if not deps._condition(event.get("conditions", {}), game):
            continue
        if event.get("repeat") == "once" and any(h.event_id == event["id"] for h in game.history):
            continue
        candidates.append((event, max(0.0, float(event.get("weight", 1)))))
    total = sum(weight for _, weight in candidates)
    if total <= 0:
        return False
    roll = rng.random() * total
    for event, weight in candidates:
        roll -= weight
        if roll <= 0:
            game.pending_event = deps._instantiate_event(event, game, rng)
            if "revenge" in event.get("tags", []):
                interval = deps._record_revenge_trigger(game, "faction", str(event["id"]))
                game.pending_event.setdefault("runtime", {})["revenge_cooldown_units"] = interval
            return True
    selected = candidates[-1][0]
    game.pending_event = deps._instantiate_event(selected, game, rng)
    if "revenge" in selected.get("tags", []):
        interval = deps._record_revenge_trigger(game, "faction", str(selected["id"]))
        game.pending_event.setdefault("runtime", {})["revenge_cooldown_units"] = interval
    return True
