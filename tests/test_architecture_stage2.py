"""Capabilities, effect order, and detached projections of the second stage."""
import copy
from dataclasses import FrozenInstanceError, fields
import inspect
from pathlib import Path
import random
from typing import Callable, get_args, get_origin, get_type_hints
from unittest.mock import Mock, patch

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.engine.actions.exploration import ExplorationDependencies, WorldMoveDependencies
from cultivation_life.engine.dependencies import SessionPreparationDependencies, ViewPreparationDependencies
from cultivation_life.engine.engine_persistence import prepare_session
from cultivation_life.engine.orchestration.response import prepare_response
from cultivation_life.engine.persistence import dependencies as preparation_contracts
from cultivation_life.engine.presentation.projection import PreparedGameView, project_game
from cultivation_life.engine.response_dependencies import ResponseDependencies
from cultivation_life.engine.world import regions
from cultivation_life.models import GameState, Player
from cultivation_life.regional_context import CalendarGame
from cultivation_life.regional_dependencies import RegionalDependencies
from cultivation_life.regional_ports import RegionSynchronizationPort
from cultivation_life.runtime import encode_rng
from cultivation_life.storage import SaveStore
from cultivation_life.time_dependencies import (
    WorldYearDependencies, ElapsedYearDependencies, MapTravelDependencies,
    TeleportDependencies, TimeSettlementDependencies,
)
from tools.check_module_dependencies import violations


ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = [RegionalDependencies, ResponseDependencies, ViewPreparationDependencies,
    SessionPreparationDependencies, ExplorationDependencies, WorldMoveDependencies,
    WorldYearDependencies, ElapsedYearDependencies, MapTravelDependencies,
    TeleportDependencies, TimeSettlementDependencies,
    *[kind for kind in vars(preparation_contracts).values()
      if inspect.isclass(kind) and kind.__module__ == preparation_contracts.__name__]]


def assert_explicit_callbacks(annotation):
    arguments = get_args(annotation)
    if get_origin(annotation) in {get_origin(Callable[[], None])}:
        assert arguments[0] is not Ellipsis
    elif inspect.isclass(annotation) and getattr(annotation, '_is_protocol', False):
        call = annotation.__dict__.get('__call__')
        if call:
            assert all(p.kind not in {p.VAR_POSITIONAL, p.VAR_KEYWORD}
                       for p in inspect.signature(call).parameters.values())
            hints = get_type_hints(call)
            assert 'return' in hints
            assert set(inspect.signature(call).parameters) - {'self'} <= hints.keys()
    else:
        for argument in arguments:
            assert_explicit_callbacks(argument)


@pytest.mark.parametrize('contract', CONTRACTS, ids=lambda kind: kind.__name__)
def test_critical_contracts_declare_callback_arguments_and_results(contract):
    for annotation in get_type_hints(contract).values():
        assert_explicit_callbacks(annotation)


@pytest.mark.parametrize('source,target', [
    ('engine.presentation.projection', 'models'),
    ('engine.presentation.projection', 'storage'),
    ('engine.presentation.projection', 'engine.engine_presentation'),
    ('engine.world.regions', 'engine'),
    ('engine.world.regions', 'engine.dependencies'),
    ('engine.world.regions', 'engine.composition.regions'),
    ('regional_dependencies', 'engine'),
    ('regional_dependencies', 'storage'),
])
def test_lifecycle_layers_cannot_regain_broader_services(source, target):
    source, target = 'cultivation_life.' + source, 'cultivation_life.' + target
    assert violations([(source, target, 9)]) == [dict(source=source, target=target, line=9)]


def test_preparation_and_movement_have_no_commit_or_projection_capability():
    for contract in [RegionalDependencies, WorldMoveDependencies, SessionPreparationDependencies,
                     ViewPreparationDependencies]:
        names = {field.name for field in fields(contract)}
        assert not names & {'store', '_get_store', 'save', 'load', 'present', 'commit'}
    assert get_type_hints(prepare_session)['deps'] is SessionPreparationDependencies
    assert_explicit_callbacks(RegionSynchronizationPort)


def test_critical_composition_callbacks_expose_their_real_arguments(tmp_path):
    engine = GameEngine(ROOT, tmp_path)
    deps = engine._dependencies
    contracts = [deps.regions, deps.response, deps.view_preparation,
        deps.time.world_year, deps.time.travel, deps.time.travel.year,
        deps.time.teleport, deps.time.elapsed_travel,
        *[getattr(deps.persistence_runtime, field.name)
          for field in fields(SessionPreparationDependencies)]]
    for contract in contracts:
        for field in fields(contract):
            callback = getattr(contract, field.name)
            if callable(callback):
                assert all(parameter.kind not in {parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD}
                    for parameter in inspect.signature(callback).parameters.values()), field.name


@pytest.mark.parametrize('moved', [False, True])
def test_response_preserves_settlement_commit_and_preparation_order(tmp_path, moved):
    store = SaveStore(tmp_path)
    game = GameState('order', 17, Player('Original', 'none'), '', '')
    store.save(game)
    original = store._path(game.id).read_bytes()
    seen = []

    def settle(actual):
        assert actual is game
        seen.append('settle')
        if moved:
            actual.player.fame += 1
        return moved

    def commit(actual):
        seen.append('commit')
        store.save(actual)

    def prepare(actual):
        seen.append('prepare')
        actual.player.mp += 3
        return dict(player=dict(name=actual.player.name, mp=actual.player.mp))

    prepared = prepare_response(ResponseDependencies(settle, commit, prepare), game)
    assert seen == (['settle', 'commit', 'prepare'] if moved else ['settle', 'prepare'])
    assert project_game(prepared)['player']['mp'] == game.player.mp
    # Preserve the existing boundary commit before the legacy lazy view repairs.
    assert store.load(game.id).player.mp == game.player.mp - 3
    if not moved:
        assert store._path(game.id).read_bytes() == original


def test_failed_boundary_commit_never_runs_view_preparation():
    game = GameState('failure', 17, Player('Original', 'none'), '', '')
    prepare = Mock(side_effect=AssertionError('View preparation ran after a failed commit'))
    deps = ResponseDependencies(lambda game: True, Mock(side_effect=OSError('Disk failed')), prepare)
    with pytest.raises(OSError, match='Disk failed'):
        prepare_response(deps, game)
    prepare.assert_not_called()


def test_prepared_snapshot_rejects_live_objects_and_cannot_be_modified():
    game = GameState('snapshot', 17, Player('Original', 'none'), '', '')
    with pytest.raises(TypeError):
        PreparedGameView(dict(game=game))
    with pytest.raises(TypeError):
        project_game(game)
    payload = dict(rows=[dict(value=1)], coordinates=(1, 2))
    prepared = PreparedGameView(payload)
    payload['rows'][0]['value'] = 99
    with pytest.raises(TypeError):
        prepared._payload['rows'][0]['value'] = 10
    with pytest.raises((FrozenInstanceError, TypeError)):
        prepared.extra = 'hidden'
    first = project_game(prepared)
    first['rows'][0]['value'] = 100
    assert project_game(prepared) == dict(rows=[dict(value=1)], coordinates=(1, 2))


@pytest.mark.parametrize('path', ['dao', 'demonic', 'ghost', 'monster', 'buddhist', 'confucian'])
def test_real_prepared_projection_cannot_load_settle_save_or_award_again(tmp_path, path):
    engine = GameEngine(ROOT, tmp_path)
    identity = engine.create_game('Projection', 'supreme_metal', path, 17,
        monster_species_id='fox' if path == 'monster' else None)['id']
    game = engine._load(identity)
    prepared = engine.prepare_response(game)
    before = copy.deepcopy(game.to_dict())
    disk = engine.store._path(identity).read_bytes()
    metadata = engine.achievements.metadata.path.read_bytes()
    denied = Mock(side_effect=AssertionError('Pure projection requested an effect'))
    with patch.object(engine.store, 'save', denied), patch.object(engine.store, 'load', denied), \
         patch.object(engine, '_advance_world_year', denied), patch.object(engine.achievements, 'evaluate', denied):
        first = engine.project_game(prepared)
        first['player']['name'] = 'Only the output changed'
        assert engine.project_game(prepared)['player']['name'] == 'Projection'
        assert game.to_dict() == before
    denied.assert_not_called()
    assert engine.store._path(identity).read_bytes() == disk
    assert engine.achievements.metadata.path.read_bytes() == metadata
    game.player.name = 'Later authoritative name'
    assert engine.project_game(prepared)['player']['name'] == 'Projection'


def test_regional_capabilities_remain_late_bound_after_engine_and_map_changes(tmp_path):
    engine = GameEngine(ROOT, tmp_path)
    deps = engine._dependencies.regions
    game = GameState('late', 17, Player('Original', 'none'), '', '')
    view = CalendarGame(game, 'human', game.player.age)
    maps = object()
    advance = Mock(return_value=['current callback'])
    with patch.object(engine, 'maps', maps), patch.object(engine, '_annual_world_npc_update', advance):
        assert deps.maps is maps
        assert deps.advance_npcs(view, random.Random(17)) == ['current callback']
    advance.assert_called_once()
    assert advance.call_args.args[0] is view


@pytest.mark.parametrize('target,capability,arguments,result', [
    ('cultivation_life.system.ghost.calendar.advance_parade_year', 'advance_parade', (), None),
    ('cultivation_life.system.war.lifecycle._advance_wars_unit', 'advance_wars_unit', ([],), ['war']),
    ('cultivation_life.system.intrigue.runtime.advance_npc_faction',
     'advance_npc_faction', ('original', []), None),
])
def test_regional_module_callbacks_remain_replaceable_after_composition(
    tmp_path, target, capability, arguments, result,
):
    engine = GameEngine(ROOT, tmp_path)
    game = GameState('module-late', 17, Player('Original', 'none'), '', '')
    view = CalendarGame(game, 'human', game.player.age)
    with patch(target, return_value=result) as callback:
        assert getattr(engine._dependencies.regions, capability)(view, random.Random(17), *arguments) == result
    callback.assert_called_once()
    assert callback.call_args.args[1] is view


def test_regional_tick_can_run_with_only_the_declared_contract(monkeypatch):
    game = GameState('regional', 17, Player('Original', 'none'), '', '')
    game.player.age = 20
    rng = random.Random(17)
    game.world_simulation = dict(regions={'human': dict(year=19, rng=encode_rng(rng))},
        people={}, society_units={'human': [dict(year=20, unit=2)]},
        faction_units={'human': [dict(year=20, unit=2, faction='original')]})
    war = dict(world='human', deferred_units=[dict(year=20, unit=2)])
    game.wars = [war]
    seen, news = [], []
    unexpected = Mock(side_effect=AssertionError('Undeclared regional collaborator'))

    def callback(name, result=None):
        def call(view, *args, **kwargs):
            assert isinstance(view, CalendarGame) and view._game is game
            assert view._region_world == 'human' and view.player.age == 20
            if name == 'sects':
                assert kwargs == dict(personal=False)
            if name == 'war_units':
                assert args[1] == [war]
            seen.append(name)
            return result
        return call

    values = {field.name: unexpected for field in fields(RegionalDependencies)}
    values.update(get_maps=lambda: None,
        advance_sects=callback('sects', ['sects']), advance_npcs=callback('npcs', ['npcs']),
        advance_family=callback('family', ['family']), advance_relationships=callback('relationships'),
        advance_buddhist_society=callback('buddhist'), advance_sage_society=callback('sage'),
        advance_parade=callback('parade'), advance_guixu=callback('guixu', False),
        advance_strategic_wars=callback('strategic'), advance_researchers=callback('researchers'),
        advance_wars_unit=callback('war_units', ['war_units']),
        pressure_npc_powers=callback('pressure'), advance_npc_faction=callback('faction'))
    for target, name in [
        ('cultivation_life.system.economy.deferred_settlement.apply', 'receipts'),
        ('cultivation_life.system.economy.state.advance_economy', 'economy'),
        ('cultivation_life.system.economy.spirit_fields.advance_field_year', 'field'),
        ('cultivation_life.system.economy.caravans.advance_caravans', 'caravans'),
        ('cultivation_life.system.economy.organizations.advance_organizations', 'organizations'),
        ('cultivation_life.system.war.stationing.advance', 'stationing'),
        ('cultivation_life.system.monster_civilizations.core.advance_year', 'civilizations'),
        ('cultivation_life.system.intrigue.custody.advance_prison_year', 'prisons'),
    ]:
        monkeypatch.setattr(target, callback(name))
    regions.tick(RegionalDependencies(**values), game, 'human', 20, news)
    assert seen == ['receipts', 'economy', 'field', 'caravans', 'organizations',
        'sects', 'npcs', 'family', 'relationships', 'buddhist', 'sage', 'parade',
        'guixu', 'stationing', 'strategic', 'researchers', 'war_units', 'pressure',
        'faction', 'civilizations', 'prisons']
    assert news == ['sects', 'npcs', 'family', 'war_units']
    assert game.world_simulation['regions']['human']['year'] == 20
    assert game.world_simulation['regions']['human']['rng'] == encode_rng(rng)
    unexpected.assert_not_called()
