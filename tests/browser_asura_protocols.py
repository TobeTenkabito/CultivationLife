"""Real office controls, paid construction, installments and stale page recovery."""
import sys,tempfile,threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.system.asura_governorship import rules
from cultivation_life.system import institution_operations as operations,institution_authority as authority
from cultivation_life.system.economy.ledger import balance
from cultivation_life.economy_content import material_id
from cultivation_life.rules import add_item
from browser_asura_politics import make
from test_asura_military import recruit,support
from scripts.browser_navigation import click_control,set_theme


def main():
    output=ROOT/'build/asura-protocols-browser';output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='asura-protocols-ui-') as folder:
        e=GameEngine(ROOT,Path(folder)/'saves')
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',e),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    for theme,width,height in [('light',1440,1000),('dark',1440,1000),('light',390,844),('dark',390,844),('dark',754,365)]:
                        g,row,_=make(e)
                        g,row,_=recruit(e,g,1);support(g,row)
                        for product in operations.market(g,row)['commodities'].values():product['stock']=10000
                        e.store.save(g)
                        page=browser.new_page(viewport=dict(width=width,height=height),reduced_motion='reduce')
                        errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                        page.goto(f'http://127.0.0.1:{http.server_port}');page.wait_for_function("typeof configData!=='undefined'&&!!configData")
                        page.evaluate('id=>loadGame(id)',g.id);set_theme(page,theme)
                        def panel():
                            if not page.locator('#building-affairs-card').is_visible():
                                target=page.locator(f'#pixel-buildings [data-building-affairs="{row["building_id"]}"]')
                                if not target.is_visible():page.locator('#pixel-scenery-toggle').click()
                                click_control(target)
                            root=page.locator('#building-affairs-content .governor-protocols')
                            if not root.evaluate('n=>n.open'):click_control(root.locator('summary').first)
                            return root
                        def click(operation,status=200):
                            root=panel();root.get_by_label('议政军权事项').select_option(operation)
                            with page.expect_response(lambda r:r.url.endswith('/upper-institution')) as response:
                                click_control(root.locator('[data-governor-action=protocol]'))
                            assert response.value.status==status,response.value.text()
                            page.wait_for_function('!busy')
                        before=balance(e.store.load(g.id),row['wallet'])
                        root=panel();root.get_by_label('议政实际金额').fill('3000');click('divert')
                        loaded=e.store.load(g.id);scope=rules.offices(loaded)[0]
                        assert balance(loaded,scope['wallet'])==before-3000
                        assert scope['protocols']['cases'][0]['amount']==3000
                        assert page.locator('#building-affairs-content .governor-military select[aria-label="军政事务"] option[value="rebel"]').count()==1
                        # Keep the page while original cash changes; first click rejects, next reload succeeds.
                        authority.fund(loaded,scope,rules.SOURCE,1);e.store.save(loaded)
                        root=panel();root.get_by_label('议政实际金额').fill('1000');click('restitute',400)
                        root=panel();root.get_by_label('议政实际金额').fill('1000');click('restitute')
                        assert e.store.load(g.id).economy_v2['administrations'][row['id']]['protocols']['cases'][0]['paid']==1000
                        root=panel();root.get_by_label('议政实际金额').fill('2000');click('restitute')
                        assert not e.store.load(g.id).economy_v2['administrations'][row['id']]['protocols']['cases']
                        root=panel();root.get_by_label('议政军权事项').select_option('restitute')
                        assert root.locator('[data-governor-action=protocol]').is_disabled()
                        assert root.locator('[data-governor-action=protocol]').get_attribute('data-dlc')=='asura'
                        assert page.locator('#building-affairs-card').evaluate('n=>n.scrollWidth<=n.clientWidth+2')
                        assert page.request.get(f'http://127.0.0.1:{http.server_port}/extension-assets/official.asura-manifestation/visual/buildings/governor-office.png').status==200
                        assert page.evaluate("(()=>{const r={subtype:'public_office',status:'intact',level:1,dependency:'official.asura-manifestation'};const real=HomeMapModes.art(r);const old=configData.extensions;try{configData.extensions=old.filter(e=>e.id!==r.dependency);return real.includes('governor-office.png')&&HomeMapModes.art(r).startsWith('/assets/pixel/')}finally{configData.extensions=old}})()")
                        root.scroll_into_view_if_needed();page.screenshot(path=str(output/f'{theme}-{width}.png'),animations='disabled')
                        assert not errors,errors
                        print(f'{theme} {width}: original evidence, partial recovery, stale UI, disabled closed case and DLC art passed',flush=True)
                        page.close()
                    browser.close()
            finally:http.shutdown();http.server_close()


if __name__=='__main__':main()
