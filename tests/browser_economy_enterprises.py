"""Actual page actions for deeds, production, stale recovery and standing freight."""
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


def main():
    output=ROOT/'build/economy-expansion-step2-browser';output.mkdir(parents=True,exist_ok=True)
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
                        for width,height in [(1440,1000),(393,852)]:
                            game=engine._load(engine.create_game('实业商路','supreme_metal','dao',419,preset_id='core')['id'])
                            game.pending_event=None;game.player.realm_index=2;game.player.next_tribulation_age=None
                            transfer_value(game,'background:human','player',10**8,'验收资金');engine.store.save(game)
                            page=browser.new_page(viewport=dict(width=width,height=height));errors=[]
                            page.on('pageerror',lambda error:errors.append(str(error)))
                            page.goto(f'http://127.0.0.1:{httpd.server_port}');page.wait_for_function('configData && window.GameThemes')
                            page.locator(f'[data-theme-picker=start] [data-theme-choice={theme}]').click()
                            page.evaluate('async id=>loadGame(id)',game.id);page.locator('[data-panel-target=map]').click()
                            page.get_by_role('button',name='本地市场',exact=True).click()
                            def expand(locator):
                                if locator.get_attribute('open') is None:locator.locator(':scope > summary').click()
                            box=page.locator('#enterprise-panel');expand(box)
                            page.get_by_label('购置产业',exact=True).select_option('mine')
                            page.locator('[data-estate-action=buy]').click()
                            page.wait_for_function('!busy && game.map.economy.enterprises.owned.length===1')
                            key=page.evaluate('game.map.economy.enterprises.owned[0].id')
                            card=page.locator(f'[data-estate-id="{key}"]')
                            def opened():expand(box);expand(card)
                            opened();page.get_by_label('产业资金金额').fill('10000');card.locator('[data-estate-action=fund]').click()
                            page.wait_for_function('!busy && game.map.economy.enterprises.owned[0].cash===10000')
                            # A second page writes first. Stale native buttons cannot charge again.
                            opened();saved=engine._load(game.id);row=saved.economy_v2['estates'][key]
                            engine.fleet_action(game.id,dict(action='estate_fund',estate_id=key,revision=row['revision'],amount=1))
                            before=engine.store._path(game.id).read_bytes()
                            card.locator('[data-estate-action=fund]').click()
                            page.wait_for_function('!busy && game.map.economy.enterprises.owned[0].cash===10001')
                            assert engine.store._path(game.id).read_bytes()==before
                            opened();card.locator('[data-estate-action=start]').click()
                            page.wait_for_function('!busy && !!game.map.economy.enterprises.owned[0].job')
                            opened();assert card.locator('[data-estate-action=start]').is_disabled()
                            card.scroll_into_view_if_needed();page.screenshot(path=str(output/f'{theme}-{width}-estate.png'))
                            engine.advance(game.id,'rest',2)
                            page.evaluate('async id=>loadGame(id)',game.id)
                            assert page.evaluate('game.map.economy.enterprises.owned[0].produced')==4
                            if page.evaluate('!!game.pending_event'):
                                g=engine._load(game.id);g.pending_event=None;engine.store.save(g);page.evaluate('async id=>loadGame(id)',game.id)
                            page.locator('[data-panel-target=merchant]').click()
                            management=page.locator('#fleet-network-content > details').nth(0);expand(management)
                            management.get_by_role('button',name='自建独立商队',exact=True).click()
                            page.wait_for_function('!busy && game.fleet_network.fleets.some(f=>f.player_controlled)')
                            orders=page.locator('#trade-orders-panel');expand(orders);form=orders.locator('[data-order-fleet]').first;expand(form)
                            form.get_by_label('订单执行方式').select_option('repeat');form.get_by_label('订单商品').select_option('dew_grass_seed')
                            form.locator('[data-fleet-action=order_configure]').click()
                            page.wait_for_function("!busy && game.fleet_network.fleets.some(f=>f.trade_order?.mode==='repeat')")
                            expand(orders);expand(form);form.locator('[data-fleet-action=order_dispatch]').click()
                            page.wait_for_function("!busy && game.fleet_network.fleets.some(f=>f.player_controlled && f.status==='travelling')")
                            expand(orders);expand(form);assert form.locator('[data-fleet-action=order_dispatch]').is_disabled()
                            form.get_by_label('订单执行方式').select_option('hold');form.locator('[data-fleet-action=order_configure]').click()
                            page.wait_for_function("!busy && game.fleet_network.fleets.some(f=>f.trade_order?.mode==='hold' && f.status==='travelling')")
                            expand(orders);expand(form);form.scroll_into_view_if_needed()
                            page.screenshot(path=str(output/f'{theme}-{width}-orders.png'))
                            page.wait_for_function('document.documentElement.scrollWidth<=innerWidth+2')
                            assert page.locator('#merchant-card').evaluate('(n)=>n.scrollWidth<=n.clientWidth+2')
                            before=engine.store._path(game.id).read_bytes();page.evaluate('async id=>loadGame(id)',game.id)
                            assert engine.store._path(game.id).read_bytes()==before and not errors,errors
                            checks.append(dict(theme=theme,width=width,status='passed'));page.close()
                    browser.close()
            finally:httpd.shutdown();httpd.server_close()
    (output/'report.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
    print('Enterprise browser passed: 8 layouts, deeds, production, stale recovery, standing dispatch and reload')


if __name__=='__main__':main()
