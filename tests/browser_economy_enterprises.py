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


from scripts.browser_navigation import navigation_locator, click_control

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
                            click_control(page.locator(f'[data-theme-picker=start] [data-theme-choice={theme}]'))
                            page.evaluate('async id=>loadGame(id)',game.id);navigation_locator(page,'[data-panel-target=map]').click()
                            click_control(page.get_by_role('button',name='本地市场',exact=True))
                            click_control(page.locator('.economy-overview > summary'))
                            def expand(locator):
                                if locator.get_attribute('open') is None:click_control(locator.locator(':scope > summary'))
                            box=page.locator('#enterprise-panel');expand(box)
                            page.get_by_label('购置产业',exact=True).select_option('mine')
                            click_control(page.locator('[data-estate-action=buy]'))
                            page.wait_for_function('!busy && game.map.economy.enterprises.owned.length===1')
                            key=page.evaluate('game.map.economy.enterprises.owned[0].id')
                            card=page.locator(f'[data-estate-id="{key}"]')
                            click_control(page.locator('#map-view-tabs button[aria-controls=map-locations]'))
                            click_control(page.locator('.map-directory-link.estate'))
                            click_control(page.get_by_role('button',name='管理产业',exact=True))
                            assert card.get_attribute('open') is not None
                            def opened():expand(box);expand(card)
                            opened();page.get_by_label('产业资金金额').fill('10000');click_control(card.locator('[data-estate-action=fund]'))
                            page.wait_for_function('!busy && game.map.economy.enterprises.owned[0].cash===10000')
                            opened();card.get_by_label('自动经营保留灵石').fill('321')
                            card.get_by_label('单次自动投产支出上限').fill('4321')
                            click_control(card.locator('[data-estate-action=configure]'))
                            page.wait_for_function('!busy && game.map.economy.enterprises.owned[0].reserve_cash===321 && game.map.economy.enterprises.owned[0].expense_limit===4321')
                            # A second page writes first. Stale native buttons cannot charge again.
                            opened();saved=engine._load(game.id);row=saved.economy_v2['estates'][key]
                            engine.fleet_action(game.id,dict(action='estate_fund',estate_id=key,revision=row['revision'],amount=1))
                            before=engine.store._path(game.id).read_bytes()
                            click_control(card.locator('[data-estate-action=fund]'))
                            page.wait_for_function('!busy && game.map.economy.enterprises.owned[0].cash===10001')
                            assert engine.store._path(game.id).read_bytes()==before
                            opened();click_control(card.locator('[data-estate-action=start]'))
                            page.wait_for_function('!busy && !!game.map.economy.enterprises.owned[0].job')
                            opened();assert card.locator('[data-estate-action=start]').is_disabled()
                            card.scroll_into_view_if_needed();page.screenshot(path=str(output/f'{theme}-{width}-estate.png'))
                            engine.advance(game.id,'rest',2)
                            page.evaluate('async id=>loadGame(id)',game.id)
                            assert page.evaluate('game.map.economy.enterprises.owned[0].produced')==4
                            if page.evaluate('!!game.pending_event'):
                                g=engine._load(game.id);g.pending_event=None;engine.store.save(g);page.evaluate('async id=>loadGame(id)',game.id)
                            # An idle farm's missing inputs must never create sales,
                            # while the background market may keep trading.
                            expand(box)
                            assert page.get_by_text('全市场累计成交',exact=True).count()==1
                            assert '场地年费' in page.get_by_label('购置产业',exact=True).text_content()
                            page.get_by_label('购置产业',exact=True).select_option('farm')
                            click_control(box.locator('[data-estate-action=buy]'))
                            page.wait_for_function('!busy && game.map.economy.enterprises.owned.length===2')
                            farm_key=page.evaluate("game.map.economy.enterprises.owned.find(r=>r.kind==='farm').id")
                            farm_card=page.locator(f'[data-estate-id="{farm_key}"]')
                            expand(box);expand(farm_card)
                            farm_card.get_by_label('产业资金金额').fill('10000')
                            click_control(farm_card.locator('[data-estate-action=fund]'))
                            page.wait_for_function("!busy && game.map.economy.enterprises.owned.find(r=>r.kind==='farm').cash===10000")
                            expand(box);expand(farm_card)
                            farm_card.get_by_label('持续经营',exact=True).check()
                            farm_card.get_by_label('自动补足原料／进货',exact=True).uncheck()
                            farm_card.get_by_label('自动销售所选成品',exact=True).check()
                            click_control(farm_card.locator('[data-estate-action=configure]'))
                            page.wait_for_function("!busy && game.map.economy.enterprises.owned.find(r=>r.kind==='farm').enabled")
                            expand(box);expand(farm_card)
                            assert '仓库原料不足，无法投产' in farm_card.text_content()
                            before=engine.store._path(game.id).read_bytes()
                            click_control(farm_card.locator('[data-estate-action=start]'))
                            page.wait_for_function('!busy')
                            assert engine.store._path(game.id).read_bytes()==before
                            engine.advance(game.id,'rest',10)
                            page.evaluate('async id=>loadGame(id)',game.id)
                            farm_row=page.evaluate("game.map.economy.enterprises.owned.find(r=>r.kind==='farm')")
                            assert farm_row['income']==farm_row['produced']==0 and not farm_row['job'] and not farm_row['stock']
                            assert farm_row['expense']>1 and farm_row['maintenance']['site']==20
                            if page.evaluate('!!game.pending_event'):
                                g=engine._load(game.id);g.pending_event=None;engine.store.save(g);page.evaluate('async id=>loadGame(id)',game.id)
                            expand(box);expand(farm_card)
                            click_control(farm_card.locator('[data-estate-action=entrust]'))
                            page.wait_for_function("!busy && game.map.economy.enterprises.owned.find(r=>r.kind==='farm').entrusted")
                            expand(box);expand(farm_card)
                            click_control(farm_card.locator('[data-estate-action=entrust]'))
                            page.wait_for_function("!busy && !game.map.economy.enterprises.owned.find(r=>r.kind==='farm').entrusted")
                            farm_row=page.evaluate("game.map.economy.enterprises.owned.find(r=>r.kind==='farm')")
                            assert not farm_row['enabled'] and not farm_row['auto_buy'] and not farm_row['auto_sell']
                            navigation_locator(page,'[data-panel-target=merchant]').click()
                            management=page.locator('#fleet-network-content > details').nth(0);expand(management)
                            management.get_by_role('button',name='自建独立商队',exact=True).click()
                            page.wait_for_function('!busy && game.fleet_network.fleets.some(f=>f.player_controlled)')
                            orders=page.locator('#trade-orders-panel');expand(orders);form=orders.locator('[data-order-fleet]').first;expand(form)
                            form.get_by_label('订单执行方式').select_option('repeat');form.get_by_label('订单商品').select_option('purple_cloud_ginseng_seed')
                            click_control(form.locator('[data-fleet-action=order_configure]'))
                            page.wait_for_function("!busy && game.fleet_network.fleets.some(f=>f.trade_order?.mode==='repeat')")
                            expand(orders);expand(form);click_control(form.locator('[data-fleet-action=order_dispatch]'))
                            page.wait_for_function("!busy && game.fleet_network.fleets.some(f=>f.player_controlled && f.status==='travelling')")
                            expand(orders);expand(form);assert form.locator('[data-fleet-action=order_dispatch]').is_disabled()
                            form.get_by_label('订单执行方式').select_option('hold');click_control(form.locator('[data-fleet-action=order_configure]'))
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
    print('Enterprise browser passed: 8 layouts, deeds, idle missing-input rejection, upkeep, steward recall, production, stale recovery, standing dispatch and reload')


if __name__=='__main__':main()
