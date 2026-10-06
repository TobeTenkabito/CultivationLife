"""Real fusion/study actions and four-theme responsive presentation."""
import copy
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys
import tempfile
import threading

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.models import Technique
from cultivation_life.rules import learn_technique

class Quiet(server.Handler):
    def log_message(self,*args): pass

def main():
    with tempfile.TemporaryDirectory(dir=ROOT/'build') as directory:
        server.PERSISTENCE_ROOT=Path(directory)
        engine=server.ENGINE=GameEngine(ROOT,Path(directory)/'saves')
        g=engine.store.load(engine.create_game('合练验收','supreme_metal','dao',1512,preset_id='true_immortal')['id'])
        g.pending_event=None;g.heavenly_court['open_election']=None
        g.player.realm_index=12;g.player.immortal_traces=1000
        g.player.next_tribulation_age=None
        d=next(d for d in g.doctrine_state['definitions'].values() if len(d['manuals'])>=6)
        key=d['id']
        for book in d['manuals']: learn_technique(g.player,Technique(**copy.deepcopy(book)))
        record=g.doctrine_state['player'];record['progress'][key]={'level':4,'experience':0};record['active']=key
        engine.store.save(g)
        httpd=ThreadingHTTPServer(('127.0.0.1',0),Quiet);threading.Thread(target=httpd.serve_forever,daemon=True).start()
        errors=[]
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch();page=browser.new_page(viewport={'width':1440,'height':1000})
                page.emulate_media(reduced_motion='reduce');page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(f'http://127.0.0.1:{httpd.server_port}');page.wait_for_function('configData!==null')
                page.evaluate('(id)=>loadGame(id)',g.id);page.evaluate("UtilityPanels.open('doctrine')")
                page.locator(f'[data-doctrine-id="{key}"] > summary').click()
                box=page.locator(f'[data-fusion-id="{key}"]')
                box.get_by_role('button',name='合练全套传承',exact=True).click()
                page.wait_for_function('(key)=>game.doctrines.rows.find(r=>r.id===key).fusion.level===1',arg=key)
                assert page.evaluate('game.doctrines.voisinages[0].name.startsWith("真·")')
                assert page.evaluate('game.player.immortal_traces')==976
                box.get_by_role('button',name='参悟合练功法',exact=True).click()
                page.wait_for_function('(key)=>{const f=game.doctrines.rows.find(r=>r.id===key).fusion;return f.level>1||f.experience>0}',arg=key)
                saved=engine.store.load(g.id);saved.pending_event=None;saved.heavenly_court['open_election']=None
                engine.store.save(saved);page.evaluate('(id)=>loadGame(id)',g.id)
                for theme in 'abdf':
                    page.evaluate('(t)=>document.querySelector(`[data-theme-picker=dialog] [data-theme-choice=${t}]`).click()',theme)
                    for width in (1440,412):
                        page.set_viewport_size({'width':width,'height':1000})
                        page.evaluate("UtilityPanels.open('doctrine')")
                        box.scroll_into_view_if_needed()
                        assert '仙痕' in box.inner_text()
                        assert page.locator('#doctrine-card').evaluate('e=>e.scrollWidth<=e.clientWidth+1')
                        if width==412: page.screenshot(path=str(ROOT/f'build/fusion-1512-{theme}.png'))
                        page.evaluate("UtilityPanels.close('doctrine');UtilityPanels.open('voisinage')")
                        assert '真·' in page.locator('#voisinage-content').inner_text()
                        page.evaluate("UtilityPanels.close('voisinage');UtilityPanels.open('yaochi')")
                        assert '当前境界可求取' in page.locator('#yaochi-content').inner_text()
                        assert page.locator('#yaochi-content optgroup').count()==26
                        page.evaluate("UtilityPanels.close('yaochi')")
                assert not errors,errors
                browser.close()
        finally: httpd.shutdown()
    print('Fusion UI passed: actual collection/study, trace payment, true voisinage, four themes, grouped commission catalog')

if __name__=='__main__': main()
