"""A single authoritative resident, two clocks and physically shared knowledge."""
import copy
from dataclasses import replace
from unittest.mock import Mock

import pytest

from cultivation_life.models import GameState, SectNpc
from cultivation_life.npc_custody import detain_person, release_person
from cultivation_life.person_assignments import research_assignment
from cultivation_life.system.heavens import operations, survey
from cultivation_life.system.heavens.definitions import RUINS_ID
from cultivation_life.system.heavens.schema import validate_state, validate_references
from test_heavens_m1 import local
from test_heavens_ruins import site, act, load, stones


def ready(site):
    act(site, 'ruins_enter')
    act(site, 'ruins_leave')
    game = load(site)
    npc = SectNpc('survey-resident', '温砚', '', 4, 1, 80, 1000,
                  spirit_root='supreme_water', world='human', affinity=30,
                  location_id='wudi_plain', encountered_player=True)
    game.world_npcs[npc.id] = npc
    site[0].store.save(game)
    return game, npc.id


def wait(site, years):
    for _ in range(years):
        act(site, 'survey_wait')
    return load(site)


def start(site):
    before, identity = ready(site)
    act(site, 'survey_start', person_id=identity)
    return before, identity


def test_real_resident_two_clocks_and_single_material(site):
    before, identity = start(site)
    game = wait(site, 2)
    npc = game.world_npcs[identity]
    assert npc.age == before.world_npcs[identity].age + 2
    assert npc.world == 'rift' and game.player.world == 'human'
    scene = game.spatial_state['instances'][game.heavens_state['runtime']['ruins']['scene_id']]
    assert scene['npc_ids'] == [identity]
    assert '内部冻结' in operations.preview(site[2], game.id, 'survey_wait', RUINS_ID, {})['message']
    frozen = wait(site, 2)
    assert frozen.world_npcs[identity].to_dict() == npc.to_dict()
    assert survey.get(frozen)['elapsed'] == 2
    act(site, 'ruins_enter')
    other_ages = {key:p.age for key,p in frozen.world_npcs.items() if key != identity}
    learned = wait(site, 8)
    assert learned.world_npcs[identity].age == npc.age + 8
    assert all(learned.world_npcs[key].age == age for key,age in other_ages.items())
    assert survey.get(learned)['learned'] and not survey.get(learned)['shared']
    assert not learned.heavens_state['runtime']['ruins']['record_acquired']
    assert learned.player.formation_materials == []
    act(site, 'survey_share')
    assert survey.get(load(site))['shared']
    with pytest.raises(ValueError, match='尚无新的'):
        act(site, 'survey_share')
    returned = wait(site, 1)
    assert returned.world_npcs[identity].world == 'human'
    assert returned.world_npcs[identity].location_id == 'wudi_plain'
    assert not research_assignment(returned, identity)
    assert returned.spatial_state['instances'][scene['id']]['npc_ids'] == []
    assert set(returned.world_npcs) == set(before.world_npcs)
    act(site, 'ruins_observe')
    act(site, 'ruins_verify')
    reading = load(site)
    act(site, 'ruins_read')
    done = load(site)
    assert done.player.age == reading.player.age + 3
    assert len(done.player.formation_materials) == 1
    assert stones(done) == stones(before) and done.player.opportunity == before.player.opportunity
    assert GameState.from_dict(done.to_dict()).to_dict() == done.to_dict()
    with pytest.raises(ValueError):
        act(site, 'ruins_read')
    act(site, 'ruins_leave')
    with pytest.raises(ValueError, match='一次'):
        act(site, 'survey_start', person_id=identity)


@pytest.mark.parametrize('years', [0, 1, 2, 7])
def test_partial_recall_preserves_actual_knowledge(site, years):
    before, identity = start(site)
    wait(site, 2)
    with pytest.raises(ValueError, match='当面'):
        act(site, 'survey_recall')
    act(site, 'ruins_enter')
    wait(site, years)
    act(site, 'survey_recall')
    game = wait(site, 1)
    row = survey.get(game)
    assert row['status'] == 'completed' and row['elapsed'] == 3 + years
    assert row['observed'] == (years >= 2) and not row['learned']
    assert game.world_npcs[identity].age == before.world_npcs[identity].age + 3 + years
    with pytest.raises(ValueError):
        act(site, 'survey_share')


def test_outbound_cancellation_after_location_change(site):
    before, identity = start(site)
    act(site, 'ruins_enter')
    assert '外界赴约冻结' in operations.preview(site[2], before.id, 'survey_wait', RUINS_ID, {})['message']
    frozen = wait(site, 1)
    assert survey.get(frozen)['elapsed'] == 0 and frozen.world_npcs[identity].age == before.world_npcs[identity].age
    act(site, 'ruins_leave')
    game = wait(site, 1)
    game.world_npcs[identity].location_id = 'muling_desert'
    site[0].store.save(game)
    paused = wait(site, 1)
    assert survey.get(paused)['progress'] == 1
    act(site, 'survey_recall')
    cancelled = load(site)
    assert survey.get(cancelled)['status'] == 'cancelled'
    assert cancelled.world_npcs[identity].location_id == 'muling_desert'
    assert not research_assignment(cancelled, identity)


def test_physical_meeting_after_return_and_frozen_other_instance(site):
    _, identity = start(site)
    wait(site, 2)
    game = load(site)
    game.player.location_id = 'muling_desert'
    site[0].store.save(game)
    from test_heavens_m1 import issue
    issue(site, 'mirror_enter', target='mirror_field')
    issue(site, 'mirror_probe', target='mirror_field')
    assert survey.get(load(site))['elapsed'] == 2
    issue(site, 'mirror_leave', target='mirror_field')
    game = load(site)
    game.player.location_id = 'wudi_plain'
    site[0].store.save(game)
    act(site, 'ruins_enter')
    wait(site, 9)
    with pytest.raises(ValueError, match='实际会面'):
        act(site, 'survey_share')
    act(site, 'ruins_leave')
    act(site, 'survey_share')
    assert survey.get(load(site))['shared']


@pytest.mark.parametrize('inside', [False, True])
def test_death_and_custody_never_replace_or_reward(site, inside):
    _, identity = start(site)
    if inside:
        wait(site, 2)
        act(site, 'ruins_enter')
    game = load(site)
    row = copy.deepcopy(survey.get(game))
    npc = game.world_npcs[identity]
    detain_person(game, npc.to_dict(), SectNpc)
    site[0].store.save(game)
    detained = wait(site, 1)
    assert survey.get(detained)['elapsed'] == row['elapsed']
    npc = release_person(detained, identity)
    npc.lifespan = npc.age + 1
    site[0].store.save(detained)
    dead = wait(site, 1)
    assert not dead.world_npcs[identity].alive
    assert survey.get(dead)['status'] == 'failed'
    assert dead.player.formation_materials == []
    validate_references(dead)


def test_projection_preview_pure_retry_atomic_and_generation_off(site):
    before, identity = ready(site)
    engine, initial, deps = site
    snapshot = copy.deepcopy(before.to_dict())
    disk = engine.store._path(initial.id).read_bytes()
    for _ in range(3):
        view = operations.project(before, 'known', RUINS_ID, deps=deps)
        assert identity in {p['id'] for p in view['ruins']['survey']['candidates']}
        operations.preview(deps, initial.id, 'survey_start', RUINS_ID, {'person_id':identity})
    assert before.to_dict() == snapshot and engine.store._path(initial.id).read_bytes() == disk
    broken = replace(deps, get_store=lambda: Mock(save=Mock(side_effect=OSError('disk'))))
    with pytest.raises(OSError):
        operations.command(broken, initial.id, before.heavens_state['command_seq']+1,
                           before.heavens_state['revision'], 'survey_start', RUINS_ID, {'person_id':identity})
    assert engine.store._path(initial.id).read_bytes() == disk
    result = act(site, 'survey_start', person_id=identity)
    assert operations.command(deps, initial.id, result['command_seq'], before.heavens_state['revision'],
                              'survey_start', RUINS_ID, {'person_id':identity}) == result
    game = load(site)
    game.heavens_state['generation_enabled'] = False
    engine.store.save(game)
    wait(site, 2)
    act(site, 'ruins_enter')
    assert survey.get(wait(site, 9))['status'] == 'completed'


@pytest.mark.parametrize('field,value', [('progress',2), ('elapsed',12), ('learned',True), ('shared',True), ('last_year',9999), ('status','completed')])
def test_schema_rejects_forged_progress(site, field, value):
    start(site)
    game = load(site)
    survey.get(game)[field] = value
    with pytest.raises(ValueError):
        validate_state(game.heavens_state)


def test_legacy_ruins_and_invalid_membership(site):
    game, identity = ready(site)
    assert 'survey' not in game.heavens_state['runtime']['ruins']
    validate_state(game.heavens_state)
    scene = game.spatial_state['instances'][game.heavens_state['runtime']['ruins']['scene_id']]
    scene['npc_ids'] = [identity]
    with pytest.raises(ValueError):
        validate_references(game)


@pytest.mark.parametrize('field,value', [('affinity',19), ('realm_index',3), ('realm_index',6), ('world','demon'), ('faction_id','sect-duty')])
def test_candidates_require_real_qualified_free_resident(site, field, value):
    game, identity = ready(site)
    setattr(game.world_npcs[identity], field, value)
    site[0].store.save(game)
    assert identity not in {p['id'] for p in site[2].survey_candidates(game)}
    with pytest.raises(ValueError):
        act(site, 'survey_start', person_id=identity)


def test_study_meeting_and_occupancy(site):
    _, identity = start(site)
    wait(site, 2)
    act(site, 'ruins_enter')
    engine, initial, _ = site
    game = load(site)
    from cultivation_life.spatial_people import accessible
    assert accessible(game, game.world_npcs[identity])
    engine.contact_action(initial.id, identity, 'improve')
    with pytest.raises(ValueError):
        engine.manage_dao_friend(initial.id, identity, 'befriend')
    scene = game.spatial_state['instances'][game.heavens_state['runtime']['ruins']['scene_id']]
    scene['npc_ids'] = []
    with pytest.raises(ValueError):
        validate_references(game)


def test_failed_arrival_save_does_not_move_original(site, monkeypatch):
    _, identity = start(site)
    wait(site, 1)
    engine, initial, _ = site
    disk = engine.store._path(initial.id).read_bytes()
    save = engine.store.save
    monkeypatch.setattr(engine.store, 'save', Mock(side_effect=OSError('full')))
    with pytest.raises(OSError):
        wait(site, 1)
    assert engine.store._path(initial.id).read_bytes() == disk
    monkeypatch.setattr(engine.store, 'save', save)
    assert wait(site, 1).world_npcs[identity].world == 'rift'
