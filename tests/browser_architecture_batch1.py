"""Real deferred catalog clicks, busy state, failures and obsolete replies."""
import hashlib
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
from cultivation_life.system.economy.ledger import transfer_value
from scripts.browser_navigation import navigation_locator, click_control
from scripts.release_evidence import inputs_digest
from test_architecture_batch1 import organization_game


def run():
    output = ROOT / 'build/architecture-batch1-20261031/browser'
    output.mkdir(parents=True, exist_ok=True)
    signature = inputs_digest(ROOT)
    with tempfile.TemporaryDirectory(dir=ROOT / 'build') as directory:
        engine = GameEngine(ROOT, Path(directory) / 'saves')
        ids = []
        for name in ('当前商队', '另一存档'):
            game = engine.store.load(engine.create_game(name, 'heavenly', 'dao', 315, preset_id='core')['id'])
            game.pending_event = None
            transfer_value(game, 'background:human', 'player', 10**7, '隔离验收资本')
            engine.store.save(game)
            engine.fleet_action(game.id, {'action': 'create', 'owner_kind': 'independent'})
            engine.get_game(game.id)
            ids.append(game.id)
        organization_ids = {kind: organization_game(engine, kind) for kind in ('sect', 'family')}
        for _ in range(2):
            for identity in [*ids, *organization_ids.values()]:
                engine.get_game(identity)
        def hashes():
            return {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in engine.store.directory.rglob('*') if p.is_file()}
        class Quiet(server.Handler):
            def log_message(self, *args):
                pass
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', Path(directory)):
            http = ThreadingHTTPServer(('127.0.0.1', 0), Quiet)
            threading.Thread(target=http.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    for width, height in ((1440, 1000), (393, 852)):
                        page = browser.new_page(viewport=dict(width=width, height=height))
                        errors, held = [], []
                        page.on('pageerror', lambda error: errors.append(str(error)))
                        mode = {'hold': True, 'fail': False}
                        requests = []
                        def catalog(route):
                            requests.append(route.request.url)
                            page.evaluate('(n) => window.catalogRequests=n', len(requests))
                            if mode['fail']:
                                mode['fail'] = False
                                route.fulfill(status=503, json={'error': '目录暂时不可用'})
                            elif mode['hold']:
                                held.append(route)
                            else:
                                route.continue_()
                        page.route('**/api/fleet-goods', catalog)
                        page.goto(f'http://127.0.0.1:{http.server_port}')
                        page.wait_for_function('configData && window.GameNavigation')
                        before = hashes()
                        page.evaluate('async id => loadGame(id)', ids[0])
                        assert page.evaluate('game.fleet_network.order_goods_deferred && !game.fleet_network.order_goods')
                        assert not requests, 'Closed panel requested its catalog'
                        navigation_locator(page, '[data-panel-target=merchant]').click()
                        page.wait_for_function('window.catalogRequests===1')
                        page.evaluate('busy=true;renderButtons()')
                        mode['hold'] = False
                        held.pop().continue_()
                        page.wait_for_function('document.querySelector("#fleet-network-content select[aria-label=订单商品]")')
                        assert page.evaluate('''[...document.querySelectorAll('#merchant-card button,#merchant-card input,#merchant-card select')]
                            .filter(n=>n.id!=='merchant-toggle').every(n=>n.disabled)''')
                        page.evaluate('busy=false;renderButtons()')
                        assert page.evaluate('''[...document.querySelectorAll('#fleet-network-content [data-merchant-unavailable="1"]')]
                            .every(n=>n.disabled)''')
                        assert page.locator('#fleet-network-content select[aria-label=订单商品] option').count() > 1000
                        # An earlier game's in-flight catalog must not repaint
                        # the next game's forms, even when its reply is valid JSON.
                        mode['hold'] = True
                        page.evaluate('async id => loadGame(id)', ids[0])
                        page.wait_for_function('window.catalogRequests===2')
                        page.evaluate('async id => loadGame(id)', ids[1])
                        old_dom = page.locator('#fleet-network-content').inner_html()
                        held.pop().fulfill(json={'goods': [{'id': 'obsolete', 'name': '过期目录'}]})
                        page.evaluate('async()=>{await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));}')
                        assert page.locator('#fleet-network-content').inner_html() == old_dom
                        # A failed read is recoverable through a real click,
                        # with the current save's controls and no game mutation.
                        mode.update(hold=False, fail=True)
                        navigation_locator(page, '[data-panel-target=merchant]').click()
                        page.wait_for_function('document.querySelector("#fleet-network-content button")?.textContent==="重新读取商品目录"')
                        click_control(page.get_by_role('button', name='重新读取商品目录', exact=True, include_hidden=True))
                        page.wait_for_function('document.querySelector("#fleet-network-content select[aria-label=订单商品]")')
                        assert page.evaluate('game.id') == ids[1]
                        assert '过期目录' not in page.locator('#fleet-network-content').inner_text()
                        for kind, identity in organization_ids.items():
                            count = len(requests)
                            page.evaluate('async id => loadGame(id)', identity)
                            assert page.evaluate('Array.isArray(game.fleet_network.order_goods)')
                            panel = 'faction' if kind == 'sect' else 'family'
                            navigation_locator(page, f'[data-panel-target={panel}]').click()
                            page.wait_for_function('kind => document.querySelector(`#trade-orders-panel-${kind} select[aria-label=订单商品]`)', arg=kind)
                            assert page.locator(f'#trade-orders-panel-{kind} select[aria-label=订单商品] option').count() > 1000
                            assert len(requests) == count, 'Organization fallback unexpectedly fetched a catalog'
                        assert hashes() == before, 'Catalog navigation changed persistence'
                        assert not errors, errors
                        page.screenshot(path=str(output / f'{width}.png'))
                        page.close()
                    browser.close()
            finally:
                http.shutdown()
                http.server_close()
    assert signature == inputs_digest(ROOT), 'Runtime changed during browser validation'
    (output / 'result.json').write_text(json.dumps(dict(
        inputs_sha256=signature, widths=[1440, 393], closed_panel_no_fetch=True,
        busy_and_unavailable_preserved=True, obsolete_reply_ignored=True,
        real_retry_click=True, organization_orders=['sect', 'family'],
        persistence_unchanged=True, page_errors=[]), indent=2) + '\n', encoding='utf-8')
    print('Deferred catalog desktop/mobile browser checks passed')


if __name__ == '__main__':
    run()
