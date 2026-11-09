"""Real base/DLC buttons, stale submissions, escrow reload and two responsive palettes."""
import sys,tempfile,threading,runpy
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from scripts.browser_navigation import navigation_locator,click_control,set_theme
from scripts.westward_navigation import open_westward

def main():
    fixture=runpy.run_path(str(ROOT/'tests/fixtures/westward_release.py'))
    out=ROOT/'build/institution-development-browser';out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='institution-ui-') as folder:
        e=GameEngine(ROOT,Path(folder)/'saves')
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',e),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            http=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=http.serve_forever,daemon=True).start();base=f'http://127.0.0.1:{http.server_port}'
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    for theme,width,height in [('light',1440,1000),('dark',390,844),('light',754,365)]:
                        g=e.create_game('机构经营验收','supreme_metal','dao',370,preset_id='core');fixture['prepare_institution'](e,g['id'])
                        page=browser.new_page(viewport=dict(width=width,height=height),reduced_motion='reduce');errors=[];page.on('pageerror',lambda x:errors.append(str(x)))
                        page.goto(base);page.wait_for_function('!!configData');page.evaluate('id=>loadGame(id)',g['id']);set_theme(page,theme)
                        navigation_locator(page,'[data-panel-target=faction]').click()
                        section=page.locator('[data-institution-scope]').first;click_control(section.locator('summary').first)
                        assert section.locator('[data-institution-action=institution_configure]').get_attribute('data-dlc') is None
                        def click(selector,endpoint,status=200):
                            with page.expect_response(lambda r:r.url.endswith(endpoint)) as r:click_control(page.locator(selector).first)
                            assert r.value.status==status,r.value.text();page.wait_for_function('!busy')
                        click('[data-institution-action=institution_start]','/fleet-action')
                        assert page.evaluate('game.fleet_network.institutions.some(r=>r.job?.funded>0)')
                        section=page.locator('[data-institution-scope]').first
                        if not section.evaluate('n=>n.open'):click_control(section.locator('summary').first)
                        page.screenshot(path=str(out/f'{theme}-{width}-base.png'),animations='disabled')
                        click('[data-institution-action=institution_cancel]','/fleet-action')
                        assert page.evaluate('game.fleet_network.institutions.some(r=>r.history.at(-1)?.refunded>0)')
                        h=e.create_game('长期契约验收','supreme_metal','dao',371,preset_id='true_immortal');fixture['prepare_westward'](e,h['id'])
                        page.evaluate('id=>loadGame(id)',h['id']);open_westward(page,'仙圃')
                        click('[data-gather-action=garden_lease]','/yaochi-action');click('[data-gather-action=garden_fund]','/yaochi-action');click('[data-gather-action=garden_configure]','/yaochi-action')
                        click('[data-contract-action=contract_open]','/yaochi-action')
                        assert page.locator('[data-contract-action=contract_deliver]').is_disabled()
                        active=page.evaluate('game.yaochi.contracts.active');assert active['funded']>0
                        page.evaluate('id=>loadGame(id)',h['id']);open_westward(page,'仙圃');assert page.evaluate('game.yaochi.contracts.active.id')==active['id']
                        assert page.locator('.utility-panel.panel-open').evaluate('n=>n.scrollWidth<=n.clientWidth+2')
                        page.screenshot(path=str(out/f'{theme}-{width}-contract.png'),animations='disabled')
                        payload=page.evaluate("({action:'contract_cancel',target_id:game.yaochi.contracts.token+'|'})")
                        assert page.request.post(base+f"/api/games/{h['id']}/yaochi-action",data=payload).status==200
                        click('[data-contract-action=contract_cancel]','/yaochi-action',400)
                        assert page.evaluate('!game.yaochi.contracts.active')
                        assert not errors,errors;page.close();print(f'{theme} {width}: base original escrow and real DLC contract/reload/stale recovery passed',flush=True)
                    browser.close()
            finally:http.shutdown();http.server_close()
if __name__=='__main__':main()
