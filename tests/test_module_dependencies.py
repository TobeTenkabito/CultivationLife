"""Import boundaries and independently executable economy/contact contracts."""
import ast
import builtins
import dis
import importlib
import inspect
from dataclasses import fields
from pathlib import Path
from types import CodeType, SimpleNamespace
from typing import get_type_hints
from unittest.mock import Mock

from cultivation_life.engine import GameEngine
from cultivation_life.models import GameState, Player, SectNpc
from cultivation_life.storage import SaveStore
from cultivation_life.system import npc_contacts
from cultivation_life.system.economy import market
from cultivation_life.system.economy.dependencies import MarketDependencies
from cultivation_life.system.economy_system import EconomySystemMixin
from cultivation_life.system.npc_contact_dependencies import NpcContactDependencies
from tools.check_module_dependencies import import_edges, report, violations


ROOT = Path(__file__).resolve().parents[1]


def test_project_respects_migrated_module_boundaries():
    result = report(ROOT)
    assert not result['violations']
    for group in result['cycles']:
        assert not {'cultivation_life.system.doctrine.effects',
                    'cultivation_life.system.doctrine.generation'} <= set(group)
        assert not {'cultivation_life.system.merchant_system',
                    'cultivation_life.system.merchant_commission_system'} <= set(group)


def test_import_checker_sees_deferred_imports_but_ignores_type_only_imports(tmp_path):
    package = tmp_path / 'cultivation_life'
    (package / 'system').mkdir(parents=True)
    (package / 'engine').mkdir()
    (package / 'engine/__init__.py').write_text('')
    (package / 'system/example.py').write_text(
        'from typing import TYPE_CHECKING\n'
        'if TYPE_CHECKING:\n    from ..engine import GameEngine\n'
        'def run():\n    from .. import engine\n', encoding='utf-8')
    _modules, edges = import_edges(tmp_path)
    bad = violations(edges)
    assert bad == [{'source': 'cultivation_life.system.example',
                    'target': 'cultivation_life.engine', 'line': 5}]


def test_import_checker_reports_real_relative_import_cycles(tmp_path):
    package = tmp_path / 'cultivation_life'
    package.mkdir()
    (package / 'a.py').write_text('def call():\n    from .b import helper\n')
    (package / 'b.py').write_text('from .a import call\n')
    assert report(tmp_path)['cycles'] == [['cultivation_life.a', 'cultivation_life.b']]


def global_names(code):
    for instruction in dis.get_instructions(code):
        if instruction.opname == 'LOAD_GLOBAL':
            yield instruction.argval
    for child in code.co_consts:
        if isinstance(child, CodeType):
            yield from global_names(child)


def test_economy_algorithms_use_real_module_globals_and_declared_collaborators():
    checked = []
    for path in (ROOT / 'cultivation_life/system/economy').glob('*.py'):
        if path.stem in {'__init__', 'dependencies', 'wiring'}:
            continue
        module = importlib.import_module('cultivation_life.system.economy.' + path.stem)
        for name, function in inspect.getmembers(module, inspect.isfunction):
            if function.__module__ != module.__name__:
                continue
            assert function.__globals__ is vars(module)
            assert not {'GameEngine', 'EconomySystemMixin'} & vars(module).keys()
            for symbol in global_names(function.__code__):
                assert symbol in vars(module) or hasattr(builtins, symbol), (name, symbol)
            contract = get_type_hints(function)['deps']
            declared = {f.name for f in fields(contract)}
            declared.update(k for k, v in vars(contract).items() if isinstance(v, property))
            for node in ast.walk(ast.parse(inspect.getsource(function))):
                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == 'deps':
                    assert node.attr in declared, (name, node.attr)
            checked.append(name)
    assert checked


def test_market_lock_can_execute_without_an_engine(tmp_path):
    store = SaveStore(tmp_path)
    game = GameState('market', 42, Player('Buyer', 'supreme_metal'), '', '')
    game.market_offers = [{'id': 'old', 'kind': 'item', 'locked': True},
                          {'id': 'new', 'kind': 'item', 'locked': False},
                          {'id': 'material', 'kind': 'crafting_material', 'locked': True}]
    unrelated = Mock(side_effect=AssertionError('Unrelated capability requested'))
    arguments = {f.name: unrelated for f in fields(MarketDependencies)}
    arguments.update(_load=lambda game_id: game, _get_store=lambda: store,
                     _get_maps=lambda: SimpleNamespace(normalize_location=lambda *args: 'market'),
                     _market_offer_group=EconomySystemMixin._market_offer_group,
                     present=lambda game: game.market_offers)
    market.toggle_market_offer_lock(MarketDependencies(**arguments), game.id, 'new')
    saved = store.load(game.id)
    assert [row['locked'] for row in saved.market_offers] == [False, True, True]
    unrelated.assert_not_called()


def test_cached_economy_contracts_follow_replaced_resources_and_methods(tmp_path, monkeypatch):
    engine = GameEngine(ROOT, tmp_path / 'original')
    contract = engine._economy_dependencies.market
    replacement = SaveStore(tmp_path / 'replacement')
    monkeypatch.setattr(engine, 'store', replacement)
    monkeypatch.setattr(engine, '_market_offer_group', lambda offer: 'replacement')
    assert contract is engine._economy_dependencies.market
    assert contract.store is replacement
    assert contract._market_offer_group({}) == 'replacement'


def test_npc_master_request_uses_injected_operation_without_engine_internals():
    game = GameState('contact', 42, Player('Student', 'supreme_metal'), '', '')
    teacher = SectNpc('teacher', 'Teacher', '', 2, 1, 100, 500, affinity=80)
    unrelated = Mock(side_effect=AssertionError('Unrelated capability requested'))
    arguments = {f.name: unrelated for f in fields(NpcContactDependencies)}
    guard = Mock()
    manage = Mock(return_value={'requested': True})
    arguments.update(_load=lambda game_id: game, _find_npc=lambda game, key: teacher,
                     assert_buddhist_operation_allowed=guard, manage_known_relationship=manage)
    result = npc_contacts.act(NpcContactDependencies(**arguments), game.id, teacher.id, 'master')
    assert result == {'requested': True}
    guard.assert_called_once_with(game.id, 'npc-contact')
    manage.assert_called_once_with(game.id, teacher.id, 'master')
    unrelated.assert_not_called()


def test_shared_battle_adapter_and_resource_ports_keep_compatibility_exports():
    from cultivation_life import ports
    from cultivation_life.engine import combat_capabilities, ports as old_ports
    from cultivation_life.system import combat_adapter
    assert combat_capabilities.bind_capabilities is combat_adapter.bind_capabilities
    assert combat_capabilities.CapabilityBinding is combat_adapter.CapabilityBinding
    assert old_ports.SavePort is ports.SavePort
