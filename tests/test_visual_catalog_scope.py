"""Catalog reuse must not retain mutable public tables or player eligibility."""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

import pytest

from cultivation_life import character_skins as skins, visual_assets as assets
from cultivation_life.engine import GameEngine
from cultivation_life.engine.transactions import request_scope
from cultivation_life.errors import NotFoundError
from cultivation_life.models import Player

ROOT = Path(__file__).resolve().parents[1]


def package(root, *, filename='first.png'):
    content = root / 'content'
    content.mkdir(parents=True, exist_ok=True)
    (content / 'visual_assets.json').write_text(json.dumps(dict(schema_version=1,
        assets={'base': dict(file='/assets/base.png', requires=[])},
        items={}, molds={}, plants={}, crafting_materials={}, maps={})), encoding='utf-8')
    folder = root / 'dlc/example/assets'
    folder.mkdir(parents=True, exist_ok=True)
    (folder.parent / 'manifest.json').write_text(json.dumps(
        dict(id='example', visual_registry='registry.json')), encoding='utf-8')
    (folder / filename).write_bytes(b'asset')
    (folder / 'registry.json').write_text(json.dumps(dict(assets={
        'extra': dict(file=f'/extension-assets/example/{filename}', requires=['example'])})), encoding='utf-8')
    return [dict(id='example', status='loaded')]


def test_public_tables_independent_and_enabled_packages_rechecked_in_scope(tmp_path):
    extensions = package(tmp_path)
    with assets.catalog_scope():
        first = assets.public_catalog(tmp_path, extensions)
        first['assets'].clear()
        first['items']['forged'] = 'extra'
        assert set(assets.public_catalog(tmp_path, extensions)['assets']) == {'base', 'extra'}
        assert not assets.public_catalog(tmp_path, extensions)['items']
        assert assets.extension_asset(tmp_path, tmp_path, extensions,
            '/extension-assets/example/first.png').is_file()
        extensions[0]['status'] = 'disabled'
        assert set(assets.public_catalog(tmp_path, extensions)['assets']) == {'base'}
        with pytest.raises(NotFoundError):
            assets.extension_asset(tmp_path, tmp_path, extensions, '/extension-assets/example/first.png')
        extensions[0]['status'] = 'loaded'
        assert 'extra' in assets.public_catalog(tmp_path, extensions)['assets']


def test_roots_separate_and_next_request_observes_registry_changes(tmp_path):
    one, two = tmp_path / 'one', tmp_path / 'two'
    extensions = package(one)
    package(two, filename='other.png')
    with assets.catalog_scope():
        assert assets.catalog_assets(one, extensions)['extra']['file'].endswith('first.png')
        assert assets.catalog_assets(two, extensions)['extra']['file'].endswith('other.png')
        assert assets.catalog_assets(one, extensions, two)['extra']['file'].endswith('other.png')
    package(one, filename='replacement.png')
    with assets.catalog_scope():
        assert assets.catalog_assets(one, extensions)['extra']['file'].endswith('replacement.png')


def test_nested_scope_cleanup_on_failure_and_thread_isolation():
    assert assets.catalog_context() is None
    with pytest.raises(ValueError):
        with assets.catalog_scope():
            first = assets.catalog_context()
            with assets.catalog_scope():
                assert assets.catalog_context() is first
            raise ValueError('failed request')
    assert assets.catalog_context() is None
    barrier = Barrier(2)

    def request(value):
        with assets.catalog_scope():
            context = assets.catalog_context()
            context.catalogs['private'] = value
            barrier.wait(timeout=10)
            assert context.catalogs['private'] == value
            return context

    with ThreadPoolExecutor(max_workers=2) as workers:
        one, two = [future.result() for future in [workers.submit(request, 1), workers.submit(request, 2)]]
    assert one is not two and assets.catalog_context() is None


def test_cached_forms_do_not_cache_unlock_path_gender_or_blocked_state():
    key = 'actor.cosmetic.reward'
    form = dict(static=key, combat='reward', scope='path', path='demonic',
                gender='female', achievement='earned')
    table = {key + '.figure': dict(file='/figure.png'),
             key + '.portrait': dict(file='/portrait.png'), 'manifest': dict(skin_forms=[form])}
    player = Player('Reward', 'none', path='demonic', gender='female')
    with patch.object(skins, '_assets', return_value=table), assets.catalog_scope():
        assert not skins.eligible_skins(player)
        assert skins.unlock_achievement_rewards(player, {'earned': {}})
        assert skins.eligible_skins(player)[0]['id'] == key
        first = skins._catalog_forms(table)
        first[key]['gender'] = 'male'
        first['player-specific'] = dict(static='player-specific')
        assert skins._catalog_forms(table)[key]['gender'] == 'female'
        assert 'player-specific' not in skins._catalog_forms(table)
        player.path = 'dao'
        assert not skins.eligible_skins(player)
        player.path, player.gender = 'demonic', 'male'
        assert not skins.eligible_skins(player)
        player.gender = 'female'
        player.ghost_host_body = {'id': 'host'}
        assert skins.public(player)['blocked']
        with pytest.raises(ValueError):
            skins.choose(player, key)


def test_engine_and_http_scopes_reuse_only_static_preparation(tmp_path):
    engine = GameEngine(ROOT, tmp_path / 'saves')
    made = engine.create_game('Catalog', 'heavenly', 'dao', 280, preset_id='core')
    identity = made['id']
    engine.get_game(identity)
    saved = engine.store._path(identity).read_bytes()
    with patch.object(assets, '_build_public_catalog', wraps=assets._build_public_catalog) as catalogs, \
         patch.object(skins, '_build_catalog_forms', wraps=skins._build_catalog_forms) as forms:
        direct = engine.get_game(identity)
        assert catalogs.call_count == forms.call_count == 1
        assert assets.catalog_context() is None
        catalogs.reset_mock(); forms.reset_mock()
        with request_scope(engine):
            assert engine.get_game(identity) == direct
            assert engine.get_game(identity) == direct
            assert catalogs.call_count == forms.call_count == 1
        assert assets.catalog_context() is None
        engine.get_game(identity)
        assert catalogs.call_count == forms.call_count == 2
    assert engine.store._path(identity).read_bytes() == saved
