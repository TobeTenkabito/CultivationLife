"""Cross-route ownership, immediate encounters, actual training time and intelligence."""
import copy
import random
from dataclasses import replace
from unittest.mock import Mock

import pytest

from test_heavens_m1 import local
from cultivation_life.content_registry import WORLD_SYSTEMS, TECHNIQUE_CATALOG
from cultivation_life.engine.orchestration import advancement
from cultivation_life.engine.actions.world_travel import plan_public_crossing
from cultivation_life.rules import max_hp, max_mp
from cultivation_life.system import spatial
from cultivation_life.system.heavens import intelligence
from cultivation_life.system.world_transition_system import (
    WorldTransitionRequest, WorldTransitionPorts, plan_world_transition, apply_world_transition,
)


@pytest.mark.parametrize('destination', [w for w in WORLD_SYSTEMS['world_profiles'] if w != 'human'])
def test_every_rift_route_preserves_independent_fame(local, destination):
    engine, game, _ = local
    p = game.player
    p.world, p.realm_index, p.layer, p.fame = 'human', 5, 1, 3115
    p.hostility = {'world:human': 900}
    ports = WorldTransitionPorts(Mock(), Mock(), Mock())
    scene = spatial.create_instance(game, random.Random(8), 'lost' if destination == 'lost' else 'secluded') if destination in {'rift', 'lost'} else None
    for target, expected in [(destination, 0), ('human', 3115), (destination, 17)]:
        plan = plan_world_transition(game, WorldTransitionRequest(
            target, 'rift', f'rift:{p.world}:{target}', instance_id=scene['id'] if scene and target == destination else None), WORLD_SYSTEMS, engine.maps)
        apply_world_transition(game, plan, ports)
        assert p.fame == expected
        assert p.hostility == {'world:human': 900}
        if target == destination:
            p.fame = 17


@pytest.mark.parametrize('action', ['spar', 'capture', 'slay', 'befriend_neighbors'])
def test_immediate_encounters_are_once_persisted_and_do_not_advance_clocks(local, action):
    engine, game, _ = local
    game.player.fame = 100
    engine.store.save(game)
    combat = Mock(return_value='一次实际遭遇')
    year = Mock(side_effect=AssertionError('Immediate action advanced the world'))
    deps = replace(engine._dependencies.advancement, _load=engine.store.load,
                   _personal_combat_step=combat, present=lambda g:g,
                   year=replace(engine._dependencies.advancement.year, _advance_world_year=year))
    result = advancement.advance(deps, game.id, action, 10)
    assert result.player.age == game.player.age
    assert result.diplomacy_unit == game.diplomacy_unit
    assert result.player.opportunity == game.player.opportunity
    assert combat.call_count == (action != 'befriend_neighbors')
    with pytest.raises(ValueError, match='本次行动已结束'):
        advancement.advance(deps, game.id, action)
    saved = engine.store.load(game.id)
    saved.player.age += 1
    engine.store.save(saved)
    advancement.advance(deps, game.id, action)


def test_demonic_early_first_layer_crossing_and_monster_dream_route(local):
    engine, game, _ = local
    p = game.player
    p.world, p.location_id, p.path, p.realm_index, p.layer = 'human', engine.maps.default_location('human'), 'demonic', 5, 1
    p.fame = 900
    engine.store.save(game)
    assert engine._public_demonic_system(p)['true_demon_ascension']['available']
    engine.begin_spirit_crossing(game.id)
    crossed = engine.store.load(game.id)
    assert crossed.player.world == 'demon' and crossed.player.fame == 0
    assert crossed.player.fame_by_world['human'] == 900
    p.world, p.path = 'monster_realm', 'monster'
    plan = plan_public_crossing(game, 'phantom_underworld', engine.maps)
    assert plan.direction.value == 'lateral' and plan.target_rank == (5, 1)
    p.world = 'phantom_underworld'
    assert plan_public_crossing(game, 'monster_realm', engine.maps).direction.value == 'lateral'
    p.path = 'dao'
    with pytest.raises(ValueError, match='妖修'):
        plan_public_crossing(game, 'monster_realm', engine.maps)


def test_rift_endpoints_cover_all_worlds_and_are_hidden_stable(local):
    engine, game, _ = local
    game.player.world = 'human'
    game.player.location_id = engine.maps.default_location('human')
    rng = random.Random(211)
    rows = [spatial.new_rift(game, rng, engine.maps, controlled=True) for _ in range(400)]
    expected = set(WORLD_SYSTEMS['world_profiles']) - {'human', 'rift'}
    assert {row['destination'] for row in rows} == expected
    before = copy.deepcopy(game.to_dict())
    visible = spatial.public(game)
    assert all('destination' not in row for row in visible['rifts'])
    assert game.to_dict() == before


@pytest.mark.parametrize('stars', range(1, 6))
def test_five_merchant_levels_disclose_only_promised_detail(local, stars):
    _, game, _ = local
    game.player.world = 'human'
    first, second = list(game.sects.values())[:2]
    game.wars = [dict(id='w', world='celestial', status='active', attacker_id=first.id,
                     defender_id=second.id, battles=4, morale={'attacker': 77},
                     logs=[dict(text='秘地决战，守军撤退。')])]
    intelligence.acquire_merchant_reports(game, 'celestial', stars)
    row = game.merchant_state['heavens_reports'][-1]
    assert row['level'] == stars
    assert ('仙界' in row['text']) == (stars == 2)
    assert ('秘地' in row['text']) == (stars >= 4)
    assert ('士气 77' in row['text']) == (stars == 5)
    assert ('war_id' in row) == (stars >= 4)
    saved = copy.deepcopy(row)
    game.wars[0]['logs'].append(dict(text='未发生于购报时的后续'))
    assert game.merchant_state['heavens_reports'][-1] == saved


def test_body_probabilities_increased_at_every_layer(local):
    engine, game, _ = local
    old = [.68, .22, .15, .10, .06]
    for layer in range(100):
        game.player.body_training = layer
        assert engine._body_breakthrough_chance(game.player)['base'] > old[layer // 20]


def test_body_stops_at_full_and_sense_gain_is_annual(local):
    engine, game, _ = local
    p = game.player
    p.body_technique = next(t for t in TECHNIQUE_CATALOG.values() if t.category == 'body')
    p.divine_sense_technique = next(t for t in TECHNIQUE_CATALOG.values() if t.category == 'divine_sense')
    p.body_progress = engine._body_progress_required(p) - 1
    p.hp, p.mp = max_hp(p), max_mp(p)
    engine.store.save(game)
    deps = engine._dependencies.advancement
    deps = replace(deps, _load=engine.store.load, present=lambda g:g,
                   year=replace(deps.year, _advance_world_year=lambda *args, **kwargs: True),
                   _ensure_market=Mock(), _finish_yaochi_action=Mock(),
                   _finish_doctrine_action=Mock(), _finish_sage_action=Mock())
    from unittest.mock import patch
    with patch.object(advancement, 'settle_elapsed_time'), patch.object(advancement, '_finish_action_events'):
        full = advancement.advance(deps, game.id, 'body_train', 10)
        assert full.player.age == p.age + 1
        assert full.player.body_progress == engine._body_progress_required(p)
        before = full.player.divine_sense_experience
        annual = engine._sense_training_step(full.player)
        trained = advancement.advance(deps, game.id, 'sense_train', 1)
        elapsed = trained.player.age - full.player.age
        assert elapsed == WORLD_SYSTEMS['time_units'][str(p.realm_index)]
        assert trained.player.divine_sense_experience - before == pytest.approx(annual * elapsed)


def test_cross_world_architecture_gate():
    from tools.check_world_transition_contract import inventory
    report = inventory()
    assert not report['errors']
    assert len(report['routes']) >= 41
    import json
    from pathlib import Path
    contract = json.loads((Path(__file__).resolve().parents[1] / 'docs/world-transition-state-contract.json').read_text(encoding='utf-8'))
    for model, fields in report['state_fields'].items():
        assert set(contract[model]) == set(fields), '新增或删除字段必须重新审阅跨界状态归属'
        assert set(contract[model].values()) <= contract['categories'].keys()
    assert intelligence.WORLD_TIERS == {
        world: profile['tier'] for world, profile in WORLD_SYSTEMS['world_profiles'].items()
        if profile['kind'] == 'world' and profile['tier'] > 0}


def test_race_hostility_and_conversion_clock_do_not_leak_between_worlds(local):
    engine, game, _ = local
    p = game.player
    p.realm_index, p.layer = 5, 1
    p.immortal_power_converted = False
    p.immortal_conversion_stage = 2
    p.immortal_conversion_last_age = p.age - 30
    p.hostility = {'race:human': 120, 'world:celestial': 900}
    ports = WorldTransitionPorts(Mock(), Mock(), Mock())
    original_age = p.age
    for target in ('spirit', 'celestial'):
        plan = engine._plan_world_transition(game, target, 'rift')
        apply_world_transition(game, plan, ports)
        if target == 'spirit':
            assert 'race:human' not in p.hostility
            p.age += 500
        else:
            assert p.hostility['race:human'] == 120
            assert p.immortal_conversion_last_age == original_age - 30 + 500
            assert p.mp <= max_mp(p) * .4


def test_distinct_lost_instances_have_distinct_reputation_and_return_cleanly(local):
    engine, game, _ = local
    from cultivation_life.engine.actions.exploration import enter_scene, move_world
    game.player.realm_index, game.player.layer = 5, 1
    game.player.fame = 40
    rng = random.Random(17)
    scenes = [spatial.create_instance(game, rng, 'lost') for _ in range(2)]
    deps = engine._exploration_dependencies()
    for scene, expected in [(scenes[0], 0), (scenes[1], 0), (scenes[0], 15)]:
        enter_scene(deps, game, scene, rng)
        assert spatial.current(game)['id'] == scene['id']
        assert game.player.fame == expected
        game.player.fame = 15
    move_world(deps, game, 'celestial', rng)
    assert spatial.current(game) is None
    assert game.player.fame == 40


def test_stale_arrival_plan_rejects_without_refunding_or_mutating(local):
    engine, game, _ = local
    plan = engine._plan_world_transition(game, 'asura', 'rift')
    game.player.location_id = 'jade_capital'
    before = copy.deepcopy(game.to_dict())
    ports = WorldTransitionPorts(Mock(), Mock(), Mock())
    with pytest.raises(ValueError, match='失效'):
        apply_world_transition(game, plan, ports)
    assert game.to_dict() == before
    ports.cancel_auction.assert_not_called()


def test_faction_relocation_updates_address_but_not_player_or_absent_people(local):
    engine, game, _ = local
    faction = next(s for s in game.sects.values() if s.world == 'human' and len(s.npcs) >= 2)
    record = {'kind': 'sect', 'id': faction.id}
    dead = faction.npcs[0]
    dead.alive = False
    living = faction.npcs[1]
    player_before = copy.deepcopy(game.player.to_dict())
    for invalid in ('lost', 'rift', 'unknown'):
        before = copy.deepcopy(game.to_dict())
        with pytest.raises(ValueError, match='主界面'):
            engine._intrigue_apply_resolution(game, record, 'relocate', invalid, random.Random(1))
        assert game.to_dict() == before
    engine._intrigue_apply_resolution(game, record, 'relocate', 'spirit', random.Random(1))
    assert faction.world == living.world == 'spirit'
    assert faction.location_id == living.location_id
    engine.maps.location('spirit', faction.location_id)
    assert dead.world == 'human'
    assert game.player.to_dict() == player_before
