"""Real upper achievement confirmation and four-theme player encyclopedia UI."""
import json
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine


class Quiet(server.Handler):
    def log_message(self, *args):
        pass


def main():
    with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
        server.PERSISTENCE_ROOT = Path(folder)
        e = server.ENGINE = GameEngine(ROOT, Path(folder)/'saves')
        httpd = ThreadingHTTPServer(('127.0.0.1', 0), Quiet)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        errors = []
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                page = browser.new_page(viewport={'width': 412, 'height': 915})
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(f'http://127.0.0.1:{httpd.server_port}')
                page.wait_for_function('configData && window.TutorialHandbook')
                page.evaluate("async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'本相功业',preset_id:'nether_upper',monster_species_id:'serpent',seed:270})});await loadGame(g.id);}")
                page.wait_for_function('game && !busy')
                game_id = page.evaluate('game.id')
                page.locator('[data-panel-target="upper-voisinage"]').click()
                confirm = page.locator('[data-true-form] button').first
                confirm.click()
                page.wait_for_function('!busy && !!game.upper_voisinages.true_form.blueprint')
                assert e.achievements.metadata.read()['achievements']['monster_true_form_confirmed']['game_id'] == game_id
                page.evaluate("UtilityPanels.close('upper-voisinage');showStart()")
                page.locator('#achievement-open').click()
                page.locator('#achievement-groups').get_by_text('本相初铭', exact=True).wait_for()
                names = ('长生初成', '一域至臻', '万战称王', '五阀有席', '奉愿神使', '照魂见我', '八部立命', '魔域至臻')
                for theme in 'abdf':
                    page.evaluate('t=>document.querySelector(`[data-theme-picker=dialog] [data-theme-choice="${t}"]`).click()', theme)
                    page.evaluate('GameThemes.saved')
                    for width, height in ((1440, 1000), (412, 915), (915, 412)):
                        page.set_viewport_size({'width': width, 'height': height})
                        text = page.locator('#achievement-groups').inner_text()
                        assert all(name in text for name in names)
                        assert page.locator('#achievement-screen').evaluate('e=>e.scrollWidth<=e.clientWidth+2')
                    print(f'Upper achievements theme {theme}: desktop, portrait and landscape passed', flush=True)
                catalog = page.evaluate('achievementCatalog.achievements')
                row = next(r for r in catalog if r['id'] == 'monster_true_form_confirmed')
                assert row['unlocked'] and row['source']['id'] == 'official.monster-bloodlines'
                assert not errors, errors
                browser.close()
        finally:
            httpd.shutdown()
    print('Release 270 UI passed: real confirmation, persistent achievement, DLC sources and four-theme layouts')


if __name__ == '__main__':
    main()
