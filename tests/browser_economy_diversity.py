"""Real page clicks: native cores, exact alchemy, bounded medicine and hunting."""
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
from cultivation_life.content_registry import ITEM_CATALOG
from cultivation_life.economy_content import inputs, material_id, product_id
from cultivation_life.rules import add_item
from cultivation_life.system.economy.ledger import transfer_value
from cultivation_life.system.economy.state import local_market


def main():
    output=ROOT/'build/economy-diversity/browser';output.mkdir(parents=True,exist_ok=True)
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
                            game=engine._load(engine.create_game('商品闭环页面','supreme_metal','dao',315,preset_id='nascent')['id'])
                            game.pending_event=None;game.settings['silent_events']=True
                            transfer_value(game,'background:human','player',10**7,'验收资金')
                            core=material_id('human',4,'core_soul');pill=product_id('human',4,'longevity')
                            for item,n in inputs('human',4,'longevity').items():add_item(game.player,item,n)
                            add_item(game.player,pill,2)
                            game.economy_v2['personal']['longevity_used']=145
                            local_market(game)['commodities'][core]['stock']=0
                            game.auction_state.update(status='black_market',world='human',location_id=game.player.location_id,location_name='验收黑市')
                            engine.store.save(game)
                            page=browser.new_page(viewport=dict(width=width,height=height));errors=[]
                            page.on('pageerror',lambda error:errors.append(str(error)))
                            page.goto(f'http://127.0.0.1:{httpd.server_port}');page.wait_for_function('configData && window.GameThemes')
                            page.locator(f'[data-theme-picker=start] [data-theme-choice={theme}]').click()
                            page.evaluate('async id=>loadGame(id)',game.id)
                            page.locator('[data-panel-target=auction]').click()
                            page.locator('#black-market-pattern').fill(ITEM_CATALOG[core].name)
                            page.locator('#black-market-search-form button').click()
                            page.wait_for_function('!busy && game.auction_system.black_market_results.length>0')
                            result=page.locator('#black-market-results .auction-lot').filter(has_text=ITEM_CATALOG[core].name).first
                            result.locator('input').fill('3');result.get_by_role('button').click()
                            page.wait_for_function('id=>!busy && game.player.inventory.some(i=>i.id===id && i.quantity===3)',arg=core)
                            assert local_market(engine.store.load(game.id))['commodities'][core]['stock']==0
                            page.locator('#black-market-leave').click();page.wait_for_function('!busy')
                            page.locator('[data-panel-target=spirit-field]').click()
                            workbench=page.locator('.alchemy-workbench');workbench.locator('summary').click()
                            page.locator('#alchemy-target').select_option(pill)
                            assert '完整' in page.locator('#alchemy-recipe-hint').inner_text()
                            required=inputs('human',4,'longevity')
                            first=next(iter(required))
                            page.locator(f'#alchemy-materials input[data-item-id="{first}"]').fill('1')
                            saved=engine.store._path(game.id).read_bytes()
                            page.locator('#alchemy-refine').click();page.wait_for_function('!busy')
                            assert engine.store._path(game.id).read_bytes()==saved
                            for item,n in required.items():page.locator(f'#alchemy-materials input[data-item-id="{item}"]').fill(str(n))
                            page.locator('#alchemy-refine').click()
                            page.wait_for_function('ids=>!busy && ids.every(k=>!game.player.inventory.some(i=>i.id===k))',arg=list(required))
                            assert engine.store.load(game.id).history[-1].event_id=='SYS_ALCHEMY'
                            assert all(not any(i.id==k for i in engine.store.load(game.id).player.inventory) for k in required)
                            page.locator('[data-panel-target=inventory]').click()
                            row=page.locator('#inventory-list .item').filter(has_text=ITEM_CATALOG[pill].name).first
                            before=engine.store.load(game.id).player.lifespan
                            row.get_by_role('button',name='服用',exact=True).click()
                            page.wait_for_function('n=>!busy && game.player.lifespan===n+5',arg=before)
                            saved=engine.store._path(game.id).read_bytes()
                            row.get_by_role('button',name='服用',exact=True).click();page.wait_for_function('!busy')
                            assert engine.store._path(game.id).read_bytes()==saved
                            page.locator('[data-panel-target=map]').click()
                            page.get_by_role('button',name='本地市场',exact=True).click()
                            box=page.locator('#enterprise-panel');box.locator(':scope > summary').click()
                            page.get_by_label('购置产业',exact=True).select_option('hunt')
                            page.locator('[data-estate-action=buy]').click()
                            page.wait_for_function('!busy && game.map.economy.enterprises.owned.some(r=>r.kind==="hunt")')
                            card=page.locator('[data-estate-id$=":hunt"]')
                            if box.get_attribute('open') is None:box.locator(':scope > summary').click()
                            card.locator(':scope > summary').click()
                            assert '本地资源' in card.inner_text()
                            card.get_by_label('产业资金金额').fill('100000')
                            card.locator('[data-estate-action=fund]').click();page.wait_for_function('!busy')
                            def opened():
                                for detail in (box,card):
                                    if detail.get_attribute('open') is None:detail.locator(':scope > summary').click()
                            opened();card.get_by_label('自动补足原料／进货').check()
                            card.locator('[data-estate-action=configure]').click();page.wait_for_function('!busy')
                            opened();card.locator('[data-estate-action=start]').click()
                            page.wait_for_function('!busy && game.map.economy.enterprises.owned.some(r=>r.kind==="hunt" && r.job)')
                            opened();assert card.locator('[data-estate-action=start]').is_disabled()
                            actual=engine.store.load(game.id);hunter=next(r for r in actual.economy_v2['estates'].values() if r['kind']=='hunt')
                            assert hunter['reserve']==4996 and len(hunter['job']['inputs'])==1
                            card.scroll_into_view_if_needed();page.screenshot(path=str(output/f'{theme}-{width}.png'))
                            page.wait_for_function('document.documentElement.scrollWidth<=innerWidth+2')
                            saved=engine.store._path(game.id).read_bytes();page.evaluate('async id=>loadGame(id)',game.id)
                            assert engine.store._path(game.id).read_bytes()==saved and not errors,errors
                            checks.append(dict(theme=theme,width=width,status='passed'));page.close()
                    browser.close()
            finally:httpd.shutdown();httpd.server_close()
    (output/'report.json').write_text(json.dumps(checks,indent=2),encoding='utf8')
    print('Economy diversity browser passed: 8 layouts, black-market cores, exact alchemy, lifespan cap, hunting and reload')


if __name__=='__main__':main()
