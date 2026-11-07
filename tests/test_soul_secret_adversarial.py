"""Adversarial loaded commands: stale conversion consent and retained inheritances."""
import pytest

from test_soul_lifecycle import ready, prisoner
from cultivation_life.models import Technique
from cultivation_life.rules import qi_level_threshold


def convertible(engine, game):
    p = game.player
    p.nascent_state['known'] = ['path_ghost', 'second_nascent']
    p.known_techniques.append(Technique(id='audit-ghost-book', name='验收阴魂经', path='ghost'))
    p.qi_experience['yin'] = qi_level_threshold(10)
    engine.store.save(game)
    view = engine.get_game(game.id)
    row = next(r for r in view['soul']['conversions'] if r['id'] == 'ghost')
    return dict(id='ghost', revision=view['soul']['revision'], quote=row.get('quote'))


@pytest.mark.parametrize('change', ['qi', 'realm', 'opportunity', 'location'])
def test_conversion_rejects_changed_quote_without_charging(ready, change):
    engine, game = ready
    payload = convertible(engine, game)
    saved = engine.store.load(game.id)
    if change == 'qi': saved.player.qi_experience['yin'] = 0
    elif change == 'realm': saved.player.layer += 1
    elif change == 'opportunity': saved.player.opportunity += 100
    else: saved.player.location_id = 'mirror_lake'
    engine.store.save(saved)
    engine.get_game(game.id)
    before = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError, match='预览|过期'):
        engine.soul_action(game.id, 'convert', payload)
    assert engine.store._path(game.id).read_bytes() == before


def test_retained_second_nascent_secret_cannot_refine_after_rank_loss(ready):
    engine, game = ready
    npc = prisoner(game)
    game.player.nascent_state['known'] = ['second_nascent']
    game.player.realm_index = 3
    engine.store.save(game)
    view = engine.get_game(game.id)
    before = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError, match='元婴'):
        engine.soul_action(game.id, 'refine', dict(id=npc.id, revision=view['soul']['revision']))
    assert engine.store._path(game.id).read_bytes() == before


@pytest.mark.parametrize('quote', [None, '', 'not-a-preview', {}, 1])
def test_conversion_requires_actual_preview(ready, quote):
    engine, game = ready
    payload = convertible(engine, game)
    payload['quote'] = quote
    before = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError, match='预览'):
        engine.soul_action(game.id, 'convert', payload)
    assert engine.store._path(game.id).read_bytes() == before


def test_preview_is_stable_readonly_and_successful_confirmation_is_single_use(ready):
    engine, game = ready
    payload = convertible(engine, game)
    before = engine.store._path(game.id).read_bytes()
    reread = engine.get_game(game.id)
    assert next(r['quote'] for r in reread['soul']['conversions'] if r['id'] == 'ghost') == payload['quote']
    assert engine.store._path(game.id).read_bytes() == before
    result = engine.soul_action(game.id, 'convert', payload)
    assert result['player']['path'] == 'ghost'
    # Complete the existing path-specific load preparation before testing replay.
    engine.get_game(game.id)
    after = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError):
        engine.soul_action(game.id, 'convert', payload)
    assert engine.store._path(game.id).read_bytes() == after


def test_in_progress_refinement_pauses_after_rank_loss_and_can_be_cancelled(ready):
    engine, game = ready
    npc = prisoner(game)
    game.player.nascent_state.update(known=['second_nascent'], refining=dict(id=npc.id, years=1))
    game.player.realm_index = 3
    engine.store.save(game)
    view = engine.get_game(game.id)
    assert not view['soul']['can_refine'] and view['soul']['refining']['years'] == 1
    before = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError, match='元婴'):
        engine.soul_action(game.id, 'refine', dict(id=npc.id, revision=view['soul']['revision']))
    assert engine.store._path(game.id).read_bytes() == before
    engine.soul_action(game.id, 'cancel_refine', dict(revision=view['soul']['revision']))
    after = engine.store.load(game.id)
    assert 'refining' not in after.player.nascent_state
    from cultivation_life.relationship_records import find_person
    retained = find_person(after, npc.id, include_inactive=True)
    assert after.player.soul_energy == game.player.soul_energy
    assert retained and retained.alive and retained.custody['holder_id'] == game.id
    assert any(r['id'] == npc.id for r in after.player.prisoners)


@pytest.mark.parametrize('place', ['lost', 'secluded', 'guixu'])
def test_real_special_area_disables_soul_and_remote_scenery_commands(ready, place):
    from test_npc_development_special_areas import make_game, enter_rift, enter_guixu
    engine, _ = ready
    game = make_game(engine)
    convertible(engine, game)
    game = engine.store.load(game.id)
    game = enter_guixu(engine, game) if place == 'guixu' else enter_rift(engine, game, place)
    shown = engine.get_game(game.id)
    assert shown['soul']['blocked']
    before = engine.store._path(game.id).read_bytes()
    quote = next(r['quote'] for r in shown['soul']['conversions'] if r['id'] == 'ghost')
    for action in ('leave', 'convert'):
        with pytest.raises(ValueError):
            engine.soul_action(game.id, action, dict(id='ghost', quote=quote, revision=shown['soul']['revision']))
        assert engine.store._path(game.id).read_bytes() == before
    with pytest.raises(ValueError):
        engine.building_action(game.id, 'enter', building_id='scenery:human:returning_soul_lamp')
    assert engine.store._path(game.id).read_bytes() == before
