"""Four highest worlds share contracts, with independent facts and funded civil work."""
import copy
from dataclasses import replace
from unittest.mock import Mock, patch

import pytest

from test_heavens_m1 import local, quiet, issue
from cultivation_life.models import GameState
from cultivation_life.rules import opportunity_required
from cultivation_life.content_registry import WORLD_SYSTEMS, ROOT_DEFINITIONS
from cultivation_life.system.heavens import operations, tasks
from cultivation_life.system.heavens.calendar import year_step, YearContext
from cultivation_life.system.heavens.cultivation import activity_gain
from cultivation_life.system.heavens.definitions import CONTACT_SITES, validate_framework
from cultivation_life.system.heavens.schema import validate_state, validate_references
from cultivation_life.system.heavens.state import create_echo, get_echo, contacts

MATERIALS = ('celestial_sun_law_crystal', 'asura_war_thunder_drum',
             'nether_worldtree_stake', 'reincarnation_other_shore_petal')


def move(local, site):
    engine, game, _ = local
    work = engine.store.load(game.id)
    work.player.world, work.player.location_id = site.world, site.location_id
    work.player.path = site.visitor_path
    work.player.immortal_power_converted = site.world == 'celestial'
    engine.store.save(work)
    return work


def evidence(local, site):
    move(local, site)
    issue(local, 'observe', target=site.id)
    issue(local, 'check_history', target=site.id)
    engine, game, _ = local
    echo = get_echo(engine.store.load(game.id).heavens_state['runtime'], site.id)
    issue(local, 'exchange', {'person_id': echo['visitor_id']}, target=site.id)
    return echo['visitor_id']


def stones(game):
    return sum(item.quantity for item in game.player.inventory if item.id == 'spirit_stone')


@pytest.mark.parametrize('site', CONTACT_SITES, ids=lambda site: site.world)
def test_full_local_cycle_and_funded_followup(local, site):
    local = quiet(local)
    engine, game, deps = local
    initial = move(local, site)
    person_id = evidence(local, site)
    before = engine.store.load(game.id)
    npc = before.world_npcs[person_id]
    assert (npc.world, npc.location_id, npc.path) == (site.world, site.location_id, site.visitor_path)
    assert npc.transcendence is not None
    assert npc.spirit_root in ROOT_DEFINITIONS
    assert deps.read_actor_facts(before, site.id)['can_apply']
    quote = operations.preview(deps, game.id, 'correspond', site.id, {'person_id': person_id})
    assert quote['years'] == 10 and quote['reward_stones'] == 2500
    seq, revision = before.heavens_state['command_seq'] + 1, quote['revision']
    done = issue(local, 'correspond', {'person_id': person_id}, target=site.id)
    after = engine.store.load(game.id)
    echo = get_echo(after.heavens_state['runtime'], site.id)
    assert done['status'] == 'completed' and after.player.age == initial.player.age + 80
    assert stones(after) == stones(initial) - 30000 + 2500
    assert stones(after) + echo['project_stones'] == stones(before) + 20000
    assert echo['project_stones'] == 17500 and echo['correspondence_completed']
    assert after.player.opportunity == initial.player.opportunity
    assert operations.command(deps, game.id, seq, revision, 'correspond', site.id, {'person_id': person_id}) == done
    with pytest.raises(ValueError, match='一次'):
        issue(local, 'correspond', {'person_id': person_id}, target=site.id)
    issue(local, 'attune', target=site.id)
    after = engine.store.load(game.id)
    echo = get_echo(after.heavens_state['runtime'], site.id)
    grant = Mock(side_effect=lambda p, amount: amount)
    activity_gain(replace(deps, grant_progress=grant), after, 100, 'cultivate')
    grant.assert_called_once_with(after.player, 115)
    assert echo['reward_claimed'] == 15
    assert echo['application']['remaining'] == 99
    engine.store.save(after)
    issue(local, 'cancel', target=site.id)
    after = engine.store.load(game.id)
    material = dict(id='local-material', material_id=MATERIALS[CONTACT_SITES.index(site)], acquired_tier=9)
    after.player.formation_materials.append(material)
    engine.store.save(after)
    issue(local, 'maintain', {'material_id': material['id']}, target=site.id)
    after = engine.store.load(game.id)
    assert get_echo(after.heavens_state['runtime'], site.id)['maintained']
    assert not after.player.formation_materials
    view = operations.project(after, 'known', deps=deps)
    assert view['target_id'] == site.id and view['echo']['world'] == site.world
    assert view['echo']['evidence'] == [f'E{i+1} {label}' for i, label in enumerate(site.evidence)]
    assert GameState.from_dict(after.to_dict()).to_dict() == after.to_dict()


@pytest.mark.parametrize('site', CONTACT_SITES, ids=lambda site: site.world)
def test_real_world_year_and_local_material_eligibility(local, site):
    engine, game, deps = local
    initial = move(local, site)
    result = issue(local, 'observe', target=site.id)
    work = engine.store.load(game.id)
    echo = get_echo(work.heavens_state['runtime'], site.id)
    assert work.world_npcs[echo['visitor_id']].age == 3000 + result['progress']
    assert work.player.age == initial.player.age + result['progress']
    work.player.formation_materials = [dict(id=f'm-{i}', material_id=key, acquired_tier=9) for i, key in enumerate(MATERIALS)]
    assert [row['material_id'] for row in deps.quote_materials(work, site.id)] == [MATERIALS[CONTACT_SITES.index(site)]]
    wrong = CONTACT_SITES[(CONTACT_SITES.index(site)+1) % 4]
    with pytest.raises(ValueError, match='亲自参与'):
        tasks.quote(deps, work, 'observe', wrong.id, {})


def test_four_contacts_survive_reload_with_global_task_and_attunement_limits(local):
    local = quiet(local)
    engine, game, deps = local
    for site in CONTACT_SITES:
        move(local, site)
        issue(local, 'observe', target=site.id)
        issue(local, 'check_history', target=site.id)
    work = engine.store.load(game.id)
    echoes = contacts(work.heavens_state['runtime'])
    assert len(echoes) == len({echo['visitor_id'] for echo in echoes}) == 4
    assert len({echo['origin_year'] for echo in echoes}) == 4
    assert len(work.heavens_state['runtime']['tasks']) == 4
    issue(local, 'attune', target='reincarnation_echo')
    move(local, CONTACT_SITES[1])
    with pytest.raises(ValueError, match='参悟安排'):
        issue(local, 'attune', target='asura_echo')
    work = engine.store.load(game.id)
    application = get_echo(work.heavens_state['runtime'], 'reincarnation_echo')['application']
    grant = Mock(return_value=100)
    activity_gain(replace(deps, grant_progress=grant), work, 100, 'cultivate')
    grant.assert_called_once_with(work.player, 100)
    assert application['remaining'] == 99
    engine.store.save(work)
    # Cancelling a remote registration is cleanup and remains available.
    issue(local, 'cancel', target='reincarnation_echo')
    def interrupt(work, rng, news):
        year_step(deps, work, YearContext(work.heavens_state['runtime']['last_year_key']+1))
        return False
    current = engine.store.load(game.id)
    identity = get_echo(current.heavens_state['runtime'], 'asura_echo')['visitor_id']
    result = issue((engine, game, replace(deps, advance_year=interrupt)), 'exchange', {'person_id': identity}, target='asura_echo')
    move(local, CONTACT_SITES[2])
    with pytest.raises(ValueError, match='当前诸天任务'):
        issue(local, 'attune', target='nether_echo')
    issue(local, 'cancel', target=result['task_id'])
    work = engine.store.load(game.id)
    before = copy.deepcopy(work.to_dict())
    view = operations.project(work, 'known', 'asura_echo', deps=deps)
    assert len(view['records']) == 4 and len(view['sites']) == 4
    assert all(not row['enabled'] for row in view['actions'])
    assert work.to_dict() == before
    validate_references(work)


@pytest.mark.parametrize('ending', ['cancel', 'death', 'npc_death', 'save_failure'])
def test_correspondence_escrow_atomicity_and_no_reward_on_interruption(local, ending):
    local = quiet(local)
    engine, game, deps = local
    site = CONTACT_SITES[2]
    identity = evidence(local, site)
    before = engine.store.load(game.id)
    original = engine.store._path(game.id).read_bytes()
    def interrupt(work, rng, news):
        if ending == 'death':
            work.player.alive = False
        if ending == 'npc_death':
            work.world_npcs[identity].alive = False
        year_step(deps, work, YearContext(work.heavens_state['runtime']['last_year_key']+1))
        return False
    interrupted = (engine, game, replace(deps, advance_year=interrupt))
    if ending == 'save_failure':
        with patch.object(engine.store, 'save', side_effect=OSError('disk unavailable')):
            with pytest.raises(OSError):
                issue(local, 'correspond', {'person_id': identity}, target=site.id)
        assert engine.store._path(game.id).read_bytes() == original
        return
    result = issue(interrupted, 'correspond', {'person_id': identity}, target=site.id)
    work = engine.store.load(game.id)
    echo = get_echo(work.heavens_state['runtime'], site.id)
    if ending == 'cancel':
        assert echo['project_stones'] == 17500
        assert work.heavens_state['runtime']['tasks'][-1]['project_reward'] == 2500
        assert stones(work) == stones(before)
        issue(local, 'cancel', target=result['task_id'])
        work = engine.store.load(game.id)
        echo = get_echo(work.heavens_state['runtime'], site.id)
    else:
        assert result['status'] == 'failed'
    assert echo['project_stones'] == 20000 and not echo.get('correspondence_completed')
    assert stones(work) == stones(before) and work.player.age == before.player.age+1
    assert work.heavens_state['runtime']['tasks'][-1]['project_reward'] == 0


def test_correspondence_resume_and_period_cannot_pay_twice(local):
    local = quiet(local)
    engine, game, deps = local
    site = CONTACT_SITES[3]
    identity = evidence(local, site)
    def interrupt(work, rng, news):
        year_step(deps, work, YearContext(work.heavens_state['runtime']['last_year_key']+1))
        return False
    result = issue((engine, game, replace(deps, advance_year=interrupt)), 'correspond', {'person_id': identity}, target=site.id)
    assert result['progress'] == 1
    assert issue(local, 'resume', target=result['task_id'])['status'] == 'completed'
    work = engine.store.load(game.id)
    work.heavens_state['generation_enabled'] = False
    for key in range(81, 2001):
        year_step(deps, work, YearContext(key))
    engine.store.save(work)
    issue(local, 'observe', target=site.id)
    with pytest.raises(ValueError, match='一次'):
        issue(local, 'correspond', {'person_id': identity}, target=site.id)
    assert get_echo(engine.store.load(game.id).heavens_state['runtime'], site.id)['project_stones'] == 17500


@pytest.mark.parametrize('site', CONTACT_SITES[1:], ids=lambda site: site.world)
def test_ordinary_upper_gain_still_uses_actual_existing_cap(local, site):
    local = quiet(local)
    engine, game, deps = local
    evidence(local, site)
    issue(local, 'attune', target=site.id)
    work = engine.store.load(game.id)
    cap = opportunity_required(work.player)
    work.player.opportunity = cap - 105
    with patch('cultivation_life.system.asura.enabled', return_value=False):
        activity_gain(deps, work, 100, 'cultivate')
        echo = get_echo(work.heavens_state['runtime'], site.id)
        assert work.player.opportunity == cap and echo['reward_claimed'] == 5
        activity_gain(deps, work, 100, 'cultivate')
    assert work.player.opportunity == cap and echo['reward_claimed'] == 5


def test_legacy_m1_document_remains_unchanged_on_read_and_extends_lazily(local):
    local = quiet(local)
    engine, game, deps = local
    issue(local, 'observe')
    work = engine.store.load(game.id)
    runtime = work.heavens_state['runtime']
    runtime['sea_echo'].pop('site')
    runtime['tasks'][0].pop('target_id')
    engine.store.save(work)
    original = engine.store._path(game.id).read_bytes()
    assert operations.view(deps, game.id, 'known')['echo']['id'] == 'sea_echo'
    remote = operations.view(deps, game.id, 'known', 'asura_echo')
    assert 'echo' not in remote and all(not row['enabled'] for row in remote['actions'])
    assert engine.store._path(game.id).read_bytes() == original
    move(local, CONTACT_SITES[1])
    issue(local, 'observe', target='asura_echo')
    saved = engine.store.load(game.id).heavens_state['runtime']
    assert 'site' not in saved['sea_echo'] and saved['tasks'][0].get('target_id') is None
    assert set(saved['contacts']) == {'asura_echo'}


@pytest.mark.parametrize('damage', ['duplicate', 'location', 'version', 'task_target', 'reward', 'person', 'unknown'])
def test_reject_corrupt_extended_documents(local, damage):
    engine, game, deps = local
    first = create_echo(deps, game)
    second = create_echo(deps, game, 'asura_echo')
    if damage == 'duplicate': game.heavens_state['runtime']['contacts']['sea_echo'] = first
    if damage == 'location': second['site']['location_id'] = 'law_sea'
    if damage == 'version': game.heavens_state['definition_versions']['asura_echo'] = True
    if damage == 'unknown': second['future_route'] = {}
    if damage == 'person': second['visitor_id'] = first['visitor_id']
    if damage in {'task_target', 'reward'}:
        task = dict(id='task', action='observe', status='paused', cycle=0, progress=1, duration=20,
                    target_id='missing' if damage == 'task_target' else 'asura_echo', person_id=None,
                    escrow=dict(total=0, spent=0, refunded=0, material=None, mp_paid=0))
        if damage == 'reward': task['project_reward'] = 2500
        game.heavens_state['runtime']['tasks'] = [task]
    with pytest.raises(ValueError):
        validate_state(game.heavens_state)
        validate_references(game)


def test_content_covers_all_highest_worlds_and_discovery_is_local(local):
    engine, game, deps = local
    config = WORLD_SYSTEMS['heavens_framework']
    validate_framework(config, set(WORLD_SYSTEMS['world_profiles']))
    highest = {key for key, value in WORLD_SYSTEMS['world_profiles'].items() if value['tier'] == 3}
    assert {site.world for site in CONTACT_SITES} == highest
    for route in WORLD_SYSTEMS['cultivation_routes'].values():
        assert route['stages'][-1]['enabled']
    game.player.realm_index = 12
    for index, site in enumerate(CONTACT_SITES):
        game.player.world, game.player.location_id = site.world, site.location_id
        # Force the perception roll only; old RNG remains untouched.
        original = game.rng_state
        with patch('cultivation_life.system.heavens.calendar.sha256') as digest:
            digest.return_value.digest.return_value = bytes(32)
            for key in range(index*100+1, (index+1)*100+1):
                year_step(deps, game, YearContext(key))
        assert bool(get_echo(game.heavens_state['runtime'], site.id)) == (index < 3)
        assert game.rng_state == original
    assert game.heavens_state['runtime']['rng_counter'] == 3
    assert len(game.heavens_state['runtime']['notifications']) == 3
    game.heavens_state['runtime']['notifications'].clear()
    year_step(deps, game, YearContext(400))
    assert not get_echo(game.heavens_state['runtime'], CONTACT_SITES[-1].id)
    with patch('cultivation_life.system.heavens.calendar.sha256') as digest:
        digest.return_value.digest.return_value = bytes(32)
        for key in range(401, 501):
            year_step(deps, game, YearContext(key))
    assert get_echo(game.heavens_state['runtime'], CONTACT_SITES[-1].id)
    assert game.heavens_state['runtime']['rng_counter'] == 4
    validate_state(game.heavens_state)
