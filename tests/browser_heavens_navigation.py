"""Real UI navigation, local omens, stale response isolation and compact four-theme pages."""
import json
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.rules import max_hp, max_mp
from cultivation_life.system.heavens.calendar import year_step, YearContext


def main():
    output=ROOT/'build/heavens-navigation-browser'
    output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder)
        engine=GameEngine(ROOT,root/'saves')
        key=engine.create_game('听石客','supreme_metal','dao',927,preset_id='core')['id']
        game=engine.store.load(key)
        p=game.player
        p.world,p.location_id,p.realm_index='human','wudi_plain',2
        p.lifespan,p.next_tribulation_age=None,999999
        p.hp,p.mp=max_hp(p),max_mp(p)
        game.settings['silent_events']=True
        for n in range(1,101):year_step(engine._dependencies.heavens,game,YearContext(n))
        assert game.heavens_state['runtime']['omens']['stone_resonance']
        engine.store.save(game)
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',root):
            httpd=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
            threading.Thread(target=httpd.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch(headless=True)
                    page=browser.new_page(viewport={'width':1440,'height':1050})
                    errors=[]
                    page.on('pageerror',lambda error:errors.append(str(error)))
                    page.goto(f'http://127.0.0.1:{httpd.server_port}')
                    page.wait_for_function('window.GameThemes && configData')
                    page.evaluate('GameThemes.ready')
                    page.evaluate('async id=>{await loadGame(id)}',key)
                    page.locator('[data-panel-target=heavens]').click()
                    def nav(label):page.get_by_role('tab',name=label,exact=True).click()
                    def no_other_details():
                        assert page.locator('[data-mirror=field]').count()==0
                        assert page.locator('[data-ruins=field]').count()==0
                        assert page.locator('#heavens-content input').count()==0
                    assert page.locator('#heavens-body').get_attribute('data-heavens-view')=='home'
                    no_other_details()
                    before=engine.store._path(key).read_bytes()
                    page.get_by_role('button',name='查看旧石回声',exact=True).click()
                    assert '赤髓城' not in page.locator('#heavens-content').inner_text()
                    page.get_by_role('button',name='在当地对照征兆',exact=True).click()
                    page.locator('#game-confirm-backdrop:not(.hidden)').wait_for()
                    assert engine.store._path(key).read_bytes()==before
                    page.locator('#game-confirm-accept').click()
                    page.wait_for_function('!busy && game.heavens.next_command_seq===2')
                    after=engine.store.load(key)
                    assert after.player.age==game.player.age+2
                    assert after.player.opportunity==game.player.opportunity
                    assert after.heavens_state['runtime']['omens']['stone_resonance']['studied']
                    page.get_by_role('button',name='查看相关异象',exact=True).click()
                    assert page.locator('[data-ruins=field]').count()==1
                    assert page.get_by_role('button',name='进入因果遗址',exact=True).is_disabled()
                    nav('异象')
                    no_other_details()
                    assert page.locator('.heavens-destination').count()==2
                    nav('诸界')
                    assert page.get_by_label('选择界域',exact=True).locator('option').count()==11
                    assert page.locator('.heavens-destination').count()==1
                    assert page.locator('[data-heavens-action]').count()==0
                    # Only a newly selected target may publish its read-only projection.
                    held=[]
                    def delay_first(route):
                        if route.request.post_data_json.get('target_id')=='sea_echo' and not held:
                            held.append((route,route.fetch()))
                        else:route.continue_()
                    page.route('**/heavens-view',delay_first)
                    page.get_by_label('选择界域',exact=True).select_option('celestial')
                    page.get_by_role('button',name='查看法则天海 · 潮汐回响',exact=True).click()
                    page.wait_for_function("document.querySelector('#heavens-body').textContent.includes('正在读取')")
                    nav('诸界')
                    page.get_by_label('选择界域',exact=True).select_option('asura')
                    page.get_by_role('button',name='查看寂灭海 · 战律余响',exact=True).click()
                    page.wait_for_function("game.heavens.target_id==='asura_echo'")
                    assert held
                    held[0][0].fulfill(response=held[0][1])
                    page.wait_for_timeout(100)
                    assert page.evaluate('game.heavens.target_id')=='asura_echo'
                    assert page.locator('#heavens-body h3').inner_text()=='寂灭海 · 战律余响'
                    page.unroute('**/heavens-view',delay_first)
                    # Keyboard navigation switches real pages and moves focus with the tab.
                    page.locator('#heavens-primary-worlds').focus()
                    page.keyboard.press('ArrowRight')
                    assert page.locator('#heavens-primary-anomalies').evaluate('el=>el===document.activeElement')
                    assert page.locator('#heavens-body').get_attribute('data-heavens-view')=='anomalies'
                    assert engine.store.load(key).player.age==after.player.age
                    snapshot=engine.store._path(key).read_bytes()
                    for theme in 'abdf':
                        page.locator('#theme-open').click()
                        page.locator(f'[data-theme-picker=dialog] [data-theme-choice={theme}]').click()
                        page.evaluate('GameThemes.saved')
                        page.locator('[data-close-dialog=theme-dialog]').click()
                        for width in (1440,393):
                            page.set_viewport_size({'width':width,'height':1050 if width==1440 else 852})
                            for label,slug in [('见闻','home'),('诸界','worlds'),('异象','anomalies'),('行程','journey'),('战局','frontier')]:
                                nav(label)
                                no_other_details()
                                assert page.locator('#heavens-body').get_attribute('data-heavens-view')==slug
                                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                                assert page.locator('#heavens-content').evaluate('el=>el.scrollWidth<=el.clientWidth+1')
                                assert page.locator('#heavens-body').evaluate('el=>el.scrollWidth<=el.clientWidth+1')
                                assert page.locator('#heavens-card').evaluate('el=>el.scrollHeight<=el.clientHeight+1')
                                if width==393:
                                    card=page.locator('#heavens-card').bounding_box()
                                    dock=page.locator('.strategy-dock.settings-dock').bounding_box()
                                    assert card['y']+card['height']<=dock['y'], (theme,card,dock)
                                page.screenshot(path=str(output/f'{theme}-{width}-{slug}.png'))
                            nav('行程')
                            page.get_by_role('tab',name='纪要',exact=True).click()
                            assert page.locator('.heavens-timeline li').count()>0
                            assert page.locator('.heavens-timeline li').count()<=12
                            page.get_by_role('button',name='诸天偏好',exact=True).click()
                            assert page.locator('#heavens-content input').count()==3
                            assert page.locator('[data-heavens-action]').count()==0
                            assert page.locator('.heavens-primary [tabindex="0"]').count()==1
                        page.set_viewport_size({'width':1440,'height':1050})
                    assert engine.store._path(key).read_bytes()==snapshot
                    # A reloaded character returns to a relevant, uncluttered default.
                    page.reload()
                    page.wait_for_function('window.GameThemes && configData')
                    page.evaluate('async id=>{await loadGame(id)}',key)
                    page.locator('[data-panel-target=heavens]').click()
                    assert page.locator('#heavens-body').get_attribute('data-heavens-view')=='home'
                    page.get_by_role('button',name='查看旧石回声',exact=True).wait_for()
                    assert page.get_by_role('button',name='查看旧石回声',exact=True).count()==1
                    assert not errors,errors
                    (output/'report.json').write_text(json.dumps(dict(themes=6,widths=[1440,393],
                        separate_pages=True,keyboard_tabs=True,stale_target_response_ignored=True,
                        local_study=True,no_entry_bypass=True,navigation_read_only=True,
                        mobile_docks_unobstructed=True,errors=errors),indent=2),encoding='utf-8')
                    browser.close()
            finally:
                httpd.shutdown()
                httpd.server_close()
    print('Heavens navigation: four themes, distinct views, keyboard, stale response and local omen passed')


if __name__=='__main__':main()
