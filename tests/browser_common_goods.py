"""Real fixed core, original forge and talisman UI, paid entry and stale recovery."""
import json
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from fixtures.common_goods_release import prepare_common_goods, common_goods_wallet, inspect_common_goods
from scripts.browser_navigation import navigation_locator, click_control


def main():
    output = ROOT/'build/common-goods-browser'
    output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='common-goods-ui-') as folder:
        engine = GameEngine(ROOT,Path(folder)/'saves')
        class Handler(server.Handler):
            def log_message(self,*args): pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            http = ThreadingHTTPServer(('127.0.0.1',0),Handler)
            threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(args=['--disable-gpu','--renderer-process-limit=1'])
                    try:
                        for theme in ('a','b','d','f'):
                            for width,height in [(1440,960),(393,852),(852,393)]:
                                identity = engine.create_game('商品界面验收','supreme_metal','dao',2151,preset_id='nascent')['id']
                                prepare_common_goods(engine,identity)
                                page = browser.new_page(viewport=dict(width=width,height=height),reduced_motion='reduce')
                                errors=[]
                                page.on('pageerror',lambda e:errors.append(str(e)))
                                page.goto(f'http://127.0.0.1:{http.server_port}')
                                page.wait_for_function('!!configData')
                                page.evaluate('async id=>loadGame(id)',identity)
                                page.evaluate('t=>document.documentElement.dataset.theme=t',theme)
                                navigation_locator(page,'[data-panel-target=auction]').click()
                                assert '高级' in page.locator('#auction-title').inner_text()
                                assert '500' in page.locator('#auction-description').inner_text()
                                assert not page.locator('#auction-lots-section').is_visible()
                                common_goods_wallet(engine,identity,499)
                                with page.expect_response(lambda r:r.url.endswith('/auction-identity')) as rejected:
                                    click_control(page.locator('#auction-identities button').first)
                                assert rejected.value.status == 400
                                page.wait_for_function('!busy && game.auction_system.spirit_stones===499')
                                assert all(b.is_disabled() for b in page.locator('#auction-identities button').all())
                                common_goods_wallet(engine,identity,100000)
                                page.evaluate('async id=>loadGame(id)',identity)
                                click_control(page.locator('#auction-identities button').first)
                                page.wait_for_function('!busy && game.auction_system.entry_paid')
                                assert page.evaluate('game.auction_system.spirit_stones') == 99500
                                click_control(page.locator('#auction-identities button').nth(1))
                                page.wait_for_function('!busy')
                                assert page.evaluate('game.auction_system.spirit_stones') == 99500
                                page.screenshot(path=str(output/f'auction-{theme}-{width}.png'))
                                click_control(page.locator('#auction-toggle'))
                                navigation_locator(page,'[data-panel-target=inventory]').click()
                                hp_before = page.evaluate('game.player.hp')
                                core = page.locator('#inventory-list .item').filter(has_text='赤兽血丹')
                                click_control(core.locator('.item-use'))
                                page.wait_for_function("!busy && !game.player.inventory.some(i=>i.id==='econ_human_4_core_blood')")
                                assert page.evaluate('game.player.hp') == hp_before+400
                                talisman = page.locator('#inventory-list .item').filter(has_text='护身符')
                                click_control(talisman.get_by_role('button',name='收入符箓'))
                                page.wait_for_function('!busy && game.talismans.rows.length>0')
                                click_control(page.locator('#inventory-toggle'))
                                navigation_locator(page,'[data-panel-target=talisman]').click()
                                click_control(page.locator('#talisman-content').get_by_role('button',name='启用',exact=True))
                                page.wait_for_function('!busy && game.talismans.rows.some(r=>r.enabled)')
                                page.screenshot(path=str(output/f'talisman-{theme}-{width}.png'))
                                click_control(page.locator('#talisman-toggle'))
                                navigation_locator(page,'[data-panel-target=crafting]').click()
                                for selector,value in [('mold','sword'),('primary','common:econ_human_4_ore_structure:0'),
                                    ('secondary-a','common:econ_human_4_ore_conduct:0'),('secondary-b','common:econ_human_4_ore_conduct:1'),
                                    ('quench','common:econ_human_4_ore_store:0')]:
                                    page.locator('#crafting-'+selector).select_option(value)
                                for field in page.locator('#crafting-allocations input').all(): field.fill('0')
                                page.locator('#crafting-allocations input[data-stat=combat_power]').fill('10')
                                page.locator('#crafting-name').fill('通用矿材验收')
                                click_control(page.locator('#crafting-preview'))
                                page.wait_for_function("!busy && document.querySelector('#crafting-preview-result button')")
                                page.screenshot(path=str(output/f'forge-{theme}-{width}.png'))
                                click_control(page.get_by_role('button',name='确认开炉',exact=True))
                                click_control(page.get_by_role('button',name='开炉炼器',exact=True))
                                page.wait_for_function("!busy && game.crafting_system.artifacts.some(a=>a.name==='通用矿材验收')")
                                inspect_common_goods(engine,identity)
                                assert page.locator('#crafting-card').evaluate('e=>e.scrollWidth<=e.clientWidth+2')
                                page.evaluate("TutorialGuide.showChapter('auction-classes')")
                                assert '固定' in page.locator('#tutorial-handbook [data-chapter=auction-classes][open]').inner_text()
                                assert not errors,errors
                                page.close()
                    finally: browser.close()
            finally:
                http.shutdown()
                http.server_close()
    (output/'result.json').write_text(json.dumps(dict(passed=True,themes=4,layouts=3,
        checks=['fixed-current-hp','real-unpack-toggle','four-real-ore-units','weak-forge','paid-entry-once',
                'stale-funds-reject-refresh','insufficient-buttons-disabled','busy-cleared','encyclopedia','no-overflow'])),encoding='utf-8')
    print('Common goods browser passed: four themes, desktop/portrait/landscape, real actions and stale recovery')


if __name__ == '__main__': main()
