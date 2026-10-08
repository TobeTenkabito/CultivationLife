"""Four-theme real peace, governance, stale recovery and responsive layouts."""
import json
import sys
import tempfile
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.system.economy.ledger import transfer_value
from cultivation_life.system.economy.market_power import record_trade
from cultivation_life.system.faction_geography import faction_site
from test_economy_governance import war_fixture


def main():
    output=ROOT/'build/economy-governance-browser';output.mkdir(parents=True,exist_ok=True)
    checks=[]
    with tempfile.TemporaryDirectory() as directory:
        engine=GameEngine(ROOT,Path(directory)/'saves')
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',Path(directory)):
            httpd=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            threading.Thread(target=httpd.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    for theme in 'abdf':
                        for width,height in [(1440,1000),(393,852),(852,393)]:
                            game=engine._load(engine.create_game('市井风云','supreme_metal','dao',419,preset_id='core')['id'])
                            game.pending_event=None;game.player.next_tribulation_age=None
                            transfer_value(game,'background:human','player',10**7,'验收资金')
                            war_fixture(engine,game)
                            game.player.location_id=faction_site(game.sects['wanmo'])['id'];engine.store.save(game)
                            page=browser.new_page(viewport=dict(width=width,height=height));errors=[]
                            page.on('pageerror',lambda error:errors.append(str(error)))
                            page.goto(f'http://127.0.0.1:{httpd.server_port}');page.wait_for_function('configData && window.GameThemes')
                            page.locator(f'[data-theme-picker=start] [data-theme-choice={theme}]').click()
                            page.evaluate('async id=>loadGame(id)',game.id)
                            if 'panel-open' not in page.locator('#war-card').get_attribute('class'):page.locator('[data-panel-target=war]').click()
                            active=page.locator('.war-card').first
                            if active.get_attribute('open') is None:active.locator(':scope > summary').click()
                            form=page.locator('.war-peace-form');form.locator('select').first.select_option('economic_rights')
                            form.get_by_role('button',name='以战果提出条件',exact=True).click()
                            page.wait_for_function("!busy && game.war_system.wars.some(w=>w.economic_transfers?.length)")
                            card=page.locator('.war-card').first
                            if card.get_attribute('open') is None:card.locator(':scope > summary').click()
                            assert page.locator('.war-economic-receipt').is_visible()
                            page.locator('[data-panel-target=map]').click();page.get_by_role('button',name='本地市场',exact=True).click()
                            box=page.locator('#market-governance')
                            def expand():
                                if box.get_attribute('open') is None:box.locator(':scope > summary').click()
                            expand();page.get_by_label('市税经营方针').select_option('reinvest')
                            page.locator('[data-governance=market_policy]').click()
                            page.wait_for_function("!busy && game.map.economy.competition.control.policy==='reinvest'")
                            expand();page.get_by_label('竞争基金投入').fill('1000')
                            g=engine._load(game.id);market=g.economy_v2['markets'][f'{g.player.world}:{g.player.location_id}']
                            engine.fleet_action(g.id,dict(action='market_relief',market_id=market['id'],revision=market['revision'],amount=1))
                            before=engine.store._path(g.id).read_bytes()
                            page.locator('[data-governance=market_relief]').click()
                            page.wait_for_function('!busy && game.map.economy.revision>'+str(market['revision']))
                            assert engine.store._path(g.id).read_bytes()==before
                            expand();page.locator('[data-governance=market_relief]').click();page.wait_for_function('!busy')
                            g=engine._load(game.id);market=g.economy_v2['markets'][f'{g.player.world}:{g.player.location_id}']
                            item=next(iter(market['commodities']));market['commodities'][item]['stock']=0
                            record_trade(g,market,item,'player','buy',100000);market['competition'][item]['pressure']=16;engine.store.save(g)
                            engine.advance(g.id,'rest',1)
                            g=engine._load(g.id);g.pending_event=None;engine.store.save(g)
                            page.evaluate('async id=>loadGame(id)',g.id);expand()
                            assert page.locator('.competition-card').count()>0
                            assert page.evaluate('game.map.economy.competition.rows.some(r=>r.added>0)')
                            page.locator('.competition-card').first.scroll_into_view_if_needed()
                            page.screenshot(path=str(output/f'{theme}-{width}-competition.png'))
                            assert page.locator('#map-card').evaluate('(n)=>n.scrollWidth<=n.clientWidth+2')
                            snapshot=engine.store._path(g.id).read_bytes();page.evaluate('async id=>loadGame(id)',g.id)
                            assert engine.store._path(g.id).read_bytes()==snapshot and not errors,errors
                            checks.append(dict(theme=theme,width=width,status='passed'));page.close()
                    browser.close()
            finally:httpd.shutdown();httpd.server_close()
    (output/'report.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
    print('Governance browser passed: 12 layouts, real peace, fiscal policy, relief, stale recovery, competition and reload')


if __name__=='__main__':main()
