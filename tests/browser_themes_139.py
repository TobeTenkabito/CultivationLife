"""Real-browser acceptance for six live layouts, persistence and untouched game state."""
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
        game_id = engine.create_game('沈清和', 'heavenly', 'dao', 1390, preset_id='core')['id']
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', root):
            httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(headless=True)
                    page = browser.new_page(viewport={'width':1440,'height':1050})
                    errors=[]
                    page.on('pageerror', lambda e: errors.append(str(e)))
                    url = f'http://127.0.0.1:{httpd.server_port}'
                    page.goto(url)
                    page.wait_for_function('window.GameThemes && configData')
                    page.evaluate('GameThemes.ready')
                    assert page.locator('html').get_attribute('data-theme') == 'a'
                    for theme in 'abcdef':
                        page.locator(f'[data-theme-picker=start] [data-theme-choice={theme}]').click()
                        page.evaluate('GameThemes.saved')
                        page.wait_for_timeout(250)
                        page.screenshot(path=str(ROOT / f'build/theme-139-{theme}-start.png'))
                    page.evaluate('async id=>{await loadGame(id);render(game)}',game_id)
                    before=page.evaluate('JSON.stringify(game)')
                    for theme in 'abcdef':
                        page.locator('#theme-open').click()
                        page.locator(f'[data-theme-picker=dialog] [data-theme-choice={theme}]').click()
                        page.evaluate('GameThemes.saved')
                        page.locator('[data-close-dialog=theme-dialog]').click()
                        page.wait_for_timeout(250)
                        assert page.locator('#hud-hp').is_visible()
                        assert page.locator('#hud-mp').is_visible()
                        assert page.locator('#hud-opportunity').is_visible()
                        assert page.locator('#cultivate-action').is_visible()
                        assert page.evaluate('JSON.stringify(game)') == before
                        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
                        page.screenshot(path=str(ROOT / f'build/theme-139-{theme}-game.png'))
                        page.locator('.hud-identity').click()
                        assert page.locator('#player-details-dialog').is_visible()
                        page.keyboard.press('Escape')
                        # Every registered feature window must still open, retain its node and inherit the palette.
                        failures=page.evaluate('''() => {const errors=[];for(const b of document.querySelectorAll('[data-panel-target]')){
                          const card=document.getElementById(b.dataset.panelTarget+'-card');
                          if(card&&!card.classList.contains('hidden')&&!b.disabled){
                            UtilityPanels.open(b.dataset.panelTarget);
                            if(!card.classList.contains('panel-open'))errors.push(b.dataset.panelTarget);
                          }
                        } document.querySelectorAll('[data-panel-target]').forEach(b=>UtilityPanels.close(b.dataset.panelTarget));return errors;}''')
                        assert not failures, failures
                        page.set_viewport_size({'width':430,'height':900})
                        page.wait_for_timeout(300)
                        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'),theme
                        page.screenshot(path=str(ROOT / f'build/theme-139-{theme}-mobile.png'))
                        page.set_viewport_size({'width':1440,'height':1050})
                        page.wait_for_timeout(300)
                    # A pending form keeps its exact node and field values during theme changes.
                    page.locator('[data-panel-target=merchant]').click()
                    panel=page.locator('#merchant-card')
                    page.evaluate("window.__merchantNode=document.querySelector('#merchant-card')")
                    page.locator('#theme-open').click()
                    page.locator('[data-theme-picker=dialog] [data-theme-choice=b]').click()
                    page.locator('[data-motion-setting]').last.check()
                    page.evaluate('GameThemes.saved')
                    page.keyboard.press('Escape')
                    assert page.evaluate("window.__merchantNode===document.querySelector('#merchant-card')")
                    assert panel.is_visible()
                    assert page.locator('html').get_attribute('data-motion') == 'reduced'
                    page.screenshot(path=str(ROOT / 'build/theme-139-b-merchant.png'))
                    page.keyboard.press('Escape')
                    previous_age=page.evaluate('game.player.age')
                    page.locator('#cultivate-action').click()
                    page.wait_for_function('!busy && game.player.age > '+str(previous_age))
                    assert page.locator('#hud-name').text_content()=='沈清和'
                    # Extreme values and a long identity retain exact accessible data and stay within the viewport.
                    page.evaluate('''() => {const preview=structuredClone(game);preview.player.name='司徒长风临江听雨问道真人';
                      preview.player.hp=1;preview.player.max_hp=1000000000000;GameThemes.render(preview);}''')
                    assert page.locator('#hud-hp').get_attribute('title').find('1,000,000,000,000')>=0
                    assert 'low' in page.locator('#hud-hp').get_attribute('class')
                    page.set_viewport_size({'width':430,'height':900})
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
                    # Fresh browser context has no localStorage; disk preferences remain authoritative.
                    fresh=browser.new_page()
                    fresh.goto(url);fresh.wait_for_function('window.GameThemes');fresh.evaluate('GameThemes.ready')
                    assert fresh.locator('html').get_attribute('data-theme') == 'b'
                    assert fresh.locator('html').get_attribute('data-motion') == 'reduced'
                    assert not errors,errors
                    browser.close()
            finally:
                httpd.shutdown();httpd.server_close()
    print('Six themes: start/game/mobile, live switching, dialogs, game-state isolation and persistence passed')


if __name__ == '__main__':
    main()
