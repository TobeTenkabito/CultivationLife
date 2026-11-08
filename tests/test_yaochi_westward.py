"""Real commands, escrow conservation, interruption and unique training outcomes."""
import copy
import random
from unittest.mock import patch

import pytest

from test_immortal_cultivation import prepared
from cultivation_life.content_registry import WORLD_SYSTEMS
from cultivation_life.rules import add_item, max_hp, max_mp
from cultivation_life.system.yaochi_rules import config
from cultivation_life.system.yaochi_westward import public, quotes
from cultivation_life.system.westward_finance import balance, BACKGROUND, YAOCHI, COURT
from cultivation_life.system.westward_rules import project
from cultivation_life.system.immortal_body_system import quantity


@pytest.fixture
def pool(prepared):
    e, g, _ = prepared
    g.player.location_id = config()['location_id']
    g.player.body_training = 100
    g.player.immortal_body.update(level=20, manuals=['jade_marrows'], active_manual='jade_marrows')
    g.yaochi_state.update(merit=100000, earned=100000)
    g.heavenly_court['player_merit'] = 50
    g.settings.update(silent_events=True, combat_popup=False, court_election_popup=False)
    g.player.nascent_state.pop('crisis', None)
    e.store.save(g)
    e._load(g.id)
    return e, g.id


def quote(e, gid, key='trace'):
    return next(r for r in e.get_game(gid)['yaochi']['westward']['services'] if r['id'] == key)


def token(e, gid):
    return e.get_game(gid)['yaochi']['westward']['project']['token']


def start(e, gid, key='trace', currency='merit'):
    return e.yaochi_action(gid, 'westward_start_' + currency, quote(e, gid, key)['token'])


def complete(e, gid):
    # Suppress unrelated ambient encounters, not annual time, fiscal or lifecycle settlement.
    with patch('cultivation_life.engine.orchestration.advancement._finish_action_events', return_value=None):
        for _ in range(150):
            shown = e.get_game(gid)
            if shown['pending_event']:
                pytest.fail('Unexpected event despite silent fixture: ' + str(shown['pending_event']['id']))
            row = shown['yaochi']['westward']['project']
            if row['progress'] >= row['years']:
                return e.yaochi_action(gid, 'westward_claim', row['token'])
            e.yaochi_action(gid, 'westward_work', row['token'])
    pytest.fail('Project failed to finish')


def test_public_is_read_only_and_quotes_show_actual_costs(pool):
    e, gid = pool
    g = e._load(gid)
    before = copy.deepcopy(g.to_dict())
    for _ in range(3):
        view = public(g)
        assert view['qualification'] == 50 and not view['adopted']
        assert next(r for r in view['services'] if r['id'] == 'trace')['price'] == 400
        assert next(r for r in view['services'] if r['id'] == 'light_kun')['materials'] == {'great_sun_divine_light': 6}
    assert g.to_dict() == before


def test_adoption_and_original_awards_share_balance_once(pool):
    e, gid = pool
    e.yaochi_action(gid, 'westward_adopt')
    e.yaochi_action(gid, 'exchange_court_merit', amount=3)
    g = e._load(gid)
    assert g.heavenly_court['player_merit'] == 53
    assert g.heavenly_court['merit_account']['available'] == 53
    with pytest.raises(ValueError, match='已经确认'):
        e.yaochi_action(gid, 'westward_adopt')
    start(e, gid, currency='court')
    g = e._load(gid)
    assert g.heavenly_court['player_merit'] == 53
    assert g.heavenly_court['merit_account']['available'] == 43
    e.yaochi_action(gid, 'westward_cancel', token(e, gid))
    assert e._load(gid).heavenly_court['merit_account']['available'] == 53


def test_escrow_funded_from_original_accounts_and_cancel_restores_exactly(pool):
    e, gid = pool
    e.yaochi_action(gid, 'westward_adopt')
    g = e._load(gid)
    original = {a: balance(g, a) for a in (BACKGROUND, COURT, YAOCHI)}
    start(e, gid, currency='court')
    g = e._load(gid)
    assert balance(g, BACKGROUND) == original[BACKGROUND] - 100000
    assert balance(g, COURT) == original[COURT]
    assert balance(g, project(g)['escrow']) == 100000
    assert g.heavenly_court['westward_budget']['committed'] == 100000
    e.yaochi_action(gid, 'westward_cancel', token(e, gid))
    g = e._load(gid)
    assert {a: balance(g, a) for a in original} == original
    assert not any(k.startswith('escrow:yaochi-westward') for k in g.economy_v2['accounts'])
    assert g.heavenly_court['westward_budget']['committed'] == 0


@pytest.mark.parametrize('cause', ['money', 'budget', 'missing', 'event', 'location', 'sealed', 'possession', 'crisis'])
def test_invalid_commands_are_atomic(pool, cause):
    e, gid = pool
    e.yaochi_action(gid, 'westward_adopt')
    g = e._load(gid)
    if cause == 'money': g.economy_v2['accounts'][BACKGROUND]['balance'] = 0
    elif cause == 'budget':
        b = public(g)['budget']
        g.heavenly_court['westward_budget'] = dict(window=b['window'], cap=0, committed=0)
    elif cause == 'missing': pass
    elif cause == 'event': g.pending_event = e._instantiate_event(e.events_by_id['EVT_SECT_FIRST_WARNING_001'], g, random.Random(1))
    elif cause == 'location': g.player.location_id = 'celestial_capital'
    elif cause == 'sealed': g.player.cultivation_suppression = {'realm_index': 8}
    elif cause == 'possession':
        g.player.ghost_host_body = {'id': 'test-host', 'realm_index': 9}
        g.player.ghost_core_state = {}
    elif cause == 'crisis': g.player.nascent_state.update(crisis='possession', depleted=True)
    e.store.save(g)
    # Use the original public engine to normalize before measuring the rejected command.
    g = e._load(gid)
    q = next(r for r in quotes(g) if r['id'] == ('body' if cause == 'missing' else 'trace'))
    before = e.store.load(gid).to_dict()
    with pytest.raises(ValueError):
        e.yaochi_action(gid, 'westward_start_court', q['token'])
    assert e.store.load(gid).to_dict() == before


def test_trace_actual_work_no_ordinary_gain_and_no_duplicate_claim(pool):
    e, gid = pool
    g = e._load(gid)
    age, traces, opportunity = g.player.age, g.player.immortal_traces, g.player.opportunity
    start(e, gid)
    complete(e, gid)
    g = e._load(gid)
    assert g.player.age == age + 100
    assert g.player.immortal_traces == traces + 45
    assert g.player.opportunity == opportunity
    assert g.yaochi_state['merit'] == 99600
    assert g.yaochi_state['earned'] == 100000
    assert not project(g)
    with pytest.raises(ValueError, match='记录已经变化'):
        e.yaochi_action(gid, 'westward_claim', 'old')


def test_old_quotes_and_duplicate_work_rejected_without_charge(pool):
    e, gid = pool
    old = quote(e, gid)['token']
    start(e, gid)
    before = e.store.load(gid).to_dict()
    with pytest.raises(ValueError, match='报价已变化'):
        e.yaochi_action(gid, 'westward_start_merit', old)
    assert e.store.load(gid).to_dict() == before
    old = token(e, gid)
    complete(e, gid)
    with pytest.raises(ValueError, match='记录已经变化'):
        e.yaochi_action(gid, 'westward_work', old)


def test_body_target_packs_then_real_ten_years_and_shared_outcome(pool):
    e, gid = pool
    q = quote(e, gid, 'body')
    e.yaochi_action(gid, 'westward_supply_merit', q['token'])
    g = e._load(gid)
    q = quote(e, gid, 'body')
    assert not q['start_reason'] and q['supply']['items'] == []
    before = {k: quantity(g.player, k) for k in q['materials']}
    age = g.player.age
    court_unit = g.heavenly_court['unit']
    start(e, gid, 'body')
    with pytest.raises(ValueError, match='已有瑶池专修'):
        e.immortal_action(gid, 'train_body')
    with pytest.raises(ValueError, match='已有瑶池专修'):
        e.immortal_action(gid, 'select_body_manual', supply_id='jade_marrows')
    complete(e, gid)
    g = e._load(gid)
    assert g.player.age == age + 10
    assert g.heavenly_court['unit'] == court_unit
    assert g.yaochi_state['westward']['settlement_years'] == 10
    assert (g.player.immortal_body['level'], g.player.immortal_body.get('failures', 0)) in [(21, 0), (20, 1)]
    assert all(quantity(g.player, k) == before[k] - n for k, n in q['materials'].items())


def test_light_uses_discounted_original_material_and_original_rank(pool):
    e, gid = pool
    g = e._load(gid)
    add_item(g.player, 'great_sun_divine_light', 20)
    e.store.save(g)
    start(e, gid, 'light_kun')
    assert quantity(e._load(gid).player, 'great_sun_divine_light') == 14
    with pytest.raises(ValueError, match='已有瑶池专修'):
        e.immortal_action(gid, 'train_divine_light', axis='kun', expected_level=0)
    complete(e, gid)
    g = e._load(gid)
    assert g.player.immortal_body['divine_lights']['kun'] == 1
    assert quantity(g.player, 'great_sun_divine_light') == 14
    assert g.yaochi_state['merit'] == 100000


def test_disabled_dlc_can_refund_but_never_progress(pool):
    e, gid = pool
    start(e, gid)
    with patch.dict(WORLD_SYSTEMS['yaochi_westward'], enabled=False):
        with pytest.raises(ValueError, match='尚未启用'):
            e.yaochi_action(gid, 'westward_work', token(e, gid))
        e.yaochi_action(gid, 'westward_cancel', token(e, gid))
    g = e._load(gid)
    assert g.yaochi_state['merit'] == 100000 and not project(g)


def test_viewing_and_ordinary_time_do_not_progress_reservation(pool):
    e, gid = pool
    start(e, gid)
    e.advance(gid, 'rest', 1)
    g = e._load(gid)
    assert project(g)['progress'] == 0
    before = copy.deepcopy(g.to_dict())
    for _ in range(5): public(g)
    assert g.to_dict() == before


def test_real_interruption_partial_refund_and_fiscal_conservation(pool):
    e, gid = pool
    e.yaochi_action(gid, 'westward_adopt')
    start(e, gid, currency='court')
    g = e._load(gid)
    age, traces = g.player.age, g.player.immortal_traces
    original = e._advance_world_year
    def interrupt(game, rng, news, **kwargs):
        result = original(game, rng, news, **kwargs)
        if game.player.age == age + 3:
            game.pending_event = e._instantiate_event(e.events_by_id['EVT_SECT_FIRST_WARNING_001'], game, random.Random(1))
            return False
        return result
    with patch.object(e, '_advance_world_year', side_effect=interrupt):
        e.yaochi_action(gid, 'westward_work', token(e, gid))
    g = e._load(gid)
    assert project(g)['progress'] == 3 and g.player.immortal_traces == traces + 1
    with pytest.raises(ValueError, match='处理事件'):
        e.yaochi_action(gid, 'westward_cancel', token(e, gid))
    e.choose(gid, 'acknowledge', event_id='EVT_SECT_FIRST_WARNING_001')
    g = e._load(gid)
    before = {a: balance(g, a) for a in (BACKGROUND, YAOCHI, COURT)}
    e.yaochi_action(gid, 'westward_cancel', token(e, gid))
    g = e._load(gid)
    assert balance(g, BACKGROUND) == before[BACKGROUND] + 97000
    assert balance(g, YAOCHI) == before[YAOCHI] + 3000
    assert balance(g, COURT) == before[COURT]
    assert g.heavenly_court['merit_account']['available'] == 49
    assert g.heavenly_court['player_merit'] == 50
    assert g.heavenly_court['westward_budget']['committed'] == 3000


def test_crossing_preserves_unique_project_and_requires_return_to_original_site(pool):
    e, gid = pool
    start(e, gid)
    g = e._load(gid)
    held = copy.deepcopy(project(g))
    # Exercise the actual shared movement commit, not a direct world assignment.
    plan = e._plan_world_transition(g, 'spirit', 'sealed_descent', reason='专修暂停状态验收')
    e._apply_world_transition(g, plan)
    e.store.save(g)
    with pytest.raises(ValueError, match='亲临'):
        e.yaochi_action(gid, 'westward_work', 'stale')
    g = e._load(gid)
    assert project(g) == held
    plan = e._plan_world_transition(g, 'celestial', 'sealed_return', arrival_location=config()['location_id'], reason='回原瑶池验收')
    e._apply_world_transition(g, plan)
    e.store.save(g)
    assert project(e._load(gid)) == held
    e.yaochi_action(gid, 'westward_cancel', token(e, gid))
    assert e._load(gid).yaochi_state['merit'] == 100000


def test_paid_project_survives_serialization_and_failed_body_preserves_pity(pool):
    e, gid = pool
    q = quote(e, gid, 'body')
    e.yaochi_action(gid, 'westward_supply_merit', q['token'])
    start(e, gid, 'body')
    g = e.store.load(gid)
    from cultivation_life.models import GameState
    assert project(GameState.from_dict(g.to_dict())) == project(g)
    with patch('cultivation_life.system.yaochi_westward.decode_rng') as decode:
        rng = random.Random(2)  # First draw .956, above this paid quote's .76.
        decode.return_value = rng
        complete(e, gid)
    g = e.store.load(gid)
    assert g.player.immortal_body['level'] == 20
    assert g.player.immortal_body['failures'] == 1
    assert quote(e, gid, 'body')['chance'] == pytest.approx(.81)
