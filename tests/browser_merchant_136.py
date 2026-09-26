"""Browser acceptance: material categories, real product previews and Debug gating."""
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from playwright.sync_api import sync_playwright
from cultivation_life import server as server_module
from cultivation_life.engine import GameEngine
from cultivation_life.rules import add_item


def main():
    with tempfile.TemporaryDirectory() as directory:
        engine=GameEngine(ROOT,Path(directory))
        game_id=engine.create_game('商盟定制验收','heavenly','dao',1361,preset_id='core')['id']
        game=engine._load(game_id)
        alliance=game.merchant_state['worlds']['human'][0]
        game.player.location_id=alliance['hq']
        add_item(game.player,'spirit_stone',10**12)
        engine.store.save(game)
        runtime={'debug':True,'mode':'debug'}
        with patch.object(server_module,'ENGINE',engine),patch.object(server_module,'load_runtime_config',return_value=runtime):
            httpd=ThreadingHTTPServer(('127.0.0.1',0),server_module.Handler)
            threading.Thread(target=httpd.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as playwright:
                    browser=playwright.chromium.launch(headless=True)
                    page=browser.new_page(viewport={'width':1440,'height':1050})
                    errors=[]
                    page.on('pageerror',lambda error:errors.append(str(error)))
                    page.goto(f'http://127.0.0.1:{httpd.server_port}')
                    page.wait_for_function('configData?.debug===true')
                    page.evaluate('async id=>{await loadGame(id);render(game);}',game_id)
                    page.locator('[data-panel-target="merchant"]').click()
                    page.locator('.merchant-debug-hq').first.click()
                    page.wait_for_function('game.merchant_system.membership?.rank===2')
                    assert '总部 特使' in page.locator('.merchant-membership').text_content()
                    panel=page.locator('.merchant-alliance').first

                    def open_form():
                        panel.get_by_text('发布委托',exact=True).click()
                        return panel.locator('form')

                    def wait_quote(form):
                        form.get_by_role('button',name='支付并发布委托').wait_for()
                        page.wait_for_function("!document.querySelector('.merchant-post button[type=submit]').disabled")

                    form=open_form()
                    form.get_by_label('材料分类',exact=True).select_option('formation')
                    form.get_by_label('材料或道具数量',exact=True).fill('3')
                    wait_quote(form)
                    form.get_by_role('button',name='支付并发布委托').click()
                    page.wait_for_function('game.merchant_system.posted.length===1')
                    assert engine._load(game_id).merchant_state['posted'][0]['material_category']=='formation'

                    form=open_form()
                    form.get_by_label('委托类型',exact=True).select_option('formation')
                    form.get_by_label('原材料等级',exact=True).select_option('2')
                    wait_quote(form)
                    assert form.locator('.merchant-product-preview table tr').count()==7
                    form.get_by_label('杀势最低要求',exact=True).fill('100')
                    page.wait_for_function("document.querySelector('.merchant-quote').textContent.includes('无法同时满足')")
                    assert form.get_by_role('button',name='支付并发布委托').is_disabled()
                    form.get_by_label('杀势最低要求',exact=True).fill('0')
                    wait_quote(form)
                    form.locator('.merchant-product-preview').scroll_into_view_if_needed()
                    page.screenshot(path=str(ROOT/'build/merchant-136-formation.png'))
                    form.get_by_role('button',name='支付并发布委托').click()
                    page.wait_for_function('game.merchant_system.posted.length===2')

                    form=open_form()
                    form.get_by_label('委托类型',exact=True).select_option('weapon')
                    form.get_by_label('炼器模具',exact=True).select_option('umbrella')
                    wait_quote(form)
                    assert '伞器胎模' in form.locator('.merchant-product-preview').text_content()
                    form.get_by_role('button',name='支付并发布委托').click()
                    page.wait_for_function('game.merchant_system.posted.length===3')

                    form=open_form()
                    form.get_by_label('委托类型',exact=True).select_option('item')
                    form.get_by_label('所需材料或道具',exact=True).select_option('jinque_metal')
                    wait_quote(form)
                    assert '金阙残书' in form.get_by_label('所需材料或道具',exact=True).text_content()
                    form.get_by_role('button',name='支付并发布委托').click()
                    page.wait_for_function('game.merchant_system.posted.length===4')

                    form=open_form()
                    assert form.get_by_label('目标界面',exact=True).locator('option').count()==1
                    wait_quote(form)
                    assert form.get_by_label('目标界面',exact=True).input_value()=='human'
                    runtime.update(debug=False,mode='release')
                    page.evaluate("async()=>{configData=await api('/api/config');render(game);}")
                    assert page.locator('.merchant-debug-hq').count()==0
                    response=page.request.post(f'http://127.0.0.1:{httpd.server_port}/api/games/{game_id}/merchant-debug-hq',data={'alliance_id':alliance['id']})
                    assert response.status==404
                    page.set_viewport_size({'width':430,'height':900})
                    panel.get_by_text('发布委托',exact=True).click()
                    form=panel.locator('form');form.get_by_label('委托类型',exact=True).select_option('weapon');wait_quote(form)
                    form.locator('.merchant-product-preview').scroll_into_view_if_needed()
                    page.screenshot(path=str(ROOT/'build/merchant-136-mobile.png'))
                    assert page.locator('#merchant-card').evaluate('e=>e.scrollWidth<=e.clientWidth+2')
                    assert not errors,errors
                    browser.close()
            finally:
                httpd.shutdown();httpd.server_close()
    print('Merchant 1.36 browser checks passed')


if __name__=='__main__':
    main()
