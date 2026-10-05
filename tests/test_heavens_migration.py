"""Real residents, finite civilian settlement, occupancy and atomic persistence."""
import copy
from dataclasses import replace
from unittest.mock import Mock

import pytest

from cultivation_life.content_registry import WORLD_SYSTEMS
from cultivation_life.models import GameState, SectNpc
from cultivation_life.npc_custody import detain_person, release_person
from cultivation_life.person_assignments import research_assignment, route_occupied
from cultivation_life.runtime import decode_rng
from cultivation_life.system.heavens import operations
from cultivation_life.system.heavens.definitions import CONTACT_SITES, VISIT_DESTINATIONS, default_site
from cultivation_life.system.heavens.schema import validate_state, validate_references
from cultivation_life.system.heavens.state import get_echo
from cultivation_life.system.npc_contacts import availability
from test_heavens_m1 import local, issue
from test_heavens_missions import prepared, wait
from test_heavens_visits import stones


def ready(local, site=CONTACT_SITES[0], *, abroad=False, visitor=False):
    game = prepared(local, site, abroad=abroad)
    echo = get_echo(game.heavens_state['runtime'], site.id)
    npc = copy.deepcopy(game.world_npcs[echo['visitor_id']])
    if not visitor:
        npc.id, npc.name = 'resident-'+site.id, '当地居民'
    npc.affinity, npc.encountered_player = 30, True
    game.world_npcs[npc.id] = npc
    local[0].store.save(game)
    return game, npc.id


def start(local, identity, site=CONTACT_SITES[0]):
    return issue(local, 'migration_start', {'person_id': identity}, target=site.id)


@pytest.mark.parametrize('site', CONTACT_SITES, ids=lambda s:s.world)
def test_real_resident_settles_without_replacing_visitor(local, site):
    before, identity = ready(local, site)
    engine, initial, deps = local
    disk = engine.store._path(initial.id).read_bytes()
    view = operations.project(before, 'known', site.id, deps=deps)
    assert identity in {row['id'] for row in view['migration']['candidates']}
    quote = operations.preview(deps, initial.id, 'migration_start', site.id, {'person_id':identity})
    assert quote['project_cost'] == 4000 and quote['years'] == 0
    assert engine.store._path(initial.id).read_bytes() == disk
    result = start(local, identity, site)
    assert operations.command(deps, initial.id, result['command_seq'], before.heavens_state['revision'],
                              'migration_start', site.id, {'person_id':identity}) == result
    moving = wait(local, 1, site.id)
    assert moving.world_npcs[identity].world == site.world and engine._find_npc(moving, identity) is None
    destination = default_site(VISIT_DESTINATIONS[site.id])
    assert route_occupied(moving, site.world, destination.world)
    arrived = wait(local, 1, site.id)
    echo = get_echo(arrived.heavens_state['runtime'], site.id)
    assert echo['migration']['phase'] == 'settling' and echo['migration']['spent'] == 2000
    assert arrived.world_npcs[identity].world == destination.world
    assert arrived.world_npcs[echo['visitor_id']].world == site.world
    assert deps.person_available(arrived, echo['visitor_id'])
    assert not route_occupied(arrived, site.world, destination.world)
    with pytest.raises(ValueError, match='尚未抵达'):
        issue(local, 'migration_cancel', target=site.id)
    settled = wait(local, 1, site.id)
    row = get_echo(settled.heavens_state['runtime'], site.id)['migration']
    assert row['status'] == 'completed' and row['spent'] == 4000 and row['refunded'] == 0
    assert get_echo(settled.heavens_state['runtime'], site.id)['project_stones'] == 13500
    assert not research_assignment(settled, identity)
    assert settled.world_npcs[identity].age == before.world_npcs[identity].age+3
    assert stones(settled) == stones(before) and settled.player.opportunity == before.player.opportunity
    assert set(settled.world_npcs) == set(before.world_npcs)
    assert GameState.from_dict(settled.to_dict()).to_dict() == settled.to_dict()
    with pytest.raises(ValueError, match='一次'):
        start(local, identity, site)
    # Normal years after settlement do not impose a return or repeat the grant.
    engine._advance_world_year(settled, decode_rng(settled.seed, settled.rng_state), [], encounters=False)
    assert settled.world_npcs[identity].world == destination.world


def test_actual_destination_contact_during_settling_then_normal_relationship(local):
    game, identity = ready(local, abroad=True)
    start(local, identity)
    game = wait(local, 2)
    engine, initial, _ = local
    assert availability(game, game.world_npcs[identity])['improve'] == ''
    engine.contact_action(initial.id, identity, 'improve')
    with pytest.raises(ValueError):
        engine.manage_dao_friend(initial.id, identity, 'befriend')
    settled = wait(local, 1)
    assert not research_assignment(settled, identity)
    assert availability(settled, settled.world_npcs[identity])['improve'] == ''


def test_cancel_after_one_year_refunds_project_without_moving(local):
    before, identity = ready(local)
    start(local, identity)
    wait(local, 1)
    issue(local, 'migration_cancel')
    game = local[0].store.load(local[1].id)
    echo = get_echo(game.heavens_state['runtime'])
    assert echo['migration']['refunded'] == 3000 and echo['project_stones'] == 16500
    assert game.world_npcs[identity].world == 'celestial' and stones(game) == stones(before)
    assert not research_assignment(game, identity)


@pytest.mark.parametrize('field,value', [('affinity',None), ('affinity',19), ('realm_index',8), ('faction_id','busy'), ('location_id','away'), ('alive',False)])
def test_requires_real_local_free_willing_person(local, field, value):
    game, identity = ready(local)
    setattr(game.world_npcs[identity], field, value)
    local[0].store.save(game)
    candidates = local[2].migration_candidates(game, 'sea_echo')
    assert identity not in {r['id'] for r in candidates}
    with pytest.raises(ValueError):
        start(local, identity)


def test_missing_permit_and_closed_route_pause_without_spending(local, monkeypatch):
    game, identity = ready(local)
    route = next(r for r in WORLD_SYSTEMS['world_transition_routes'] if r['id']=='study:celestial:reincarnation')
    monkeypatch.setitem(route, 'civilian_residency', False)
    with pytest.raises(ValueError, match='通道'):
        start(local, identity)
    monkeypatch.setitem(route, 'civilian_residency', True)
    start(local, identity)
    monkeypatch.setitem(route, 'enabled', False)
    paused = wait(local, 1)
    row = get_echo(paused.heavens_state['runtime'])['migration']
    assert row['spent'] == row['progress'] == 0
    issue(local, 'migration_cancel')


def test_captivity_pauses_then_release_allows_settlement(local):
    game, identity = ready(local)
    start(local, identity)
    game = wait(local, 1)
    detain_person(game, {'id':identity}, SectNpc)
    local[0].store.save(game)
    game = wait(local, 2)
    assert get_echo(game.heavens_state['runtime'])['migration']['spent'] == 1000
    with pytest.raises(ValueError, match='恢复自由'):
        issue(local, 'migration_cancel')
    release_person(game, identity)
    local[0].store.save(game)
    assert get_echo(wait(local, 2).heavens_state['runtime'])['migration']['status'] == 'completed'


@pytest.mark.parametrize('years', [2,3])
def test_real_lifespan_death_precedes_arrival_or_settlement(local, years):
    game, identity = ready(local)
    npc = game.world_npcs[identity]
    npc.lifespan = npc.age+years
    local[0].store.save(game)
    start(local, identity)
    saved = wait(local, years)
    row = get_echo(saved.heavens_state['runtime'])['migration']
    assert row['status'] == 'failed' and row['spent'] == (years-1)*1000
    assert row['refunded'] == 4000-row['spent'] and not saved.world_npcs[identity].alive
    assert saved.world_npcs[identity].world == ('celestial' if years==2 else 'reincarnation')


def test_isolation_and_duplicate_year_do_not_advance_twice(local):
    game, identity = ready(local)
    start(local, identity)
    engine, initial, deps = local
    game = engine.store.load(initial.id)
    before = copy.deepcopy(get_echo(game.heavens_state['runtime'])['migration'])
    game.player.world = 'rift'
    engine._advance_world_year(game, decode_rng(game.seed, game.rng_state), [], encounters=False)
    assert get_echo(game.heavens_state['runtime'])['migration'] == before
    game = engine.store.load(initial.id)
    deps.advance_researchers(game)
    once = copy.deepcopy(game.heavens_state)
    deps.advance_researchers(game)
    assert game.heavens_state == once


def test_arrival_save_failure_rolls_back_world_age_and_budget(local, monkeypatch):
    _, identity = ready(local)
    start(local, identity)
    wait(local, 1)
    engine, initial, _ = local
    disk = engine.store._path(initial.id).read_bytes()
    save = engine.store.save
    monkeypatch.setattr(engine.store, 'save', Mock(side_effect=OSError('full')))
    with pytest.raises(OSError):
        wait(local, 1)
    assert engine.store._path(initial.id).read_bytes() == disk
    monkeypatch.setattr(engine.store, 'save', save)
    assert wait(local, 1).world_npcs[identity].world == 'reincarnation'


@pytest.mark.parametrize('key,value', [('progress',2),('spent',1),('refunded',1),('destination','sea_echo'),('person_id',''),('status','completed')])
def test_corrupt_migration_rejected(local, key, value):
    _, identity = ready(local)
    start(local, identity)
    game = local[0].store.load(local[1].id)
    get_echo(game.heavens_state['runtime'])['migration'][key] = value
    with pytest.raises(ValueError):
        validate_state(game.heavens_state)


def test_missing_resident_reference_rejected(local):
    _, identity = ready(local)
    start(local, identity)
    game = local[0].store.load(local[1].id)
    game.world_npcs.pop(identity)
    with pytest.raises(ValueError, match='权威引用'):
        validate_references(game)


def test_moving_original_visitor_removes_source_cooperation(local):
    _, identity = ready(local, visitor=True)
    start(local, identity)
    game = wait(local, 3)
    assert not local[2].person_available(game, identity)
    assert game.world_npcs[identity].world == 'reincarnation'


def test_closed_route_after_arrival_does_not_prevent_local_settlement(local, monkeypatch):
    _, identity = ready(local)
    start(local, identity)
    wait(local, 2)
    route = next(r for r in WORLD_SYSTEMS['world_transition_routes'] if r['id']=='study:celestial:reincarnation')
    monkeypatch.setitem(route, 'enabled', False)
    game = wait(local, 1)
    assert get_echo(game.heavens_state['runtime'])['migration']['status'] == 'completed'


def test_registration_save_failure_and_generation_switch(local):
    _, identity = ready(local)
    engine, initial, deps = local
    disk = engine.store._path(initial.id).read_bytes()
    broken = replace(deps, get_store=lambda: Mock(save=Mock(side_effect=OSError('full'))))
    with pytest.raises(OSError):
        start((engine, initial, broken), identity)
    assert engine.store._path(initial.id).read_bytes() == disk
    start(local, identity)
    game = engine.store.load(initial.id)
    game.heavens_state['generation_enabled'] = False
    engine.store.save(game)
    assert get_echo(wait(local, 3).heavens_state['runtime'])['migration']['status'] == 'completed'


def test_resident_cannot_be_enlisted_or_assigned_a_second_trip(local):
    _, identity = ready(local)
    start(local, identity)
    engine, initial, _ = local
    game = engine.store.load(initial.id)
    npc = game.world_npcs[identity]
    assert identity not in {p.id for p in engine._war_side_members(game, 'race', npc.race, npc.world)}
    with pytest.raises(ValueError):
        engine.manage_party(initial.id, identity, 'invite')
    with pytest.raises(ValueError, match='已有同道行程'):
        issue(local, 'mission_start')


def test_same_person_cannot_receive_second_world_settlement(local):
    _, identity = ready(local)
    start(local, identity)
    wait(local, 3)
    destination = default_site(VISIT_DESTINATIONS['sea_echo'])
    ready(local, destination)
    with pytest.raises(ValueError, match='已使用过迁居'):
        start(local, identity, destination)
