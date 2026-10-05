"""Personal visits: physical routes, paid return, interruptions and atomic saves."""
import copy
from dataclasses import replace
from unittest.mock import Mock

import pytest

from cultivation_life.content_registry import WORLD_SYSTEMS
from cultivation_life.models import GameState
from cultivation_life.system.heavens import operations, tasks
from cultivation_life.system.heavens.definitions import CONTACT_SITES, VISIT_DESTINATIONS, default_site
from cultivation_life.system.heavens.schema import validate_state
from cultivation_life.system.heavens.state import create_echo, get_echo
from test_heavens_m1 import local, quiet, issue


def stones(game):
    return sum(i.quantity for i in game.player.inventory if i.id == 'spirit_stone')


def ready(local, site=CONTACT_SITES[0]):
    engine, initial, deps = local
    game = engine.store.load(initial.id)
    game.player.world, game.player.location_id = site.world, site.location_id
    game.settings['silent_events'] = True
    echo = create_echo(deps, game, site.id)
    echo.update(history_checked=True, exchanged=True, correspondence_completed=True, project_stones=17500)
    engine.store.save(game)
    return game


@pytest.mark.parametrize('site', CONTACT_SITES, ids=lambda s: s.world)
def test_real_roundtrip_all_four_worlds(local, site):
    local = quiet(local)
    engine, initial, deps = local
    before = ready(local, site)
    origin_npcs = set(before.world_npcs)
    disk = engine.store._path(initial.id).read_bytes()
    preview = operations.preview(deps, initial.id, 'visit_depart', site.id, {})
    assert preview['years'] == 2 and preview['costs']['stones'] == 4000
    operations.project(before, 'known', site.id, deps=deps)
    assert engine.store._path(initial.id).read_bytes() == disk
    result = issue(local, 'visit_depart', target=site.id)
    game = engine.store.load(initial.id)
    destination = default_site(VISIT_DESTINATIONS[site.id])
    assert result['status'] == 'completed'
    assert (game.player.world, game.player.location_id) == (destination.world, destination.location_id)
    assert game.player.age == before.player.age + 2
    assert stones(before) - stones(game) == 4000
    assert set(game.world_npcs) == origin_npcs
    visitor = game.world_npcs[get_echo(game.heavens_state['runtime'], site.id)['visitor_id']]
    assert visitor.world == site.world
    assert not game.player.sealed_cultivation
    assert operations.command(deps, initial.id, 1, before.heavens_state['revision'], 'visit_depart', site.id, {}) == result
    issue(local, 'visit_study', target=site.id)
    game = engine.store.load(initial.id)
    v = operations.project(game, 'known', site.id, deps=deps)['visit']
    assert v['studied'] and destination.name.split(' · ')[0] in v['finding']
    assert v['return_fare'] == 2000
    with pytest.raises(ValueError, match='重复'):
        issue(local, 'visit_study', target=site.id)
    issue(local, 'visit_return', target=site.id)
    game = engine.store.load(initial.id)
    visit = get_echo(game.heavens_state['runtime'], site.id)['visit']
    assert (game.player.world, game.player.location_id) == (site.world, site.location_id)
    assert visit['status'] == 'returned' and visit['return_fare'] == 0
    assert game.player.age == before.player.age + 8
    assert stones(before) - stones(game) == 4000
    assert game.player.opportunity == before.player.opportunity
    assert game.heavens_state['runtime']['unit_credit'] == {'numerator': 2, 'denominator': 25}
    assert GameState.from_dict(game.to_dict()).to_dict() == game.to_dict()
    with pytest.raises(ValueError, match='一次'):
        issue(local, 'visit_depart', target=site.id)


def pause_after(local, years):
    engine, initial, deps = local
    count = 0
    advance = deps.advance_year
    def interrupted(game, rng, news):
        nonlocal count
        advance(game, rng, news)
        count += 1
        if count == years:
            return False
        return True
    return engine, initial, replace(deps, advance_year=interrupted)


def test_last_year_pending_event_defers_crossing_and_retry_costs_nothing(local):
    local = quiet(local)
    before = ready(local)
    engine, initial, deps = local
    advance = deps.advance_year
    def event(game, rng, news):
        advance(game, rng, news)
        if game.heavens_state['runtime']['processed_years'] == 2:
            game.pending_event = {'id': 'test_visit_pause'}
        return not game.pending_event
    interrupted = engine, initial, replace(deps, advance_year=event)
    result = issue(interrupted, 'visit_depart')
    game = engine.store.load(initial.id)
    assert result['status'] == 'paused' and result['progress'] == 2
    assert game.player.world == 'celestial'
    with pytest.raises(ValueError, match='事件'):
        issue(local, 'resume', target=result['task_id'])
    game.pending_event = None
    engine.store.save(game)
    resumed = issue(local, 'resume', target=result['task_id'])
    game = engine.store.load(initial.id)
    assert resumed['status'] == 'completed' and game.player.world == 'reincarnation'
    assert game.player.age == before.player.age + 2 and stones(before)-stones(game) == 4000


def test_cancel_outgoing_refunds_only_unspent_and_closes_permit(local):
    local = quiet(local)
    before = ready(local)
    result = issue(pause_after(local, 1), 'visit_depart')
    engine, initial, deps = local
    quote = operations.preview(deps, initial.id, 'cancel', result['task_id'], {})
    assert quote['refundable']['stones'] == 3000
    issue(local, 'cancel', target=result['task_id'])
    game = engine.store.load(initial.id)
    assert stones(before)-stones(game) == 1000 and game.player.world == 'celestial'
    assert get_echo(game.heavens_state['runtime'])['visit']['status'] == 'cancelled'
    with pytest.raises(ValueError, match='一次'):
        issue(local, 'visit_depart')


def test_early_return_and_paused_return_never_cash_out_or_double_charge(local):
    local = quiet(local)
    before = ready(local)
    engine, initial, deps = local
    issue(local, 'visit_depart')
    result = issue(pause_after(local, 1), 'visit_return')
    assert operations.preview(deps, initial.id, 'cancel', result['task_id'], {})['refundable']['stones'] == 0
    cancelled = issue(local, 'cancel', target=result['task_id'])
    assert cancelled['status'] == 'paused'
    midway = engine.store.load(initial.id)
    assert midway.player.world == 'reincarnation' and stones(before)-stones(midway) == 4000
    issue(local, 'resume', target=result['task_id'])
    game = engine.store.load(initial.id)
    assert game.player.world == 'celestial' and game.player.age == before.player.age+4
    assert not get_echo(game.heavens_state['runtime'])['visit']['studied']
    assert stones(before)-stones(game) == 4000


def test_foreign_movement_cannot_teleport_back(local):
    local = quiet(local)
    ready(local)
    engine, initial, deps = local
    issue(local, 'visit_depart')
    game = engine.store.load(initial.id)
    game.player.world, game.player.location_id = 'asura', 'destruction_sea'
    engine.store.save(game)
    before = engine.store._path(initial.id).read_bytes()
    for action in ('visit_return', 'visit_study'):
        with pytest.raises(ValueError, match='亲自'):
            issue(local, action)
    assert engine.store._path(initial.id).read_bytes() == before


def test_existing_permission_survives_generation_window_and_visitor_death(local):
    local = quiet(local)
    ready(local)
    engine, initial, deps = local
    issue(local, 'visit_depart')
    game = engine.store.load(initial.id)
    echo = get_echo(game.heavens_state['runtime'])
    game.world_npcs[echo['visitor_id']].alive = False
    game.heavens_state['generation_enabled'] = False
    engine.store.save(game)
    issue(local, 'visit_study')
    issue(local, 'visit_return')
    assert engine.store.load(initial.id).player.world == 'celestial'


@pytest.mark.parametrize('at', ['idle', 'outgoing', 'studying', 'returning'])
def test_death_closes_real_escrow_without_moving_or_resurrecting(local, at):
    local = quiet(local)
    before = ready(local)
    engine, initial, deps = local
    if at == 'outgoing':
        issue(pause_after(local, 1), 'visit_depart')
    else:
        issue(local, 'visit_depart')
        if at in {'studying','returning'}:
            issue(pause_after(local, 1), 'visit_study' if at == 'studying' else 'visit_return')
    game = engine.store.load(initial.id)
    world = game.player.world
    game.player.alive = False
    tasks.reconcile(deps, game)
    validate_state(game.heavens_state)
    visit = get_echo(game.heavens_state['runtime'])['visit']
    assert visit['status'] == 'failed' and visit['return_fare'] == 0
    assert game.player.world == world and not game.player.alive
    assert stones(before)-stones(game) == {'outgoing':1000,'idle':2000,'studying':2000,'returning':3000}[at]
    saved = copy.deepcopy(game.to_dict())
    tasks.reconcile(deps, game)
    assert game.to_dict() == saved


def test_route_and_capacity_rechecked_before_arrival(local, monkeypatch):
    local = quiet(local)
    ready(local)
    engine, initial, deps = local
    game = engine.store.load(initial.id)
    game.player.party = [{'id': get_echo(game.heavens_state['runtime'])['visitor_id']}]
    engine.store.save(game)
    with pytest.raises(ValueError):
        issue(local, 'visit_depart')
    game.player.party = []
    engine.store.save(game)
    result = issue(pause_after(local, 1), 'visit_depart')
    route = next(r for r in WORLD_SYSTEMS['world_transition_routes'] if r['id'] == 'study:celestial:reincarnation')
    monkeypatch.setitem(route, 'enabled', False)
    with pytest.raises(ValueError, match='路线'):
        issue(local, 'resume', target=result['task_id'])
    monkeypatch.setitem(route, 'enabled', True)
    issue(local, 'resume', target=result['task_id'])
    assert engine.store.load(initial.id).player.world == 'reincarnation'


def test_unlicensed_route_cannot_be_planned(local):
    engine, initial, deps = local
    with pytest.raises(ValueError, match='许可'):
        engine._plan_world_transition(initial, 'reincarnation', 'study', arrival_location='karma_city')


def test_pending_return_route_does_not_depend_on_observation_deadline(local):
    local = quiet(local)
    ready(local)
    engine, initial, deps = local
    issue(local, 'visit_depart')
    game = engine.store.load(initial.id)
    runtime = game.heavens_state['runtime']
    runtime.update(processed_years=1199, last_year_key=1199, last_discovery_window=10)
    game.player.age += 1197
    engine.store.save(game)
    issue(local, 'visit_study')
    issue(local, 'visit_return')
    assert engine.store.load(initial.id).player.world == 'celestial'


def test_capacity_changed_during_settlement_defers_completed_crossing(local):
    local = quiet(local)
    ready(local)
    engine, initial, deps = local
    def settle(game, *args):
        identity = get_echo(game.heavens_state['runtime'])['visitor_id']
        game.player.party = [{'id': identity}]
    result = issue((engine,initial,replace(deps,settle_activity_units=settle)), 'visit_depart')
    game = engine.store.load(initial.id)
    assert result['status'] == 'paused' and result['progress'] == 2
    assert game.player.world == 'celestial'
    game.player.party = []
    engine.store.save(game)
    issue(local, 'resume', target=result['task_id'])
    assert engine.store.load(initial.id).player.world == 'reincarnation'


def test_real_year_ages_npcs_once_per_year(local):
    before = ready(local)
    engine, initial, deps = local
    identity = get_echo(before.heavens_state['runtime'])['visitor_id']
    result = issue(local, 'visit_depart')
    assert result['status'] == 'completed'
    game = engine.store.load(initial.id)
    assert game.world_npcs[identity].age == before.world_npcs[identity].age + 2
    assert game.player.age == before.player.age + 2
    assert game.world_npcs[identity].world == 'celestial'


def test_failed_commit_keeps_world_fare_and_permit_unchanged(local, monkeypatch):
    local = quiet(local)
    ready(local)
    engine, initial, deps = local
    original = engine.store._path(initial.id).read_bytes()
    monkeypatch.setattr(engine.store, 'save', Mock(side_effect=OSError('disk full')))
    with pytest.raises(OSError, match='disk full'):
        issue(local, 'visit_depart')
    assert engine.store._path(initial.id).read_bytes() == original


@pytest.mark.parametrize('field,value', [('destination','asura_echo'),('return_fare',4000),
    ('studied',1),('status','returned'),('arrived_at',9999)])
def test_forged_visit_state_is_rejected(local, field, value):
    local = quiet(local)
    ready(local)
    issue(local, 'visit_depart')
    game = local[0].store.load(local[1].id)
    get_echo(game.heavens_state['runtime'])['visit'][field] = value
    with pytest.raises(ValueError):
        validate_state(game.heavens_state)


@pytest.mark.parametrize('corrupt', [[], {}, {'status': []}])
def test_malformed_visit_is_rejected_before_task_reference_checks(local, corrupt):
    local = quiet(local)
    ready(local)
    issue(pause_after(local, 1), 'visit_depart')
    game = local[0].store.load(local[1].id)
    get_echo(game.heavens_state['runtime'])['visit'] = corrupt
    with pytest.raises(ValueError, match='访学'):
        validate_state(game.heavens_state)
