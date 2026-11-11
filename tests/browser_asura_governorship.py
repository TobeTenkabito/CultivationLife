"""Real court/building buttons, stale requests, events and responsive palettes."""
import sys,tempfile,threading,json
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.system.asura_court import change_rank
from cultivation_life.system.asura_governorship import rules
from cultivation_life.system import institution_authority as authority
from cultivation_life.system.economy.state import ensure_regional_market
from cultivation_life.system.economy.ledger import balance
from scripts.browser_navigation import navigation_locator,click_control,set_theme


def main():
    out=ROOT/'build/asura-governorship-browser';out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='asura-province-') as folder:
        e=GameEngine(ROOT,Path(folder)/'saves')
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',e),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            threading.Thread(target=http.serve_forever,daemon=True).start();base=f'http://127.0.0.1:{http.server_port}'
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    for theme,width,height in [('light',1440,1000),('dark',1440,1000),('light',390,844),('dark',390,844),('dark',754,365)]:
                        g=e._load(e.create_game('地方任职验收','supreme_metal','demonic',371,preset_id='asura_upper')['id'])
                        e.upper_institution_action(g.id,'join');g=e._load(g.id)
                        g.pending_event=None;state=g.upper_institutions['asura'];change_rank(g,state,1)
                        state.update(earned=100,regard=60,treasury=10**12);e.store.save(g)
                        page=browser.new_page(viewport=dict(width=width,height=height),reduced_motion='reduce');errors=[]
                        page.on('pageerror',lambda error:errors.append(str(error)))
                        page.goto(base);page.wait_for_function('!!configData');page.evaluate('async id=>loadGame(id)',g.id);set_theme(page,theme)
                        navigation_locator(page,'[data-panel-target=upper-institution]').click()
                        click_control(page.locator('#upper-institution-content').get_by_role('button',name='内政',exact=True))
                        panel=page.locator('#upper-institution-content .asura-governorship')
                        click_control(panel.locator('.governor-section summary').first)
                        def click(action,status=200):
                            target=page.locator(f'.utility-panel.panel-open [data-governor-action="{action}"]').first
                            with page.expect_response(lambda r:r.url.endswith('/upper-institution')) as response:click_control(target)
                            assert response.value.status==status,response.value.text();page.wait_for_function('!busy')
                        click('request')
                        loaded=e.store.load(g.id);row=rules.offices(loaded)[0]
                        assert loaded.player.location_id=='ten_thousand_battle_city' and balance(loaded,row['wallet'])==0
                        # Arrival fixture only; appointment above demonstrably does not teleport.
                        loaded.player.location_id=row['location'];loaded.pending_event=None
                        ensure_regional_market(loaded,e.maps,'asura',row['location'])
                        authority.fund(loaded,row,rules.SOURCE,10**11);e.store.save(loaded)
                        page.evaluate('async id=>loadGame(id)',g.id)
                        if page.locator('#upper-institution-card').is_visible():page.locator('#upper-institution-toggle').click()
                        button=page.locator(f'#pixel-buildings [data-building-affairs="{row["city_id"]}"]')
                        if not button.is_visible():page.locator('#pixel-scenery-toggle').click()
                        click_control(button)
                        click('assume')
                        affairs=page.locator('#building-affairs-content')
                        click_control(affairs.get_by_text('公款与府署',exact=True))
                        before=e.store.load(g.id);cash=balance(before,row['wallet'])
                        click('build')
                        loaded=e.store.load(g.id);row=rules.offices(loaded)[0]
                        assert loaded.building_state['records'][row['building_id']]['owner']['kind']=='sect'
                        assert balance(loaded,row['wallet'])<cash
                        assert page.locator('#pixel-buildings [data-building-affairs^="office:"]').count()==1
                        click_control(affairs.get_by_text('公款与府署',exact=True))
                        assert affairs.locator('[data-governor-action=donate]').get_attribute('data-dlc')=='asura'
                        assert page.locator('#building-affairs-card').evaluate('n=>n.scrollWidth<=n.clientWidth+2')
                        page.screenshot(path=str(out/f'{theme}-{width}-office.png'),animations='disabled')
                        # Another request revokes authority while the original page remains open.
                        loaded=e.store.load(g.id);authority.revoke(loaded,rules.offices(loaded)[0]);e.store.save(loaded)
                        click('donate',400)
                        assert page.evaluate('game.upper_institution.court.governorship.offices[0].status')=='handover'
                        assert not affairs.locator('[data-governor-action=donate]').count()
                        click_control(affairs.get_by_text('任职交接',exact=True));click('return')
                        click_control(affairs.get_by_text('任职交接',exact=True));click('resign')
                        assert e.store.load(g.id).economy_v2['administrations'][row['id']]['status']=='vacant'
                        page.locator('#building-affairs-toggle').click()
                        # Enter the real building event, then leave through its actual choice.
                        entrance=page.locator('#pixel-buildings').get_by_role('button',name=row['name'],exact=True)
                        if not entrance.is_visible():page.locator('#pixel-scenery-toggle').click()
                        with page.expect_response(lambda r:r.url.endswith('/building-action')) as response:click_control(entrance)
                        assert response.value.status==200
                        page.wait_for_function('!busy&&game.buildings.inside')
                        index=page.evaluate("game.pending_event.choices.findIndex(c=>c.id==='leave')")
                        page.locator('#event-choices button').nth(index).click();page.wait_for_function('!busy&&!game.buildings.inside')
                        assert not errors,errors
                        page.close();print(f'{theme} {width}: appointment, original building, escrow, stale revocation, handover and real building event passed',flush=True)
                    browser.close()
            finally:http.shutdown();http.server_close()


if __name__=='__main__':main()
