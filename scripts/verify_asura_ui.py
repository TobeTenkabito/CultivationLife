"""Exercise real Asura actions and responsive shared-theme rendering."""
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine


class Quiet(server.Handler):
    def log_message(self, *args):
        pass


def main():
    with tempfile.TemporaryDirectory() as directory:
        server.PERSISTENCE_ROOT = Path(directory)
        engine = server.ENGINE = GameEngine(ROOT, Path(directory) / 'saves')
        game = engine.store.load(engine.create_game('八部验收', 'supreme_metal', 'demonic', 720,
                                                   preset_id='asura_upper')['id'])
        game.player.asura_cultivation.update(conversion=5, body_level=20, souls=10000,
            route='garuda', level=9, domain_rank=8, domain_name='验收翼域')
        game.player.foreign_souls = [dict(id='ui-soul', name='旧魂', refined=True, realm_index=9, strength=1)]
        engine.store.save(game)
        httpd = ThreadingHTTPServer(('127.0.0.1', 0), Quiet)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        errors = []
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                page = browser.new_page(viewport={'width':1440,'height':1000})
                page.on('pageerror', lambda e: errors.append(str(e)))
                page.goto(f'http://127.0.0.1:{httpd.server_port}')
                page.wait_for_function('configData !== null')
                assert page.locator('[aria-label$="种属"]').count() >= 1
                page.evaluate('(id)=>loadGame(id)', game.id)
                # Open whichever shared utility panel owns the soul list.
                page.evaluate("UtilityPanels.open('captive')")
                page.get_by_role('button', name='提纯为精魂', exact=True).click()
                page.wait_for_function('game.asura.souls === 10090')
                page.evaluate("UtilityPanels.open('asura')")
                page.locator('#asura-cultivation').get_by_role('button', name='获取随机神通（100精魂）').click()
                page.wait_for_function('game.asura.powers?.length === 1')
                assert '当' in page.locator('#asura-cultivation').inner_text()
                for theme in 'abcdef':
                    page.evaluate('(t)=>document.querySelector(`[data-theme-picker=dialog] [data-theme-choice=${t}]`).click()', theme)
                    for width in (1440, 412):
                        page.set_viewport_size({'width':width,'height':1000})
                        page.evaluate("UtilityPanels.open('asura')")
                        assert page.locator('#asura-cultivation').evaluate('e=>e.scrollWidth <= e.clientWidth + 1')
                assert not errors, errors
                browser.close()
        finally:
            httpd.shutdown()
    print('Asura UI passed: purification, random power, six themes and mobile widths.')


if __name__ == '__main__':
    main()
