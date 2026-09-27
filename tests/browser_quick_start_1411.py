"""Regression of real quick starts, full rendering, actions and saved-game reload."""
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
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', root):
            httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(headless=True)
                    page = browser.new_page(viewport={'width':393,'height':873})
                    page.goto(f'http://127.0.0.1:{httpd.server_port}')
                    page.wait_for_function('window.GameThemes && configData')
                    page.evaluate('GameThemes.ready')
                    page.add_script_tag(path=str(ROOT/'tests/fixtures/quick_start_regression.js'))
                    for preset in ('demonic_void','core','void','ghost_void','monster_void','confucian_void','buddhist_void'):
                        result = page.evaluate('preset=>QuickStartProbe.run(preset)', preset)
                        assert engine.get_game(result['id'])['player']['world_age'] == result['age']
                        print(f'{preset}: create, render, advance and reload passed', flush=True)
                    assert not page.evaluate('QuickStartProbe.errors')
                    browser.close()
            finally:
                httpd.shutdown(); httpd.server_close()
    print('Quick-start regression passed: seven presets; demonic void in six themes')


if __name__ == '__main__':
    main()
