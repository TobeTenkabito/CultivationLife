"""Import boundaries and independently executable system contracts."""
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

import pytest

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
    assert not result['cycles']


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


@pytest.mark.parametrize('area', ['economy', 'tianji', 'intrigue', 'court'])
def test_system_algorithms_use_real_module_globals_and_declared_collaborators(area):
    checked = []
    for path in (ROOT / 'cultivation_life/system' / area).glob('*.py'):
        if path.stem in {'__init__', 'dependencies', 'wiring', 'tiers'}:
            continue
        module = importlib.import_module(f'cultivation_life.system.{area}.' + path.stem)
        for name, function in inspect.getmembers(module, inspect.isfunction):
            if function.__module__ != module.__name__:
                continue
            assert function.__globals__ is vars(module)
            assert not {'GameEngine', 'EconomySystemMixin', 'TianjiSystemMixin', 'IntrigueSystemMixin'} & vars(module).keys()
            for symbol in global_names(function.__code__):
                assert symbol in vars(module) or hasattr(builtins, symbol), (name, symbol)
            if 'deps' not in inspect.signature(function).parameters:
                continue  # Pure court helpers take data rather than collaborators.
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


@pytest.mark.parametrize('area', ['tianji', 'intrigue'])
def test_import_checker_rejects_new_system_back_references(area):
    module = f'cultivation_life.system.{area}.state'
    for target in (f'cultivation_life.system.{area}_system',
                   f'cultivation_life.system.{area}.wiring'):
        assert violations([(module, target, 5)]) == [dict(source=module, target=target, line=5)]


def test_no_system_rebuilds_functions_with_a_foreign_global_namespace():
    assert not (ROOT / 'cultivation_life/system/_assembly.py').exists()
    for path in (ROOT / 'cultivation_life/system').rglob('*.py'):
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8-sig'))):
            if isinstance(node, ast.ImportFrom) and node.module == 'types':
                assert not any(alias.name == 'FunctionType' for alias in node.names), path
            if isinstance(node, ast.Attribute):
                assert node.attr != 'FunctionType', path


def test_tianji_reveal_runs_without_engine_and_preserves_discovery_history():
    from cultivation_life.system.tianji.dependencies import TianjiIntelligenceDependencies
    from cultivation_life.system.tianji.intelligence import _tianji_reveal

    unrelated = Mock(side_effect=AssertionError('Unrelated capability requested'))
    arguments = {f.name: unrelated for f in fields(TianjiIntelligenceDependencies)}
    arguments['_tianji_artifact'] = lambda state, key: {'name': 'Test artifact'}
    deps = TianjiIntelligenceDependencies(**arguments)
    game = GameState('reveal', 42, Player('Player', 'supreme_metal'), '', '')
    game.tianji_state = {'knowledge': {'artifact': 2}, 'discovery_log': []}
    assert _tianji_reveal(deps, game, 'artifact', 9, 'conversation')
    assert game.tianji_state['knowledge']['artifact'] == 5
    assert game.tianji_state['discovery_log'] == [dict(
        artifact_id='artifact', name='Test artifact', source='conversation',
        age=game.player.age, **{'from': 2, 'to': 5})]
    assert not _tianji_reveal(deps, game, 'artifact', 3, 'repeat')
    assert len(game.tianji_state['discovery_log']) == 1
    unrelated.assert_not_called()


def test_intrigue_permission_threshold_accepts_an_independent_rule_provider():
    from cultivation_life.system.intrigue.dependencies import IntrigueGovernanceDependencies
    from cultivation_life.system.intrigue.governance import _intrigue_decision_threshold

    unrelated = Mock(side_effect=AssertionError('Unrelated capability requested'))
    arguments = {f.name: unrelated for f in fields(IntrigueGovernanceDependencies)}
    arguments['intrigue_rules'] = lambda: {'decision_thresholds': {'sect': 7}}
    deps = IntrigueGovernanceDependencies(**arguments)
    assert _intrigue_decision_threshold(deps, 'sect') == 7
    assert _intrigue_decision_threshold(deps, 'family') == 3
    assert _intrigue_decision_threshold(deps, 'unknown') == 99
    unrelated.assert_not_called()


@pytest.mark.parametrize('area,component', [('tianji', 'intelligence'), ('intrigue', 'governance')])
def test_system_contracts_follow_late_resource_method_and_config_replacement(tmp_path, monkeypatch, area, component):
    module = importlib.import_module(f'cultivation_life.system.{area}_system')
    host = getattr(module, area.title() + 'SystemMixin')()
    host.store = SaveStore(tmp_path / 'original')
    deps = getattr(getattr(host, f'_{area}_dependencies'), component)
    replacement = SaveStore(tmp_path / 'replacement')
    monkeypatch.setattr(host, 'store', replacement)
    monkeypatch.setattr(host, '_load', lambda key: 'replacement', raising=False)
    assert deps.store is replacement
    assert deps._load('save') == 'replacement'
    if area == 'tianji':
        monkeypatch.setattr(module, 'tianji_content_available', lambda: False)
        assert deps.tianji_content_available() is False
        monkeypatch.setattr(module, 'tianji_content_available', lambda: True)
        assert deps.tianji_content_available() is True
    else:
        rules = {'decision_thresholds': {'sect': 9}}
        monkeypatch.setattr(module, 'intrigue_rules', lambda: rules)
        assert deps.intrigue_rules() is rules
        assert host._intrigue_decision_threshold('sect') == 9


def test_shared_rule_schema_and_mentorship_preserve_compatibility_exports():
    from cultivation_life import combat_rule_engine, combat_rule_schema, monster_bloodline_rules
    from cultivation_life.system import tutorial_system, tutorial_mentorship

    assert combat_rule_engine.validate_rule is combat_rule_schema.validate_rule
    assert combat_rule_engine.RULE_TRIGGERS is combat_rule_schema.RULE_TRIGGERS
    malformed_v2 = {'schema_version': 2, 'trigger': 'unknown', 'conditions': ['unknown']}
    assert monster_bloodline_rules.validate_generated_trait(malformed_v2) == combat_rule_schema.validate_rule(malformed_v2)
    assert tutorial_system.mentor_action is tutorial_mentorship.mentor_action
    assert tutorial_system.blocked_reason is tutorial_mentorship.blocked_reason


@pytest.mark.parametrize('source,target', [
    ('combat_adapter', 'immortal_aperture'),
    ('combat_plan', 'immortal_aperture'),
    ('doctrine.provider', 'upper_voisinage'),
    ('spirit_voisinage', 'doctrine.provider'),
    ('asura_court', 'upper_institutions'),
    ('institution_state', 'asura_court'),
    ('aperture_resources', 'combat_adapter'),
    ('upper_voisinage_rules', 'upper_institutions'),
    ('doctrine.state', 'doctrine.provider'),
])
def test_import_checker_rejects_combat_back_references(source, target):
    source, target = (f'cultivation_life.system.{name}' for name in (source, target))
    assert violations([(source, target, 7)]) == [dict(source=source, target=target, line=7)]


@pytest.mark.parametrize('facade,shared,names', [
    ('immortal_aperture', 'aperture_resources',
     'true_realm cultivation_stage investment_multiplier spirit_books lower_world available ensure_aperture energy_state commit_energy'),
    ('doctrine.provider', 'doctrine.state', 'config ensure player_record'),
    ('upper_voisinage', 'upper_voisinage_rules', 'config world_config available record level project player_source'),
    ('upper_institutions', 'institution_state', 'config definition fresh account policy record'),
])
def test_combat_shared_functions_keep_original_import_paths(facade, shared, names):
    original = importlib.import_module(f'cultivation_life.system.{facade}')
    implementation = importlib.import_module(f'cultivation_life.system.{shared}')
    for name in names.split():
        function = getattr(implementation, name)
        assert getattr(original, name) is function
        assert function.__globals__ is vars(implementation)


def test_shared_energy_ledger_preserves_sealed_reserves_without_an_engine():
    from cultivation_life.system.aperture_resources import commit_energy, energy_state

    player = Player('Lower realm', 'supreme_metal', realm_index=8, world='spirit')
    player.sealed_cultivation = {'realm_index': 9, 'layer': 1}
    player.immortal_aperture = dict(version=1, capacity=1200, current=731,
                                   imitation_current=45, imitation_capacity=60)
    state = energy_state(player)
    assert (state['capacity'], state['current']) == (60, 45)
    commit_energy(player, 12)
    assert player.immortal_aperture['current'] == 731
    assert energy_state(player)['current'] == 12
    player.world = 'celestial'
    assert energy_state(player)['current'] == 731
    commit_energy(player, 500)
    assert player.immortal_aperture['imitation_current'] == 12
    assert energy_state(player)['current'] == 500


def test_shared_institution_reads_do_not_create_accounts_or_repair_state():
    import copy
    from cultivation_life.system.institution_state import account, policy, record

    game = GameState('institution', 42, Player('Player', 'supreme_metal', world='nether'), '', '')
    before = copy.deepcopy(game.to_dict())
    fresh = account(game)
    policy(game, fresh)
    assert game.to_dict() == before
    fresh['log'].append({'text': 'temporary'})
    assert not account(game)['log']
    state = account(game, create=True)
    state['unit'] = 3
    record(game, state, 'policy applied')
    assert game.upper_institutions['nether'] is state
    assert state['log'] == [dict(unit=3, text='policy applied')]
    assert game.history[-1].event_id == 'SYS_UPPER_INSTITUTION'
