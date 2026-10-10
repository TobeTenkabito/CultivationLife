"""Real HTTP mirror route: all solutions, four themes, retry and persistent revisit."""
import copy
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


from scripts.browser_navigation import navigation_locator

def main():
    output = ROOT/'build/heavens-mirror-browser'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        engine = GameEngine(ROOT, root/'saves')
        key = engine.create_game('镜中客', 'supreme_metal', 'dao', 4242, preset_id='core')['id']
        game = engine.store.load(key)
        p = game.player
        p.world, p.location_id, p.realm_index = 'human', 'muling_desert', 4
        p.lifespan, p.next_tribulation_age = None, 999999
        p.hp, p.mp = max_hp(p), max_mp(p)
        p.formation_materials.append(dict(id='browser-cut', material_id='human_quiet_soul_mirror', name='寂识镜片', acquired_tier=4))
        game.settings['silent_events'] = True
        engine.store.save(game)
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', root):
            httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(headless=True)
                    page = browser.new_page(viewport={'width':1440, 'height':1050})
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.goto(f'http://127.0.0.1:{httpd.server_port}')
                    page.wait_for_function('window.GameThemes && configData')
                    page.evaluate('GameThemes.ready')
                    page.evaluate('async id=>{await loadGame(id)}', key)
                    navigation_locator(page,'[data-panel-target=heavens]').click()
                    page.get_by_role('tab',name='异象',exact=True).click()
                    page.get_by_role('button',name='查看镜律场域',exact=True).click()
                    def propose(label, chamber=None):
                        if chamber is not None:
                            page.locator(f'#heavens-chamber-{chamber}').click()
                        area = page.locator('[data-mirror=field]') if chamber is None else page.locator(f'[data-mirror-chamber="{chamber}"]')
                        before = engine.store._path(key).read_bytes()
                        area.get_by_role('button', name=label, exact=True).click()
                        page.locator('#game-confirm-backdrop:not(.hidden)').wait_for()
                        assert engine.store._path(key).read_bytes() == before
                    def commit():
                        seq = engine.store.load(key).heavens_state['command_seq']+2
                        page.locator('#game-confirm-accept').click()
                        page.wait_for_function('seq=>!busy && game.heavens.next_command_seq===seq', arg=seq)
                    propose('进入镜律场域')
                    assert '保留退路' in page.locator('#game-confirm-body').inner_text()
                    commit()
                    assert engine.store.load(key).player.world == 'rift'
                    navigation_locator(page,'[data-panel-target=map]').click()
                    page.get_by_role('button',name='查看诸天机关与返程',exact=True).wait_for()
                    assert '诸天面板' in page.locator('#spatial-panel').inner_text()
                    assert page.locator('#spatial-panel').get_by_role('button',name='探索 · 一年').count() == 0
                    page.get_by_role('button',name='查看诸天机关与返程',exact=True).click()
                    propose('低耗试探')
                    def lose_response(route):
                        route.fetch()
                        route.abort()
                    page.route('**/heavens-command', lose_response, times=1)
                    page.locator('#game-confirm-accept').click()
                    retry = page.get_by_role('button',name='重试上次提交（不会重复扣费）',exact=True)
                    retry.wait_for()
                    first = engine.store.load(key)
                    age, mana = first.player.age, first.player.mp
                    collected = first.heavens_state['runtime']['mirror']['collected_mana']
                    retry.click()
                    page.wait_for_function('!busy && game.heavens.next_command_seq===3')
                    after = engine.store.load(key)
                    assert (after.player.age, after.player.mp) == (age, mana)
                    assert after.heavens_state['runtime']['mirror']['collected_mana'] == collected
                    propose('材料隔断', 0)
                    assert '开始施工即消耗' in page.locator('#game-confirm-body').inner_text()
                    commit()
                    propose('低耗破解', 0)
                    commit()
                    assert engine.store.load(key).heavens_state['runtime']['mirror']['collected_mana'] == collected
                    propose('强攻机关', 1)
                    assert '可能负伤或死亡' in page.locator('#game-confirm-body').inner_text()
                    commit()
                    assert engine.store.load(key).last_combat_report['result'] == 'victory'
                    page.locator('#battle-report-card button').filter(has_text='关闭').click()
                    propose('低耗破解', 2)
                    commit()
                    saved = engine.store.load(key)
                    assert saved.heavens_state['runtime']['mirror']['record_acquired']
                    assert len(saved.player.formation_materials) == 2
                    snapshot = copy.deepcopy(saved.heavens_state['runtime']['mirror'])
                    for theme in 'abdf':
                        page.locator('#theme-open').click()
                        page.locator(f'[data-theme-picker=dialog] [data-theme-choice={theme}]').click()
                        page.evaluate('GameThemes.saved')
                        page.locator('[data-close-dialog=theme-dialog]').click()
                        for width in (1440,393):
                            page.set_viewport_size({'width':width, 'height':1050 if width==1440 else 852})
                            page.locator('[data-mirror=field] h3').scroll_into_view_if_needed()
                            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'), (theme,width)
                            assert page.locator('#heavens-content').evaluate('(el)=>el.scrollWidth<=el.clientWidth+1'), (theme,width)
                            page.screenshot(path=str(output/f'{theme}-{width}.png'))
                        page.set_viewport_size({'width':1440,'height':1050})
                    propose('沿原路退出')
                    commit()
                    assert engine.store.load(key).player.location_id == 'muling_desert'
                    propose('进入镜律场域')
                    commit()
                    final = engine.store.load(key)
                    assert final.heavens_state['runtime']['mirror'] == snapshot
                    assert len(final.player.formation_materials) == 2
                    assert not errors, errors
                    (output/'report.json').write_text(json.dumps(dict(themes=6, widths=[1440,393],
                        all_solutions=True, pure_previews=True, lost_response_retry=True,
                        duplicate_costs=0, stable_revisit=True, materials=2, record=True, errors=errors),indent=2),encoding='utf-8')
                    browser.close()
            finally:
                httpd.shutdown()
                httpd.server_close()
    print('Mirror browser: solutions, retry, revisit and four themes passed')


if __name__ == '__main__':
    main()
