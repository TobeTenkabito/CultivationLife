"""Actual HTTP/click acceptance for the original office military fold."""
import sys,tempfile,threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.system.asura_governorship import rules,military as m,politics
from cultivation_life.system import institution_garrisons as troops,institution_authority as authority
from cultivation_life.system.economy.ledger import balance
from browser_asura_politics import make
from scripts.browser_navigation import click_control,set_theme


def main():
    output=ROOT/'build/asura-military-browser';output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='asura-military-ui-') as folder:
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
                        g,row,people=make(e);page=browser.new_page(viewport=dict(width=width,height=height),reduced_motion='reduce')
                        errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                        page.goto(base);page.wait_for_function('!!configData');page.evaluate('id=>loadGame(id)',g.id);set_theme(page,theme)
                        def open_office():
                            if not page.locator('#building-affairs-card').is_visible():
                                target=page.locator(f'#pixel-buildings [data-building-affairs="{row["building_id"]}"]')
                                if not target.is_visible():page.locator('#pixel-scenery-toggle').click()
                                click_control(target)
                            host=page.locator('#building-affairs-content .governor-military')
                            if not host.evaluate('n=>n.open'):click_control(host.locator('summary').first)
                            return host
                        def act(operation,status=200,**fields):
                            host=open_office();host.get_by_label('军政事务',exact=True).select_option(operation)
                            for key,value in fields.items():
                                target=host.get_by_label(key,exact=True)
                                if target.evaluate('n=>n.tagName')=='SELECT':target.select_option(value)
                                else:target.fill(value)
                            with page.expect_response(lambda r:r.url.endswith('/upper-institution')) as response:
                                click_control(host.locator('[data-governor-action=military]'))
                            assert response.value.status==status,response.value.text();page.wait_for_function('!busy')
                        before=e.store.load(g.id);cash=balance(before,row['wallet'])
                        act('enlist',**{'征募原人物':people[0].id})
                        act('provision',**{'营务军费金额':'100000000'})
                        loaded=e.store.load(g.id);scope=rules.offices(loaded)[0]
                        assert balance(loaded,scope['wallet'])==cash-100000000
                        assert len(troops.active(scope))==1
                        m.issue(loaded,scope,m.CAPITAL);e.store.save(loaded);page.evaluate('id=>loadGame(id)',g.id)
                        act('respond',**{'军令回应':'delay'})
                        act('respond',**{'军令回应':'refuse'})
                        host=open_office();host.scroll_into_view_if_needed()
                        page.screenshot(path=str(output/f'{theme}-{width}-military.png'),animations='disabled')
                        assert page.locator('#building-affairs-card').evaluate('n=>n.scrollWidth<=n.clientWidth+2')
                        assert host.locator('[data-governor-action=military]').get_attribute('data-dlc')=='asura'
                        act('respond',**{'军令回应':'comply'})
                        loaded=e.store.load(g.id);scope=rules.offices(loaded)[0]
                        assert not troops.stationed(loaded,scope,m.CAPITAL)
                        assert loaded.player.location_id==row['location']
                        loaded.player.age+=1;m.advance(loaded,e.maps,scope);e.store.save(loaded)
                        # Submit stale UI from the prior year; rejection must refresh and unlock.
                        act('recall',status=400)
                        act('recall')
                        loaded=e.store.load(g.id);scope=rules.offices(loaded)[0]
                        for _ in range(2):loaded.player.age+=1;m.advance(loaded,e.maps,scope)
                        e.store.save(loaded);page.evaluate('id=>loadGame(id)',g.id)
                        assert not troops.active(scope)
                        act('enlist',**{'征募原人物':people[0].id})
                        act('provision',**{'营务军费金额':'100000000'})
                        loaded=e.store.load(g.id);scope=rules.offices(loaded)[0]
                        politics.remember(loaded,people[0].id,'player',20,'原履约支持测试',scope['id']);e.store.save(loaded)
                        page.evaluate('id=>loadGame(id)',g.id);act('rebel')
                        loaded=e.store.load(g.id);scope=rules.offices(loaded)[0]
                        assert scope['status']=='handover' and m.fighting(scope) and m.king_id(loaded)!='player'
                        act('claim',status=400)
                        act('standdown')
                        assert m.conflict(rules.offices(e.store.load(g.id))[0])['status']=='withdrawn'
                        assert not errors,errors
                        page.close();print(f'{theme} {width}: enlist, real funds, delay/refusal, road dispatch, stale recovery, uprising and return passed',flush=True)
                    browser.close()
            finally:http.shutdown();http.server_close()


if __name__=='__main__':main()
