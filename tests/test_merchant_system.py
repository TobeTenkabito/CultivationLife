import copy
import random
from pathlib import Path
from unittest.mock import patch

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.models import GameState
from cultivation_life.rules import add_item, max_hp, max_mp
from cultivation_life.system.crafting_system import make_crafting_material_instance, store_crafted_artifact


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def setup(tmp_path):
    engine = GameEngine(ROOT, tmp_path)
    game_id = engine.create_game('商盟验收', 'heavenly', 'dao', 1350, preset_id='core')['id']
    game = engine._load(game_id)
    game.player.next_tribulation_age = None
    return engine, game


def join(engine, game, *, world='human', hq=False, alliance_id=None):
    game.player.world = world
    alliance = next((row for row in game.merchant_state['worlds'][world] if row['id'] == alliance_id), game.merchant_state['worlds'][world][0])
    game.player.location_id = alliance['hq'] if hq else alliance['offices'][0]['location_id']
    engine.store.save(game)
    engine.merchant_action(game.id, 'join', {'alliance_id': alliance['id']})
    return engine._load(game.id), alliance


def stones(game):
    return next((row.quantity for row in game.player.inventory if row.id == 'spirit_stone'), 0)


def test_three_alliances_per_world_single_hq_and_save_migration(setup):
    engine, game = setup
    for world, alliances in game.merchant_state['worlds'].items():
        assert len(alliances) == 3
        assert len({row['id'] for row in alliances}) == 3
        for alliance in alliances:
            assert alliance['hq'] not in [office['location_id'] for office in alliance['offices']]
            assert not engine.maps.location(world, alliance['hq']).get('min_realm_index')
            assert alliance['offices']
    saved = game.to_dict()
    assert GameState.from_dict(saved).merchant_state == game.merchant_state
    saved.pop('merchant_state')
    old = GameState.from_dict(saved)
    assert engine._ensure_merchant(old)
    assert old.merchant_state == game.merchant_state
    assert not engine._ensure_merchant(old)


def test_join_at_site_independent_identity_and_hq_promotion_path(setup):
    engine, game = setup
    game.player.faction_id = 'test-sect'
    game, alliance = join(engine, game, hq=True)
    assert game.player.faction_id == 'test-sect'
    with pytest.raises(ValueError, match='总部直入'):
        engine.merchant_action(game.id, 'promote')
    game.player.location_id = alliance['offices'][0]['location_id']
    engine.store.save(game)
    engine.merchant_action(game.id, 'transfer_branch')
    game = engine._load(game.id)
    key = engine._merchant_influence_key(game.merchant_state['membership'])
    game.merchant_state['influence'][key] = 600
    engine.store.save(game)
    engine.merchant_action(game.id, 'promote')
    engine.merchant_action(game.id, 'promote')
    game = engine._load(game.id)
    assert game.merchant_state['membership']['rank'] == 2
    if len(alliance['offices']) > 1:
        game.player.location_id = alliance['offices'][1]['location_id']
        engine.store.save(game)
        engine.merchant_action(game.id, 'transfer_branch')
        game = engine._load(game.id)
        assert engine._public_merchant(game)['membership']['influence'] == 600
    game.player.location_id = alliance['hq']
    engine.store.save(game)
    shown = engine.merchant_action(game.id, 'hq_exam')['merchant_system']
    assert shown['membership']['site'] == 'hq' and shown['membership']['rank'] == 1
    assert shown['membership']['influence'] == 0


def test_world_information_isolation_and_crossworld_catalog(setup):
    engine, game = setup
    game, alliance = join(engine, game, world='true_demon', alliance_id='xuanji')
    public = engine._public_merchant(game)
    assert len(public['alliances']) == 3
    cross = next(row for row in public['alliances'] if row['id'] == 'xuanji')
    assert {'spirit', 'true_demon'} <= {row['world'] for row in cross['catalog']}
    for row in public['alliances']:
        if row['id'] != 'xuanji':
            assert row['tasks'] == row['catalog'] == []


def test_supply_exact_years_and_one_time_rewards(setup):
    engine, game = setup
    game, alliance = join(engine, game)
    game.player.realm_index = 8
    game.player.layer = 1
    game.player.lifespan = 100000
    game.player.karma = 100
    task = next(row for row in engine._merchant_board(game, alliance) if row['kind'] == 'supply' and row['stars'] == 1)
    definition = engine._crafting_material_defs()[task['definition_id']]
    game.player.crafting_materials.append(make_crafting_material_instance(definition, random.Random(1), source='test', origin_world='human'))
    engine.store.save(game)
    engine.merchant_action(game.id, 'accept', {'task_id':task['id']})
    before = engine._load(game.id)
    # Exercise real annual updates; isolate unrelated ascension/tribulation.
    with patch.object(engine, '_resolve_breakthroughs'), patch.object(engine, '_check_tribulation'), patch.object(engine, '_advance_guixu_calendar', return_value=False):
        engine.merchant_action(game.id, 'work')
    after = engine._load(game.id)
    assert after.player.age - before.player.age == task['years'] == 1
    assert stones(after) - stones(before) == task['reward']['stones']
    assert after.player.karma == 97
    assert after.merchant_state['active'] is None
    with pytest.raises(ValueError, match='没有待完成'):
        engine.merchant_action(game.id, 'work')


def test_missing_materials_no_time_or_reward(setup):
    engine, game = setup
    game, alliance = join(engine, game)
    task = next(row for row in engine._merchant_board(game, alliance) if row['kind'] == 'supply')
    engine.merchant_action(game.id, 'accept', {'task_id':task['id']})
    before = engine._load(game.id)
    with pytest.raises(ValueError, match='需准备'):
        engine.merchant_action(game.id, 'work')
    after = engine._load(game.id)
    assert after.player.age == before.player.age and stones(after) == stones(before)


def test_interrupted_mission_keeps_progress_without_reward(setup):
    engine, game = setup
    game, alliance = join(engine, game)
    task = next(row for row in engine._merchant_board(game, alliance) if row['kind'] == 'escort' and row['stars'] == 2)
    engine.merchant_action(game.id, 'accept', {'task_id':task['id']})
    before = engine._load(game.id)
    with patch.object(engine, '_advance_world_year', return_value=False):
        engine.merchant_action(game.id, 'work')
    after = engine._load(game.id)
    assert after.merchant_state['active']['worked'] == 1
    assert stones(after) == stones(before)
    with patch.object(engine, '_advance_world_year', return_value=True), patch.object(engine, '_combat', return_value=('victory', '获胜')) as fight:
        engine.merchant_action(game.id, 'work')
    assert fight.call_args.args[1]['player_defending'] is True
    assert engine._load(game.id).player.age - before.player.age == task['years']


@pytest.mark.parametrize('kind', ['supply','weapon','formation','recruit','intel','escort','bounty'])
def test_posted_delivery_is_persistent_and_exactly_once(setup, kind):
    engine, game = setup
    game, alliance = join(engine, game)
    add_item(game.player, 'spirit_stone', 10000000)
    engine.store.save(game)
    definition = engine._merchant_materials('human')[0]
    target = next(npc for npc in engine._all_world_npcs(game) if npc.alive and npc.world == 'human')
    engine.merchant_action(game.id, 'post', {'kind':kind,'stars':2,'quantity':2,'definition_id':definition['id'],'target_id':target.id})
    game = engine._load(game.id)
    order = game.merchant_state['posted'][0]
    assert order['status'] == 'open'
    order.update(status='working',started_age=game.player.age,finish_age=game.player.age+2,will_finish=True,worker='测试行商')
    game.player.age += 2
    engine._advance_merchant_year(game)
    assert order['status'] == 'completed' and order['delivery']
    if kind == 'bounty':
        assert not engine._find_npc(game,target.id).alive
    if kind == 'formation':
        assert game.player.formation_loadouts[-1]['name'] == '商盟2星护行阵'
    snapshot = copy.deepcopy(game.to_dict())
    engine._advance_merchant_year(game)
    assert game.to_dict() == snapshot
    engine.store.save(game)
    shown = engine.get_game(game.id)['merchant_system']
    assert shown['posted'][0]['progress'] == 1
    assert 'will_finish' not in shown['posted'][0]


@pytest.mark.parametrize('status', ['open', 'working'])
def test_timeout_refunds_by_acceptance_status_only_once(setup, status):
    engine, game = setup
    game, alliance = join(engine, game)
    add_item(game.player, 'spirit_stone', 10000000)
    engine.store.save(game)
    before = stones(game)
    engine.merchant_action(game.id, 'post', {'kind':'intel','stars':1})
    game = engine._load(game.id)
    order = game.merchant_state['posted'][0]
    assert stones(game) == before - order['principal'] - order['fee']
    order.update(status=status,finish_age=game.player.age+1,will_finish=False)
    game.player.age = order['deadline']
    engine._advance_merchant_year(game)
    refund = (order['fee'] + 1) // 2 if status == 'working' else 0
    assert stones(game) == before - order['fee'] + refund
    assert order['status'] == ('failed' if status == 'working' else 'cancelled')
    game.player.age += 1
    engine._advance_merchant_year(game)
    assert stones(game) == before - order['fee'] + refund


def test_crossworld_delivery_slow_and_ordinary_alliance_cannot_outsource(setup):
    engine, game = setup
    game, alliance = join(engine, game, world='true_demon', alliance_id='xuanji')
    add_item(game.player,'spirit_stone',100000000)
    engine.store.save(game)
    definition = engine._merchant_materials('spirit')[0]
    engine.merchant_action(game.id,'post',{'kind':'supply','source_world':'spirit','definition_id':definition['id']})
    game = engine._load(game.id)
    assert game.merchant_state['posted'][0]['years'] == 45
    ordinary = next(row for row in game.merchant_state['worlds']['true_demon'] if not row['cross_world'])
    with pytest.raises(ValueError, match='分总部'):
        engine._merchant_post(game,ordinary,{'source_world':'spirit','definition_id':definition['id']})


def test_passage_rank_gate_suppression_and_return(setup):
    engine, game = setup
    game.player.realm_index = 8
    game.player.layer = 9
    game.player.hp, game.player.mp = max_hp(game.player), max_mp(game.player)
    game, alliance = join(engine, game, world='spirit', hq=True, alliance_id='xuanji')
    add_item(game.player,'spirit_stone',10**12)
    engine.store.save(game)
    with pytest.raises(ValueError,match='使节'):
        engine.merchant_action(game.id,'passage',{'destination':'human'})
    game.merchant_state['membership']['rank'] = 1
    engine.store.save(game)
    for destination in ('human', 'monster_realm'):
        with pytest.raises(ValueError, match='逆灵通道'):
            engine.merchant_action(game.id,'passage',{'destination':destination})
    engine.merchant_action(game.id,'passage',{'destination':'true_demon'})
    game = engine._load(game.id)
    assert game.player.realm_index == 8 and game.player.layer == 9
    assert game.merchant_state['membership']['world'] == 'spirit'
    engine.merchant_action(game.id,'passage',{'destination':'spirit'})
    assert engine._load(game.id).player.world == 'spirit'


def test_policies_rotate_reserves_change_but_presentation_does_not_tick(setup):
    engine, game = setup
    before = copy.deepcopy(game.merchant_state)
    engine._public_merchant(game)
    assert game.merchant_state == before
    game.player.age += 30
    engine._advance_merchant_year(game)
    for world, rows in game.merchant_state['worlds'].items():
        assert all(row['policy'] != old['policy'] for row,old in zip(rows,before['worlds'][world]))
        assert any(row['reserves'] != old['reserves'] for row,old in zip(rows,before['worlds'][world]))


def test_natal_cost_exact_base_and_nonlinear_growth(setup):
    engine, game = setup
    artifact = {'id':'pricing','name':'测试神兵','actual_stats':{'combat_power':3000000,'max_hp':999999999},'is_natal':False}
    store_crafted_artifact(game.player, artifact)
    engine._bind_crafted_natal_artifact(game,artifact)
    assert engine._natal_refine_cost(1,game) == 3000000
    initial = engine._natal_refine_cost(3,game)
    artifact['actual_stats']['max_hp'] *= 100
    game.player.world = 'human'
    game.natal_artifact['slots'] = ['geng_essence']
    assert engine._natal_refine_cost(3,game) == initial
    assert engine._natal_refine_cost(100,game) > 100 * engine._natal_refine_cost(1,game)
