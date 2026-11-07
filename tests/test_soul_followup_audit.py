"""Real soul commands across spatial emergencies and stale custody boundaries."""
import copy
import random
from unittest.mock import patch

import pytest

from test_survival_settlement import base, ready, attach_second
from test_soul_lifecycle import prisoner, act
from cultivation_life.content_registry import TECHNIQUE_CATALOG
from cultivation_life.system import soul_lifecycle as life
from cultivation_life.system import second_nascent
from cultivation_life.system.possession_system import advance_player_age


@pytest.mark.parametrize('place', ['lost', 'secluded', 'guixu'])
def test_crisis_can_be_resisted_after_real_special_area_entry(ready, place):
    from test_npc_development_special_areas import make_game, enter_rift, enter_guixu
    engine, _ = ready
    game = make_game(engine)
    game = enter_guixu(engine, game) if place == 'guixu' else enter_rift(engine, game, place)
    game.pending_event = None
    game.player.soul_energy = 0
    rng = random.Random(9)
    with patch.object(rng, 'randrange', return_value=1):
        life.resolve_energy(game, rng, engine._die)
    assert game.player.nascent_state['crisis'] == 'possession'
    with pytest.raises(ValueError, match='危机'):
        advance_player_age(game.player)
    engine.store.save(game)
    address = life.address(game)
    age = game.player.age
    with patch.object(random.Random, 'random', return_value=0):
        shown = act(engine, game, 'resist')
    assert shown['player']['alive'] and not shown['soul']['crisis']
    after = engine.store.load(game.id)
    assert life.address(after) == address and after.player.age == age
    assert after.guixu_state == game.guixu_state
    with pytest.raises(ValueError):
        act(engine, after, 'leave')


@pytest.mark.parametrize('kind', ['living_puppet', 'concubine', 'external_avatar', 'second_nascent'])
def test_stale_prisoner_reference_cannot_refine_a_different_custody_kind(ready, kind):
    engine, game = ready
    npc = prisoner(game)
    game.player.nascent_state['known'] = ['second_nascent']
    npc.custody['kind'] = kind
    engine.store.save(game)
    engine.get_game(game.id)
    before = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError, match='俘虏'):
        act(engine, game, 'refine', id=npc.id)
    assert engine.store._path(game.id).read_bytes() == before
    assert engine.store.load(game.id).inactive_npcs[npc.id].custody['kind'] == kind
    assert all(row['id'] != npc.id for row in engine.store.load(game.id).player.prisoners)


def test_second_power_ignores_techniques_disabled_in_its_world(ready):
    _, game = ready
    npc = attach_second(game)
    npc.main_technique_id = None
    npc.technique_slots = {}
    baseline = second_nascent.full_power(game)
    book = copy.deepcopy(TECHNIQUE_CATALOG['TECH_BASIC_QI'])
    book.effective_worlds = ['celestial']
    book.combat_bonus = 1234
    npc.main_technique_id = book.id
    npc.main_technique_level = 1
    npc.technique_levels = {book.id: 1}
    with patch.dict(TECHNIQUE_CATALOG, {book.id: book}):
        assert second_nascent.full_power(game) == baseline
        book.effective_worlds = [npc.world]
        assert second_nascent.full_power(game) > baseline


@pytest.mark.parametrize('second', [False, True])
def test_failed_resistance_in_real_space_uses_normal_death_settlement(ready, second):
    from test_npc_development_special_areas import make_game, enter_rift
    engine, _ = ready
    game = make_game(engine)
    if second:
        attach_second(game)
    game = enter_rift(engine, game, 'secluded')
    game.pending_event = None
    game.player.nascent_state.update(crisis='possession', depleted=True)
    game.player.soul_energy = 0
    engine.store.save(game)
    address = life.address(game)
    age = game.player.age
    with patch.object(random.Random, 'random', return_value=.9999):
        view = act(engine, game, 'resist')
    after = engine.store.load(game.id)
    assert after.player.alive is second and view['player']['alive'] is second
    assert 'second' not in after.player.nascent_state
    assert life.address(after) == address and after.player.age == age
    assert len([r for r in after.history if r.result == 'dead']) == (0 if second else 1)


@pytest.mark.parametrize('blocked_by', ['dead', 'event', 'trial', 'no_crisis'])
def test_resistance_does_not_bypass_terminal_or_pending_content(ready, blocked_by):
    from cultivation_life.system.soul_actions import execute
    from cultivation_life.system.soul_presentation import public
    _, game = ready
    game.player.nascent_state.update(crisis='possession', depleted=True)
    if blocked_by == 'dead': game.player.alive = False
    elif blocked_by == 'event': game.pending_event = {'id': 'ongoing-event'}
    elif blocked_by == 'trial': game.active_trial = {'id': 'ongoing-trial'}
    else: game.player.nascent_state.pop('crisis')
    original = copy.deepcopy(game.to_dict())
    assert not public(game)['can_resist']
    with pytest.raises(ValueError):
        execute(None, game, 'resist', {'revision': game.player.nascent_state.get('revision', 0)}, random.Random(1))
    assert game.to_dict() == original


def test_load_preserves_foreign_holder_despite_stale_prisoner_list(ready):
    engine, game = ready
    npc = prisoner(game)
    npc.custody['holder_id'] = 'another-holder'
    game.player.nascent_state['known'] = ['second_nascent']
    engine.store.save(game)
    loaded = engine.store.load(game.id)
    assert loaded.inactive_npcs[npc.id].custody == npc.custody
    assert not any(row['id'] == npc.id for row in loaded.player.prisoners)
    with pytest.raises(ValueError, match='俘虏'):
        act(engine, loaded, 'refine', id=npc.id)


@pytest.mark.parametrize('field', ['imprisonment', 'ghost_captor', 'sealed_cultivation', 'cultivation_suppression'])
def test_internal_resistance_preserves_existing_constraints(ready, field):
    from cultivation_life.system.soul_actions import execute, SoulDependencies
    from cultivation_life.system.soul_presentation import public
    engine, game = ready
    restriction = dict(realm_index=4, layer=2, lifespan=10000, id='existing-constraint')
    setattr(game.player, field, copy.deepcopy(restriction))
    game.player.nascent_state.update(crisis='possession', depleted=True)
    game.player.soul_energy = 0
    assert public(game)['can_resist'] and public(game)['blocked']
    rng = random.Random(1)
    with patch.object(rng, 'random', return_value=0):
        execute(SoulDependencies(None, None, engine._die), game, 'resist',
                {'revision': game.player.nascent_state.get('revision', 0)}, rng)
    assert getattr(game.player, field) == restriction
    assert game.player.alive and 'crisis' not in game.player.nascent_state
