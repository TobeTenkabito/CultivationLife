"""Real bulk exchanges and responsive shop controls in all six themes."""
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.system.immortal_system import item_quantity
from cultivation_life.system.yaochi_system import config


class Quiet(server.Handler):
    def log_message(self, *args):
        pass


def main():
    with tempfile.TemporaryDirectory(dir=ROOT / 'build') as directory:
        server.PERSISTENCE_ROOT = Path(directory)
        e = server.ENGINE = GameEngine(ROOT, Path(directory) / 'saves')
        made = e.create_game('批量兑换验收', 'supreme_metal', 'dao', seed=1520, preset_id='true_immortal')
        g = e._load(made['id'])
        g.pending_event = None
        g.heavenly_court['open_election'] = None
        g.player.location_id = config()['location_id']
        g.yaochi_state['merit'] = 100000
        e.store.save(g)
        httpd = ThreadingHTTPServer(('127.0.0.1', 0), Quiet)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        errors = []
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                page = browser.new_page()
                page.emulate_media(reduced_motion='reduce')
                page.route('**/merchant-preview', lambda route: route.fulfill(
                    status=400, content_type='application/json', body='{"error":"Isolated shop test"}'))
                page.on('pageerror', lambda err: errors.append(str(err)))
                page.goto(f'http://127.0.0.1:{httpd.server_port}')
                page.wait_for_function('configData!==null')
                page.evaluate('(id)=>loadGame(id)', g.id)
                offer = page.evaluate("game.yaochi.shop.find(o=>o.kind==='item'&&o.quantity>1)")
                row = page.locator(f'[data-offer-id="{offer["id"]}"]')
                quantity = row.get_by_role('spinbutton')
                buy = row.get_by_role('button', name='兑换', exact=True)
                for theme in 'abcdef':
                    page.evaluate('(t)=>document.querySelector(`[data-theme-picker=dialog] [data-theme-choice=${t}]`).click()', theme)
                    page.evaluate('GameThemes.saved')
                    page.evaluate("UtilityPanels.open('yaochi')")
                    for width, height in [(1440, 1080), (412, 915), (915, 412)]:
                        page.set_viewport_size(dict(width=width, height=height))
                        for value in ['', '0', '1.5', '1000001']:
                            quantity.fill(value)
                            assert buy.is_disabled(), (theme, value)
                        quantity.fill('7')
                        assert not buy.is_disabled()
                        assert row.locator('.yaochi-purchase-total').inner_text() == (
                            f"所得 ×{offer['quantity'] * 7:,} · 合计 {offer['price'] * 7:,} 功勋")
                        assert page.locator('#yaochi-card').evaluate('e=>e.scrollWidth<=e.clientWidth+1'), (theme, width)
                        assert row.evaluate('e=>e.scrollWidth<=e.clientWidth+1'), (theme, width)
                        quantity.scroll_into_view_if_needed()
                        if width == 412:
                            page.screenshot(path=str(ROOT / f'build/yaochi-bulk-{theme}.png'))
                    before = e._load(g.id)
                    balance = before.yaochi_state['merit']
                    count = item_quantity(before.player, offer['id'])
                    buy.click()
                    page.wait_for_function('(balance)=>!busy&&game.yaochi.merit===balance', arg=balance - 7 * offer['price'])
                    saved = e._load(g.id)
                    assert item_quantity(saved.player, offer['id']) == count + 7 * offer['quantity']
                    assert quantity.input_value() == '1'
                body = page.evaluate("game.yaochi.shop.find(o=>o.kind==='body_manual').id")
                assert page.locator(f'[data-offer-id="{body}"] input').is_disabled()
                assert not errors, errors
                browser.close()
        finally:
            httpd.shutdown()
    print('Bulk shop UI passed: six themes, three viewports, invalid quantities, totals and persisted purchases')


if __name__ == '__main__':
    main()
