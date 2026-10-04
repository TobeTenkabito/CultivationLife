"""Ordinary operation coverage and real isolated console workflows."""
import ast
import copy
import inspect
import json
import os
import random
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from test_debug_console import environment, api_environment
from cultivation_life.debug.capabilities import CAPABILITIES, BY_OPERATION, EXCLUDED_OPERATIONS
from cultivation_life.debug.commands import build_registry
from cultivation_life.debug.engine_adapter import SessionEngine
from cultivation_life.debug.registry import CommandError
from cultivation_life.debug.runtime import atomic_json
from cultivation_life.engine import GameEngine


ROOT = Path(__file__).resolve().parents[1]


def sample(schema):
    kind = schema['type']
    kind = kind[0] if isinstance(kind, list) else kind
    if 'enum' in schema:
        return schema['enum'][0]
    if kind == 'string':
        return 'test'
    if kind == 'boolean':
        return True
    if kind in {'number', 'integer'}:
        return max(1, schema.get('minimum', 0))
    if kind == 'object':
        return {key: sample(value) for key, value in schema['properties'].items()}
    if kind == 'array':
        return [sample(schema['items'])]
    return None


def test_all_game_post_routes_are_explicitly_classified():
    tree = ast.parse((ROOT / 'cultivation_life/server.py').read_text(encoding='utf-8-sig'))
    # Inspect the per-game dispatch chain, excluding separate save-transfer APIs.
    tree = next(node for node in ast.walk(tree) if isinstance(node, ast.If)
                and ast.unparse(node.test) == "operation == 'advance'")
    routes = set()
    methods = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
            continue
        test = node.test
        if isinstance(test.left, ast.Name) and test.left.id == 'operation' and isinstance(test.ops[0], ast.Eq):
            route = ast.literal_eval(test.comparators[0])
            routes.add(route)
            for child in node.body:
                if isinstance(child, ast.Assign) and isinstance(child.value, ast.Call):
                    method = child.value.func
                    if isinstance(method, ast.Attribute) and ast.unparse(method.value) == 'ENGINE':
                        methods[route] = method.attr
    assert len(BY_OPERATION) == len(CAPABILITIES)
    assert not set(BY_OPERATION) & set(EXCLUDED_OPERATIONS)
    assert routes == set(BY_OPERATION) | set(EXCLUDED_OPERATIONS)
    for cap in CAPABILITIES:
        assert methods[cap.operation] in cap.invoke.__code__.co_names
    for route in ('market-buy', 'map-travel', 'breakthrough', 'family-action', 'crafting-forge',
                  'war-peace', 'upper-voisinage', 'upper-institution', 'heavenly-court', 'use-item'):
        assert route in BY_OPERATION


@pytest.mark.parametrize('capability', CAPABILITIES, ids=lambda c: c.operation)
def test_capability_binds_real_engine_signature_and_preserves_types(capability):
    calls = []
    class Probe:
        def __getattr__(self, name):
            def call(*args, **kwargs):
                method = getattr(GameEngine, name)
                bound = inspect.signature(method).bind(self, *args, **kwargs)
                for key, value in bound.arguments.items():
                    annotation = inspect.signature(method).parameters[key].annotation
                    if annotation in {'str', 'int', 'bool'} and value is not None:
                        assert type(value) is {'str': str, 'int': int, 'bool': bool}[annotation], (name, key, value)
                calls.append((name, bound))
            return call
    payload = {a.name: sample(a.schema()) for a in capability.arguments}
    capability.invoke(Probe(), 'game-id', payload)
    assert len(calls) == 1


def test_optional_boolean_array_object_and_union_arguments():
    registry = build_registry()
    assert registry.parse('setting set combat_popup false')[1] == ['combat_popup', False]
    assert registry.parse('tutorial guide_next welcome')[1] == ['guide_next', 'welcome', None]
    assert registry.parse('tutorial navigate 1')[1] == ['navigate', 1, None]
    assert registry.parse('formation save \'[null,"material-a"]\' "My Array"')[1][:2] == [[None, 'material-a'], 'My Array']
    assert registry.structured('combat plan', {'stance': 'guard', 'mp_reserve': 0.5})[1] == ['guard', None, None, 0.5, None, None]
    for name, args in [('combat plan', {'mp_reserve': True}), ('combat plan', {'neighborhood': 'off'}),
                       ('formation save', {'slots': ['x']*10}), ('formation save', {'slots': [True]}),
                       ('alchemy refine', {'target_item_id': 'healing_pill', 'materials': [{'item_id': 'x', 'quantity': False}]}),
                       ('merchant preview', {'metrics': {'made_up_metric': 1}}),
                       ('technique equip', {'technique_id': 'x', 'slot': 1}),
                       ('setting set', {'setting': 'combat_popup', 'enabled': 'false'})]:
        with pytest.raises(CommandError):
            registry.structured(name, args)
    for command in ['setting set combat_popup yes', 'formation save not-json', 'upper neighborhood activate x']:
        with pytest.raises(CommandError):
            registry.parse(command)


def test_isolated_scene_creation_and_stop_roundtrip(environment):
    engine, manager, _, _ = environment
    source = {p.name: p.read_bytes() for p in engine.store.directory.glob('*.json')}
    scene = manager.execute('scenario create "New Test" supreme_metal dao 42 core')['data']
    sid = scene['session_id']
    saved = manager.load(sid)
    assert saved['source_kind'] == 'generated' and saved['current']['game']['seed'] == 42
    assert not (engine.store.directory / f'{scene["game_id"]}.json').exists()
    assert manager.execute('debug stop', session_id=sid)['data']['return_to_title'] is True
    imported = manager.import_bundle(saved)['session_id']
    assert manager.execute('debug stop', session_id=imported)['data']['return_to_title'] is True
    assert source == {p.name: p.read_bytes() for p in engine.store.directory.glob('*.json')}


def test_game_view_commits_preparation_and_returns_discoverable_ids(environment):
    engine, manager, sid, gid = environment
    before = (engine.store.directory / f'{gid}.json').read_bytes()
    result = manager.execute('game view', session_id=sid)
    assert 'map' in result['data']['view']['sections'] and result['revision'] == 1
    market = manager.execute('game view /market', session_id=sid)['data']['view']
    assert market['offers']
    saved = manager.load(sid)['current']
    with pytest.raises(CommandError):
        manager.execute('game view /missing', session_id=sid)
    assert manager.load(sid)['current'] == saved
    assert (engine.store.directory / f'{gid}.json').read_bytes() == before


def test_market_inventory_equipment_settings_and_field_workflow(environment):
    engine, manager, sid, _ = environment
    source = {p.name: p.read_bytes() for p in engine.store.directory.glob('*.json')}
    def run(text):
        return manager.execute(text, session_id=sid)['data']
    run('player set spirit_stones 10000000')
    offer = next(row for row in run('game view /market')['view']['offers'] if row['kind'] == 'item')
    run('market lock ' + offer['id'])
    run('market buy ' + offer['id'])
    assert any(row['id'] == offer['content_id'] for row in run('inventory'))
    run('item give healing_pill 1')
    run('player set hp 1')
    run('item use healing_pill')
    assert run('player get hp')['hp'] > 1
    technique = run('state get /player/known_techniques')[0]['id']
    run(f'technique equip {technique} main')
    assert run('state get /player/technique/id') == technique
    run('setting set manual_combat_plan true')
    run('combat plan guard 10 never 0.4 false true')
    assert run('state get /player/combat_plan')['transformations'] is False
    run('world news set true')
    assert run('state get /debug_world_news') is True
    run('spirit field reclaim')
    assert run('game view /spirit_field')['view']['reclaimed_qing'] == 1
    run('item give dew_grass_seed 1')
    seeds = run('game view /spirit_field')['view']['seeds']
    run('spirit field plant ' + seeds[0]['plant_id'])
    assert run('game view /spirit_field')['view']['plots']
    assert source == {p.name: p.read_bytes() for p in engine.store.directory.glob('*.json')}


def test_preview_is_pure_even_when_engine_writes_or_raises(environment, monkeypatch):
    _, manager, sid, _ = environment
    before = manager._path(sid).read_bytes()
    result = manager.execute("formation preview '[]'", session_id=sid)
    assert result['type'] == 'preview'
    assert manager._path(sid).read_bytes() == before
    def broken(engine, gid, payload):
        game = engine.store.load(gid)
        game.player.age += 10
        engine.store.save(game)
        raise ValueError('implementation failure in preview')
    monkeypatch.setattr(SessionEngine, 'preview_formation', broken)
    with pytest.raises(RuntimeError):
        manager.execute("formation preview '[]'", session_id=sid)
    assert manager._path(sid).read_bytes() == before


@pytest.mark.parametrize('guard_name', ['assert_ghost_operation_allowed', 'assert_guixu_operation_allowed',
                                       'assert_buddhist_operation_allowed'])
def test_new_operations_respect_each_formal_guard(environment, monkeypatch, guard_name):
    manager, sid = environment[1:3]
    before = manager.load(sid)['current']
    def block(*args):
        raise ValueError('blocked by formal guard')
    def never(*args):
        pytest.fail('Operation escaped its formal guard')
    monkeypatch.setattr(SessionEngine, guard_name, block)
    monkeypatch.setattr(SessionEngine, 'use_item', never)
    with pytest.raises(RuntimeError):
        manager.execute('item use healing_pill', session_id=sid)
    assert manager.load(sid)['current'] == before


def test_new_simulation_failure_and_retry_do_not_commit_partial_state(environment, monkeypatch):
    manager, sid = environment[1:3]
    before = manager.load(sid)['current']
    def broken(engine, gid, name):
        game = engine.store.load(gid)
        game.player.age += 5
        engine.store.save(game)
        raise ValueError('family internal error')
    monkeypatch.setattr(SessionEngine, 'create_family', broken)
    payload = dict(arguments={'name': 'Test'}, session_id=sid, expected_revision=0, request_key='create-family')
    with pytest.raises(RuntimeError):
        manager.execute('create family', **payload)
    with pytest.raises(CommandError, match='revision conflict'):
        manager.execute('create family', **payload)
    assert manager.load(sid)['current'] == before


def test_map_travel_uses_ordinary_time_and_interruptions(environment):
    engine, manager, sid, gid = environment
    original = (engine.store.directory / f'{gid}.json').read_bytes()
    before = copy.deepcopy(manager.load(sid)['current'])
    destination = next(row['id'] for row in manager.execute('game view /map', session_id=sid)['data']['view']['locations']
                       if row['travel_status'] == 'ok')
    result = manager.execute('map travel ' + destination, session_id=sid)
    assert result['type'] == 'simulation'
    game = manager.load(sid)['current']['game']
    assert game['player']['age'] > before['game']['player']['age'] or game.get('pending_event')
    assert (engine.store.directory / f'{gid}.json').read_bytes() == original


def test_http_new_scene_preview_and_structured_boolean(environment, api_environment):
    request, config = api_environment
    config.write_text('Debug=True')
    status, result = request('/api/debug/command', {'command': 'scenario create', 'arguments': {
        'name': 'HTTP scene', 'spirit_root': 'supreme_metal', 'path': 'dao', 'seed': 12, 'preset_id': 'core'}})
    assert status == 200, result
    sid = result['data']['session_id']
    status, result = request('/api/debug/command', {'command': 'setting set', 'arguments': {
        'setting': 'combat_popup', 'enabled': False}, 'session_id': sid, 'expected_revision': 0, 'request_key': 'setting-one'})
    assert status == 200, result
    assert request('/api/debug/command', {'command': 'formation preview', 'arguments': {'slots': []}, 'session_id': sid})[0] == 200
    config.write_text('Debug=False')
    assert request('/api/debug/command', {'command': 'game view', 'session_id': sid})[0] == 404


def test_base_only_install_can_discover_and_execute_tools(tmp_path):
    shutil.copytree(ROOT / 'content', tmp_path / 'content')
    script = '''
import os
from pathlib import Path
from cultivation_life.engine import GameEngine
from cultivation_life.debug.runtime import Runtime
from cultivation_life.debug.capabilities import BY_OPERATION
from cultivation_life.content_registry import EXTENSION_REPORT
root = Path(os.environ['CULTIVATION_APP_ROOT'])
engine = GameEngine(root, root/'normal')
runtime = Runtime(root, root/'debug', engine.store)
made = runtime.execute('scenario create Base supreme_metal dao 77 core')['data']
sid = made['session_id']
runtime.execute('player set spirit_stones 999999', session_id=sid)
runtime.execute('setting set combat_popup false', session_id=sid)
runtime.execute('action advance rest 1', session_id=sid)
runtime.execute('game view /map', session_id=sid)
runtime.execute("formation preview '[]'", session_id=sid)
from cultivation_life.debug.dlc import available
from cultivation_life.debug.registry import CommandError
for cap in BY_OPERATION.values():
    if not cap.dlc:
        continue
    assert not available(cap.dlc)
    session = runtime.load(sid)
    before = runtime._path(sid).read_bytes()
    try:
        (runtime.preview if cap.preview else runtime.simulate)(session, cap.operation, {})
    except CommandError as error:
        assert 'Required DLC is not enabled' in str(error)
    else:
        raise AssertionError(cap.operation)
    assert runtime._path(sid).read_bytes() == before
assert not list((root/'normal').glob('*.json'))
print('base-only operations passed')
'''
    result = subprocess.run([sys.executable, '-c', script], cwd=ROOT,
        env={**os.environ, 'CULTIVATION_APP_ROOT': str(tmp_path)}, capture_output=True, timeout=60)
    assert result.returncode == 0, result.stderr.decode('utf-8', errors='replace')


def test_crafting_and_formation_use_real_materials_and_pure_previews(environment):
    from cultivation_life.system.crafting_system import crafting_material_definitions, make_crafting_material_instance
    from cultivation_life.system.formation_system import formation_material_definitions, make_formation_material_instance
    manager, sid = environment[1:3]
    session = manager.load(sid)
    definitions = crafting_material_definitions()
    instances = [make_crafting_material_instance(definitions[key], random.Random(i), source='test', origin_world='human')
        for i, key in enumerate(('human_cold_iron', 'human_cloud_silk', 'human_cloud_silk', 'human_sun_fire'))]
    session['current']['game']['player']['crafting_materials'].extend(instances)
    forms = formation_material_definitions()
    nodes = [make_formation_material_instance(forms[key], source='test', origin_world='human')
        for key in ('human_greenwood_stake', 'human_red_sun_sand', 'human_xuanyin_stone')]
    session['current']['game']['player']['formation_materials'].extend(nodes)
    atomic_json(manager._path(sid), session)
    payload = dict(mold_id='umbrella', primary_id=instances[0]['id'], secondary_a_id=instances[1]['id'],
                   secondary_b_id=instances[2]['id'], quench_id=instances[3]['id'], allocations={'combat_power': 20}, name='Tool artifact')
    before = manager._path(sid).read_bytes()
    preview = manager.execute('crafting preview', arguments=payload, session_id=sid)
    assert preview['data']['mold']['id'] == 'umbrella'
    assert manager._path(sid).read_bytes() == before
    forged = manager.execute('crafting forge', arguments=payload, session_id=sid, expected_revision=0, request_key='forge')
    assert forged['changed'] and not manager.load(sid)['current']['game']['player']['crafting_materials']
    slots = [row['id'] for row in nodes]
    formed = manager.execute('formation save', arguments={'slots': slots, 'name': 'Tool formation', 'activate': True},
                            session_id=sid, expected_revision=forged['revision'], request_key='form')
    player = manager.load(sid)['current']['game']['player']
    assert formed['changed'] and player['formation_active_bindings']
    formation_id = player['active_formation_id']
    manager.execute('formation deactivate', session_id=sid)
    assert len(manager.load(sid)['current']['game']['player']['formation_materials']) == 3
    manager.execute('formation delete ' + formation_id, session_id=sid)


def test_breakthrough_and_faction_family_commands(environment):
    manager, sid = environment[1:3]
    manager.execute('player set opportunity 1000000', session_id=sid)
    manager.execute('player set breakthrough_chance 1', session_id=sid)
    before = manager.load(sid)['current']['game']['player']['layer']
    manager.execute('breakthrough attempt', session_id=sid)
    assert manager.load(sid)['current']['game']['player']['layer'] > before
    manager.execute('player set realm_index 4', session_id=sid)
    manager.execute('player set spirit_stones 10000000', session_id=sid)
    manager.execute('create faction TestSect', session_id=sid)
    assert manager.load(sid)['current']['game']['player']['faction_id']
    before = manager.load(sid)['current']
    with pytest.raises(RuntimeError):
        manager.execute('create family TestFamily', session_id=sid)
    assert manager.load(sid)['current'] == before  # The tool does not bypass the heir requirement.
    saved = manager.load(sid)
    saved['current']['game']['player']['offspring'].append({
        'id': 'debug-test-heir', 'name': 'Heir', 'alive': True, 'world': 'human', 'age': 20,
        'lifespan': 120, 'realm_index': 1, 'layer': 1, 'spirit_root': 'supreme_metal',
        'path': 'dao', 'cultivation_started': True})
    atomic_json(manager._path(sid), saved)
    manager.execute('create family TestFamily', session_id=sid)
    assert manager.load(sid)['current']['game']['family']['name'] == 'TestFamily'


def test_npc_interaction_uses_authoritative_relationship_state(environment):
    from cultivation_life.debug.state import npc_rows
    manager, sid = environment[1:3]
    game = manager.load(sid)['current']['game']
    npc = next(row for _, row in npc_rows(game) if row.get('alive') and row.get('world') == game['player']['world'])
    before = npc.get('affinity') or 0
    manager.execute(f"npc contact {npc['id']} improve", session_id=sid)
    inspected = manager.execute('npc inspect ' + npc['id'], session_id=sid)['data']
    assert any(row['npc'].get('affinity', 0) > before for row in inspected['records'])
