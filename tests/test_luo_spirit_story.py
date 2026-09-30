"""The lamp interrupts a real field; recommendation never scales the enemy."""
import copy
import random
from dataclasses import replace
from types import SimpleNamespace

import pytest

from cultivation_life.content_registry import ContentRegistry, ContentError, STORY_COMBAT_SCENARIOS, WORLD_SYSTEMS
from cultivation_life.engine.combat_capabilities import bind_capabilities
from cultivation_life.engine.engine_event_runtime import _resolve_story_combat_check, _story_unit_full_power
from cultivation_life.system.combat.contracts import VoisinageSeal
from scripts.calibrate_luo_spirit_battle import fixture, replay
from test_domain_combat import engine_game


def test_opening_control_lamp_intervention_and_third_round_cutoff():
    report = replay(fixture(105_000_000), 0)
    assert report.outcome == 'victory'
    first, second, third = report.rounds[:3]
    assert first['initiative'] == second['initiative'] == 'voisinage'
    assert first['player_hp_ratio'] == 1
    assert second['player_hp_ratio'] < first['player_hp_ratio']
    assert second['player_morale'] < first['player_morale']
    for row in (first, second):
        assert row['voisinage']['relations']['player']['relation'] == 'dominated'
        assert any(f['name'] == '太虚灵域' for f in row['voisinage']['fields'])
    assert any('锁仙灯' in event for event in second['events'])
    assert third['initiative'] != 'voisinage'
    for row in report.rounds[2:]:
        assert not row['voisinage']['fields']
        assert row['voisinage']['relations']['player']['relation'] == 'uncovered'
        assert row['voisinage']['pressure']['player'] > 0
        assert row['voisinage']['resources']['enemy-0'] > 0  # sealed, not exhausted
    assert sum('自本轮起不再结算' in event for row in report.rounds for event in row['events']) == 1


def test_removing_lamp_protection_reinstates_normal_two_round_terminal():
    data = fixture(1_000_000_000)
    data[1]['player_interventions'] = []
    report = replay(data, 0)
    assert report.outcome == 'defeat'
    assert len(report.rounds) == 2
    assert report.voisinage_lethal


def test_cutoff_releases_only_owner_control_and_does_not_mutate_saved_abilities():
    game, target, units = fixture(105_000_000)
    binding = bind_capabilities(game, units, target, WORLD_SYSTEMS['transcendent_combat'])
    battle = binding.battle
    for n in range(1, 4):
        battle.begin_round(n, player_condition=1, enemy_condition=1, player_mp=1, enemy_mp=1)
    assert not battle.fields
    assert battle.units['player'].pressure > 0
    assert not battle.units['player'].escape_locked
    assert all(battle.units[key].fighting for key in ('player', 'story-ally-0', 'story-ally-1'))
    assert not binding.owners['enemy-0']['transcendence'].get('sealed')
    # The same actor can open again in a later encounter. The lamp does not
    # persist its borrowed response into player equipment or save state.
    clean_target = copy.deepcopy(target)
    clean_target['voisinage_seals'] = []
    clean_target['player_interventions'] = []
    later = bind_capabilities(game, units, clean_target, WORLD_SYSTEMS['transcendent_combat']).battle
    later.begin_round(1, player_condition=1, enemy_condition=1, player_mp=1, enemy_mp=1)
    assert later.fields
    assert not later.units['player'].unit.capabilities.interventions


def test_recommendation_is_independent_from_enemy_power():
    game = fixture(105_000_000)[0]
    captured = []
    deps = SimpleNamespace(_story_unit_full_power=_story_unit_full_power,
                           _combat=lambda game, target, lethal, rng: (captured.append(target) or 'victory', ''))
    for recommendation in (55_000_000, 105_000_000, 999_000_000):
        _resolve_story_combat_check(deps, {'checks': [{'stat': 'combat_power', 'value': recommendation}]},
                                   game, {'id': 'EVT_MA_LIANG_005'}, random.Random(0))
    assert all(target['target_power'] == 55_000_000 for target in captured)
    assert captured[0]['members'] == captured[1]['members'] == captured[2]['members']


@pytest.mark.parametrize('power,expected', [(55_000_000, 'stalemate'), (105_000_000, 'victory')])
def test_real_story_runtime_uses_phases(engine_game, power, expected):
    engine, game = engine_game
    game.player = fixture(power)[0].player
    event = engine.events_by_id['EVT_MA_LIANG_005']
    effect = next(c for c in event['choices'] if c['id'] == 'attack_bottle')['effects'][0]
    result, _ = engine._resolve_story_combat_check(effect, game,
        {'id': event['id'], '_choice_id': 'attack_bottle'}, random.Random(0))
    assert result == ('check_success' if expected == 'victory' else 'check_failed')
    assert len(game.last_combat_report['rounds']) >= 3
    assert not game.last_combat_report['rounds'][2]['voisinage']['fields']


@pytest.mark.parametrize('patch', [
    {'voisinage_seals': [{'owner': 'missing', 'first_round': 3, 'message': 'seal'}]},
    {'voisinage_seals': [{'owner': 'enemy-0', 'first_round': 0, 'message': 'seal'}]},
    {'target_power': float('nan')},
    {'player_interventions': [{'kind': 'unknown', 'effects': ['execute']}]},
])
def test_invalid_story_mechanics_fail_content_loading(patch):
    row = copy.deepcopy(STORY_COMBAT_SCENARIOS['EVT_MA_LIANG_005'])
    row.update(event_id='EVT_MA_LIANG_005', **patch)
    with pytest.raises(ContentError):
        ContentRegistry._build_story_combat_scenarios({'scenarios': [row]})


def test_seal_contract_rejects_fractional_round():
    with pytest.raises(ValueError):
        VoisinageSeal('enemy-0', 2.5, 'seal')


def test_sealing_luo_leaves_another_casters_voisinage_active():
    game, target, units = fixture(105_000_000)
    battle = bind_capabilities(game, units, target, WORLD_SYSTEMS['transcendent_combat']).battle
    enemy = battle.units['enemy-0'].unit.capabilities
    state = battle.units['player']
    state.unit = replace(state.unit, capabilities=replace(enemy, stance='guard'))
    state.current = 60
    for n in range(1, 4):
        battle.begin_round(n, player_condition=1, enemy_condition=1, player_mp=1, enemy_mp=1)
    assert {field.owner for field in battle.fields} == {'player'}


def test_borrowed_lamp_coexists_with_eight_existing_responses():
    game, target, units = fixture(105_000_000)
    game.player.transcendence = {'interventions': [
        {'kind': 'resist', 'effects': ['suppress'], 'strength': .1} for _ in range(8)]}
    battle = bind_capabilities(game, units, target, WORLD_SYSTEMS['transcendent_combat']).battle
    assert len(battle.units['player'].unit.capabilities.interventions) == 9
