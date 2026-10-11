"""DLC commands use real rules, typed tools and disposable/atomic sessions."""
import copy
import random

import pytest

from test_debug_console import environment, api_environment
from test_debug_capabilities import sample
from cultivation_life.content_registry import GUIXU_TIDE_CONTENT, REALMS, TECHNIQUE_CATALOG
from cultivation_life.debug.capabilities import CAPABILITIES, EXCLUDED_OPERATIONS
from cultivation_life.debug.commands import build_registry
from cultivation_life.debug.dlc import CHECKS
from cultivation_life.debug.engine_adapter import SessionEngine
from cultivation_life.debug.registry import CommandError
from cultivation_life.debug.runtime import atomic_json
from cultivation_life.models import GameState
from cultivation_life.rules import opportunity_required, learn_technique, add_technique_copy


DLC_CAPABILITIES = tuple(cap for cap in CAPABILITIES if cap.dlc)


def call(manager, sid, command, **arguments):
    if next(cap for cap in CAPABILITIES if cap.name == command).preview:
        return manager.execute(command, arguments=arguments, session_id=sid)
    return manager.execute(command, arguments=arguments, session_id=sid,
        expected_revision=manager.load(sid)['revision'], request_key=f"test-{manager.load(sid)['revision']}")


def scene(manager, path, preset_id=None, **options):
    made = manager.create_scene(dict(name='DLC tools', spirit_root='supreme_metal',
        path=path, seed=7301, **({'preset_id': preset_id} if preset_id else {}), **options))
    sid = made['session_id']
    game = current_game(manager, sid)
    game.pending_event = None
    game.active_trial = None
    save_fixture(manager, sid, game)
    return sid


def current_game(manager, sid):
    return GameState.from_dict(manager.load(sid)['current']['game'])


def save_fixture(manager, sid, game):
    envelope = manager.load(sid)
    envelope['current']['game'] = game.to_dict()
    atomic_json(manager._path(sid), envelope)


@pytest.fixture
def isolated(environment):
    engine, manager, sid, _ = environment
    source = {p.name: p.read_bytes() for p in engine.store.directory.glob('*.json')}
    yield engine, manager, sid
    assert source == {p.name: p.read_bytes() for p in engine.store.directory.glob('*.json')}


def test_all_remaining_routes_have_typed_metadata_and_no_exclusions(isolated):
    _, manager, _ = isolated
    covered = manager.execute('capability list')['data']['covered']
    assert not EXCLUDED_OPERATIONS
    assert {'civilizations view','civilizations action'} <= {cap.name for cap in DLC_CAPABILITIES}
    assert all(row['content_available'] for row in covered if row['dlc'])
    assert {row['operation'] for row in covered if row['shortcut']} == {'merchant-debug-hq', 'tianji-debug-reveal-all'}
    registry = build_registry()
    assert registry.parse('sage recruitment false')[1] == [False]
    assert registry.parse('asura action fuse null \'["body-one","body-two"]\'')[1][2] == ['body-one', 'body-two']
    for name, args in [
        ('guixu action', {'action': 'fight', 'confirm_betrayal': 'false'}),
        ('guixu action', {'action': 'enter', 'dungeon': 'wrong-alias'}),
        ('asura action', {'action': 'fuse', 'body_ids': ['a', 'b', 'c']}),
        ('sage doctrine', {'action': 'found', 'combo': {'philosophie': 'mind'}}),
        ('custom lineage confirm', {'evolution_id': 'x', 'name': 'Test', 'rules': [{'effect': 'might'}]}),
        ('custom lineage confirm', {'evolution_id': 'x', 'name': 'Test', 'rules': [{
            'phase': 'round_start', 'schedule': 'every', 'condition': 'always',
            'target': 'player', 'effect': 'might', 'value': True}]}),
    ]:
        with pytest.raises(CommandError):
            registry.structured(name, args)


@pytest.mark.parametrize('cap', DLC_CAPABILITIES, ids=lambda cap: cap.operation)
def test_disabled_dlc_never_reaches_engine_or_changes_game(isolated, monkeypatch, cap):
    _, manager, sid = isolated
    monkeypatch.setitem(CHECKS, cap.dlc, lambda: False)
    before = manager.load(sid)['current']
    before_file = manager._path(sid).read_bytes()
    method = next(name for name in cap.invoke.__code__.co_names if hasattr(SessionEngine, name))
    def forbidden(*args, **kwargs):
        pytest.fail('Disabled DLC reached gameplay')
    monkeypatch.setattr(SessionEngine, method, forbidden)
    with pytest.raises(CommandError, match='Required DLC is not enabled'):
        call(manager, sid, cap.name, **{a.name: sample(a.schema()) for a in cap.arguments})
    assert manager.load(sid)['current'] == before
    if cap.preview:
        assert manager._path(sid).read_bytes() == before_file


def test_civilizations_preview_and_action_are_isolated_and_revision_guarded(isolated, tmp_path):
    _, manager, sid = isolated
    game = current_game(manager, sid)
    game.player.location_id = 'wudi_plain'
    game.player.opportunity = 10000
    preparer = SessionEngine(manager.project_root, tmp_path / 'prepared', {})
    preparer.store.save(game)
    game = preparer._load(game.id)
    save_fixture(manager, sid, game)
    before = manager._path(sid).read_bytes()
    preview = call(manager, sid, 'civilizations view')['data']
    assert preview['world'] == 'human' and preview['revision'] == 0
    assert manager._path(sid).read_bytes() == before
    economic = copy.deepcopy(game.economy_v2)
    rng = copy.deepcopy(game.rng_state)
    arguments = dict(action='observe', expected_revision=0,
                     expected_world=preview['world'], expected_location=preview['location'])
    call(manager, sid, 'civilizations action', **arguments)
    actual = current_game(manager, sid)
    assert actual.monster_civilization_state['revision'] == 1
    assert actual.economy_v2 == economic and actual.rng_state == rng
    committed = manager.load(sid)['current']
    with pytest.raises(RuntimeError):
        call(manager, sid, 'civilizations action', **arguments)
    assert manager.load(sid)['current'] == committed


def test_buddhist_temple_and_assembly_commands(isolated):
    _, manager, _ = isolated
    sid = scene(manager, 'buddhist')
    manager.execute('player set spirit_stones 1000000', session_id=sid)
    call(manager, sid, 'buddhist action', action='temple')
    game = current_game(manager, sid)
    assert game.buddhist_state['worlds'][game.player.world]['sites'][game.player.location_id]['temple'] == 1
    learn_technique(game.player, copy.deepcopy(next(row for row in TECHNIQUE_CATALOG.values() if row.path == 'buddhist')))
    save_fixture(manager, sid, game)
    technique = game.player.known_techniques[0].id
    call(manager, sid, 'buddhist action', action='start', technique=technique)
    assert current_game(manager, sid).buddhist_state['assembly']
    # A new temple cannot bypass a pending assembly event.
    game = current_game(manager, sid)
    if game.pending_event:
        before = manager.load(sid)['current']
        with pytest.raises(RuntimeError):
            call(manager, sid, 'buddhist action', action='temple')
        assert manager.load(sid)['current'] == before


def test_guixu_enter_team_response_rest_return(isolated):
    engine, manager, sid = isolated
    game = current_game(manager, sid)
    dungeon = next(row for row in GUIXU_TIDE_CONTENT['dungeons'] if row['world'] == 'human')
    engine._open_guixu_cycle(game, dungeon, game.guixu_state['cycles'][dungeon['id']], random.Random(17))
    game.pending_event = None
    game.player.location_id = dungeon['entry_location_id']
    game.player.realm_index, game.player.layer = 3, 1
    save_fixture(manager, sid, game)
    call(manager, sid, 'guixu action', action='enter', dungeon_id=dungeon['id'])
    if current_game(manager, sid).guixu_state['player_session'].get('pending_team_offer'):
        call(manager, sid, 'guixu action', action='team_decline')
    before = current_game(manager, sid).guixu_state['player_session']['remaining_days']
    call(manager, sid, 'guixu action', action='rest')
    assert current_game(manager, sid).guixu_state['player_session']['remaining_days'] < before
    call(manager, sid, 'guixu action', action='return')
    assert current_game(manager, sid).guixu_state['player_session'] is None


def test_asura_reroll_locks_and_cultivation_boundaries(isolated):
    _, manager, ordinary_sid = isolated
    before = manager.load(ordinary_sid)['current']
    with pytest.raises(RuntimeError):
        call(manager, ordinary_sid, 'asura action', action='train_body')
    assert manager.load(ordinary_sid)['current'] == before
    sid = scene(manager, 'demonic', 'asura_upper')
    game = current_game(manager, sid)
    game.player.asura_cultivation.update(conversion=5, body_level=0, souls=10000,
        route='asura', level=9, domain_rank=1, domain_name='Test', veins={'9': 3})
    game.player.body_training = 100
    game.player.opportunity = 10 * opportunity_required(game.player)
    save_fixture(manager, sid, game)
    call(manager, sid, 'asura action', action='train_body')
    call(manager, sid, 'asura action', action='learn_power')
    call(manager, sid, 'asura action', action='learn_power')
    power = copy.deepcopy(current_game(manager, sid).player.asura_cultivation['powers'][0])
    call(manager, sid, 'asura action', action='lock_power', target_id=power['id'])
    call(manager, sid, 'asura action', action='reroll_power')
    state = current_game(manager, sid).player.asura_cultivation
    assert state['body_level'] == 1
    assert next(row for row in state['powers'] if row['id'] == power['id']) == power


def test_tianji_preview_forge_activate_and_reveal_retries(isolated):
    engine, manager, sid = isolated
    initial_revision = manager.load(sid)['revision']
    reveal = call(manager, sid, 'tianji reveal all')
    assert manager.execute('tianji reveal all', arguments={}, session_id=sid,
        expected_revision=initial_revision, request_key=f'test-{initial_revision}')['replayed']
    game = current_game(manager, sid)
    assert all(level == 5 for level in game.tianji_state['knowledge'].values())
    artifact = game.tianji_state['artifacts'][-1]
    definitions = {row['id']: row for row in game.tianji_state['materials']}
    materials = [engine._tianji_material_instance(game, definitions[key], random.Random(i), 'debug test')
                 for i, key in enumerate(artifact['recipe'])]
    game.player.crafting_materials.extend(materials)
    save_fixture(manager, sid, game)
    payload = dict(target_artifact_id=artifact['id'], mold_id=artifact['mold_id'],
        **dict(zip(('primary_id', 'secondary_a_id', 'secondary_b_id', 'quench_id'), [row['id'] for row in materials])))
    before = manager._path(sid).read_bytes()
    preview = manager.execute('tianji preview', arguments=payload, session_id=sid)
    assert preview['data']['exact_slots'] == [True] * 4
    assert manager._path(sid).read_bytes() == before
    call(manager, sid, 'tianji forge', **payload)
    game = current_game(manager, sid)
    assert not game.player.crafting_materials and game.tianji_state['player_artifacts']
    call(manager, sid, 'tianji action', action='activate', artifact_id=artifact['id'])
    assert current_game(manager, sid).tianji_state['activated_artifact_id']
    call(manager, sid, 'tianji action', action='deactivate', artifact_id=artifact['id'])
    assert current_game(manager, sid).tianji_state['activated_artifact_id'] is None
    before = manager.load(sid)['current']
    with pytest.raises(RuntimeError):
        call(manager, sid, 'tianji forge', **payload)
    assert manager.load(sid)['current'] == before
    assert reveal['changed']


def test_sage_doctrine_recruitment_and_outer_king(isolated):
    _, manager, _ = isolated
    sid = scene(manager, 'confucian', 'confucian_core')
    call(manager, sid, 'sage doctrine', action='found', name='New School',
        combo={'classic': 'guliang', 'philosophy': 'mind', 'practice': 'statecraft', 'script': 'old_text'})
    call(manager, sid, 'sage recruitment', enabled=False)
    assert current_game(manager, sid).sage_state['recruit_enabled'] is False
    call(manager, sid, 'sage worship', sage_id='mencius')
    game = current_game(manager, sid)
    game.player.haoran_exp = 100000
    save_fixture(manager, sid, game)
    call(manager, sid, 'sage outer king', action='spirit_stone')
    assert current_game(manager, sid).player.haoran_exp < 100000
    call(manager, sid, 'sage doctrine', action='leave')
    assert 'human' not in current_game(manager, sid).sage_state['memberships']


def test_custom_lineage_editor_is_pure_and_confirmation_uses_real_budget(isolated):
    _, manager, _ = isolated
    sid = scene(manager, 'monster', monster_species_id='fox')
    game = current_game(manager, sid)
    game.player.world, game.player.location_id = 'monster_realm', 'myriad_beast_city'
    game.player.realm_index, game.player.layer = 8, REALMS[8].layers
    game.player.monster_evolution_id = 'FOX_MAHAYANA_HEAVENLY'
    game.player.monster_evolution_history = ['FOX_MAHAYANA_HEAVENLY']
    game.player.opportunity = opportunity_required(game.player)
    game.player.awaiting_major_breakthrough = True
    save_fixture(manager, sid, game)
    before = manager._path(sid).read_bytes()
    result = manager.execute('custom lineage prepare', arguments={'evolution_id': 'FOX_NETHER_SELF_1'}, session_id=sid)
    editor = result['data']['monster_bloodline']['custom_lineage_editor']
    assert editor['stage'] == 1 and editor['slots'] == 2
    assert manager._path(sid).read_bytes() == before
    rule = dict(phase='round_start', schedule='every', condition='always', target='player', effect='might', value=.03)
    before = manager.load(sid)['current']
    with pytest.raises(RuntimeError) as error:
        call(manager, sid, 'custom lineage confirm', evolution_id='FOX_NETHER_SELF_1', name='Test Lineage',
             rules=[{**rule, 'target': 'enemy', 'value': .12}, {**rule, 'target': 'enemy', 'effect': 'guard', 'value': .12}])
    assert '功业点不足' in str(error.value.__cause__)
    assert manager.load(sid)['current'] == before
    call(manager, sid, 'custom lineage confirm', evolution_id='FOX_NETHER_SELF_1', name='Test Lineage', rules=[rule])
    player = current_game(manager, sid).player
    assert (player.world, player.realm_index) == ('nether', 9)
    assert player.monster_custom_lineage['rules'][0]['value'] == .03


def test_sage_join_debate_and_refine_manual(isolated):
    _, manager, _ = isolated
    sid = scene(manager, 'confucian', 'confucian_core')
    game = current_game(manager, sid)
    doctrine = game.sage_state['worlds']['human']['doctrines'][0]
    member = next(row for row in doctrine['members'] if row.get('path') == 'confucian')
    call(manager, sid, 'sage doctrine', action='join', doctrine_id=doctrine['id'])
    call(manager, sid, 'sage debate', doctrine_id=doctrine['id'], member_id=member['id'])
    game = current_game(manager, sid)
    assert any(row.event_id == 'SYS_SAGE_DEBATE' for row in game.history)
    technique = copy.deepcopy(next(row for row in TECHNIQUE_CATALOG.values() if row.grade == 4))
    add_technique_copy(game.player, technique, level=4)
    item = next(row for row in game.player.inventory if row.technique_id == technique.id)
    before = game.player.haoran_exp
    save_fixture(manager, sid, game)
    call(manager, sid, 'sage refine manual', item_id=item.id)
    assert current_game(manager, sid).player.haoran_exp == before + 320


def test_monster_evolution_and_merchant_shortcut(isolated):
    _, manager, normal_sid = isolated
    sid = scene(manager, 'monster', monster_species_id='serpent')
    game = current_game(manager, sid)
    game.player.layer = REALMS[game.player.realm_index].layers
    game.player.opportunity = opportunity_required(game.player)
    game.player.awaiting_major_breakthrough = True
    save_fixture(manager, sid, game)
    call(manager, sid, 'monster evolve', evolution_id='SERPENT_SPIRIT')
    game = current_game(manager, sid)
    assert game.player.realm_index == 1 and game.player.monster_evolution_id == 'SERPENT_SPIRIT'
    manager.execute('game view /merchant_system', session_id=normal_sid)
    game = current_game(manager, normal_sid)
    alliance_id = game.merchant_state['worlds'][game.player.world][0]['id']
    call(manager, normal_sid, 'merchant debug hq', alliance_id=alliance_id)
    member = current_game(manager, normal_sid).merchant_state['membership']
    assert member['alliance_id'] == alliance_id and member['site'] == 'hq' and member['rank'] == 2


def test_dlc_tools_available_without_config_in_isolated_sessions(environment, api_environment):
    request, config = api_environment
    from cultivation_life.debug.client import DebugClient
    from http.server import ThreadingHTTPServer
    config.write_text('Debug=True')
    httpd = next(cell.cell_contents for cell in request.__closure__ if isinstance(cell.cell_contents, ThreadingHTTPServer))
    client = DebugClient(f'http://127.0.0.1:{httpd.server_port}')
    sid = client.call('debug start', game_id=environment[3])['data']['session_id']
    metadata = {row['name']: row for row in client.tools()}
    assert metadata['cultivation_custom_lineage_prepare']['annotations']['readOnlyHint']
    assert metadata['cultivation_custom_lineage_confirm']['inputSchema']['properties']['arguments']['properties']['rules']['items']['required']
    args = {'arguments': {}, 'session_id': sid, 'expected_revision': 0, 'request_key': 'http-reveal'}
    client.call_tool('cultivation_tianji_reveal_all', args)
    assert client.call_tool('cultivation_tianji_reveal_all', args)['replayed']
    state = client.call('state get', {'pointer': '/tianji_state/knowledge'}, session_id=sid)['data']
    assert state and all(level == 5 for level in state.values())
    config.write_text('Debug=False')
    assert request('/api/debug/command', {'command': 'tianji reveal all', **args})[0] == 200
    config.write_text('Debug=True')
    assert client.call('state get', {'pointer': '/tianji_state/knowledge'}, session_id=sid)['data'] == state
