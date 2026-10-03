"""Key lifecycle flows execute without an engine or implicit Mixin collaborators."""
import ast
import builtins
import copy
import dis
import importlib
import inspect
import random
from dataclasses import fields
from pathlib import Path
from types import CodeType
from typing import get_type_hints
from unittest.mock import Mock

import pytest

from cultivation_life.content_registry import WORLD_SYSTEMS
from cultivation_life.engine import GameEngine
from cultivation_life.models import GameState, Player, SectNpc
from cultivation_life.storage import SaveStore
from cultivation_life.system.buddhist.assembly import _continue_buddhist_assembly
from cultivation_life.system.buddhist.dependencies import BuddhistAssemblyDependencies, NirvanaDependencies
from cultivation_life.system.buddhist.rules import buddhist_config
from cultivation_life.system.buddhist_wish import ensure_wish, nirvana
from cultivation_life.system.demonic.dependencies import DemonicAnnualDependencies, DemonicRefinementDependencies
from cultivation_life.system.demonic.annual import _annual_demonic_update
from cultivation_life.system.demonic.refinement import secluded_refine_foreign_souls
from cultivation_life.system.ghost.dependencies import GhostIdentityDependencies
from cultivation_life.system.ghost.identity import ghost_constraint_action
from cultivation_life.system.relationship_rules import _rank
from cultivation_life.system.relationships.captivity import _convert_to_puppet, _remove_conversion_target
from cultivation_life.system.relationships.concubines import manage_concubine
from cultivation_life.system.relationships.dependencies import (
    CaptivityDependencies, ConcubineActionDependencies, DependentLifecycleDependencies, RelationshipViolenceDependencies,
)
from cultivation_life.system.relationships.dependents import (
    _advance_concubine_status, _maybe_transfer_player_dependency, _runtime_from_status, _set_concubine_status,
)
from cultivation_life.system.relationships.violence import relationship_violence
from tools.check_module_dependencies import violations

ROOT = Path(__file__).resolve().parents[1]
MODULES = ['ghost.identity', 'ghost.erosion', 'ghost.reincarnation', 'ghost.calendar', 'ghost.progression',
           'demonic.annual', 'demonic.refinement', 'relationships.captivity', 'relationships.concubines',
           'relationships.dependents', 'relationships.sanctions', 'relationships.violence',
           'buddhist.actions', 'buddhist.assembly', 'buddhist.rules', 'relationship_rules']


@pytest.mark.parametrize('name', ['ghost_constraint_action', 'post_battle_possess', 'reincarnate_ghost',
    'secluded_refine_foreign_souls', 'captive_action', '_annual_demonic_update',
    'manage_concubine', '_advance_concubine_status', '_maybe_transfer_player_dependency', 'relationship_violence',
    '_continue_buddhist_assembly', '_resolve_buddhist_assembly'])
def test_key_workflows_are_explicit_engine_entries_not_inherited_business_bodies(name):
    assert name in GameEngine.__dict__
    assert all(name not in base.__dict__ for base in GameEngine.__mro__[1:-1])


def contract(kind, **overrides):
    unexpected = Mock(side_effect=AssertionError('Undeclared or unrelated capability invoked'))
    return kind(**({f.name: unexpected for f in fields(kind)} | overrides)), unexpected


def game_state(path='demonic'):
    game = GameState('flows', 42, Player('Player', 'supreme_fire', path=path, realm_index=2), '', '')
    game.player.divine_sense_rank = 2
    return game


def global_names(code):
    for instruction in dis.get_instructions(code):
        if instruction.opname == 'LOAD_GLOBAL':
            yield instruction.argval
    for child in code.co_consts:
        if isinstance(child, CodeType):
            yield from global_names(child)


@pytest.mark.parametrize('name', MODULES)
def test_extracted_operations_use_declared_contracts_and_real_module_globals(name):
    module = importlib.import_module('cultivation_life.system.' + name)
    assert not any(isinstance(value, type) and value.__name__.endswith('Mixin') for value in vars(module).values())
    for _, function in inspect.getmembers(module, inspect.isfunction):
        if function.__module__ != module.__name__:
            continue
        assert function.__globals__ is vars(module)
        assert not {'self', 'host', 'engine'} & inspect.signature(function).parameters.keys()
        for symbol in global_names(function.__code__):
            assert symbol in vars(module) or hasattr(builtins, symbol), (function.__name__, symbol)
        if 'deps' not in inspect.signature(function).parameters:
            continue
        kind = get_type_hints(function)['deps']
        declared = {f.name for f in fields(kind)} | {k for k, v in vars(kind).items() if isinstance(v, property)}
        for node in ast.walk(ast.parse(inspect.getsource(function))):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == 'deps':
                assert node.attr in declared, (function.__name__, node.attr)


@pytest.mark.parametrize('death', [False, True])
def test_ghost_wait_advances_once_and_applies_erosion_only_while_alive(death):
    game, trace, store = game_state('ghost'), [], Mock()
    game.player.ghost_captor = {'id': 'owner', 'combat_power': 100}
    age = game.player.age
    def advance(actual, rng, news, **kwargs):
        assert actual is game and game.player.age == age + 1 and kwargs == {'encounters': False}
        trace.append('year')
        game.player.alive = not death
        return False
    erosion = Mock(side_effect=lambda *args: trace.append('erosion'))
    deps, unexpected = contract(GhostIdentityDependencies,
        _load=lambda _: game, _advance_world_year=advance, _advance_soul_erosion_time=erosion,
        _get_store=lambda: store, present=lambda game: game.player.alive)
    assert ghost_constraint_action(deps, game.id, 'wait') is not death
    assert trace == (['year'] if death else ['year', 'erosion'])
    assert game.history[-1].event_id == 'SYS_GHOST_CONSTRAINT'
    store.save.assert_called_once_with(game)
    unexpected.assert_not_called()


@pytest.mark.parametrize('death', [False, True])
def test_secluded_refinement_stops_before_progress_without_spending_resources(death):
    game, store = game_state(), Mock()
    game.player.foreign_souls = [dict(id='s', name='Soul', strength=1, required=10, progress=0, refined=False)]
    before = (game.player.age, game.player.opportunity, game.player.mp)
    def stop(game, rng, news, **kwargs):
        game.player.alive = not death
        if not death:
            game.pending_event = {'id': 'interrupted'}
        return False
    deps, unexpected = contract(DemonicRefinementDependencies,
        _load=lambda _: game, _secluded_refining_years=lambda _: 3, _soul_refine_gain=lambda _: 10,
        _demonic_rules=lambda: {}, _advance_world_year=stop, _ensure_market=Mock(),
        _compact_world_history=Mock(), _get_store=lambda: store, present=lambda game: game.history[-1].result)
    assert secluded_refine_foreign_souls(deps, game.id) == ('dead' if death else 'interrupted')
    assert game.player.age == before[0] + 1
    assert (game.player.opportunity, game.player.mp) == before[1:]
    assert game.player.foreign_souls[0]['progress'] == 0
    store.save.assert_called_once_with(game)
    unexpected.assert_not_called()


def test_soul_backlash_records_consequence_before_dispatching_death():
    game = game_state()
    game.player.hp = 1
    game.player.foreign_souls = [{'id': 's', 'strength': 20, 'refined': False}]
    def die(actual, reason, event):
        assert actual is game and event == 'SYS_SOUL_BACKLASH_DEATH'
        assert game.player.hp == 0 and game.history[-1].event_id == 'SYS_SOUL_BACKLASH'
        game.player.alive = False
    deps, unexpected = contract(DemonicAnnualDependencies, _demonic_rules=lambda: WORLD_SYSTEMS['demonic_cultivation'],
        _sage_scaled_gain=lambda player, amount, key: amount, _die=Mock(side_effect=die))
    _annual_demonic_update(deps, game, Mock(random=lambda: 0))
    assert not game.player.alive and game.player.heart_demon == 10
    deps._die.assert_called_once()
    unexpected.assert_not_called()


@pytest.mark.parametrize('kind,roll,result', [('corpse', 0, 'created'), ('living', 0, 'created'),
                                            ('corpse', 1, 'destroyed'), ('living', 1, 'resisted')])
@pytest.mark.parametrize('disciple', [False, True])
def test_puppet_conversion_preserves_failure_and_identity_cleanup(kind, roll, result, disciple):
    game = game_state()
    npc = SectNpc('target', 'Target', '', 1, 1, 30, 120)
    game.notable_npcs[npc.id] = npc
    target = {'id': npc.id, 'npc_id': npc.id, 'name': npc.name, 'realm_index': 1, 'layer': 1,
              'combat_power': 10, 'affinity': 20, 'source': 'relationship:master'}
    roster = game.player.disciples if disciple else game.player.prisoners
    roster.append(target)
    deps, unexpected = contract(CaptivityDependencies, _demonic_rules=lambda: WORLD_SYSTEMS['demonic_cultivation'],
        _find_npc=lambda *args: npc, _remove_conversion_target=_remove_conversion_target)
    outcome, _ = _convert_to_puppet(deps, game, target, kind, Mock(random=lambda: roll), disciple)
    assert outcome == result
    remaining = game.player.disciples if disciple else game.player.prisoners
    assert (target in remaining) is (result == 'resisted')
    assert npc.alive is (kind == 'living')
    if kind == 'living' and result == 'created':
        assert npc.custody['kind'] == 'living_puppet'
        assert game.player.puppets[0]['source_npc_id'] == npc.id
    assert len(game.player.puppets) == int(result == 'created')
    if result == 'resisted':
        assert target['affinity'] == 5
    elif result == 'created':
        assert game.player.puppets[0]['type'] == kind
    unexpected.assert_not_called()


def test_captive_recruitment_clears_previous_roles_and_saves_once():
    game, store = game_state(), Mock()
    target = dict(id='target', npc_id='target', name='Target', gender='female', world='human',
                  realm_index=1, layer=1, affinity=0, alive=True)
    game.player.prisoners = [target]
    game.player.master = game.player.dao_companion = target
    game.player.dao_friends = game.player.disciples = game.player.party = [target]
    deps, unexpected = contract(ConcubineActionDependencies,
        _load=lambda _: game, _concubine_target=lambda *args: (target, 'captive'),
        _normalize_concubine=lambda target, source: dict(target, source=source), _rank=_rank,
        _get_store=lambda: store, present=lambda game: game.player.concubines)
    result = manage_concubine(deps, game.id, 'target', 'recruit')
    assert len(result) == 1 and result[0]['source'] == 'captive'
    assert not any([game.player.prisoners, game.player.master, game.player.dao_companion,
                    game.player.dao_friends, game.player.disciples, game.player.party])
    store.save.assert_called_once_with(game)
    unexpected.assert_not_called()


@pytest.mark.parametrize('role', ['ghost', 'concubine'])
def test_dependency_transfer_updates_owner_without_losing_controlled_form(role):
    game = game_state()
    loser = SectNpc('old', 'Old', '', 2, 1, 30, 200)
    winner = SectNpc('new', 'New', '', 3, 1, 40, 300)
    if role == 'ghost':
        game.player.ghost_captor = {'id': loser.id, 'controlled_form': '法器器灵'}
    else:
        game.player.concubine_status = {'owner_id': loser.id}
    holder = {}
    deps, unexpected = contract(DependentLifecycleDependencies,
        _npc_power=lambda npc: 100, _npc_realm_name=lambda npc: 'Realm', _default_npc_main_technique=lambda npc: None,
        _runtime_from_status=_runtime_from_status,
        _set_concubine_status=lambda *args, **kwargs: _set_concubine_status(holder['deps'], *args, **kwargs))
    holder['deps'] = deps
    assert _maybe_transfer_player_dependency(deps, game, loser, winner, Mock(random=lambda: 0), context='test')
    if role == 'ghost':
        assert game.player.ghost_captor['id'] == winner.id
        assert game.player.ghost_captor['controlled_form'] == '法器器灵'
    else:
        assert game.player.concubine_status['owner_id'] == winner.id
        assert game.player.concubine_status['forced'] is True
    assert game.history[-1].event_id == 'SYS_DEPENDENT_TRANSFERRED'
    unexpected.assert_not_called()


def test_bound_execution_uses_kill_service_and_cleans_joint_crossings_once():
    game, store = game_state(), Mock()
    target = dict(id='captive', npc_id='npc', name='Target', world='human', alive=True, realm_index=1, layer=1)
    game.player.prisoners = [target]
    game.player.joint_friend_crossing = [{'id': 'npc'}, {'id': 'keep'}]
    game.player.joint_spirit_crossing = {'id': 'npc'}
    npc = SectNpc('npc', 'Target', '', 1, 1, 30, 120)
    game.notable_npcs[npc.id] = npc
    target = game.detain_person(target)
    game.player.prisoners = [target]
    guard, kill = Mock(), Mock()
    deps, unexpected = contract(RelationshipViolenceDependencies,
        _load=lambda _: game, assert_buddhist_operation_allowed=guard, _public_party=lambda _: [],
        _find_npc=lambda *args: npc, _apply_cultivator_kill=kill,
        _get_store=lambda: store, present=lambda game: game.history[-1].result)
    assert relationship_violence(deps, game.id, 'captive', npc.id) == 'killed'
    guard.assert_called_once_with(game.id, 'relationship-violence')
    kill.assert_called_once()
    assert not game.player.prisoners and game.player.joint_spirit_crossing is None
    assert game.player.joint_friend_crossing == [{'id': 'keep'}]
    assert not target['alive'] and npc.death_reason == target['death_reason']
    store.save.assert_called_once_with(game)
    unexpected.assert_not_called()


@pytest.mark.parametrize('state,units', [('active', 1), ('dead', 1), ('away', 1), ('missing-away', 1), ('active', 0)])
def test_dependency_year_releases_unavailable_owner_before_any_drain(state, units):
    game = game_state()
    game.player.opportunity = 100
    game.player.concubine_status = dict(owner_id='owner', owner_world='spirit' if state == 'missing-away' else 'human')
    owner = SectNpc('owner', 'Owner', '', 3, 1, 40, 300, alive=state != 'dead',
                    world='spirit' if state == 'away' else 'human')
    find = Mock(return_value=None if state == 'missing-away' else owner)
    deps, unexpected = contract(DependentLifecycleDependencies, _find_npc=find)
    drain = _advance_concubine_status(deps, game, units)
    if state != 'active':
        assert game.player.concubine_status is None and drain == 0
        assert game.player.opportunity == 100
    elif units == 0:
        assert game.player.concubine_status is not None and drain == 0
        assert game.player.opportunity == 100
        find.assert_not_called()
    else:
        assert drain > 0 and game.player.opportunity == 100 - drain
        assert game.player.concubine_status['turns'] == 1
    unexpected.assert_not_called()


def test_assembly_resumes_remaining_years_and_restores_event_without_reroll():
    game = game_state('buddhist')
    session = dict(world=game.player.world, location=game.player.location_id, stage=0,
                   stage_years=0, unit_years=3, burden=0, technique_name='Art', level=1, pending=None)
    game.buddhist_state = {'assembly': session, 'dharma_karma': 0}
    year = Mock(side_effect=[False, True, True])
    templates = {key: {'id': key, 'body': 'Event'} for key in
                 [*buddhist_config()['positive_events'], *buddhist_config()['negative_events']]}
    instantiate = Mock(side_effect=lambda template, *args: dict(template))
    deps, unexpected = contract(BuddhistAssemblyDependencies, _advance_world_year=year,
        _advance_soul_erosion_time=Mock(), _buddhist_permissions=lambda _: [],
        _instantiate_event=instantiate, _get_events_by_id=lambda: templates)
    age, rng = game.player.age, random.Random(42)
    _continue_buddhist_assembly(deps, game, rng)
    assert session['stage_years'] == 1 and game.player.age == age + 1 and game.pending_event is None
    _continue_buddhist_assembly(deps, game, rng)
    assert session['stage_years'] == 3 and game.player.age == age + 3 and year.call_count == 3
    pending, state = copy.deepcopy(game.pending_event), rng.getstate()
    game.pending_event = None
    _continue_buddhist_assembly(deps, game, rng)
    assert game.pending_event == pending and game.pending_event is not session['pending']
    assert rng.getstate() == state and year.call_count == 3
    instantiate.assert_called_once()
    unexpected.assert_not_called()


def test_nirvana_only_needs_breakthrough_and_record_ports():
    game = game_state('buddhist')
    ensure_wish(game)['value'] = 100
    rng = random.Random(1)
    def complete(actual, actual_rng, label):
        assert actual is game and actual_rng is rng
        assert game.buddhist_state['wish']['value'] == 0
        game.player.layer += 1
    complete, record = Mock(side_effect=complete), Mock()
    nirvana(NirvanaDependencies(_buddhist_record=record, _complete_minor_breakthrough=complete), game, rng)
    assert game.player.layer == 2 and game.player.opportunity == 0
    assert game.buddhist_state['wish']['nirvana_units'] == 3
    complete.assert_called_once()
    record.assert_called_once()


def test_contracts_keep_late_resources_overrides_and_shared_helper_exports(tmp_path, monkeypatch):
    engine = GameEngine(ROOT, tmp_path/'original')
    deps = engine._dependencies
    replacement, maps, events = SaveStore(tmp_path/'replacement'), object(), {'replaced': {}}
    monkeypatch.setattr(engine, 'store', replacement)
    monkeypatch.setattr(engine, 'maps', maps)
    monkeypatch.setattr(engine, 'events_by_id', events)
    monkeypatch.setattr(engine, '_load', lambda key: key)
    monkeypatch.setattr(engine, '_advance_world_year', lambda *a, **kw: 'replaced')
    for cap in [deps.ghost_flows.identity, deps.ghost_flows.erosion, deps.ghost_flows.reincarnation,
                deps.demonic_flows.refinement, deps.relationships.captivity, deps.relationships.concubines,
                deps.relationships.dependents, deps.relationships.violence, deps.buddhist_flows.actions]:
        assert cap.store is replacement and cap._load('key') == 'key'
    assert deps.ghost_flows.calendar.maps is deps.buddhist_flows.actions.maps is maps
    assert deps.ghost_flows.reincarnation.events_by_id is deps.relationships.captivity.events_by_id is events
    for cap in [deps.ghost_flows.identity, deps.demonic_flows.refinement, deps.buddhist_flows.assembly]:
        assert cap._advance_world_year(None) == 'replaced'
    for source, target, symbol in [('ghost_system', 'ghost.progression', 'perform_reincarnation'),
                                   ('buddhist_system', 'buddhist.rules', 'buddhist_modifier')]:
        a, b = [importlib.import_module('cultivation_life.system.' + mod) for mod in (source, target)]
        assert getattr(a, symbol) is getattr(b, symbol)


@pytest.mark.parametrize('source,target', [
    ('ghost.identity', 'ghost_system'), ('ghost.progression', 'ghost.identity'),
    ('ghost.calendar', 'concubine_system'), ('demonic.refinement', 'demonic_system'),
    ('relationships.concubines', 'demonic_system'), ('relationships.captivity', 'concubine_system'),
    ('relationships.violence', 'relationship_violence'), ('buddhist.assembly', 'buddhist_system'),
    ('buddhist.rules', 'buddhist.actions'), ('relationships.dependencies', 'relationships.dependents'),
])
def test_key_flow_import_boundaries_reject_hidden_back_references(source, target):
    source, target = 'cultivation_life.system.' + source, 'cultivation_life.system.' + target
    assert violations([(source, target, 9)]) == [dict(source=source, target=target, line=9)]
