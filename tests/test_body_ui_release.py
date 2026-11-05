from pathlib import Path
from cultivation_life.version import BASE_GAME_VERSION
from scripts.body_ui_release_scope import TESTS,BROWSERS
ROOT=Path(__file__).resolve().parents[1]

def test_release_scope_has_body_sources_upstreams_and_real_browsers():
    assert BASE_GAME_VERSION=='3.5.3'
    assert len(TESTS)==len(set(TESTS)) and all((ROOT/name).is_file() for name in TESTS)
    for name in BROWSERS:assert (ROOT/'tests'/(name+'.py')).is_file()
    for name in ('field_disciplines','field_discipline_boundaries','divine_lights','monster_body','ghost_body','body_round_wuyun'):
        assert 'tests/test_'+name+'.py' in TESTS

def test_retired_styles_are_absent_from_runtime_sources():
    html=(ROOT/'web/index.html').read_text(encoding='utf8')
    assert 'data-pixel-setting' not in html and 'data-visual="pixel"' in html
    for theme in 'abdf':assert not (ROOT/f'web/themes/{theme}.css').exists()
    assert '/themes/pixel-base.css' in html
    manager=(ROOT/'web/theme-manager.js').read_text(encoding='utf8')
    assert 'data-theme-choice' not in manager and 'data-pixel-setting' not in manager
