"""Save-local spatial instances, rift clocks and isolation policy.

Generated definitions are never inserted into shared content registries. Dormant
instances retain their data but have no yearly simulation cost.
"""

import copy
import math
import random

from ..content_registry import WORLD_SYSTEMS, REALMS
from ..models import Item, Technique, SectNpc, HistoryRecord
from ..rules import learn_technique
from . import talismans
from .formation_system import active_formation_profile
from .spatial_population import generation_profile, initial_rank
from ..npc_names import person_name
from ..spatial_people import people, bind as bind_people
from .spatial_capabilities import PERSONAL_COMMANDS, LOCAL_SOCIETY_COMMANDS, panels

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
        "evolve_monster",
        "prepare_custom_lineage",
        "confirm_custom_lineage",
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


def location_qi(location, field="qi_gain_efficiencies"):
    """Complete finite source profiles, including old instance map saves."""
    source = location.get(field) or {}
    return {key: float(value) if isinstance(value, (float, int)) and math.isfinite(value) and value > 0 else 1.
            for key in ("spirit", "demon", "monster", "yin") for value in [source.get(key)]}


def current_qi(game):
    scene = current(game)
    location = next(row for row in scene["locations"] if row["id"] == scene["location_id"])
    return location_qi(location)


def public_map(game):
    scene = current(game)
    locations = copy.deepcopy(scene["locations"])
    here = next(row for row in locations if row["id"] == scene["location_id"])
    for row in locations:
        row.update(qi_gain_efficiencies=location_qi(row), qi_concentrations=location_qi(row, "qi_concentrations"),
                   current=row["id"] == here["id"], travel_status="safe",
                   travel_years=0 if row["id"] == here["id"] else 1,
                   route_names=[here["name"], row["name"]])
    return dict(world=game.player.world, world_name=scene["name"], current=here["id"],
                current_name=here["name"], locations=locations,
                edges=copy.deepcopy(scene.get("edges", [])), teleport={"arrays": []})


def guard(game, command):
    allowed = LOCAL_COMMANDS | PERSONAL_COMMANDS
    allowed |= {'heavens_view', 'heavens_preview', 'heavens_command'}
    if game.player.world == 'lost':
        allowed |= LOCAL_SOCIETY_COMMANDS
    if game.player.world in SPECIAL_WORLDS and command not in allowed:
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
        kind="node" if rng.random() < .35 else "rift",
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
        for person in people(game, scene):
            npc = person.__dict__
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
        if len(local) < 6 and rng.random() < cfg()["spawn_chance"]:
            for _ in range(min(6 - len(local), rng.randint(1, 3))):
                new_rift(game, rng, maps)


def create_instance(game, rng, kind):
    state = ensure(game)
    state["sequence"] += 1
    identity = f"{kind}_{state['sequence']}"
    # A dedicated generator bounds generation cost and makes each instance
    # independent of how often its view is requested.
    generator = random.Random(rng.getrandbits(64))
    power_ceiling = generator.randint(5, 7) if kind == "lost" and generator.random() < .4 else 8
    resource_ceiling = min(power_ceiling, generator.randint(5, 7) if kind == "lost" and generator.random() < .4 else 8)
    population = generation_profile(generator, power_ceiling, resource_ceiling) if kind == "lost" else None
    stem = generator.choice(["苍", "玄", "霜", "赤", "玉", "幽"]) + generator.choice(
        ["岚", "岑", "渊", "陵", "岳", "泽"]
    )
    name = stem + ("秘境" if kind == "secluded" else "界")
    suffixes = generator.sample(["古原", "灵谷", "荒海", "天山", "幽林", "石岭"], 4)
    locations = [
        dict(
            id=f"{identity}_map_{i}",
            name=stem + suffixes[i],
            description=f"{name}内的{suffixes[i]}，气脉自成循环，与外界隔绝。",
            themes=["独立空间", suffixes[i]],
            combat_terrain=generator.choice(["开阔", "险要"]),
            combat_conditions=[],
            qi_gain_efficiencies={source: round(generator.uniform(.6, 1.4), 2)
                                  for source in ("spirit", "demon", "monster", "yin")},
            qi_concentrations={source: round(generator.uniform(.5, 1.5), 2)
                               for source in ("spirit", "demon", "monster", "yin")},
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
                grade=generator.randint(1, resource_ceiling if kind == "lost" else 8),
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
        rank, layer = initial_rank(generator, population, i)
        npc = SectNpc(
            f"{identity}_npc_{i}",
            person_name(generator, [n["name"] for n in npcs]),
            "散修" if i % 3 == 0 else "门人",
            rank,
            layer,
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
            gender=generator.choice(['male', 'female']),
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
        edges=[dict(source=a["id"], target=b["id"], years=1)
               for i, a in enumerate(locations) for b in locations[i + 1:]],
        location_id=locations[0]["id"],
        materials=materials,
        techniques=techniques,
        npcs=npcs,
        sects=sects,
        joined_sect=None,
        next_open_age=game.player.age + cfg()["reopen_interval"],
        visits=0,
        explored=0,
        resource_ceiling=resource_ceiling if kind == "lost" else None,
        power_ceiling=power_ceiling if kind == "lost" else None,
        power_description=f"界面之力最多承载{REALMS[power_ceiling].name}后期九层，超出后将被排斥。" if kind == "lost" else "独立秘境没有界面之力修为上限。",
        population_rules=population,
        resource_description=(f"修炼资源稀薄，本界只能支持修炼至{REALMS[resource_ceiling].name}后期九层；须另觅界面继续修炼。"
                              if kind == "lost" and resource_ceiling < 8 else "修炼资源可支持至大乘后期。" if kind == "lost" else "灵气充沛的独立秘境。"),
    )
    state["instances"][identity] = scene
    bind_people(game, SectNpc)
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
    if scene.get('heavens_target'):
        raise ValueError('此处所得由诸天机关持有，不能重复随机探索领取')
    scene["explored"] += 1
    if rng.random() < .25:
        from ..talisman_content import local_catalog
        available = [r for r in local_catalog(game)[0].values()
                     if r["tier"] <= max(1, game.player.realm_index)]
        definition = rng.choice(available)
        existing = next((i for i in game.player.inventory if i.id == definition["id"]), None)
        if existing:
            existing.quantity += 1
        else:
            game.player.inventory.append(Item(id=definition["id"], name=definition["name"],
                description=definition["description"], quantity=1,
                tags=["spatial_exclusive", "material", "talisman_material"]))
        return f"在{scene['name']}取得{definition['name']}。"
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
        person = next((r for r in people(game, scene) if r.id == target and r.alive), None)
        npc = person.__dict__ if person else None
        if not npc:
            raise ValueError("此人不在当前空间或已经陨落")
        npc["affinity"] = min(100, (npc.get("affinity") or 0) + 1)
        return f"与{npc['name']}交流修行，亲近 +1。"
    raise ValueError("未知空间内事务")


def visible(game):
    return game.player.realm_index >= 4


def cultivation_block_reason(game):
    scene = current(game)
    cap = (scene or {}).get("resource_ceiling")
    if game.player.world == "lost" and cap and cap < 8 and (game.player.realm_index, game.player.layer) >= (cap, 9):
        return f"{scene['name']}修炼资源稀薄，只能支持至{REALMS[cap].name}后期九层，请离开本界后继续修炼。"
    return ""


def rift_requirement(rift, age):
    lifespan = max(1, rift["expires_age"] - rift["created_age"])
    elapsed = min(1., max(0., (age - rift["created_age"]) / lifespan))
    return round(rift["requirement"] * (1 + 3 * elapsed ** 3) + 25 * elapsed ** 3, 2)


def outcome_weights(rift):
    return {"passage": 80, "secluded": 10, "local": 10} if rift.get("kind") == "node" else cfg()["outcome_weights"]


def public(game):
    p, state = game.player, game.spatial_state
    scene = copy.deepcopy(current(game))
    if scene:
        scene["locations"] = public_map(game)["locations"]
        scene['npcs'] = [npc.to_dict() for npc in people(game)]
    return dict(
        inside=p.world in SPECIAL_WORLDS,
        panels=panels(game),
        visible=visible(game),
        scene=copy.deepcopy(scene),
        rifts=[
            dict(copy.deepcopy(r), requirement=rift_requirement(r, p.age),
                 name="空间节点" if r.get("kind") == "node" else "空间裂缝",
                 passage_chance=outcome_weights(r).get("passage", 0) / sum(outcome_weights(r).values()))
            for r in state.get("rifts", [])
            if visible(game) and r["world"] == p.world
            and r["instance_id"] == state.get("current")
            and r["expires_age"] > p.age
        ],
        protection=protection(game) if visible(game) else None,
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
