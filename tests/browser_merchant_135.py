"""Isolated browser acceptance for merchant membership, work and commissions."""
import random
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright
from cultivation_life import server as server_module
from cultivation_life.engine import GameEngine
from cultivation_life.rules import add_item
from cultivation_life.system.crafting_system import make_crafting_material_instance


def main():
    with tempfile.TemporaryDirectory() as directory:
        engine = GameEngine(ROOT, Path(directory))
        game_id = engine.create_game('商盟验收', 'heavenly', 'dao', 1351, preset_id='core')['id']
        game = engine._load(game_id)
        alliance = game.merchant_state['worlds']['human'][0]
        game.player.location_id = alliance['offices'][0]['location_id']
        game.player.next_tribulation_age = None
        add_item(game.player, 'spirit_stone', 1000000)
        task = next(row for row in engine._merchant_board(game, alliance) if row['kind'] == 'supply')
        game.player.crafting_materials.append(make_crafting_material_instance(engine._crafting_material_defs()[task['definition_id']], random.Random(1), source='test', origin_world='human'))
        engine.store.save(game)
        server_module.ENGINE = engine
        httpd = ThreadingHTTPServer(('127.0.0.1', 0), server_module.Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        errors = []
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(viewport={'width':1440, 'height':1050})
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(f'http://127.0.0.1:{httpd.server_port}')
                page.evaluate('async id => { await loadGame(id); render(game); }', game_id)
                page.locator('[data-panel-target="merchant"]').click()
                assert page.locator('.merchant-alliance').count() == 3
                page.locator('.merchant-alliance').first.get_by_role('button', name='加入商盟', exact=True).click()
                page.wait_for_function('!!game.merchant_system.membership')
                assert '分部 成员' in page.locator('.merchant-membership').text_content()
                page.locator('.merchant-task').first.get_by_role('button', name='接取', exact=True).click()
                page.wait_for_function('!!game.merchant_system.active')
                page.get_by_role('button',name='执行 / 继续任务',exact=True).click()
                page.wait_for_function('!game.merchant_system.active')
                assert engine._load(game_id).merchant_state['influence']
                panel = page.locator('.merchant-alliance').first
                panel.get_by_text('发布委托',exact=True).click()
                form = panel.locator('form')
                form.get_by_label('委托类型',exact=True).select_option('intel')
                form.get_by_role('button',name='支付并发布委托').click()
                page.wait_for_function('game.merchant_system.posted.length===1')
                assert '等待接取' in page.locator('.merchant-order').text_content()
                game = engine._load(game_id)
                order = game.merchant_state['posted'][0]
                order.update(status='working',started_age=game.player.age-1,finish_age=game.player.age+2,worker='商路行者',will_finish=True)
                engine.store.save(game)
                page.evaluate('async id => { await loadGame(id); render(game); }', game_id)
                assert page.locator('.merchant-order progress').count() == 1
                assert '预计第' in page.locator('.merchant-order').text_content()
                page.screenshot(path=str(ROOT / 'build/merchant-135-desktop.png'))
                page.set_viewport_size({'width':430,'height':900})
                page.screenshot(path=str(ROOT / 'build/merchant-135-mobile.png'))
                assert page.locator('#merchant-card').evaluate('e => e.scrollWidth <= e.clientWidth + 2')
                assert not errors, errors
                browser.close()
        finally:
            httpd.shutdown()
    print('Merchant 1.35 browser checks passed')


if __name__ == '__main__':
    main()
