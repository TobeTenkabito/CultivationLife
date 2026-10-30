"""HTTP snapshot isolation and economic replay against the released algorithm."""
import copy
from dataclasses import FrozenInstanceError
import hashlib
from http.server import ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import threading
from unittest.mock import Mock, patch
from urllib.request import urlopen

import pytest

from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.engine.orchestration.response import prepare_json_response
from cultivation_life.engine.presentation.projection import PreparedGameView, PreparedJsonGameView, project_game
from cultivation_life.engine.response_dependencies import ResponseDependencies
from cultivation_life.system.economy import basket_consumption, basket_production, state

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / 'tests/fixtures/basket_consumption_332.py'
spec = importlib.util.spec_from_file_location('cultivation_life.system.economy._released_baskets', REFERENCE)
released = importlib.util.module_from_spec(spec)
spec.loader.exec_module(released)


def test_released_basket_algorithm_is_unchanged():
    assert hashlib.sha256(REFERENCE.read_bytes().replace(b'\r\n', b'\n')).hexdigest() == \
        '36c66ba2d89250847a28453cb4c6a952e75d10dd3992fdc17d81b830f613592e'


def test_json_snapshot_preserves_http_semantics_without_aliases():
    payload = {'rows': [{'name': '原名'}], 'coordinates': (1, 2), 'keys': {1: 'one', None: 'null'}}
    legacy = project_game(PreparedGameView(payload))
    snapshot = PreparedJsonGameView(payload)
    assert json.loads(snapshot.body) == json.loads(json.dumps(legacy))
    payload['rows'][0]['name'] = '后续修改'
    assert json.loads(snapshot.body)['rows'][0]['name'] == '原名'
    with pytest.raises((FrozenInstanceError, TypeError)):
        snapshot.body = b'changed'
    # The in-process API still keeps tuples and integer/None keys.
    assert isinstance(legacy['coordinates'], tuple)
    assert legacy['keys'] == {1: 'one', None: 'null'}
    for bad in ({'live': object()}, {'number': float('nan')}, {'number': float('inf')}):
        with pytest.raises((TypeError, ValueError)):
            PreparedJsonGameView(bad)


@pytest.mark.parametrize('moved', [False, True])
def test_json_response_keeps_effect_order_and_catalog_policy(moved):
    seen = []
    payload = {'pending_event': {'id': 'event'}, 'fleet_network': {
        'can_act': False, 'fleets': [{'id': 'original-fleet'}], 'order_goods': [{'id': 'ore'}]}}
    deps = ResponseDependencies(lambda game: seen.append('settle') or moved,
        lambda game: seen.append('commit'), lambda game: seen.append('prepare') or payload)
    result = json.loads(prepare_json_response(deps, object(), defer_order_goods=True).body)
    assert seen == (['settle', 'commit', 'prepare'] if moved else ['settle', 'prepare'])
    assert result['pending_event'] == payload['pending_event']
    assert result['fleet_network'] == {'can_act': False, 'fleets': [{'id': 'original-fleet'}],
                                      'order_goods_deferred': True}
    assert 'order_goods' in payload['fleet_network']


def test_json_response_never_prepares_after_failed_commit():
    prepare = Mock(side_effect=AssertionError('Prepared after failed commit'))
    deps = ResponseDependencies(lambda game: True, Mock(side_effect=OSError('Disk failed')), prepare)
    with pytest.raises(OSError, match='Disk failed'):
        prepare_json_response(deps, object())
    prepare.assert_not_called()


@pytest.mark.parametrize('network', [None, [], 'custom'])
def test_catalog_policy_leaves_other_valid_public_values_unchanged(network):
    payload = {'fleet_network': network}
    deps = ResponseDependencies(lambda game: False, lambda game: None, lambda game: payload)
    assert json.loads(prepare_json_response(deps, object(), defer_order_goods=True).body) == payload


@pytest.mark.parametrize('kind,can_order,retained', [
    ('sect', True, True), ('family', True, True),
    ('sect', False, False), ('family', False, False),
    ('independent', True, False), ('alliance', True, False),
])
def test_catalog_policy_keeps_existing_organization_order_consumers(kind, can_order, retained):
    payload = {'fleet_network': {'can_act': False, 'order_goods': [{'id': 'ore'}],
               'fleets': [{'owner_kind': kind, 'can_order': can_order}]}}
    deps = ResponseDependencies(lambda game: False, lambda game: None, lambda game: payload)
    result = json.loads(prepare_json_response(deps, object(), defer_order_goods=True).body)
    assert ('order_goods' in result['fleet_network']) is retained
    assert result['fleet_network']['fleets'] == payload['fleet_network']['fleets']
    assert result['fleet_network']['can_act'] is False


@pytest.fixture
def local(tmp_path):
    return GameEngine(ROOT, tmp_path / 'saves')


@pytest.mark.parametrize('preset,path', [('core', 'dao'), ('true_immortal', 'dao'), ('core', 'ghost')])
def test_real_json_snapshot_equals_legacy_and_is_detached(local, preset, path):
    identity = local.create_game('字节快照', 'heavenly', path, 315, preset_id=preset)['id']
    local.get_game(identity)
    before = local.store._path(identity).read_bytes()
    metadata = local.achievements.metadata.path.read_bytes()
    legacy = local.get_game(identity)
    encoded = local.get_game(identity, as_json=True)
    assert json.loads(encoded.body) == json.loads(json.dumps(legacy))
    denied = Mock(side_effect=AssertionError('Detached snapshot requested a service'))
    with patch.object(local.store, 'load', denied), patch.object(local.store, 'save', denied), \
         patch.object(local.achievements, 'evaluate', denied):
        assert json.loads(encoded.body)['player']['name'] == '字节快照'
    assert local.store._path(identity).read_bytes() == before
    assert local.achievements.metadata.path.read_bytes() == metadata


@pytest.mark.parametrize('hook', ['present', 'prepare_response', 'project_game'])
def test_http_snapshot_keeps_instance_response_hooks(local, hook):
    identity = local.create_game('嵌入接口', 'heavenly', 'dao', 315, preset_id='core')['id']
    if hook == 'prepare_response':
        replacement = lambda game: PreparedGameView({'hook': hook})
    else:
        replacement = lambda value: {'hook': hook}
    with patch.object(local, hook, replacement):
        assert json.loads(local.get_game(identity, as_json=True).body) == {'hook': hook}


@pytest.mark.parametrize('hook', ['present', 'prepare_response', 'project_game'])
def test_http_snapshot_keeps_class_response_hooks(local, hook):
    identity = local.create_game('类接口', 'heavenly', 'dao', 315, preset_id='core')['id']
    if hook == 'prepare_response':
        replacement = lambda self, game: PreparedGameView({'hook': hook})
    elif hook == 'project_game':
        replacement = staticmethod(lambda value: {'hook': hook})
    else:
        replacement = lambda self, game: {'hook': hook}
    with patch.object(GameEngine, hook, replacement):
        assert json.loads(local.get_game(identity, as_json=True).body) == {'hook': hook}


@pytest.fixture
def http(local, tmp_path):
    class Quiet(server.Handler):
        def log_message(self, *args):
            pass
    with patch.object(server, 'ENGINE', local), patch.object(server, 'PERSISTENCE_ROOT', tmp_path):
        httpd = ThreadingHTTPServer(('127.0.0.1', 0), Quiet)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        def request(path):
            with urlopen(f'http://127.0.0.1:{httpd.server_port}{path}') as response:
                assert response.headers['Cache-Control'] == 'no-store'
                body = response.read()
                assert len(body) == int(response.headers['Content-Length'])
                return json.loads(body)
        try:
            yield request
        finally:
            httpd.shutdown()
            httpd.server_close()


def test_actual_http_catalog_split_reconstructs_full_response(local, http):
    identity = local.create_game('HTTP目录', 'heavenly', 'dao', 315, preset_id='core')['id']
    expected = http(f'/api/games/{identity}')
    before = local.store._path(identity).read_bytes()
    lean = http(f'/api/games/{identity}?fleet_goods=deferred')
    assert lean['fleet_network'].pop('order_goods_deferred') is True
    assert 'order_goods' not in lean['fleet_network']
    denied = Mock(side_effect=AssertionError('Static catalog loaded a game'))
    with patch.object(local.store, 'load', denied), patch.object(local.store, 'save', denied):
        lean['fleet_network']['order_goods'] = http('/api/fleet-goods')['goods']
    assert lean == expected
    assert local.store._path(identity).read_bytes() == before


def organization_game(engine, kind):
    from cultivation_life.system.economy.organizations import register
    from cultivation_life.system.economy.ledger import transfer_value
    from cultivation_life.system.faction_geography import faction_site
    if kind == 'sect':
        from test_release_290 import game_at
        game, entity = game_at(engine)
    else:
        from test_family_expansion import family_game
        game = family_game(engine)
        game = engine._load(game.id)
        entity = game.family
    game.player.location_id = faction_site(entity)['id']
    register(game, kind, entity.id, game.player.world)
    transfer_value(game, f'background:{game.player.world}',
                   f'organization:{kind}:{entity.id}', 100000, '隔离组织订单验收资本')
    engine.store.save(game)
    engine.fleet_action(game.id, {'action': 'create', 'owner_kind': kind})
    return game.id


@pytest.mark.parametrize('kind', ['sect', 'family'])
def test_actual_http_organization_orders_keep_their_catalog(local, http, kind):
    identity = organization_game(local, kind)
    expected = http(f'/api/games/{identity}')
    assert any(f['owner_kind'] == kind and f['can_order'] for f in expected['fleet_network']['fleets'])
    assert http(f'/api/games/{identity}?fleet_goods=deferred') == expected


def test_http_keeps_old_get_game_override_signature(local, http):
    with patch.object(local, 'get_game', lambda identity: {'id': identity, 'custom': True}):
        assert http('/api/games/custom?fleet_goods=deferred') == {'id': 'custom', 'custom': True}


def test_http_keeps_old_class_get_game_override_signature(http):
    with patch.object(GameEngine, 'get_game', lambda self, identity: {'id': identity, 'custom': True}):
        assert http('/api/games/custom?fleet_goods=deferred') == {'id': 'custom', 'custom': True}


def test_http_keeps_callable_without_an_inspectable_signature(local, http):
    with patch.object(local, 'get_game', str):
        assert http('/api/games/custom?fleet_goods=deferred') == 'custom'


def test_json_read_rejects_all_old_schemas_without_rewriting(local):
    identity = local.create_game('结构边界', 'heavenly', 'dao', 315, preset_id='core')['id']
    path = local.store._path(identity)
    original = path.read_bytes()
    document = json.loads(original)
    for version in range(1, 11):
        document['version'] = version
        obsolete = json.dumps(document, ensure_ascii=False).encode('utf-8')
        path.write_bytes(obsolete)
        with pytest.raises(ValueError, match='仅支持结构 11'):
            local.get_game(identity, as_json=True, defer_order_goods=True)
        assert path.read_bytes() == obsolete
    path.write_bytes(original)


@pytest.mark.parametrize('preset', ['core', 'true_immortal'])
@pytest.mark.parametrize('years', [1, 5, 20])
def test_basket_cache_matches_released_full_state_across_batches(local, preset, years):
    identity = local.create_game('原版经济对照', 'heavenly', 'dao', 315, preset_id=preset)['id']
    original = local.store.load(identity)
    optimized = copy.deepcopy(original)
    for batch in range(2):
        results = []
        for game, settle in ((original, released.settle), (optimized, basket_consumption.settle)):
            market = state.local_market(game)
            if batch:
                # The next batch must not reuse recipes with old reference
                # prices or a previous market's commodity membership.
                material = next(key for key in market['commodities']
                                if key.startswith('econ_') and key.endswith('ore_structure'))
                del market['commodities'][material]
                for position, row in enumerate(market['commodities'].values()):
                    if position % 3 == 0:
                        row['reference'] *= 2
                    if position % 5 == 0:
                        row['stock'] = 0
            game.player.age += years
            results.append(settle(game, market, years))
        assert results[0] == results[1]
        assert original.to_dict() == optimized.to_dict()


@pytest.mark.parametrize('imported,wanted', [(True, 10), (False, 0)])
def test_cached_production_keeps_early_rejection_before_recipe(imported, wanted):
    market = {'commodities': {'item': {'stock': 100, 'target': 100, 'imported': imported}}}
    with patch.object(basket_production, 'recipe', side_effect=AssertionError('Unused recipe evaluated')):
        assert basket_production.produce(object(), market, 'owner', 'item', wanted,
                                         _recipe_cache={}) == (0, 0)
