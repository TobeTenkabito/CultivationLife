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
from cultivation_life.rules import add_item
from cultivation_life.save_transfer import export_snapshot

ROOT = Path(__file__).resolve().parents[1]


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
