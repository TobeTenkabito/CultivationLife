"""Android commission touch targets, decimal bounds, validation and publication."""
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'scripts'))

from playwright.sync_api import sync_playwright
from cultivation_life import server as server_module
from cultivation_life.engine import GameEngine
from cultivation_life.rules import add_item
from android_css import compile_css


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
        with patch.object(server_module,'ENGINE',engine),patch.object(server_module,'PERSISTENCE_ROOT',Path(directory)),patch.object(server_module,'load_runtime_config',return_value=runtime):
            httpd=ThreadingHTTPServer(('127.0.0.1',0),server_module.Handler)
            threading.Thread(target=httpd.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as playwright:
                    browser=playwright.chromium.launch(headless=True)
                    page=browser.new_page(viewport={'width':1440,'height':1050})
                    page.route('**/android/fonts/WendaoSerif.woff2',lambda route:route.fulfill(path=str(ROOT/'android/app/src/main/mobile/fonts/WendaoSerif.woff2')))
                    errors=[]
                    page.on('pageerror',lambda error:errors.append(str(error)))
                    page.goto(f'http://127.0.0.1:{httpd.server_port}')
                    page.wait_for_function('configData?.debug===true')
                    page.add_style_tag(content=compile_css((ROOT/'android/app/src/main/mobile/mobile.css').read_text(encoding='utf-8')))
                    page.evaluate('document.fonts.ready')
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
                    form.get_by_label('委托类型',exact=True).select_option('formation')
                    wait_quote(form)
                    for width in (360,393,800):
                        page.set_viewport_size({'width':width,'height':900})
                        for theme in 'abcdef':
                            page.evaluate("t=>document.querySelector('[data-theme-picker=dialog] [data-theme-choice='+t+']').click()",theme)
                            page.evaluate('GameThemes.saved')
                            field=form.get_by_label('杀势最低要求',exact=True)
                            field.scroll_into_view_if_needed()
                            box=field.bounding_box()
                            page.screenshot(path=str(ROOT/f'build/commission-1412-{width}-{theme}.png'))
                            assert box['width']>=80 and box['height']>=44, (width,theme,'input too small',box)
                            assert field.get_attribute('inputmode')=='decimal'
                            field.fill('0.25')
                            assert field.input_value()=='0.25'
                            form.get_by_label('杀势最高要求',exact=True).fill('99.75')
                            wait_quote(form)
                            assert field.input_value()=='0.25'
                    field.fill('')
                    assert not form.evaluate('e=>e.checkValidity()'), 'Empty bound accepted'
                    field.fill('100.01')
                    assert not form.evaluate('e=>e.checkValidity()'), 'Out-of-range bound accepted'
                    field.fill('0.251')
                    assert not form.evaluate('e=>e.checkValidity()'), 'Invalid decimal step accepted'
                    field.fill('0.25')
                    wait_quote(form)
                    form.get_by_role('button',name='支付并发布委托').click()
                    page.wait_for_function('game.merchant_system.posted.length===1')
                    order=engine._load(game_id).merchant_state['posted'][0]
                    assert order['spec']['requirements']['kill']==0.25
                    assert order['spec']['maxima']['kill']==99.75
                    assert not errors,errors
                    browser.close()
            finally:
                httpd.shutdown();httpd.server_close()
    print('Commission touch layout and decimal input passed: six themes, three widths, actual publication')

if __name__=='__main__':main()
