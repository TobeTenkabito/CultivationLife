"""Actual map data and upgrade API, followed by six independent theme layouts."""
import copy
import sys
import tempfile
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.content_registry import TECHNIQUE_CATALOG
from cultivation_life.engine import GameEngine
from cultivation_life.rules import acquire_technique, add_technique_copy


def main():
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        engine = GameEngine(ROOT, root / 'data/saves')
        gid = engine.create_game('山河问道', 'supreme_metal', 'dao', 1410)['id']
        game = engine.store.load(gid)
        game.player.realm_index, game.player.layer = 5, 3
        technique = copy.deepcopy(TECHNIQUE_CATALOG['TECH_COMMON_GUI'])
        acquire_technique(game.player, technique)
        add_technique_copy(game.player, technique)
        engine.store.save(game)
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', root):
            httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(headless=True)
                    page = browser.new_page()
                    errors=[]
                    page.on('pageerror', lambda error:errors.append(str(error)))
                    page.goto(f'http://127.0.0.1:{httpd.server_port}')
                    page.wait_for_function('window.GameThemes && configData')
                    page.evaluate('GameThemes.ready')
                    page.evaluate('id=>loadGame(id)',gid)
                    assert page.evaluate('game.map.locations.some(p=>p.factions.length>0)')
                    page.evaluate("document.querySelector('#player-details-dialog').showModal();document.querySelector('#known-technique-list').closest('details').open=true")
                    with page.expect_response(lambda response:'/technique-upgrade' in response.url) as result:
                        page.locator('#known-technique-list .technique-upgrade').click()
                    assert result.value.status==200, result.value.text()
                    page.wait_for_function("game.player.known_techniques.some(t=>t.id==='TECH_COMMON_GUI'&&t.level===2)")
                    assert engine.store.load(gid).player.known_techniques[0].level==2
                    page.add_script_tag(path=str(ROOT/'tests/fixtures/world_update_layout.js'))
                    before=page.evaluate('JSON.stringify(game)')
                    for width in (1440,800,393,360):
                        page.set_viewport_size({'width':width,'height':1000})
                        for theme in 'abdf':
                            page.evaluate("t=>document.querySelector('[data-theme-picker=dialog] [data-theme-choice='+t+']').click()",theme)
                            page.evaluate('GameThemes.saved')
                            for panel in ('map','growth'):
                                page.evaluate('p=>WorldUpdateProbe.mount(p)',panel)
                                page.wait_for_timeout(1100 if theme=='f' else 250)
                                failures=page.evaluate('p=>WorldUpdateProbe.check(p)',panel)
                                assert not failures,(width,theme,panel,failures)
                                if width in (1440,393):
                                    page.screenshot(path=str(ROOT/f'build/world-1410-{panel}-{width}-{theme}.png'))
                    assert page.evaluate('JSON.stringify(game)')==before,'Rendering mutated saved game'
                    assert not errors,errors
                    browser.close()
            finally:
                httpd.shutdown();httpd.server_close()
    print('World map and technique API; four themes x four widths passed; state isolation passed')


if __name__=='__main__':
    main()
