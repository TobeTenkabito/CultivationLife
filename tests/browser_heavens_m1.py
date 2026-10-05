"""Real HTTP/UI M1 smoke: six themes, narrow screens and lost response retry."""
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
from cultivation_life.engine import GameEngine
from cultivation_life.rules import add_item, max_hp, max_mp


def main():
    output = ROOT / 'build/heavens-m1-browser'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        engine = GameEngine(ROOT, root / 'saves')
        key = engine.create_game('观海客', 'heavenly', 'dao', 4242, preset_id='core')['id']
        game = engine.store.load(key)
        p = game.player
        p.world, p.location_id, p.realm_index = 'celestial', 'law_sea', 9
        p.immortal_power_converted, p.lifespan = True, None
        p.hp, p.mp = max_hp(p), max_mp(p)
        p.next_tribulation_age = 999999
        add_item(p, 'spirit_stone', 100000)
        engine.store.save(game)
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', root):
            httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(headless=True)
                    page = browser.new_page(viewport={'width':1440, 'height':1050})
                    errors=[]
                    page.on('pageerror', lambda err: errors.append(str(err)))
                    page.goto(f'http://127.0.0.1:{httpd.server_port}')
                    page.wait_for_function('window.GameThemes && configData')
                    page.evaluate('GameThemes.ready')
                    page.evaluate('async id=>{await loadGame(id)}', key)
                    page.locator('[data-panel-target=heavens]').click()
                    page.get_by_role('tab',name='诸界',exact=True).click()
                    page.get_by_role('button',name='查看法则天海 · 潮汐回响',exact=True).click()
                    before = engine.store._path(key).read_bytes()
                    page.locator('#heavens-content').get_by_role('button',name='体察潮汐',exact=True).click()
                    page.locator('#game-confirm-backdrop:not(.hidden)').wait_for()
                    assert '20 年' in page.locator('#game-confirm-body').inner_text()
                    assert engine.store._path(key).read_bytes() == before
                    # Lose only the response after a successful commit, then retry.
                    requests=[]
                    def lose_response(route):
                        requests.append(route.request.post_data_json)
                        route.fetch()
                        route.abort()
                    page.route('**/heavens-command', lose_response, times=1)
                    page.locator('#game-confirm-accept').click()
                    page.get_by_role('button',name='重试上次提交（不会重复扣费）',exact=True).wait_for()
                    saved=engine.store.load(key)
                    age=saved.player.age
                    page.get_by_role('button',name='重试上次提交（不会重复扣费）',exact=True).click()
                    page.wait_for_function('!busy && game.heavens.next_command_seq === 2')
                    assert engine.store.load(key).player.age == age
                    assert requests[0]['command_seq'] == 1
                    assert page.locator('#heavens-content').get_by_text('法则天海 · 潮汐回响',exact=True).is_visible()
                    snapshot=engine.store._path(key).read_bytes()
                    for theme in 'abcdef':
                        page.locator('#theme-open').click()
                        page.locator(f'[data-theme-picker=dialog] [data-theme-choice={theme}]').click()
                        page.evaluate('GameThemes.saved')
                        page.locator('[data-close-dialog=theme-dialog]').click()
                        for width in (1440,393):
                            page.set_viewport_size({'width':width,'height':1050 if width==1440 else 852})
                            page.wait_for_timeout(120)
                            assert page.locator('#heavens-card').is_visible()
                            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'), (theme,width)
                            assert page.locator('#heavens-content').evaluate('(el)=>el.scrollWidth<=el.clientWidth+1'), (theme,width)
                            page.screenshot(path=str(output / f'{theme}-{width}.png'))
                        page.set_viewport_size({'width':1440,'height':1050})
                    assert engine.store._path(key).read_bytes() == snapshot
                    # Another client commits settings; a stale panel must recover
                    # from the business rejection and obtain the next sequence.
                    state=engine.store.load(key).heavens_state
                    engine.heavens_command(key,state['command_seq']+1,state['revision'],'configure',options={'watch':False})
                    page.get_by_role('button',name='诸天偏好',exact=True).click()
                    page.locator('#heavens-content input').first.uncheck()
                    page.wait_for_function('!busy && game.heavens.next_command_seq === 3')
                    assert page.locator('#heavens-content input').first.is_checked()
                    assert not page.locator('#heavens-content input').nth(1).is_checked()
                    page.locator('#heavens-content input').nth(1).check()
                    page.wait_for_function('!busy && game.heavens.next_command_seq === 4')
                    assert engine.store.load(key).player.age == age
                    assert not errors, errors
                    (output / 'report.json').write_text(json.dumps(dict(themes=6,widths=[1440,393],
                        lost_response_retry=True,stale_view_recovered=True,duplicate_years=0,errors=errors),indent=2),encoding='utf-8')
                    browser.close()
            finally:
                httpd.shutdown(); httpd.server_close()
    print('M1 browser: six themes, two widths, preview purity and response-loss retry passed')


if __name__ == '__main__':
    main()
