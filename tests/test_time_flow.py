"""Time pipeline boundaries: exact phase order, interruption, and activity policies."""
import random
from dataclasses import fields
from pathlib import Path
from unittest.mock import Mock

import pytest

from cultivation_life.content_registry import WORLD_SYSTEMS
from cultivation_life.engine import GameEngine
from cultivation_life.engine.dependencies import AdvancementDependencies
from cultivation_life.engine.orchestration.advancement import _finish_action_events
from cultivation_life.models import GameState, Player
from cultivation_life.system.map_system import TravelPlan
from cultivation_life.time_dependencies import (
    ElapsedYearDependencies,
    TimeSettlementDependencies,
)
from cultivation_life.time_flow import (
    ACTION_TIME,
    TRAVEL_TIME,
    advance_elapsed_year,
    completed_action_units,
    settle_elapsed_time,
)
from tools.check_module_dependencies import violations

ROOT = Path(__file__).resolve().parents[1]
UNIT_PHASES = ['diplomacy', 'aftermath', 'court', 'intrigue']


def game_state():
    return GameState('time', 17, Player('Player', 'none', realm_index=1), '', '')


@pytest.mark.parametrize('encounters', [False, True])
@pytest.mark.parametrize('outcome', ['continue', 'event', 'world-death', 'erosion-death'])
def test_year_interruption_settles_erosion_only_when_still_alive(encounters, outcome):
    game, rng, news, calls = game_state(), random.Random(1), [], []
    age = game.player.age
    def annual(actual, actual_rng, actual_news, **kwargs):
        assert (actual, actual_rng, actual_news) == (game, rng, news)
        assert kwargs == ({} if encounters else {'encounters': False})
        calls.append('world')
        if outcome == 'world-death':
            game.player.alive = False
        if outcome == 'event':
            game.pending_event = {'id': 'interrupted'}
        return outcome not in {'event', 'world-death'}
    def erosion(actual, years):
        assert actual is game and years == 1
        calls.append('erosion')
        if outcome == 'erosion-death':
            game.player.alive = False
    deps = ElapsedYearDependencies(annual, erosion)
    assert advance_elapsed_year(deps, game, rng, news, encounters=encounters) is (outcome == 'continue')
    assert calls == (['world'] if outcome == 'world-death' else ['world', 'erosion'])
    assert game.player.age == age  # Aging remains at the activity's established position.


@pytest.mark.parametrize('elapsed,unit,expected', [(0, 5, 0), (1, 5, 1), (5, 5, 1), (6, 5, 2), (11, 5, 3), (10, 1, 10)])
def test_partial_units_round_up_without_creating_zero_year_work(elapsed, unit, expected):
    assert completed_action_units(elapsed, unit) == expected


@pytest.mark.parametrize('unit', [0, -1])
def test_invalid_unit_duration_is_rejected(unit):
    with pytest.raises(ValueError):
        completed_action_units(2, unit)


def settlement_ports(game, rng, calls, outcome):
    names = {
        '_advance_diplomacy_unit': 'diplomacy', '_advance_concubine_aftermath': 'aftermath',
        '_advance_heavenly_court_unit': 'court', '_advance_intrigue_unit': 'intrigue',
        '_advance_natal_artifact': 'artifact', '_advance_concubine_status': 'drain',
        '_advance_player_bounties': 'bounty', '_record_era_summary': 'summary',
        '_advance_auction_clock': 'auction', '_advance_exchange_clock': 'exchange',
        '_maybe_tianji_intelligence_event': 'intelligence',
    }
    def callback(name):
        def call(actual, *args):
            assert actual is game
            calls.append(name)
            for value in args:
                if isinstance(value, random.Random):
                    assert value is rng
            if outcome == name:
                game.player.alive = False
            if name == 'diplomacy':
                game.pending_event = {'id': 'pending'}
            if name in {'diplomacy', 'court', 'intrigue'}:
                return [name]
            if name in {'artifact', 'intelligence'}:
                return name
            if name == 'drain':
                assert args == (2,)
                return 3.0
        return call
    return TimeSettlementDependencies(**{key: callback(value) for key, value in names.items()})


@pytest.mark.parametrize('policy', [ACTION_TIME, TRAVEL_TIME])
@pytest.mark.parametrize('outcome', ['alive', 'entry', 'artifact', 'diplomacy', 'drain'])
def test_settlement_preserves_order_pending_events_and_death_boundaries(policy, outcome):
    game, rng, calls, news = game_state(), random.Random(2), [], []
    if outcome == 'entry':
        game.player.alive = False
    deps = settlement_ports(game, rng, calls, outcome)
    event = lambda: calls.append('events')
    settle_elapsed_time(deps, game, rng, news, action='rest' if policy is ACTION_TIME else 'travel',
                        units=2, start_age=game.player.age-6, policy=policy,
                        after_units=event if policy is ACTION_TIME else None)
    expected = (['artifact'] + (UNIT_PHASES + ['intelligence']) * 2 if policy is ACTION_TIME
                else UNIT_PHASES * 2 + ['artifact'])
    expected += ['drain', 'bounty'] + (['events'] if policy is ACTION_TIME else []) + ['summary']
    expected += ['auction', 'exchange'] * (2 if policy is ACTION_TIME else int(outcome == 'alive'))
    assert calls == expected
    assert any('抽走机缘 3.0' in item for item in news) is (policy is ACTION_TIME)


@pytest.mark.parametrize('policy', [ACTION_TIME, TRAVEL_TIME])
def test_zero_units_has_no_side_effects(policy):
    unexpected = Mock(side_effect=AssertionError('Zero time must not settle'))
    deps = TimeSettlementDependencies(**{field.name: unexpected for field in fields(TimeSettlementDependencies)})
    settle_elapsed_time(deps, game_state(), random.Random(1), [], action='rest', units=0,
                        start_age=0, policy=policy, after_units=unexpected)
    unexpected.assert_not_called()


def test_missing_required_action_hook_rejects_before_any_settlement():
    unexpected = Mock(side_effect=AssertionError('Must reject before side effects'))
    ports = {field.name: unexpected for field in fields(TimeSettlementDependencies)}
    ports['_maybe_tianji_intelligence_event'] = None
    with pytest.raises(RuntimeError, match='神机'):
        settle_elapsed_time(TimeSettlementDependencies(**ports), game_state(), random.Random(1), [],
                            action='rest', units=1, start_age=0, policy=ACTION_TIME)
    unexpected.assert_not_called()


EVENT_PRIORITY = [
    '_maybe_relationship_sanction', '_maybe_immortal_conversion_event', '_maybe_concubine_proposal',
    '_maybe_personal_revenge', '_maybe_probability_story_event', '_maybe_xiang_node_event',
    '_maybe_founded_sect_pressure', '_maybe_affinity_gift', '_maybe_faction_event',
]


@pytest.mark.parametrize('stop', range(len(EVENT_PRIORITY) + 1))
def test_action_events_preserve_priority_and_stop_after_first_event(stop):
    game, calls = game_state(), []
    unexpected = Mock(side_effect=AssertionError('Unrelated dependency invoked'))
    ports = {field.name: unexpected for field in fields(AdvancementDependencies)}
    def callback(name, index):
        def call(*args):
            calls.append(name)
            return index == stop
        return call
    ports.update({name: callback(name, index) for index, name in enumerate(EVENT_PRIORITY)})
    ports['_select_event'] = Mock(return_value={'id': 'fallback'})
    ports['_instantiate_event'] = Mock(return_value={'id': 'resolved'})
    _finish_action_events(AdvancementDependencies(**ports), game, 'rest', random.Random(1))
    assert calls == EVENT_PRIORITY[:stop+1]
    if stop == len(EVENT_PRIORITY):
        assert game.pending_event == {'id': 'resolved'}
    else:
        ports['_select_event'].assert_not_called()
    unexpected.assert_not_called()


@pytest.mark.parametrize('state', ['pending', 'captured'])
def test_action_events_do_not_overwrite_pending_or_offer_captor_unrelated_events(state):
    game = game_state()
    unexpected = Mock(side_effect=AssertionError('No unrelated events allowed'))
    ports = {field.name: unexpected for field in fields(AdvancementDependencies)}
    ports['_maybe_relationship_sanction'] = Mock(return_value=False)
    if state == 'pending':
        game.pending_event = {'id': 'existing'}
    else:
        game.player.ghost_captor = {'id': 'owner'}
    _finish_action_events(AdvancementDependencies(**ports), game, 'rest', random.Random(1))
    assert ports['_maybe_relationship_sanction'].call_count == (state == 'captured')
    unexpected.assert_not_called()


@pytest.mark.parametrize('activity', ['rest', 'travel'])
@pytest.mark.parametrize('stop', ['complete', 'event', 'death'])
def test_engine_time_entry_preserves_unit_basis_and_single_save(tmp_path, monkeypatch, activity, stop):
    engine, game, calls = GameEngine(ROOT, tmp_path), game_state(), []
    game.player.location_id = 'origin'
    store = Mock(lock=engine.store.lock)
    monkeypatch.setattr(engine, 'store', store)
    monkeypatch.setattr(engine, '_load', lambda key: game)
    monkeypatch.setattr(engine, 'present', lambda actual: actual)
    for contract in (engine._dependencies.advancement, engine._dependencies.time.elapsed_travel):
        for field in fields(contract):
            if field.name.startswith('_') and field.name not in {'_load', '_get_store', '_get_maps', '_advance_natal_artifact'}:
                monkeypatch.setattr(engine, field.name, Mock(return_value=[]))
    monkeypatch.setattr(engine, '_apply_action_resources', Mock())
    monkeypatch.setattr(engine, '_clear_market', Mock())
    monkeypatch.setattr(engine, '_monster_travel_multiplier', lambda *args: 1)
    monkeypatch.setattr(engine, '_advance_soul_erosion_time', Mock())
    monkeypatch.setattr(engine, '_maybe_tianji_intelligence_event', Mock(return_value=None))
    monkeypatch.setattr(engine, '_select_event', Mock(return_value=None))
    def annual(actual, rng, news, **kwargs):
        # Simulate a breakthrough in the first year; action keeps its starting
        # unit duration, while travel uses the arrival realm's duration.
        game.player.realm_index = 2
        calls.append('year')
        if stop == 'event':
            game.pending_event = {'id': 'interrupted'}
        if stop == 'death':
            game.player.alive = False
        return stop == 'complete'
    monkeypatch.setattr(engine, '_advance_world_year', annual)
    artifact = Mock(return_value=None)
    monkeypatch.setattr(engine, '_advance_natal_artifact', artifact)
    maps = Mock()
    maps.travel_plan.return_value = TravelPlan('origin', 'target', 11, 11, ('origin', 'target'), 'ok', '')
    maps.location.return_value = {'name': 'Location'}
    monkeypatch.setattr(engine, 'maps', maps)
    initial_age = game.player.age
    initial_unit = int(WORLD_SYSTEMS['time_units']['1'])
    if activity == 'travel':
        engine.travel_map(game.id, 'target')
        expected_years = 11 if stop == 'complete' else 1
        expected_units = completed_action_units(expected_years, int(WORLD_SYSTEMS['time_units']['2']))
        assert game.player.location_id == ('target' if stop == 'complete' else 'origin')
    else:
        engine.advance(game.id, 'rest', 3)
        expected_years = 3 * initial_unit if stop == 'complete' else 1
        expected_units = completed_action_units(expected_years, initial_unit)
    assert len(calls) == game.player.age - initial_age == expected_years
    if activity == 'rest' and stop == 'death':
        artifact.assert_not_called()
    else:
        artifact.assert_called_once_with(game, activity, expected_units)
    assert engine._advance_soul_erosion_time.call_count == (0 if stop == 'death' else expected_years)
    store.save.assert_called_once_with(game)


@pytest.mark.parametrize('target', ['engine', 'engine.orchestration.advancement', 'map_runtime', 'system.ghost_system'])
def test_shared_time_flow_cannot_import_callers(target):
    assert violations([('cultivation_life.time_flow', 'cultivation_life.' + target, 1)])
