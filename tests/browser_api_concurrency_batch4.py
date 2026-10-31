"""Two real tabs during an action: responsive reads, busy UI, serialized restore."""
import hashlib
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
from unittest.mock import patch
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.system.economy.ledger import transfer_value
from scripts.browser_navigation import navigation_locator, click_control
from scripts.release_evidence import inputs_digest


def files(folder):
    return {path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in folder.glob('*.json')}


def run():
    output = ROOT/'build/architecture-batch4-20261031/browser'
    output.mkdir(parents=True, exist_ok=True)
    signature = inputs_digest(ROOT)
    rows = []
    with tempfile.TemporaryDirectory(dir=ROOT/'build') as directory:
        folder = Path(directory)
        engine = GameEngine(ROOT, folder/'saves')
        state = dict(watch=None)
        entered, release, attempted, loaded = (threading.Event() for _ in range(4))
        year, load = engine._advance_world_year, engine._load
        def gated_year(*args, **kwargs):
            entered.set()
            if not release.wait(35):
                raise TimeoutError('Browser did not release action gate')
            return year(*args, **kwargs)
        def observed_load(identity):
            if identity == state['watch']:
                loaded.set()
            return load(identity)
        class Quiet(server.Handler):
            def log_message(self, *args):
                pass
            def _validate_request(self):
                super()._validate_request()
                if state['watch'] and urlparse(self.path).path == '/api/games/'+state['watch']:
                    attempted.set()
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', folder), \
             patch.object(engine, '_advance_world_year', gated_year), patch.object(engine, '_load', observed_load):
            http = ThreadingHTTPServer(('127.0.0.1', 0), Quiet)
            threading.Thread(target=http.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{http.server_port}'
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    context = browser.new_context()
                    for width, height in ((1440, 960), (393, 852)):
                        release.set()
                        identities = []
                        for name in ('长行动', '另一存档'):
                            identity = engine.create_game(name, 'heavenly', 'dao', 315, preset_id='core')['id']
                            game = engine.store.load(identity)
                            game.pending_event = None
                            game.player.next_tribulation_age = None
                            game.settings['silent_events'] = True
                            transfer_value(game, 'background:human', 'player', 10**7, '并发页面隔离验收资金')
                            engine.store.save(game)
                            if not identities:
                                engine.fleet_action(identity, dict(action='create', owner_kind='independent'))
                            for _ in range(2):
                                engine.get_game(identity)
                            identities.append(identity)
                        first = context.new_page()
                        first.set_viewport_size(dict(width=width, height=height))
                        errors = []
                        first.on('pageerror', lambda error: errors.append(str(error)))
                        first.goto(base)
                        first.wait_for_function('configData && window.GameNavigation')
                        first.evaluate('async id=>loadGame(id)', identities[0])
                        first.wait_for_function('id=>!busy&&game?.id===id', arg=identities[0])
                        navigation_locator(first, '[data-panel-target=merchant]').click()
                        first.wait_for_function('document.querySelector("#fleet-network-content select[aria-label=订单商品]")')
                        first.locator('#merchant-toggle').click()
                        start_age = engine.store.load(identities[0]).player.age
                        before = files(engine.store.directory)
                        entered.clear(); release.clear(); attempted.clear(); loaded.clear()
                        state['watch'] = identities[1]
                        try:
                            click_control(first.locator('[data-action=rest]'))
                            first.wait_for_function('busy')
                            assert entered.wait(5)
                            assert first.locator('[data-action=rest]').is_disabled()
                            # Existing navigation is deliberately disabled while
                            # busy; do not force-click it to exercise concurrency.
                            assert first.locator('[data-panel-target=merchant]').is_disabled()
                            assert first.evaluate('busy && [...document.querySelectorAll("#fleet-network-content button,#fleet-network-content input,#fleet-network-content select")].every(n=>n.disabled)')
                            values = first.evaluate('''async()=>{
                              const paths=['/api/config','/api/ui-preferences','/api/visual-assets','/api/fleet-goods','/api/domain-styles','/api/games','/api/achievements','/api/authored-lineages'];
                              return await Promise.all(paths.map(async path=>{const r=await fetch(path);await r.json();return r.status;}));
                            }''')
                            assert values == [200]*8 and first.evaluate('busy')
                            second = context.new_page()
                            second.set_viewport_size(dict(width=width, height=height))
                            second.on('pageerror', lambda error: errors.append(str(error)))
                            second.goto(base)
                            second.wait_for_function('configData&&document.querySelectorAll(".save-entry").length>=2')
                            assert not release.is_set()
                            second.locator(f'[data-save-id="{identities[1]}"] .save-resume').click()
                            second.wait_for_function('busy')
                            assert attempted.wait(5) and not loaded.is_set()
                            assert files(engine.store.directory) == before
                            first.screenshot(path=str(output/f'busy-{width}.png'))
                        finally:
                            release.set()
                        first.wait_for_function('id=>!busy&&game?.id===id', arg=identities[0])
                        second.wait_for_function('id=>!busy&&game?.id===id', arg=identities[1])
                        assert loaded.is_set()
                        assert engine.store.load(identities[0]).player.age > start_age
                        navigation_locator(first, '[data-panel-target=merchant]').click()
                        first.wait_for_function('document.querySelector("#fleet-network-content select[aria-label=订单商品]")')
                        assert first.evaluate("""[...document.querySelectorAll('#fleet-network-content [data-merchant-unavailable="1"]')].every(n=>n.disabled)""")
                        assert not errors, errors
                        second.screenshot(path=str(output/f'restored-{width}.png'))
                        rows.append(dict(width=width, responsive_reads=8, new_tab_booted_while_action_held=True,
                            real_deferred_navigation=True, busy_preserved=True,
                            other_game_waited_until_commit=True, writes_before_release=False, page_errors=[]))
                        state['watch'] = None
                        first.close(); second.close()
                    context.close(); browser.close()
            finally:
                release.set()
                http.shutdown(); http.server_close()
    assert signature == inputs_digest(ROOT)
    (output/'result.json').write_text(json.dumps(dict(inputs_sha256=signature, layouts=rows), indent=2)+'\n', encoding='utf-8')
    print('Concurrent API browser passed: desktop/mobile, eight responsive reads, busy deferred panel, second-tab boot and serialized game restore')


if __name__ == '__main__':
    run()
