"""M3 round one: authority, unique deployment, visible evidence and safe return."""
import copy
from dataclasses import replace
from unittest.mock import Mock, patch

import pytest

from test_heavens_m1 import local
from test_heavens_ruins import site, act, prepared, load
from cultivation_life.models import GameState
from cultivation_life.content_registry import FACTION_SYSTEMS
from cultivation_life.person_assignments import deployment_assignment, require_unassigned
from cultivation_life.system.heavens import frontier, operations
from cultivation_life.system.heavens.calendar import year_step, YearContext
from cultivation_life.system.heavens.frontier_definitions import FRONTIER_ID, ROUTE, INITIAL_RESERVE
from cultivation_life.system.heavens.schema import validate_state


def tick(site, count=1):
    engine, game, deps = site
    work = load(site)
    for _ in range(count):
        work.player.age += 1
        frontier.year_step(deps, work)
        year_step(deps, work, YearContext(work.heavens_state['runtime']['last_year_key']+1))
    engine.store.save(work)
    return work


def issue(site, action, target=FRONTIER_ID):
    engine, game, deps = site
    state = load(site).heavens_state
    return operations.command(deps, game.id, state['command_seq']+1, state['revision'], action, target, {})


@pytest.fixture
def ready(site):
    engine, game, deps = site
    def advance(work, rng, news):
        if not work.spatial_state.get('current'):
            frontier.year_step(deps, work)
        year_step(deps, work, YearContext(work.heavens_state['runtime']['last_year_key']+1))
        return True
    deps = replace(deps, advance_year=advance, settle_activity_units=Mock())
    site = engine, game, deps
    prepared(site)
    act(site, 'ruins_contact')
    act(site, 'ruins_leave')
    tick(site, 10)
    return site


def start(ready):
    issue(ready, 'frontier_inquire')
    return tick(ready)


def arrive(ready):
    start(ready)
    for _ in range(80):
        work = load(ready)
        if frontier.get(work)['phase'] == 'scouting':
            work.player.location_id = ROUTE.destination_location
            ready[0].store.save(work)
            return work
        tick(ready)
    raise AssertionError('No actual arrival')


def test_full_peaceful_reconnaissance_and_single_ownership(ready):
    before = load(ready)
    work = arrive(ready)
    row = frontier.get(work)
    identity = row['person_id']
    npc = work.world_npcs[identity]
    assert npc.world == 'human' and npc.location_id == 'lanjiang_steppe'
    assert npc.faction_id == 'blood_prison'
    assert all(n.id != identity for s in work.sects.values() for n in s.npcs)
    assert len(work.world_npcs)+sum(len(s.npcs) for s in work.sects.values()) == len(before.world_npcs)+sum(len(s.npcs) for s in before.sects.values())
    assert row['authorization']['scope'] == 'recon_only' and row['authorization']['capacity'] == 1
    assert row['road'][0] == row['home'] and row['road'][-1] == 'red_marrow_city'
    with pytest.raises(ValueError): require_unassigned(work, identity)
    issue(ready, 'frontier_scout')
    issue(ready, 'frontier_parley')
    returning = load(ready)
    assert frontier.get(returning)['phase'] == 'returning' and returning.world_npcs[identity].world == 'human'
    for _ in range(80):
        work = tick(ready)
        if frontier.get(work)['status'] != 'active': break
    row = frontier.get(work)
    assert row['status'] == 'completed'
    assert work.world_npcs[identity].world == 'demon' and work.world_npcs[identity].location_id == row['home']
    assert row['budget']['spent']+row['budget']['refunded'] == INITIAL_RESERVE
    assert not deployment_assignment(work, identity)
    assert not work.wars and not work.heavens_state['runtime'].get('gates')
    assert GameState.from_dict(work.to_dict()).to_dict() == work.to_dict()
    with pytest.raises(ValueError): issue(ready, 'frontier_inquire')


def test_preview_directory_and_distant_reports_do_not_leak_or_write(ready):
    start(ready)
    work = load(ready)
    before = ready[0].store._path(work.id).read_bytes()
    public = operations.view(ready[2], work.id, 'known', FRONTIER_ID)['frontier']
    assert set(public) <= {'id','name','known','reports','actions','observed','reported','local'}
    assert not public['local'] and not public['observed']
    assert all(word not in str(public) for word in ['bp_', 'budget', 'expires_at', 'road_years'])
    operations.preview(ready[2], work.id, 'frontier_wait', FRONTIER_ID, {})
    assert ready[0].store._path(work.id).read_bytes() == before


def test_local_projection_does_not_initialize_political_state(ready):
    work = arrive(ready)
    work.intrigue_state = {}
    before = copy.deepcopy(work.to_dict())
    frontier.project(ready[2],work)
    assert work.to_dict() == before


def test_passive_ruins_and_returned_core_never_automatically_create_expedition(ready):
    work = tick(ready, 150)
    assert frontier.get(work) is None
    assert not work.wars


@pytest.mark.parametrize('block', ['dead_leader', 'player_controller', 'extinct', 'no_scout', 'old_war', 'funding'])
def test_approval_requires_actual_issuer_available_scout_and_bounded_budget(ready, block):
    work = load(ready)
    sect = work.sects['blood_prison']
    if block == 'dead_leader':
        for n in sect.npcs: n.alive = False
    elif block == 'player_controller': work.intrigue_state.setdefault('factions', {})['sect:blood_prison'] = {'controller_id':'player'}
    elif block == 'extinct': sect.extinct = True
    elif block == 'no_scout':
        for n in sect.npcs: n.realm_index = 6
    elif block == 'old_war': work.wars = [dict(status='active',roster={'attacker':[n.id for n in sect.npcs]})]
    ready[0].store.save(work)
    if block == 'funding':
        original = ready[2].frontier_candidate
        ready = ready[0], ready[1], replace(ready[2], frontier_candidate=lambda game: dict(original(game), road_years=100))
    work = start(ready)
    assert frontier.get(work)['person_id'] is None
    work = tick(ready,2)
    assert frontier.get(work)['status'] == 'declined'
    assert frontier.get(work)['budget']['refunded'] == INITIAL_RESERVE


def test_authority_revocation_causes_real_return_without_teleport(ready):
    work = arrive(ready)
    row = frontier.get(work)
    identity = row['person_id']
    work.intrigue_state.setdefault('factions', {})['sect:blood_prison'] = {'controller_id':'player'}
    ready[0].store.save(work)
    work = tick(ready)
    assert frontier.get(work)['withdrawal']
    assert work.world_npcs[identity].world == 'human'
    work = tick(ready,ROUTE.crossing_years-1)
    assert work.world_npcs[identity].world == 'demon'


def test_custody_pauses_and_death_refunds_without_replacement(ready):
    work = arrive(ready)
    identity = frontier.get(work)['person_id']
    work.world_npcs[identity].roster_state = 'held'
    # The authoritative held roster flag blocks deployment independently of
    # whichever custody system owns the release operation.
    ready[0].store.save(work)
    spent = frontier.get(work)['budget']['spent']
    work = tick(ready,5)
    assert frontier.get(work)['budget']['spent'] == spent
    work.world_npcs[identity].alive = False
    ready[0].store.save(work)
    work = tick(ready)
    assert frontier.get(work)['status'] == 'failed' and not work.world_npcs[identity].alive
    assert frontier.get(work)['budget']['spent']+frontier.get(work)['budget']['refunded'] == INITIAL_RESERVE


def test_generation_off_keeps_existing_plan_and_isolation_does_not_catch_up(ready):
    work = start(ready)
    row = copy.deepcopy(frontier.get(work))
    work.heavens_state['generation_enabled'] = False
    for _ in range(20):
        year_step(ready[2], work, YearContext(work.heavens_state['runtime']['last_year_key']+1))
    assert frontier.get(work) == row
    ready[0].store.save(work)
    work = tick(ready)
    assert frontier.get(work)['budget']['spent'] == row['budget']['spent']+100


def test_annual_callback_is_idempotent_and_uses_no_legacy_rng(ready):
    work = start(ready)
    random = work.rng_state
    frontier.year_step(ready[2], work)
    first = copy.deepcopy(frontier.get(work))
    frontier.year_step(ready[2], work)
    assert frontier.get(work) == first and work.rng_state == random


@pytest.mark.parametrize('action', ['frontier_scout', 'frontier_report', 'frontier_parley'])
def test_personal_commands_cannot_operate_remotely_or_assume_collective_rights(ready, action):
    start(ready)
    with pytest.raises(ValueError): issue(ready, action)
    with pytest.raises(ValueError): operations.plan(ready[2].get_definitions(), action, FRONTIER_ID, {'commander':'player'})


def test_command_retry_and_failed_save_do_not_duplicate_person_or_budget(ready):
    state = load(ready).heavens_state
    args = (ready[1].id,state['command_seq']+1,state['revision'],'frontier_inquire',FRONTIER_ID,{})
    before = ready[0].store._path(ready[1].id).read_bytes()
    with patch.object(ready[0].store,'save',side_effect=OSError('disk full')):
        with pytest.raises(OSError): operations.command(ready[2], *args)
    assert ready[0].store._path(ready[1].id).read_bytes() == before
    result = operations.command(ready[2], *args)
    saved = ready[0].store._path(ready[1].id).read_bytes()
    assert operations.command(ready[2], *args) == result
    assert ready[0].store._path(ready[1].id).read_bytes() == saved


@pytest.mark.parametrize('damage', ['budget','scope','capacity','issuer','clock','phase','progress','evidence','report','road'])
def test_corrupt_campaigns_are_rejected(ready, damage):
    work = start(ready)
    row = frontier.get(work)
    if damage == 'budget': row['budget']['spent'] = INITIAL_RESERVE+100
    elif damage == 'scope': row['authorization']['scope'] = 'all_worlds'
    elif damage == 'capacity': row['authorization']['capacity'] = 32
    elif damage == 'issuer': row['authorization']['issuer_id'] = 'player'
    elif damage == 'clock': row['last_year'] += 100
    elif damage == 'phase': row['phase'] = 'invasion'
    elif damage == 'progress': row['progress'] = row['duration']+1
    elif damage == 'evidence': row['source_evidence'] = None
    elif damage == 'report': row['observed'] = True
    elif damage == 'road': row['road'][-1] = 'fake'
    with pytest.raises(ValueError): GameState.from_dict(work.to_dict())


def test_real_npc_annual_continues_once_after_registry_handoff(ready):
    work = start(ready)
    identity = frontier.get(work)['person_id']
    age = work.world_npcs[identity].age
    # Use the actual engine year and settlement, not the fast rule fixture.
    real = ready[0], ready[1], ready[0]._dependencies.heavens
    with patch.object(ready[0], '_advance_guixu_calendar', return_value=False):
        issue(real, 'frontier_wait')
    work = load(ready)
    assert work.world_npcs[identity].age == age+1
    assert frontier.get(work)['budget']['spent'] == 100
    assert all(n.id != identity for n in work.sects['blood_prison'].npcs)


def test_final_year_event_defers_inquiry_and_resume_does_not_repeat_time(ready):
    original = ready[2].advance_year
    calls = []
    def interrupt(work, rng, news):
        original(work,rng,news)
        calls.append(True)
        if len(calls) == 2: work.pending_event = {'id':'interrupt'}
        return not work.pending_event
    ready = ready[0], ready[1], replace(ready[2], advance_year=interrupt)
    result = issue(ready,'frontier_inquire')
    work = load(ready)
    assert result['status'] == 'paused' and frontier.get(work)['source_evidence'] is None
    age = work.player.age
    work.pending_event = None
    ready[0].store.save(work)
    result = issue(ready,'resume',result['task_id'])
    assert result['status'] == 'completed' and load(ready).player.age == age
    assert len(calls) == 2


def test_cancelling_unsent_inquiry_never_dispatches_or_credits_player(ready):
    def pause(work,rng,news):
        year_step(ready[2],work,YearContext(work.heavens_state['runtime']['last_year_key']+1))
        work.pending_event = {'id':'pause'}
        return False
    ready = ready[0], ready[1], replace(ready[2], advance_year=pause)
    result = issue(ready,'frontier_inquire')
    before = load(ready)
    issue(ready,'cancel',result['task_id'])
    work = tick(ready,5)
    assert frontier.get(work)['status'] == 'cancelled' and frontier.get(work)['source_evidence'] is None
    assert work.player.inventory == before.player.inventory
    assert not frontier.get(work)['person_id']


def test_atomic_failure_after_real_person_registry_transfer(ready):
    issue(ready,'frontier_inquire')
    before = ready[0].store._path(ready[1].id).read_bytes()
    original = ready[2].frontier_deploy
    deployed = []
    def deploy(game, person, home):
        original(game,person,home)
        deployed.append(person)
    ready = ready[0], ready[1], replace(ready[2], frontier_deploy=deploy)
    # The fixture's annual closure uses its original ports; replace the year
    # explicitly so this failure proves the handoff happened before saving.
    def advance(game,rng,news):
        frontier.year_step(ready[2],game)
        year_step(ready[2],game,YearContext(game.heavens_state['runtime']['last_year_key']+1))
        return True
    ready = ready[0], ready[1], replace(ready[2],advance_year=advance)
    with patch.object(ready[0].store,'save',side_effect=OSError('disk full')):
        with pytest.raises(OSError): issue(ready,'frontier_wait')
    assert deployed
    assert ready[0].store._path(ready[1].id).read_bytes() == before
    assert deployed[0] not in load(ready).world_npcs


def test_normal_growth_beyond_route_capacity_releases_deployment_without_faking_rank(ready):
    work = arrive(ready)
    identity = frontier.get(work)['person_id']
    work.world_npcs[identity].realm_index = 6
    work.world_npcs[identity].concealed_realm_index = 4
    ready[0].store.save(work)
    work = tick(ready)
    assert frontier.get(work)['status'] == 'failed'
    assert work.world_npcs[identity].realm_index == 6 and work.world_npcs[identity].world == 'human'
    assert not deployment_assignment(work,identity)


def test_actual_road_and_recon_route_roundtrip_uses_one_npc_year_per_elapsed_year(ready):
    work = load(ready)
    issuer = ready[2].frontier_authority(work)['issuer_id']
    # Use the supported existing-office path so an unrelated strong recruit
    # does not replace the authorizer through the native leadership fallback.
    work.intrigue_state.setdefault('factions', {})['sect:blood_prison'] = {'controller_id': issuer}
    ready[0].store.save(work)
    work = start(ready)
    identity = frontier.get(work)['person_id']
    start_age = work.world_npcs[identity].age
    real = ready[0], ready[1], ready[0]._dependencies.heavens
    count = 0
    # This exact-duration test needs a surviving authorizer. A DLC changes the
    # unrelated random accident stream; revocation/death have separate tests.
    # Keep both real annual loops, settlement and all ordinary age processing.
    with (patch.object(ready[0], '_advance_guixu_calendar', return_value=False),
          patch.object(ready[0], '_advance_npc_cultivation', return_value=None),
          patch.dict(FACTION_SYSTEMS['npc_cultivation'], accident_death_chance=0)):
        while frontier.get(load(real))['status'] == 'active' and count < 160:
            issue(real,'frontier_wait')
            count += 1
    work = load(real)
    row = frontier.get(work)
    assert row['status'] == 'completed' and count == 2*row['road_years']+2*ROUTE.crossing_years+12+2
    assert work.world_npcs[identity].age == start_age+count
    assert work.world_npcs[identity].world == 'demon' and work.world_npcs[identity].location_id == row['home']
