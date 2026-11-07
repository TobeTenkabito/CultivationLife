"""Real loaded scenery choices, one-time inheritance and rejected obsolete purchases."""
import copy

import pytest

from test_building_system import local, choose
from cultivation_life.soul_rules import SECRETS
from cultivation_life.soul_secret_content import STORIES
from cultivation_life.system import buildings


def arrive(engine, game, key, rank=4):
    # Prepare only an isolated fixture's starting address; gameplay never teleports.
    game.player.location_id = STORIES[key]['location']
    game.player.realm_index = rank
    game.player.layer = 1
    game.player.lifespan = 10000
    engine.store.save(game)
    engine.get_game(game.id)
    return engine.store.load(game.id)


def enter(engine, game, key):
    row = next(r for r in buildings.local_rows(game) if r.get('content_id') == STORIES[key]['building'])
    engine.building_action(game.id, 'enter', building_id=row['id'])
    choose(engine, game.id, 'secret:main')
    return choose(engine, game.id, 'secret:read')


@pytest.mark.parametrize('key', SECRETS)
def test_real_story_grants_once_without_payment_time_or_randomness(local, key):
    engine, game = local
    game = arrive(engine, game, key)
    before = copy.deepcopy(game.player.to_dict())
    age, rng = game.player.age, game.rng_state
    view = enter(engine, game, key)
    stale = view['pending_event']['id']
    assert engine.get_game(game.id)['pending_event']['id'] == stale
    assert key not in engine.store.load(game.id).player.nascent_state.get('known', [])
    choose(engine, game.id, 'secret:learn')
    after = engine.store.load(game.id)
    assert after.player.nascent_state['known'].count(key) == 1
    assert (after.player.age, after.rng_state) == (age, rng)
    baseline_state = before.pop('nascent_state')
    after_dict = after.player.to_dict()
    after_dict.pop('nascent_state')
    assert after_dict == before
    assert after.player.nascent_state['revision'] == baseline_state.get('revision', 0) + 1
    unchanged = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError):
        engine.choose(game.id, 'secret:learn', event_id=stale)
    assert engine.store._path(game.id).read_bytes() == unchanged
    choose(engine, game.id, 'secret:main')
    view = choose(engine, game.id, 'secret:read')
    assert not next(c for c in view['pending_event']['choices'] if c['id'] == 'secret:learn')['enabled']
    with pytest.raises(ValueError):
        choose(engine, game.id, 'secret:learn')
    choose(engine, game.id, 'leave')
    assert not engine.get_game(game.id)['buildings']['inside']
    assert engine.store.load(game.id).player.nascent_state['known'].count(key) == 1


@pytest.mark.parametrize('key', SECRETS)
def test_old_purchase_rejected_and_hint_points_to_real_building(local, key):
    engine, game = local
    game = arrive(engine, game, key)
    view = engine.get_game(game.id)
    secret = next(s for s in view['soul']['secrets'] if s['id'] == key)
    assert STORIES[key]['name'] in secret['acquisition_hint'] and 'price' not in secret
    before = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError, match='探索剧情'):
        engine.soul_action(game.id, 'study', dict(id=key, revision=view['soul']['revision']))
    assert engine.store._path(game.id).read_bytes() == before


@pytest.mark.parametrize('key', ['path_ghost', 'second_nascent'])
def test_under_rank_can_return_later_without_losing_inheritance(local, key):
    engine, game = local
    game = arrive(engine, game, key, SECRETS[key][1] - 1)
    view = enter(engine, game, key)
    assert not view['pending_event']['choices'][0]['enabled']
    before = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError):
        choose(engine, game.id, 'secret:learn')
    assert engine.store._path(game.id).read_bytes() == before
    choose(engine, game.id, 'leave')
    game = arrive(engine, engine.store.load(game.id), key)
    enter(engine, game, key)
    choose(engine, game.id, 'secret:learn')
    assert key in engine.store.load(game.id).player.nascent_state['known']


def test_no_forged_skip_and_invalid_address_keeps_followup(local):
    engine, game = local
    game = arrive(engine, game, 'path_dao')
    row = next(r for r in buildings.local_rows(game) if r.get('content_id') == 'lake_mist')
    view = engine.building_action(game.id, 'enter', building_id=row['id'])
    before = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError):
        engine.choose(game.id, 'secret:learn', event_id=view['pending_event']['id'])
    assert engine.store._path(game.id).read_bytes() == before
    choose(engine, game.id, 'secret:main')
    view = choose(engine, game.id, 'secret:read')
    saved = engine.store.load(game.id)
    saved.pending_event['_followup_event'] = copy.deepcopy(engine.events_by_id['EVT_SECT_FIRST_WARNING_001'])
    saved.player.location_id = 'wudi_plain'
    engine.store.save(saved)
    with pytest.raises(ValueError):
        engine.choose(game.id, 'secret:learn', event_id=view['pending_event']['id'])
    current = engine.get_game(game.id)
    assert current['pending_event']['id'] == 'EVT_SECT_FIRST_WARNING_001'
    assert not current['buildings']['inside']
    assert 'path_dao' not in engine.store.load(game.id).player.nascent_state.get('known', [])


def test_acquired_secret_survives_real_cross_world_roundtrip(local):
    engine, game = local
    game = arrive(engine, game, 'path_ghost')
    enter(engine, game, 'path_ghost')
    choose(engine, game.id, 'secret:learn')
    choose(engine, game.id, 'leave')
    game = engine.store.load(game.id)
    known = copy.deepcopy(game.player.nascent_state)
    origin = game.player.location_id
    engine._apply_world_transition(game, engine._plan_world_transition(
        game, 'demon', 'rift', route_id='rift:human:demon', reason='隔离测试秘法随人跨界'))
    engine.store.save(game)
    assert next(s for s in engine.get_game(game.id)['soul']['secrets'] if s['id'] == 'path_ghost')['known']
    with pytest.raises(ValueError):
        engine.building_action(game.id, 'enter', building_id='scenery:human:returning_soul_lamp')
    game = engine.store.load(game.id)
    engine._apply_world_transition(game, engine._plan_world_transition(
        game, 'human', 'rift', route_id='rift:demon:human', arrival_location=origin, reason='隔离测试秘法原址重访'))
    engine.store.save(game)
    assert game.player.nascent_state == known
    view = enter(engine, game, 'path_ghost')
    assert not view['pending_event']['choices'][0]['enabled']


def test_soul_crisis_blocks_story_claim_without_consuming_it(local):
    engine, game = local
    game = arrive(engine, game, 'path_ghost')
    enter(engine, game, 'path_ghost')
    game = engine.store.load(game.id)
    game.player.nascent_state['crisis'] = 'possession'
    engine.store.save(game)
    shown = engine.get_game(game.id)
    assert not shown['pending_event']['choices'][0]['enabled']
    before = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError, match='危机'):
        choose(engine, game.id, 'secret:learn')
    assert engine.store._path(game.id).read_bytes() == before
    game = engine.store.load(game.id)
    game.player.nascent_state.pop('crisis')
    engine.store.save(game)
    choose(engine, game.id, 'secret:learn')
    assert 'path_ghost' in engine.store.load(game.id).player.nascent_state['known']
