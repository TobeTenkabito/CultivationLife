"""Paid-year interruptions and expiry of a captive soul before extraction."""

import pytest

from test_survival_settlement import base, ready, attach_second
from test_soul_lifecycle import act, prisoner
from cultivation_life.system import soul_lifecycle as life
from cultivation_life.system.soul_presentation import public


def test_real_rest_stops_after_erosion_consumes_second_soul(ready):
    engine, game = ready
    game.player.path = 'ghost'
    engine.store.save(game)
    engine.get_game(game.id)
    game = engine.store.load(game.id)
    attach_second(game)
    game.player.ghost_soul_erosion_rate_pp = 100
    game.player.ghost_soul_erosion_time_progress = .99
    engine.store.save(game)
    engine.advance(game.id, 'rest', 1)
    after = engine.store.load(game.id)
    assert after.player.alive
    assert 'second' not in after.player.nascent_state
    assert after.player.age == game.player.age + 1
    assert len([r for r in after.history if r.state_diff.get('second_rescued')]) == 1


@pytest.mark.parametrize('expired', ['lifespan', 'spirit'])
def test_expired_captive_cannot_start_refinement(ready, expired):
    engine, game = ready
    npc = prisoner(game)
    game.player.nascent_state['known'] = ['second_nascent']
    if expired == 'lifespan':
        npc.lifespan = npc.age
    else:
        npc.spirit_state = dict(mode='wandering', body_intact=False,
            entered=game.player.age-5, deadline=game.player.age-1, address=life.address(game))
    engine.store.save(game)
    engine.get_game(game.id)
    assert not public(engine.store.load(game.id))['captives']
    before = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError):
        act(engine, game, 'refine', id=npc.id)
    assert engine.store._path(game.id).read_bytes() == before


def test_captive_spirit_expiring_in_last_paid_year_is_not_revived_as_second(ready):
    engine, game = ready
    npc = prisoner(game)
    npc.spirit_state = dict(mode='wandering', body_intact=False, entered=game.player.age-5,
                           deadline=game.player.age, address=life.address(game))
    game.player.nascent_state.update(known=['second_nascent'], refining=dict(id=npc.id, years=2))
    engine.store.save(game)
    act(engine, game, 'refine', id=npc.id)
    after = engine.store.load(game.id)
    assert after.player.age == game.player.age+1
    assert 'second' not in after.player.nascent_state
    assert 'refining' not in after.player.nascent_state
    assert not after.inactive_npcs[npc.id].alive
    assert after.inactive_npcs[npc.id].roster_state == 'retired'
    assert after.inactive_npcs[npc.id].custody is None
    assert after.inactive_npcs[npc.id].death_reason == '神游超时，元婴消散'
    assert after.player.soul_energy == game.player.soul_energy - 15
    assert not public(after)['captives']
    engine.get_game(game.id)
    before = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError):
        act(engine, game, 'refine', id=npc.id)
    assert engine.store._path(game.id).read_bytes() == before


@pytest.mark.parametrize('path,deadline_offset', [('dao', 1), ('ghost', -1)])
def test_exact_deadline_and_ghost_exemption_still_allow_final_refinement(ready, path, deadline_offset):
    engine, game = ready
    npc = prisoner(game)
    npc.path = path
    npc.spirit_state = dict(mode='wandering', body_intact=False, entered=game.player.age-5,
                           deadline=game.player.age+deadline_offset, address=life.address(game))
    game.player.nascent_state.update(known=['second_nascent'], refining=dict(id=npc.id, years=2))
    engine.store.save(game)
    assert public(game)['captives'][0]['id'] == npc.id
    act(engine, game, 'refine', id=npc.id)
    after = engine.store.load(game.id)
    assert after.player.nascent_state['second']['id'] == npc.id
    assert after.inactive_npcs[npc.id].alive
    from cultivation_life.system.npc_soul import expired
    assert not expired(after.inactive_npcs[npc.id], after.player.age + 100)


@pytest.mark.parametrize('invalid', ['foreign-world', 'foreign-holder', 'other-kind', 'dead', 'low-rank'])
def test_refinement_list_uses_original_captive_eligibility(ready, invalid):
    _, game = ready
    npc = prisoner(game)
    assert public(game)['captives'][0]['id'] == npc.id
    if invalid == 'foreign-world':
        npc.world = 'spirit'
    elif invalid == 'foreign-holder':
        npc.custody['holder_id'] = 'someone-else'
    elif invalid == 'other-kind':
        npc.custody['kind'] = 'living_puppet'
    elif invalid == 'dead':
        npc.alive = False
    else:
        npc.realm_index = 3
    assert not public(game)['captives']
