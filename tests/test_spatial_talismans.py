from cultivation_life.spatial_people import people
import copy
import random
from pathlib import Path

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.models import SectNpc, GameState
from cultivation_life.rules import add_item, max_mp, opportunity_required
from cultivation_life.runtime import decode_rng, encode_rng
from cultivation_life.system import spatial, talismans, world_boundary
from cultivation_life.engine.actions.exploration import enter_scene
from cultivation_life.debug.runtime import Runtime

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def ready(tmp_path):
    e = GameEngine(ROOT, tmp_path / "normal")
    data = e.create_game("空间试炼", "supreme_metal", "dao", 1658, preset_id="core")
    g = e._load(data["id"])
    g.pending_event = g.active_trial = None
    g.player.lifespan = 100000
    e.store.save(g)
    return e, g


def occupy(e, g, kind="secluded"):
    rng = decode_rng(g.seed, g.rng_state)
    scene = spatial.create_instance(g, rng, kind)
    if kind == "lost":
        scene["power_ceiling"] = 8  # These tests exercise the full-capacity variant.
    enter_scene(e._exploration_dependencies(), g, scene, rng)
    g.rng_state = encode_rng(rng)
    e.store.save(g)
    return scene


def test_lazy_persisted_independent_instances(ready):
    e, g = ready
    assert not g.spatial_state.get("instances")
    first = occupy(e, g, "lost")
    assert len(people(g, first)) == 9 and len(first["sects"]) == 3
    assert all(n.realm_index <= 8 for n in people(g, first))
    assert e.get_game(g.id)["spatial"]["scene"]["id"] == first["id"]
    g = e._load(g.id)
    before = copy.deepcopy(g.spatial_state["instances"][first["id"]])
    second = occupy(e, g, "lost")
    assert first["id"] != second["id"]
    assert g.spatial_state["instances"][first["id"]] == before
    assert GameState.from_dict(g.to_dict()).spatial_state == g.spatial_state


def test_rift_calendar_covers_longest_unit_and_queries_do_not_roll(ready):
    e, g = ready
    r = spatial.new_rift(g, random.Random(2), e.maps, controlled=True)
    from cultivation_life.content_registry import WORLD_SYSTEMS

    assert r["expires_age"] - g.player.age > max(WORLD_SYSTEMS["time_units"].values())
    state = copy.deepcopy(g.spatial_state)
    for _ in range(3):
        spatial.public(g)
    assert g.spatial_state == state
    g.player.age = r["expires_age"]
    spatial.tick(g, random.Random(2), e.maps)
    assert r not in g.spatial_state["rifts"]


def test_rift_failure_kills_and_spends_protection_once(ready):
    e, g = ready
    g.player.realm_index = 4
    g.player.talismans = [
        dict(
            id="a",
            name="护符",
            power=0,
            protection=1,
            assistance=0,
            uses=3,
            enabled=True,
        )
    ]
    r = spatial.new_rift(g, random.Random(2), e.maps, controlled=True)
    r["requirement"] = 100
    e.store.save(g)
    result = e.spatial_action(g.id, "enter", {"target_id": r["id"]})
    assert not result["player"]["alive"]
    assert e.store.load(g.id).player.talismans[0]["uses"] == 2
    assert not e.store.load(g.id).spatial_state["rifts"]


def test_local_rift_ignores_map_lethal_gate(ready, monkeypatch):
    e, g = ready
    g.player.realm_index = 4
    r = spatial.new_rift(g, random.Random(3), e.maps, controlled=True)
    r["kind"] = "rift"
    e.store.save(g)
    monkeypatch.setitem(spatial.cfg(), "outcome_weights", {"local": 1})
    monkeypatch.setattr(
        random.Random,
        "choice",
        lambda self, seq: max(seq, key=lambda row: row.get("min_realm_index", 0)),
    )
    view = e.spatial_action(g.id, "enter", {"target_id": r["id"]})
    assert view["player"]["alive"]
    assert (
        e.maps.location(g.player.world, view["player"]["location_id"]).get(
            "min_realm_index", 0
        )
        > g.player.realm_index
    )


def test_spatial_isolation_blocks_direct_engine_and_allows_personal_training(ready):
    e, g = ready
    occupy(e, g)
    for command in [
        lambda: e.buy_market_offer(g.id, "fake"),
        lambda: e.travel_map(g.id, "rift_interior"),
        lambda: e.upper_institution_action(g.id, "join"),
    ]:
        with pytest.raises(ValueError, match="隔绝"):
            command()
    e.advance(g.id, "rest", 1)
    pending = e.store.load(g.id).pending_event
    if pending:
        e.choose(g.id, 'leave', event_id=pending['id'])
    with pytest.raises(ValueError):
        e.advance(g.id, "commission", 1)
    assert e.store.load(g.id).player.world == "rift"
    g = e.store.load(g.id)
    g.player.realm_index, g.player.layer = 8, 9
    g.player.cultivation_suppression = {"realm_index": 9, "layer": 1}
    e.store.save(g)
    with pytest.raises(ValueError, match="界壁"):
        e.spatial_action(g.id, "descend")


def test_exclusive_rewards_never_join_global_catalogs(ready):
    from cultivation_life.content_registry import (
        ITEM_CATALOG,
        TECHNIQUE_CATALOG,
        restricted_acquisition,
    )

    e, g = ready
    scene = occupy(e, g)
    for row in scene["materials"]:
        assert row["id"] not in ITEM_CATALOG and restricted_acquisition(
            "item", row["id"]
        )
    for row in scene["techniques"]:
        assert row["id"] not in TECHNIQUE_CATALOG and restricted_acquisition(
            "technique", row["id"]
        )
    result = e.spatial_action(g.id, "explore")
    assert result["spatial"]["scene"]["explored"] == 1


@pytest.mark.parametrize(
    "path,destination",
    [
        ("dao", "spirit"),
        ("confucian", "spirit"),
        ("buddhist", "spirit"),
        ("demonic", "true_demon"),
        ("ghost", "hell"),
        ("monster", "monster_realm"),
    ],
)
def test_expulsion_follows_path_not_exit_world(ready, path, destination):
    e, g = ready
    p = g.player
    p.path = path
    p.world = "demon"
    p.location_id = e.maps.default_location("demon")
    p.realm_index = 5
    p.layer = 7
    assert world_boundary.destination(p) == destination
    e.store.save(g)
    assert e.get_game(g.id)["player"]["world"] == destination


def test_late_stage_suppression_allows_stay_concealment_does_not(ready):
    e, g = ready
    p = g.player
    p.realm_index = 5
    p.layer = 9
    p.cultivation_suppression = {"realm_index": 9, "layer": 1}
    assert world_boundary.destination(p) is None
    p.cultivation_suppression = None
    p.cultivation_concealment = {"realm_index": 1, "layer": 1}
    assert world_boundary.destination(p) == "spirit"
    p.world = "rift"
    p.realm_index = 12
    assert world_boundary.destination(p) is None
    p.world = "lost"
    p.realm_index = 9
    p.layer = 1
    assert world_boundary.destination(p) == "celestial"


def test_console_realm_change_immediately_ascends_only_copy(ready, tmp_path):
    e, g = ready
    manager = Runtime(ROOT, tmp_path / "debug", e.store)
    sid = manager.start(g.id)["session_id"]
    before = (
        e.store.path(g.id).read_bytes()
        if hasattr(e.store, "path")
        else (e.store.directory / f"{g.id}.json").read_bytes()
    )
    manager.execute("player set realm_index 5", session_id=sid)
    manager.execute("player set layer 7", session_id=sid)
    assert manager.load(sid)["current"]["game"]["player"]["world"] == "spirit"
    manager.execute("player set realm_index 9", session_id=sid)
    assert manager.load(sid)["current"]["game"]["player"]["world"] == "celestial"
    assert (e.store.directory / f"{g.id}.json").read_bytes() == before


def test_lost_world_thunder_and_dormant_instances(ready):
    e, g = ready
    scene = occupy(e, g, "lost")
    other = spatial.create_instance(g, random.Random(4), "lost")
    before = copy.deepcopy(other)
    p = g.player
    p.realm_index = 6
    p.layer = 1
    p.next_tribulation_age = p.age + 1
    p.tribulation_power = 4000
    e.store.save(g)
    result = e.advance(g.id, "rest", 1)
    restored = e.store.load(g.id)
    assert restored.active_trial["kind"] == "periodic_thunder"
    assert restored.active_trial["world_base_power_cap"] == 32000
    assert restored.spatial_state["instances"][other["id"]] == before
    assert result["spatial"]["scene"]["id"] == scene["id"]


def test_lost_descend_revisit_requires_actual_suppression(ready):
    e, g = ready
    p = g.player
    p.world = "celestial"
    p.location_id = e.maps.default_location("celestial")
    p.realm_index = 9
    p.layer = 1
    p.immortal_power_converted = True
    e.store.save(g)
    with pytest.raises(ValueError, match="压制"):
        e.spatial_action(g.id, "descend")
    p.realm_index = 8
    p.layer = 9
    p.cultivation_suppression = {"realm_index": 9, "layer": 1, "opportunity": 0}
    e.store.save(g)
    first = e.spatial_action(g.id, "descend")["spatial"]["scene"]
    g = e.store.load(g.id)
    g.player.world = "celestial"
    g.player.location_id = e.maps.default_location("celestial")
    g.spatial_state["current"] = None
    e.store.save(g)
    second = e.spatial_action(g.id, "descend", {"target_id": first["id"]})["spatial"][
        "scene"
    ]
    assert second["visits"] == 2 and second["npcs"] == first["npcs"]


def test_talisman_duplicate_material_cost_validation_and_npc_roots(ready, monkeypatch):
    monkeypatch.setattr(talismans, "success_chance", lambda *_: 1.)
    e, g = ready
    p = g.player
    add_item(p, "spirit_stone", 10000)
    add_item(p, "talisman_human_1_paper", 1)
    talismans.act(g, "learn", {"method_id": "talisman_human_1_protection"})
    payload = dict(
        method_id="talisman_human_1_protection",
        material1="talisman_human_1_paper",
        material2="talisman_human_1_paper",
        element="metal",
    )
    before = copy.deepcopy(p.to_dict())
    with pytest.raises(ValueError, match="符材"):
        talismans.craft(g, payload)
    assert p.to_dict() == before
    add_item(p, "talisman_human_1_paper", 3)
    p.mp = max_mp(p)
    talismans.craft(g, payload)
    assert len(p.talismans) == 1 and not p.talismans[0]["enabled"]
    payload["element"] = "water"
    with pytest.raises(ValueError, match="灵根"):
        talismans.craft(g, payload)
    npc = SectNpc(
        "helper",
        "注灵者",
        "",
        2,
        1,
        20,
        200,
        spirit_root="supreme_water",
        world=p.world,
        affinity=0,
    )
    g.notable_npcs[npc.id] = npc
    payload["npc_id"] = npc.id
    talismans.craft(g, payload)
    assert len(p.talismans) == 2


def test_charges_are_per_dimension_and_empty_dimensions_do_not_spend(ready):
    _, g = ready
    p = g.player
    p.talismans = [
        dict(
            id="x",
            name="三元符",
            power=10,
            protection=20,
            assistance=30,
            uses=2,
            enabled=True,
        ),
        dict(
            id="y",
            name="护身符",
            power=0,
            protection=20,
            assistance=0,
            uses=2,
            enabled=False,
        ),
    ]
    assert talismans.read(p, "protection") == 20 and p.talismans[0]["uses"] == 2
    assert talismans.consume(p, "power") == 10
    assert talismans.consume(p, "protection") == 20
    assert talismans.consume(p, "assistance") == 0
    assert p.talismans[1]["uses"] == 2


def test_malformed_inputs_do_not_commit(ready):
    e, g = ready
    before = (e.store.directory / f"{g.id}.json").read_bytes()
    with pytest.raises(ValueError):
        e.spatial_action(g.id, "descend", {"target_id": []})
    with pytest.raises(ValueError):
        e.talisman_action(g.id, "craft", {"material1": {}})
    assert (e.store.directory / f"{g.id}.json").read_bytes() == before


def test_secluded_cultivation_gains_qi_and_removes_demonic_penalty(ready):
    e, g = ready
    occupy(e, g)
    start = copy.deepcopy(g)
    start.player.path = "demonic"
    e.store.save(start)
    result = e.advance(g.id, "cultivate", 1)
    advanced = e.store.load(g.id)
    assert advanced.player.opportunity > start.player.opportunity
    assert sum(advanced.player.qi_experience.values()) > sum(
        start.player.qi_experience.values()
    )
    demon_gain = advanced.player.opportunity - start.player.opportunity
    start.player.path = "dao"
    e.store.save(start)
    e.advance(g.id, "cultivate", 1)
    assert e.store.load(
        g.id
    ).player.opportunity - start.player.opportunity == pytest.approx(demon_gain)
    assert result["spatial"]["inside"]


def test_secluded_late_breakthrough_and_manual_exit_need_no_smuggling(
    ready, monkeypatch
):
    e, g = ready
    occupy(e, g)
    p = g.player
    p.realm_index, p.layer = 5, 6
    p.opportunity = opportunity_required(p) * 2
    e.store.save(g)
    monkeypatch.setattr(e, "_breakthrough_chance", lambda *args, **kw: {"final": 1.0})
    result = e.breakthrough(g.id)
    assert result["player"]["world"] == "rift" and result["player"]["layer"] == 7
    g = e.store.load(g.id)
    with pytest.raises(ValueError, match='合体'):
        e.spatial_action(g.id, 'open')
    g.player.realm_index, g.player.layer = 8, 7
    g.player.mp = max_mp(g.player)
    e.store.save(g)
    opened = e.spatial_action(g.id, "open")
    rift = opened["spatial"]["rifts"][-1]
    # Endpoints are now bound at creation, not rerolled at entry.
    stored = e.store.load(g.id)
    next(row for row in stored.spatial_state['rifts'] if row['id'] == rift['id'])['destination'] = 'human'
    e.store.save(stored)
    monkeypatch.setitem(spatial.cfg(), "outcome_weights", {"passage": 1})
    original = random.Random.choice
    monkeypatch.setattr(
        random.Random,
        "choice",
        lambda self, seq: "human" if "human" in seq else original(self, seq),
    )
    result = e.spatial_action(g.id, "enter", {"target_id": rift["id"]})
    assert result["player"]["world"] == "spirit"
    assert not result["spatial"]["inside"] and result["spatial"]["scene"] is None


def test_lost_rifts_track_instance_map_and_npc_thunder(ready):
    e, g = ready
    scene = occupy(e, g, "lost")
    scene["location_id"] = scene["locations"][2]["id"]
    rift = spatial.new_rift(g, random.Random(2), e.maps, controlled=True)
    assert rift["location_id"] == scene["location_id"]
    high = people(g, scene)[0].__dict__
    high.update(realm_index=6, lifespan=None)
    high["next_tribulation_age"] = g.player.age
    spatial.tick(g, random.Random(2), e.maps)
    assert high["tribulation_count"] == 1
    assert high["next_tribulation_age"] == g.player.age + 3000


def test_combat_consumes_each_enabled_dimension_once(ready):
    from cultivation_life.system.combat_system import PlayerCombatSystem, BattleUnit

    _, g = ready
    g.player.talismans = [
        dict(
            id="battle",
            name="符",
            power=10,
            protection=20,
            assistance=10,
            uses=6,
            enabled=True,
        )
    ]
    PlayerCombatSystem.resolve(
        g.player,
        [BattleUnit("player", "玩家", "player", 100, 3)],
        dict(target_name="试炼", target_power=100, target_realm_index=3),
        False,
        random.Random(2),
        current_hp_ratio=1,
        current_mp_ratio=1,
    )
    assert g.player.talismans[0]["uses"] == 3


def test_secluded_body_bottleneck_does_not_truncate_rest(ready):
    from cultivation_life.content_registry import WORLD_SYSTEMS

    e, g = ready
    occupy(e, g)
    g.player.awaiting_body_breakthrough = True
    start = g.player.age
    e.store.save(g)
    result = e.advance(g.id, "rest", 1)
    assert (
        result["player"]["age"] - start
        == WORLD_SYSTEMS["time_units"][str(g.player.realm_index)]
    )
    g = e.store.load(g.id)
    g.player.realm_index = 9
    assert e._manual_minor_layers(g.player) == set(range(1, 10)) - {9}
