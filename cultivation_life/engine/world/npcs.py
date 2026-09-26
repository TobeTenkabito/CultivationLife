from __future__ import annotations

import random
from typing import Any
from ...content_registry import (
    FACTION_SYSTEMS,
    GUIXU_EXCLUSIVE_TECHNIQUE_IDS,
    ITEM_CATALOG,
    MARKET_GOODS,
    PATH_NAMES,
    REALMS,
    RACE_DEFINITIONS,
    ROOT_DEFINITIONS,
    TECHNIQUE_CATALOG,
    WORLD_SYSTEMS,
)
from ...models import GameState, HistoryRecord, Player, SectNpc, SectState
from ...system.npc_system import npc_breakthrough_chance, npc_combat_power
from ...rules import can_practice_technique, expected_combat_power, divine_sense_level
from ..dependencies import NpcClassDependencies, NpcDependencies


def _select_npc_treasure(npc: SectNpc, rng: random.Random) -> str | None:
    tier = max(1, min(8, npc.realm_index))
    market_worlds = {str(row.get("world", "human")) for row in MARKET_GOODS}
    world = npc.world if npc.world in market_worlds else ("spirit" if npc.realm_index >= 6 else "human")
    candidates = [
        row for row in MARKET_GOODS
        if row["kind"] == "item" and row.get("world", "human") == world
        and int(row["tier"]) == tier
        and "currency" not in ITEM_CATALOG[row["content_id"]].tags
        and "root_manual" not in ITEM_CATALOG[row["content_id"]].tags
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda row: int(row["price"]), reverse=True)
    return str(rng.choice(candidates[: min(4, len(candidates))])["content_id"])


def _npc_power(deps: NpcDependencies, npc: SectNpc) -> float:
    treasure = ITEM_CATALOG.get(npc.treasure_item_id or "")
    return npc_combat_power(
        npc, expected_combat_power, deps._npc_root_efficiency(npc.spirit_root), treasure
    ) * max(0.1, float(getattr(npc, "combat_factor", 1.0))) * max(0.35, 1 - int(getattr(npc, "wounds", 0)) * 0.15)


def _npc_breakthrough_probability(deps: NpcDependencies, npc: SectNpc) -> float:
    if npc.realm_index >= 9 or (npc.realm_index == 8 and npc.layer >= REALMS[8].layers):
        return 0.0
    return npc_breakthrough_chance(
        npc, FACTION_SYSTEMS["npc_cultivation"], deps._npc_root_efficiency(npc.spirit_root)
    )


def _npc_faction_id(deps: NpcDependencies, game: GameState, npc_id: str) -> str | None:
    npc = deps._find_npc(game, npc_id)
    if npc and npc.faction_id and npc.faction_id in game.sects and not game.sects[npc.faction_id].extinct:
        return npc.faction_id
    return next(
        (sect_id for sect_id, sect in game.sects.items() if any(npc.id == npc_id for npc in sect.npcs)),
        None,
    )


def _sect_members(deps: NpcDependencies, game: GameState, sect: SectState) -> list[SectNpc]:
    members = {npc.id:npc for npc in sect.npcs}
    for npc in [*game.world_npcs.values(), *game.notable_npcs.values()]:
        if npc.faction_id == sect.id:
            members[npc.id] = npc
    return list(members.values())


def _find_npc(deps: NpcDependencies, game: GameState, npc_id: str) -> SectNpc | None:
    if npc_id in game.world_npcs:
        return game.world_npcs[npc_id]
    if npc_id in game.notable_npcs:
        return game.notable_npcs[npc_id]
    return next((npc for sect in game.sects.values() for npc in sect.npcs if npc.id == npc_id), None)


def _random_npc_path(faction_id: str, rng: random.Random) -> str:
    weights = FACTION_SYSTEMS["npc_path_distribution"].get(
        faction_id, {"dao": 0.55, "confucian": 0.15, "buddhist": 0.10, "demonic": 0.10, "ghost": 0.05, "monster": 0.05},
    )
    roll = rng.random()
    selected = next(reversed(weights))
    for path, weight in weights.items():
        roll -= float(weight)
        if roll <= 0:
            selected = path
            break
    return selected


def _random_npc_root(realm_index: int, rng: random.Random) -> str:
    """人界 NPC 只生成常规五行或变异灵根，且高境界自然筛去伪灵根。"""
    distributions = FACTION_SYSTEMS["npc_root_distribution"]
    weights = distributions.get(str(min(5, max(1, realm_index))), distributions["1"])
    families = list(weights)
    roll = rng.random() * sum(float(weights[name]) for name in families)
    family = families[-1]
    for name in families:
        weight = float(weights[name])
        if weight <= 0:
            continue
        roll -= weight
        if roll <= 0:
            family = name
            break
    pools = {
        "pseudo": [root_id for root_id in ROOT_DEFINITIONS if root_id.startswith("pseudo_")],
        "heavenly": [root_id for root_id in ROOT_DEFINITIONS if root_id.startswith("heavenly_")],
        "supreme": [root_id for root_id in ROOT_DEFINITIONS if root_id.startswith("supreme_")],
        "mutated": [root_id for root_id in ROOT_DEFINITIONS if root_id.startswith("mutated_")],
    }
    return rng.choice(pools[family])


def _npc_root_name(root_id: str) -> str:
    return ROOT_DEFINITIONS.get(root_id, {"name": "灵根未明"})["name"]


def _npc_root_efficiency(root_id: str) -> float:
    return float(ROOT_DEFINITIONS.get(root_id, {"efficiency": 1.0})["efficiency"])


def _mortal_root_completion_chance(player: Player) -> float:
    if player.age < 35 or not player.born_rootless or player.spirit_root != "none":
        return 0.0
    if not any(item.id.startswith("jinque_") and item.quantity > 0 for item in player.inventory):
        return 0.0
    return min(1.0, (player.age - 34) * 0.01)


def _maybe_mortal_root_completion(deps: NpcDependencies, game: GameState, rng: random.Random) -> bool:
    chance = deps._mortal_root_completion_chance(game.player)
    if chance <= 0 or rng.random() >= chance:
        return False
    event = deps.events_by_id["EVT_MORTAL_ROOT_COMPLETE_001"]
    game.pending_event = deps._instantiate_event(event, game, rng)
    game.pending_event["body"] += f"（本年逆天改命机率 {chance:.0%}）"
    return True


def _annual_world_npc_update(deps: NpcDependencies, game: GameState, rng: random.Random) -> list[str]:
    deps._advance_merchant_year(game)
    news: list[str] = []
    living_human_spirits = sum(
        npc.alive and npc.world == "human" and npc.realm_index == 5
        for npc in game.world_npcs.values()
    ) + sum(
        npc.alive and npc.world == "human" and npc.realm_index == 5
        for sect in game.sects.values() for npc in sect.npcs
    )
    simulated_npcs = [*game.world_npcs.values(), *game.notable_npcs.values()]
    for npc in simulated_npcs:
        if not npc.alive:
            continue
        npc.age += 1
        if deps._intrigue_is_imprisoned(game, npc.id):
            if npc.lifespan is not None and npc.age >= npc.lifespan:
                npc.alive = False
                npc.death_reason = "服刑期间寿元耗尽"
            continue
        if npc.wounds > 0 and rng.random() < 0.35:
            npc.wounds -= 1
        tribulation = deps._resolve_npc_periodic_tribulation(game, npc, rng, npc.title)
        if tribulation:
            if npc.world == game.player.world:
                news.append(f"{game.player.age}岁：{tribulation}")
            if not npc.alive:
                continue
        if npc.lifespan is not None and npc.age >= npc.lifespan:
            event_world = npc.world
            npc.alive = False
            npc.death_reason = "寿元耗尽，坐化于世间"
            summary = f"{npc.title}{npc.name}寿元耗尽，此后再无音讯。"
            if event_world == game.player.world:
                news.append(f"{game.player.age}岁：{summary}")
            game.history.append(HistoryRecord(
                "SYS_WORLD_NPC_FALL", 1, game.player.age, "天下讣闻", None, "npc_fallen", summary,
                {"npc_id": npc.id, "alive": [True, False]},
                ["system", "world_npc", "world_news", f"world:{event_world}"],
            ))
            continue
        crossing_to_spirit = npc.world == "human" and npc.realm_index == 4 and npc.layer == REALMS[4].layers
        event_world = npc.world
        result = deps._advance_npc_cultivation(npc, rng, not crossing_to_spirit or living_human_spirits < 1)
        if not result:
            continue
        if result["type"] == "departure":
            living_human_spirits = max(0, living_human_spirits - 1)
            summary = f"{npc.title}{npc.name}{result['new']}；在人界看来，其魂灯已熄，等同陨落。"
            outcome = "npc_departed"
        else:
            if npc.realm_index == 5:
                living_human_spirits += 1
            summary = f"{npc.title}{npc.name}由{result['old']}突破至{result['new']}。"
            outcome = "npc_breakthrough"
        if event_world == game.player.world:
            news.append(f"{game.player.age}岁：{summary}")
        game.history.append(HistoryRecord(
            "SYS_WORLD_NPC_CHANGE", 1, game.player.age, "天下异动", None, outcome, summary,
            {"npc_id": npc.id, "realm": [result["old"], result["new"]]},
            ["system", "world_npc", "world_news", f"world:{event_world}"],
        ))
    deps._maybe_notorious_npc_killing(game, rng, news)
    return news


def _maybe_notorious_npc_killing(deps: NpcDependencies, game: GameState, rng: random.Random, news: list[str]) -> None:
    protected = {
        str(row.get("id")) for row in [game.player.master, game.player.dao_companion, *game.player.dao_friends, *game.player.disciples]
        if row
    }
    villains = [
        npc for npc in game.world_npcs.values()
        if npc.alive and not npc.encountered_player and not deps._intrigue_is_imprisoned(game, npc.id)
        and (npc.notorious or npc.path == "demonic")
        and rng.random() < (0.014 if npc.path == "demonic" else 0.004)
    ]
    for villain in villains:
        villain_faction = deps._npc_faction_id(game, villain.id)
        victims = [
            npc for npc in deps._all_world_npcs(game)
            if npc.alive and not npc.notorious and npc.world == villain.world
            and npc.id not in protected and npc.realm_index < villain.realm_index
            and not (
                villain.path == "demonic" and villain_faction
                and deps._npc_faction_id(game, npc.id) == villain_faction
            )
        ]
        if not victims:
            continue
        victim = rng.choice(victims)
        victim.alive = False
        victim.death_reason = f"遭{villain.name}截杀"
        summary = f"臭名昭著的{villain.name}又造血案，{victim.name}（{deps._npc_realm_name(victim)}）遭其截杀。"
        game.history.append(HistoryRecord(
            "SYS_NOTORIOUS_KILLING", 1, game.player.age, "凶名远播", villain.id, "npc_murdered", summary,
            {"villain_id":villain.id,"victim_id":victim.id},
            ["system","world_npc","notorious","world_news",f"world:{villain.world}"],
        ))
        if game.player.world == villain.world:
            news.append(f"{game.player.age}岁：{summary}")


def _all_world_npcs(game: GameState) -> list[SectNpc]:
    return [*game.world_npcs.values(), *game.notable_npcs.values(), *(npc for sect in game.sects.values() for npc in sect.npcs)]


def _npc_lethal_chance(world: str, realm_index: int, context: str) -> float:
    config = WORLD_SYSTEMS.get("npc_mortality", {})
    if context == "duel":
        protected = config.get("protected_duel_chance", {}).get(world, {})
        if str(realm_index) in protected:
            return float(protected[str(realm_index)])
        return float(config.get("duel_lethal_chance", 0.16))
    table = config.get("elite_war_chance", {}).get(world, {})
    return float(table.get(str(realm_index), 0.02))


def _npc_lifespan_multiplier(path: str) -> int:
    if path != "monster":
        return 1
    return int(WORLD_SYSTEMS.get("monster_cultivation", {}).get("lifespan_multiplier", 3))


def _scale_npc_lifespan(deps: NpcClassDependencies, lifespan: int | None, path: str, age: int = 0) -> int | None:
    if lifespan is None:
        return None
    return max(age + 1, int(lifespan) * deps._npc_lifespan_multiplier(path))


def _maybe_npc_found_power(deps: NpcDependencies, game: GameState, rng: random.Random, news: list[str]) -> None:
    if rng.random() >= 0.012 or sum(sect.founded_by_npc and not sect.extinct for sect in game.sects.values()) >= 8:
        return
    world = game.player.world
    realm_cap = deps._world_realm_cap(world)
    realm_index = (
        (5 if rng.random() < 0.02 else 4)
        if realm_cap <= 5 else (8 if rng.random() < 0.10 else 7)
    )
    kind = rng.choice(["sect", "family"])
    serial = sum(sect.founded_by_npc for sect in game.sects.values()) + 1
    surname = rng.choice(["顾", "叶", "陆", "楚", "白", "谢", "云", "林"])
    founder_name = surname + rng.choice(["玄岳", "长风", "照夜", "问天", "清河"])
    power_name = (founder_name[0] + "氏仙族") if kind == "family" else rng.choice(["玄岳门", "长风谷", "照夜宫", "问天盟"]) + str(serial)
    sect_id = f"npc_{kind}_{game.diplomacy_unit}_{serial}"
    layer = rng.randint(1, REALMS[realm_index].layers)
    age = rng.randint(500, 1200) if realm_cap <= 5 else rng.randint(8000, 30000)
    founder = SectNpc(
        f"{sect_id}_founder", founder_name, "开山祖师" if kind == "sect" else "始祖",
        realm_index, layer, age, None if realm_index >= 6 else max(age + 1, REALMS[realm_index].lifespan[1]),
        spirit_root=deps._random_npc_root(realm_index, rng), path=rng.choice(list(PATH_NAMES)),
        race="human", world=world, faction_id=sect_id, affinity=0,
    )
    founder.lifespan = deps._scale_npc_lifespan(founder.lifespan, founder.path, founder.age)
    sect = SectState(
        sect_id, power_name, world, [founder], f"由{founder_name}自行建立的{'修仙家族' if kind == 'family' else '宗门'}。",
        path=founder.path, kind=kind, founded_by_npc=True, founder_npc_id=founder.id,
        allegiance_race=founder.race,
    )
    for _ in range(2):
        deps._recruit_sect_npc(sect, game.player.age, rng)
    game.sects[sect_id] = sect
    deps._ensure_sect_relations(game)
    summary = f"{founder_name}建立了{power_name}，一座新的{'修仙家族' if kind == 'family' else '宗门'}进入天下势力谱。"
    game.history.append(HistoryRecord("SYS_NPC_FOUND_POWER", 1, game.player.age, "新势力崛起", sect_id, "founded", summary, {"faction_id":sect_id,"kind":kind}, ["system","faction","founding","npc",f"world:{world}"]))
    news.append(f"{game.player.age}岁：{summary}")


def _advance_npc_cultivation(
    deps: NpcDependencies, npc: SectNpc, rng: random.Random, allow_spirit_crossing: bool = True,
    breakthrough_bonus: float = 0.0,
) -> dict[str, str] | None:
    if not npc.alive or npc.realm_index <= 0:
        return None
    if npc.realm_index >= len(REALMS):
        return None
    if npc.realm_index >= 9 or (npc.realm_index == 8 and npc.layer >= REALMS[8].layers):
        return None
    realm_cap = deps._world_realm_cap(npc.world)
    if npc.realm_index > realm_cap or (
        npc.world != "human" and npc.realm_index == realm_cap and npc.layer >= REALMS[realm_cap].layers
    ):
        return None
    if npc.realm_index == len(REALMS) - 1 and npc.layer >= REALMS[-1].layers:
        return None
    settings = FACTION_SYSTEMS["npc_cultivation"]
    rate = float(settings["progress_per_year"][str(npc.realm_index)])
    root_efficiency = deps._npc_root_efficiency(npc.spirit_root)
    npc.cultivation_progress += rate * root_efficiency * rng.uniform(0.82, 1.18)
    threshold = float(settings["threshold"]) * (1 + 0.06 * (npc.layer - 1))
    if npc.cultivation_progress < threshold:
        return None
    crossing_to_spirit = npc.world == "human" and npc.realm_index == 4 and npc.layer == REALMS[4].layers
    leaving_human_world = npc.world == "human" and npc.realm_index == 5 and npc.layer >= 3
    if crossing_to_spirit and not allow_spirit_crossing:
        npc.cultivation_progress = min(npc.cultivation_progress, threshold)
        return None
    success_chance = min(0.98, deps._npc_breakthrough_probability(npc) + max(0.0, float(breakthrough_bonus)))
    if rng.random() >= success_chance:
        npc.cultivation_progress = threshold * float(settings["failed_progress_retained"])
        return None
    old_name = deps._npc_realm_name(npc)
    npc.cultivation_progress = max(0.0, npc.cultivation_progress - threshold)
    if leaving_human_world:
        destination = deps._ascension_destination(npc.path)
        npc.world = destination
        npc.departed_age = npc.age
        npc.departure_reason = f"飞升{WORLD_SYSTEMS['world_names'][destination]}"
        return {"type": "departure", "old": old_name, "new": npc.departure_reason}
    current = REALMS[npc.realm_index]
    if npc.layer < current.layers:
        npc.layer += 1
        stage = "middle" if npc.layer == 4 else "late" if npc.layer == 7 else None
        stage_ranges = WORLD_SYSTEMS.get("stage_lifespan_bonus", {}).get(current.id, {})
        if stage and stage in stage_ranges and npc.lifespan is not None:
            npc.lifespan += rng.randint(*stage_ranges[stage]) * deps._npc_lifespan_multiplier(npc.path)
    else:
        npc.realm_index += 1
        npc.layer = 1
        span = REALMS[npc.realm_index].lifespan
        if span:
            rolled = rng.randint(*span) * deps._npc_lifespan_multiplier(npc.path)
            npc.lifespan = max(npc.lifespan or 0, rolled, npc.age + 1)
        else:
            npc.lifespan = None
    return {"type": "breakthrough", "old": old_name, "new": deps._npc_realm_name(npc)}


def _resolve_npc_periodic_tribulation(
    deps: NpcDependencies, game: GameState, npc: SectNpc, rng: random.Random, affiliation: str = "",
) -> str | None:
    """Resolve one NPC thunder tribulation; immortal lifespan does not mean immortal NPCs."""
    if not npc.alive or not deps._world_supports(npc.world, "ranking") or npc.realm_index < 6:
        return None
    config = WORLD_SYSTEMS["breakthrough"]["periodic_thunder"]
    if npc.next_tribulation_age is None:
        npc.next_tribulation_age = npc.age + int(config["interval_years"])
        npc.tribulation_power = float(config["base_power"]) * float(config["power_multiplier"]) ** npc.tribulation_count
        return None
    if npc.age < npc.next_tribulation_age:
        return None
    expected = expected_combat_power(npc.realm_index, npc.layer)
    own_power = deps._npc_power(npc)
    uncapped_pressure = max(1.0, float(npc.tribulation_power or config["base_power"]))
    world_cap = deps._tribulation_base_power_cap(npc.world)
    pressure = min(uncapped_pressure, world_cap) if world_cap is not None else uncapped_pressure
    preparedness = own_power / max(1.0, expected * 0.72 + pressure * 16)
    success_chance = max(0.48, min(0.985, 0.62 + preparedness * 0.24))
    old_count = npc.tribulation_count
    npc.tribulation_count += 1
    npc.next_tribulation_age += int(config["interval_years"])
    npc.tribulation_power = float(config["base_power"]) * float(config["power_multiplier"]) ** npc.tribulation_count
    prefix = f"{affiliation}{npc.name}" if affiliation else npc.name
    if rng.random() >= success_chance:
        npc.alive = False
        npc.death_reason = f"第{old_count + 1}次大天劫下灰飞烟灭"
        summary = f"{prefix}迎击第{old_count + 1}次大天劫失败，灰飞烟灭。"
        result = "npc_tribulation_fallen"
    else:
        summary = f"{prefix}扛过第{old_count + 1}次大天劫（渡过概率 {success_chance:.0%}），下一劫威力再增一倍。"
        if world_cap is not None and uncapped_pressure > world_cap:
            summary += f" 本界将实际基础雷威压制在 {world_cap:.0f}。"
        result = "npc_tribulation_survived"
    game.history.append(HistoryRecord(
        "SYS_NPC_TRIBULATION", 1, game.player.age,
        f"{WORLD_SYSTEMS['world_names'].get(npc.world, npc.world)}天劫", None, result, summary,
        {
            "npc_id": npc.id, "tribulation_count": npc.tribulation_count,
            "chance": round(success_chance, 3), "base_power": pressure,
            "uncapped_base_power": uncapped_pressure, "world_base_power_cap": world_cap,
        },
        ["system", "npc", "tribulation", "world_news", f"world:{npc.world}"],
    ))
    return summary


def _ascension_destination(path: str) -> str:
    if path == "demonic":
        return "demon"
    if path == "ghost":
        return "hell"
    if path == "monster" and "monster_realm" in WORLD_SYSTEMS.get("world_profiles", {}):
        return "monster_realm"
    return "spirit"


def _npc_realm_name(npc: SectNpc) -> str:
    definition = REALMS[npc.realm_index]
    if npc.world == "asura" and npc.realm_index >= 9:
        return WORLD_SYSTEMS.get("demonic_cultivation", {}).get("realm_names", {}).get(
            str(npc.realm_index), definition.name,
        )
    if definition.layers == 1:
        return definition.name
    if npc.path == "demonic" and definition.id != "mortal":
        name = WORLD_SYSTEMS.get("demonic_cultivation", {}).get("realm_names", {}).get(
            str(npc.realm_index), definition.name,
        )
        if definition.id == "qi":
            return f"{name}{npc.layer}层"
        stage = "初期" if npc.layer <= 3 else "中期" if npc.layer <= 6 else "后期"
        return f"{name}{stage}"
    if definition.id == "qi":
        return f"{definition.name}{npc.layer}层"
    if definition.id == "mortal":
        return definition.name
    stage = "初期" if npc.layer <= 3 else "中期" if npc.layer <= 6 else "后期"
    return f"{definition.name}{stage}"


def _stable_secret_art_roll(identity: str) -> int:
    return sum((index + 1) * ord(character) for index, character in enumerate(identity))


def _ensure_npc_concealment(deps: NpcDependencies, npc: SectNpc) -> tuple[int, int] | None:
    if (
        npc.concealed_realm_index is not None
        and 0 <= int(npc.concealed_realm_index) < npc.realm_index
    ):
        realm_index = int(npc.concealed_realm_index)
        layer = max(1, min(int(npc.concealed_layer or 1), REALMS[realm_index].layers))
        npc.concealed_layer = layer
        return realm_index, layer
    npc.concealed_realm_index = None
    npc.concealed_layer = None
    if npc.realm_index < 2:
        return None
    rules = WORLD_SYSTEMS.get("secret_arts", {})
    roll = deps._stable_secret_art_roll(f"{npc.id}|{npc.name}|收敛修为")
    chance = max(0.0, min(1.0, float(rules.get("npc_concealment_chance", 0.18))))
    if roll % 10_000 >= round(chance * 10_000):
        return None
    maximum_drop = min(
        npc.realm_index,
        max(1, int(rules.get("npc_max_realm_drop", 3))),
    )
    drop = 1 + (roll // 10_000) % maximum_drop
    realm_index = max(0, npc.realm_index - drop)
    layer = 1 + (roll // 100_000) % REALMS[realm_index].layers
    npc.concealed_realm_index = realm_index
    npc.concealed_layer = layer
    return realm_index, layer


def _npc_cultivation_perception(
    deps: NpcDependencies, game: GameState, npc: SectNpc, require_realm_visibility: bool = False,
) -> dict[str, Any]:
    concealed = deps._ensure_npc_concealment(npc)
    actual_name = deps._npc_realm_name(npc)
    if not concealed:
        visible = not require_realm_visibility or npc.realm_index <= game.player.realm_index + 1
        return {
            "realm_index": npc.realm_index,
            "layer": npc.layer,
            "realm_name": actual_name if visible else "无法看清",
            "concealed": False,
            "detected": False,
            "revealed": visible,
            "actual_realm_name": actual_name if visible else None,
            "display_power": deps._npc_power(npc) if visible else None,
        }
    concealed_realm, concealed_layer = concealed
    shell = SectNpc(
        npc.id, npc.name, npc.title, concealed_realm, concealed_layer,
        npc.age, npc.lifespan, path=npc.path, world=npc.world,
    )
    concealed_name = deps._npc_realm_name(shell)
    sense = divine_sense_level(game.player)
    detect_requirement = deps._cultivation_sense_requirement(concealed_realm, concealed_layer)
    reveal_requirement = deps._cultivation_sense_requirement(npc.realm_index, npc.layer)
    detected = sense >= detect_requirement
    revealed = sense >= reveal_requirement
    if revealed:
        realm_name = f"{concealed_name}（已识破：真实{actual_name}）"
        shown_realm, shown_layer = npc.realm_index, npc.layer
        display_power = deps._npc_power(npc)
    else:
        realm_name = f"{concealed_name}（气机有异）" if detected else concealed_name
        shown_realm, shown_layer = concealed_realm, concealed_layer
        actual_expected = max(1.0, expected_combat_power(npc.realm_index, npc.layer))
        display_power = deps._npc_power(npc) * (
            expected_combat_power(concealed_realm, concealed_layer) / actual_expected
        )
    return {
        "realm_index": shown_realm,
        "layer": shown_layer,
        "realm_name": realm_name,
        "concealed": True,
        "detected": detected,
        "revealed": revealed,
        "actual_realm_name": actual_name if revealed else None,
        "concealed_realm_name": concealed_name,
        "detect_requirement": detect_requirement,
        "reveal_requirement": reveal_requirement if revealed else None,
        "display_power": round(max(1.0, display_power), 1),
    }


def _dynamic_sect_title(npc: SectNpc, sect: SectState) -> str:
    """随修为投影宗门职位，同时保留掌门等唯一职衔。"""
    if any(marker in npc.title for marker in ("宗主","掌门","台主","住持","方丈","太上","宫主","山主","族长","祭酒","老祖","尊者")):
        return npc.title
    if sect.world == "human":
        return {0:"杂役",1:"外门弟子",2:"宗门执事",3:"结丹护法",4:"元婴长老",5:"供奉老祖"}.get(npc.realm_index,"门人")
    return {0:"杂役",1:"外门弟子",2:"内门弟子",3:"真传弟子",4:"宗门执事",5:"化神护法",6:"炼虚长老",7:"合体太上",8:"大乘老祖"}.get(npc.realm_index,"门人")


def _default_npc_main_technique(npc: SectNpc) -> str | None:
    candidates = [
        technique for technique in TECHNIQUE_CATALOG.values()
        if technique.path == npc.path and technique.grade <= max(1, npc.realm_index)
        and technique.element != "sex" and can_practice_technique(npc.spirit_root, technique.element)
        and technique.id not in GUIXU_EXCLUSIVE_TECHNIQUE_IDS
    ]
    if not candidates:
        candidates = [
            technique for technique in TECHNIQUE_CATALOG.values()
            if technique.element == "neutral"
            and technique.id not in GUIXU_EXCLUSIVE_TECHNIQUE_IDS
        ]
    return max(candidates, key=lambda technique: (technique.grade, technique.combat_bonus)).id if candidates else None


def _recruit_realm_index(roll: float, world: str = "human") -> int:
    distributions = FACTION_SYSTEMS.get("recruitment_distribution_by_world", {})
    rows = distributions.get(world, FACTION_SYSTEMS["recruitment_distribution"])
    for entry in rows:
        if roll < float(entry["upper"]):
            return int(entry["realm_index"])
    raise ValueError("宗门招募概率表未覆盖完整区间")


def _roll_recruit_age_lifespan(
    deps: NpcClassDependencies, realm_index: int, path: str, rng: random.Random, *, young: bool = False,
) -> tuple[int, int | None]:
    """Generate recruits with a meaningful amount of lifespan still remaining."""
    age_ranges = {
        0: (16, 36), 1: (18, 72), 2: (45, 150), 3: (120, 330),
        4: (280, 850), 5: (750, 2300), 6: (2200, 5800),
        7: (6000, 21000), 8: (14000, 80000), 9: (40000, 150000),
        10: (120000, 520000), 11: (420000, 1500000), 12: (1000000, 4200000),
    }
    low, high = age_ranges.get(realm_index, (18, 80))
    if young:
        high = low + max(6, (high - low) // 2)
    lifespan_range = REALMS[realm_index].lifespan
    if lifespan_range is None:
        return rng.randint(low, high), None
    lifespan = rng.randint(*lifespan_range) * deps._npc_lifespan_multiplier(path)
    minimum_remaining = max(12, int(lifespan * 0.25))
    safe_high = max(low, min(high, lifespan - minimum_remaining))
    safe_low = min(low, safe_high)
    age = rng.randint(safe_low, safe_high)
    return age, lifespan


def _recruit_sect_npc(deps: NpcDependencies, sect: SectState, world_age: int, rng: random.Random) -> SectNpc:
    realm_index = deps._recruit_realm_index(rng.random(), sect.world)
    surnames = ["顾", "叶", "陆", "楚", "白", "谢", "云", "林", "江", "闻"]
    given = ["玄", "宁", "川", "微", "岳", "霜", "澄", "昭", "离", "砚"]
    name = rng.choice(surnames) + rng.choice(given)
    layer = rng.randint(1, REALMS[realm_index].layers)
    title = "仙宫供奉" if realm_index >= 9 else "跨域客卿" if realm_index >= 5 else "加盟客卿" if realm_index >= 3 else "新晋内门" if realm_index == 2 else "新入门弟子"
    path = deps._random_npc_path(sect.id, rng)
    age, lifespan = deps._roll_recruit_age_lifespan(realm_index, path, rng)
    race = "human"
    if deps._world_supports(sect.world, "races"):
        race = rng.choice([
            race_id for race_id, definition in RACE_DEFINITIONS.items()
            if sect.world in definition.get("worlds", [])
        ])
    npc = SectNpc(
        id=f"{sect.id}_recruit_{world_age}_{len(sect.npcs)}", name=name, title=title,
        realm_index=realm_index, layer=layer, age=age, lifespan=lifespan,
        spirit_root=deps._random_npc_root(realm_index, rng),
        path=path, race=race, world=sect.world,
    )
    npc.affinity = rng.uniform(-6, 10)
    npc.treasure_item_id = deps._select_npc_treasure(npc, rng)
    sect.npcs.append(npc)
    return npc
