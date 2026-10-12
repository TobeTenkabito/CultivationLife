"""Real persisted commands for zero-time static trials, not settlement shortcuts."""
import copy
import json
import random
import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.engine.transactions import request_scope
from cultivation_life.models import GameState
from cultivation_life.rules import expected_combat_power, max_hp, max_mp
from cultivation_life.system import trial_sites
from cultivation_life.trial_site_generation import generate, rank_for_floor
from cultivation_life.trial_site_schema import REALM_ROWS, decode_state

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def local(tmp_path):
    engine = GameEngine(ROOT, tmp_path / 'saves')
    game = engine.store.load(engine.create_game('试境验收', 'heavenly', 'dao', 341, preset_id='core')['id'])
    game.player.realm_index, game.player.layer = 3, 1
    game.player.opportunity = 0
    game.player.hp, game.player.mp = max_hp(game.player), max_mp(game.player)
    game.settings['silent_events'] = True
    site = trial_sites.bound_site(game, engine.maps, 'human')
    game.player.location_id = site['location_id']
    engine.store.save(game)
    engine.get_game(game.id)
    return engine, engine.store.load(game.id)


def act(engine, game_id, action, **extra):
    saved = engine.store.load(game_id)
    _, floor = trial_sites.current(saved)
    payload = dict(floor_id=floor['id'], revision=floor['revision']) if floor else {}
    return engine.trial_site_action(game_id, action, {**payload, **extra})


def enter(engine, game, number=1):
    return act(engine, game.id, 'enter', world=game.player.world, floor=number)


def complete_events(engine, game_id):
    response = engine.get_game(game_id)
    for index in range(5):
        assert response['pending_event']
        assert f'事件 {index + 1}/5' in response['pending_event']['title']
        saved = engine.store.load(game_id)
        _, floor = trial_sites.current(saved)
        _, _, outcomes = trial_sites.situation(floor)
        # Interpret the generated truth for test fixtures, click through the
        # public command; prefer an intact reward and no hidden damage.
        keys = sorted(outcomes, key=lambda key: (outcomes[key][2], outcomes[key][3].get('treasure') is False,
                                                outcomes[key][3].get('field') is not False))
        key = keys[0]
        response = engine.choose(game_id, key, event_id=response['pending_event']['id'])
    assert response['pending_event'] is None
    return response


def test_actual_five_choices_fight_claim_does_not_advance_time(local):
    engine, game = local
    original = game.to_dict()
    response = enter(engine, game)
    first = engine.store.load(game.id)
    assert len(first.trial_site_state['sites']['human']['floors']) == 1
    before_inventory = [row.to_dict() for row in first.player.inventory]
    complete_events(engine, game.id)
    ready = engine.store.load(game.id)
    assert [row.to_dict() for row in ready.player.inventory] == before_inventory
    assert ready.player.mp < game.player.mp
    response = act(engine, game.id, 'fight')
    assert response['trial_site']['session']['status'] == 'won'
    assert response['last_combat_report']['result'] == 'victory'
    assert len(response['last_combat_report']['trial_site']['choices']) == 5
    assert response['last_combat_report']['enemy_roster'][0]['kind'] == 'mechanical'
    claim = act(engine, game.id, 'claim')
    saved = engine.store.load(game.id)
    assert claim['trial_site']['cleared'] == 1
    assert not claim['trial_site']['active']
    assert saved.player.age == original['player']['age']
    assert saved.auction_sequence == original['auction_sequence']
    assert saved.diplomacy_unit == original['diplomacy_unit']
    assert saved.world_npcs.keys() == original['world_npcs'].keys()
    assert saved.player.fame == original['player']['fame']
    assert saved.player.karma == original['player']['karma']
    assert saved.player.sha_qi == original['player']['sha_qi']
    enter(engine, saved, 2)
    assert len(engine.store.load(game.id).trial_site_state['sites']['human']['floors']) == 2


def test_catalog_floors_match_confirmed_sequences_and_repeat_strengths(local):
    engine, game = local
    expected = {
        'human': [1, 2, 3, 4, 4, 5, 5],
        'spirit': [1, 2, 3, 4, 5, 6, 6, 7, 7, 7, 8, 8, 8, 8],
        'celestial': [1, 2, 3, 4, 5, 6, 7, 8, 9, 9, 10, 10, 10, 11, 11, 11, 11, 12, 12, 12, 12, 12],
    }
    for world, sequence in expected.items():
        assert list(REALM_ROWS[world]) == sequence
        last = {}
        for number, realm in enumerate(sequence, 1):
            rank, layer = rank_for_floor(world, number)
            ordinal = sequence[:number].count(realm) - 1
            base = expected_combat_power(rank, layer) * (1 + .12 * ordinal)
            if realm in last:
                assert base > last[realm]
            last[realm] = base
            for seed in range(8):
                record = generate(seed, world, number, base, engine._trial_site_reward_pool(world, engine.maps.default_location(world), rank))
                assert len(record['nodes']) == 5
                assert all(row['tier'] <= realm for row in record['rewards'])
                assert record['base_power'] == base
                assert generate(seed, world, number, base, engine._trial_site_reward_pool(world, engine.maps.default_location(world), rank)) == record


@pytest.mark.parametrize('world', list(REALM_ROWS))
def test_actual_world_entry_and_public_projection_hides_truth(local, world):
    engine, game = local
    game.player.world = world  # Isolated fixture, never a gameplay movement.
    game.player.location_id = trial_sites.bound_site(game, engine.maps, world)['location_id']
    game.player.immortal_power_converted = True
    engine.store.save(game)
    engine.get_game(game.id)
    raw = engine.store._path(game.id).read_bytes()
    rng_before = engine.store.load(game.id).rng_state
    first = engine.get_game(game.id)
    assert len(first['trial_site']['floors']) == len(REALM_ROWS[world])
    assert not engine.store.load(game.id).trial_site_state
    assert engine.store._path(game.id).read_bytes() == raw
    shown = enter(engine, engine.store.load(game.id))
    assert shown['trial_site']['active']
    assert 'trial_site_state' not in shown
    event = shown['pending_event']
    assert not {'runtime', 'nodes', 'variant', 'rewards'} & event.keys()
    assert all(not {'effects', 'result_text', 'variant', 'hp_cost'} & row.keys() for row in event['choices'])
    assert shown['trial_site']['session'].get('rewards') is None
    assert engine.store.load(game.id).rng_state == rng_before
    complete_events(engine, game.id)
    assert engine.get_game(game.id)['trial_site']['session']['status'] == 'ready'


def test_load_restores_missing_display_and_preserves_followup(local):
    engine, game = local
    shown = enter(engine, game)
    opened = engine.store.load(game.id)
    blueprint = copy.deepcopy(opened.trial_site_state)
    opened.pending_event = None
    engine.store.save(opened)
    restored = engine.get_game(game.id)
    assert restored['pending_event'] == shown['pending_event']
    assert engine.store.load(game.id).trial_site_state == blueprint
    opened = engine.store.load(game.id)
    reward = engine._prepare_treasure_reward_event(opened, random.Random(19))
    opened.pending_event['_followup_event'] = reward
    engine.store.save(opened)
    response = engine.choose(game.id, 'pause', event_id=opened.pending_event['id'])
    assert response['pending_event']['runtime'] == reward['runtime']
    engine.choose(game.id, 'pill', event_id=reward['id'])
    assert engine.get_game(game.id)['pending_event'] is None
    resume = enter(engine, engine.store.load(game.id))
    assert resume['pending_event']['id'] == shown['pending_event']['id']


def test_stale_choice_fight_and_duplicate_reward_rejected_atomically(local):
    engine, game = local
    shown = enter(engine, game)
    old = shown['pending_event']['id']
    engine.choose(game.id, 'c', event_id=old)
    raw = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError):
        engine.choose(game.id, 'c', event_id=old)
    with pytest.raises(ValueError):
        engine.choose(game.id, 'c')
    assert engine.store._path(game.id).read_bytes() == raw
    # Finish the remaining four events through the real public interface.
    for _ in range(4):
        current = engine.get_game(game.id)['pending_event']
        engine.choose(game.id, 'c', event_id=current['id'])
    ready = engine.get_game(game.id)['trial_site']['session']
    act(engine, game.id, 'fight')
    raw = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError):
        engine.trial_site_action(game.id, 'fight', dict(floor_id=ready['floor_id'], revision=ready['revision']))
    assert engine.store._path(game.id).read_bytes() == raw
    win = engine.get_game(game.id)['trial_site']['session']
    act(engine, game.id, 'claim')
    raw = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError):
        engine.trial_site_action(game.id, 'claim', dict(floor_id=win['floor_id'], revision=win['revision']))
    with pytest.raises(ValueError):
        enter(engine, engine.store.load(game.id), 1)
    assert engine.store._path(game.id).read_bytes() == raw


@pytest.mark.parametrize('blocked', ['remote', 'pending', 'mortal', 'prison', 'captive', 'trial', 'guixu', 'dead', 'unconverted', 'other_world', 'locked'])
def test_entry_checks_reject_without_blueprint_or_cost(local, blocked):
    engine, game = local
    if blocked == 'remote':
        game.player.location_id = next(row['id'] for row in engine.maps.worlds['human']['locations'] if row['id'] != game.player.location_id)
    elif blocked == 'pending':
        game.pending_event = engine._instantiate_event(engine.events_by_id['EVT_SECT_FIRST_WARNING_001'], game, random.Random(1))
    elif blocked == 'mortal':
        game.player.realm_index = 0
    elif blocked == 'prison':
        game.player.imprisonment = {'key': 'world:human', 'remaining_years': 1}
    elif blocked == 'captive':
        game.player.ghost_captor = {'name': '拘魂者'}
    elif blocked == 'trial':
        game.active_trial = {'kind': 'periodic_thunder'}
        game.pending_event = engine._instantiate_event(engine.events_by_id['EVT_SECT_FIRST_WARNING_001'], game, random.Random(1))
    elif blocked == 'guixu':
        game.guixu_state['player_session'] = {'dungeon_id': 'human_sea', 'trapped': False}
    elif blocked == 'dead':
        game.player.alive = False
    elif blocked == 'unconverted':
        game.player.world = 'celestial'
        game.player.location_id = trial_sites.bound_site(game, engine.maps, 'celestial')['location_id']
        game.player.immortal_power_converted = False
    elif blocked == 'other_world':
        from test_spatial_talismans import occupy
        occupy(engine, game)
    engine.store.save(game)
    try:
        engine.get_game(game.id)
    except (KeyError, ValueError):
        pass
    raw = engine.store._path(game.id).read_bytes()
    with pytest.raises((ValueError, KeyError)):
        enter(engine, engine.store.load(game.id), 2 if blocked == 'locked' else 1)
    assert engine.store._path(game.id).read_bytes() == raw


def test_resource_gates_both_processing_options_and_pause(local):
    engine, game = local
    shown = enter(engine, game)
    saved = engine.store.load(game.id)
    saved.player.hp, saved.player.mp = 1., 0.
    engine.store.save(saved)
    response = engine.get_game(game.id)
    assert {row['id'] for row in response['pending_event']['choices'] if row['enabled']} == {'c', 'pause'}
    raw = engine.store._path(game.id).read_bytes()
    for choice in ['a', 'b']:
        with pytest.raises(ValueError):
            engine.choose(game.id, choice, event_id=shown['pending_event']['id'])
        assert engine.store._path(game.id).read_bytes() == raw
    engine.choose(game.id, 'pause', event_id=shown['pending_event']['id'])
    assert not engine.store.load(game.id).trial_site_state['active']


def test_pause_external_time_does_not_call_or_change_trial(local):
    engine, game = local
    enter(engine, game)
    first = engine.get_game(game.id)['pending_event']
    engine.choose(game.id, 'c', event_id=first['id'])
    act(engine, game.id, 'pause')
    state = copy.deepcopy(engine.store.load(game.id).trial_site_state)
    with patch.object(trial_sites, 'command', side_effect=AssertionError('annual trial command')), patch.object(trial_sites, 'generate', side_effect=AssertionError('annual trial generation')):
        engine.advance(game.id, 'rest', 1)
    assert engine.store.load(game.id).trial_site_state == state
    # Event-free silent rest, then resume the unchanged second node.
    current = engine.store.load(game.id)
    current.pending_event = None
    engine.store.save(current)
    resumed = enter(engine, current)
    assert resumed['trial_site']['session']['event_index'] == 1
    assert engine.store.load(game.id).trial_site_state['sites']['human']['floors']['1']['nodes'] == state['sites']['human']['floors']['1']['nodes']


def test_active_scene_blocks_direct_external_operations(local):
    engine, game = local
    enter(engine, game)
    complete_events(engine, game.id)
    raw = engine.store._path(game.id).read_bytes()
    for action in [lambda: engine.advance(game.id, 'rest'), lambda: engine.travel_map(game.id, engine.maps.default_location('human'))]:
        with pytest.raises(ValueError):
            action()
        assert engine.store._path(game.id).read_bytes() == raw


def test_save_failure_does_not_publish_choice_in_same_request(local):
    engine, game = local
    shown = enter(engine, game)
    raw = engine.store._path(game.id).read_bytes()
    with request_scope(engine):
        engine.get_game(game.id)
        with patch.object(engine.store, 'save', side_effect=OSError('disk full')):
            with pytest.raises(OSError):
                engine.choose(game.id, 'a', event_id=shown['pending_event']['id'])
        assert engine.get_game(game.id)['pending_event']['id'] == shown['pending_event']['id']
    assert engine.store._path(game.id).read_bytes() == raw


@pytest.mark.parametrize('corruption', ['version', 'world', 'negative', 'nan', 'nodes', 'effect'])
def test_invalid_save_rejected_and_original_file_retained(local, corruption):
    engine, game = local
    enter(engine, game)
    document = engine.store.load(game.id).to_dict()
    state = document['trial_site_state']
    floor = state['sites']['human']['floors']['1']
    if corruption == 'version':
        state['version'] = 999
    elif corruption == 'world':
        state['sites']['human']['world'] = 'unknown'
    elif corruption == 'negative':
        floor['energy'] = -1
    elif corruption == 'nan':
        floor['base_power'] = float('nan')
    elif corruption == 'nodes':
        floor['nodes'].pop()
    else:
        floor['nodes'][0]['effects'] = [{'type': 'enter_celestial'}]
    file = engine.store._path(game.id)
    file.write_text(json.dumps(document, ensure_ascii=False), encoding='utf8')
    raw = file.read_bytes()
    with pytest.raises(ValueError):
        engine.get_game(game.id)
    assert file.read_bytes() == raw


def test_optional_structure_ten_field_and_unknown_version(local):
    engine, game = local
    document = game.to_dict()
    document.pop('trial_site_state')
    assert GameState.from_dict(document).trial_site_state == {}
    assert decode_state({}) == {}


def test_same_operation_has_opposite_consequence_and_prior_choice_changes_next(local):
    engine, game = local
    pool = engine._trial_site_reward_pool('human', game.player.location_id, 1)
    floors = [generate(seed, 'human', 1, 100, pool) for seed in range(60)]
    incoming = next(f for f in floors if f['nodes'][0]['variant'] == 0)
    outgoing = next(f for f in floors if f['nodes'][0]['variant'] == 1)
    assert trial_sites.situation(incoming)[2]['a'][3]['delta'] < 0
    assert trial_sites.situation(outgoing)[2]['a'][3]['delta'] > 0
    before = copy.deepcopy(incoming)
    before['index'] = 1
    after = copy.deepcopy(before)
    after['supply'] = False
    assert trial_sites.situation(before)[1] != trial_sites.situation(after)[1]
    assert trial_sites.situation(before)[2]['a'][3]['delta'] == -trial_sites.situation(after)[2]['a'][3]['delta']


def test_named_buff_changes_real_six_dimension_stats(local):
    engine, game = local
    pool = engine._trial_site_reward_pool('human', game.player.location_id, 1)
    floor = generate(1, 'human', 1, expected_combat_power(1, 5), pool)
    site = trial_sites.bound_site(game, engine.maps, 'human')
    baseline = copy.deepcopy(game)
    engine._combat(baseline, trial_sites.target_for(site, floor), True, random.Random(11))
    floor['guard'] = False
    modified = copy.deepcopy(game)
    engine._combat(modified, trial_sites.target_for(site, floor), True, random.Random(11))
    assert baseline.last_combat_report['enemy_stats']['guard'] == pytest.approx(modified.last_combat_report['enemy_stats']['guard'] * 1.2, abs=.1)


def test_static_guardian_finite_resources_do_not_recover_with_world_time(local):
    from cultivation_life.system.combat_adapter import bind_capabilities
    from cultivation_life.content_registry import WORLD_SYSTEMS
    engine, game = local
    game.player.world = 'celestial'
    game.player.immortal_power_converted = True
    game.player.location_id = engine.maps.default_location('celestial')
    site = trial_sites.bound_site(game, engine.maps, 'celestial')
    floor = generate(3, 'celestial', 11, expected_combat_power(10, 1), engine._trial_site_reward_pool('celestial', site['location_id'], 10))
    floor['energy'] = 77.
    target = trial_sites.target_for(site, floor)
    binding = bind_capabilities(game, engine._player_combat_units(game, target), target, WORLD_SYSTEMS['transcendent_combat'])
    key = target['members'][0]['id']
    assert binding.resources[key].state['current'] == 77
    game.player.age += 100
    again = bind_capabilities(game, engine._player_combat_units(game, target), target, WORLD_SYSTEMS['transcendent_combat'])
    assert again.resources[key].state['current'] == 77
    assert 'lifecycle' not in target['members'][0]['transcendence']


@pytest.mark.parametrize('world', list(REALM_ROWS))
def test_every_floor_is_playable_through_real_five_node_battle_reward_commands(local, world):
    engine, game = local
    game.player.world = world
    game.player.realm_index, game.player.layer = (12, 9) if trial_sites.WORLD_TIERS[world] == 3 else (8, 9) if trial_sites.WORLD_TIERS[world] == 2 else (3, 1)
    game.player.immortal_power_converted = True
    game.player.quick_start_base_combat_power = expected_combat_power(12, 9) * 50
    if trial_sites.WORLD_TIERS[world] == 3:
        game.player.transcendence = dict(version=1, resource_link='independent', capacity=100000., current=100000.,
            conversion=1., force_tier=2, ward_tier=1, attack_cost=10., ward_cost=0., attainments={}, voisinage_ids=[])
    game.player.location_id = trial_sites.bound_site(game, engine.maps, world)['location_id']
    game.player.hp, game.player.mp = max_hp(game.player), max_mp(game.player)
    engine.store.save(game)
    engine.get_game(game.id)
    age = engine.store.load(game.id).player.age
    for number in range(1, len(REALM_ROWS[world]) + 1):
        # Fixture restores resources between layers so this checks each legal
        # floor independently; the gameplay commands never perform this refill.
        saved = engine.store.load(game.id)
        saved.player.hp, saved.player.mp = max_hp(saved.player), max_mp(saved.player)
        engine.store.save(saved)
        enter(engine, saved, number)
        for index in range(5):
            saved = engine.store.load(game.id)
            _, floor = trial_sites.current(saved)
            choices = trial_sites.situation(floor)[2]
            if index == 4:
                key = next((key for key in ('a', 'b') if choices[key][3].get('field') is False), 'c')
            else:
                key = min(choices, key=lambda key: (choices[key][2], choices[key][3].get('treasure') is False))
            event = engine.get_game(game.id)['pending_event']
            engine.choose(game.id, key, event_id=event['id'])
        result = act(engine, game.id, 'fight')
        assert result['trial_site']['session'] and result['trial_site']['session']['status'] == 'won', (world, number, result['last_combat_report'])
        assert result['last_combat_report']['result'] == 'victory'
        if floor['realm'] >= 9:
            assert result['trial_site']['session']['energy'] < 1200
        result = act(engine, game.id, 'claim')
        assert result['trial_site']['cleared'] == number
        assert engine.store.load(game.id).player.age == age
    assert all(row['status'] == 'claimed' for row in result['trial_site']['floors'])


def test_actual_overwhelming_guardian_death_never_rewards_or_keeps_busy(local):
    engine, game = local
    enter(engine, game)
    complete_events(engine, game.id)
    saved = engine.store.load(game.id)
    _, floor = trial_sites.current(saved)
    floor['base_power'] = expected_combat_power(12, 9) * 50
    saved.player.hp = 1
    engine.store.save(saved)
    before = [row.to_dict() for row in saved.player.inventory]
    result = act(engine, game.id, 'fight')
    assert not result['player']['alive']
    assert result['trial_site']['cleared'] == 0
    assert not result['trial_site']['active']
    assert [row.to_dict() for row in engine.store.load(game.id).player.inventory] == before
    assert result['last_combat_report']['result'] == 'dead'


def test_high_guardian_field_uses_real_budget_and_retains_it_after_pause(local):
    engine, game = local
    game.player.world = 'celestial'
    game.player.realm_index, game.player.layer = 9, 1
    game.player.immortal_power_converted = True
    game.player.location_id = trial_sites.bound_site(game, engine.maps, 'celestial')['location_id']
    engine.store.save(game)
    # Build the prior cleared records as an isolated fixture; the layer under
    # test still uses the real loading, five choices and original combat call.
    game = engine.store.load(game.id)
    site = trial_sites.bound_site(game, engine.maps, 'celestial')
    for number in range(1, 9):
        realm, layer = rank_for_floor('celestial', number)
        floor = generate(game.seed, 'celestial', number, expected_combat_power(realm, layer), engine._trial_site_reward_pool('celestial', site['location_id'], realm))
        floor['index'], floor['status'] = 5, 'claimed'
        floor['history'] = [dict(event_id=f"{floor['id']}_node_{n}", choice_id='c', summary='既有通关记录') for n in range(1, 6)]
        site['floors'][str(number)] = floor
    site['cleared'] = 8
    game.trial_site_state = dict(version=1, sites={'celestial': site}, active=None)
    game.player.hp, game.player.mp = max_hp(game.player), max_mp(game.player)
    game.player.quick_start_base_combat_power = expected_combat_power(9, 1) * 10
    engine.store.save(game)
    enter(engine, game, 9)
    for _ in range(5):
        event = engine.get_game(game.id)['pending_event']
        engine.choose(game.id, 'c', event_id=event['id'])
    ready = engine.store.load(game.id)
    _, floor = trial_sites.current(ready)
    assert floor['field']
    result = act(engine, game.id, 'fight')
    saved = engine.store.load(game.id)
    floor = saved.trial_site_state['sites']['celestial']['floors']['9']
    assert floor['energy'] < 1200
    assert result['last_combat_report']['capability_updates']
    energy = floor['energy']
    if result['trial_site']['active'] and result['trial_site']['session']['can_pause']:
        act(engine, game.id, 'pause')
        saved = engine.store.load(game.id)
        state = copy.deepcopy(saved.trial_site_state)
        saved.player.age += 100
        engine.store.save(saved)
        engine.get_game(game.id)
        assert engine.store.load(game.id).trial_site_state == state
        assert state['sites']['celestial']['floors']['9']['energy'] == energy


@pytest.mark.parametrize('override', [{'npc_id': 'world_npc'}, {'actor_id': 'companion'}, {'base_power': 1}, {'rewards': []}])
def test_non_player_and_hidden_config_parameters_rejected(local, override):
    engine, game = local
    raw = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError):
        engine.trial_site_action(game.id, 'enter', dict(world='human', floor=1, **override))
    assert engine.store._path(game.id).read_bytes() == raw


def test_without_trial_dlc_has_no_trial_actions_and_only_trial_package_is_sufficient(tmp_path):
    base = tmp_path / 'base_only'
    shutil.copytree(ROOT / 'content', base / 'content')
    disabled_script = '''
from pathlib import Path
import os
from cultivation_life.engine import GameEngine
from cultivation_life.system import trial_sites
engine = GameEngine(Path.cwd(), Path(os.environ['CULTIVATION_APP_ROOT']) / 'saves')
shown = engine.create_game('纯本体', 'heavenly', 'dao', 341, preset_id='core')
assert not trial_sites.enabled()
assert shown['trial_site'] == {'enabled':False, 'available':False, 'active':False, 'blocked_session':False}
try:
    engine.trial_site_action(shown['id'],'enter',{'world':'human','floor':1})
except ValueError:
    pass
else:
    raise AssertionError('DLC-free trial entry accepted')
'''
    result = subprocess.run([sys.executable, '-c', disabled_script], cwd=ROOT,
                            env={**os.environ, 'CULTIVATION_APP_ROOT': str(base)}, capture_output=True,
                            text=True, encoding='utf8', timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
    shutil.copytree(ROOT / 'dlc/trial-sites', base / 'dlc/trial-sites')
    script = '''
from pathlib import Path
import os
from cultivation_life.engine import GameEngine
from cultivation_life.content_registry import EXTENSION_REPORT
from cultivation_life.rules import max_hp, max_mp
from cultivation_life.system.trial_sites import bound_site
engine = GameEngine(Path.cwd(), Path(os.environ['CULTIVATION_APP_ROOT']) / 'saves')
for world in ('human', 'spirit', 'celestial'):
    shown = engine.create_game('本体试境', 'heavenly', 'dao', 341, preset_id='core')
    game = engine.store.load(shown['id'])
    game.player.world = world
    game.player.immortal_power_converted = True
    game.player.location_id = bound_site(game, engine.maps, world)['location_id']
    game.player.hp, game.player.mp = max_hp(game.player), max_mp(game.player)
    age = game.player.age
    engine.store.save(game)
    shown = engine.trial_site_action(game.id, 'enter', {'world': world, 'floor': 1})
    for _ in range(5):
        event = shown['pending_event']
        shown = engine.choose(game.id, 'c', event_id=event['id'])
    session = shown['trial_site']['session']
    shown = engine.trial_site_action(game.id, 'fight', {'floor_id': session['floor_id'], 'revision': session['revision']})
    assert shown['trial_site']['session']['status'] == 'won'
    session = shown['trial_site']['session']
    shown = engine.trial_site_action(game.id, 'claim', {'floor_id': session['floor_id'], 'revision': session['revision']})
    assert shown['trial_site']['cleared'] == 1
    assert engine.store.load(game.id).player.age == age
assert [row['id'] for row in EXTENSION_REPORT if row.get('status') == 'loaded'] == ['official.trial-sites']
print('independent trial DLC passed')
'''
    result = subprocess.run([sys.executable, '-c', script], cwd=ROOT,
                            env={**os.environ, 'CULTIVATION_APP_ROOT': str(base)}, capture_output=True,
                            text=True, encoding='utf8', timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('phase', ['node', 'ready', 'won'])
def test_dlc_disable_freezes_blueprint_and_preserves_earned_followup(local, phase, monkeypatch):
    engine, game = local
    enter(engine, game)
    if phase != 'node':
        complete_events(engine, game.id)
    if phase == 'won':
        act(engine, game.id, 'fight')
    saved = engine.store.load(game.id)
    _, floor = trial_sites.current(saved)
    original = copy.deepcopy(floor)
    reward = engine._prepare_treasure_reward_event(saved, random.Random(19))
    if saved.pending_event:
        saved.pending_event['_followup_event'] = reward
    else:
        saved.pending_event = reward
    engine.store.save(saved)
    monkeypatch.setattr(trial_sites, 'enabled', lambda: False)
    response = engine.get_game(game.id)
    assert not response['trial_site']['enabled']
    assert response['pending_event']['runtime'] == reward['runtime']
    frozen = engine.store.load(game.id)
    assert frozen.trial_site_state['active'] is None
    preserved = frozen.trial_site_state['sites']['human']['floors']['1']
    assert {k:v for k,v in preserved.items() if k != 'revision'} == {k:v for k,v in original.items() if k != 'revision'}
    engine.choose(game.id, 'pill', event_id=reward['id'])
    with pytest.raises(ValueError):
        enter(engine, engine.store.load(game.id))
    monkeypatch.setattr(trial_sites, 'enabled', lambda: True)
    response = enter(engine, engine.store.load(game.id))
    assert response['trial_site']['session']['status'] == original['status']


def test_visual_projection_only_reveals_observed_mechanisms(local):
    engine, game = local
    shown = enter(engine, game)
    mechanisms = shown['trial_site']['session']['mechanisms']
    assert len(mechanisms) == 5
    assert all(row['subject'] is None and row['summary'] is None for row in mechanisms[1:])
    assert all('variant' not in row and 'effects' not in row for row in mechanisms)
    event = shown['pending_event']
    shown = engine.choose(game.id, 'c', event_id=event['id'])
    assert shown['trial_site']['session']['mechanisms'][0]['status'] == 'done'
    assert shown['trial_site']['session']['mechanisms'][0]['summary']


@pytest.mark.parametrize('path_id', ['dao', 'demonic', 'monster', 'ghost', 'buddhist', 'confucian'])
def test_first_layer_accepts_actual_player_paths_without_npc_copies(local, path_id):
    engine, game = local
    game.player.path = path_id
    game.player.hp, game.player.mp = max_hp(game.player), max_mp(game.player)
    engine.store.save(game)
    engine.get_game(game.id)
    opened = enter(engine, engine.store.load(game.id))
    assert opened['trial_site']['active']
    complete_events(engine, game.id)
    before = engine.store.load(game.id)
    participants = set(before.world_npcs) | set(before.notable_npcs)
    result = act(engine, game.id, 'fight')
    assert result['trial_site']['session']['status'] == 'won'
    act(engine, game.id, 'claim')
    after = engine.store.load(game.id)
    assert set(after.world_npcs) | set(after.notable_npcs) == participants
    assert after.player.world == before.player.world
    assert after.player.location_id == before.player.location_id


def test_debug_trial_commands_use_original_rules_and_preserve_source(local, tmp_path):
    from cultivation_life.debug.runtime import Runtime
    from cultivation_life.debug.registry import CommandError
    from cultivation_life.content_registry import WORLD_SYSTEMS
    engine, game = local
    original = engine.store._path(game.id).read_bytes()
    manager = Runtime(ROOT, tmp_path / 'debug', engine.store)
    sid = manager.start(game.id)['session_id']
    def run(text):
        return manager.execute(text, session_id=sid)
    run('trial site enter human 1')
    state = manager.load(sid)['current']['game']['trial_site_state']
    floor = state['sites']['human']['floors']['1']
    run(f"trial site pause null null {floor['id']} {floor['revision']}")
    run('trial site enter human 1')
    before_choice = copy.deepcopy(manager.load(sid)['current'])
    with pytest.raises(RuntimeError):
        run('event choose c stale-node')
    assert manager.load(sid)['current'] == before_choice
    for _ in range(5):
        run('event choose c')
    floor = manager.load(sid)['current']['game']['trial_site_state']['sites']['human']['floors']['1']
    run(f"trial site fight null null {floor['id']} {floor['revision']}")
    saved = manager.load(sid)['current']['game']
    assert saved['trial_site_state']['sites']['human']['floors']['1']['status'] == 'won'
    floor = saved['trial_site_state']['sites']['human']['floors']['1']
    run(f"trial site claim null null {floor['id']} {floor['revision']}")
    saved = manager.load(sid)['current']['game']
    assert saved['trial_site_state']['sites']['human']['cleared'] == 1
    assert saved['player']['age'] == game.player.age
    before = copy.deepcopy(manager.load(sid)['current'])
    with patch.dict(WORLD_SYSTEMS['trial_sites'], enabled=False):
        with pytest.raises(CommandError):
            run('trial site enter human 2')
    assert manager.load(sid)['current'] == before
    assert engine.store._path(game.id).read_bytes() == original
