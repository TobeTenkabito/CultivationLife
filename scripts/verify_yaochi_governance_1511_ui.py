"""Six-theme browser acceptance: locked stock, NPC cabinet and categorized contacts."""
import random
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.models import SectNpc

class Quiet(server.Handler):
    def log_message(self,*args): pass

def main():
    with tempfile.TemporaryDirectory(dir=ROOT/'build') as directory:
        server.PERSISTENCE_ROOT=Path(directory)
        e=server.ENGINE=GameEngine(ROOT,Path(directory)/'saves')
        made=e.create_game('瑶池故人验收','supreme_metal','dao',seed=1511,preset_id='true_immortal')
        g=e._load(made['id']);g.pending_event=None;g.heavenly_court['open_election']=None
        g.player.location_id='expanse_celestial_8';g.yaochi_state['merit']=100000
        sect=next(s for s in g.sects.values() if s.world=='celestial' and not s.extinct and s.npcs)
        g.player.faction_id=sect.id
        npc=SectNpc(id='ui_contact',name='云笺客',title='游历修士',realm_index=9,layer=1,age=1000,lifespan=None,world='celestial',spirit_root='supreme_metal',affinity=40)
        g.encounter_npc_cache.append(dict(id=npc.id,npc=npc.to_dict(),last_seen_age=g.player.age))
        g.heavenly_court['player_grade']=9;e._advance_heavenly_court_unit(g,random.Random(9));e.store.save(g)
        httpd=ThreadingHTTPServer(('127.0.0.1',0),Quiet);threading.Thread(target=httpd.serve_forever,daemon=True).start()
        errors=[]
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch();page=browser.new_page();page.emulate_media(reduced_motion='reduce')
                page.route('**/merchant-preview',lambda route:route.fulfill(status=400,content_type='application/json',body='{"error":"Isolated non-merchant test"}'))
                page.on('pageerror',lambda err:errors.append(str(err)))
                page.goto(f'http://127.0.0.1:{httpd.server_port}');page.wait_for_function('configData!==null')
                page.evaluate('(id)=>loadGame(id)',g.id)
                for theme in 'abdf':
                    page.evaluate('(t)=>document.querySelector(`[data-theme-picker=dialog] [data-theme-choice=${t}]`).click()',theme);page.evaluate('GameThemes.saved')
                    for width,height in [(1440,1080),(412,915),(915,412)]:
                        page.set_viewport_size(dict(width=width,height=height))
                        for panel in ['yaochi','heavenly-court','relationship']:
                            page.evaluate('(p)=>UtilityPanels.open(p)',panel)
                            assert page.locator(f'#{panel}-card').evaluate('e=>e.scrollWidth<=e.clientWidth+1'),(theme,width,panel)
                            if width==412:page.screenshot(path=str(ROOT/f'build/governance-1511-{panel}-{theme}.png'))
                page.evaluate("UtilityPanels.open('yaochi')")
                book=page.evaluate('game.yaochi.shop.find(o=>o.can_lock).id')
                page.locator(f'[data-offer-id="{book}"] button').nth(1).click()
                page.wait_for_function('game.yaochi.locked_count===1 && !busy')
                saved=e._load(g.id);saved.player.age+=300;e.store.save(saved)
                page.evaluate('(id)=>loadGame(id)',g.id)
                assert page.evaluate('(id)=>game.yaochi.shop.some(o=>o.id===id&&o.locked)',book)
                page.locator(f'[data-offer-id="{book}"] button').first.click();page.wait_for_function('game.yaochi.locked_count===0')
                page.evaluate("UtilityPanels.open('heavenly-court')")
                assert page.locator('.court-governance').inner_text().find('主持天庭议政')>=0
                page.evaluate("UtilityPanels.open('relationship')")
                page.get_by_role('button',name='一面之缘',exact=True).click()
                page.get_by_role('searchbox',name='搜索重要人物').fill('云笺客')
                assert page.locator('.contact-person').count()==1
                page.locator('[data-contact-action=improve]').click()
                page.wait_for_function("game.world_npcs.some(n=>n.id==='ui_contact'&&n.affinity>40)")
                page.get_by_role('searchbox',name='搜索重要人物').fill('')
                page.get_by_role('button',name='重要人物',exact=True).click()
                page.get_by_role('searchbox',name='搜索重要人物').fill('云笺客')
                assert page.locator('.contact-person').count()==1
                assert page.locator('[data-contact-action=improve]').is_disabled()
                page.get_by_role('searchbox',name='搜索重要人物').fill('')
                page.get_by_role('button',name='宗门同道',exact=True).click()
                assert page.locator('.contact-person').count()>0
                assert page.locator('.contact-action').count()==10
                assert page.locator('#npc-contacts select').count()==0
                assert not errors,errors
                browser.close()
        finally:httpd.shutdown()
    print('Yaochi governance UI passed: four themes and three viewports, stock lock/purchase/reload, autonomous cabinet, categorized NPC search and actual interactions')

if __name__=='__main__':main()
