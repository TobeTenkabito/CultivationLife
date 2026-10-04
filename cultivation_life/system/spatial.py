"""Save-local spatial instances, rift clocks and isolation policy.

Generated definitions are never inserted into shared content registries. Dormant
instances retain their data but have no yearly simulation cost.
"""

import copy
import random

from ..content_registry import WORLD_SYSTEMS, REALMS
from ..models import Item, Technique, SectNpc, HistoryRecord
from ..rules import learn_technique
from . import talismans
from .formation_system import active_formation_profile

SPECIAL_WORLDS = frozenset({"rift", "lost"})
LOCAL_COMMANDS = frozenset(
    {
        "assert_ghost_operation_allowed",
        "assert_buddhist_operation_allowed",
        "assert_guixu_operation_allowed",
        "get_game",
        "present",
        "advance",
        "choose",
        "spatial_action",
        "talisman_action",
        "breakthrough",
        "body_breakthrough",
        "divine_sense_breakthrough",
        "manage_secret_art",
        "use_item",
        "equip_known_technique",
        "upgrade_technique",
        "merge_technique_manuals",
        "update_setting",
        "set_world_news_debug",
        "update_combat_plan",
        "preview_formation",
        "save_formation",
        "activate_formation",
        "deactivate_formation",
        "delete_formation",
        "list_games",
        "list_achievements",
    }
)


def cfg():
    return WORLD_SYSTEMS["spatial_rifts"]


def ensure(game):
    state = game.spatial_state
    state.setdefault("instances", {})
    state.setdefault("rifts", [])
    state.setdefault("current", None)
    state.setdefault("sequence", 0)
    state.setdefault("next_spawn_age", game.player.age + 20)
    return state


def current(game):
    state = game.spatial_state
    return state.get("instances", {}).get(state.get("current"))


def guard(game, command):
    if game.player.world in SPECIAL_WORLDS and command not in LOCAL_COMMANDS:
        raise ValueError("独立空间与外界隔绝；请使用空间内的修炼、探索和人物入口")


def journal(game, text):
    game.history.append(
        HistoryRecord(
            "SYS_SPATIAL",
            1,
            game.player.age,
            "空间裂缝",
            None,
            "resolved",
            text,
            {},
            ["spatial", "world:global"],
        )
    )


def new_rift(game, rng, maps, *, controlled=False):
    state, p = ensure(game), game.player
    state["sequence"] += 1
    scene = current(game)
    locations = scene["locations"] if scene else maps.worlds[p.world]["locations"]
    local_id = scene["location_id"] if scene else p.location_id
    row = dict(
        id=f"rift_{state['sequence']}",
        world=p.world,
        instance_id=state["current"],
        location_id=local_id if controlled else rng.choice(locations)["id"],
        created_age=p.age,
        expires_age=p.age
        + max(cfg()["lifetime_years"], max(WORLD_SYSTEMS["time_units"].values()) + 100),
        requirement=0 if controlled else rng.randint(15, 110),
        controlled=controlled,
    )
    state["rifts"].append(row)
    return row


def tick(game, rng, maps):
    state, p = ensure(game), game.player
    state["rifts"][:] = [r for r in state["rifts"] if r["expires_age"] > p.age]
    scene = current(game)
    if scene:
        if scene["kind"] == "secluded" and p.age >= scene["next_open_age"]:
            if rng.random() < cfg()["reopen_chance"]:
                new_rift(game, rng, maps, controlled=True)
                journal(game, "秘境界壁再度出现空间裂缝；可于闭合前离开。")
                scene["next_open_age"] = (
                    p.age + cfg()["lifetime_years"] + cfg()["reopen_interval"]
                )
            else:
                scene["next_open_age"] = p.age + cfg()["reopen_interval"]
        # Only the occupied instance ages, and all persons live in its own
        # authoritative table. They never enter an outside NPC spawn pool.
        for npc in scene["npcs"]:
            if not npc["alive"]:
                continue
            npc["age"] += 1
            if npc["lifespan"] is not None and npc["age"] >= npc["lifespan"]:
                npc["alive"] = False
                npc["death_reason"] = "寿元已尽"
            if npc["realm_index"] >= 6 and p.age >= npc["next_tribulation_age"]:
                npc["tribulation_count"] += 1
                npc["next_tribulation_age"] = p.age + 3000
                if rng.random() < 0.2:
                    npc["alive"] = False
                    npc["death_reason"] = "失落界面雷劫"
    if p.world != "rift" and p.age >= state["next_spawn_age"]:
        state["next_spawn_age"] = p.age + cfg()["spawn_interval"]
        local = [
            r
            for r in state["rifts"]
            if r["world"] == p.world and r["instance_id"] == state["current"]
        ]
        if len(local) < 3 and rng.random() < cfg()["spawn_chance"]:
            new_rift(game, rng, maps)


def create_instance(game, rng, kind):
    state = ensure(game)
    state["sequence"] += 1
    identity = f"{kind}_{state['sequence']}"
    # A dedicated generator bounds generation cost and makes each instance
    # independent of how often its view is requested.
    generator = random.Random(rng.getrandbits(64))
    stem = generator.choice(["苍", "玄", "霜", "赤", "玉", "幽"]) + generator.choice(
        ["岚", "岑", "渊", "陵", "岳", "泽"]
    )
    name = stem + ("秘境" if kind == "secluded" else "界")
    locations = [
        dict(
            id=f"{identity}_map_{i}",
            name=stem + generator.choice(["古原", "灵谷", "荒海", "天山"]) + str(i + 1),
        )
        for i in range(4)
    ]
    materials = [
        dict(
            id=f"SPATIAL_{identity}_material_{i}",
            name=stem + suffix,
            quantity=1,
            tags=["spatial_exclusive", "material"],
            description=f"仅可在{name}内获得。",
            opportunity_bonus=0,
        )
        for i, suffix in enumerate(["灵髓", "界晶", "道果"])
    ]
    # Technique is a dataclass whose save form is the dataclass dictionary.
    from dataclasses import asdict

    techniques = [
        asdict(
            Technique(
                id=f"SPATIAL_{identity}_technique_{i}",
                name=stem + suffix,
                path=game.player.path,
                element="neutral",
                grade=generator.randint(1, 8),
                combat_bonus=generator.uniform(0.03, 0.12),
                opportunity_bonus=generator.uniform(0.1, 0.4),
            )
        )
        for i, suffix in enumerate(["养元经", "御灵诀", "混元法"])
    ]
    sects = (
        [
            dict(
                id=f"{identity}_sect_{i}",
                name=stem + suffix,
                location_id=locations[i]["id"],
            )
            for i, suffix in enumerate(["宗", "阁", "门"])
        ]
        if kind == "lost"
        else []
    )
    npcs = []
    for i in range(9 if kind == "lost" else 0):
        rank = generator.randint(1, 8)
        npc = SectNpc(
            f"{identity}_npc_{i}",
            generator.choice(["林", "顾", "沈", "裴"])
            + generator.choice(["玄川", "清衡", "玉微", "长庚"])
            + str(i + 1),
            "散修" if i % 3 == 0 else "门人",
            rank,
            generator.randint(1, 9),
            generator.randint(20, 80),
            generator.randint(*REALMS[rank].lifespan)
            if REALMS[rank].lifespan
            else None,
            spirit_root=generator.choice(
                [
                    "supreme_metal",
                    "supreme_wood",
                    "supreme_water",
                    "supreme_fire",
                    "supreme_earth",
                ]
            ),
            world="lost",
            faction_id=sects[i % 3]["id"],
            affinity=0,
            next_tribulation_age=game.player.age + 3000,
            tribulation_count=0,
        )
        npcs.append(npc.to_dict())
    scene = dict(
        id=identity,
        name=name,
        kind=kind,
        tier=-1 if kind == "secluded" else 0,
        origin_world=game.player.world,
        locations=locations,
        location_id=locations[0]["id"],
        materials=materials,
        techniques=techniques,
        npcs=npcs,
        sects=sects,
        joined_sect=None,
        next_open_age=game.player.age + cfg()["reopen_interval"],
        visits=0,
        explored=0,
    )
    state["instances"][identity] = scene
    return scene


def protection(game, *, consume=False):
    p = game.player
    ward = (
        talismans.consume(p, "protection")
        if consume
        else talismans.read(p, "protection")
    )
    profile = active_formation_profile(p)
    growth = (
        float(profile.get("metrics", {}).get("growth", 0))
        if profile.get("active")
        else 0
    )
    return dict(
        talisman_protection=ward,
        formation_growth=growth,
        score=round(
            ward * cfg()["protection_weight"] + growth * cfg()["growth_weight"], 3
        ),
    )


def explore(game, rng):
    scene = current(game)
    if not scene:
        raise ValueError("当前不在独立空间")
    scene["explored"] += 1
    if rng.random() < 0.7:
        definition = rng.choice(scene["materials"])
        existing = next(
            (i for i in game.player.inventory if i.id == definition["id"]), None
        )
        if existing:
            existing.quantity += 1
        else:
            game.player.inventory.append(Item(**copy.deepcopy(definition)))
        return f"在{scene['name']}取得{definition['name']}。"
    technique = Technique(**copy.deepcopy(rng.choice(scene["techniques"])))
    learn_technique(game.player, technique)
    return f"参悟空间内独有的{technique.name}。"


def local_action(game, action, target):
    scene = current(game)
    if not scene:
        raise ValueError("当前不在独立空间")
    if action == "move":
        if target not in {row["id"] for row in scene["locations"]}:
            raise ValueError("目标不属于当前空间")
        scene["location_id"] = target
        return "抵达空间内的新地点。"
    if action == "join":
        sect = next((r for r in scene["sects"] if r["id"] == target), None)
        if not sect or scene["location_id"] != sect["location_id"]:
            raise ValueError("须前往该宗门所在地图")
        scene["joined_sect"] = target
        return f"加入{sect['name']}，本界身份仅在此失落界面生效。"
    if action == "talk":
        npc = next((r for r in scene["npcs"] if r["id"] == target and r["alive"]), None)
        if not npc:
            raise ValueError("此人不在当前空间或已经陨落")
        npc["affinity"] = min(100, (npc.get("affinity") or 0) + 1)
        return f"与{npc['name']}交流修行，亲近 +1。"
    raise ValueError("未知空间内事务")


def public(game):
    p, state = game.player, game.spatial_state
    scene = current(game)
    return dict(
        inside=p.world in SPECIAL_WORLDS,
        scene=copy.deepcopy(scene),
        rifts=[
            copy.deepcopy(r)
            for r in state.get("rifts", [])
            if r["world"] == p.world
            and r["instance_id"] == state.get("current")
            and r["expires_age"] > p.age
        ],
        protection=protection(game),
        can_open=(p.realm_index, p.layer) >= (5, 7),
        visited=[
            dict(id=r["id"], name=r["name"])
            for r in state.get("instances", {}).values()
            if r["kind"] == "lost"
        ],
        weights={
            "protection": cfg()["protection_weight"],
            "growth": cfg()["growth_weight"],
        },
    )
