"""Behavioral boundaries of the Guixu and war composition contracts."""
import copy
import random
from dataclasses import fields
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.models import GameState, Player
from cultivation_life.storage import SaveStore
from cultivation_life.system import guixu_system, war_system
from cultivation_life.system.guixu.calendar import _consume_guixu_days
from cultivation_life.system.guixu.dependencies import GuixuCalendarDependencies
from cultivation_life.system.war.dependencies import WarLifecycleDependencies, WarPeaceDependencies
from cultivation_life.system.war.lifecycle import _finish_war_by_morale
from cultivation_life.system.war.peace import _conclude_war_bundle, _generate_ai_peace_offer
from tools.check_module_dependencies import violations

ROOT = Path(__file__).resolve().parents[1]


def contract(kind, **overrides):
    unexpected = Mock(side_effect=AssertionError('Unexpected collaborator'))
    return kind(**({f.name: unexpected for f in fields(kind)} | overrides)), unexpected


def test_engine_no_longer_inherits_expedition_mixins():
    assert not {guixu_system.GuixuSystemMixin, war_system.WarSystemMixin} & set(GameEngine.__mro__)


@pytest.mark.parametrize('days,remaining,events', [(2, 1, ['assign']), (3, 0, ['assign', 'close']), (9, 0, ['assign', 'close'])])
def test_tide_deadline_assigns_loot_before_closing_without_engine(days, remaining, events):
    seen = []
    rng = random.Random(42)
    session = {'remaining_days': 3}
    deps, unexpected = contract(
        GuixuCalendarDependencies,
        _guixu_elapsed_days=lambda dungeon, session: 10 - session['remaining_days'],
        _assign_due_guixu_entries=lambda game, dungeon, cycle, elapsed, actual_rng: seen.append(('assign', elapsed, actual_rng)),
        _close_guixu_cycle=lambda game, dungeon, cycle, actual_rng: seen.append(('close', 10, actual_rng)),
    )
    _consume_guixu_days(deps, None, {'window_days': 10}, {}, session, days, rng)
    assert session['remaining_days'] == remaining
    assert [row[0] for row in seen] == events
    assert seen[0][1] == 10 - remaining
    assert all(row[2] is rng for row in seen)
    unexpected.assert_not_called()


def test_morale_collapse_generates_offer_once_and_preserves_score():
    offer = Mock(return_value={'budget': 76, 'demands': [{'label': 'Vassal'}]})
    log = Mock()
    deps, unexpected = contract(WarLifecycleDependencies,
        _append_war_log=log, _war_side_name=lambda *args: 'Loser',
        _player_war_side=lambda *args: 'attacker', _generate_ai_peace_offer=offer)
    war = {'status': 'active', 'morale': {'attacker': 0, 'defender': 40}, 'controller': 'player',
           'war_score': -76, 'kind': 'sect', 'attacker_id': 'a', 'defender_id': 'b'}
    assert _finish_war_by_morale(deps, None, war)
    assert (war['winner'], war['loser'], war['war_score']) == ('defender', 'attacker', -76)
    assert _finish_war_by_morale(deps, None, war)
    offer.assert_called_once_with(None, war, 'defender')
    assert log.call_count == 2
    unexpected.assert_not_called()


@pytest.mark.parametrize('score', [0, 19, 58, 76, 100])
def test_ai_demands_respect_score_budget_without_engine(score):
    deps, unexpected = contract(WarPeaceDependencies,
        _get_WAR_TERM_DEFS=lambda: war_system.WAR_TERM_DEFS,
        _war_total_power=lambda *args: 100, _war_entity_power=lambda *args: 100,
        _war_rules=lambda: {}, _available_warriors=lambda *args: [])
    war = {'kind': 'sect', 'attacker_id': 'a', 'defender_id': 'b', 'war_score': score}
    offer = _generate_ai_peace_offer(deps, SimpleNamespace(diplomacy_unit=7), war, 'attacker')
    assert offer['total_cost'] == sum(row['cost'] for row in offer['demands'])
    assert 0 <= offer['total_cost'] <= offer['budget'] == score
    assert all(row['target_power_id'] == 'b' for row in offer['demands'])
    unexpected.assert_not_called()


def test_peace_bundle_collects_resources_before_dissolving_and_finalizes_once():
    calls = []
    war = {'defender_id': 'b', 'logs': [{'text': ''}]}
    demands = [{'term': 'dissolve'}, {'term': 'stones'}]
    original = copy.deepcopy(demands)

    def conclude(game, war, term, side, **kwargs):
        calls.append((term, kwargs['finalize']))
        return term

    deps, unexpected = contract(WarPeaceDependencies, _conclude_war=conclude)
    _conclude_war_bundle(deps, None, war, demands, 'attacker')
    assert calls == [('stones', False), ('dissolve', True)]
    assert demands == original
    demands[0]['term'] = 'modified'
    assert war['peace_terms'] == original
    unexpected.assert_not_called()


def test_cached_contracts_follow_resource_method_and_config_replacements(tmp_path, monkeypatch):
    engine = GameEngine(ROOT, tmp_path / 'original')
    guixu, war = engine._guixu_dependencies, engine._war_dependencies
    replacement = SaveStore(tmp_path / 'replacement')
    maps, events = object(), {'replacement': {}}
    monkeypatch.setattr(engine, 'store', replacement)
    monkeypatch.setattr(engine, 'maps', maps)
    monkeypatch.setattr(engine, 'events_by_id', events)
    monkeypatch.setattr(engine, '_load', lambda key: key)
    for deps in (guixu.actions, war.actions, war.peace):
        assert deps.store is replacement
        assert deps._load('replaced') == 'replaced'
    assert guixu.calendar.maps is war.actions.maps is maps
    assert guixu.calendar.events_by_id is war.actions.events_by_id is events
    monkeypatch.setattr(engine, '_combat', lambda *args: 'replacement')
    assert guixu.encounters._combat(None) == war.combat._combat(None) == 'replacement'
    monkeypatch.setattr(guixu_system, 'MOVE_COSTS', {'custom': 8})
    monkeypatch.setattr(guixu_system, 'guixu_content_available', lambda: False)
    monkeypatch.setattr(war_system, 'WAR_TERM_DEFS', {'custom': ('Custom', 3)})
    assert guixu.actions.MOVE_COSTS == {'custom': 8}
    assert not guixu.state.guixu_content_available()
    assert war.peace.WAR_TERM_DEFS is war.presentation.WAR_TERM_DEFS is war_system.WAR_TERM_DEFS
    for module, deps in [(guixu_system, guixu.actions), (war_system, war.actions)]:
        monkeypatch.setattr(module, 'decode_rng', lambda *args: 'rng')
        assert deps.decode_rng(42, '') == 'rng'


def test_legacy_adapters_work_without_engine_and_keep_late_overrides():
    class LegacyGuixu(guixu_system.GuixuSystemMixin):
        @staticmethod
        def _guixu_definitions():
            return {}

    host = LegacyGuixu()
    game = GameState('legacy', 42, Player('Player', 'none'), '', '')
    host._ensure_guixu_state(game)
    assert game.guixu_state['cycles'] == {}
    host._guixu_definitions = lambda: {'late': {'period_years': 10, 'announce_lead_years': 1, 'treasure_pool': []}}
    host._ensure_guixu_state(game)
    assert 'late' in game.guixu_state['cycles']
    war = war_system.WarSystemMixin()
    assert war._coalition_ids({'coalitions': {'attacker': [{'id': 'a'}]}}, 'attacker') == ['a']


def test_subclass_super_dispatch_remains_available(tmp_path):
    class Specialized(GameEngine):
        def _guixu_relation_ids(self, game):
            return super()._guixu_relation_ids(game) | {'custom'}

        def _coalition_ids(self, war, side):
            return super()._coalition_ids(war, side) + ['custom']

    engine = Specialized(ROOT, tmp_path)
    game = GameState('subclass', 42, Player('Player', 'none'), '', '')
    assert 'custom' in engine._guixu_dependencies.npcs._guixu_relation_ids(game)
    assert engine._war_dependencies.diplomacy._coalition_ids({'coalitions': {'attacker': [{'id': 'a'}]}}, 'attacker') == ['a', 'custom']


@pytest.mark.parametrize('area', ['guixu', 'war'])
@pytest.mark.parametrize('target', ['facade', 'wiring'])
def test_algorithms_cannot_import_own_facade_or_wiring(area, target):
    source = f'cultivation_life.system.{area}.actions'
    destination = f'cultivation_life.system.{area}' + ('_system' if target == 'facade' else '.wiring')
    assert violations([(source, destination, 9)]) == [{'source': source, 'target': destination, 'line': 9}]
