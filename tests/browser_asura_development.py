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
from scripts.browser_navigation import click_control,set_theme


def main():
    output=ROOT/'build/asura-development-browser';output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='asura-development-ui-') as folder:
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
                            root=page.locator('#building-affairs-content .governor-development')
                            if not root.evaluate('n=>n.open'):click_control(root.locator('summary').first)
                            return root
                        def click(operation,status=200):
                            root=panel();root.get_by_label('地方经营事项').select_option(operation)
                            with page.expect_response(lambda r:r.url.endswith('/upper-institution')) as response:
                                click_control(root.locator('[data-governor-action=development]'))
                            assert response.value.status==status,response.value.text()
                            page.wait_for_function('!busy')
                        before=balance(e.store.load(g.id),row['wallet'])
                        click('facility:supply')
                        assert balance(e.store.load(g.id),row['wallet'])<before
                        root=panel();root.get_by_label('地方经营事项').select_option('facility:supply')
                        assert root.locator('[data-governor-action=development]').is_disabled()
                        # Keep the loaded page, change the original public cash, then click.
                        loaded=e.store.load(g.id);authority.fund(loaded,rules.offices(loaded)[0],rules.SOURCE,1);e.store.save(loaded)
                        click('facility:training',400);click('facility:training')
                        loaded=e.store.load(g.id);scope=rules.offices(loaded)[0];m=operations.market(loaded,scope)
                        item=material_id('asura',9,'ore_structure');m['commodities'][item].update(stock=0,target=100)
                        loaded.economy_v2['accounts']['market:'+m['id']]['balance']=10**12
                        add_item(loaded.player,item,24);e.store.save(loaded)
                        page.evaluate('id=>loadGame(id)',g.id);click('supply:ore_structure')
                        root=panel();root.get_by_label('地方经营事项').select_option('deliver')
                        assert root.locator('[data-governor-action=development]').is_disabled()
                        loaded=e.store.load(g.id);scope=rules.offices(loaded)[0];c=operations.book(scope)['contract']
                        loaded.player.age=c['next'];e.store.save(loaded)
                        page.evaluate('id=>loadGame(id)',g.id);click('deliver')
                        loaded=e.store.load(g.id);c=operations.book(rules.offices(loaded)[0])['contract']
                        assert c['completed']==1 and balance(loaded,c['wallet'])==c['price']*2
                        root=panel();root.get_by_label('地方经营事项').select_option('deliver')
                        assert root.locator('[data-governor-action=development]').is_disabled()
                        assert root.locator('[data-governor-action=development]').get_attribute('data-dlc')=='asura'
                        assert page.locator('#building-affairs-card').evaluate('n=>n.scrollWidth<=n.clientWidth+2')
                        root.scroll_into_view_if_needed();page.screenshot(path=str(output/f'{theme}-{width}.png'),animations='disabled')
                        click('cancel');loaded=e.store.load(g.id)
                        assert operations.book(rules.offices(loaded)[0])['contract']['status']=='cancelled'
                        page.evaluate('id=>loadGame(id)',g.id)
                        # The original building event still loads, submits and releases busy.
                        if page.locator('#building-affairs-card').is_visible():page.locator('#building-affairs-toggle').click()
                        entrance=page.locator('#pixel-buildings').get_by_role('button',name=row['name'],exact=True)
                        if not entrance.is_visible():page.locator('#pixel-scenery-toggle').click()
                        with page.expect_response(lambda r:r.url.endswith('/building-action')) as response:click_control(entrance)
                        assert response.value.status==200;page.wait_for_function('!busy&&game.buildings.inside')
                        index=page.evaluate("game.pending_event.choices.findIndex(c=>c.id==='leave')")
                        page.locator('#event-choices button').nth(index).click()
                        page.wait_for_function('!busy&&!game.buildings.inside')
                        assert not errors,errors
                        print(f'{theme} {width}: paid facilities, stale recovery, real installments, refunds and event exit passed',flush=True)
                        page.close()
                    browser.close()
            finally:http.shutdown();http.server_close()


if __name__=='__main__':main()
