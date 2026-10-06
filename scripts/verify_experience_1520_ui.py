"""Six-theme compact collections, real visitor retention and election settings."""
import copy
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
from cultivation_life.models import Technique
from cultivation_life.rules import learn_technique


class Quiet(server.Handler):
    def log_message(self, *args): pass


def main():
    with tempfile.TemporaryDirectory(dir=ROOT/'build') as directory:
        server.PERSISTENCE_ROOT = Path(directory)
        engine = server.ENGINE = GameEngine(ROOT, Path(directory)/'saves')
        g = engine.store.load(engine.create_game('体验验收', 'supreme_metal', 'dao', 1520,
                                               preset_id='true_immortal')['id'])
        g.pending_event = None
        g.player.location_id = 'expanse_celestial_8'
        g.heavenly_court['player_grade'] = 4
        g.yaochi_state['experience'] = 900
        for definition in g.doctrine_state['definitions'].values():
            learn_technique(g.player, Technique(**copy.deepcopy(definition['manuals'][0])))
            g.doctrine_state['player']['progress'][definition['id']] = dict(level=4, experience=0)
        key = next(iter(g.doctrine_state['definitions']))
        g.doctrine_state['player']['active'] = key
        engine.store.save(g)
        httpd = ThreadingHTTPServer(('127.0.0.1',0), Quiet)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        errors=[]
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch()
                page=browser.new_page(viewport={'width':1440,'height':1000})
                page.emulate_media(reduced_motion='reduce')
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(f'http://127.0.0.1:{httpd.server_port}')
                page.wait_for_function('configData!==null')
                page.evaluate('(id)=>loadGame(id)',g.id)
                for theme in 'abdf':
                    page.evaluate('(t)=>document.querySelector(`[data-theme-picker=dialog] [data-theme-choice=${t}]`).click()',theme)
                    for width,height in [(1440,1000),(412,915),(915,412)]:
                        page.set_viewport_size(dict(width=width,height=height))
                        for panel, attribute, search in [('doctrine','doctrine','搜索已获道统'),
                            ('voisinage','voisinage','搜索邻域名称、道统或能力'),('daomen','daomen','搜索道门')]:
                            page.evaluate('(p)=>UtilityPanels.open(p)',panel)
                            cards=page.locator(f'#{panel}-content .doctrine-compact')
                            assert cards.count()==25
                            assert cards.locator(':scope > summary').first.is_visible()
                            assert cards.locator(':scope > summary').first.bounding_box()['height'] < 300
                            search_box=page.get_by_role('searchbox',name=search,exact=True)
                            search_box.fill('不存在的道统')
                            assert cards.locator('visible=true').count()==0
                            search_box.fill('')
                            target=page.locator(f'[data-{attribute}-id="{key}"]')
                            if not target.evaluate('e=>e.open'):
                                target.locator(':scope > summary').click()
                            assert target.evaluate('e=>e.open')
                            assert page.locator(f'#{panel}-card').evaluate('e=>e.scrollWidth<=e.clientWidth+1')
                            target.locator(':scope > summary').click()
                            if width==412 and panel=='voisinage':
                                page.screenshot(path=str(ROOT/f'build/experience-{theme}-1520.png'))
                        page.evaluate("UtilityPanels.open('yaochi')")
                        assert '瑶池等级 Lv4' in page.locator('.yaochi-experience').inner_text()
                        assert '×1.3' in page.locator('.yaochi-experience').inner_text()
                        assert page.locator('#yaochi-card').evaluate('e=>e.scrollWidth<=e.clientWidth+1')
                page.set_viewport_size(dict(width=1440,height=1000))
                page.evaluate("UtilityPanels.open('daomen')")
                card=page.locator(f'[data-daomen-id="{key}"]')
                card.locator(':scope > summary').click()
                age=page.evaluate('game.player.age')
                roster=len(engine.store.load(g.id).notable_npcs)
                card.get_by_role('button',name='寻找同道 · 不消耗时间',exact=True).click()
                page.wait_for_function('(k)=>!busy && !!game.doctrines.rows.find(r=>r.id===k).peer_preview',arg=key)
                assert len(engine.store.load(g.id).notable_npcs)==roster
                assert card.evaluate('e=>e.open')
                card.get_by_role('button',name='结识这位同道',exact=False).click()
                page.wait_for_function('(k)=>!busy && game.doctrines.rows.find(r=>r.id===k).peers.length===1',arg=key)
                assert page.evaluate('game.player.age')==age
                assert len(engine.store.load(g.id).notable_npcs)==roster+1
                page.evaluate("UtilityPanels.open('settings')")
                page.locator('#setting-court-election').check()
                page.wait_for_function('!busy && game.settings.court_election_popup===false')
                page.evaluate('(id)=>loadGame(id)',g.id)
                assert engine.store.load(g.id).settings['court_election_popup'] is False
                assert not errors,errors
                browser.close()
        finally:
            httpd.shutdown()
    print('Experience UI passed: four themes, three viewports, 25 collapsed searchable collections, retained open state, real free preview and retained peer, settings persistence and Yaochi experience')


if __name__=='__main__': main()
