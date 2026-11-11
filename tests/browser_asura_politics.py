"""Real provincial petitions, accountable votes, stale pages and original events."""
import sys,tempfile,threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.system.asura_court import change_rank
from cultivation_life.system import institution_authority as authority
from cultivation_life.system.asura_governorship import rules,management
from cultivation_life.system.economy.ledger import balance
from test_asura_politics import prepare
from scripts.browser_navigation import click_control,navigation_locator,set_theme


def make(engine,build=True):
    made=engine.create_game('地方议事验收','supreme_metal','demonic',373,preset_id='asura_upper')
    engine.upper_institution_action(made['id'],'join');g=engine._load(made['id']);g.pending_event=None
    change_rank(g,g.upper_institutions['asura'],1)
    g.upper_institutions['asura'].update(earned=100,regard=60,treasury=10**12)
    engine.store.save(g)
    return prepare(engine,g,build=build)


def main():
    output=ROOT/'build/asura-politics-browser';output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='asura-politics-ui-') as folder:
        e=GameEngine(ROOT,Path(folder)/'saves')
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',e),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            http=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
            base=f'http://127.0.0.1:{http.server_port}'
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    for theme,width,height in [('light',1440,1000),('dark',1440,1000),('light',390,844),('dark',390,844),('dark',754,365)]:
                        g,row,_=make(e);page=browser.new_page(viewport=dict(width=width,height=height),reduced_motion='reduce')
                        errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                        page.goto(base);page.wait_for_function('!!configData');page.evaluate('id=>loadGame(id)',g.id);set_theme(page,theme)
                        def open_office(scope):
                            if page.locator('#building-affairs-card').is_visible():
                                if page.locator(f'#building-affairs-content [data-governor-office="{scope["id"]}"]').count():return
                                page.locator('#building-affairs-toggle').click()
                            target=page.locator(f'#pixel-buildings [data-building-affairs="{scope["building_id"]}"]')
                            if not target.count():target=page.locator(f'#pixel-buildings [data-building-affairs="{scope["city_id"]}"]')
                            if not target.is_visible():page.locator('#pixel-scenery-toggle').click()
                            click_control(target)
                        def panel(kind=None):
                            root=page.locator('#building-affairs-content .governor-disputes')
                            if not root.evaluate('n=>n.open'):click_control(root.locator('summary').first)
                            if not kind:return root
                            item=root.locator(f'[data-case-kind="{kind}"]')
                            if not item.evaluate('n=>n.open'):click_control(item.locator('summary').first)
                            return item
                        def click(operation,kind=None,choice=None,status=200):
                            host=panel(kind)
                            if choice:host.get_by_label('裁决方案').select_option(choice)
                            with page.expect_response(lambda r:r.url.endswith('/upper-institution')) as response:
                                click_control(host.locator(f'[data-petition-operation="{operation}"]').first)
                            assert response.value.status==status,response.value.text();page.wait_for_function('!busy')
                        open_office(row);click('observe')
                        assert panel().locator('[data-case-kind]').count()>=3
                        before=e.store.load(g.id);cash=balance(before,row['wallet']);treasury=balance(before,rules.SOURCE)
                        click('endorse','remittance','pay')
                        assert panel('remittance').locator('[data-petition-operation=endorse]').is_disabled()
                        panel('remittance').scroll_into_view_if_needed()
                        page.screenshot(path=str(output/f'{theme}-{width}-dispute.png'),animations='disabled')
                        assert page.locator('#building-affairs-card').evaluate('n=>n.scrollWidth<=n.clientWidth+2')
                        assert panel('remittance').locator('[data-petition-operation=resolve]').get_attribute('data-dlc')=='asura'
                        click('resolve','remittance','pay')
                        loaded=e.store.load(g.id);delta=cash-balance(loaded,row['wallet'])
                        assert delta>0 and balance(loaded,rules.SOURCE)==treasury+delta
                        click('resolve','personnel','appoint');assert rules.offices(e.store.load(g.id))[0]['people']
                        click('resolve','access','restrict')
                        assert not rules.building(e.store.load(g.id),row)['public']
                        page.locator('#building-affairs-toggle').click()
                        entrance=page.locator('#pixel-buildings').get_by_role('button',name=row['name'],exact=True)
                        if not entrance.is_visible():page.locator('#pixel-scenery-toggle').click()
                        with page.expect_response(lambda r:r.url.endswith('/building-action')) as response:click_control(entrance)
                        assert response.value.status==200
                        page.wait_for_function('!busy&&game.buildings.inside')
                        index=page.evaluate("game.pending_event.choices.findIndex(c=>c.id==='leave')")
                        page.locator('#event-choices button').nth(index).click();page.wait_for_function('!busy&&!game.buildings.inside')
                        open_office(row)
                        loaded=e.store.load(g.id);authority.revoke(loaded,rules.offices(loaded)[0]);e.store.save(loaded)
                        click('observe',status=400)
                        assert panel().locator('[data-petition-operation=observe]').is_disabled()
                        assert page.locator('#pixel-buildings').get_by_role('button',name=row['name'],exact=True,include_hidden=True).is_disabled()
                        # A separate original charter tests a submitted budget and actual NPC ruling.
                        h,scope,_=make(e,build=False);page.evaluate('id=>loadGame(id)',h.id);open_office(scope)
                        click('observe');click('resolve','budget','submit')
                        assert not panel('budget').locator('[data-petition-operation=resolve]').count()
                        click('endorse','budget','approve')
                        loaded=e.store.load(h.id);original=balance(loaded,rules.SOURCE)
                        loaded.player.age+=1;management.advance(loaded,e.maps);e.store.save(loaded)
                        assert balance(loaded,scope['wallet'])>0 and balance(loaded,rules.SOURCE)<original
                        page.evaluate('id=>loadGame(id)',h.id);open_office(scope)
                        assert not panel().locator('[data-case-kind=budget]').count()
                        # Inspect the existing politics tab, without adding navigation controls.
                        loaded=e.store.load(h.id);loaded.player.location_id='ten_thousand_battle_city';e.store.save(loaded)
                        page.evaluate('id=>loadGame(id)',h.id)
                        navigation_locator(page,'[data-panel-target=upper-institution]').click()
                        click_control(page.locator('#upper-institution-content').get_by_role('button',name='政令',exact=True))
                        assert page.locator('#upper-institution-content').get_by_text('族 · 血裔诸族',exact=True).count()==1
                        assert not errors,errors
                        page.close();print(f'{theme} {width}: original funds, endorsement, personnel, private office event, stale revocation and NPC approval passed',flush=True)
                    browser.close()
            finally:http.shutdown();http.server_close()


if __name__=='__main__':main()
