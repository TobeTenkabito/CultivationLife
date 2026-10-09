"""Real custom-start submission around the immortal conversion boundary."""
import sys, tempfile, threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine

def main():
    with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
        engine = GameEngine(ROOT, Path(folder)/'saves')
        class Quiet(server.Handler):
            def log_message(self, *args): pass
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', Path(folder)):
            httpd = ThreadingHTTPServer(('127.0.0.1', 0), Quiet)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    for theme in 'abdf':
                        for width,height in ((1440,1000),(412,915),(915,412)):
                            for realm,world in ((8,'spirit'),(9,'celestial')):
                                page=browser.new_page(viewport=dict(width=width,height=height))
                                errors=[]
                                page.on('pageerror',lambda error:errors.append(str(error)))
                                page.goto(f'http://127.0.0.1:{httpd.server_port}')
                                page.locator(f'[data-theme-picker=start] [data-theme-choice={theme}]').click()
                                page.locator('#custom-start > summary').click()
                                page.locator('#custom-root').select_option('otherworld')
                                page.locator('#custom-path').select_option('dao')
                                page.locator('#custom-world').select_option(world)
                                page.locator('#custom-realm').select_option(str(realm))
                                page.locator('#custom-start-submit').click()
                                page.wait_for_function('game && !busy')
                                gid=page.evaluate('game.id')
                                raw=engine.store.load(gid)
                                assert raw.player.realm_index==realm and raw.player.world==world
                                assert raw.player.immortal_power_converted==(realm>=9)
                                assert not raw.player.body_technique.requires_immortal_power or raw.player.immortal_power_converted
                                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
                                page.reload();page.wait_for_function('configData && !busy')
                                page.evaluate('async id=>loadGame(id)',gid)
                                assert page.evaluate('game.player.immortal_power_converted')==(realm>=9)
                                assert not errors,errors
                                page.close()
                    browser.close()
            finally:
                httpd.shutdown();httpd.server_close()
    print('Release 271 UI passed: 24 real creations, four themes, desktop/portrait/landscape, conversion gate and reload')

if __name__=='__main__':main()
