"""Spatial choices, real inventory use and deterministic, private expedition maps."""

import copy
import random
import pytest
from test_seeded_dungeons import local, discover, act
from test_dungeon_rank_ecology import loaded
from cultivation_life.content_registry import ITEM_CATALOG
from cultivation_life.rules import add_item, has_item, max_hp, max_mp
from cultivation_life.system.dungeons import trails, perception
from cultivation_life.system.dungeons.rewards import fixed_cache


def prepare_loadout(
    engine,
    game,
    name="青木炼阳阵",
    activate=False,
    types=("human_greenwood_stake", "human_red_sun_sand", "human_xuanyin_stone"),
):
    from cultivation_life.system.formation_system import (
        formation_material_definitions,
        make_formation_material_instance,
    )

    saved = engine.store.load(game.id)
    materials = [
        make_formation_material_instance(
            formation_material_definitions()[key], source="试阵", origin_world="human"
        )
        for key in types
    ]
    saved.player.formation_materials.extend(materials)
    engine.store.save(saved)
    system = engine.save_formation(
        game.id, dict(name=name, slots=[r["id"] for r in materials], activate=activate)
    )["formation_system"]
    return system["loadouts"][-1]["id"], {r["id"] for r in materials}


def enter(local):
    e, g = local
    g.player.realm_index = 1
    g.player.layer = 1
    g.player.divine_sense_rank = 4
    add_item(g.player, "spirit_stone", 10000)
    e.store.save(g)
    assert discover(e, g)["dungeons"]["session"] is None
    view = act(e, g, "enter")["dungeons"]["session"]
    saved, site = loaded(e, g)
    for r in site["roles"].values():
        r["offer_step"] = 99
    e.store.save(saved)
    return e, g, view


def test_fog_movement_and_old_blueprint(local):
    e, g, low = enter(local)
    saved, site = loaded(e, g)
    assert not any(c.get("omen") for c in low["map"]["cells"])
    chart = low["map"]
    seen = {(c["x"], c["y"]) for c in chart["cells"]}
    assert chart["routes"] and all(tuple(p) in seen for route in chart["routes"] for p in route)
    assert {c["direction"] for c in chart["cells"] if c.get("direction")} == set(trails.exits(site["space"], 0))
    saved.player.divine_sense_rank = 300
    e.store.save(saved)
    high = e.get_game(g.id)["dungeons"]["session"]["map"]
    assert len(high["cells"]) == len(site["nodes"]) and all(c.get("omen") for c in high["cells"])
    assert len(high["routes"]) == sum(len(trails.exits(site["space"], i)) for i in range(len(site["nodes"]))) // 2
    assert not any(k in str(high) for k in ("assassinate", "power_factor", "resolve"))
    d, dest = next(iter(trails.exits(site["space"], 0).items()))
    act(e, g, "move", choice=d)
    saved, site = loaded(e, g)
    assert site["step"] == dest and saved.player.age == g.player.age
    with pytest.raises(ValueError, match="过期"):
        e.dungeon_action(g.id, "move", dict(dungeon_id=site["id"], revision=low["revision"], choice=d))
    original = copy.deepcopy(site["nodes"])
    del site["space"]
    e.store.save(saved)
    assert e.get_game(g.id)["dungeons"]["session"]["map"]
    assert "space" not in loaded(e, g)[1]
    d = next(
        row["name"] for row in e.get_game(g.id)["dungeons"]["session"]["map"]["directions"] if row["open"]
    )
    act(e, g, "move", choice=d)
    assert loaded(e, g)[1]["nodes"] == original


def test_lead_pursuer_into_owned_formation(local):
    e, g = local
    loadout, materials = prepare_loadout(e, g)
    portable, _ = prepare_loadout(e, g, "锁空阵", types=("human_void_lock_nail",) * 3)
    e, g, _ = enter((e, e.store.load(g.id)))
    saved, site = loaded(e, g)
    space = site["space"]
    space["snares"].clear()
    for r in site["roles"].values():
        r["offer_step"] = 99
    e.store.save(saved)
    e.activate_formation(g.id, portable)
    mp = saved.player.mp
    with pytest.raises(ValueError):
        act(e, g, "ward", loadout_id="另一人的阵图")
    act(e, g, "ward", loadout_id=loadout)
    saved, site = loaded(e, g)
    assert saved.player.mp == mp
    assert saved.player.active_formation_id == portable
    assert not materials.intersection(r["id"] for r in saved.player.formation_materials)
    assert {r["id"] for r in saved.player.formation_ground_arrays[0]["bindings"] if r} == materials
    with pytest.raises(ValueError):
        act(e, g, "ward", loadout_id=loadout)
    d, dest = next(iter(trails.exits(site["space"], 0).items()))
    act(e, g, "move", choice=d)
    saved, site = loaded(e, g)
    hunter = site["nodes"][dest]["actor"]
    saved.player.realm_index = 4
    saved.player.hp = max_hp(saved.player)
    saved.player.mp = max_mp(saved.player)
    site["space"]["positions"][hunter] = dest
    site["pending"] = dict(kind="ambush", actor=hunter)
    e.store.save(saved)
    v = act(e, g, "choose", choice="flee")["dungeons"]["session"]
    assert v["map"]["chasing"] and not v["can_exit"]
    with pytest.raises(ValueError):
        act(e, g, "exit")
    saved, site = loaded(e, g)
    back = next(d for d, i in trails.exits(site["space"], dest).items() if i == 0)
    v = act(e, g, "move", choice=back)["dungeons"]["session"]
    saved, site = loaded(e, g)
    assert site["pending"] == dict(kind="ambush", actor=hunter, intercepted=True, snared=True)
    assert v["choices"][0]["label"] == "启阵迎敌"
    with pytest.raises(ValueError):
        act(e, g, "choose", choice="flee")
    act(e, g, "choose", choice="fight")
    saved = e.store.load(g.id)
    report = saved.last_combat_report
    assert report["objective"] == "kill" and report["formation_profile"]["name"] == "青木炼阳阵"
    assert report["rounds"] and report["formation_experience_gain"] > 0
    assert saved.player.active_formation_id == portable and saved.dungeon_state["active"]
    array = saved.player.formation_ground_arrays[0]
    assert array["durability"] < 100 and array["battles"] == 1
    act(e, g, "withdraw_ward")
    assert not e.store.load(g.id).player.formation_ground_arrays
    assert {r["id"] for r in e.store.load(g.id).player.formation_materials}.issuperset(materials)


def test_node_array_locks_materials_and_recovers_on_exit(local):
    from cultivation_life.system.dungeons.formations import local_field

    e, g = local
    key, materials = prepare_loadout(e, g, activate=True)
    e, g, _ = enter((e, e.store.load(g.id)))
    saved, site = loaded(e, g)
    act(e, g, "ward", loadout_id=key)
    saved, site = loaded(e, g)
    assert local_field(saved)["loadout_id"] == key and not saved.player.formation_active_bindings
    direction = next(iter(trails.exits(site["space"], 0)))
    act(e, g, "move", choice=direction)
    saved, site = loaded(e, g)
    assert not local_field(saved)
    with pytest.raises(ValueError):
        act(e, g, "withdraw_ward")
    with pytest.raises(ValueError, match="缺少"):
        act(e, g, "ward", loadout_id=key)
    assert len(e.store.load(g.id).player.formation_ground_arrays) == 1
    act(e, g, "exit")
    saved = e.store.load(g.id)
    assert not saved.player.formation_ground_arrays
    assert sorted(r["id"] for r in saved.player.formation_materials if r["id"] in materials) == sorted(
        materials
    )


def test_snare_and_quality_thresholds(local):
    e, g, _ = enter(local)
    saved, site = loaded(e, g)
    space = site["space"]
    d, dest = next(iter(trails.exits(space, 0).items()))
    space["snares"] = {str(dest): site["nodes"][dest]["actor"]}
    saved.player.divine_sense_rank = 45
    normal = perception.sense(saved, {**site, "quality": "ordinary"})
    assert normal > perception.sense(saved, {**site, "quality": "legendary"})
    saved.player.divine_sense_rank = 0
    hp = saved.player.hp
    e.store.save(saved)
    act(e, g, "move", choice=d)
    saved, site = loaded(e, g)
    assert saved.player.hp < hp and dest in site["space"]["spent"]
    return_way = next(d for d, p in trails.exits(site["space"], dest).items() if p == 0)
    act(e, g, "move", choice=return_way)
    saved, site = loaded(e, g)
    saved.player.divine_sense_rank = 180
    site["space"]["spent"].clear()
    hp = saved.player.hp
    e.store.save(saved)
    shown = e.get_game(g.id)["dungeons"]["session"]["map"]
    assert any("暗阵" in c["marks"] for c in shown["cells"])
    act(e, g, "move", choice=d)
    saved, site = loaded(e, g)
    assert saved.player.hp == hp and dest in site["space"]["spent"]
    assert any("挑断阵脚" in row["text"] for row in site["logs"])


@pytest.mark.parametrize(
    "key,path,world,rank",
    [
        ("cavern_guard_6", "dao", "spirit", 6),
        ("cavern_blood_8", "demonic", "true_demon", 8),
        ("cavern_trace_9", "dao", "celestial", 9),
    ],
)
def test_catalog_elixirs_full_inventory_route(local, key, path, world, rank):
    e, g = local
    node = dict(kind="cache")
    original = dict(kind="artifact", id="trial", realm=rank)
    assert any(
        fixed_cache(random.Random(s), original, node, world, "ruins", path).get("items", [{}])[0].get("id")
        == key
        for s in range(80)
    )
    g.player.world = world
    g.player.location_id = e.maps.default_location(world)
    g.player.realm_index = rank
    g.player.immortal_power_converted = True
    add_item(g.player, key, 2)
    g.player.path = "ghost"
    e.store.save(g)
    with pytest.raises(ValueError):
        e.use_item(g.id, key)
    assert has_item(e.store.load(g.id).player, key, 2)
    g.player.path = path
    e.store.save(g)
    e.use_item(g.id, key)
    p = e.store.load(g.id).player
    assert has_item(p, key) and not has_item(p, key, 2)
    if "trace" in key:
        assert p.immortal_traces == g.player.immortal_traces + 12
    else:
        assert p.next_thunder_damage_reduction == pytest.approx(0.08 + 0.03 * (rank - 6))
        with pytest.raises(ValueError):
            e.use_item(g.id, key)
        guarded = e.store.load(g.id)
        guarded.player.hp = max_hp(guarded.player)
        guarded.player.mp = max_mp(guarded.player)
        guarded.active_trial = dict(
            kind="periodic_thunder",
            source_realm=rank,
            target_realm=rank,
            target_layer=1,
            major=False,
            old_label="渡劫",
            step_index=0,
            power=0.001,
            lethal=True,
            event_ids=[f"EVT_PERIODIC_THUNDER_00{i}" for i in (1, 2, 3)],
        )
        plain = copy.deepcopy(guarded)
        plain.player.next_thunder_damage_reduction = 0
        for i in (1, 2, 3):
            e._resolve_trial_step(plain, f"thunder_{i}", random.Random(11))
            e._resolve_trial_step(guarded, f"thunder_{i}", random.Random(11))
        assert guarded.player.hp > plain.player.hp
        assert guarded.player.tribulation_count == plain.player.tribulation_count == p.tribulation_count + 1
        assert guarded.player.next_thunder_damage_reduction == 0


@pytest.mark.parametrize("mistaken", [True, False])
def test_sense_reads_local_evidence_without_materializing_people(local, mistaken):
    e, g, _ = enter(local)
    saved, site = loaded(e, g)
    site["quality"] = "epic"
    a, b = list(site["roles"])[:2]
    site["expedition"]["facts"] = [
        dict(
            id="cache-witness",
            actors=[a, b],
            scope="person",
            direction="东",
            occurred=1,
            reported=2,
            verified=4,
            result="一方带伤离开",
            mistaken=mistaken,
            winner=a,
            treasure=dict(id="cache-witness:background", name="铜印"),
        )
    ]
    floor = site["space"]
    floor.update(turn=3, echoes={"cache-witness": [1, 2]})
    site["expedition"]["evidence"] = {"cache-witness": 2}
    distant = site["roles"][b]
    distant.update(known=True, state="observed")
    floor["positions"][b] = 1
    saved.player.divine_sense_rank = 208
    e.store.save(saved)
    before = e.store.load(g.id).dungeon_state
    session = e.get_game(g.id)["dungeons"]["session"]
    assert any(("认错" if mistaken else "吻合") in row for row in session["map"]["readings"])
    assert any("余波" in c["marks"] for c in session["map"]["cells"])
    assert not next(p["can_slay"] for p in session["people"] if p["id"] == b)
    assert before == e.store.load(g.id).dungeon_state
    saved.player.divine_sense_rank = 4
    e.store.save(saved)
    assert not any(
        "夺宝之人" in s or "吻合" in s for s in e.get_game(g.id)["dungeons"]["session"]["map"]["readings"]
    )


def test_determined_higher_realm_closes_distance(local):
    e, g, _ = enter(local)
    saved, site = loaded(e, g)
    space = site["space"]
    space["snares"].clear()
    hunter = site["nodes"][0]["actor"]
    site["roles"][hunter].update(realm=2, true_realm=2, resolve=100)
    site["pending"] = dict(kind="ambush", actor=hunter)
    e.store.save(saved)
    act(e, g, "choose", choice="flee")
    direction, first = next(
        (d, p)
        for d, p in trails.exits(space, 0).items()
        if any(trails.distance(space, 0, i) == 2 for i in trails.exits(space, p).values())
    )
    act(e, g, "move", choice=direction)
    saved, site = loaded(e, g)
    assert site["space"]["positions"][hunter] == 0 and site["space"]["chase"]["round"] == 1
    d, second = next(
        (d, i) for d, i in trails.exits(space, first).items() if trails.distance(space, 0, i) == 2
    )
    act(e, g, "move", choice=d)
    saved, site = loaded(e, g)
    assert site["step"] == site["space"]["positions"][hunter] == second
    assert site["pending"]["intercepted"] and not site["space"]["chase"]


def test_named_cache_receipt_survives_round_trip(local):
    e, g, _ = enter(local)
    saved, site = loaded(e, g)
    node = site["nodes"][0]
    node.update(kind="cache", mechanism="cache")
    site["quality"] = "ordinary"
    site["space"]["snares"].clear()
    reward = next(
        r
        for seed in range(120)
        if (r := fixed_cache(random.Random(seed), node["reward"], node, "human", "grove", "dao"))["kind"]
        == "fixed"
    )
    node["reward"] = reward
    key = reward["items"][0]["id"]

    def amount(player):
        return sum(i.quantity for i in player.inventory if i.id == key)

    before = amount(saved.player)
    e.store.save(saved)
    act(e, g, "choose", choice="seize")
    saved, site = loaded(e, g)
    assert amount(saved.player) == before + 1 and site["claims"].count(reward["id"]) == 1
    d = next(d for d, i in trails.exits(site["space"], site["step"]).items() if i == 0)
    act(e, g, "move", choice=d)
    with pytest.raises(ValueError, match="已经探过"):
        act(e, g, "choose", choice="seize")
    assert amount(e.store.load(g.id).player) == before + 1


def test_fixed_breakthrough_and_equipment_use_catalog(local):
    original = dict(kind="artifact", id="t", realm=1)
    items = [
        fixed_cache(random.Random(s), original, dict(kind="cache"), "human", theme, "dao")
        for s in range(32)
        for theme in ("grove", "fort")
    ]
    assert any(ITEM_CATALOG[r["items"][0]["id"]].breakthrough_bonus for r in items if r["kind"] == "fixed")
    items = [
        fixed_cache(random.Random(s), original, dict(kind="seal"), "human", "fort", "dao") for s in range(32)
    ]
    assert any(ITEM_CATALOG[r["items"][0]["id"]].combat_bonus for r in items if r["kind"] == "fixed")
