"""M1 actual time, authoritative people, escrow and isolated commands."""
import copy
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.models import GameState
from cultivation_life.rules import add_item, max_hp, max_mp
from cultivation_life.system.heavens import operations, tasks
from cultivation_life.system.heavens.calendar import YearContext, year_step
from cultivation_life.system.heavens.cultivation import activity_gain
from cultivation_life.system.heavens.definitions import HeavensDefinitions
from cultivation_life.system.heavens.schema import validate_state
from cultivation_life.system.heavens.state import initialize, create_echo

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def local(tmp_path):
    engine = GameEngine(ROOT, tmp_path / 'saves')
    public = engine.create_game('天海测试', 'heavenly', 'dao', 4242, preset_id='core')
    game = engine.store.load(public['id'])
    p = game.player
    p.world, p.location_id, p.realm_index = 'celestial', 'law_sea', 9
    p.immortal_power_converted = True
    p.lifespan = None
    p.hp, p.mp = max_hp(p), max_mp(p)
    p.next_tribulation_age = 999999
    add_item(p, 'spirit_stone', 100000)
    initialize(game)
    deps = replace(engine._dependencies.heavens, load_game=engine.store.load,
                   get_definitions=lambda: HeavensDefinitions(generation_available=True))
    engine.store.save(game)
    return engine, game, deps


def issue(local, action, options=None, target='sea_echo'):
    engine, game, deps = local
    current = engine.store.load(game.id)
    state = current.heavens_state
    return operations.command(deps, game.id, state['command_seq'] + 1, state['revision'],
                              action, target, options or {})


def quiet(local):
    """Use the real year hook; isolate random interruptions for exact accounting."""
    engine, game, deps = local
    def advance(work, rng, news):
        runtime = work.heavens_state['runtime']
        year_step(deps, work, YearContext(runtime['last_year_key'] + 1))
        return True
    return engine, game, replace(deps, advance_year=advance, settle_activity_units=Mock())


def test_full_evidence_sequence_credit_and_retry(local):
    local = quiet(local)
    engine, game, deps = local
    start = engine.store.load(game.id)
    result = issue(local, 'observe')
    assert result['status'] == 'completed' and result['progress'] == 20
    observed = engine.store.load(game.id)
    assert observed.player.age == start.player.age + 20
    assert observed.player.opportunity == start.player.opportunity
    assert observed.heavens_state['runtime']['unit_credit'] == {'numerator': 1, 'denominator': 5}
    snapshot = engine.store._path(game.id).read_bytes()
    assert operations.command(deps, game.id, 1, 0, 'observe', 'sea_echo', {}) == result
    assert engine.store._path(game.id).read_bytes() == snapshot
    issue(local, 'check_history')
    g = engine.store.load(game.id)
    identity = g.heavens_state['runtime']['sea_echo']['visitor_id']
    issue(local, 'exchange', {'person_id': identity})
    g = engine.store.load(game.id)
    echo = g.heavens_state['runtime']['sea_echo']
    assert echo['history_checked'] and echo['exchanged'] and echo['project_stones'] == 20000
    assert g.heavens_state['runtime']['unit_credit'] == {'numerator': 7, 'denominator': 10}
    assert all(call.args[2] == 0 for call in deps.settle_activity_units.call_args_list)
    issue(local, 'attune')
    g = engine.store.load(game.id)
    assert g.player.opportunity == start.player.opportunity
    echo = g.heavens_state['runtime']['sea_echo']
    grant = Mock(side_effect=lambda p, amount: amount)
    for _ in range(100):
        activity_gain(replace(deps, grant_progress=grant), g, 1e9, 'cultivate')
    assert grant.call_count == 100
    assert echo['reward_claimed'] == pytest.approx(echo['reward_base'] * .03)
    assert echo['application'] is None
    validate_state(g.heavens_state)


def test_real_engine_observation_ages_authoritative_visitor(local):
    engine, game, deps = local
    # Existing simulation is exercised, including interruptions and NPC aging.
    result = issue(local, 'observe')
    after = engine.store.load(game.id)
    runtime = after.heavens_state['runtime']
    npc = after.world_npcs[runtime['sea_echo']['visitor_id']]
    assert npc.transcendence is not None
    assert 1 <= result['progress'] <= 20
    assert after.player.age - game.player.age == result['progress']
    assert npc.age - 3000 == result['progress']
    assert runtime['processed_years'] == result['progress']
    assert GameState.from_dict(after.to_dict()).to_dict() == after.to_dict()


def test_queries_are_pure_and_quote_has_costs(local):
    engine, game, deps = local
    before = engine.store._path(game.id).read_bytes()
    assert operations.preview(deps, game.id, 'observe', 'sea_echo', {})['years'] == 20
    view = operations.view(deps, game.id, 'known')
    assert 'echo' not in view and view['actions'][0]['enabled']
    assert engine.store._path(game.id).read_bytes() == before


def test_cancel_returns_only_unused_stones_and_material(local):
    local = quiet(local)
    engine, game, deps = local
    issue(local, 'observe'); issue(local, 'check_history')
    g = engine.store.load(game.id)
    material = dict(id='test-material', material_id='celestial_sun_law_crystal', name='测试阵材', acquired_tier=9)
    g.player.formation_materials.append(material)
    engine.store.save(g)
    mp = g.player.mp
    def interrupt(work, rng, news):
        runtime = work.heavens_state['runtime']
        year_step(deps, work, YearContext(runtime['last_year_key'] + 1))
        return False
    interrupted = (engine, game, replace(deps, advance_year=interrupt))
    result = issue(interrupted, 'maintain', {'material_id': material['id']})
    assert result['progress'] == 1 and result['status'] == 'paused'
    g = engine.store.load(game.id)
    assert not g.player.formation_materials
    issue(local, 'cancel', target=result['task_id'])
    g = engine.store.load(game.id)
    task = g.heavens_state['runtime']['tasks'][-1]
    assert task['escrow']['spent'] == 400 and task['escrow']['refunded'] == 19600
    assert g.player.formation_materials == [material]
    assert g.player.mp == mp - max_mp(g.player) * .05


def test_failed_save_rolls_back_whole_command(local):
    local = quiet(local)
    engine, game, deps = local
    before = engine.store._path(game.id).read_bytes()
    with patch.object(engine.store, 'save', side_effect=OSError('disk unavailable')):
        with pytest.raises(OSError):
            issue(local, 'observe')
    assert engine.store._path(game.id).read_bytes() == before
    assert engine.store.load(game.id).heavens_state['runtime']['sea_echo'] is None


def test_calendar_is_idempotent_and_generation_off_keeps_cycle(local):
    engine, game, deps = local
    echo = create_echo(deps, game)
    echo.update(history_checked=True, exchanged=True, observed_cycle=0, maintained=True, maintenance_started=True)
    game.heavens_state['generation_enabled'] = False
    original_rng = game.rng_state
    for key in range(1, 2001):
        year_step(deps, game, YearContext(key))
        year_step(deps, game, YearContext(key))
    assert game.heavens_state['runtime']['processed_years'] == 2000
    assert echo['cycle'] == 1 and not echo['maintained']
    assert echo['history_checked'] and echo['exchanged'] and echo['observed_cycle'] == 0
    assert game.rng_state == original_rng
    assert list(game.world_npcs).count(echo['visitor_id']) == 1
    validate_state(game.heavens_state)


def test_discovery_uses_full_real_century_and_no_ineligible_draw(local):
    engine, game, deps = local
    game.player.location_id = 'not-law-sea'
    for key in range(1, 101):
        year_step(deps, game, YearContext(key))
    runtime = game.heavens_state['runtime']
    assert runtime['last_discovery_window'] == 0 and runtime['rng_counter'] == 0
    game.player.location_id = 'law_sea'
    for key in range(101, 200):
        year_step(deps, game, YearContext(key))
    assert runtime['rng_counter'] == 0
    year_step(deps, game, YearContext(200))
    assert runtime['rng_counter'] == 1
    assert not runtime['pause_requested']


@pytest.mark.parametrize('change', ['dead', 'moved', 'party', 'war', 'faction'])
def test_person_availability_uses_authoritative_identity(local, change):
    local = quiet(local)
    engine, game, deps = local
    issue(local, 'observe'); issue(local, 'check_history')
    g = engine.store.load(game.id)
    identity = g.heavens_state['runtime']['sea_echo']['visitor_id']
    npc = g.world_npcs[identity]
    if change == 'dead': npc.alive = False
    if change == 'moved': npc.location_id = 'jade_capital'
    if change == 'party': g.player.party.append({'id': identity})
    if change == 'war': g.wars.append({'status': 'active', 'roster': {'left': [identity]}})
    if change == 'faction': npc.faction_id = 'other'
    assert not deps.person_available(g, identity)
    with pytest.raises(ValueError, match='人物'):
        tasks.quote(deps, g, 'exchange', 'sea_echo', {'person_id': identity})
    # The independent evidence path remains usable.
    assert tasks.quote(deps, g, 'attune', 'sea_echo', {})['years'] == 0


def test_person_death_mid_exchange_refunds_and_does_not_grant_evidence(local):
    local = quiet(local)
    engine, game, deps = local
    issue(local, 'observe'); issue(local, 'check_history')
    g = engine.store.load(game.id)
    identity = g.heavens_state['runtime']['sea_echo']['visitor_id']
    def death(work, rng, news):
        work.world_npcs[identity].alive = False
        runtime = work.heavens_state['runtime']
        year_step(deps, work, YearContext(runtime['last_year_key']+1))
        return True
    result = issue((engine, game, replace(deps, advance_year=death)), 'exchange', {'person_id': identity})
    g = engine.store.load(game.id)
    echo = g.heavens_state['runtime']['sea_echo']
    assert result['status'] == 'failed' and not echo['exchanged']
    assert echo['project_stones'] == 1000
    assert g.heavens_state['runtime']['tasks'][-1]['escrow']['refunded'] == 19000
    with pytest.raises(ValueError):
        issue(local, 'exchange', {'person_id': identity})


def test_maintenance_then_second_application_share_cap_and_complete_credit(local):
    local = quiet(local)
    engine, game, deps = local
    issue(local, 'observe'); issue(local, 'check_history'); issue(local, 'attune')
    g = engine.store.load(game.id)
    echo = g.heavens_state['runtime']['sea_echo']
    for _ in range(100): activity_gain(deps, g, 1e8, 'cultivate')
    first = echo['reward_claimed']
    assert first == pytest.approx(.02 * echo['reward_base'])
    g.player.formation_materials.append(dict(id='material', material_id='celestial_sun_law_crystal', acquired_tier=9))
    engine.store.save(g)
    result = issue(local, 'maintain', {'material_id':'material'})
    assert result['status'] == 'completed'
    assert deps.settle_activity_units.call_args.args[2] == 1
    issue(local, 'attune')
    g = engine.store.load(game.id)
    for _ in range(100): activity_gain(deps, g, 1e8, 'cultivate')
    assert g.heavens_state['runtime']['sea_echo']['reward_claimed'] == first
    assert not g.player.formation_materials
    assert operations.project(g, 'known', deps=deps)['echo']['remaining'] == 1700


def test_fraction_is_exact_across_realm_change_and_resume(local):
    local = quiet(local)
    engine, game, deps = local
    issue(local, 'observe')
    g = engine.store.load(game.id)
    g.player.realm_index = 10
    engine.store.save(g)
    def stop(work, rng, news):
        runtime = work.heavens_state['runtime']
        year_step(deps, work, YearContext(runtime['last_year_key']+1))
        return False
    partial = issue((engine, game, replace(deps, advance_year=stop)), 'check_history')
    assert partial['progress'] == 1
    result = issue(local, 'resume', target=partial['task_id'])
    g = engine.store.load(game.id)
    assert result['status'] == 'completed'
    assert g.heavens_state['runtime']['unit_credit'] == {'numerator': 13, 'denominator': 50}


@pytest.mark.parametrize('result,dead', [(True,False),(False,False),(False,True)])
def test_annual_boundary_after_original_result_even_death(local, result, dead):
    engine, game, deps = local
    from cultivation_life.engine import world_time
    def old(*args, **kwargs):
        assert game.heavens_state['runtime']['processed_years'] == 0
        game.player.alive = not dead
        return result
    with patch.object(world_time, '_advance_world_year', side_effect=old):
        assert engine._advance_world_year(game, Mock(), []) == result
    assert game.heavens_state['runtime']['processed_years'] == 1


def test_spatial_annual_boundary_and_cleanup_access(local):
    engine, game, deps = local
    from cultivation_life.engine import world_time
    from cultivation_life.system import spatial
    game.player.world = 'rift'
    with patch.object(spatial, 'tick'), patch.object(world_time, 'advance_spatial_year', return_value=False) as old:
        assert not engine._advance_world_year(game, Mock(), [])
    old.assert_called_once()
    assert game.heavens_state['runtime']['processed_years'] == 1
    spatial.guard(game, 'heavens_command')
    with pytest.raises(ValueError, match='法则天海'):
        tasks.quote(deps, game, 'observe', 'sea_echo', {})


def test_application_survives_save_interrupt_but_not_period_and_does_not_boost_other_action(local):
    local = quiet(local)
    engine, game, deps = local
    issue(local, 'observe'); issue(local, 'check_history'); issue(local, 'attune')
    g = engine.store.load(game.id)
    echo = g.heavens_state['runtime']['sea_echo']
    assert activity_gain(deps, g, 100, 'sense_train') == 100
    assert echo['application']['remaining'] == 100
    assert activity_gain(deps, g, 100, 'cultivate') == 110
    engine.store.save(g); g = engine.store.load(game.id)
    echo = g.heavens_state['runtime']['sea_echo']
    assert echo['application']['remaining'] == 99
    g.player.world = 'human'
    assert activity_gain(deps, g, 100, 'cultivate') == 100
    for key in range(g.heavens_state['runtime']['last_year_key']+1, 2001):
        year_step(deps, g, YearContext(key))
    assert echo['application'] is None and echo['reward_claimed'] == 0


def test_references_and_capacity_fail_closed(local):
    engine, game, deps = local
    echo = create_echo(deps, game)
    game.world_npcs.pop(echo['visitor_id'])
    with pytest.raises(ValueError, match='引用'):
        engine.store.save(game)
    game.heavens_state['runtime']['notifications'] = [dict(id='sea_echo',text='x',expires_at=100)] * 4
    with pytest.raises(ValueError, match='容量'):
        validate_state(game.heavens_state)


def test_unused_registration_can_be_cancelled_without_new_reward(local):
    local = quiet(local)
    engine, game, deps = local
    issue(local, 'observe'); issue(local, 'check_history'); issue(local, 'attune')
    initial = engine.store.load(game.id)
    issue(local, 'cancel'); issue(local, 'attune')
    g = engine.store.load(game.id)
    assert g.player.age == initial.player.age and g.player.opportunity == initial.player.opportunity
    assert g.heavens_state['runtime']['sea_echo']['applications_used'] == 1


def test_retry_enable_ignores_later_content_gate(local):
    engine, game, deps = local
    g=engine.store.load(game.id);g.heavens_state={};engine.store.save(g)
    options={'generation_enabled':True}
    first=operations.command(deps,game.id,1,0,'configure',None,options)
    closed=replace(deps,get_definitions=HeavensDefinitions)
    assert operations.command(closed,game.id,1,0,'configure',None,options)==first


def test_partial_capacity_records_only_actual_extra_once(local):
    local=quiet(local)
    engine,game,deps=local
    issue(local,'observe');issue(local,'check_history');issue(local,'attune')
    g=engine.store.load(game.id)
    grant=Mock(return_value=105)
    activity_gain(replace(deps,grant_progress=grant),g,100,'cultivate')
    grant.assert_called_once_with(g.player,110)
    assert g.heavens_state['runtime']['sea_echo']['reward_claimed']==5


def test_late_window_quote_and_next_cycle_needs_observation(local):
    local=quiet(local)
    engine,game,deps=local
    issue(local,'observe');issue(local,'check_history')
    g=engine.store.load(game.id)
    for key in range(51,1201):year_step(deps,g,YearContext(key))
    with pytest.raises(ValueError,match='窗口'):
        tasks.quote(deps,g,'attune','sea_echo',{})
    for key in range(1201,2001):year_step(deps,g,YearContext(key))
    with pytest.raises(ValueError,match='体察'):
        tasks.quote(deps,g,'attune','sea_echo',{})
    assert tasks.quote(deps,g,'observe','sea_echo',{})['years']==20


def test_normal_500_year_application_stops_at_actual_old_interrupt(local):
    local=quiet(local)
    engine,game,deps=local
    issue(local,'observe');issue(local,'check_history')
    g=engine.store.load(game.id);g.player.realm_index=10;engine.store.save(g)
    issue(local,'attune')
    g=engine.store.load(game.id)
    assert g.heavens_state['runtime']['sea_echo']['application']['unit_years']==500
    start_age=g.player.age
    def interrupt(work,rng,news,**kwargs):
        runtime=work.heavens_state['runtime']
        year_step(deps,work,YearContext(runtime['last_year_key']+1))
        return work.player.age-start_age<7
    with patch.object(engine,'_advance_world_year',side_effect=interrupt), patch.object(engine,'_add_opportunity',wraps=engine._add_opportunity) as grant:
        engine.advance(game.id,'cultivate',1)
    g=engine.store.load(game.id)
    assert g.player.age-start_age==7
    assert grant.call_count==7
    assert g.heavens_state['runtime']['sea_echo']['application']['remaining']==493


@pytest.mark.parametrize('watch_pause,expected',[(False,1000),(True,500)])
def test_opportunity_pause_only_at_full_normal_unit(local,watch_pause,expected):
    from cultivation_life.system.heavens.state import visible_notice
    engine,game,deps=local
    game.player.realm_index=10
    game.heavens_state['runtime']['pause_on_opportunity']=watch_pause
    game.settings['silent_events']=True
    engine.store.save(game)
    start_age=game.player.age
    def annual(work,rng,news,**kwargs):
        runtime=work.heavens_state['runtime']
        year_step(deps,work,YearContext(runtime['last_year_key']+1))
        if work.player.age-start_age==1:
            create_echo(deps,work);visible_notice(work,'测试可知线索')
        return True
    with patch.object(engine,'_advance_world_year',side_effect=annual):
        engine.advance(game.id,'cultivate',2)
    assert engine.store.load(game.id).player.age-start_age==expected


def test_real_common_settlement_runs_once_after_short_tasks_accumulate_unit(local):
    engine,game,ports=local
    _,_,deps=quiet(local)
    settle=Mock(wraps=ports.settle_activity_units)
    local=(engine,game,replace(deps,settle_activity_units=settle))
    issue(local,'observe');issue(local,'check_history')
    g=engine.store.load(game.id)
    g.player.formation_materials.append(dict(id='material',material_id='celestial_sun_law_crystal',acquired_tier=9))
    engine.store.save(g)
    with patch.object(engine,'_advance_auction_clock',wraps=engine._advance_auction_clock) as auction:
        result=issue(local,'maintain',{'material_id':'material'})
    g=engine.store.load(game.id)
    assert result['status']=='completed'
    assert [call.args[2] for call in settle.call_args_list]==[0,0,1]
    auction.assert_called_once()
    assert g.player.age-game.player.age==100
    assert g.player.opportunity==game.player.opportunity
    assert g.heavens_state['runtime']['unit_credit']=={'numerator':0,'denominator':1}
