"""Actual six-theme controls, lower-world MP transitions and manual plans."""
import sys, tempfile, threading
from pathlib import Path
from http.server import ThreadingHTTPServer
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine

class Quiet(server.Handler):
    def log_message(self,*args):pass

def main():
    with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
        server.PERSISTENCE_ROOT=Path(folder)
        e=server.ENGINE=GameEngine(ROOT,Path(folder)/'saves')
        made=e.create_game('邻域小版验收','supreme_metal','dao',seed=1471,preset_id='true_immortal')
        g=e.store.load(made['id']);g.pending_event=None;g.heavenly_court['open_election']=None;e.store.save(g)
        httpd=ThreadingHTTPServer(('127.0.0.1',0),Quiet);threading.Thread(target=httpd.serve_forever,daemon=True).start()
        errors=[]
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch();page=browser.new_page(viewport={'width':412,'height':915})
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(f'http://127.0.0.1:{httpd.server_port}');page.wait_for_function('configData!==null')
                for theme in 'abcdef':
                    g=e.store.load(g.id);g.player.world='celestial';g.player.realm_index=9;g.player.layer=4
                    g.player.location_id=e.maps.default_location('celestial');g.player.combat_plan['manual']=False;e.store.save(g)
                    page.evaluate('(id)=>loadGame(id)',g.id)
                    page.evaluate('(t)=>document.querySelector(`[data-theme-picker=dialog] [data-theme-choice=${t}]`).click()',theme)
                    page.evaluate('GameThemes.saved')
                    assert page.locator('[data-panel-target=combat-plan]').is_hidden()
                    assert page.evaluate('game.aperture.capacity===2000 && game.aperture.current===300')
                    assert page.locator('#hud-mp .hud-values strong').text_content().endswith('%')
                    page.evaluate("UtilityPanels.open('settings')")
                    page.locator('#setting-manual-combat-plan').select_option('manual')
                    page.wait_for_function('!busy && game.combat_plan.manual')
                    page.locator('[data-panel-target=combat-plan]').click()
                    page.get_by_label('邻域姿态',exact=True).select_option('guard')
                    page.get_by_label('每轮追加仙力',exact=True).fill('37')
                    page.get_by_label('高消耗术式',exact=True).select_option('never')
                    page.get_by_role('button',name='保存战斗预案',exact=True).click()
                    page.wait_for_function('!busy && game.combat_plan.investment===37 && game.combat_plan.stance==="guard"')
                    for width in (412,1440):
                        page.set_viewport_size({'width':width,'height':915})
                        assert page.locator('#combat-plan-card').evaluate('(e)=>e.scrollWidth<=e.clientWidth+1')
                        page.screenshot(path=str(ROOT/f'build/combat-plan-{theme}-{width}-1471.png'))
                    page.set_viewport_size({'width':412,'height':915})
                    page.evaluate("UtilityPanels.open('map')")
                    assert page.locator('[aria-label="传送目的地"]').count()==0
                    age=page.evaluate('game.player.age');location=page.evaluate('game.player.location_id')
                    page.locator('.teleport-methods button').filter(has_text='暗杀').click()
                    assert page.locator('[aria-label="传送目的地"]').count()==1
                    assert page.locator('.teleport-controls').evaluate('(e)=>e.scrollWidth<=e.clientWidth+1')
                    page.screenshot(path=str(ROOT/f'build/teleport-{theme}-1471.png'))
                    page.get_by_role('button',name='确认传送',exact=True).click()
                    page.wait_for_function('(old)=>!busy && game.player.location_id!==old',arg=location)
                    assert page.evaluate('game.player.age')==age
                    g=e.store.load(g.id);g.player.world='spirit';g.player.location_id=e.maps.default_location('spirit')
                    g.player.sealed_cultivation={'realm_index':9,'layer':4};g.player.realm_index=8;e.store.save(g)
                    page.evaluate('(id)=>loadGame(id)',g.id)
                    assert page.evaluate("game.player.resource_kind==='mana' && !document.querySelector('#player-hud').classList.contains('immortal-resource')")
                    assert not page.locator('#hud-mp .hud-values strong').text_content().endswith('%')
                    assert page.locator('#mp-meter').evaluate("e=>e.classList.contains('blue') && !e.classList.contains('purple')")
                    assert page.locator('#mp-label').text_content()=='MP'
                    g=e.store.load(g.id);g.player.world='celestial';g.player.location_id=e.maps.default_location('celestial')
                    g.player.realm_index=9;g.player.layer=4;g.player.sealed_cultivation=None;e.store.save(g)
                    page.evaluate('(id)=>loadGame(id)',g.id)
                    assert page.locator('#hud-mp .hud-values strong').text_content().endswith('%')
                    assert page.locator('#mp-meter').evaluate("e=>e.classList.contains('purple') && !e.classList.contains('blue')")
                    page.evaluate("UtilityPanels.open('settings')")
                    page.locator('#setting-manual-combat-plan').select_option('auto')
                    page.wait_for_function('!busy && !game.combat_plan.manual')
                    assert page.locator('[data-panel-target=combat-plan]').is_hidden()
                    assert e.store.load(g.id).player.combat_plan['investment']==37
                assert not errors,errors
                browser.close()
        finally:httpd.shutdown()
    print('v1.47.1 six-theme UI passed: lower MP / return conversion, phase capacity, saved manual plans, method-first teleport and real assassination transit')

if __name__=='__main__':main()
