"""Independent civilian decisions, actual encounters and bounded discovery."""
import copy
from dataclasses import replace
from hashlib import sha256
from unittest.mock import Mock

import pytest

from cultivation_life.models import GameState, SectNpc
from cultivation_life.runtime import decode_rng, encode_rng
from cultivation_life.system.heavens import autonomy, operations, survey
from cultivation_life.system.heavens.calendar import YearContext, year_step
from cultivation_life.system.heavens.schema import validate_state, validate_references
from cultivation_life.system.heavens.definitions import RUINS_ID
from test_heavens_m1 import local
from test_heavens_ruins import site, act, load
from test_heavens_survey import wait


def setup(site, *, success=True):
    game = load(site)
    game.seed = next(seed for seed in range(1000) if (int.from_bytes(sha256(
        f'{seed}:heavens:resident-survey:v1:1'.encode()).digest()[:8], 'big') < 2**62) == success)
    game.player.location_id = 'muling_desert'
    game.heavens_state['runtime'].update(processed_years=99, last_year_key=99)
    npc = SectNpc('independent-resident', '访古客', '', 4, 1, 80, 1000,
                  spirit_root='supreme_water', world='human', affinity=0,
                  location_id='wudi_plain', encountered_player=False)
    game.world_npcs = {npc.id:npc}
    site[0].store.save(game)
    return game, npc.id


def annual(site, count=1):
    engine, _, _ = site
    game = load(site)
    rng = decode_rng(game.seed, game.rng_state)
    for _ in range(count):
        game.player.age += 1
        engine._advance_world_year(game, rng, [], encounters=False)
    game.rng_state = encode_rng(rng)
    engine.store.save(game)
    return game


def enter(site):
    game = load(site)
    game.player.location_id = 'wudi_plain'
    site[0].store.save(game)
    act(site, 'ruins_enter')
    return load(site)


def test_independent_discovery_is_hidden_then_actual_meeting_and_exchange(site):
    before, identity = setup(site)
    game = annual(site)
    row = survey.get(game)
    assert row['autonomous'] and not row['introduced'] and row['elapsed'] == 0
    assert row['started_at'] == 100 and game.world_npcs[identity].age == 81
    assert game.player.world == 'human' and game.player.location_id == 'muling_desert'
    assert not game.heavens_state['runtime']['ruins']['player_known']
    assert not game.heavens_state['runtime']['history']
    view = operations.project(game, 'known', deps=site[2])
    assert view['ruins']['survey'] == dict(status='unmet',actions=[],candidates=[])
    assert not view['ruins']['known'] and 'core' not in view['ruins']
    assert all(r['id'] != RUINS_ID for r in view['records'])
    arrived = annual(site, 2)
    assert arrived.world_npcs[identity].world == 'rift'
    assert arrived.world_npcs[identity].age == before.world_npcs[identity].age + 3
    assert not arrived.heavens_state['runtime']['history']
    frozen = annual(site, 2)
    assert frozen.world_npcs[identity].age == arrived.world_npcs[identity].age
    met = enter(site)
    assert survey.get(met)['introduced'] and met.heavens_state['runtime']['ruins']['player_known']
    assert not met.heavens_state['runtime']['ruins']['observed']
    assert len(met.heavens_state['runtime']['history']) == 2
    with pytest.raises(ValueError, match='交情'):
        act(site, 'survey_recall')
    learned = wait(site, 8)
    assert survey.get(learned)['learned'] and not survey.get(learned)['shared']
    with pytest.raises(ValueError, match='交情'):
        act(site, 'survey_share')
    learned.world_npcs[identity].affinity = 20
    site[0].store.save(learned)
    act(site, 'survey_share')
    done = wait(site, 1)
    assert done.world_npcs[identity].world == 'human' and survey.get(done)['status'] == 'completed'
    assert done.player.formation_materials == [] and len(done.world_npcs) == 1
    assert GameState.from_dict(done.to_dict()).to_dict() == done.to_dict()


def test_window_and_queries_do_not_reroll_or_draw_existing_rng(site):
    game, identity = setup(site)
    baseline = copy.deepcopy(game.to_dict())
    for _ in range(4):
        operations.project(game, 'known', deps=site[2])
    assert game.to_dict() == baseline
    autonomy.year_step(site[2], game)
    row = copy.deepcopy(survey.get(game))
    assert game.rng_state == baseline['rng_state']
    assert game.heavens_state['runtime']['rng_counter'] == baseline['heavens_state']['runtime']['rng_counter']
    for _ in range(4): autonomy.year_step(site[2], game)
    assert survey.get(game) == row and len(game.world_npcs) == 1
    year_step(site[2], game, YearContext(100))
    validate_state(game.heavens_state)
    validate_references(game)


@pytest.mark.parametrize('empty', [False, True])
def test_empty_or_failed_window_remains_spent_after_reload(site, empty):
    game, identity = setup(site, success=empty)
    if empty:
        game.world_npcs[identity].faction_id = 'unavailable-duty'
    site[0].store.save(game)
    game = annual(site)
    assert not survey.get(game) and game.heavens_state['runtime']['survey_discovery_window'] == 1
    game.world_npcs[identity].faction_id = None
    site[0].store.save(game)
    assert not survey.get(annual(site, 1))


@pytest.mark.parametrize('gate', ['setting', 'content', 'space', 'early'])
def test_discovery_gates_never_create_a_scene(site, gate):
    game, _ = setup(site)
    deps = site[2]
    if gate == 'setting': game.heavens_state['generation_enabled'] = False
    if gate == 'content': deps = replace(deps, get_definitions=lambda:replace(site[2].get_definitions(),generation_available=False))
    if gate == 'space': game.player.world = 'rift'
    if gate == 'early': game.heavens_state['runtime'].update(processed_years=98,last_year_key=98)
    before = copy.deepcopy(game.to_dict())
    autonomy.year_step(deps, game)
    assert game.to_dict() == before


def test_real_spatial_year_does_not_start_external_discovery(site):
    setup(site)
    from test_heavens_m1 import issue
    issue(site, 'mirror_enter', target='mirror_field')
    issue(site, 'mirror_probe', target='mirror_field')
    assert not survey.get(load(site))
    assert 'survey_discovery_window' not in load(site).heavens_state['runtime']


@pytest.mark.parametrize('before_discovery', [False, True])
def test_natural_death_precedes_discovery_and_no_replacement_after_death(site, before_discovery):
    game, identity = setup(site)
    if before_discovery:
        game.world_npcs[identity].lifespan = 81
        site[0].store.save(game)
        dead = annual(site)
        assert not dead.world_npcs[identity].alive and not survey.get(dead)
        return
    discovered = annual(site)
    discovered.world_npcs[identity].lifespan = discovered.world_npcs[identity].age+1
    site[0].store.save(discovered)
    failed = annual(site)
    assert survey.get(failed)['status'] == 'failed'
    assert failed.heavens_state['runtime']['history'] == []
    row = copy.deepcopy(survey.get(failed))
    assert survey.get(annual(site, 1)) == row


def test_known_ruin_keeps_manual_invitation_and_existing_reward(site):
    game, identity = setup(site)
    enter(site)
    act(site, 'ruins_leave')
    game = load(site)
    game.world_npcs[identity].affinity = 30
    site[0].store.save(game)
    act(site, 'survey_start',person_id=identity)
    row = copy.deepcopy(survey.get(load(site)))
    game = annual(site)
    assert not survey.get(game).get('autonomous')
    assert survey.get(game)['person_id'] == row['person_id']
    assert 'survey_discovery_window' not in game.heavens_state['runtime']


def test_generation_disabled_retains_real_trip_and_cannot_remote_recall(site):
    setup(site)
    game = annual(site)
    identity = survey.get(game)['person_id']
    # The player actually meets the independent traveler at the departure site.
    game.player.location_id = 'wudi_plain'
    game.heavens_state['generation_enabled'] = False
    site[0].store.save(game)
    met = annual(site)
    assert survey.get(met)['introduced'] and met.heavens_state['runtime']['ruins']['player_known']
    assert survey.get(annual(site))['phase'] == 'studying'
    game = load(site)
    game.world_npcs[identity].affinity = 30
    site[0].store.save(game)
    with pytest.raises(ValueError,match='实际会面'):
        act(site,'survey_recall')
    enter(site)
    act(site,'survey_recall')
    assert survey.get(wait(site,1))['status'] == 'completed'


@pytest.mark.parametrize('kind', ['window', 'origin', 'introduced', 'visibility'])
def test_corrupt_autonomy_rejected(site, kind):
    setup(site)
    game = annual(site)
    row = survey.get(game)
    if kind == 'window': game.heavens_state['runtime']['survey_discovery_window'] = 2
    if kind == 'origin': row['autonomous'] = False
    if kind == 'introduced': row['introduced'] = 1
    if kind == 'visibility': game.heavens_state['runtime']['ruins']['observed'] = True
    with pytest.raises(ValueError): validate_state(game.heavens_state)


def test_command_save_failure_rolls_back_autonomous_discovery(site):
    game, identity = setup(site)
    # A normal action unit crosses the autonomous decision boundary.
    game.player.location_id = 'wudi_plain'
    site[0].store.save(game)
    engine, initial, deps = site
    act(site,'ruins_enter')
    act(site,'ruins_leave')
    # Use a normal yearly action through the public advancement transaction.
    # Normalize the deliberately minimal test roster before fault injection;
    # otherwise a legacy roster repair could fail before the actual action.
    engine._load(initial.id)
    engine._load(initial.id)
    disk = engine.store._path(initial.id).read_bytes()
    from unittest.mock import patch
    def fail_save(work):
        assert survey.get(work)['autonomous']
        raise OSError('full')
    with patch.object(engine.store,'save',fail_save):
        with pytest.raises(OSError): engine.advance(initial.id,'rest',1)
    assert engine.store._path(initial.id).read_bytes() == disk


@pytest.mark.parametrize('reason', ['death', 'event'])
def test_early_year_interrupt_cannot_run_npc_discovery(site, reason):
    game, identity = setup(site)
    if reason == 'death':
        game.player.lifespan = game.player.age+1
    else:
        game.pending_event = {'id':'test-interruption', 'title':'测试中断', 'body':'请先处理', 'choices':[]}
    site[0].store.save(game)
    stopped = annual(site)
    assert not survey.get(stopped)
    assert 'survey_discovery_window' not in stopped.heavens_state['runtime']
    assert stopped.world_npcs[identity].age == game.world_npcs[identity].age


def test_custody_and_player_relationships_are_not_autonomous_candidates(site):
    game, identity = setup(site)
    from cultivation_life.npc_custody import detain_person, release_person
    npc=game.world_npcs[identity]
    detain_person(game,npc.to_dict(),SectNpc)
    assert site[2].survey_candidates(game,autonomous=True)==[]
    release_person(game,identity)
    game.player.party=[{'id':identity,'npc_id':identity}]
    assert site[2].survey_candidates(game,autonomous=True)==[]


def test_empty_windows_scan_once_without_catching_up_skipped_centuries(site):
    game, _ = setup(site)
    candidates=Mock(return_value=[])
    deps=replace(site[2],survey_candidates=candidates)
    autonomy.year_step(deps,game)
    autonomy.year_step(deps,game)
    assert candidates.call_count==1
    game.heavens_state['runtime'].update(processed_years=9999,last_year_key=9999)
    autonomy.year_step(deps,game)
    # At most the one current window, never the 99 missed opportunities.
    assert candidates.call_count<=2
    assert game.heavens_state['runtime']['survey_discovery_window']==100


@pytest.mark.parametrize('blocked', ['dead', 'event', 'held'])
def test_player_must_be_available_for_an_actual_introduction(site, blocked):
    setup(site)
    game=annual(site)
    game.player.location_id='wudi_plain'
    if blocked=='dead': game.player.alive=False
    elif blocked=='event': game.pending_event={'id':'interruption'}
    else: game.player.imprisonment={'remaining_years':1}
    before=copy.deepcopy(game.heavens_state)
    survey.reveal(site[2],game)
    assert game.heavens_state==before


@pytest.mark.parametrize('changed', ['world', 'rank', 'location'])
def test_autonomous_departure_ends_when_original_qualification_is_lost(site, changed):
    setup(site)
    game=annual(site)
    identity=survey.get(game)['person_id']
    npc=game.world_npcs[identity]
    if changed=='world': npc.world='spirit'
    elif changed=='rank': npc.realm_index=3
    else: npc.location_id='muling_desert'
    original=(npc.world,npc.location_id)
    site[0].store.save(game)
    stopped=annual(site)
    assert survey.get(stopped)['status']=='cancelled' and survey.get(stopped)['elapsed']==0
    from cultivation_life.person_assignments import research_assignment
    assert not research_assignment(stopped,identity)
    assert (stopped.world_npcs[identity].world,stopped.world_npcs[identity].location_id)==original


def test_catalog_resident_survives_public_reload_without_duplicate_or_relocation(site):
    game=load(site)
    game.seed=next(seed for seed in range(1000) if int.from_bytes(sha256(
        f'{seed}:heavens:resident-survey:v1:1'.encode()).digest()[:8],'big')<2**62)
    game.heavens_state['runtime'].update(processed_years=99,last_year_key=99)
    original=set(game.world_npcs)
    site[0].store.save(game)
    arrived=annual(site,3)
    identity=survey.get(arrived)['person_id']
    assert identity in original and arrived.world_npcs[identity].world=='rift'
    for _ in range(3):
        loaded=site[0]._load(game.id)
        assert set(loaded.world_npcs)==original
        assert loaded.world_npcs[identity].world=='rift'
        assert survey.get(loaded)['person_id']==identity
