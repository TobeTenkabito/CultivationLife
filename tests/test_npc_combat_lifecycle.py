"""Persistent NPC resources: lazy time, world boundaries and real owner adapters."""
import copy
import random
from pathlib import Path

import pytest

from cultivation_life.content_registry import WORLD_SYSTEMS
from cultivation_life.engine import GameEngine
from cultivation_life.engine.combat_capabilities import bind_capabilities, persistent_owners
from cultivation_life.models import SectNpc, SectState
from cultivation_life.system.combat.npc_battle import resolve_npc_engagement
from cultivation_life.system.combat.npc_lifecycle import (
    initialize_native, move_world, prepare, settle, validate_lifecycle,
)
from cultivation_life.system.combat_system import BattleUnit
from cultivation_life.system.world_transition_system import EntourageManifest


@pytest.fixture
def config():
    return copy.deepcopy(WORLD_SYSTEMS["transcendent_combat"])


def immortal(config, *, current=200, world="celestial", key="immortal"):
    npc = SectNpc(key, "仙修", "", 9, 1, 10000, None, world=world)
    npc.transcendence = copy.deepcopy(config["npc_lifecycle"]["native_state"])
    npc.transcendence["current"] = current
    return npc


@pytest.fixture
def engine_game(tmp_path):
    engine = GameEngine(Path(__file__).resolve().parents[1], tmp_path)
    shown = engine.create_game("资源测试", "none", "dao", seed=1440)
    return engine, engine.store.load(shown["id"])


def test_native_creation_is_explicit_and_never_grants_doctrine(config):
    npc = SectNpc("new", "新仙", "", 9, 1, 1000, None, world="celestial")
    # Legacy migration and battle entry do not infer mastery from realm.
    assert prepare(npc, 100, config).state is None
    initialize_native(npc, config, now=100)
    assert npc.transcendence["conversion"] == 1
    assert npc.transcendence["voisinage_ids"] == []
    assert npc.transcendence["attainments"] == {}
    npc.transcendence["current"] = 37
    initialize_native(npc, config, now=200)
    assert npc.transcendence["current"] == 37
    assert config["npc_lifecycle"]["native_state"]["current"] == 1000


@pytest.mark.parametrize("world,realm,explicit", [("human", 9, None), ("celestial", 8, None),
                                                   ("celestial", 9, {})])
def test_unconverted_and_mortal_npcs_are_not_upgraded(config, world, realm, explicit):
    npc = SectNpc("plain", "未转化", "", realm, 1, 100, None, world=world, transcendence=explicit)
    initialize_native(npc, config, now=100)
    assert npc.transcendence is explicit


def test_lazy_recovery_matches_annual_steps_without_replaying_them(config):
    batch = immortal(config)
    settle(batch, 100, config)
    steps = copy.deepcopy(batch)
    settle(batch, 175, config)
    for now in range(101, 176):
        settle(steps, now, config)
    assert batch.transcendence == steps.transcendence
    assert batch.transcendence["current"] == 950
    settle(batch, 10**9, config)
    assert batch.transcendence["current"] == 1000


def test_migration_and_repeated_access_do_not_refill(config):
    npc = immortal(config, current=17)
    settle(npc, 100000, config)
    settle(npc, 100000, config)
    restored = SectNpc.from_dict(npc.to_dict())
    settle(restored, 100000, config)
    assert restored.transcendence["current"] == 17
    assert restored.transcendence == npc.transcendence


def test_crossing_settles_each_environment_and_preserves_mastery(config):
    npc = immortal(config)
    npc.transcendence.update(attainments={"future_doctrine": 4}, voisinage_ids=["future_voisinage"])
    settle(npc, 100, config)
    move_world(npc, "human", 130, config)
    settle(npc, 230, config)
    assert npc.transcendence["current"] == 500
    bound = prepare(npc, 230, config)
    assert bound.state["current"] == 20
    bound.commit(5)
    assert npc.transcendence["current"] == 485
    move_world(npc, "celestial", 230, config)
    settle(npc, 240, config)
    assert npc.transcendence["current"] == 585
    assert npc.transcendence["capacity"] == 1000
    assert npc.transcendence["attainments"] == {"future_doctrine": 4}
    assert npc.transcendence["voisinage_ids"] == ["future_voisinage"]


def test_unrecorded_world_change_cannot_create_recovery(config):
    npc = immortal(config, world="human")
    settle(npc, 100, config)
    npc.world = "celestial"  # Unknown legacy move time: start an anchor, not a windfall.
    settle(npc, 200, config)
    assert npc.transcendence["current"] == 200
    settle(npc, 205, config)
    assert npc.transcendence["current"] == 250


def test_saved_rate_and_conversion_bound_control_accrual(config):
    npc = immortal(config, current=0)
    settle(npc, 100, config)
    config["npc_lifecycle"]["environments"]["celestial"]["recovery_per_year"] = .02
    settle(npc, 110, config)
    assert npc.transcendence["current"] == 100  # Old rate for elapsed time.
    settle(npc, 120, config)
    assert npc.transcendence["current"] == 300
    npc.transcendence["conversion"] = .5
    settle(npc, 1000, config)
    assert npc.transcendence["current"] == 500
    npc.alive = False
    npc.transcendence["current"] = 0
    settle(npc, 2000, config)
    assert npc.transcendence["current"] == 0


def test_clock_rewind_rejected_without_changing_ledger(config):
    npc = immortal(config)
    settle(npc, 100, config)
    before = copy.deepcopy(npc.transcendence)
    with pytest.raises(ValueError, match="backwards"):
        settle(npc, 99, config)
    assert npc.transcendence == before


@pytest.mark.parametrize("field,value", [("available_fraction", 2), ("available_fraction", -1),
                                          ("recovery_per_year", float("nan"))])
def test_bad_environment_configuration_rejected(config, field, value):
    config["npc_lifecycle"]["environments"]["celestial"][field] = value
    with pytest.raises(ValueError):
        validate_lifecycle(config)


def test_npc_background_combat_uses_clock_and_keeps_inaccessible_reserve(config):
    npc = immortal(config, current=100, world="human")
    victim = SectNpc("victim", "凡修", "", 8, 1, 100, None)
    result = resolve_npc_engagement([(npc, 1000)], [(victim, 1000)], config, random.Random(4),
                                    max_rounds=1, now=100)
    assert result is not None
    assert npc.transcendence["current"] == 90
    assert victim.wounds >= 0
    # No recovery in the lower world, even after one hundred years.
    resolve_npc_engagement([(npc, 1000)], [(victim, 1000)], config, random.Random(4),
                           max_rounds=1, now=200)
    assert npc.transcendence["current"] == 80


def test_restored_resource_enables_npc_voisinage_in_background_combat(config):
    config["voisinages"] = [dict(id="test", name="仙域", attainment="test", required_level=4,
                              strength=100, opening_cost=120, upkeep_cost=40,
                              effect="suppress", effect_cost=20)]
    npc = immortal(config, current=0)
    npc.transcendence.update(voisinage_ids=["test"], attainments={"test": 4})
    settle(npc, 100, config)
    victim = SectNpc("victim", "敌人", "", 8, 1, 100, None)
    result = resolve_npc_engagement([(npc, 1)], [(victim, 1e12)], config, random.Random(1), now=120)
    assert result.outcome == "victory"
    assert result.suppressed == (victim.id,)
    assert npc.transcendence["current"] == 20


def test_faction_relocation_settles_resource_before_changing_world(engine_game, config):
    engine, game = engine_game
    npc = immortal(config)
    settle(npc, game.player.age, config)
    game.sects["resource_test"] = SectState("resource_test", "迁徙宗门", "celestial", [npc])
    game.player.age += 10
    record = {"id": "resource_test", "kind": "sect"}
    engine._intrigue_apply_resolution(game, record, "relocate", "human", random.Random(1))
    settle(npc, game.player.age + 100, config)
    assert npc.world == "human"
    assert npc.transcendence["current"] == 300


def test_owner_binding_debits_family_record_not_stale_duplicate(engine_game, config):
    _, game = engine_game
    npc = immortal(config, current=100, world="human")
    stale = copy.deepcopy(npc)
    game.family = SectState("family", "家族", "human", [npc])
    game.notable_npcs[npc.id] = stale
    bound = bind_capabilities(game, [BattleUnit("player", "主角", "player", 1000, 8)],
                              dict(npc_id=npc.id, target_name=npc.name, target_power=1000,
                                   target_realm_index=9), config)
    assert bound.owners[npc.id] is npc
    bound.battle.units[npc.id].current = 7
    bound.commit(bound.battle.updates())
    assert npc.transcendence["current"] == 87
    assert stale.transcendence["current"] == 100


def test_cache_promotion_and_reload_keep_resource_history(engine_game, config):
    engine, game = engine_game
    npc = immortal(config)
    settle(npc, game.player.age, config)
    game.encounter_npc_cache.append({"id": npc.id, "npc": npc.to_dict(), "last_seen_age": game.player.age})
    game.player.age += 10
    promoted = engine._promote_cached_npc(game, npc.id, "结识")
    assert promoted.transcendence == npc.transcendence
    settle(promoted, game.player.age, config)
    assert promoted.transcendence["current"] == 300
    engine.store.save(game)
    loaded = engine.store.load(game.id)
    settle(loaded.notable_npcs[npc.id], game.player.age, config)
    assert loaded.notable_npcs[npc.id].transcendence["current"] == 300
    assert persistent_owners(loaded, {npc.id})[npc.id] is loaded.notable_npcs[npc.id]


def test_encounter_cache_retains_explicit_unconverted_state(engine_game):
    engine, game = engine_game
    game.player.world = "celestial"
    target = dict(combat_type="cultivator", target_name="过客", members=[
        dict(realm_index=9, layer=1, power=1000, transcendence={"conversion": 0})])
    engine._cache_encounter_target(game, target, random.Random(10))
    key = target["members"][0]["npc_id"]
    owner = persistent_owners(game, {key})[key]
    state = owner.get("transcendence") if isinstance(owner, dict) else owner.transcendence
    assert state["conversion"] == 0
    assert state.get("voisinage_ids", []) == []


def test_new_upper_world_recruits_receive_basic_resources(engine_game):
    engine, game = engine_game
    sect = SectState("test_upper", "仙宗", "celestial", [])
    npc = engine._recruit_sect_npc(sect, game.player.age, random.Random(1))
    assert npc.realm_index >= 9
    assert npc.transcendence["current"] == 1000
    assert npc.transcendence["attainments"] == {}


def test_entourage_move_uses_resource_port(engine_game, config):
    _, game = engine_game
    npc = immortal(config)
    settle(npc, game.player.age, config)
    game.notable_npcs[npc.id] = npc
    game.player.age += 10
    manifest = EntourageManifest(False, frozenset({npc.id}), (npc.name,), (), ((npc.id, True, "同行"),))
    manifest.commit(game, "human", move_npc=lambda actor, world, now: move_world(actor, world, now, config))
    settle(npc, game.player.age + 100, config)
    assert npc.world == "human"
    assert npc.transcendence["current"] == 300


def test_converted_player_uses_existing_mp_without_acquiring_voisinage(engine_game, config):
    _, game = engine_game
    game.player.realm_index = 9
    game.player.immortal_power_converted = True
    bound = bind_capabilities(game, [BattleUnit("player", "主角", "player", 1000, 9)],
                              dict(target_name="敌人", target_power=1000, target_realm_index=9), config)
    caps = bound.battle.units["player"].unit.capabilities
    assert caps.resource_link == "legacy_mp"
    assert caps.current == game.player.mp
    assert caps.force_tier == 2 and not caps.voisinages
    assert game.player.transcendence is None
    game.player.immortal_power_converted = False
    bound = bind_capabilities(game, [BattleUnit("player", "主角", "player", 1000, 9)],
                              dict(target_name="敌人", target_power=1000, target_realm_index=9), config)
    assert bound.battle.units["player"].unit.capabilities.force_tier == 1
