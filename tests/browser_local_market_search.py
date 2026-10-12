"""Real navigation/search/trade, path-scoped expansion UI, and worker cancellation."""
import json,re,sys,tempfile,threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.rules import add_item
from scripts.browser_navigation import navigation_locator

def main():
    output=ROOT/'build/local-market-search';output.mkdir(exist_ok=True);checks=[]
    with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
        engine=GameEngine(ROOT,Path(folder)/'saves')
        ids={}
        for path in ('dao','monster'):
            g=engine._load(engine.create_game('市场搜索','supreme_metal',path,315,custom_start=dict(world='human',realm_index=4),monster_species_id='fox' if path=='monster' else None)['id'])
            g.pending_event=None;add_item(g.player,'spirit_stone',10**8);engine.store.save(g);ids[path]=g.id
        class Quiet(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            http=ThreadingHTTPServer(('127.0.0.1',0),Quiet);threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    for theme in 'abdf':
                        for width,height in [(1440,960),(393,852)]:
                            page=browser.new_page(viewport=dict(width=width,height=height));errors=[]
                            page.on('pageerror',lambda e:errors.append(str(e)))
                            page.goto(f'http://127.0.0.1:{http.server_port}');page.wait_for_function('configData && window.GameThemes')
                            page.locator(f'[data-theme-picker=start] [data-theme-choice={theme}]').click()
                            page.evaluate('async id=>loadGame(id)',ids['dao'])
                            assert page.locator('[data-panel-target=civilizations]').evaluate('(n)=>n.classList.contains("hidden")')
                            navigation_locator(page,'[data-panel-target=market]').click()
                            page.locator('#market-view-tabs [data-market-view=local]').click()
                            assert page.locator('#market-local #local-market-content').is_visible()
                            before=engine.store._path(ids['dao']).read_bytes()
                            page.get_by_label('查找本地商品').fill('矿')
                            assert page.locator('.economy-good').count()>0
                            assert all('矿' in name for name in page.locator('.economy-good b').all_text_contents())
                            page.get_by_label('匹配方式').select_option('pattern')
                            page.get_by_label('查找本地商品').fill('矿|草|丹')
                            page.wait_for_function('document.querySelector(".economy-search-feedback").textContent.startsWith("找到")')
                            expected=page.evaluate('game.map.economy.rows.filter(r=>/矿|草|丹/u.test(r.name)).length')
                            assert page.locator('.economy-good').count()==expected
                            page.get_by_label('查找本地商品').fill('[')
                            page.get_by_role('status').filter(has_text='正则表达式无效').wait_for()
                            assert page.locator('.economy-good').count()==0
                            page.get_by_label('查找本地商品').fill('矿|草')
                            page.wait_for_function('document.querySelector(".economy-search-feedback").textContent.startsWith("找到")')
                            assert before==engine.store._path(ids['dao']).read_bytes()
                            page.locator('.economy-overview > summary').click()
                            card=page.locator('.economy-good').filter(has=page.locator('[data-trade=buy]:enabled')).first
                            item=card.get_attribute('data-item-id');revision=page.evaluate('game.map.economy.revision')
                            stock=page.evaluate('id=>game.map.economy.rows.find(r=>r.id===id).stock',item)
                            card.locator('[data-trade=buy]').click()
                            page.wait_for_function('r=>!busy && game.map.economy.revision>r',arg=revision)
                            page.wait_for_function('document.querySelector(".economy-search-feedback").textContent.startsWith("找到")')
                            assert page.evaluate('id=>game.map.economy.rows.find(r=>r.id===id).stock',item)==stock-1
                            assert page.locator('.economy-overview').get_attribute('open') is not None
                            page.locator('.economy-overview > summary').click()
                            navigation_locator(page,'[data-panel-target=map]').click()
                            page.locator('#map-view-tabs').get_by_role('button',name='本地市场',exact=True).click()
                            assert page.locator('#map-economy #local-market-content').is_visible()
                            assert page.locator('#local-market-content').count()==1
                            assert page.get_by_label('查找本地商品').input_value()=='矿|草'
                            navigation_locator(page,'[data-panel-target=market]').click()
                            page.wait_for_selector('#market-local #local-market-content',state='visible')
                            page.locator('#market-card').evaluate('(n)=>n.scrollTop=0')
                            page.wait_for_function('!document.querySelector("#market-card").getAnimations({subtree:true}).some(a=>a.playState==="running" && a.effect.getTiming().iterations!==Infinity)')
                            assert page.locator('#market-card').evaluate('(n)=>n.scrollWidth<=n.clientWidth+1')
                            page.screenshot(path=str(output/f'market-{theme}-{width}.png'))
                            page.evaluate('async id=>loadGame(id)',ids['monster'])
                            assert not page.locator('[data-panel-target=civilizations]').evaluate('(n)=>n.classList.contains("hidden")')
                            navigation_locator(page,'[data-panel-target=civilizations]').click()
                            page.wait_for_selector('#civilizations-card.panel-open .mc-tabs')
                            page.wait_for_function('!document.querySelector("#civilizations-card").getAnimations({subtree:true}).some(a=>a.playState==="running" && a.effect.getTiming().iterations!==Infinity)')
                            page.screenshot(path=str(output/f'monster-{theme}-{width}.png'))
                            assert page.locator('#civilizations-card').evaluate('(n)=>n.scrollWidth<=n.clientWidth+1')
                            page.evaluate('async id=>loadGame(id)',ids['dao'])
                            page.wait_for_selector('#civilizations-card',state='hidden')
                            assert not errors,errors
                            checks.append(dict(theme=theme,width=width,status='passed'));page.close()
                    # A deliberately pathological expression must leave the UI alive.
                    page=browser.new_page();page.goto(f'http://127.0.0.1:{http.server_port}');page.wait_for_function('configData')
                    page.evaluate('async id=>loadGame(id)',ids['dao'])
                    navigation_locator(page,'[data-panel-target=market]').click()
                    page.locator('#market-view-tabs [data-market-view=local]').click()
                    page.evaluate('''()=>LocalEconomy.prepare({...game.map.economy,rows:[{...game.map.economy.rows[0],name:'a'.repeat(40000)+'!'}]},game,()=>{},()=>{})''')
                    page.get_by_label('查找本地商品').fill('(a+)+$');page.get_by_label('匹配方式').select_option('pattern')
                    page.get_by_role('status').filter(has_text='表达式过于复杂').wait_for(timeout=10000)
                    page.get_by_label('匹配方式').select_option('text');page.get_by_label('查找本地商品').fill('a')
                    assert page.locator('.economy-good').count()==1
                    page.close();browser.close()
            finally:http.shutdown();http.server_close()
    (output/'report.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
    print('8 layouts passed: path visibility, distinct DLC buttons, regex errors/timeouts, actual buy, shared market and read-only navigation')
if __name__=='__main__':main()
