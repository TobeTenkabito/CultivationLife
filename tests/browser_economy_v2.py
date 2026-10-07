"""Real HTTP + clicks: market trades, stale recovery, reload and four themes."""
import json
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.rules import add_item
from cultivation_life.system.economy.state import local_market
from cultivation_life.system.economy.local_market import quote


def main():
    output=ROOT/'build/economy-v2-browser';output.mkdir(exist_ok=True)
    checks=[]
    with tempfile.TemporaryDirectory() as folder:
        engine=GameEngine(ROOT,Path(folder)/'saves')
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            httpd=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            threading.Thread(target=httpd.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    for theme in 'abdf':
                        for width,height in [(1440,960),(393,852)]:
                            game=engine._load(engine.create_game('市井经营','supreme_metal','dao',213,preset_id='core')['id'])
                            game.pending_event=None
                            add_item(game.player,'spirit_stone',10**8)
                            engine.store.save(game)
                            page=browser.new_page(viewport=dict(width=width,height=height))
                            errors=[];requests=[]
                            page.on('pageerror',lambda err:errors.append(str(err)))
                            page.on('request',lambda req:requests.append(req.post_data_json)
                                    if req.method=='POST' and req.url.endswith('/local-market-trade') else None)
                            page.goto(f'http://127.0.0.1:{httpd.server_port}')
                            page.wait_for_function('configData && window.GameThemes')
                            page.locator(f'[data-theme-picker=start] [data-theme-choice={theme}]').click()
                            page.evaluate('async id=>loadGame(id)',game.id)
                            page.locator('[data-panel-target=map]').click()
                            page.get_by_role('button',name='本地市场',exact=True).click()
                            assert page.locator('#map-economy').is_visible()
                            before=engine.store._path(game.id).read_bytes()
                            page.get_by_role('button',name='地域地图',exact=True).click()
                            page.get_by_role('button',name='本地市场',exact=True).click()
                            assert before==engine.store._path(game.id).read_bytes()
                            card=page.locator('.economy-good').filter(has=page.locator('[data-trade=buy]:enabled')).first
                            item=card.get_attribute('data-item-id')
                            stock=local_market(engine.store.load(game.id))['commodities'][item]['stock']
                            revision=page.evaluate('game.map.economy.revision')
                            card.locator('[data-trade=buy]').click()
                            page.wait_for_function('r=>!busy && game.map.economy.revision>r',arg=revision)
                            saved=engine.store.load(game.id)
                            assert local_market(saved)['commodities'][item]['stock']==stock-1
                            assert len(requests)==1
                            # Another page trades first. The rejected stale page refreshes once.
                            market=local_market(saved);row=market['commodities'][item]
                            engine.trade_local_market(game.id,dict(market_id=market['id'],revision=market['revision'],
                                item_id=item,side='buy',quantity=1,total=quote(row,'buy',1)['total']))
                            before=engine.store._path(game.id).read_bytes()
                            page.locator(f'.economy-good[data-item-id="{item}"] [data-trade=buy]').click()
                            page.wait_for_function('r=>!busy && game.map.economy.revision>r',arg=market['revision'])
                            assert len(requests)==2
                            assert before==engine.store._path(game.id).read_bytes()
                            assert page.locator(f'.economy-good[data-item-id="{item}"] [data-trade=sell]').is_enabled()
                            page.locator(f'.economy-good[data-item-id="{item}"] [data-trade=sell]').click()
                            page.wait_for_function('!busy')
                            assert len(requests)==3
                            page.get_by_label('本地市场交易数量').select_option('100')
                            assert page.locator(f'.economy-good[data-item-id="{item}"] [data-trade=sell]').is_disabled()
                            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
                            assert page.locator('#map-card').evaluate('(n)=>n.scrollWidth<=n.clientWidth+1')
                            page.get_by_label('本地市场交易数量').select_option('1')
                            page.locator('#map-card').evaluate('(n)=>n.scrollTop=0')
                            page.wait_for_function("getComputedStyle(document.querySelector('#toast')).opacity === '0'")
                            page.screenshot(path=str(output/f'{theme}-{width}.png'))
                            page.reload();page.wait_for_function('configData')
                            page.evaluate('async id=>loadGame(id)',game.id)
                            assert page.evaluate('game.map.economy.turnover')>0
                            assert not errors,errors
                            checks.append(dict(theme=theme,width=width,status='passed'))
                            page.close()
                    browser.close()
            finally:httpd.shutdown();httpd.server_close()
    (output/'report.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Economy V2 browser passed: 8 layouts, real buy/sell, stale recovery, exact persistence and disabled options')


if __name__=='__main__':main()
