import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from cultivation_life.ui_preferences import load_ui_preferences, write_ui_preferences


def test_defaults_and_partial_updates_survive_reload(tmp_path):
    assert load_ui_preferences(tmp_path) == {'theme': 'a', 'reduced_motion': False}
    for theme in 'abcdef':
        write_ui_preferences(tmp_path, {'theme': theme})
        assert load_ui_preferences(tmp_path)['theme'] == theme
    write_ui_preferences(tmp_path, {'reduced_motion': True})
    assert load_ui_preferences(tmp_path) == {'theme': 'f', 'reduced_motion': True}
    assert list((tmp_path / 'data').iterdir()) == [tmp_path / 'data/ui_preferences.json']


@pytest.mark.parametrize('payload', [{}, [], {'theme': []}, {'theme': 'g'}, {'theme': 'A'}, {'reduced_motion': 1}, {'unknown': True}])
def test_invalid_update_preserves_existing_preference(tmp_path, payload):
    write_ui_preferences(tmp_path, {'theme': 'b'})
    with pytest.raises(ValueError):
        write_ui_preferences(tmp_path, payload)
    assert load_ui_preferences(tmp_path)['theme'] == 'b'


@pytest.mark.parametrize('raw', ['broken', '[]', 'null', '{"theme":[],"reduced_motion":"true"}'])
def test_corrupt_file_recovers_without_breaking_startup(tmp_path, raw):
    (tmp_path / 'data').mkdir()
    (tmp_path / 'data/ui_preferences.json').write_text(raw, encoding='utf-8')
    assert load_ui_preferences(tmp_path) == {'theme': 'a', 'reduced_motion': False}
    write_ui_preferences(tmp_path, {'theme': 'e'})
    assert load_ui_preferences(tmp_path)['theme'] == 'e'


def test_concurrent_writes_are_atomic_and_do_not_touch_saves(tmp_path):
    saves = tmp_path / 'data/saves'
    saves.mkdir(parents=True)
    sentinel = saves / 'existing.json'
    sentinel.write_text('{"age":38}', encoding='utf-8')
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda theme: write_ui_preferences(tmp_path, {'theme': theme}), 'abcdef' * 5))
    assert json.loads((tmp_path / 'data/ui_preferences.json').read_text())['theme'] in 'abcdef'
    assert sentinel.read_text() == '{"age":38}'
    assert not list((tmp_path / 'data').glob('*.tmp'))
