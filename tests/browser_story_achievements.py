"""Real member join, commission preview/submission and achievement catalog UI."""
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
from cultivation_life.rules import add_item
from scripts.browser_navigation import navigation_locator, click_control


class Quiet(server.Handler):
    def log_message(self, *args):
        pass


def main():
    output = ROOT / 'build' / 'story-achievement-ui'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        engine = GameEngine(ROOT, Path(directory) / 'saves')
        identity = engine.create_game('本盟委托验收', 'supreme_fire', 'dao', 354, preset_id='core')['id']
        game = engine._load(identity)
        alliance = game.merchant_state['worlds']['human'][0]
        game.player.location_id = alliance['hq']
        add_item(game.player, 'spirit_stone', 10**8)
        engine.store.save(game)
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', Path(directory)):
            httpd = ThreadingHTTPServer(('127.0.0.1', 0), Quiet)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    page = browser.new_page(viewport={'width': 412, 'height': 915})
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.goto(f'http://127.0.0.1:{httpd.server_port}')
                    page.wait_for_function('!!configData')
                    page.evaluate('async id=>loadGame(id)', identity)
                    navigation_locator(page, '[data-panel-target="merchant"]').click()
                    panel = page.locator('.merchant-alliance').first
                    click_control(panel.get_by_role('button', name='加入商盟', exact=True))
                    page.wait_for_function('!busy && !!game.merchant_system.membership')
                    click_control(panel.get_by_text('发布委托', exact=True))
                    form = panel.locator('form')
                    form.get_by_label('委托类型', exact=True).select_option('weapon')
                    submit = form.get_by_role('button', name='支付并发布委托')
                    page.wait_for_function("!document.querySelector('.merchant-post button[type=submit]').disabled")
                    assert 'merchant_post_to_own_alliance' not in engine.achievements.metadata.read()['achievements']
                    with page.expect_response(lambda response: '/merchant' in response.url
                                              and response.request.method == 'POST') as pending:
                        submit.click()
                    result = pending.value.json()
                    assert '黑钱洗白' in {row['name'] for row in result['new_achievements']}
                    page.wait_for_function('!busy && game.merchant_system.posted.length===1')
                    page.locator('#achievement-toast-name').get_by_text('黑钱洗白', exact=True).wait_for()
                    saved = engine.store.load(identity)
                    assert saved.player.milestones['posted_to_own_alliance'] == 1
                    assert saved.merchant_state['posted'][0]['status'] == 'open'
                    page.evaluate('async id=>loadGame(id)', identity)
                    page.wait_for_function('!busy')
                    assert not page.evaluate('game.new_achievements.some(row=>row.name==="黑钱洗白")')
                    page.evaluate("UtilityPanels.close('merchant');showStart()")
                    page.locator('#achievement-open').click()
                    names = ('先帝还在创业', '教父', '满门忠烈', '黑钱洗白',
                             '天下布武', '一个能打的都没有', '钞能力', '我徒弟有大帝之姿', '替身使者',
                             '死了，但没完全死', '这不是我最后一条命', '账号找回成功', '衣锦还乡',
                             '田氏代齐', '我养你啊', '铁打的弟子，流水的掌门', '谢谢老板')
                    dlc_names=('我抄我自己','祖宗之法不可变')
                    for theme in 'abdf':
                        page.evaluate('t=>document.querySelector(`[data-theme-picker=dialog] [data-theme-choice="${t}"]`).click()', theme)
                        page.evaluate('GameThemes.saved')
                        for width, height in ((1440, 1000), (412, 915), (915, 412)):
                            page.set_viewport_size({'width': width, 'height': height})
                            for name in (*names,*dlc_names):
                                page.locator('#achievement-groups b').get_by_text(name, exact=True).wait_for()
                            assert page.locator('#achievement-screen').evaluate('e=>e.scrollWidth<=e.clientWidth+2')
                            page.locator('.achievement-row').filter(has=page.get_by_text('田氏代齐', exact=True)).scroll_into_view_if_needed()
                            page.screenshot(path=str(output / f'{theme}-{width}.png'), animations='disabled')
                    catalog = page.evaluate('achievementCatalog.achievements')
                    selected = [row for row in catalog if row['name'] in names]
                    assert len(selected) == len(names) and all(row['source']['kind'] == 'base' for row in selected)
                    assert all(next(r for r in catalog if r['name']==name)['source']['id']=='official.authored-techniques' for name in dlc_names)
                    assert '不使用更名资格' in next(r for r in catalog if r['name']=='田氏代齐')['description']
                    assert next(row for row in selected if row['name'] == '黑钱洗白')['unlocked']
                    assert '外姓成员不计' in next(row for row in selected if row['name'] == '满门忠烈')['description']
                    assert not errors, errors
                    browser.close()
            finally:
                httpd.shutdown()
                httpd.server_close()
    print('Story achievements UI passed: real join/preview/post, persistent unlock, no repeat, four themes x three viewports')


if __name__ == '__main__':
    main()
