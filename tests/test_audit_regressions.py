"""Regression coverage for the full-project audit's state and boundary bugs."""
import copy
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from cultivation_life import server
from cultivation_life.content_registry import ITEM_CATALOG, MARKET_GOODS, WORLD_SYSTEMS
from cultivation_life.engine import GameEngine
from cultivation_life.engine.transactions import request_scope
from cultivation_life.rules import add_item
from cultivation_life.save_transfer import export_snapshot

ROOT = Path(__file__).resolve().parents[1]


def post_json(base, path, payload):
    request = Request(base + path, data=json.dumps(payload).encode(),
                      headers={'Content-Type': 'application/json'})
    with urlopen(request, timeout=10) as response:
        return json.load(response)


def test_http_heavens_retry_and_gate(local_api, engine):
    game = create(engine)
    path = f'/api/games/{game.id}/heavens-command'
    payload = dict(command_seq=1, expected_revision=0, action='configure', options={'watch': False})
    first = post_json(local_api, path, payload)
    assert post_json(local_api, path, payload) == first
    view = post_json(local_api, f'/api/games/{game.id}/heavens-view', {'view': 'known'})
    assert view['next_command_seq'] == 2 and view['watch'] is False
    original = engine.store._path(game.id).read_bytes()
    for bad in ({**payload, 'command_seq': True},
                {**payload, 'options': {'generation_enabled': True}}):
        with pytest.raises(HTTPError) as error:
            post_json(local_api, path, bad)
        assert error.value.code == 400
    assert engine.store._path(game.id).read_bytes() == original


def test_http_settings_loads_once_and_next_request_reads_fresh_state(local_api, engine):
    game = create(engine)
    with patch.object(engine.store, 'load', wraps=engine.store.load) as load:
        first = post_json(local_api, f'/api/games/{game.id}/settings',
                          {'setting': 'combat_popup', 'enabled': False})
        assert load.call_count == 1
        assert first['settings']['combat_popup'] is False
    saved = engine.store.load(game.id)
    assert saved.settings['combat_popup'] is False
    saved.player.name = 'external update'
    engine.store.save(saved)
    with patch.object(engine.store, 'load', wraps=engine.store.load) as load:
        second = post_json(local_api, f'/api/games/{game.id}/settings',
                           {'setting': 'achievement_popup', 'enabled': False})
        assert load.call_count == 1
        assert second['player']['name'] == 'external update'
        assert second['settings']['combat_popup'] is False
        assert second['settings']['achievement_popup'] is False


def test_http_current_save_is_prepared_once_before_command(local_api, engine):
    from cultivation_life.engine import engine_persistence
    game = create(engine)
    path = engine.store._path(game.id)
    document = json.loads(path.read_text(encoding='utf-8'))
    document['player'].pop('asura_cultivation', None)
    path.write_text(json.dumps(document), encoding='utf-8')
    with patch.object(engine_persistence, '_load', wraps=engine_persistence._load) as migrate:
        post_json(local_api, f'/api/games/{game.id}/settings',
                  {'setting': 'combat_popup', 'enabled': False})
        assert migrate.call_count == 1
    saved = engine.store.load(game.id)
    assert saved.player.asura_cultivation['branches']
    assert saved.rng_state == document['rng_state']
    assert saved.settings['combat_popup'] is False


@pytest.mark.parametrize('guard', ['ghost', 'guixu', 'buddhist'])
def test_request_guards_check_the_shared_state_without_extra_reads(engine, guard):
    game = create(engine)
    before = engine.store._path(game.id).read_bytes()
    with patch.object(engine.store, 'load', wraps=engine.store.load) as load, request_scope(engine):
        shared = engine._load(game.id)
        if guard == 'ghost':
            shared.player.ghost_captor = {'id': 'captor'}
        elif guard == 'guixu':
            shared.guixu_state['player_session'] = {'trapped': False}
        else:
            shared.player.path = 'buddhist'
            shared.buddhist_state['assembly'] = {'world': shared.player.world,
                                                 'location': shared.player.location_id}
        with pytest.raises(ValueError):
            getattr(engine, f'assert_{guard}_operation_allowed')(game.id, 'buy')
        assert load.call_count == 1
    assert engine.store._path(game.id).read_bytes() == before


@pytest.mark.parametrize('exception', [RuntimeError, TypeError, KeyError, PermissionError])
def test_internal_error_is_500_logged_and_request_state_is_discarded(
    local_api, engine, tmp_path, caplog, exception,
):
    game = create(engine)
    before = engine.store._path(game.id).read_bytes()

    def fail(game_id, *_args):
        engine._load(game_id).player.name = 'unsaved mutation'
        raise exception('internal diagnostic detail')

    with patch.object(engine, 'update_setting', side_effect=fail):
        with pytest.raises(HTTPError) as caught:
            post_json(local_api, f'/api/games/{game.id}/settings',
                      {'setting': 'combat_popup', 'enabled': False, 'private': 'private-payload-marker'})
    assert caught.value.code == 500
    body = json.load(caught.value)
    assert body['code'] == 'internal_error'
    assert body['request_id'] in body['error']
    assert 'internal diagnostic detail' not in body['error']
    records = [r for r in caplog.records if r.name == 'cultivation_life.server' and r.exc_info]
    assert len(records) == 1
    assert body['request_id'] in records[0].getMessage()
    log = (tmp_path / 'data/logs/server-errors.log').read_text(encoding='utf-8')
    assert body['request_id'] in log and 'Traceback' in log and 'operation=settings' in log
    assert 'private-payload-marker' not in log
    assert engine.store._path(game.id).read_bytes() == before
    with urlopen(local_api + f'/api/games/{game.id}', timeout=10) as response:
        assert json.load(response)['player']['name'] == game.player.name


@pytest.mark.parametrize('path', ['/api/games/missing', '/missing-file', '/api/games/missing/unknown'])
def test_missing_resources_remain_404(local_api, path):
    with pytest.raises(HTTPError) as caught:
        if path.endswith('/unknown'):
            post_json(local_api, path, {})
        else:
            urlopen(local_api + path, timeout=10)
    assert caught.value.code == 404
    assert json.load(caught.value)['code'] == 'not_found'


def test_business_rejection_remains_400_without_error_log(local_api, engine, tmp_path):
    game = create(engine)
    with pytest.raises(HTTPError) as caught:
        post_json(local_api, f'/api/games/{game.id}/settings', {'setting': 'unknown'})
    assert caught.value.code == 400
    assert json.load(caught.value)['code'] == 'invalid_request'
    assert not (tmp_path / 'data/logs/server-errors.log').exists()


def test_error_log_write_failure_does_not_prevent_500_response(local_api, engine):
    game = create(engine)
    with (patch.object(engine, 'update_setting', side_effect=RuntimeError('failure')),
          patch('cultivation_life.error_reporting.RotatingFileHandler', side_effect=PermissionError('read only'))):
        with pytest.raises(HTTPError) as caught:
            post_json(local_api, f'/api/games/{game.id}/settings', {'setting': 'combat_popup'})
    assert caught.value.code == 500
    assert json.load(caught.value)['code'] == 'internal_error'


def test_concurrent_http_updates_preserve_both_changes(local_api, engine):
    game = create(engine)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(post_json, local_api, f'/api/games/{game.id}/settings',
                               {'setting': setting, 'enabled': False})
                   for setting in ('combat_popup', 'achievement_popup')]
        for future in futures:
            future.result(timeout=10)
    saved = engine.store.load(game.id)
    assert saved.settings['combat_popup'] is False
    assert saved.settings['achievement_popup'] is False


@pytest.fixture
def engine(tmp_path):
    return GameEngine(ROOT, tmp_path / 'saves')


def create(engine, realm=0):
    game_id = engine.create_game('回归', 'supreme_wood', 'dao', seed=14)['id']
    game = engine._load(game_id)
    game.player.realm_index = realm
    engine.store.save(game)
    game = engine._load(game_id)
    engine.store.save(game)
    return game


def test_concurrent_commands_preserve_both_updates_across_engine_instances(engine):
    game = create(engine)
    second = GameEngine(ROOT, engine.store.directory)
    first_loaded, release_first, second_entered, second_loaded = (threading.Event() for _ in range(4))
    original_load = engine._load
    second_load = second._load

    def held_load(game_id):
        loaded = original_load(game_id)
        first_loaded.set()
        assert release_first.wait(5)
        return loaded

    def update_second():
        second_entered.set()
        return second.update_setting(game.id, 'achievement_popup', False)

    def observe_second(game_id):
        loaded = second_load(game_id)
        second_loaded.set()
        return loaded

    with ThreadPoolExecutor(max_workers=2) as pool, patch.object(engine, '_load', side_effect=held_load), \
         patch.object(second, '_load', side_effect=observe_second):
        first = pool.submit(engine.update_setting, game.id, 'combat_popup', False)
        assert first_loaded.wait(5)
        other = pool.submit(update_second)
        assert second_entered.wait(5)
        try:
            # A completed second write here would be overwritten by the first.
            assert not second_loaded.wait(0.1)
        finally:
            release_first.set()
        first.result(timeout=5)
        other.result(timeout=5)
    saved = engine.store.load(game.id)
    assert saved.settings['combat_popup'] is False
    assert saved.settings['achievement_popup'] is False


@pytest.fixture
def local_api(engine, tmp_path):
    class QuietHandler(server.Handler):
        def log_message(self, *_args):
            pass

    httpd = ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', tmp_path):
        thread.start()
        try:
            yield f'http://127.0.0.1:{httpd.server_port}'
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5)


@pytest.mark.parametrize('headers', [
    {'Origin': 'https://outside.example'}, {'Origin': 'null'},
    {'Host': 'outside.example'}, {'Sec-Fetch-Site': 'cross-site'},
    {'Content-Type': 'text/plain'}, {'Content-Type': 'application/x-www-form-urlencoded'},
])
def test_local_api_rejects_cross_site_mutation(local_api, tmp_path, headers):
    request = Request(local_api + '/api/extensions/audit', data=b'{"enabled":false}',
                      headers={'Content-Type': 'application/json', **headers})
    with pytest.raises(HTTPError) as error:
        urlopen(request)
    assert error.value.code == 403
    assert not (tmp_path / 'data/extension_preferences.json').exists()


def test_local_api_accepts_same_origin_and_native_clients(local_api):
    for origin in ({}, {'Origin': local_api}):
        request = Request(local_api + '/api/ui-preferences', data=b'{"theme":"a"}',
                          headers={'Content-Type': 'application/json', **origin})
        with urlopen(request) as response:
            assert json.load(response)['theme'] == 'a'


@pytest.mark.parametrize('value', ['NaN', 'Infinity', '-Infinity', '1e999'])
def test_http_rejects_nonfinite_json_numbers(local_api, value):
    request = Request(local_api + '/api/ui-preferences', data=('{"number":' + value + '}').encode(),
                      headers={'Content-Type': 'application/json'})
    with pytest.raises(HTTPError) as error:
        urlopen(request)
    assert error.value.code == 400


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -float('inf')])
def test_irrigation_rejects_nonfinite_values_without_modifying_save(engine, value):
    game = create(engine)
    game.player.spirit_field['reclaimed_qing'] = 1
    add_item(game.player, 'purple_cloud_ginseng_seed')
    engine.store.save(game)
    planted = engine.plant_spirit_crop(game.id, 'purple_cloud_ginseng')
    crop_id = planted['spirit_field']['plots'][0]['id']
    before = export_snapshot(engine.store, game.id)['payload']
    with pytest.raises(ValueError):
        engine.irrigate_spirit_crop(game.id, crop_id, value)
    assert export_snapshot(engine.store, game.id)['payload'] == before


def test_invalid_numeric_save_does_not_replace_existing_file(engine):
    game = create(engine)
    path = engine.store._path(game.id)
    before = path.read_bytes()
    game.player.mp = float('nan')
    with pytest.raises(ValueError):
        engine.store.save(game)
    assert path.read_bytes() == before
    assert not list(engine.store.directory.glob('*.tmp'))


@pytest.mark.parametrize('item_id', ['true_immortal_breakthrough_1', 'guixu_canghai_consumable_01', 'heroic_progeny_elixir'])
def test_special_pills_cannot_bypass_recipe_whitelist(engine, item_id):
    game = create(engine, realm=8)
    herb = engine._add_harvested_plant(game.player, 'purple_cloud_ginseng', 100)
    engine.store.save(game)
    before = engine.store._path(game.id).read_bytes()
    assert item_id not in engine._alchemy_targets(game.player)
    with pytest.raises(ValueError):
        engine.refine_pill(game.id, item_id, [{'item_id': herb.id, 'quantity': 1}])
    assert engine.store._path(game.id).read_bytes() == before


def test_alchemy_tier_filter_cannot_be_undone_by_fallback(engine):
    game = create(engine)
    targets = engine._alchemy_targets(game.player)
    assert 'healing_pill' in targets and 'foundation_pill' in targets
    high = next(row for row in MARKET_GOODS if row['kind'] == 'item' and row['tier'] == 4
                and 'pill' in ITEM_CATALOG[row['content_id']].tags)
    assert high['content_id'] not in targets
    with pytest.raises(ValueError):
        engine.refine_pill(game.id, high['content_id'], [])
    game.player.realm_index = 3
    assert engine._alchemy_targets(game.player)[high['content_id']]['tier'] == 4


def test_expelled_template_npc_is_not_restored_and_old_duplicate_is_repaired(engine):
    game = create(engine, realm=5)
    sect = game.sects['tianjian']
    game.player.faction_id = sect.id
    sect.founded_by_player = True
    sect.founder_player_id = game.id
    original = copy.deepcopy(sect.npcs[-1])
    engine.store.save(game)
    engine.intrigue_personnel_action(game.id, 'sect', 'expel', original.id)
    saved = engine.store.load(game.id)
    affinity = saved.world_npcs[original.id].affinity
    # Simulate a copy already persisted by the old loader.
    saved.sects[sect.id].npcs.append(original)
    engine.store.save(saved)
    for _ in range(2):
        loaded = engine._load(game.id)
        assert not any(npc.id == original.id for npc in loaded.sects[sect.id].npcs)
        assert loaded.world_npcs[original.id].affinity == affinity
        engine.store.save(loaded)


def test_transferred_template_npc_and_new_content_template_coexist(engine):
    game = create(engine)
    source = game.sects['tianjian']
    target = next(sect for sect in game.sects.values() if sect.id != source.id and sect.world == source.world)
    npc = source.npcs.pop()
    npc.faction_id = target.id
    target.npcs.append(npc)
    # A genuinely missing template still needs content migration.
    missing = source.npcs.pop()
    engine.store.save(game)
    loaded = engine._load(game.id)
    assert not any(row.id == npc.id for row in loaded.sects[source.id].npcs)
    assert sum(row.id == npc.id for sect in loaded.sects.values() for row in sect.npcs) == 1
    assert any(row.id == missing.id for row in loaded.sects[source.id].npcs)


@pytest.mark.parametrize('realm', [1, 3])
def test_batch_resolves_each_unit_but_not_each_year(engine, realm):
    game = create(engine, realm=realm)
    years = int(WORLD_SYSTEMS['time_units'][str(realm)])
    with patch.object(engine, '_advance_world_year', return_value=True), \
         patch.object(engine, '_personal_combat_step', return_value='test') as combat, \
         patch.object(engine, '_select_event', return_value=None), \
         patch.object(engine, '_advance_auction_clock') as auction:
        engine.advance(game.id, 'hunt_beast', 3)
    assert engine.store.load(game.id).player.age == game.player.age + years * 3
    assert combat.call_count == auction.call_count == 3


def test_batch_charges_cost_per_unit_and_stops_on_interruption(engine):
    game = create(engine, realm=3)
    years = int(WORLD_SYSTEMS['time_units']['3'])
    with patch.object(engine, '_advance_world_year', side_effect=[True] * years + [False]), \
         patch.object(engine, '_apply_action_resources') as resources, \
         patch.object(engine, '_select_event', return_value=None):
        engine.advance(game.id, 'travel', 3)
    assert sum(call.args[2] for call in resources.call_args_list) == 2
    assert engine.store.load(game.id).player.age == game.player.age + years + 1


def test_treasure_batch_stops_for_first_manual_reward(engine):
    game = create(engine, realm=1)
    with patch.object(engine, '_advance_world_year', return_value=True), \
         patch.object(engine, '_treasure_step', return_value='test') as treasure:
        engine.advance(game.id, 'treasure', 3)
    loaded = engine.store.load(game.id)
    assert treasure.call_count == 1
    assert loaded.player.age == game.player.age + 1
    assert loaded.pending_event['id'] == 'EVT_TREASURE_REWARD_SELECT_001'


def test_dead_character_cannot_found_faction_or_consume_items(engine):
    game = create(engine)
    game.player.alive = False
    game.player.hp = 0
    add_item(game.player, 'healing_pill')
    engine.store.save(game)
    before = engine.store._path(game.id).read_bytes()
    for operation, args in [(engine.create_faction, ('死后宗门',)),
                            (engine.create_family, ('死后家族',)), (engine.use_item, ('healing_pill',))]:
        with pytest.raises(ValueError):
            operation(game.id, *args)
    assert engine.store._path(game.id).read_bytes() == before
