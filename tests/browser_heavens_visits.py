"""Real HTTP/Chromium study trips, separate detail pages and mobile layout."""
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
from cultivation_life.system.heavens.definitions import CONTACT_SITES, VISIT_DESTINATIONS, default_site
from cultivation_life.system.heavens.state import create_echo, get_echo


def main():
    output = ROOT / 'build/heavens-visits-browser'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        engine = GameEngine(ROOT, root / 'saves')
        ids = []
        for site in CONTACT_SITES:
            key = engine.create_game('诸天访学', 'supreme_metal', site.visitor_path, 4242, preset_id='core')['id']
            game = engine.store.load(key)
            p = game.player
            p.world, p.location_id, p.realm_index = site.world, site.location_id, 9
            p.immortal_power_converted, p.lifespan = site.world == 'celestial', None
            p.hp, p.mp = max_hp(p), max_mp(p)
            p.next_tribulation_age = 999999
            game.settings['silent_events'] = True
            add_item(p, 'spirit_stone', 100000)
            echo = create_echo(engine._dependencies.heavens, game, site.id)
            echo.update(history_checked=True, exchanged=True, correspondence_completed=True, project_stones=17500)
            engine.store.save(game)
            ids.append(key)
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', root):
            httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(headless=True)
                    page = browser.new_page(viewport={'width':1440,'height':1050})
                    errors, results = [], []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.goto(f'http://127.0.0.1:{httpd.server_port}')
                    page.wait_for_function('window.GameThemes && configData')
                    def act(label, years):
                        seq = page.evaluate('game.heavens.next_command_seq')
                        page.get_by_role('button',name=label,exact=True).click()
                        page.locator('#game-confirm-backdrop:not(.hidden)').wait_for()
                        assert f'{years} 年' in page.locator('#game-confirm-body').inner_text()
                        page.locator('#game-confirm-accept').click()
                        page.wait_for_function('seq=>!busy && game.heavens.next_command_seq===seq+1', arg=seq)
                    for index,(key,site) in enumerate(zip(ids,CONTACT_SITES)):
                        page.evaluate('async id=>{await loadGame(id)}', key)
                        if not page.locator('#heavens-card').is_visible():
                            page.locator('[data-panel-target=heavens]').click()
                        page.get_by_role('tab',name='诸界',exact=True).click()
                        page.get_by_role('button',name='查看'+site.name,exact=True).click()
                        page.get_by_role('tab',name='访学',exact=True).click()
                        page.get_by_role('button',name='启程访学',exact=True).wait_for()
                        before = engine.store.load(key)
                        disk = engine.store._path(key).read_bytes()
                        if index == 0:
                            for theme in 'abdf':
                                page.locator('#theme-open').click()
                                page.locator(f'[data-theme-picker=dialog] [data-theme-choice={theme}]').click()
                                page.evaluate('GameThemes.saved')
                                page.locator('[data-close-dialog=theme-dialog]').click()
                                for width in (1440,393):
                                    page.set_viewport_size({'width':width,'height':1050 if width==1440 else 852})
                                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                                    assert page.locator('#heavens-content').evaluate('(el)=>el.scrollWidth<=el.clientWidth+1')
                                    assert page.locator('#heavens-content .heavens-visit-route').count() == 1
                                    assert page.get_by_role('button',name='对照抄录',exact=True).count() == 0
                                    page.screenshot(path=str(output/f'{theme}-{width}-visit.png'))
                            assert engine.store._path(key).read_bytes() == disk
                        act('启程访学',2)
                        destination = default_site(VISIT_DESTINATIONS[site.id])
                        saved = engine.store.load(key)
                        assert saved.player.world == destination.world
                        assert saved.player.location_id == destination.location_id
                        # Reload in the foreign world, then find the held return ticket.
                        page.reload()
                        page.wait_for_function('window.GameThemes && configData')
                        page.evaluate('async id=>{await loadGame(id)}',key)
                        if not page.locator('#heavens-card').is_visible():
                            page.locator('[data-panel-target=heavens]').click()
                        page.get_by_role('tab',name='行程',exact=True).click()
                        page.get_by_role('button',name='查看访学与返程',exact=True).click()
                        page.get_by_role('button',name='实地研读',exact=True).wait_for()
                        act('实地研读',4)
                        page.locator('.heavens-visit-finding').wait_for()
                        assert page.get_by_role('button',name='实地研读',exact=True).count() == 0
                        act('循约返程',2)
                        saved = engine.store.load(key)
                        assert saved.player.world == site.world and saved.player.location_id == site.location_id
                        assert saved.player.age == before.player.age+8
                        assert get_echo(saved.heavens_state['runtime'],site.id)['visit']['status'] == 'returned'
                        assert page.get_by_role('button',name='启程访学',exact=True).count() == 0
                        results.append(dict(source=site.world,destination=destination.world,years=8))
                    assert not errors,errors
                    (output/'report.json').write_text(json.dumps(dict(trips=results,themes=list('abdf'),
                        widths=[1440,393],reload_return_ticket=True,navigation_read_only=True,errors=errors),indent=2),encoding='utf-8')
                    browser.close()
            finally:
                httpd.shutdown()
                httpd.server_close()
    print('Four-world study visits browser checks passed')


if __name__ == '__main__':
    main()
