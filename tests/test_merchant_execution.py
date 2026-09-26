import copy
import random

import pytest

from test_merchant_system import setup, join, stones
from cultivation_life.models import GameState
from cultivation_life.rules import add_item


def posted(setup, stars=3):
    engine, game = setup
    game, alliance = join(engine, game)
    add_item(game.player, 'spirit_stone', 10**9)
    engine._merchant_post(game, alliance, {'kind':'intel', 'stars':stars})
    return engine, game, game.merchant_state['posted'][-1]


def test_risk_increases_with_stars_and_decreases_with_realm(setup):
    engine, _ = setup
    for realm in range(1, 9):
        risks = [engine._merchant_failure_chance(stars, realm, 5) for stars in range(1, 6)]
        assert risks == sorted(risks)
        assert all(.03 <= risk <= .92 for risk in risks)
    risks = [engine._merchant_failure_chance(5, realm, 5) for realm in range(1, 9)]
    assert risks == sorted(risks, reverse=True)
    assert risks[0] > risks[-1]


@pytest.mark.parametrize('succeed', [False, True])
def test_real_worker_progress_persistence_terminal_settlement(setup, succeed):
    engine, game, order = posted(setup)
    engine._merchant_start_order(game, order, random.Random(4))
    worker = engine._find_npc(game, order['worker_id'])
    assert worker.alive and worker.realm_index == order['worker_realm']
    order.update(will_finish=succeed, failure_age=order['started_age'] + 7)
    before = stones(game)
    game.player.age += 5
    engine._advance_merchant_year(game)
    assert order['status'] == 'working' and .5 < order['progress'] < 1
    assert len(order['logs']) >= 3
    game = GameState.from_dict(game.to_dict())
    order = game.merchant_state['posted'][-1]
    game.player.age = order['finish_age']
    engine._advance_merchant_year(game)
    assert order['status'] == ('completed' if succeed else 'failed')
    assert (order['progress'] == 1) == succeed
    refund = 0 if succeed else order['principal'] + (order['fee'] + 1) // 2
    assert stones(game) == before + refund
    assert any(('已完成' if succeed else '失败') in row['message'] for row in game.merchant_state['notices'])
    logs = copy.deepcopy(order['logs'])
    game.player.age += 100
    engine._advance_merchant_year(game)
    assert stones(game) == before + refund and order['logs'] == logs
    public = engine._public_merchant(game)['posted'][-1]
    assert 'will_finish' not in public and 'failure_age' not in public


def test_worker_death_fails_without_reward(setup):
    engine, game, order = posted(setup)
    engine._merchant_start_order(game, order, random.Random(4))
    order['will_finish'] = True
    engine._find_npc(game, order['worker_id']).alive = False
    game.player.age += 1
    engine._advance_merchant_year(game)
    assert order['status'] == 'failed' and not order.get('delivery')
    assert '失联' in order['logs'][-1]['message']


def test_unlinked_routes_rejected_for_all_order_types(setup):
    engine, game = setup
    game, alliance = join(engine, game, world='true_demon', alliance_id='xuanji')
    assert {row['world'] for row in engine._merchant_procurement_catalog(game, alliance)} == {'spirit', 'true_demon'}
    before = copy.deepcopy(game.to_dict())
    for kind in ('supply', 'item', 'weapon', 'formation', 'bounty', 'intel', 'escort', 'recruit'):
        for target in ('human', 'monster_realm', 'hell'):
            with pytest.raises(ValueError, match='分总部'):
                engine._merchant_post(game, alliance, {'kind':kind, 'source_world':target})
    assert game.to_dict() == before


def test_v1_migration_preserves_identity_active_task_and_refunds_removed_routes(setup):
    engine, game, order = posted(setup)
    state = game.merchant_state
    old = state['worlds']['human'][0]
    # Reproduce the former three-alliance topology and identity.
    old.update(id='xuanji', name='璇玑商盟', cross_world=True, linked_worlds=['human','spirit','true_demon','monster_realm'])
    state['worlds']['human'][1]['id'] = 'human-0'
    state['worlds']['human'][2]['id'] = 'human-1'
    state['membership'].update(alliance_id='xuanji', rank=2)
    state['influence'] = {'human:xuanji:offices':650}
    state['active'] = {'world':'human', 'alliance_id':'xuanji', 'influence_key':'human:xuanji:offices', 'worked':2}
    order.update(alliance_id='xuanji', source_world='spirit')
    state['version'] = 1
    before = stones(game)
    assert engine._ensure_merchant(game)
    assert state['version'] == 2
    assert state['membership']['alliance_id'] == 'human-2' and state['membership']['rank'] == 2
    assert state['active']['worked'] == 2 and state['active']['influence_key'] == 'human:human-2:offices'
    assert state['influence']['human:human-2:offices'] == 650
    assert len({row['id'] for row in state['worlds']['human']}) == 3
    assert not engine._merchant_alliance(game, 'human', 'xuanji')
    assert order['status'] == 'cancelled' and order['refund_fee'] == order['fee']
    assert stones(game) == before + order['total']
    snapshot = copy.deepcopy(game.to_dict())
    assert not engine._ensure_merchant(game)
    assert game.to_dict() == snapshot


def test_removed_passage_seal_returns_old_visitor_safely(setup):
    engine, game = setup
    game.merchant_state['version'] = 1
    game.player.world = 'monster_realm'
    game.player.realm_index, game.player.layer = 7, 9
    game.player.sealed_cultivation = {'merchant_passage':True, 'realm_index':8, 'layer':9,
                                    'upper_world':'spirit', 'lower_world':'monster_realm',
                                    'lifespan':50000, 'tribulation_remaining':50}
    age = game.player.age
    engine._ensure_merchant(game)
    assert game.player.world == 'spirit' and game.player.realm_index == 8
    assert not game.player.sealed_cultivation
    assert game.player.next_tribulation_age == age + 50


def test_large_time_jump_delivers_due_order_before_later_deadline(setup):
    engine, game, order = posted(setup)
    engine._merchant_start_order(game, order, random.Random(4))
    order['will_finish'] = True
    game.player.age = order['deadline'] + 100
    engine._advance_merchant_year(game)
    assert order['status'] == 'completed'
    assert [row['age'] for row in order['logs']] == sorted(row['age'] for row in order['logs'])
