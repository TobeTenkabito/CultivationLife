"""M3 round one HTTP UI: separate directory, local evidence and peaceful recall."""
import json
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from test_heavens_frontier import local, site, ready, arrive, load


def main():
    output = ROOT/'build/heavens-m3-r1-browser'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        fixture = ready.__wrapped__(site.__wrapped__(local.__wrapped__(Path(folder))))
        engine, initial, _ = fixture
        arrive(fixture)
        key = initial.id
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', Path(folder)):
            httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(headless=True)
                    page = browser.new_page(viewport={'width':1440, 'height':1050})
                    errors = []
                    page.on('pageerror', lambda e: errors.append(str(e)))
                    page.goto(f'http://127.0.0.1:{httpd.server_port}')
                    page.wait_for_function('window.GameThemes && configData')
                    page.evaluate('async id=>{await loadGame(id)}', key)
                    page.locator('[data-panel-target=heavens]').click()
                    snapshot = engine.store._path(key).read_bytes()
                    page.get_by_role('tab', name='战局', exact=True).click()
                    assert page.locator('#heavens-content .heavens-destination').count() == 1
                    assert page.get_by_role('button', name='查明先遣身份', exact=True).count() == 0
                    page.get_by_role('button', name='查看岚疆边情', exact=True).click()
                    assert page.get_by_role('tab', name='情报', exact=True).count() == 1
                    assert 'bp_' not in page.locator('#heavens-content').inner_text()
                    page.get_by_role('tab', name='现场', exact=True).click()
                    page.get_by_role('button', name='查明先遣身份', exact=True).click()
                    page.locator('#game-confirm-backdrop:not(.hidden)').wait_for()
                    assert engine.store._path(key).read_bytes() == snapshot
                    page.locator('#game-confirm-cancel').click()
                    assert engine.store._path(key).read_bytes() == snapshot
                    page.get_by_role('button', name='查明先遣身份', exact=True).click()
                    page.locator('#game-confirm-accept').click()
                    page.wait_for_function('!busy && game.heavens.frontier.observed')
                    work = engine.store.load(key)
                    assert work.heavens_state['runtime']['frontier']['observed']
                    before = work.player.age
                    page.get_by_role('button', name='出示修复凭据', exact=True).click()
                    page.locator('#game-confirm-accept').click()
                    page.wait_for_function("!busy && game.heavens.frontier.reports.some(r=>r.kind==='agreement')")
                    work = engine.store.load(key)
                    assert work.player.age == before+2
                    row = work.heavens_state['runtime']['frontier']
                    assert row['phase'] == 'returning' and work.world_npcs[row['person_id']].world == 'human'
                    page.reload()
                    page.wait_for_function('window.GameThemes && configData')
                    page.evaluate('async id=>{await loadGame(id)}', key)
                    if not page.locator('#heavens-card').is_visible(): page.locator('[data-panel-target=heavens]').click()
                    snapshot = engine.store._path(key).read_bytes()
                    for theme in 'abcdef':
                        page.locator('#theme-open').click()
                        page.locator(f'[data-theme-picker=dialog] [data-theme-choice={theme}]').click()
                        page.locator('[data-close-dialog=theme-dialog]').click()
                        for width in (1440,393,320):
                            page.set_viewport_size({'width':width, 'height':1050 if width == 1440 else 852})
                            page.get_by_role('tab', name='战局', exact=True).click()
                            page.get_by_role('button', name='查看岚疆边情', exact=True).click()
                            for tab in ('情报','现场'):
                                page.get_by_role('tab', name=tab, exact=True).click()
                                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                                assert page.locator('#heavens-content').evaluate('el=>el.scrollWidth<=el.clientWidth+1')
                                assert page.locator('#heavens-body').evaluate('el=>el.scrollWidth<=el.clientWidth+1')
                                assert page.locator('[data-ruins=field]').count() == 0
                                assert page.get_by_role('button', name='部署托管护持', exact=True).count() == 0
                                if width != 320: page.screenshot(path=str(output/f'{theme}-{width}-{tab}.png'))
                    assert engine.store._path(key).read_bytes() == snapshot
                    assert not errors, errors
                    (output/'report.json').write_text(json.dumps(dict(themes=list('abcdef'),widths=[1440,393,320],errors=errors,
                        local_scout=True,peaceful_return_started=True,pure_navigation=True),indent=2),encoding='utf-8')
                    browser.close()
            finally:
                httpd.shutdown()
                httpd.server_close()
    print('M3 frontier HTTP / six-theme browser acceptance passed')


if __name__ == '__main__':
    main()
