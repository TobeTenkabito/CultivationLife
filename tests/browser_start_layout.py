"""Check real start controls, compact groups and tutorial in all six themes."""
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright  # noqa: E402
from cultivation_life import server  # noqa: E402
from cultivation_life.engine import GameEngine  # noqa: E402


class Quiet(server.Handler):
    def log_message(self, *_args):
        pass


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        engine = GameEngine(ROOT, root / 'data/saves')
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', root):
            httpd = ThreadingHTTPServer(('127.0.0.1', 0), Quiet)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    page = browser.new_page()
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.goto(f'http://127.0.0.1:{httpd.server_port}')
                    page.wait_for_function('window.TutorialGuide && configData && window.GameThemes')
                    page.evaluate('GameThemes.ready')
                    count = page.evaluate('configData.quick_starts.length')
                    for width, height in ((1440, 1000), (393, 873), (320, 700)):
                        page.set_viewport_size({'width': width, 'height': height})
                        for theme in 'abcdef':
                            page.locator(f'[data-theme-picker=start] [data-theme-choice={theme}]').click()
                            page.evaluate('GameThemes.saved')
                            page.wait_for_timeout(350)
                            entry = page.locator('#start-screen [data-tutorial-open]')
                            assert entry.locator('svg').count() == 1
                            assert entry.locator('strong').inner_text() == '新手教程'
                            entry.click()
                            assert page.locator('#tutorial-dialog').evaluate('e=>e.open')
                            page.locator('#tutorial-close').click()
                            groups = page.locator('.quick-start-group')
                            assert page.locator('.quick-start-button').count() == count
                            assert groups.count() >= 4
                            for i in range(groups.count()):
                                group = groups.nth(i)
                                group.evaluate('e=>e.open=false')
                                group.locator('summary').click()
                                assert group.evaluate('e=>e.open')
                                for button in group.locator('.quick-start-button').all():
                                    assert button.is_visible()
                                    assert button.get_attribute('title')
                                    assert button.evaluate('e=>e.scrollWidth<=e.clientWidth+1')
                                group.locator('summary').click()
                            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                            if theme == 'a' and width in (1440, 393):
                                groups.first.locator('summary').click()
                                page.locator('#start-screen').screenshot(path=str(ROOT / f'build/start-layout-{width}.png'))
                                groups.first.locator('summary').click()
                    for preset, badge in [('buddhist_void', '佛修 DLC'), ('reincarnation_upper', '鬼修 DLC'),
                                          ('asura_upper', '修罗 DLC'), ('nether_upper', '妖修 DLC')]:
                        assert badge in page.locator(f'[data-preset-id={preset}]').text_content()
                    monster = page.locator('[data-preset-id=monster_void]')
                    monster.locator('xpath=ancestor::details').evaluate('e=>e.open=true')
                    assert monster.is_disabled()
                    species = monster.locator('..').locator('select')
                    species.select_option('serpent')
                    assert monster.is_enabled()
                    species.select_option('')
                    page.evaluate('renderButtons()')
                    assert monster.is_disabled()
                    buddhist = page.locator('[data-preset-id=buddhist_void]')
                    buddhist.click()
                    page.wait_for_function('game?.player.path==="buddhist" && !busy')
                    entry = page.locator('#action-card [data-tutorial-open]')
                    assert entry.locator('svg').count() == 1
                    entry.click()
                    assert page.locator('#tutorial-dialog').evaluate('e=>e.open')
                    page.locator('#tutorial-close').click()
                    for path in ('dao', 'monster'):
                        page.locator('#new-game-button').click()
                        lost = page.locator('[data-preset-id=lost_world]')
                        lost.locator('xpath=ancestor::details').evaluate('e=>e.open=true')
                        page.select_option('[data-quick-path]', '')
                        page.evaluate('renderButtons()')
                        assert lost.is_disabled()
                        page.select_option('[data-quick-path]', path)
                        if path == 'monster':
                            assert lost.is_disabled()
                            page.select_option('[data-quick-species]', 'serpent')
                        else:
                            assert page.locator('[data-quick-species]').is_hidden()
                        assert lost.is_enabled()
                        lost.click()
                        page.wait_for_function('game?.player.world==="lost" && !busy')
                        assert page.evaluate('game.player.path') == path
                        page.locator('[data-panel-target=map]').click()
                        assert page.locator('#map-locations .map-location').count() == 4
                        assert 'null' not in page.locator('#map-locations').inner_text()
                        assert page.locator('#map-locations').get_by_text('气经验：', exact=False).count() == 4
                        assert page.evaluate('game.map.locations.every(l=>Object.keys(l.qi_concentrations).length===4)')
                    assert not errors, errors
                    browser.close()
            finally:
                httpd.shutdown()
                httpd.server_close()
    print('Start layout passed: six themes, desktop and two phone widths; folding, tutorial, DLC labels, Buddhist and lost-world starts, mandatory path/species and generated maps.')


if __name__ == '__main__':
    main()
