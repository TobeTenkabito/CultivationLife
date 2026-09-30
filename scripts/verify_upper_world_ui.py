"""Three upper worlds in all themes, including a real ordinary breakthrough."""
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.rules import opportunity_required


class Quiet(server.Handler):
    def log_message(self, *args): pass


def main():
    with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
        server.PERSISTENCE_ROOT=Path(folder)
        engine=server.ENGINE=GameEngine(ROOT,Path(folder)/'saves')
        httpd=ThreadingHTTPServer(('127.0.0.1',0),Quiet)
        threading.Thread(target=httpd.serve_forever,daemon=True).start()
        errors=[]
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch();page=browser.new_page()
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(f'http://127.0.0.1:{httpd.server_port}');page.wait_for_function('configData!==null')
                for world,path in [('asura','demonic'),('nether','monster'),('reincarnation','ghost')]:
                    game=engine.store.load(engine.create_game('三界验收','supreme_metal','dao',1500)['id'])
                    p=game.player;p.world=world;p.path=path;p.realm_index=9;p.layer=1;p.lifespan=None
                    p.location_id=engine.maps.normalize_location(world,None)
                    p.opportunity=opportunity_required(p)*3;game.pending_event=None
                    engine.store.save(game);page.evaluate('(id)=>loadGame(id)',game.id)
                    for theme in 'abcdef':
                        page.evaluate('(t)=>document.querySelector(`[data-theme-picker=dialog] [data-theme-choice=${t}]`).click()',theme)
                        page.evaluate('GameThemes.saved')
                        for width in (1440,412):
                            page.set_viewport_size({'width':width,'height':1000})
                            assert '无尽' not in page.locator('#opportunity-text').inner_text()
                            note=page.locator('#upper-progression-note')
                            assert ('血脉进化' if world=='nether' else '普通修行') in note.inner_text()
                            assert note.evaluate('(e)=>e.scrollWidth<=e.clientWidth+1')
                            page.screenshot(path=str(ROOT/f'build/upper-{world}-{theme}-{width}.png'))
                    if world!='nether':
                        assert page.locator('#breakthrough-panel').is_visible()
                        page.get_by_role('button',name='突破小境界',exact=True).click()
                        page.wait_for_function('!busy')
                        saved=engine.store.load(game.id)
                        assert saved.player.opportunity < opportunity_required(saved.player)
                        assert saved.player.layer in (1,2)
                chapters=page.evaluate('TutorialHandbook.build(configData)')
                assert {'roots','upper-worlds'} <= {c['id'] for c in chapters}
                assert not errors, errors
                browser.close()
        finally:
            httpd.shutdown();httpd.server_close()
    print('Six-theme upper worlds UI passed: finite opportunity, DLC routing, ordinary action, mobile layout and handbook.')


if __name__=='__main__': main()
