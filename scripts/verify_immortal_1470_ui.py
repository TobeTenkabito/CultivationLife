"""Real quick-start, instant teleport, spirit domain and commission controls."""
import sys, tempfile, threading
from pathlib import Path
from http.server import ThreadingHTTPServer
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.rules import max_hp,max_mp
from cultivation_life.system.spirit_voisinage import catalog,grant

class Quiet(server.Handler):
    def log_message(self,*args):pass

def main():
    with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
        server.PERSISTENCE_ROOT=Path(folder)
        e=server.ENGINE=GameEngine(ROOT,Path(folder)/'saves')
        made=e.create_game('仙窍验收','supreme_metal','dao',seed=1470,preset_id='true_immortal')
        g=e.store.load(made['id']);g.pending_event=None;g.heavenly_court['open_election']=None;e.store.save(g)
        httpd=ThreadingHTTPServer(('127.0.0.1',0),Quiet);threading.Thread(target=httpd.serve_forever,daemon=True).start()
        errors=[]
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch();page=browser.new_page(viewport={'width':412,'height':915})
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(f'http://127.0.0.1:{httpd.server_port}');page.wait_for_function('configData!==null')
                page.evaluate('(id)=>loadGame(id)',g.id)
                assert page.evaluate('game.player.body_training===100 && game.doctrines.immortal_body.level===1')
                assert page.locator('#immortal-market-content .doctrine-book').count()==5
                assert page.locator('#daomen-content .doctrine-book').count()==0
                assert page.locator('[data-panel-target=voisinage]').is_hidden()
                page.evaluate("UtilityPanels.open('map')")
                age=page.evaluate('game.player.age');old=page.evaluate('game.player.location_id')
                page.locator('.teleport-controls button').nth(1).click()
                page.wait_for_function('(old)=>game.player.location_id!==old',arg=old)
                assert page.evaluate('game.player.age')==age
                page.screenshot(path=str(ROOT/'build/teleport-1470-mobile.png'))
                g=e.store.load(g.id);g.player.world='spirit';g.player.realm_index=8;g.player.location_id=e.maps.default_location('spirit')
                g.player.immortal_power_converted=False;g.player.immortal_conversion_stage=0;g.player.sealed_cultivation=None
                g.player.hp=max_hp(g.player);g.player.mp=max_mp(g.player)
                book=grant(g,next(iter(catalog(g))),4);e.store.save(g)
                page.evaluate('(id)=>loadGame(id)',g.id)
                assert page.locator('[data-panel-target=spirit-voisinage]').is_visible()
                assert page.locator('[data-panel-target=voisinage]').is_hidden()
                page.evaluate("UtilityPanels.close('map');UtilityPanels.open('immortal-aperture')")
                page.get_by_role('button',name='凝练仿仙灵力',exact=True).click()
                page.wait_for_function('game.aperture.current===20')
                for theme in 'abcdef':
                    page.evaluate('(t)=>document.querySelector(`[data-theme-picker=dialog] [data-theme-choice=${t}]`).click()',theme)
                    page.evaluate('GameThemes.saved')
                    page.evaluate("UtilityPanels.close('immortal-aperture');UtilityPanels.open('spirit-voisinage')")
                    title = page.locator('#spirit-voisinage-content h3').text_content()
                    assert '灵域' in title, (theme,title,page.evaluate('game.aperture.field'))
                    assert page.locator('#spirit-voisinage-card').evaluate('(e)=>e.scrollWidth<=e.clientWidth+1')
                page.screenshot(path=str(ROOT/'build/spirit-voisinage-1470-mobile.png'))
                g=e._load(g.id);e._ensure_merchant(g);alliance=g.merchant_state['worlds']['spirit'][0]
                g.player.location_id=alliance['hq'];e.store.save(g)
                e.merchant_action(g.id,'join',{'alliance_id':alliance['id']})
                page.evaluate('(id)=>loadGame(id)',g.id);page.evaluate("UtilityPanels.close('spirit-voisinage');UtilityPanels.open('merchant')")
                form=page.locator('.merchant-post').first;form.locator('..').evaluate('(e)=>e.open=true')
                form.get_by_label('委托类型',exact=True).select_option('spirit_manual')
                assert form.get_by_label('所需材料或道具',exact=True).locator('option').count()==25
                colours=[]
                for realm in (9,10,11,12):
                    g=e.store.load(g.id);g.player.world='celestial';g.player.realm_index=realm
                    g.player.location_id=e.maps.default_location('celestial');g.player.immortal_veins[str(realm)]=1;e.store.save(g)
                    page.evaluate('(id)=>loadGame(id)',g.id);page.evaluate("UtilityPanels.close('merchant');UtilityPanels.open('immortal-veins')")
                    colours.append(page.locator('.meridian-figure svg').evaluate('(e)=>getComputedStyle(e).color'))
                    assert page.locator('.meridian-node.opened').count()==1
                assert len(set(colours))==4,colours
                assert not errors,errors
                browser.close()
        finally:httpd.shutdown()
    print('v1.47 UI passed: seeded quick-start, market/daomen separation, instant teleport, six-theme spirit domain and merchant manual commission')

if __name__=='__main__':main()
