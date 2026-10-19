"""Buildings use real loaded commands, original assets and zero-year events."""
import copy
from pathlib import Path

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.models import GameState
from cultivation_life.building_schema import decode_state, address, address_key
from cultivation_life.building_rules import describe, display_name, qi_multiplier, may_use
from cultivation_life.rules import add_item, grant_qi_experience, remove_item
from cultivation_life.system import buildings
from cultivation_life.system.buddhist.rules import buddhist_config
from cultivation_life.system.economy.ledger import balance


@pytest.fixture
def local(tmp_path):
    engine = GameEngine(Path(__file__).resolve().parents[1], tmp_path / 'saves')
    game = engine.store.load(engine.create_game('建筑验收', 'heavenly', 'dao', 317, preset_id='core')['id'])
    game.pending_event = None
    add_item(game.player, 'spirit_stone', 100000)
    engine.store.save(game)
    return engine, engine._load(game.id)


def choose(engine, identity, choice):
    shown = engine.get_game(identity)
    return engine.choose(identity, choice, event_id=shown['pending_event']['id'])


def construct(engine, game, level=1, quality='professional'):
    engine.building_action(game.id, 'construct')
    choose(engine, game.id, f'level:{level}')
    choose(engine, game.id, f'plan:{level}:{quality}')
    choose(engine, game.id, 'confirm')
    return engine.store.load(game.id)


def stable_time(game):
    return game.player.age, game.rng_state, copy.deepcopy(game.world_simulation), copy.deepcopy(game.economy_v2.get('transport'))


def test_actual_construction_branch_and_back_do_not_advance_time_or_duplicate_charge(local):
    engine, game = local
    before = stable_time(game)
    funds = balance(game, 'player')
    built = construct(engine, game)
    assert before == stable_time(built)
    assert funds - balance(built, 'player') == 800
    assert len(built.building_state['records']) == 1
    record = next(iter(built.building_state['records'].values()))
    assert record['address'] == address(game)
    assert qi_multiplier(built.player) == 1.04
    old = engine.get_game(game.id)['pending_event']['id']
    choose(engine, game.id, 'qi')
    with pytest.raises(ValueError):
        engine.choose(game.id, 'leave', event_id=old)
    choose(engine, game.id, 'back')
    choose(engine, game.id, 'details')
    choose(engine, game.id, 'back')
    choose(engine, game.id, 'leave')
    exited = engine.store.load(game.id)
    assert not exited.pending_event and 'scene' not in exited.building_state
    assert before == stable_time(exited)
    assert balance(exited, 'player') == balance(built, 'player')
    assert any(row['id']==record['id'] for row in engine.get_game(game.id)['buildings']['rows'])


def test_confirm_replay_missing_event_and_insufficient_funds_are_rejected(local):
    engine, game = local
    engine.building_action(game.id, 'construct')
    choose(engine, game.id, 'level:1')
    plan = choose(engine, game.id, 'plan:1:professional')
    with pytest.raises(ValueError): engine.choose(game.id, 'confirm')
    game = engine.store.load(game.id)
    remove_item(game.player, 'spirit_stone', balance(game, 'player'))
    engine.store.save(game)
    with pytest.raises(ValueError): engine.choose(game.id, 'confirm', event_id=plan['pending_event']['id'])
    shown = engine.get_game(game.id)
    assert not next(c for c in shown['pending_event']['choices'] if c['id']=='confirm')['enabled']
    assert not engine.store.load(game.id).building_state['records']
    game = engine.store.load(game.id);add_item(game.player, 'spirit_stone', 800);engine.store.save(game)
    choose(engine, game.id, 'confirm')
    before = engine.store.load(game.id).to_dict()
    with pytest.raises(ValueError): engine.choose(game.id, 'confirm', event_id=plan['pending_event']['id'])
    assert engine.store.load(game.id).to_dict() == before


def test_upgrade_pays_difference_and_professional_cannot_downgrade(local):
    engine, game = local
    game = construct(engine, game, quality='self')
    identity = next(iter(game.building_state['records']))
    choose(engine, game.id, 'renovate')
    choose(engine, game.id, 'level:2')
    choose(engine, game.id, 'plan:2:professional')
    before = balance(engine.store.load(game.id), 'player')
    choose(engine, game.id, 'confirm')
    game = engine.store.load(game.id)
    assert before - balance(game, 'player') == 3000
    assert set(game.building_state['records']) == {identity}
    assert game.building_state['records'][identity]['invested'] == 3200
    choose(engine, game.id, 'renovate')
    shown = choose(engine, game.id, 'level:3')
    assert not next(c for c in shown['pending_event']['choices'] if c['id']=='plan:3:self')['enabled']


def test_saved_session_restores_and_earned_followup_survives_invalidation(local):
    engine, game = local
    game = construct(engine, game)
    expected = game.pending_event['id']
    game.pending_event = None;engine.store.save(game)
    assert engine.get_game(game.id)['pending_event']['id'] == expected
    game = engine.store.load(game.id)
    following = copy.deepcopy(engine.events_by_id['EVT_SECT_FIRST_WARNING_001'])
    game.pending_event['_followup_event'] = following
    next(iter(game.building_state['records'].values()))['users'] = []
    next(iter(game.building_state['records'].values()))['owner'] = dict(kind='npc',id='another')
    engine.store.save(game)
    shown = engine.get_game(game.id)
    assert shown['pending_event']['id'] == following['id']
    assert not shown['buildings']['inside'] and shown['buildings']['qi_multiplier'] == 1
    assert engine.store.load(game.id).building_state['records']


def test_qi_bonus_uses_original_gain_and_actual_permission_address(local):
    engine, game = local
    game = construct(engine, game, level=3)
    plain = GameState.from_dict(game.to_dict())
    plain.building_state['cultivation'].clear()
    efficiencies = {source:1 for source in game.player.qi_experience}
    actual = grant_qi_experience(game.player, 100, efficiencies)
    baseline = grant_qi_experience(plain.player, 100, efficiencies)
    assert sum(baseline.values()) > 0
    for source in actual: assert actual[source] == pytest.approx(baseline[source]*1.12)
    assert game.player.opportunity == plain.player.opportunity
    row = next(iter(game.building_state['records'].values()))
    row['owner'] = dict(kind='npc',id='other')
    assert qi_multiplier(game.player) == 1
    row['users'] = [dict(kind='player',id=game.id)]
    assert qi_multiplier(game.player) == 1.12
    row['status'] = 'destroyed'
    assert qi_multiplier(game.player) == 1
    row['status'] = 'intact'
    row['address'] = dict(world='spirit',instance_id=None,location_id='remote')
    assert qi_multiplier(game.player) == 1


def test_overview_readonly_and_remote_entry_rejected(local):
    engine, game = local
    game = construct(engine, game)
    choose(engine, game.id, 'leave')
    game = engine.store.load(game.id)
    row = next(iter(game.building_state['records'].values()))
    remote = next(p for p in engine.maps.worlds[game.player.world]['locations'] if p['id'] != game.player.location_id)
    row['address']['location_id'] = remote['id']
    game.building_state['cultivation'].clear();engine.store.save(game)
    shown = engine.get_game(game.id)
    snapshot = copy.deepcopy(game.to_dict())
    buildings.attach_overview(game, shown['map'])
    target = next(p for p in shown['map']['locations'] if p['id'] == remote['id'])
    assert len(target['buildings']) == 1 and not target['buildings'][0]['can_enter']
    assert game.to_dict() == snapshot
    with pytest.raises(ValueError):engine.building_action(game.id,'enter',building_id=row['id'])


def test_entered_building_blocks_real_time_and_remote_commands(local):
    engine, game = local
    game = construct(engine, game)
    before = stable_time(game)
    for command in ('action','travel','buddhist-action','fleet-action'):
        with pytest.raises(ValueError):engine.assert_building_operation_allowed(game.id,command)
    with pytest.raises(ValueError):engine.advance(game.id,'cultivate',1)
    assert stable_time(engine.store.load(game.id)) == before


@pytest.mark.parametrize('subtype', ['military','economic','comprehensive'])
@pytest.mark.parametrize('level', [1,2,3])
def test_city_description_comes_from_real_type_size_and_defenses(subtype,level):
    row = dict(name='无羁城',type='city',subtype=subtype,level=level,status='intact')
    text = describe(row)
    assert ('大都市' in text) == (level==3)
    assert '大阵' not in text and '禁制' not in text
    if subtype=='economic':assert '商' in text and '守卒' not in text
    row['features']=['defensive_array','restrictions']
    assert '大阵' in describe(row) and '禁制' in describe(row)
    row['status']='destroyed'
    assert display_name(row)=='无羁城遗址' and '断垣残壁' in describe(row)


def test_schema_roundtrip_and_invalid_scene_or_scenery(local):
    engine, game = local
    game = construct(engine, game)
    assert GameState.from_dict(game.to_dict()).building_state == game.building_state
    value = copy.deepcopy(game.building_state)
    value['scene']['address']={}
    with pytest.raises(ValueError):decode_state(value)
    value = copy.deepcopy(game.building_state)
    value['scene'].update(kind='construction',node='plan:9:bogus')
    with pytest.raises(ValueError):decode_state(value)
    row = next(iter(value['records'].values()));value.pop('scene');value['cultivation'].clear()
    row.update(type='scenery',subtype='view',status='destroyed',owner=dict(kind='none',id=None))
    with pytest.raises(ValueError):decode_state(value)


def test_dlc_temple_is_same_asset_and_disabled_dlc_preserves_data(local,monkeypatch):
    engine, game = local
    monkeypatch.setitem(buddhist_config(),'enabled',True)
    game.player.path='buddhist';engine.store.save(game)
    initial = stable_time(game)
    engine.building_action(game.id,'temple-plan')
    choose(engine,game.id,'confirm')
    game = engine.store.load(game.id)
    site = game.buddhist_state['worlds'][game.player.world]['sites'][game.player.location_id]
    assert site['temple']==1 and not game.building_state['records']
    assert stable_time(game)==initial
    choose(engine,game.id,'temple');choose(engine,game.id,'temple:upgrade')
    game = engine.store.load(game.id)
    assert game.buddhist_state['worlds'][game.player.world]['sites'][game.player.location_id]['temple']==2
    assert next(r for r in buildings.local_rows(game) if r.get('subtype')=='temple')['level']==2
    preserved=copy.deepcopy(game.buddhist_state)
    game.pending_event['_followup_event']=copy.deepcopy(engine.events_by_id['EVT_SECT_FIRST_WARNING_001']);engine.store.save(game)
    monkeypatch.setitem(buddhist_config(),'enabled',False)
    shown=engine.get_game(game.id)
    assert not any(r.get('subtype')=='temple' for r in shown['buildings']['rows']) and not shown['buildings']['inside']
    assert shown['pending_event']['id']=='EVT_SECT_FIRST_WARNING_001'
    assert engine.store.load(game.id).buddhist_state==preserved


def test_existing_industry_uses_original_record(local):
    from test_economy_enterprises import buy
    engine,game=local
    game,identity=buy(engine,game,'farm')
    before=copy.deepcopy(game.economy_v2['estates'][identity])
    row=next(r for r in buildings.local_rows(game) if r['type']=='industry')
    assert row['source_id']==identity and 'stock' not in row
    engine.building_action(game.id,'enter',building_id=row['id'])
    choose(engine,game.id,'details');choose(engine,game.id,'back');choose(engine,game.id,'leave')
    assert engine.store.load(game.id).economy_v2['estates'][identity]==before


def test_real_cultivation_advances_original_years_with_only_qi_amplified(local):
    engine, game = local
    construct(engine, game)
    choose(engine, game.id, 'leave')
    game = engine.store.load(game.id)
    game.settings['silent_events'] = True
    game.settings['guixu_event_popup'] = False
    snapshot = copy.deepcopy(game.to_dict())
    engine.store.save(game)
    engine.advance(game.id, 'cultivate', 1)
    boosted = engine.store.load(game.id)
    plain = GameState.from_dict(snapshot)
    plain.building_state['cultivation'].clear();engine.store.save(plain)
    engine.advance(game.id, 'cultivate', 1)
    plain = engine.store.load(game.id)
    assert boosted.player.age == plain.player.age > game.player.age
    assert boosted.player.opportunity == plain.player.opportunity
    assert boosted.rng_state == plain.rng_state
    for source, before in game.player.qi_experience.items():
        assert boosted.player.qi_experience[source]-before == pytest.approx((plain.player.qi_experience[source]-before)*1.04)


def test_qi_lookup_never_scans_building_records(local):
    engine, game = local
    game = construct(engine, game)
    class IndexOnly(dict):
        def values(self):raise AssertionError('Annual qi lookup scanned all buildings')
        def __iter__(self):raise AssertionError('Annual qi lookup iterated all buildings')
    game.building_state['records'] = IndexOnly(game.building_state['records'])
    for _ in range(1000):assert qi_multiplier(game.player) == 1.04


def test_ground_cave_does_not_boost_guixu_or_trial_scene(local):
    engine, game = local
    game = construct(engine, game)
    game.guixu_state['player_session'] = dict(dungeon_id='instance',trapped=True)
    assert qi_multiplier(game.player)==1
    game.guixu_state['player_session']=None
    game.trial_site_state['active']=dict(world=game.player.world,floor=1)
    assert qi_multiplier(game.player)==1
