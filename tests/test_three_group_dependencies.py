"""Independent execution and behavioral boundaries of the three migrated groups."""
import ast
import builtins
import dis
import importlib
import inspect
import random
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
from types import CodeType
from typing import get_type_hints
from unittest.mock import Mock

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.engine.orchestration.world_time import _advance_world_year, _finish_travel_time
from cultivation_life.models import GameState, Player
from cultivation_life.storage import SaveStore
from cultivation_life.system.cultivation_dependencies import CultivationCommitDependencies, ImmortalBodyDependencies
from cultivation_life.system.immortal_body_system import _immortal_body_action
from cultivation_life.system.immortal_cultivation import rules
from cultivation_life.system.merchant.dependencies import MerchantExecutionDependencies, MerchantSettlementDependencies
from cultivation_life.system.merchant.settlement import _merchant_refund
from cultivation_life.system.merchant_execution_system import _merchant_tick_order
from cultivation_life.time_dependencies import WorldYearDependencies, ElapsedTravelDependencies
from tools.check_module_dependencies import violations

ROOT = Path(__file__).resolve().parents[1]
MODULES = [
    'engine.orchestration.world_time', 'map_runtime', 'system.teleport_system',
    'system.merchant.state', 'system.merchant.catalog', 'system.merchant.calendar',
    'system.merchant.settlement', 'system.merchant.work', 'system.merchant.passage',
    'system.merchant.presentation', 'system.merchant_system',
    'system.merchant_commission_system', 'system.merchant_execution_system',
    'system.doctrine_system', 'system.doctrine_fusion_system', 'system.immortal_system',
    'system.immortal_body_system', 'system.immortal_aperture', 'system.cultivation_session',
    'system.upper_voisinage',
]
REMOVED = {'MapTravelMixin', 'TeleportMixin', 'MerchantSystemMixin', 'MerchantCommissionMixin',
           'MerchantExecutionMixin', 'DoctrineSystemMixin', 'DoctrineFusionMixin',
           'ImmortalCultivationMixin', 'ImmortalBodyMixin', 'ImmortalApertureMixin'}


def contract(kind, **overrides):
    unexpected = Mock(side_effect=AssertionError('Unexpected collaborator'))
    return kind(**({f.name: unexpected for f in fields(kind)} | overrides)), unexpected


def game_state():
    game = GameState('independent', 42, Player('Player', 'none'), '', '')
    game.player.lifespan = None
    return game


def global_names(code):
    for instruction in dis.get_instructions(code):
        if instruction.opname == 'LOAD_GLOBAL':
            yield instruction.argval
    for child in code.co_consts:
        if isinstance(child, CodeType):
            yield from global_names(child)


def test_engine_no_longer_inherits_any_of_the_three_groups():
    assert not REMOVED & {cls.__name__ for cls in GameEngine.__mro__}


@pytest.mark.parametrize('name', MODULES)
def test_operations_have_real_globals_and_only_declared_dependencies(name):
    module = importlib.import_module('cultivation_life.' + name)
    assert not REMOVED & vars(module).keys()
    for _, function in inspect.getmembers(module, inspect.isfunction):
        if function.__module__ != module.__name__:
            continue
        assert function.__globals__ is vars(module)
        assert not {'self', 'engine', 'host'} & inspect.signature(function).parameters.keys()
        for symbol in global_names(function.__code__):
            assert symbol in vars(module) or hasattr(builtins, symbol), (function.__name__, symbol)
        if 'deps' not in inspect.signature(function).parameters:
            continue
        kind = get_type_hints(function)['deps']
        declared = {f.name for f in fields(kind)} | {k for k, v in vars(kind).items() if isinstance(v, property)}
        for node in ast.walk(ast.parse(inspect.getsource(function))):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == 'deps':
                assert node.attr in declared, (function.__name__, node.attr)


ANNUAL_ORDER = [
    '_advance_buddhist_year', '_advance_merchant_year', '_advance_sage_year',
    '_advance_ghost_phase_two_year', '_advance_monster_bloodline_year', '_resolve_breakthroughs',
    '_check_tribulation', '_annual_sect_update', '_annual_world_npc_update',
    '_annual_demonic_update', '_annual_spirit_field_update', '_resolve_breakthroughs',
    '_advance_guixu_calendar', '_maybe_wanted_encounter', '_maybe_race_war_ambush',
    '_maybe_artifact_synthesis', '_maybe_mortal_root_completion',
]


@pytest.mark.parametrize('stop', [None, 5, 6, 9, 11, 12, 13, 14, 15, 16])
def test_annual_phases_preserve_order_rng_and_interruption_without_engine(stop):
    game, rng, seen, news = game_state(), random.Random(91), [], []
    list_hooks = {'_advance_sage_year', '_annual_sect_update', '_annual_world_npc_update'}

    def callback(name):
        def call(*args):
            seen.append(name)
            for arg in args:
                if isinstance(arg, random.Random):
                    assert arg is rng
            stopping = len(seen) - 1 == stop
            if stopping and name == '_annual_demonic_update':
                game.player.alive = False
            elif stopping and name in {'_resolve_breakthroughs', '_check_tribulation'}:
                game.pending_event = {'id': 'interrupt'}
            if name in list_hooks:
                return [name]
            return stopping
        return call

    def advance_researchers(actual):
        assert actual is game
        # M2 civilian work runs only after the original NPC annual settlement.
        # Keep the legacy callback list and interruption indices unchanged.
        assert seen == ANNUAL_ORDER[:9]

    researchers = Mock(side_effect=advance_researchers)
    def advance_freight(actual):
        assert actual is game and seen == []
    freight = Mock(side_effect=advance_freight)
    deps, unexpected = contract(WorldYearDependencies,
        **{name: callback(name) for name in set(ANNUAL_ORDER)}, advance_researchers=researchers,
        advance_caravans=freight)
    assert _advance_world_year(deps, game, rng, news) is (stop is None)
    # Existing yearly semantics settle fields after demonic consequences, then
    # check death. Preserve that ordering instead of introducing a new rule.
    end = None if stop is None else stop + (2 if stop == 9 else 1)
    assert seen == ANNUAL_ORDER[:end]
    assert news == [name for name in seen if name in list_hooks]
    freight.assert_called_once_with(game)
    if stop is None or stop >= 9:
        researchers.assert_called_once_with(game)
    else:
        researchers.assert_not_called()
    unexpected.assert_not_called()


def test_lifespan_stops_before_world_npcs_and_demonic_updates():
    game = game_state()
    game.player.lifespan = game.player.age
    die = Mock(side_effect=lambda *args: setattr(game.player, 'alive', False))
    permitted = {name: Mock(return_value=[]) for name in ANNUAL_ORDER[:7]}
    freight = Mock()
    deps, unexpected = contract(WorldYearDependencies, **permitted, _die=die, advance_caravans=freight)
    assert not _advance_world_year(deps, game, random.Random(1), [])
    die.assert_called_once_with(game, '寿元已尽', 'SYS_LIFESPAN')
    freight.assert_called_once_with(game)
    unexpected.assert_not_called()


def test_elapsed_travel_reuses_rng_and_does_not_run_clocks_after_death():
    game, rng, seen = game_state(), random.Random(17), []
    game.player.age += 2
    game.player.alive = False
    def callback(name):
        def call(*args):
            seen.append(name)
            for arg in args:
                if isinstance(arg, random.Random):
                    assert arg is rng
            return []
        return call
    names = {'_advance_diplomacy_unit', '_advance_concubine_aftermath', '_advance_heavenly_court_unit',
             '_advance_intrigue_unit', '_advance_natal_artifact', '_advance_concubine_status', '_advance_player_bounties'}
    deps, unexpected = contract(ElapsedTravelDependencies, **{name: callback(name) for name in names})
    _finish_travel_time(deps, game, game.player.age - 2, 'celestial', 1, [], rng)
    assert seen == ['_advance_diplomacy_unit', '_advance_concubine_aftermath',
                    '_advance_heavenly_court_unit', '_advance_intrigue_unit'] * 2 + [
                    '_advance_natal_artifact', '_advance_concubine_status', '_advance_player_bounties']
    unexpected.assert_not_called()


def test_merchant_refund_is_once_only_without_engine_or_store():
    game = game_state()
    order = {'status': 'working', 'principal': 75, 'fee': 9, 'name': 'Order'}
    notice, log = Mock(), Mock()
    deps, unexpected = contract(MerchantSettlementDependencies, _merchant_notice=notice, _merchant_log=log)
    _merchant_refund(deps, game, order, 'failed', '失联', 5)
    _merchant_refund(deps, game, order, 'failed', '失联', 5)
    assert sum(i.quantity for i in game.player.inventory if i.id == 'spirit_stone') == 80
    assert order['status'] == 'failed'
    assert order['refund_principal'] == 75 and order['refund_fee'] == 5
    notice.assert_called_once()
    log.assert_called_once()
    unexpected.assert_not_called()


def test_order_delivery_precedes_completion_and_reserve_update():
    game = game_state()
    order = {'status': 'working', 'kind': 'intel', 'name': 'Order', 'principal': 75, 'fee': 9,
             'started_age': 0, 'posted_age': 0, 'finish_age': 2, 'deadline': 10,
             'execution_stage': 3, 'world': 'human', 'alliance_id': 'a'}
    game.player.age = 2
    alliance = {'reserves': 100}
    def deliver(game, order):
        assert order['status'] == 'working' and alliance['reserves'] == 100
        order['delivery'] = 'done'
    deps, unexpected = contract(MerchantExecutionDependencies,
        _merchant_deliver_order=Mock(side_effect=deliver), _merchant_alliance=lambda *args: alliance,
        _merchant_log=Mock(), _merchant_notice=Mock())
    _merchant_tick_order(deps, game, order)
    assert (order['status'], order['progress'], alliance['reserves']) == ('completed', 1, 116)
    deps._merchant_deliver_order.assert_called_once_with(game, order)
    unexpected.assert_not_called()


def test_body_selection_uses_shared_commit_without_cultivation_parent(tmp_path):
    game, store = game_state(), SaveStore(tmp_path)
    key = rules()['body']['manuals'][0]['id']
    game.player.immortal_body = {'manuals': [key], 'level': 7, 'failures': 3}
    present = Mock(side_effect=lambda game: {'selected': game.player.immortal_body['active_manual']})
    deps = ImmortalBodyDependencies(CultivationCommitDependencies(present=present, _get_store=lambda: store))
    assert _immortal_body_action(deps, game, 'select_body_manual', key) == {'selected': key}
    saved = store.load(game.id)
    assert saved.player.immortal_body['level'] == 7 and saved.player.immortal_body['failures'] == 3
    assert saved.history[-1].event_id == 'SYS_IMMORTAL_CULTIVATION'
    present.assert_called_once_with(game)


def test_grouped_ports_remain_late_bound_and_cannot_gain_hidden_attributes(tmp_path, monkeypatch):
    engine = GameEngine(ROOT, tmp_path / 'first')
    time, merchant, cultivation = engine._dependencies.time, engine._dependencies.merchant, engine._dependencies.cultivation
    replacement, maps = SaveStore(tmp_path / 'second'), object()
    monkeypatch.setattr(engine, 'store', replacement)
    monkeypatch.setattr(engine, 'maps', maps)
    monkeypatch.setattr(engine, '_load', lambda key: key)
    for deps in [time.travel, time.teleport, merchant.actions, merchant.commissions, cultivation.actions, cultivation.aperture]:
        assert deps.store is replacement
    for deps in [time.travel, time.teleport, merchant.actions, merchant.state, merchant.calendar, merchant.view]:
        assert deps.maps is maps
    assert cultivation.session._load('replacement') == 'replacement'
    assert cultivation.body.commit.store is cultivation.fusion.commit.store is replacement
    monkeypatch.setattr(engine, '_advance_world_year', lambda *args, **kwargs: 'replaced')
    assert time.travel.year._advance_world_year(None) == merchant.work._advance_world_year(None) == 'replaced'
    with pytest.raises((FrozenInstanceError, TypeError, AttributeError)):
        cultivation.body.engine = engine


@pytest.mark.parametrize('source,target', [
    ('system.merchant.settlement', 'system.merchant_system'),
    ('system.merchant.settlement', 'system.merchant_execution_system'),
    ('system.cultivation_session', 'system.immortal_system'),
    ('system.immortal_body_system', 'system.immortal_system'),
    ('system.doctrine_fusion_system', 'system.immortal_system'),
    ('engine.orchestration.world_time', 'map_runtime'),
    ('time_dependencies', 'engine'),
    ('system.cultivation_dependencies', 'system.immortal_body_system'),
])
def test_new_boundaries_reject_reverse_imports(source, target):
    source, target = 'cultivation_life.' + source, 'cultivation_life.' + target
    assert violations([(source, target, 7)]) == [dict(source=source, target=target, line=7)]
