"""Real commission execution and shared button styles, desktop and narrow screen."""
import random
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright
from cultivation_life import server as server_module
from cultivation_life.engine import GameEngine
from cultivation_life.rules import add_item


def main():
    with tempfile.TemporaryDirectory() as directory:
        engine = GameEngine(ROOT, Path(directory))
        game_id = engine.create_game('商路进度验收', 'heavenly', 'dao', 1371, preset_id='core')['id']
        game = engine._load(game_id)
        alliance = game.merchant_state['worlds']['human'][0]
        game.player.location_id = alliance['hq']
        add_item(game.player, 'spirit_stone', 10**9)
        engine.store.save(game)
        engine.merchant_action(game_id, 'join', {'alliance_id':alliance['id']})
        game = engine._load(game_id)
        for stars in (3, 5):
            engine._merchant_post(game, alliance, {'kind':'intel', 'stars':stars})
            order = game.merchant_state['posted'][-1]
            engine._merchant_start_order(game, order, random.Random(stars))
            order.update(will_finish=stars == 3, failure_age=game.player.age + 4)
        game.player.age += 5
        engine._advance_merchant_year(game)
        engine.store.save(game)
        with patch.object(server_module, 'ENGINE', engine):
            httpd = ThreadingHTTPServer(('127.0.0.1', 0), server_module.Handler)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(headless=True)
                    page = browser.new_page(viewport={'width':1440, 'height':1050})
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.goto(f'http://127.0.0.1:{httpd.server_port}')
                    page.wait_for_function('!!configData')
                    page.evaluate('async id=>{await loadGame(id);render(game);}', game_id)
                    page.locator('[data-panel-target="merchant"]').click()
                    failed = page.locator('.merchant-order[data-status="failed"]')
                    working = page.locator('.merchant-order[data-status="working"]')
                    assert failed.count() == working.count() == 1
                    failed.locator('.merchant-refund').wait_for(state='visible')
                    assert '已退本金' in failed.text_content() and '手续费' in failed.text_content()
                    assert failed.locator('.merchant-progress-log p').count() >= 3
                    assert working.locator('progress').evaluate('e=>e.value>0 && e.value<1')
                    assert '失败风险' in working.inner_text() and '预计第' in working.inner_text()
                    failed.scroll_into_view_if_needed()
                    page.screenshot(path=str(ROOT/'build/merchant-137-execution-desktop.png'))
                    page.set_viewport_size({'width':430,'height':900})
                    failed.scroll_into_view_if_needed()
                    page.screenshot(path=str(ROOT/'build/merchant-137-execution-mobile.png'))
                    assert page.locator('#merchant-card').evaluate('e=>e.scrollWidth<=e.clientWidth+2')
                    page.set_viewport_size({'width':1440, 'height':1050})
                    # The same base treatment must reach temporary buttons added after render.
                    appearance = page.evaluate('''() => {
                      const b=document.createElement('button');b.textContent='临时操作';document.body.append(b);
                      b.focus();const c=getComputedStyle(b);
                      const result={bg:c.backgroundImage,fg:c.color,radius:c.borderRadius,focus:c.outlineStyle};
                      b.disabled=true;result.disabled=getComputedStyle(b).opacity;b.remove();return result;
                    }''')
                    assert 'gradient' in appearance['bg'] and appearance['radius']=='5px'
                    assert appearance['fg'] != 'rgb(0, 0, 0)' and float(appearance['disabled']) < 1
                    # Open representative systems that generate temporary buttons.
                    for panel in ('crafting', 'formation', 'natal-artifact', 'map', 'auction'):
                        dock = page.locator(f'[data-panel-target="{panel}"]')
                        if not dock.count() or not dock.is_visible():
                            continue
                        dock.click()
                        card = page.locator(f'#{panel}-card.panel-open')
                        card.wait_for(state='visible')
                        assert card.evaluate('e=>e.scrollWidth<=e.clientWidth+2')
                        assert card.locator('button').count()
                        page.screenshot(path=str(ROOT/f'build/buttons-137-{panel}.png'), animations='disabled')
                    assert not errors, errors
                    browser.close()
            finally:
                httpd.shutdown()
                httpd.server_close()
    print('Merchant 1.37 execution and button browser acceptance passed')


if __name__ == '__main__':
    main()
