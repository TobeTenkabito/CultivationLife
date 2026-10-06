"""Confirm and cancel deletion through all six actual startup screens."""
import sys
import tempfile
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine


def main():
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        engine = GameEngine(ROOT, root / 'data/saves')
        ids = [engine.create_game(f'删除验收{i}', 'supreme_metal', 'dao', 1392+i)['id'] for i in range(7)]
        survivor = engine.store._path(ids[-1]).read_bytes()
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', root):
            httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(headless=True)
                    page = browser.new_page(viewport={'width':430, 'height':900})
                    errors=[]
                    page.on('pageerror', lambda e: errors.append(str(e)))
                    page.goto(f'http://127.0.0.1:{httpd.server_port}')
                    page.wait_for_function('configData && window.GameThemes')
                    page.evaluate('GameThemes.ready')
                    assert page.locator('.save-entry').count() == 7
                    for theme, gid in zip('abdf', ids):
                        page.locator(f'[data-theme-picker=start] [data-theme-choice={theme}]').click()
                        row = page.locator(f'[data-save-id="{gid}"]')
                        row.locator('.save-delete').click()
                        assert '删除验收' in page.locator('#game-confirm-body').inner_text()
                        page.locator('#game-confirm-cancel').click()
                        assert engine.store._path(gid).exists()
                        row.locator('.save-delete').click()
                        page.locator('#game-confirm-accept').click()
                        row.wait_for(state='detached')
                        assert not engine.store._path(gid).exists()
                    assert engine.store._path(ids[-1]).read_bytes() == survivor
                    page.locator('.save-entry button').first.click()
                    page.wait_for_function('game && !busy')
                    page.evaluate('showStart()')
                    assert page.locator('.save-entry').count() == 1
                    assert not errors, errors
                    browser.close()
            finally:
                httpd.shutdown(); httpd.server_close()
    print('Six-theme save deletion, cancellation, full list and surviving save checks passed')


if __name__ == '__main__': main()
