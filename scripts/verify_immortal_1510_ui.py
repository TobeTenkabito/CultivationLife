"""Live four-theme checks for merit economy, gold tempering and timed permits."""
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
from cultivation_life.rules import add_item


class Quiet(server.Handler):
    def log_message(self,*args): pass


def main():
    with tempfile.TemporaryDirectory(dir=ROOT/'build') as directory:
        server.PERSISTENCE_ROOT=Path(directory)
        e=server.ENGINE=GameEngine(ROOT,Path(directory)/'saves')
        created=e.create_game('功勋验收','supreme_metal','dao',seed=1510,preset_id='true_immortal')
        g=e.store.load(created['id']);g.pending_event=None;g.heavenly_court['open_election']=None
        g.player.immortal_body['level']=20;g.player.location_id='expanse_celestial_8'
        g.yaochi_state['merit']=100000;add_item(g.player,'spirit_stone',100000)
        e.store.save(g)
        httpd=ThreadingHTTPServer(('127.0.0.1',0),Quiet)
        threading.Thread(target=httpd.serve_forever,daemon=True).start()
        errors=[]
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch();page=browser.new_page()
                page.emulate_media(reduced_motion='reduce')
                page.on('pageerror',lambda err:errors.append(str(err)))
                page.goto(f'http://127.0.0.1:{httpd.server_port}');page.wait_for_function('configData!==null')
                page.evaluate('(id)=>loadGame(id)',g.id)
                assert page.locator('.left-dock [data-panel-target=golden-light]').count()==1
                assert page.locator('#strategy-dock [data-panel-target=yaochi]').count()==1
                assert page.locator('#immortal-market-content').is_hidden()
                for theme in 'abdf':
                    page.evaluate('(t)=>document.querySelector(`[data-theme-picker=dialog] [data-theme-choice=${t}]`).click()',theme)
                    page.evaluate('GameThemes.saved')
                    for width,height in [(1440,1080),(412,915),(915,412)]:
                        page.set_viewport_size({'width':width,'height':height})
                        for panel in ['yaochi','golden-light','immortal-veins']:
                            page.evaluate('(p)=>UtilityPanels.open(p)',panel)
                            assert page.locator(f'#{panel}-card').evaluate('e=>e.scrollWidth<=e.clientWidth+1'),(theme,width,panel)
                            if width==412:
                                page.screenshot(path=str(ROOT/f'build/immortal-1510-{panel}-{theme}.png'))
                page.evaluate("UtilityPanels.open('yaochi')")
                for count in range(8):
                    page.locator('[data-offer-id=great_sun_divine_light] button').click()
                    page.wait_for_function('(n)=>game.golden_light.recipe[0].owned===n',arg=count+1)
                page.evaluate("UtilityPanels.open('golden-light')")
                page.get_by_role('button',name='锤炼护体金光',exact=True).click()
                page.wait_for_function('game.golden_light.rank===2')
                page.evaluate("UtilityPanels.open('yaochi')")
                page.get_by_role('button',name='发布委托',exact=True).click()
                page.wait_for_function('game.yaochi.orders.length===1')
                page.get_by_role('button',name='兑换灵石',exact=True).click()
                page.wait_for_function('!busy')
                saved=e._load(g.id);saved.player.location_id='ascension_terrace';e.store.save(saved)
                page.evaluate('(id)=>loadGame(id)',g.id);page.evaluate("UtilityPanels.open('map')")
                assert page.locator('.teleport-route select').count()==0
                page.get_by_role('button',name='申请临时通行证',exact=False).click()
                page.wait_for_function("game.map.teleport.temporary.status==='pending'")
                page.locator('.teleport-methods button').filter(has_text='伪造').click()
                assert page.locator('.teleport-route select').count()==1
                saved=e._load(g.id);saved.player.age+=100;e.store.save(saved)
                page.evaluate('(id)=>loadGame(id)',g.id);page.evaluate("UtilityPanels.open('map')")
                page.get_by_role('button',name='持临时通行证',exact=True).click()
                page.get_by_role('button',name='确认传送',exact=True).click()
                page.wait_for_function("game.player.location_id!=='ascension_terrace'")
                assert not errors,errors
                browser.close()
        finally:httpd.shutdown()
    print('Immortal 1510 UI passed: four themes, desktop/portrait/landscape, actual merit trade, gold training and timed teleport')


if __name__=='__main__':main()
