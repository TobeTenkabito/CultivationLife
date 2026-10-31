"""Real hunting, busy disablement, report reload and detached replay snapshots."""
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from scripts.browser_navigation import navigation_locator
from scripts.release_evidence import inputs_digest


def run():
    output = ROOT/'build/architecture-batch3-20261031/browser'
    output.mkdir(parents=True, exist_ok=True)
    signature = inputs_digest(ROOT)
    layouts = []
    with tempfile.TemporaryDirectory(dir=ROOT/'build') as directory:
        folder = Path(directory)
        engine = GameEngine(ROOT, folder/'saves')
        identity = engine.create_game('快照实点验收', 'heavenly', 'dao', 941, preset_id='core')['id']
        game = engine.store.load(identity)
        game.pending_event = None
        game.settings.update(silent_events=True, combat_popup=True)
        engine.store.save(game)
        class Quiet(server.Handler):
            def log_message(self, *args):
                pass
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', folder):
            http = ThreadingHTTPServer(('127.0.0.1', 0), Quiet)
            threading.Thread(target=http.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    page = browser.new_page(viewport=dict(width=1440, height=960), reduced_motion='reduce')
                    errors, requests, held = [], [], []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.on('request', lambda request: requests.append((request.method, request.url)))
                    page.goto(f'http://127.0.0.1:{http.server_port}')
                    page.wait_for_function('configData && window.CombatReplay && window.GameThemes')
                    page.evaluate('id=>loadGame(id)', identity)
                    page.wait_for_function('id=>!busy&&game?.id===id', arg=identity)
                    page.locator('#theme-open').click()
                    page.locator('#theme-dialog [data-pixel-setting]').set_checked(True)
                    page.evaluate('GameThemes.saved')
                    page.locator('[data-close-dialog=theme-dialog]').click()
                    def hold_action(route):
                        held.append(route)
                        page.evaluate('window.snapshotRequestHeld=true')
                    page.route('**/api/games/*/advance', hold_action)
                    page.locator('[data-action-tab=combat]').click()
                    hunt = page.locator('[data-action=hunt_beast]')
                    hunt.click()
                    page.wait_for_function('window.snapshotRequestHeld&&busy')
                    assert held and hunt.is_disabled()
                    held.pop().continue_()
                    page.wait_for_function('!busy&&!!game.last_combat_report')
                    assert not hunt.is_disabled()
                    assert any(method == 'POST' and url.endswith('/advance') for method, url in requests)
                    report = page.evaluate('game.last_combat_report')
                    assert report['rounds'] and report == engine.store.load(identity).last_combat_report
                    for _ in range(2):
                        engine.get_game(identity)
                    original = engine.store._path(identity).read_bytes()
                    metadata = engine.achievements.metadata.path.read_bytes()
                    detached = engine.get_game(identity)
                    detached['last_combat_report']['rounds'][0]['caller-only'] = ['mutated']
                    assert engine.store.load(identity).last_combat_report == report
                    response = page.request.get(f'http://127.0.0.1:{http.server_port}/api/games/{identity}')
                    assert response.ok and response.json()['last_combat_report'] == report
                    for width, height in ((1440, 960), (393, 852)):
                        page.set_viewport_size(dict(width=width, height=height))
                        page.evaluate('id=>loadGame(id)', identity)
                        page.wait_for_function('id=>!busy&&game?.id===id', arg=identity)
                        page.evaluate('async()=>{await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));}')
                        if page.locator('#battle-report-card').evaluate('n=>n.classList.contains("report-closed")'):
                            navigation_locator(page, '#battle-report-open').click()
                        page.wait_for_function('CombatReplay.diagnostics().active&&!document.querySelector("[data-combat-replay]").disabled')
                        assert page.evaluate('game.last_combat_report') == report
                        page.evaluate('CombatReplay.seek(10000)')
                        before = page.evaluate('JSON.stringify(game)')
                        requests.clear()
                        page.locator('[data-combat-replay]').click()
                        page.wait_for_function('CombatReplay.diagnostics().time>0')
                        page.locator('[data-combat-pause]').click()
                        assert not any('/api/' in url for _, url in requests)
                        assert page.evaluate('JSON.stringify(game)') == before
                        assert engine.store._path(identity).read_bytes() == original
                        assert engine.achievements.metadata.path.read_bytes() == metadata
                        assert not errors, errors
                        page.screenshot(path=str(output/f'report-{width}.png'))
                        layouts.append(dict(width=width, passed=True, report_equal=True,
                            replay_without_requests_or_writes=True))
                        page.keyboard.press('Escape')
                    browser.close()
            finally:
                http.shutdown(); http.server_close()
    assert signature == inputs_digest(ROOT)
    (output/'result.json').write_text(json.dumps(dict(inputs_sha256=signature,
        real_hunt=True, busy_disabled_and_released=True, python_output_isolated=True,
        layouts=layouts, page_errors=[]), indent=2)+'\n', encoding='utf-8')
    print('Snapshot browser passed: real hunt, busy disablement, detached HTTP/Python reports and desktop/mobile replay')


if __name__ == '__main__':
    run()
