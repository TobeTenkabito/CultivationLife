"""Generated situations through real saves, loads and the ordinary choice command."""
import copy
import json
import random
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from cultivation_life.content_registry import ITEM_CATALOG, TECHNIQUE_CATALOG, WORLD_SYSTEMS
from cultivation_life.engine import GameEngine
from cultivation_life.generated_event_generation import generate, SITUATIONS
from cultivation_life.generated_event_schema import decode_state
from cultivation_life.models import GameState
from cultivation_life.rules import max_hp, max_mp

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def local(tmp_path):
    engine = GameEngine(ROOT, tmp_path / 'saves')
    game = engine.store.load(engine.create_game('异闻验收', 'heavenly', 'dao', 431, preset_id='core')['id'])
    game.player.realm_index, game.player.layer = 1, 1
    game.player.opportunity = 0
    game.player.hp, game.player.mp = max_hp(game.player), max_mp(game.player)
    game.settings['silent_events'] = True
    engine.store.save(game)
    engine.get_game(game.id)  # Reconcile the fixture's changed realm/market first.
    return engine, engine.store.load(game.id)


def open_event(engine, game):
    game.pending_event = engine._dependencies.advancement._prepare_generated_event(game)
    engine.store.save(game)
    return game.generated_event_state['active']


def rewarded_choice(record):
    return next(row for row in record['choices'] if row['reward'])


def test_generator_is_repeatable_varies_mechanisms_and_does_not_mutate_inputs():
    source = dict(world='human', location_id='village', instance_id=None,
                  realm_index=1, layer=1, location_name='山村')
    pool = [dict(kind='item', content_id='spirit_sword', name='灵剑', tier=1)]
    before = copy.deepcopy((source, pool))
    records = [generate(seed, 1, source, pool) for seed in range(120)]
    assert records == [generate(seed, 1, source, list(reversed(pool))) for seed in range(120)]
    assert (source, pool) == before
    assert {row['template_id'] for row in records} == set(SITUATIONS)
    assert {row['variant'] for row in records} == {0, 1}
    for template in SITUATIONS:
        samples = [row for row in records if row['template_id'] == template]
        assert {rewarded_choice(row)['id'] for row in samples} == {'route_a', 'route_b'}
    assert generate(0, 1, source, pool)['id'] != generate(0, 2, source, pool)['id']


def test_public_action_spends_one_real_unit_even_when_ten_requested(local):
    engine, game = local
    age = game.player.age
    response = engine.advance(game.id, 'generated_explore', 10)
    saved = engine.store.load(game.id)
    assert saved.player.age == age + WORLD_SYSTEMS['time_units']['1']
    assert saved.generated_event_state['sequence'] == 1
    assert response['pending_event']['id'] == saved.generated_event_state['active']['id']
    assert response['generated_event']['pending']
    assert saved.pending_event is not None  # Explicit exploration is not silenced.


def test_load_preserves_blueprint_rng_and_only_projects_public_choices(local):
    engine, game = local
    record = copy.deepcopy(open_event(engine, game))
    first = engine.get_game(game.id)
    after = engine.store.load(game.id)
    rng, raw = after.rng_state, engine.store._path(game.id).read_bytes()
    second = engine.get_game(game.id)
    assert first['pending_event'] == second['pending_event']
    assert after.generated_event_state['active'] == record
    assert engine.store.load(game.id).rng_state == rng
    assert engine.store._path(game.id).read_bytes() == raw
    assert 'generated_event_state' not in first
    assert 'runtime' not in first['pending_event']
    for row in first['pending_event']['choices']:
        assert not {'reward', 'signal', 'effects', 'conditions', 'hp_cost', 'mp_cost', 'result_text'} & row.keys()


@pytest.mark.parametrize('path_id', ['dao', 'demonic', 'monster', 'ghost', 'buddhist', 'confucian'])
def test_rewarded_choice_uses_existing_resource_and_reward_entries(local, path_id):
    engine, game = local
    game.player.path = path_id
    record = open_event(engine, game)
    row = rewarded_choice(record)
    reward = row['reward']
    before = engine.store.load(game.id)
    engine.choose(game.id, row['id'], event_id=record['id'])
    saved = engine.store.load(game.id)
    assert saved.player.mp == pytest.approx(before.player.mp - max_mp(before.player) * row['mp_cost'])
    assert saved.player.hp == before.player.hp
    assert saved.generated_event_state['active'] is None
    assert saved.generated_event_state['last_result']['signal'] == row['signal']
    if reward['kind'] == 'item':
        count = lambda p: sum(item.quantity for item in p.inventory if item.id == reward['content_id'])
        assert count(saved.player) == count(before.player) + 1
    else:
        techniques = [saved.player.technique, *saved.player.known_techniques]
        assert any(t and t.id == reward['content_id'] for t in techniques) or any(
            item.technique_copy_id == reward['content_id'] for item in saved.player.inventory)
    assert any('遗藏得以保存' in row.summary for row in saved.history)


def test_wrong_interpretation_causes_saved_damage_without_reward(local):
    engine, game = local
    record = open_event(engine, game)
    row = next(row for row in record['choices'] if row['signal'] == 'damaged')
    before = engine.store.load(game.id)
    engine.choose(game.id, row['id'], event_id=record['id'])
    saved = engine.store.load(game.id)
    assert saved.player.hp == pytest.approx(before.player.hp - max_hp(before.player) * row['hp_cost'])
    assert saved.player.mp == pytest.approx(before.player.mp - max_mp(before.player) * row['mp_cost'])
    assert [item.to_dict() for item in saved.player.inventory] == [item.to_dict() for item in before.player.inventory]
    assert saved.generated_event_state['last_result']['signal'] == 'damaged'


def test_safety_gate_does_not_reveal_hidden_answer_and_rejection_does_not_save(local):
    engine, game = local
    record = open_event(engine, game)
    game.player.hp = max_hp(game.player) * .01
    game.player.mp = 0
    engine.store.save(game)
    response = engine.get_game(game.id)
    assert {row['id'] for row in response['pending_event']['choices'] if row['enabled']} == {'leave'}
    raw = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError):
        engine.choose(game.id, rewarded_choice(record)['id'], event_id=record['id'])
    assert engine.store._path(game.id).read_bytes() == raw
    engine.choose(game.id, 'leave', event_id=record['id'])
    assert engine.store.load(game.id).generated_event_state['last_result']['signal'] == 'left'


def test_new_instance_rejects_old_page_and_duplicate_reward(local):
    engine, game = local
    first = open_event(engine, game)
    row = rewarded_choice(first)
    engine.choose(game.id, row['id'], event_id=first['id'])
    saved = engine.store.load(game.id)
    raw = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError):
        engine.choose(game.id, row['id'], event_id=first['id'])
    assert engine.store._path(game.id).read_bytes() == raw
    saved.pending_event = None
    second = open_event(engine, saved)
    assert second['sequence'] == 2
    raw = engine.store._path(game.id).read_bytes()
    for event_id in (first['id'], None):
        with pytest.raises(ValueError):
            engine.choose(game.id, 'leave', event_id=event_id)
        assert engine.store._path(game.id).read_bytes() == raw


def test_earned_followup_survives_generated_event_load_and_submission(local):
    engine, game = local
    record = open_event(engine, game)
    reward = engine._prepare_treasure_reward_event(game, random.Random(19))
    game.pending_event['_followup_event'] = reward
    engine.store.save(game)
    shown = engine.get_game(game.id)
    assert shown['pending_event']['_followup_event']['runtime'] == reward['runtime']
    result = engine.choose(game.id, 'leave', event_id=record['id'])
    assert result['pending_event']['id'] == reward['id']
    assert result['pending_event']['runtime'] == reward['runtime']
    engine.choose(game.id, 'pill', event_id=reward['id'])
    assert engine.store.load(game.id).pending_event is None


def test_static_event_before_generated_discovery_does_not_erase_it(local):
    engine, game = local
    record = open_event(engine, game)
    generated = game.pending_event
    warning = engine._instantiate_event(engine.events_by_id['EVT_SECT_FIRST_WARNING_001'], game, random.Random(1))
    warning['_followup_event'] = generated
    game.pending_event = warning
    engine.store.save(game)
    shown = engine.get_game(game.id)
    assert shown['pending_event']['id'] == warning['id']
    result = engine.choose(game.id, 'acknowledge', event_id=warning['id'])
    assert result['pending_event']['id'] == record['id']
    engine.choose(game.id, 'leave', event_id=record['id'])
    assert not engine.store.load(game.id).generated_event_state['active']


def test_scene_change_only_allows_rewardless_dismissal(local):
    engine, game = local
    record = open_event(engine, game)
    game.player.location_id = next(row['id'] for row in engine.maps.worlds['human']['locations']
                                   if row['id'] != game.player.location_id)
    engine.store.save(game)
    shown = engine.get_game(game.id)
    assert {row['id'] for row in shown['pending_event']['choices'] if row['enabled']} == {'leave'}
    engine.choose(game.id, 'leave', event_id=record['id'])
    assert engine.store.load(game.id).pending_event is None


@pytest.mark.parametrize('world', [w for w, p in WORLD_SYSTEMS['world_profiles'].items() if p['tier'] > 0])
def test_generated_rewards_are_local_legal_catalog_entries(local, world):
    engine, game = local
    game.player.world = world
    game.player.location_id = engine.maps.default_location(world)
    record = engine._dependencies.advancement._prepare_generated_event(game)
    active = game.generated_event_state['active']
    reward = rewarded_choice(active)['reward']
    assert reward['content_id'] in (TECHNIQUE_CATALOG if reward['kind'] == 'technique' else ITEM_CATALOG)
    assert reward['tier'] <= game.player.realm_index
    assert record['id'] == active['id']


@pytest.mark.parametrize('blocked', ['mortal', 'trial', 'prison', 'captive', 'guixu', 'space', 'pending', 'dead'])
def test_new_action_rejects_existing_busy_and_space_rules(local, blocked):
    engine, game = local
    if blocked == 'mortal':
        game.player.realm_index = 0
    elif blocked == 'trial':
        game.active_trial = {'kind': 'periodic_thunder'}
        game.pending_event = engine._instantiate_event(engine.events_by_id['EVT_SECT_FIRST_WARNING_001'], game, random.Random(1))
    elif blocked == 'prison':
        game.player.imprisonment = {'key': 'world:human', 'remaining_years': 1}
    elif blocked == 'captive':
        game.player.ghost_captor = {'name': '拘魂者'}
    elif blocked == 'guixu':
        game.guixu_state['player_session'] = {'dungeon_id': 'human_sea', 'trapped': False}
    elif blocked == 'space':
        from test_spatial_talismans import occupy
        occupy(engine, game)
    elif blocked == 'pending':
        game.pending_event = engine._instantiate_event(engine.events_by_id['EVT_SECT_FIRST_WARNING_001'], game, random.Random(1))
    elif blocked == 'dead':
        game.player.alive = False
    engine.store.save(game)
    # Preparation may reconcile pre-existing fixture state; use its committed baseline.
    try:
        engine.get_game(game.id)
    except (KeyError, ValueError):
        pass
    raw = engine.store._path(game.id).read_bytes()
    with pytest.raises((ValueError, KeyError)):
        engine.advance(game.id, 'generated_explore')
    assert engine.store._path(game.id).read_bytes() == raw


@pytest.mark.parametrize('corruption', ['version', 'negative_cost', 'infinite', 'foreign_effect'])
def test_invalid_generated_records_are_rejected_without_overwriting_save(local, corruption):
    engine, game = local
    open_event(engine, game)
    document = game.to_dict()
    record = document['generated_event_state']['active']
    if corruption == 'version':
        record['version'] = 99
    elif corruption == 'negative_cost':
        record['choices'][0]['mp_cost'] = -1
    elif corruption == 'infinite':
        record['choices'][0]['opportunity'] = float('inf')
    else:
        record['choices'][0]['effects'] = [{'type': 'enter_spirit_realm'}]
    file = engine.store._path(game.id)
    file.write_text(json.dumps(document, ensure_ascii=False), encoding='utf-8')
    raw = file.read_bytes()
    with pytest.raises(ValueError):
        engine.get_game(game.id)
    assert file.read_bytes() == raw


def test_structure_ten_missing_container_defaults_without_migrating_older_structures(local):
    engine, game = local
    document = game.to_dict()
    document.pop('generated_event_state')
    assert GameState.from_dict(document).generated_event_state == {}
    assert decode_state({}) == {}


def test_missing_display_is_recovered_from_saved_authority_without_reroll(local):
    engine, game = local
    record = copy.deepcopy(open_event(engine, game))
    game.pending_event = None
    engine.store.save(game)
    rng = game.rng_state
    shown = engine.get_game(game.id)
    assert shown['pending_event']['id'] == record['id']
    saved = engine.store.load(game.id)
    assert saved.generated_event_state['active'] == record
    assert saved.rng_state == rng
    engine.choose(game.id, 'leave', event_id=record['id'])


def test_feature_runs_with_only_base_content_and_no_extensions(tmp_path):
    app_root = tmp_path / 'base_only'
    shutil.copytree(ROOT / 'content', app_root / 'content')
    script = '''
from pathlib import Path
from cultivation_life.engine import GameEngine
from cultivation_life.content_registry import EXTENSION_REPORT
engine = GameEngine(Path.cwd(), Path(__import__('os').environ['CULTIVATION_APP_ROOT']) / 'saves')
shown = engine.create_game('本体异闻', 'heavenly', 'dao', 901, preset_id='core')
game = engine.store.load(shown['id'])
game.settings['silent_events'] = True
game.player.opportunity = 0
engine.store.save(game)
shown = engine.advance(game.id, 'generated_explore')
assert engine.store.load(game.id).generated_event_state['active']
assert not any(row.get('status') == 'loaded' for row in EXTENSION_REPORT)
while shown['pending_event']:
    event = shown['pending_event']
    selected = next((c for c in event['choices'] if c['id'] == 'leave'), event['choices'][0])
    shown = engine.choose(game.id, selected['id'], event_id=event['id'])
assert shown['generated_event']['last_result']['signal'] == 'left'
print('base-only generated event passed')
'''
    result = subprocess.run([sys.executable, '-c', script], cwd=ROOT,
                            env={**os.environ, 'CULTIVATION_APP_ROOT': str(app_root)},
                            capture_output=True, text=True, encoding='utf-8', timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
