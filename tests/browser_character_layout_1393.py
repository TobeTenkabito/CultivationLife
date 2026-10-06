"""Real layout regression: populated NPCs, many actions, long names, all four themes."""
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

def main():
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder)
        engine=GameEngine(ROOT,root/'data/saves')
        gid=engine.create_game('布局验收','heavenly','dao',1393,preset_id='core')['id']
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',root):
            httpd=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
            threading.Thread(target=httpd.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch(headless=True)
                    page=browser.new_page()
                    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    page.goto(f'http://127.0.0.1:{httpd.server_port}')
                    page.wait_for_function('window.GameThemes && configData')
                    page.evaluate('GameThemes.ready')
                    page.evaluate('id=>loadGame(id)',gid)
                    page.add_script_tag(path=str(ROOT/'tests/fixtures/character_layout.js'))
                    before=page.evaluate('JSON.stringify(game)')
                    for width in (1440,800,393,360):
                        page.set_viewport_size({'width':width,'height':900})
                        for theme in 'abdf':
                            page.evaluate("t=>document.querySelector('[data-theme-picker=dialog] [data-theme-choice='+t+']').click()",theme)
                            page.evaluate('GameThemes.saved')
                            for panel in ('faction','world-npc','family','relationship','sage'):
                                page.evaluate('p=>CharacterLayoutProbe.mount(p)',panel)
                                page.wait_for_function("p=>getComputedStyle(document.getElementById(p+'-card')).visibility==='visible'",arg=panel)
                                page.wait_for_timeout(1000 if theme=='f' else 250)
                                failures=page.evaluate('p=>CharacterLayoutProbe.check(p)',panel)
                                assert not failures,(width,theme,panel,failures)
                                if panel=='faction' and width in (1440,393):
                                    page.evaluate("()=>{const c=document.querySelector('#faction-card'),r=document.querySelector('#faction-roster');c.scrollTop+=r.getBoundingClientRect().top-c.getBoundingClientRect().top-110;}")
                                    page.screenshot(path=str(ROOT/f'build/sect-1393-{width}-{theme}.png'))
                                page.evaluate('p=>UtilityPanels.close(p)',panel)
                    assert page.evaluate('JSON.stringify(game)')==before,'Rendering modified game state'
                    assert not errors,errors
                    browser.close()
            finally:httpd.shutdown();httpd.server_close()
    print('Six themes x four widths x five populated character lists: layout and state isolation passed')

if __name__=='__main__':main()
