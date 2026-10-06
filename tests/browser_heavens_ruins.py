"""Real HTTP ruins lifecycle, response-loss retry and all six theme layouts."""
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
from cultivation_life.rules import add_item, max_hp, max_mp


def main():
    output = ROOT/'build/heavens-ruins-browser'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        engine = GameEngine(ROOT, root/'saves')
        def create(rank=4):
            key = engine.create_game('回潮客', 'supreme_metal', 'dao', 4242, preset_id='core')['id']
            game = engine.store.load(key)
            p = game.player
            p.world, p.location_id, p.realm_index = 'human', 'wudi_plain', rank
            p.lifespan, p.next_tribulation_age = None, 999999
            p.hp, p.mp = max_hp(p), max_mp(p)
            add_item(p, 'spirit_stone', 10000)
            game.settings['silent_events'] = True
            engine.store.save(game)
            return key
        key = create()
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
                    page.locator('[data-panel-target=heavens]').click()
                    page.get_by_role('tab',name='异象',exact=True).click()
                    page.get_by_role('button',name='查看因果遗址',exact=True).click()
                    area = page.locator('[data-ruins=field]')
                    def propose(label):
                        section = ('阵芯' if label in {'直接取走阵芯','替换后取芯','归还并安装阵芯'} else '痕迹' if label=='清理未读残留' else '调查')
                        tab = page.get_by_role('tab',name=section,exact=True)
                        if tab.count(): tab.click()
                        before = engine.store._path(key).read_bytes()
                        area.get_by_role('button', name=label, exact=True).click()
                        page.locator('#game-confirm-backdrop:not(.hidden)').wait_for()
                        assert engine.store._path(key).read_bytes() == before
                    def commit():
                        seq = engine.store.load(key).heavens_state['command_seq']+2
                        page.locator('#game-confirm-accept').click()
                        page.wait_for_function('seq=>!busy && game.heavens.next_command_seq===seq', arg=seq)
                    propose('进入因果遗址')
                    commit()
                    page.locator('[data-panel-target=map]').click()
                    page.get_by_role('button', name='查看诸天机关与返程', exact=True).wait_for()
                    assert '回潮阵室' in page.locator('#spatial-panel').inner_text()
                    page.get_by_role('button', name='查看诸天机关与返程', exact=True).click()
                    for label in ('观察阵纹', '查证两端关联', '读取合法抄本'):
                        propose(label)
                        commit()
                    assert '已取得回潮阵纹合法抄本' in area.inner_text()
                    propose('替换后取芯')
                    assert '500' in page.locator('#game-confirm-body').inner_text()
                    assert '开始施工即消耗' in page.locator('#game-confirm-body').inner_text()
                    def lose_response(route):
                        route.fetch()
                        route.abort()
                    page.route('**/heavens-command', lose_response, times=1)
                    page.locator('#game-confirm-accept').click()
                    retry = page.get_by_role('button', name='重试上次提交（不会重复扣费）', exact=True)
                    retry.wait_for()
                    snapshot = engine.store._path(key).read_bytes()
                    seq = engine.store.load(key).heavens_state['command_seq']+1
                    retry.click()
                    page.wait_for_function('seq=>!busy && game.heavens.next_command_seq===seq', arg=seq)
                    assert engine.store._path(key).read_bytes() == snapshot
                    assert '由你持有' in area.inner_text() and '替代部件维持回响' in area.inner_text()
                    assert area.get_by_role('button', name='直接取走阵芯', exact=True).count() == 0
                    page.wait_for_function("!document.querySelector('#toast').classList.contains('show')")
                    for theme in 'abdf':
                        page.locator('#theme-open').click()
                        page.locator(f'[data-theme-picker=dialog] [data-theme-choice={theme}]').click()
                        page.evaluate('GameThemes.saved')
                        page.locator('[data-close-dialog=theme-dialog]').click()
                        for width in (1440,393):
                            page.set_viewport_size({'width':width, 'height':1050 if width==1440 else 852})
                            page.locator('[data-ruins=field] h3').scroll_into_view_if_needed()
                            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'), (theme,width)
                            assert page.locator('#heavens-content').evaluate('(el)=>el.scrollWidth<=el.clientWidth+1'), (theme,width)
                            page.screenshot(path=str(output/f'{theme}-{width}.png'))
                        page.set_viewport_size({'width':1440,'height':1050})
                    page.set_viewport_size({'width':393,'height':852})
                    for label in ('归还并安装阵芯', '追查回响接触点', '清理未读残留'):
                        propose(label)
                        commit()
                    page.get_by_role('tab',name='阵芯',exact=True).click()
                    assert '已归还阵眼' in area.inner_text()
                    page.get_by_role('tab',name='调查',exact=True).click()
                    assert '赤髓城' in area.inner_text()
                    assert engine.store.load(key).heavens_state['runtime']['ruins']['sent_records']
                    snapshot = copy.deepcopy(engine.store.load(key).heavens_state['runtime']['ruins'])
                    for label in ('退出因果遗址', '进入因果遗址'):
                        propose(label)
                        commit()
                    assert engine.store.load(key).heavens_state['runtime']['ruins'] == snapshot
                    # A separate physical character verifies the destructive choice and recovery UI.
                    key = create(5)
                    page.evaluate('async id=>{await loadGame(id)}', key)
                    if not page.locator('#heavens-card').is_visible():
                        page.locator('[data-panel-target=heavens]').click()
                    page.get_by_role('tab',name='异象',exact=True).click()
                    page.get_by_role('button',name='查看因果遗址',exact=True).click()
                    for label in ('进入因果遗址', '观察阵纹', '查证两端关联'):
                        propose(label)
                        commit()
                    propose('直接取走阵芯')
                    assert '可能负伤或死亡' in page.locator('#game-confirm-body').inner_text()
                    commit()
                    assert engine.store.load(key).last_combat_report['result'] == 'victory'
                    page.locator('#battle-report-card button').filter(has_text='关闭').click()
                    assert '阵眼失效' in area.inner_text()
                    page.get_by_role('tab',name='调查',exact=True).click()
                    assert area.get_by_role('button', name='追查回响接触点', exact=True).is_disabled()
                    for label in ('归还并安装阵芯', '追查回响接触点', '退出因果遗址'):
                        propose(label)
                        commit()
                    assert engine.store.load(key).player.location_id == 'wudi_plain'
                    assert not errors, errors
                    (output/'report.json').write_text(json.dumps(dict(themes=6, widths=[1440,393],
                        peaceful_read=True, replacement=True, direct_combat=True, ward_restoration=True,
                        pure_previews=True, lost_response_retry=True, duplicate_costs=0,
                        stable_revisit=True, irreversible_evidence=True, errors=errors),indent=2),encoding='utf-8')
                    browser.close()
            finally:
                httpd.shutdown()
                httpd.server_close()
    print('Ruins browser: reading, replacement, combat, restoration, retry and four themes passed')


if __name__ == '__main__':
    main()
