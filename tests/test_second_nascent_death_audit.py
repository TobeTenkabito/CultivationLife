"""Authoritative second-soul identity, possession death gates and escrow regressions."""
import copy
import random
from unittest.mock import patch

import pytest

from test_survival_settlement import base, ready, attach_second
from cultivation_life.models import Item
from cultivation_life.system import soul_lifecycle as life
from cultivation_life.system.possession_system import enter_host_body, is_possessed
from cultivation_life.npc_custody import release_person


def possess(game, rank=3):
    life.leave_body(game, destroyed=True)
    return enter_host_body(game.player, dict(id='audit-host', name='异名宿主', realm_index=rank,
        layer=1, age=30, lifespan=10000, path='demonic', spirit_root='heavenly',
        body_training=5, divine_sense_rank=5))


def escrow(game):
    game.player.nascent_state['second']['equipment'] = [Item('audit-escrow', '托管剑', combat_bonus=10).to_dict()]


@pytest.mark.parametrize('stage', ['body', 'spirit_failed'])
def test_low_rank_host_does_not_remove_original_soul_survival_qualification(ready, stage):
    engine, game = ready
    attach_second(game)
    original_name = game.player.name
    possess(game, 3)
    engine._die(game, '宿身遭到致命伤', 'SYS_TEST_FATAL', survival_stage=stage)
    assert game.player.alive
    assert not is_possessed(game.player) and game.player.name == original_name
    assert ('second' in game.player.nascent_state) is (stage == 'body')


def test_second_rescue_restores_core_identity_before_inheriting_new_rank(ready):
    engine, game = ready
    npc = attach_second(game, rank=5, remaining=7)
    original = (game.player.name, game.player.path, game.player.spirit_root,
                game.player.divine_sense_rank, copy.deepcopy(game.player.known_techniques))
    escrow(game)
    possess(game, 4)
    engine._die(game, '宿身与本魂受创', 'SYS_TEST_FATAL', survival_stage='spirit_failed')
    assert game.player.alive and not is_possessed(game.player)
    assert (game.player.name, game.player.path, game.player.spirit_root,
            game.player.divine_sense_rank, game.player.known_techniques) == original
    assert (game.player.realm_index, game.player.layer) == (npc.realm_index, npc.layer)
    assert game.player.lifespan == game.player.age + 7
    assert not npc.alive and sum(i.quantity for i in game.player.inventory if i.id == 'audit-escrow') == 1
    engine.store.save(game)
    loaded = engine.store.load(game.id)
    life.settle_second(loaded)
    assert loaded.to_dict() == game.to_dict()


@pytest.mark.parametrize('stage', ['body', 'spirit_failed'])
def test_damaged_core_cannot_borrow_host_rank_to_survive(ready, stage):
    engine, game = ready
    attach_second(game)
    possess(game, 4)
    game.player.ghost_core_state['realm_index'] = 3
    engine._die(game, '本魂跌境后受创', 'SYS_TEST_FATAL', survival_stage=stage)
    assert not game.player.alive and 'second' in game.player.nascent_state


@pytest.mark.parametrize('cause', ['host_expired', 'story', 'special'])
def test_possessed_survival_still_obeys_terminal_death_gates(ready, cause):
    engine, game = ready
    attach_second(game)
    possess(game)
    if cause == 'host_expired':
        game.player.lifespan = game.player.ghost_host_body['age']
    engine._die(game, '不可承接的死亡', 'EVT_FATAL' if cause == 'story' else 'SYS_TEST_FATAL',
                survival_stage='special' if cause == 'special' else 'spirit_failed')
    assert not game.player.alive and 'second' in game.player.nascent_state


@pytest.mark.parametrize('invalid', ['released', 'other_holder', 'different_kind', 'already_dead'])
def test_stale_second_reference_cannot_age_or_kill_uncontrolled_person(ready, invalid):
    _, game = ready
    npc = attach_second(game)
    escrow(game)
    if invalid == 'released': release_person(game, npc.id)
    elif invalid == 'other_holder': npc.custody['holder_id'] = 'another-holder'
    elif invalid == 'different_kind': npc.custody['kind'] = 'prisoner'
    else:
        npc.alive = False
        npc.death_reason = '先前已陨落'
    original = copy.deepcopy(npc.to_dict())
    game.player.age += 2
    life.settle_second(game)
    assert npc.to_dict() == original
    assert 'second' not in game.player.nascent_state
    assert sum(i.quantity for i in game.player.inventory if i.id == 'audit-escrow') == 1
    life.settle_second(game)
    life.consume_second(game, '重复清理')
    assert sum(i.quantity for i in game.player.inventory if i.id == 'audit-escrow') == 1


def test_dead_actor_repeated_settlement_cannot_consume_second_or_duplicate_death(ready):
    engine, game = ready
    attach_second(game)
    escrow(game)
    engine._die(game, '必死剧情', 'EVT_AUDIT_FATAL')
    original = copy.deepcopy(game.to_dict())
    engine._die(game, '重复普通死亡', 'SYS_TEST_FATAL')
    life.tick(game, random.Random(1), engine._die)
    assert game.to_dict() == original


@pytest.mark.parametrize('damage', [1, 2])
def test_final_refinement_year_cannot_complete_after_soul_damage(ready, damage):
    from test_soul_lifecycle import prisoner, act
    engine, game = ready
    npc = prisoner(game)
    game.player.nascent_state.update(known=['second_nascent'], refining=dict(id=npc.id, years=2))
    game.player.soul_energy = 15
    engine.store.save(game)
    original_randrange = random.Random.randrange

    def outcome(rng, *args, **kwargs):
        return damage if args == (3,) and not kwargs else original_randrange(rng, *args, **kwargs)

    with patch.object(random.Random, 'randrange', outcome):
        act(engine, game, 'refine', id=npc.id)
    loaded = engine.store.load(game.id)
    assert loaded.player.alive
    assert loaded.player.realm_index < 4 if damage == 2 else loaded.player.nascent_state.get('crisis')
    assert 'second' not in loaded.player.nascent_state
    assert loaded.player.nascent_state['refining']['years'] == 2
    assert any(row['id'] == npc.id for row in loaded.player.prisoners)
    assert loaded.player.age == game.player.age + 1 and loaded.player.soul_energy == 0
    loaded.pending_event = None
    loaded.player.realm_index = 4
    loaded.player.soul_energy = 100
    loaded.player.nascent_state.pop('crisis', None)
    engine.store.save(loaded)
    act(engine, loaded, 'refine', id=npc.id)
    completed = engine.store.load(game.id)
    assert life.second_person(completed).id == npc.id
    assert 'refining' not in completed.player.nascent_state
