"""Actual family API interactions plus theme/width checks for new family and Guixu controls."""
import sys
import tempfile
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from test_family_expansion import family_game

def main():
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder);engine=GameEngine(ROOT,root/'data/saves');g=family_game(engine)
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',root):
            httpd=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
            threading.Thread(target=httpd.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch(headless=True);page=browser.new_page();errors=[]
                    page.on('pageerror',lambda e:errors.append(str(e)))
                    page.goto(f'http://127.0.0.1:{httpd.server_port}')
                    page.wait_for_function('window.GameThemes && configData');page.evaluate('GameThemes.ready')
                    page.evaluate('id=>loadGame(id)',g.id)
                    page.evaluate("UtilityPanels.open('family')")
                    def click(action):
                        with page.expect_response(lambda r:'/family-action' in r.url) as response:
                            page.locator(f'[data-family-member="family_heir"] button[data-family*="{action}"]').click()
                        assert response.value.status==200,response.value.text()
                        page.wait_for_timeout(150)
                    click('teach');click('gift_equipment');click('invite');click('infuse');click('marry')
                    saved=engine.store.load(g.id)
                    assert saved.family.npcs[0].family_combat_bonus>0
                    assert saved.family.npcs[0].family_traits['spouse_id']
                    assert any(m['id']=='family_heir' for m in saved.player.party)
                    assert saved.player.opportunity<100000
                    page.add_script_tag(path=str(ROOT/'tests/fixtures/family_guixu_layout.js'))
                    before=page.evaluate('JSON.stringify(game)')
                    for width in (1440,800,393,360):
                        page.set_viewport_size({'width':width,'height':900})
                        for theme in 'abdf':
                            page.evaluate("t=>document.querySelector('[data-theme-picker=dialog] [data-theme-choice='+t+']').click()",theme)
                            page.evaluate('GameThemes.saved')
                            for panel in ('family','offer','guixu'):
                                page.evaluate('p=>FamilyGuixuProbe.mount(p)',panel)
                                page.wait_for_timeout(1100 if theme=='f' else 300)
                                failures=page.evaluate('p=>FamilyGuixuProbe.check(p)',panel)
                                assert not failures,(width,theme,panel,failures)
                                if panel=='family' and width in (1440,393):
                                    page.screenshot(path=str(ROOT/f'build/family-1400-{width}-{theme}.png'))
                                page.evaluate("p=>UtilityPanels.close(p==='family'?'family':'guixu')",panel)
                    assert page.evaluate('JSON.stringify(game)')==before,'Rendering mutated game state'
                    assert not errors,errors
                    browser.close()
            finally:httpd.shutdown();httpd.server_close()
    print('Family live API actions and four themes x four widths x family/invitation/treasure controls: passed; state isolation passed')

if __name__=='__main__':main()
