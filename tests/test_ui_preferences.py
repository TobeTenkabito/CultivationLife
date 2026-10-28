import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from cultivation_life.ui_preferences import load_ui_preferences, write_ui_preferences


def test_defaults_and_partial_updates_survive_reload(tmp_path):
    assert load_ui_preferences(tmp_path) == {'theme': 'a', 'reduced_motion': False, 'pixel_art': False, 'pixel_theme': 'light', 'compact_docks': True}
    for theme in 'abdf':
        write_ui_preferences(tmp_path, {'theme': theme})
        assert load_ui_preferences(tmp_path)['theme'] == theme
    write_ui_preferences(tmp_path, {'reduced_motion': True})
    assert load_ui_preferences(tmp_path) == {'theme': 'f', 'reduced_motion': True, 'pixel_art': False, 'pixel_theme': 'light', 'compact_docks': True}
    assert list((tmp_path / 'data').iterdir()) == [tmp_path / 'data/ui_preferences.json']


@pytest.mark.parametrize('payload', [{}, [], {'theme': []}, {'theme': 'g'}, {'theme': 'A'}, {'reduced_motion': 1}, {'pixel_art': 1}, {'pixel_art': 'true'}, {'unknown': True}])
def test_invalid_update_preserves_existing_preference(tmp_path, payload):
    write_ui_preferences(tmp_path, {'theme': 'b'})
    with pytest.raises(ValueError):
        write_ui_preferences(tmp_path, payload)
    assert load_ui_preferences(tmp_path)['theme'] == 'b'


@pytest.mark.parametrize('raw', ['broken', '[]', 'null', '{"theme":[],"reduced_motion":"true"}'])
def test_corrupt_file_recovers_without_breaking_startup(tmp_path, raw):
    (tmp_path / 'data').mkdir()
    (tmp_path / 'data/ui_preferences.json').write_text(raw, encoding='utf-8')
    assert load_ui_preferences(tmp_path) == {'theme': 'a', 'reduced_motion': False, 'pixel_art': False, 'pixel_theme': 'light', 'compact_docks': True}
    write_ui_preferences(tmp_path, {'theme': 'f'})
    assert load_ui_preferences(tmp_path)['theme'] == 'f'


def test_concurrent_writes_are_atomic_and_do_not_touch_saves(tmp_path):
    saves = tmp_path / 'data/saves'
    saves.mkdir(parents=True)
    sentinel = saves / 'existing.json'
    sentinel.write_text('{"age":38}', encoding='utf-8')
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda theme: write_ui_preferences(tmp_path, {'theme': theme}), 'abdf' * 5))
    assert json.loads((tmp_path / 'data/ui_preferences.json').read_text())['theme'] in 'abdf'
    assert sentinel.read_text() == '{"age":38}'
    assert not list((tmp_path / 'data').glob('*.tmp'))


def test_pixel_preference_preserves_theme_navigation_and_motion(tmp_path):
    original = write_ui_preferences(tmp_path, {'theme': 'd', 'reduced_motion': True,
                                             'navigation': {'pins': ['map'], 'recent': []}})
    assert write_ui_preferences(tmp_path, {'pixel_art': True}) == original | {'pixel_art': True}
    assert load_ui_preferences(tmp_path)['pixel_art'] is True
    assert write_ui_preferences(tmp_path, {'pixel_art': False}) == original


def test_two_new_palettes_and_desktop_labels_are_independent(tmp_path):
    write_ui_preferences(tmp_path, {'theme': 'd', 'pixel_art': True, 'pixel_theme': 'dark', 'compact_docks': False})
    saved=load_ui_preferences(tmp_path)
    assert saved['theme']=='d' and saved['pixel_theme']=='dark' and not saved['compact_docks']
    for payload in ({'pixel_theme':'a'}, {'pixel_theme':[]}, {'compact_docks':1}):
        with pytest.raises(ValueError):write_ui_preferences(tmp_path,payload)
        assert load_ui_preferences(tmp_path)==saved
    write_ui_preferences(tmp_path, {'navigation':{'pins':['map'],'recent':[]}})
    assert load_ui_preferences(tmp_path)['pixel_theme']=='dark'
