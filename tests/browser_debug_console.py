"""Run directly: six-theme desktop/mobile console, session isolation and recovery."""
import json
from pathlib import Path
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        engine = GameEngine(ROOT, root / 'data' / 'saves')
        made = engine.create_game('Console Browser', 'heavenly', 'dao', seed=557, preset_id='core')
        saved = engine.store.load(made['id']); saved.pending_event = None; engine.store.save(saved)
        config = root / 'game_config.txt'
        config.write_text('Debug=True')
        class QuietHandler(server.Handler):
            def log_message(self, *_args):
                pass
        httpd = ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        errors = []
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'APP_ROOT', root), patch.object(server, 'PERSISTENCE_ROOT', root):
            thread.start()
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch()
                    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    url = f'http://127.0.0.1:{httpd.server_port}'
                    page.goto(url)
                    page.wait_for_function('configData !== null')
                    page.evaluate('async id => loadGame(id)', made['id'])
                    original = (engine.store.directory / f'{made["id"]}.json').read_bytes()
                    page.locator('#debug-console-open').click()
                    page.wait_for_function('!busy')
                    def command(text):
                        page.locator('#debug-console-input').fill(text)
                        page.locator('#debug-console-input').press('Enter')
                        page.wait_for_function('!busy && !document.querySelector("#debug-console-input").disabled')
                        assert page.locator('#debug-console-output pre').last.get_attribute('class') != 'debug-error', page.locator('#debug-console-output').inner_text()
                    command('debug start')
                    sid = page.evaluate("sessionStorage.getItem('cultivation-debug-session')")
                    assert sid
                    command('player set spirit_stones 7654321')
                    assert page.evaluate("game.player.inventory.find(x=>x.id==='spirit_stone').quantity") == 7654321
                    command('player set breakthrough_chance 1')
                    command('snapshot create baseline')
                    command('player set realm_index 4')
                    command('player set layer 7')
                    command('give spirit_stone 100')
                    command('snapshot restore baseline')
                    assert page.evaluate("game.player.inventory.find(x=>x.id==='spirit_stone').quantity") == 7654321
                    command('help player')
                    field = page.locator('#debug-console-input')
                    field.fill('player set spirit_'); field.press('Tab')
                    assert field.input_value() == 'player set spirit_stones '
                    field.press('ArrowUp'); assert field.input_value() == 'help player'
                    field.press('Control+l'); assert page.locator('#debug-console-output').inner_text() == ''
                    command('state get /player/realm_index')
                    command('item list "spirit_stone" 0')
                    command('item give spirit_stone 12')
                    assert page.evaluate("game.player.inventory.find(x=>x.id==='spirit_stone').quantity") == 7654333
                    command('item remove spirit_stone 12')
                    command('action advance rest 1')
                    command('event inspect')
                    command('snapshot restore baseline')
                    assert page.evaluate("game.player.inventory.find(x=>x.id==='spirit_stone').quantity") == 7654321
                    for width, height in ((1440, 1000), (412, 915), (915, 412)):
                        page.set_viewport_size({'width': width, 'height': height})
                        for theme in 'abcdef':
                            page.evaluate("theme => document.querySelector(`[data-theme-choice=\"${theme}\"]`).click()", theme)
                            command('player get realm_index')
                            assert page.locator('#debug-console-input').is_visible()
                            box = page.locator('#debug-console').bounding_box()
                            assert box['x'] >= 0 and box['x'] + box['width'] <= width + 1
                    page.set_viewport_size({'width': 1440, 'height': 1000})
                    command('repro export')
                    with page.expect_download() as downloaded:
                        page.locator('#debug-console-output a[download]').last.click()
                    artifact = ROOT / 'build' / 'debug-console-repro.json'
                    downloaded.value.save_as(artifact)
                    bundle = json.loads(artifact.read_text(encoding='utf-8'))
                    assert bundle['format'] == 'CultivationLife.debug.v1'
                    page.screenshot(path=str(ROOT / 'build' / 'debug-console-desktop.png'))
                    page.locator('#debug-console header button').click()
                    page.evaluate('async () => mutate(`/api/games/${game.id}/advance`, {action:"rest",years:1})')
                    assert (engine.store.directory / f'{made["id"]}.json').read_bytes() == original
                    # A second independent tab uses the original save, never the debug token.
                    normal = browser.new_page(); normal.goto(url)
                    normal.wait_for_function('configData !== null')
                    normal.evaluate('async id => loadGame(id)', made['id'])
                    assert normal.evaluate("game.player.inventory.find(x=>x.id==='spirit_stone')?.quantity || 0") != 7654321
                    normal.close()
                    # Disabling debug must not silently route stale session actions to production.
                    config.write_text('Debug=False')
                    current = (engine.store.directory / f'{made["id"]}.json').read_bytes()
                    page.evaluate('async () => mutate(`/api/games/${game.id}/advance`, {action:"rest",years:1})')
                    assert (engine.store.directory / f'{made["id"]}.json').read_bytes() == current
                    page.locator('#debug-console-open').click()
                    page.get_by_role('button', name='断开会话', exact=True).click()
                    page.wait_for_function('typeof configData !== "undefined" && configData !== null && !DebugConsole.active()')
                    assert page.locator('#debug-console-open').count() == 0
                    assert not errors, errors
                    browser.close()
            finally:
                httpd.shutdown(); httpd.server_close(); thread.join(timeout=5)
    print('Debug console: six themes, three viewports, items, action simulation, snapshots, completion, export, two-tab isolation and disabled-mode recovery passed.')


if __name__ == '__main__':
    main()
