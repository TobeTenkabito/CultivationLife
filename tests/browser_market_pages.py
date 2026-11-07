"""Real clicks: dedicated shelf, tabs, paging, local trades and stale quotes."""
import json, os, sys, tempfile, threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.rules import add_item
from scripts.browser_navigation import navigation_locator, reveal_subpage


def main():
    out=ROOT/'build'/os.environ.get('UI_SCREENSHOT_DIR','market-pages');out.mkdir(exist_ok=True);checks=[]
    with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
        engine=GameEngine(ROOT,Path(folder)/'saves')
        g=engine._load(engine.create_game('分页验收','supreme_metal','dao',315,custom_start=dict(world='human',realm_index=4))['id'])
        g.pending_event=None;add_item(g.player,'spirit_stone',10**9);engine.store.save(g)
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            http=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
            base=f'http://127.0.0.1:{http.server_port}'
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    for palette in ('light','dark'):
                        for width,height in ((1440,960),(390,844),(844,390)):
                            page=browser.new_page(viewport=dict(width=width,height=height));errors=[]
                            page.on('pageerror',lambda e:errors.append(str(e)))
                            page.goto(base);page.wait_for_function('configData && !busy')
                            page.locator(f'[data-theme-picker=start] [data-pixel-theme-choice={palette}]').click()
                            page.evaluate('async id=>loadGame(id)',g.id);page.wait_for_function('!busy && game')
                            navigation_locator(page,'[data-panel-target=market]').click()
                            page.locator('#market-content [data-subpage="培养与能源"]').click()
                            before=engine.store._path(g.id).read_bytes()
                            page.get_by_label('培养资材用途').select_option('energy')
                            assert page.locator('#training-market-offers .market-offer:visible').count()>0
                            assert page.evaluate('''()=>[...document.querySelectorAll('#training-market-offers .market-offer:not(.hidden):not([data-list-page-hidden]) .market-buy')].every(b=>game.market.training_material_offers.find(r=>r.id===b.dataset.offerId).training_category==='energy')''')
                            page.get_by_label('培养资材用途').select_option('all')
                            assert engine.store._path(g.id).read_bytes()==before
                            listing=page.locator('#training-market-offers');pager=listing.locator('xpath=preceding-sibling::nav[1]')
                            count=listing.locator('.market-offer').count();assert count>10
                            page.screenshot(animations='disabled',path=str(out/f'shelf-first-{palette}-{width}.png'))
                            seen=set()
                            while True:
                                for row in listing.locator('.market-offer:visible').all():seen.add(row.locator('.market-buy').get_attribute('data-offer-id'))
                                if pager.get_by_role('button',name='下一页').is_disabled():break
                                pager.get_by_role('button',name='下一页').click()
                            assert len(seen)==count
                            assert engine.store._path(g.id).read_bytes()==before
                            # Genuine purchase on the last page retains page and refuses replay.
                            buy=listing.locator('.market-offer:visible .market-buy:enabled').first
                            if buy.count():
                                offer=buy.get_attribute('data-offer-id');status=pager.locator('span').inner_text()
                                buy.click();page.wait_for_function('!busy')
                                page.wait_for_function('id=>game.market.training_material_offers.find(r=>r.id===id)?.sold',arg=offer)
                                assert pager.locator('span').inner_text()==status
                                assert page.request.post(base+f'/api/games/{g.id}/market-buy',data=dict(offer_id=offer)).status==400
                            page.screenshot(animations='disabled',path=str(out/f'shelf-{palette}-{width}.png'))
                            page.locator('#market-view-tabs [data-market-view=local]').click()
                            page.get_by_label('查找本地商品').fill('矿')
                            assert page.locator('.economy-good:visible').count()>0
                            before=engine.store._path(g.id).read_bytes()
                            for title in ('市场概况','商队流通','市政商势','产业经营','商品交易'):
                                tab=page.locator(f'#local-market-content [data-subpage="{title}"]')
                                if tab.count():tab.click()
                            assert engine.store._path(g.id).read_bytes()==before
                            page.get_by_label('匹配方式').select_option('pattern');page.get_by_label('查找本地商品').fill('矿|草')
                            page.wait_for_function('document.querySelector(".economy-search-feedback").textContent.startsWith("找到")')
                            card=page.locator('.economy-good:visible').filter(has=page.locator('[data-trade=buy]:enabled')).first
                            if card.count():
                                item=card.get_attribute('data-item-id');stock=page.evaluate('id=>game.map.economy.rows.find(r=>r.id===id).stock',item)
                                card.locator('[data-trade=buy]').click();page.wait_for_function('!busy')
                                page.wait_for_function('({item,stock})=>game.map.economy.rows.find(r=>r.id===item).stock===stock-1',arg=dict(item=item,stock=stock))
                            page.locator('#market-card').evaluate('n=>n.scrollTop=0')
                            page.screenshot(animations='disabled',path=str(out/f'local-{palette}-{width}.png'))
                            assert page.locator('.economy-good:visible').first.evaluate('n=>{const box=n.closest(".utility-panel").getBoundingClientRect(),b=n.querySelector(".economy-actions").getBoundingClientRect();return b.top>=box.top&&b.bottom<=box.bottom+1}')
                            navigation_locator(page,'[data-panel-target=map]').click()
                            page.locator('#map-view-tabs').get_by_role('button',name='本地市场',exact=True).click()
                            assert page.locator('#map-economy #local-market-content').is_visible()
                            assert page.locator('#local-market-content').count()==1
                            assert page.get_by_label('查找本地商品').input_value()=='矿|草'
                            navigation_locator(page,'[data-panel-target=formation]').click()
                            tabs=page.locator('#formation-card > .panel-page-tabs')
                            page.locator('#formation-name').fill('分页不丢失')
                            for title in ('阵材库','镇地阵域','阵法预设','布阵推演'):tabs.get_by_role('tab',name=title,exact=True).click()
                            assert page.locator('#formation-name').input_value()=='分页不丢失'
                            page.screenshot(animations='disabled',path=str(out/f'formation-{palette}-{width}.png'))
                            navigation_locator(page,'[data-panel-target=captive]').click()
                            for title in ('傀儡','外来元神','俘虏'):page.locator('#captive-card > .panel-page-tabs').get_by_role('tab',name=title,exact=True).click()
                            page.screenshot(animations='disabled',path=str(out/f'captive-{palette}-{width}.png'))
                            navigation_locator(page,'[data-panel-target=puppet-workshop]').click()
                            page.screenshot(animations='disabled',path=str(out/f'workshop-{palette}-{width}.png'))
                            # Small/large list replacement clamps page; controls and values remain live.
                            result=page.evaluate("""()=>{const list=document.createElement('div');document.body.append(list);let clicked=0;
                                for(let i=0;i<9;i++){const b=document.createElement('button');b.textContent=String(i);b.onclick=()=>clicked++;list.append(b);}
                                PanelPages.paginate(list,{key:'fixture',size:2});const nav=list.previousElementSibling;nav.lastChild.click();nav.lastChild.click();nav.lastChild.click();nav.lastChild.click();
                                list.children[8].click();list.replaceChildren(document.createElement('button'));PanelPages.paginate(list,{key:'fixture',size:2});
                                const ok=clicked===1&&!list.firstChild.hasAttribute('data-list-page-hidden')&&nav.firstChild.disabled&&nav.lastChild.disabled;nav.remove();list.remove();return ok;}""")
                            assert result and not errors,errors
                            checks.append(dict(palette=palette,width=width,status='passed',training_goods=count));page.close()
                    browser.close()
            finally:http.shutdown();http.server_close()
    (out/'report.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Market pages: six layouts, complete read-only paging, purchase/replay, local trades, shared view, formation drafts and bounds passed')

if __name__=='__main__':main()
