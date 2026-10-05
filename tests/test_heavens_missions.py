"""Authoritative civilian NPC trips, shared occupancy, escrow and ordinary years."""
import copy
from dataclasses import replace
from unittest.mock import Mock

import pytest

from cultivation_life.content_registry import WORLD_SYSTEMS
from cultivation_life.models import GameState, SectNpc
from cultivation_life.npc_custody import detain_person, release_person
from cultivation_life.person_assignments import research_assignment
from cultivation_life.runtime import decode_rng
from cultivation_life.system.heavens import operations
from cultivation_life.system.heavens.definitions import CONTACT_SITES, VISIT_DESTINATIONS, default_site
from cultivation_life.system.heavens.schema import validate_state
from cultivation_life.system.heavens.state import get_echo
from cultivation_life.system.npc_contacts import availability
from test_heavens_m1 import local, quiet, issue
from test_heavens_visits import ready, stones


def prepared(local, site=CONTACT_SITES[0], *, abroad=False):
    ready(local, site)
    for action in ('visit_depart', 'visit_study') + (() if abroad else ('visit_return',)):
        issue(quiet(local), action, target=site.id)
    engine, initial, deps = local
    game = engine.store.load(initial.id)
    npc = game.world_npcs[get_echo(game.heavens_state['runtime'], site.id)['visitor_id']]
    npc.next_tribulation_age = 999999
    engine.store.save(game)
    return game


def wait(local, count, target='sea_echo'):
    for _ in range(count):
        issue(local, 'mission_wait', target=target)
    return local[0].store.load(local[1].id)


@pytest.mark.parametrize('site', CONTACT_SITES, ids=lambda s:s.world)
def test_four_real_npc_roundtrips_keep_identity_and_exact_budget(local, site):
    before = prepared(local, site)
    engine, initial, deps = local
    identity = get_echo(before.heavens_state['runtime'], site.id)['visitor_id']
    npc_before = before.world_npcs[identity]
    data = engine.store._path(initial.id).read_bytes()
    proposal = operations.preview(deps, initial.id, 'mission_start', site.id, {})
    assert proposal['project_cost'] == 6000 and proposal['costs'] == {}
    operations.project(before, 'known', site.id, deps=deps)
    assert engine.store._path(initial.id).read_bytes() == data
    result = issue(local, 'mission_start', target=site.id)
    start = engine.store.load(initial.id)
    assert start.player.age == before.player.age and stones(start) == stones(before)
    assert operations.command(deps, initial.id, result['command_seq'], before.heavens_state['revision'],
                              'mission_start', site.id, {}) == result
    assert get_echo(start.heavens_state['runtime'], site.id)['project_stones'] == 11500
    travel = wait(local, 1, site.id)
    assert travel.world_npcs[identity].world == site.world
    assert engine._find_npc(travel, identity) is None
    assert all(availability(travel, travel.world_npcs[identity]).values())
    arrived = wait(local, 1, site.id)
    destination = default_site(VISIT_DESTINATIONS[site.id])
    npc = arrived.world_npcs[identity]
    assert (npc.world,npc.location_id) == (destination.world,destination.location_id)
    assert npc.age == npc_before.age+2 and npc.id == identity
    arrival = next(r for r in arrived.heavens_state['runtime']['history'] if '已经实际抵达' in r['text'])
    assert arrival['year'] == arrived.heavens_state['runtime']['processed_years']
    assert arrived.player.world == site.world
    returned = wait(local, 6, site.id)
    echo = get_echo(returned.heavens_state['runtime'], site.id)
    mission = echo['mission']
    assert mission['status'] == 'completed' and mission['studied']
    assert mission['spent'] == 6000 and mission['refunded'] == 0 and echo['project_stones'] == 11500
    assert returned.world_npcs[identity].world == site.world and returned.world_npcs[identity].age == npc_before.age+8
    assert returned.player.age == before.player.age+8 and stones(returned) == stones(before)
    assert returned.player.opportunity == before.player.opportunity
    assert returned.heavens_state['runtime']['history'][-1]['year'] == returned.heavens_state['runtime']['processed_years']
    assert set(returned.world_npcs) == set(before.world_npcs)
    assert not research_assignment(returned, identity)
    assert GameState.from_dict(returned.to_dict()).to_dict() == returned.to_dict()
    with pytest.raises(ValueError, match='一次'):
        issue(local,'mission_start',target=site.id)


def test_can_meet_actual_researcher_but_not_redeploy_them(local):
    prepared(local, abroad=True)
    engine, initial, deps = local
    issue(local,'mission_start')
    game = wait(local,2)
    npc = game.world_npcs[get_echo(game.heavens_state['runtime'])['visitor_id']]
    assert engine._find_npc(game,npc.id) is npc
    assert availability(game,npc)['improve'] == ''
    before = npc.affinity
    engine.contact_action(initial.id,npc.id,'improve')
    saved = engine.store.load(initial.id)
    assert saved.world_npcs[npc.id].affinity > before
    for run in (
        lambda: engine.manage_party(initial.id,npc.id,'invite'),
        lambda: engine.manage_dao_friend(initial.id,npc.id,'befriend'),
        lambda: engine.manage_dao_companion(initial.id,'propose',npc_id=npc.id),
        lambda: engine.manage_faction_relationship(initial.id,npc.id,'master'),
        lambda: engine.manage_concubine(initial.id,npc.id,'recruit'),
    ):
        with pytest.raises(ValueError, match='访学'):
            run()
    assert npc.id not in {p.id for p in engine._war_side_members(saved,'race',npc.race,npc.world)}
    saved.player.location_id = 'samsara_river'
    # Availability also requires the exact reception site, not just world equality.
    assert availability(saved,saved.world_npcs[npc.id])['improve']


@pytest.mark.parametrize('progress,spent', [(0,0),(1,1000),(2,4000),(4,5000)])
def test_early_recall_refunds_unused_project_funds_and_never_teleports(local, progress, spent):
    before = prepared(local)
    engine,initial,deps = local
    issue(local,'mission_start')
    game = wait(local,progress) if progress else engine.store.load(initial.id)
    identity = get_echo(game.heavens_state['runtime'])['visitor_id']
    world = game.world_npcs[identity].world
    issue(local,'mission_recall')
    game = engine.store.load(initial.id)
    assert game.world_npcs[identity].world == world
    if progress >= 2:
        game = wait(local,2)
    echo = get_echo(game.heavens_state['runtime'])
    assert echo['mission']['spent'] == spent and echo['mission']['refunded'] == 6000-spent
    assert echo['project_stones'] == 17500-spent and not echo['mission']['studied']
    assert stones(game) == stones(before)
    assert game.world_npcs[identity].world == 'celestial'


def test_closed_route_preserves_progress_resources_and_real_npc_age(local,monkeypatch):
    before = prepared(local)
    engine,initial,deps=local
    issue(local,'mission_start')
    game=wait(local,1)
    identity=get_echo(game.heavens_state['runtime'])['visitor_id']
    route=next(r for r in WORLD_SYSTEMS['world_transition_routes'] if r['id']=='study:celestial:reincarnation')
    monkeypatch.setitem(route,'enabled',False)
    paused=wait(local,2)
    mission=get_echo(paused.heavens_state['runtime'])['mission']
    assert mission['progress']==1 and mission['spent']==1000
    assert paused.world_npcs[identity].age==before.world_npcs[identity].age+3
    assert operations.project(paused,'known','sea_echo',deps=deps)['mission']['blocked_reason']
    monkeypatch.setitem(route,'enabled',True)
    resumed=wait(local,1)
    assert resumed.world_npcs[identity].world=='reincarnation'


def test_capture_and_release_preserve_same_identity_and_return_ticket(local):
    prepared(local,abroad=True)
    engine,initial,deps=local
    issue(local,'mission_start')
    game=wait(local,2)
    identity=get_echo(game.heavens_state['runtime'])['visitor_id']
    detain_person(game,{'id':identity},SectNpc)
    engine.store.save(game)
    paused=wait(local,2)
    mission=get_echo(paused.heavens_state['runtime'])['mission']
    assert mission['phase']=='studying' and mission['progress']==0 and mission['spent']==2000
    assert identity in paused.inactive_npcs and identity not in paused.world_npcs
    with pytest.raises(ValueError,match='接洽'):
        issue(local,'mission_recall')
    release_person(paused,identity)
    engine.store.save(paused)
    returned=wait(local,6)
    assert returned.world_npcs[identity].world=='celestial'
    assert get_echo(returned.heavens_state['runtime'])['mission']['status']=='completed'


def test_npc_death_refunds_project_once_without_replacement(local):
    prepared(local)
    engine,initial,deps=local
    issue(local,'mission_start')
    game=wait(local,1)
    identity=get_echo(game.heavens_state['runtime'])['visitor_id']
    game.world_npcs[identity].alive=False
    engine.store.save(game)
    ended=wait(local,1)
    echo=get_echo(ended.heavens_state['runtime'])
    assert echo['mission']['status']=='failed' and echo['project_stones']==16500
    assert echo['mission']['refunded']==5000 and not ended.world_npcs[identity].alive
    deps.advance_researchers(ended)
    assert echo['project_stones']==16500


def test_personal_return_reserved_before_npc_queue_does_not_deadlock(local):
    prepared(local,abroad=True)
    engine,initial,deps=local
    issue(local,'mission_start')
    game=wait(local,5)
    identity=get_echo(game.heavens_state['runtime'])['visitor_id']
    assert get_echo(game.heavens_state['runtime'])['mission']['progress']==3
    result=issue(local,'visit_return')
    assert result['status']=='completed'
    game=engine.store.load(initial.id)
    assert game.player.world=='celestial' and game.world_npcs[identity].world=='reincarnation'
    mission=get_echo(game.heavens_state['runtime'])['mission']
    assert mission['phase']=='returning' and mission['progress']==0
    returned=wait(local,2)
    assert returned.world_npcs[identity].world=='celestial'
    assert get_echo(returned.heavens_state['runtime'])['mission']['spent']==6000


def test_npc_reserved_lane_blocks_player_until_arrival(local):
    prepared(local,abroad=True)
    engine,initial,deps=local
    issue(local,'mission_start')
    wait(local,6)
    with pytest.raises(ValueError,match='通道'):
        issue(local,'visit_return')
    wait(local,2)
    assert issue(local,'visit_return')['status']=='completed'


def test_independent_space_and_early_personal_event_do_not_tick_outer_npc(local,monkeypatch):
    prepared(local)
    engine,initial,deps=local
    issue(local,'mission_start')
    game=engine.store.load(initial.id)
    identity=get_echo(game.heavens_state['runtime'])['visitor_id']
    before=copy.deepcopy(get_echo(game.heavens_state['runtime'])['mission'])
    # The engine's spatial annual branch owns only the player and local space.
    game.player.world='rift'
    engine._advance_world_year(game,decode_rng(game.seed,game.rng_state),[],encounters=False)
    assert get_echo(game.heavens_state['runtime'])['mission']==before
    assert game.world_npcs[identity].age==engine.store.load(initial.id).world_npcs[identity].age
    def interrupt(work,rng):
        work.pending_event={'id':'mission_test_event'}
    monkeypatch.setattr(engine,'_check_tribulation',interrupt)
    issue(local,'mission_wait')
    paused=engine.store.load(initial.id)
    assert get_echo(paused.heavens_state['runtime'])['mission']==before


def test_disabled_generation_and_daily_hook_idempotency(local):
    prepared(local)
    engine,initial,deps=local
    issue(local,'mission_start')
    game=engine.store.load(initial.id)
    game.heavens_state['generation_enabled']=False
    engine.store.save(game)
    returned=wait(local,8)
    assert get_echo(returned.heavens_state['runtime'])['mission']['status']=='completed'


def test_repeated_year_callback_is_deduplicated(local):
    prepared(local)
    engine,initial,deps=local
    issue(local,'mission_start')
    game=engine.store.load(initial.id)
    deps.advance_researchers(game)
    before=copy.deepcopy(get_echo(game.heavens_state['runtime'])['mission'])
    deps.advance_researchers(game)
    assert get_echo(game.heavens_state['runtime'])['mission']==before


def test_save_failure_rolls_back_project_and_occupancy(local,monkeypatch):
    prepared(local)
    engine,initial,deps=local
    before=engine.store._path(initial.id).read_bytes()
    monkeypatch.setattr(engine.store,'save',Mock(side_effect=OSError('full')))
    with pytest.raises(OSError):
        issue(local,'mission_start')
    assert engine.store._path(initial.id).read_bytes()==before


def test_arrival_save_failure_rolls_back_age_location_and_spending(local,monkeypatch):
    prepared(local)
    engine,initial,deps=local
    issue(local,'mission_start')
    wait(local,1)
    before=engine.store._path(initial.id).read_bytes()
    save=engine.store.save
    monkeypatch.setattr(engine.store,'save',Mock(side_effect=OSError('full')))
    with pytest.raises(OSError):
        issue(local,'mission_wait')
    assert engine.store._path(initial.id).read_bytes()==before
    monkeypatch.setattr(engine.store,'save',save)
    after=wait(local,1)
    echo=get_echo(after.heavens_state['runtime'])
    assert after.world_npcs[echo['visitor_id']].world=='reincarnation'
    assert echo['mission']['spent']==2000


def test_actual_lifespan_death_precedes_due_arrival(local):
    prepared(local)
    engine,initial,deps=local
    game=engine.store.load(initial.id)
    identity=get_echo(game.heavens_state['runtime'])['visitor_id']
    npc=game.world_npcs[identity]
    npc.lifespan=npc.age+2
    engine.store.save(game)
    issue(local,'mission_start')
    game=wait(local,2)
    echo=get_echo(game.heavens_state['runtime'])
    assert not game.world_npcs[identity].alive and game.world_npcs[identity].world=='celestial'
    assert echo['mission']['status']=='failed' and echo['mission']['spent']==1000


def test_cannot_spend_missing_project_budget_or_send_occupied_person(local):
    prepared(local)
    engine,initial,deps=local
    game=engine.store.load(initial.id)
    echo=get_echo(game.heavens_state['runtime'])
    echo['project_stones']=5999
    engine.store.save(game)
    with pytest.raises(ValueError,match='项目'):
        issue(local,'mission_start')
    echo['project_stones']=17500
    game.player.party=[{'id':echo['visitor_id']}]
    engine.store.save(game)
    with pytest.raises(ValueError,match='职责'):
        issue(local,'mission_start')
    assert 'mission' not in get_echo(engine.store.load(initial.id).heavens_state['runtime'])


def test_can_cancel_outbound_when_route_closes(local,monkeypatch):
    prepared(local)
    issue(local,'mission_start')
    wait(local,1)
    route=next(r for r in WORLD_SYSTEMS['world_transition_routes'] if r['id']=='study:celestial:reincarnation')
    monkeypatch.setitem(route,'enabled',False)
    issue(local,'mission_recall')
    echo=get_echo(local[0].store.load(local[1].id).heavens_state['runtime'])
    assert echo['mission']['status']=='cancelled' and echo['project_stones']==16500


@pytest.mark.parametrize('field,value',[('source','asura'),('destination','nether'),('mode','rift'),('research_visitors',False)])
def test_npc_permission_never_uses_wrong_route_or_generic_spatial_permission(local,monkeypatch,field,value):
    prepared(local)
    issue(local,'mission_start')
    route=next(r for r in WORLD_SYSTEMS['world_transition_routes'] if r['id']=='study:celestial:reincarnation')
    monkeypatch.setitem(route,field,value)
    game=wait(local,1)
    echo=get_echo(game.heavens_state['runtime'])
    assert echo['mission']['progress']==0 and echo['mission']['spent']==0
    assert game.world_npcs[echo['visitor_id']].world=='celestial'


@pytest.mark.parametrize('field,value',[('spent',6001),('refunded',1),('progress',2),('destination','asura_echo'),
    ('last_year',99999),('studied',True),('phase','other'),('elapsed',6)])
def test_invalid_ledger_or_route_is_rejected(local,field,value):
    prepared(local)
    issue(local,'mission_start')
    game=local[0].store.load(local[1].id)
    get_echo(game.heavens_state['runtime'])['mission'][field]=value
    with pytest.raises(ValueError,match='同道'):
        validate_state(game.heavens_state)
