"""M2 real HTTP touch acceptance in an emulated Android browser, not an APK test."""
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
from cultivation_life.rules import max_hp,max_mp
from cultivation_life.system.heavens.definitions import CONTACT_SITES
from cultivation_life.system.heavens.state import get_echo


def main():
    output=ROOT/'build/heavens-m2-touch'
    output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder)
        engine=GameEngine(ROOT,root/'saves')
        keys=[]
        for contact in CONTACT_SITES:
            key=engine.create_game('触屏验收','supreme_metal',contact.visitor_path,4242,preset_id='core')['id']
            game=engine.store.load(key)
            p=game.player
            p.world,p.location_id,p.realm_index=contact.world,contact.location_id,9
            p.immortal_power_converted=contact.world=='celestial'
            p.lifespan,p.next_tribulation_age=None,999999
            p.hp,p.mp=max_hp(p),max_mp(p)
            game.settings['silent_events']=True
            engine.store.save(game)
            keys.append(key)
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',root):
            httpd=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
            threading.Thread(target=httpd.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch(headless=True)
                    context=browser.new_context(**pw.devices['Pixel 7'])
                    page=context.new_page()
                    errors=[]
                    page.on('pageerror',lambda e:errors.append(str(e)))
                    page.goto(f'http://127.0.0.1:{httpd.server_port}')
                    page.wait_for_function('window.GameThemes && configData')
                    page.evaluate('window.touchEvents=0;document.addEventListener("touchstart",()=>touchEvents++,{passive:true})')
                    for index,(key,contact) in enumerate(zip(keys,CONTACT_SITES)):
                        page.evaluate('async id=>{await loadGame(id)}',key)
                        if not page.locator('#heavens-card').is_visible(): page.locator('[data-panel-target=heavens]').tap()
                        page.get_by_role('tab',name='诸界',exact=True).tap()
                        page.get_by_role('button',name='查看'+contact.name,exact=True).tap()
                        label='体察潮汐' if contact.id=='sea_echo' else '体察'+contact.evidence[0]
                        page.get_by_role('button',name=label,exact=True).wait_for()
                        before=engine.store._path(key).read_bytes()
                        page.get_by_role('button',name=label,exact=True).tap()
                        page.locator('#game-confirm-backdrop:not(.hidden)').wait_for()
                        assert engine.store._path(key).read_bytes()==before
                        page.locator('#game-confirm-accept').tap()
                        page.wait_for_function('!busy && game.heavens.next_command_seq===2')
                        saved=engine.store.load(key)
                        assert get_echo(saved.heavens_state['runtime'],contact.id)['observed_cycle']==0
                        assert saved.heavens_state['runtime']['processed_years']==20
                        page.get_by_role('tab',name='行程',exact=True).tap()
                        page.get_by_role('tab',name='护持',exact=True).tap()
                        back=page.get_by_role('button',name='‹ 返回护持目录',exact=True)
                        if back.count():back.tap()
                        assert page.locator('#heavens-content .heavens-destination').count()==4
                        page.get_by_role('button',name='查看'+contact.name,exact=True).tap()
                        page.locator('[data-upkeep=unavailable]').wait_for()
                        assert page.get_by_role('button',name='部署托管护持',exact=True).is_disabled()
                        if index==0:
                            disk=engine.store._path(key).read_bytes()
                            for theme in 'abdf':
                                page.locator('#theme-open').tap()
                                page.locator(f'[data-theme-picker=dialog] [data-theme-choice={theme}]').tap()
                                page.locator('[data-close-dialog=theme-dialog]').tap()
                                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                                assert page.locator('#heavens-content').evaluate('(el)=>el.scrollWidth<=el.clientWidth+1')
                                assert page.get_by_role('button',name='资助迁居',exact=True).count()==0
                                page.screenshot(path=str(output/f'{theme}-android.png'))
                            assert engine.store._path(key).read_bytes()==disk
                    touches=page.evaluate('touchEvents')
                    assert touches>40 and page.evaluate('navigator.maxTouchPoints')>0
                    assert 'Android' in page.evaluate('navigator.userAgent')
                    assert not errors,errors
                    (output/'report.json').write_text(json.dumps(dict(device='Pixel 7',android_browser_emulation=True,
                        native_apk_test=False,worlds=[c.world for c in CONTACT_SITES],themes=list('abdf'),
                        touch_events=touches,errors=errors),indent=2),encoding='utf-8')
                    browser.close()
            finally:
                httpd.shutdown();httpd.server_close()
    print('M2 Android browser touch checks passed')


if __name__=='__main__':main()
