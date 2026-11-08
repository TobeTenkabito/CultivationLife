"""Real temple commands, paid local work and the existing cultivation grant."""
import copy
import random
from unittest.mock import patch

import pytest

from test_immortal_cultivation import prepared
from cultivation_life.building_schema import address
from cultivation_life.building_rules import config as buildings_config
from cultivation_life.content_registry import WORLD_SYSTEMS
from cultivation_life.rules import add_item
from cultivation_life.system.earth_temple import public, bill
from cultivation_life.system.earth_temple_rules import state, temple, bonus
from cultivation_life.system.economy.ledger import balance
from cultivation_life.system.economy.local_market import operator_account


@pytest.fixture
def village(prepared):
    e, g, _ = prepared
    spec = next(c for c in buildings_config()['cities']['celestial'] if c['population'] == 'mixed')
    g.player.location_id = spec['location_id']
    g.settings.update(silent_events=True, combat_popup=False, court_election_popup=False)
    add_item(g.player, 'spirit_stone', 10**11)
    for key in bill(g)['materials']:
        add_item(g.player, key, 1000)
    e.store.save(g)
    return e, g.id


def command(e, gid, action, target=''):
    shown = e.get_game(gid)['yaochi']['earth']
    return e.yaochi_action(gid, 'earth_' + action, shown['token'] + ('|' + target if target else ''))


def build(e, gid):
    shown = e.get_game(gid)['yaochi']['earth']
    target = next(c for c in shown['cities'] if not c['reason'])['id']
    return command(e, gid, 'build', target)


def work(e, gid):
    with patch('cultivation_life.engine.orchestration.advancement._finish_action_events', return_value=None):
        return command(e, gid, 'work')


def fulfill(e, gid, kind='watch', plan='standard'):
    command(e, gid, 'accept', kind)
    work(e, gid)
    command(e, gid, 'plan', plan)
    for _ in range(3):
        if (s := state(e._load(gid)))['duty']['progress'] >= s['duty']['years']:
            break
        work(e, gid)
    return command(e, gid, 'claim')


def test_build_uses_original_building_inventory_and_operator_with_stale_rejection(village):
    e, gid = village
    g = e._load(gid)
    before = copy.deepcopy(g.to_dict())
    for _ in range(3):
        public(g)
    assert g.to_dict() == before
    quote = public(g)
    original = quote['cities'][0]
    old = quote['token'] + '|' + original['id']
    cost = bill(g)
    account = operator_account(g)
    money = balance(g, 'player'), balance(g, account)
    age, rng = g.player.age, g.rng_state
    build(e, gid)
    g = e._load(gid)
    assert (g.player.age, g.rng_state) == (age, rng)
    assert balance(g, 'player') == money[0] - cost['coins']
    assert balance(g, account) == money[1] + cost['coins']
    assert temple(g)['city_id'] == original['id'] and temple(g)['address'] == address(g)
    assert len(g.building_state['records']) == 1  # no cloned original city
    assert state(g)['trust'] == 50 and not bonus(g)
    assert any(r['id'] == temple(g)['id'] for r in e.get_game(gid)['buildings']['rows'])
    saved = g.to_dict()
    with pytest.raises(ValueError, match='变化'):
        e.yaochi_action(gid, 'earth_build', old)
    assert e.store.load(gid).to_dict() == saved


@pytest.mark.parametrize('kind,trust', [('watch',60),('care',65),('teach',55)])
def test_actual_staged_duty_once_and_no_double_merit(village, kind, trust):
    e, gid = village
    build(e, gid)
    g = e._load(gid)
    age, opportunity, traces = g.player.age, g.player.opportunity, g.player.immortal_traces
    merit = g.yaochi_state.get('merit', 0), g.heavenly_court.get('player_merit', 0)
    fulfill(e, gid, kind)
    g = e._load(gid)
    assert g.player.age == age + 100
    assert g.player.opportunity == opportunity and g.player.immortal_traces == traces
    assert (g.yaochi_state.get('merit',0), g.heavenly_court.get('player_merit',0)) == merit
    assert state(g)['trust'] == trust and state(g)['allowance'] == 400
    assert state(g)['until'] == age + 500 and state(g)['completed'] == 1
    assert g.yaochi_state['westward']['settlement_years'] == 0
    with pytest.raises(ValueError, match='尚未用尽'):
        command(e, gid, 'accept', kind)
    with pytest.raises(ValueError, match='尚未完成'):
        command(e, gid, 'claim')


def test_careful_plan_trades_fifty_real_years_for_half_materials(village):
    e, gid = village
    build(e, gid)
    g = e._load(gid)
    start_age = g.player.age
    standard = bill(g, kind='watch')
    fulfill(e, gid, plan='careful')
    g = e._load(gid)
    assert g.player.age == start_age + 150
    assert state(g)['until'] == start_age + 500
    assert state(g)['trust'] == 60
    assert bill(g, kind='watch', careful=True)['coins'] == standard['coins'] // 2
    assert g.yaochi_state['westward']['settlement_years'] == 50


def test_ordinary_cultivation_single_trace_trial_and_no_boost_on_other_awards(village):
    e, gid = village
    build(e, gid)
    fulfill(e, gid)
    g = e._load(gid)
    before_rng, age = g.player.immortal_trace_rng, g.player.age
    from cultivation_life.system.immortal_cultivation import grant_trace_chance
    with patch('cultivation_life.system.opportunity.grant_trace_chance', wraps=grant_trace_chance) as traced:
        with patch('cultivation_life.engine.orchestration.advancement._finish_action_events', return_value=None):
            command(e, gid, 'cultivate')
        assert traced.call_count == 100
        assert all(c.kwargs['chance_multiplier'] == 1.3 for c in traced.call_args_list)
    g = e._load(gid)
    assert g.player.age == age + 100 and state(g)['allowance'] == 300
    assert g.player.immortal_trace_rng == (before_rng + 100*0x9E3779B97F4A7C15) & ((1<<64)-1)
    with patch('cultivation_life.system.opportunity.grant_trace_chance', wraps=grant_trace_chance) as traced:
        e._add_opportunity(g.player, 100)
        assert traced.call_args.kwargs['chance_multiplier'] == 1.
    assert state(g)['allowance'] == 300


def test_interruption_event_blocks_plan_and_cancel_then_recovers(village):
    e, gid = village
    build(e, gid)
    command(e, gid, 'accept', 'care')
    age = e._load(gid).player.age
    original = e._advance_world_year
    def interrupt(game, rng, news, **kwargs):
        result = original(game, rng, news, **kwargs)
        if game.player.age == age + 3:
            game.pending_event = e._instantiate_event(e.events_by_id['EVT_SECT_FIRST_WARNING_001'], game, random.Random(1))
            return False
        return result
    with patch.object(e, '_advance_world_year', side_effect=interrupt):
        command(e, gid, 'work')
    assert state(e._load(gid))['duty']['progress'] == 3
    for action in ['work', 'cancel']:
        with pytest.raises(ValueError, match='处理事件'):
            command(e, gid, action)
    e.choose(gid, 'acknowledge', event_id='EVT_SECT_FIRST_WARNING_001')
    work(e, gid)
    assert state(e._load(gid))['duty']['progress'] == 10
    command(e, gid, 'plan', 'standard')
    g = e._load(gid)
    funds = balance(g, 'player')
    command(e, gid, 'cancel')
    g = e._load(gid)
    assert state(g)['trust'] == 40 and not state(g).get('duty')
    assert balance(g, 'player') == funds and not state(g)['allowance']
    assert g.yaochi_state['westward']['settlement_years'] == 10


def test_suspend_disable_and_real_crossing_preserve_local_asset_and_expiry(village):
    e, gid = village
    build(e, gid)
    fulfill(e, gid)
    g = e._load(gid)
    until, identity, original = state(g)['until'], temple(g)['id'], copy.deepcopy(temple(g))
    command(e, gid, 'suspend')
    assert not bonus(e._load(gid))
    command(e, gid, 'resume')
    assert bonus(e._load(gid)) == .3
    with patch.dict(WORLD_SYSTEMS['yaochi_westward'], enabled=False):
        assert not bonus(e._load(gid))
        command(e, gid, 'suspend')
        with pytest.raises(ValueError, match='尚未启用'):
            command(e, gid, 'resume')
    command(e, gid, 'resume')
    g = e._load(gid)
    plan = e._plan_world_transition(g, 'spirit', 'sealed_descent', reason='地仙原址验证')
    e._apply_world_transition(g, plan)
    e.store.save(g)
    assert not bonus(g) and temple(g) == original
    plan = e._plan_world_transition(g, 'celestial', 'sealed_return', reason='返回原庙', arrival_location=original['address']['location_id'])
    e._apply_world_transition(g, plan)
    e.store.save(g)
    assert temple(g)['id'] == identity and state(g)['until'] == until
    g.player.age = until + 1  # expiry boundary fixture, not elapsed-work settlement
    assert not bonus(g) and public(g)['allowance'] == 0


def test_original_destroy_rebuild_cost_and_identity_do_not_reset_faith(village):
    e, gid = village
    build(e, gid)
    fulfill(e, gid)
    g = e._load(gid)
    saved = copy.deepcopy(state(g))
    identity = temple(g)['id']
    def choose(key):
        view = e.get_game(gid)
        return e.choose(gid, key, event_id=view['pending_event']['id'])
    e.building_action(gid, 'manage', building_id=identity)
    shown = choose('destroy')
    choose(next(c['id'] for c in shown['pending_event']['choices'] if c['id'].startswith('destroy:')))
    assert temple(e._load(gid))['status'] == 'destroyed'
    assert not bonus(e._load(gid))
    # Menus retain original event guards and quote; inspect exact original route.
    shown = choose('rebuild')
    confirm = next(c for c in shown['pending_event']['choices'] if c['id'].startswith('rebuild:'))
    assert confirm['enabled']
    g = e._load(gid)
    before = balance(g, 'player')
    choose(confirm['id'])
    choose('leave')
    g = e._load(gid)
    assert balance(g, 'player') == before - 5600000000
    assert temple(g)['id'] == identity and temple(g)['status'] == 'intact'
    assert state(g) == saved and bonus(g) == .3


def test_expiry_last_paid_year_and_city_permission_stop_bonus(village):
    e, gid = village
    build(e, gid)
    fulfill(e, gid)
    g = e._load(gid)
    # Put an already-earned allowance two years before its fixed deadline.
    state(g)['until'] = g.player.age + 2
    e.store.save(g)
    from cultivation_life.system.immortal_cultivation import grant_trace_chance
    with patch('cultivation_life.system.opportunity.grant_trace_chance', wraps=grant_trace_chance) as traced:
        with patch('cultivation_life.engine.orchestration.advancement._finish_action_events', return_value=None):
            command(e, gid, 'cultivate')
        assert [c.kwargs['chance_multiplier'] for c in traced.call_args_list] == [1.3]*2 + [1.]*98
    g = e._load(gid)
    assert state(g)['allowance'] == 398  # stored history, not spendable expired years
    assert public(g)['allowance'] == 0 and not bonus(g)
    fulfill(e, gid)
    from cultivation_life.system.earth_temple_rules import city
    from cultivation_life.system.building_projects import persist
    original = persist(g := e._load(gid), city(g))
    original['public'] = False
    e.store.save(g)
    assert not bonus(g)
    with pytest.raises(ValueError, match='使用许可'):
        command(e, gid, 'cultivate')
    original['public'] = True
    original['status'] = 'destroyed'
    e.store.save(g)
    with pytest.raises(ValueError, match='使用许可'):
        command(e, gid, 'accept', 'watch')


def test_build_rejects_ineligible_city_and_insufficient_money_without_asset(village):
    e, gid = village
    g = e._load(gid)
    spec = next(c for c in buildings_config()['cities']['celestial'] if c['population'] == 'cultivator')
    g.player.location_id = spec['location_id']
    e.store.save(g)
    view = e.get_game(gid)['yaochi']['earth']
    before = e.store.load(gid).to_dict()
    with pytest.raises(ValueError, match='凡人城或混居城'):
        command(e, gid, 'build', view['cities'][0]['id'])
    assert e.store.load(gid).to_dict() == before
    g = e._load(gid)
    g.player.location_id = next(c['location_id'] for c in buildings_config()['cities']['celestial'] if c['population']=='mixed')
    from cultivation_life.rules import remove_item
    remove_item(g.player, 'spirit_stone', balance(g, 'player'))
    e.store.save(g)
    view = e.get_game(gid)['yaochi']['earth']
    with pytest.raises(ValueError, match='材料不足'):
        command(e, gid, 'build', view['cities'][0]['id'])
    assert not temple(e._load(gid))
