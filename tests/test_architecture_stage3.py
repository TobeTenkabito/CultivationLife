"""Character composition, compatibility dispatch and side-effect capabilities."""
import ast
from dataclasses import fields, is_dataclass
import importlib
import inspect
import json
from pathlib import Path
import subprocess
import sys
from typing import get_type_hints
from unittest.mock import Mock, patch
from types import SimpleNamespace

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.models import GameState, Player
from cultivation_life.storage import SaveStore
from cultivation_life.system.character import dependencies, wiring
from cultivation_life.system import demonic_system, monster_bloodline_system
from cultivation_life.system import world_transition_schema, world_transition_system
from tools.check_module_dependencies import character_contract_violations, violations

ROOT = Path(__file__).resolve().parents[1]
MODULES = ['buddhist_system', 'family_system', 'sage_system', 'concubine_system',
    'ghost_system', 'monster_bloodline_system', 'natal_artifact_system', 'demonic_system',
    'upper_institutions', 'asura_court']
CALL_FORMS = json.loads((ROOT / 'tests/fixtures/character_callback_contracts.json').read_text(encoding='utf-8'))['cases']


@pytest.mark.parametrize('case', CALL_FORMS,
    ids=lambda case: case['module'] + '.' + case['function'] + ':' + case['callback'] + ':' + ','.join(case['keywords']))
def test_callback_forms_match_pre_refactor_consumers(case):
    module = importlib.import_module('cultivation_life.system.' + case['module'])
    contract = get_type_hints(getattr(module, case['function']))['deps']
    groups = {kind: name for name, kind in get_type_hints(dependencies.CharacterDependencies).items()}
    groups[dependencies.AsuraCourtDependencies] = 'asura_court'
    target = Mock(return_value=object())
    host = SimpleNamespace(**{case['callback']: target})
    bound = getattr(wiring, 'bind_' + groups[contract])(host)
    arguments = [object() for _ in range(case['positional'])]
    keywords = {name: object() for name in case['keywords']}
    getattr(bound, case['callback'])(*arguments, **keywords)
    target.assert_called_once_with(*arguments, **keywords)


def test_engine_has_no_implicit_character_inheritance():
    assert GameEngine.__bases__ == (object,)
    assert not character_contract_violations(ROOT)


@pytest.mark.parametrize('name', MODULES[:-1])
def test_legacy_method_interfaces_and_descriptors_remain_available(name):
    module = importlib.import_module('cultivation_life.system.' + name)
    cls = next(value for value in vars(module).values()
        if inspect.isclass(value) and value.__module__ == module.__name__ and value.__name__.endswith('Mixin'))
    for method, descriptor in vars(cls).items():
        if method.startswith('__'):
            continue
        current = inspect.getattr_static(GameEngine, method)
        assert isinstance(current, (staticmethod, classmethod)) == isinstance(descriptor, (staticmethod, classmethod))
        assert isinstance(current, classmethod) == isinstance(descriptor, classmethod)
        assert inspect.signature(getattr(GameEngine, method)) == inspect.signature(getattr(cls, method)), method


@pytest.mark.parametrize('name', MODULES)
def test_character_algorithms_use_only_declared_capabilities(name):
    module = importlib.import_module('cultivation_life.system.' + name)
    for function in vars(module).values():
        if not inspect.isfunction(function) or function.__module__ != module.__name__:
            continue
        if 'deps' not in inspect.signature(function).parameters:
            continue
        contract = get_type_hints(function)['deps']
        assert is_dataclass(contract) and contract.__dataclass_params__.frozen
        declared = {field.name for field in fields(contract)}
        declared.update(key for key, value in vars(contract).items() if isinstance(value, property))
        for node in ast.walk(ast.parse(inspect.getsource(function))):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == 'deps':
                assert node.attr in declared, (function.__name__, node.attr)


def test_callbacks_keep_explicit_arguments_and_resources_resolve_on_use(tmp_path):
    engine = GameEngine(ROOT, tmp_path / 'original')
    replacement = SaveStore(tmp_path / 'replacement')
    contract = engine._dependencies.character
    for group in fields(contract):
        for field in fields(getattr(contract, group.name)):
            value = getattr(getattr(contract, group.name), field.name)
            if callable(value):
                assert all(p.kind not in {p.VAR_POSITIONAL, p.VAR_KEYWORD}
                    for p in inspect.signature(value).parameters.values()), field.name
    with patch.object(engine, 'store', replacement), patch.object(engine, 'maps', object()) as maps:
        assert contract.natal_actions.store is replacement
        assert contract.buddhist_state.maps is maps


def test_optional_argument_omission_and_explicit_values_survive_late_replacement(tmp_path):
    engine = GameEngine(ROOT, tmp_path)
    game = GameState('optional', 17, Player('Original', 'none'), '', '')
    callback = Mock(return_value='plan')
    with patch.object(engine, '_plan_world_transition', callback):
        contract = engine._dependencies.character.monster_evolution
        assert contract._plan_world_transition(game, 'nether', reason='lineage') == 'plan'
        callback.assert_called_once_with(game, 'nether', reason='lineage')
        callback.reset_mock()
        contract._plan_world_transition(game, 'nether', 'story', arrival_location=None, instance_id='same')
        callback.assert_called_once_with(game, 'nether', 'story', arrival_location=None, instance_id='same')


def test_class_dispatch_uses_subclass_rules_and_legacy_consumers():
    class Engine(GameEngine):
        @staticmethod
        def _demonic_rules():
            return dict(puppet_combat_contribution=dict(mechanical=.25, corpse=.5, living=.75))
    class Legacy(demonic_system.DemonicSystemMixin):
        _demonic_rules = staticmethod(Engine._demonic_rules)
    player = Player('Original', 'none')
    player.puppets = [dict(type='mechanical', alive=True, durability=100, combat_power=100),
                      dict(type='corpse', alive=True, corpse_integrity=50, combat_power=80)]
    assert Engine._puppet_intrinsic_contribution(player) == 45
    assert Legacy._puppet_intrinsic_contribution(player) == 45


def test_preview_and_validation_cannot_commit_or_render():
    assert {f.name for f in fields(dependencies.DemonicPreviewDependencies)} == {'_load'}
    assert {f.name for f in fields(dependencies.MonsterValidationDependencies)} == {'_manual_breakthrough_kind'}
    game = GameState('preview', 17, Player('Original', 'none'), '', '')
    load = Mock(return_value=game)
    with patch('cultivation_life.system.puppet_crafting.preview', return_value={'preview': True}) as preview:
        assert demonic_system.preview_puppet(dependencies.DemonicPreviewDependencies(load),
            'preview', 'bird', 'core', 'shell', 'energy') == {'preview': True}
    load.assert_called_once_with('preview')
    assert preview.call_args.args[0] is game.player


def test_transition_values_are_shared_without_loading_transition_runtime():
    for name in ['WorldTransitionRequest', 'WorldTransitionPlan', 'WorldTransitionResult']:
        assert getattr(world_transition_system, name) is getattr(world_transition_schema, name)
    subprocess.run([sys.executable, '-c',
        "import sys; from cultivation_life.system.world_transition_schema import WorldTransitionPlan; "
        "assert 'cultivation_life.system.world_transition_system' not in sys.modules"], cwd=ROOT, check=True)


def test_engine_import_preserves_provider_and_event_registration_order():
    # Providers overwrite the previous result in insertion order. This baseline
    # was captured from the pre-refactor engine in a fresh isolated interpreter.
    result = subprocess.check_output([sys.executable, '-c',
        "import json; import cultivation_life.engine; "
        "from cultivation_life.system import path_modifiers,semantic_events; "
        "print(json.dumps(dict(providers=list(path_modifiers._providers), "
        "listeners=list(semantic_events._listeners))))"], cwd=ROOT, text=True)
    assert json.loads(result) == dict(providers=['world.ascension', 'buddhist.wish', 'buddhist'],
                                     listeners=['buddhist.wish'])


def test_checker_rejects_reintroduced_inheritance_and_hidden_capabilities(tmp_path):
    package = tmp_path / 'cultivation_life'
    (package / 'engine').mkdir(parents=True)
    (package / 'system/character').mkdir(parents=True)
    (package / 'engine/__init__.py').write_text('class GameEngine(HiddenMixin): pass\n')
    (package / 'system/character/dependencies.py').write_text('class Declared: pass\n')
    (package / 'system/family_system.py').write_text(
        'def run(deps: Declared):\n    return deps.store.save(None)\n')
    issues = character_contract_violations(tmp_path)
    assert {row['target'] for row in issues} == {'implicit-character-inheritance', 'undeclared-character-capability:store'}
    assert violations([('cultivation_life.system.character.dependencies',
                        'cultivation_life.system.world_transition_system', 1)])
