"""Real clicks and stale-page recovery; one low-memory Chromium page at a time."""
import json
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.system.economy import caravans, trade_orders
from cultivation_life.system.economy.ledger import balance, transfer_value
from cultivation_life.system.economy.fleet_network import guard_wages
from cultivation_life.system.faction_geography import faction_site
from scripts.browser_navigation import navigation_locator, click_control
from scripts.release_evidence import inputs_digest
from test_economy_audit_round3 import sect_owner
from test_economy_enterprises import own_fleet, fleet
from test_economy_network import act
from browser_economy_round2 import new_game, estate_card, expand


def verify(page, engine, output, width):
    # A stale industry button cannot spend an original treasury after loss of rank.
    game = new_game(engine)
    game.player.realm_index = 4
    game.player.faction_id = 'tianjian'
    game.player.location_id = faction_site(game.sects['tianjian'])['id']
    transfer_value(game, 'player', 'organization:sect:tianjian', 100000, 'browser original treasury')
    engine.store.save(game)
    page.evaluate('async id=>loadGame(id)', game.id)
    navigation_locator(page, '[data-panel-target=merchant]').click()
    expand(page, page.locator('#fleet-network-content > details').first)
    button = page.locator('#fleet-network-content [data-fleet-action=industry]').filter(has_text='扩建宗门')
    assert not button.is_disabled()
    changed = engine._load(game.id)
    changed.player.realm_index = 2
    changed.sects['tianjian'].founded_by_player = False
    changed.intrigue_state['factions']['sect:tianjian']['controller_id'] = 'player'
    engine.store.save(changed)
    engine._load(game.id)
    frozen = engine.store._path(game.id).read_bytes()
    with page.expect_response(lambda r: '/fleet-action' in r.url) as response:
        click_control(button)
    assert response.value.status == 400
    page.wait_for_function('!busy && game.player.realm_index === 2')
    assert engine.store._path(game.id).read_bytes() == frozen
    assert button.is_disabled()

    # Deed purchase goes through the form, retaining the actual fiscal receipt.
    game = new_game(engine)
    sect_owner(game)
    game.player.location_id = faction_site(game.sects['tianjian'])['id']
    engine.store.save(game)
    page.evaluate('async id=>loadGame(id)', game.id)
    navigation_locator(page, '[data-panel-target=faction]').click()
    expand(page, page.locator('#faction-card .organization-business'))
    box = page.locator('#enterprise-panel-sect')
    expand(page, box)
    box.get_by_label('购置产业', exact=True).select_option('farm')
    before = engine._load(game.id)
    key = 'organization:sect:tianjian'
    pending = before.economy_v2['organizations'][key].get('pending_expense', 0)
    treasury = balance(before, key)
    click_control(box.locator('[data-estate-action=buy]'))
    page.wait_for_function('!busy && game.map.economy.enterprises.owned.some(r=>r.owner_kind === "sect" && r.kind === "farm")')
    saved = engine._load(game.id)
    assert saved.economy_v2['organizations'][key]['pending_expense'] - pending == treasury - balance(saved, key) > 0
    assert saved.economy_v2['organizations'][key]['estate_cost_credit'] == 0
    frozen = engine.store._path(game.id).read_bytes()
    page.reload()
    page.wait_for_function('configData && !busy')
    page.evaluate('async id=>loadGame(id)', game.id)
    assert engine.store._path(game.id).read_bytes() == frozen

    # Accepted order form, rejected underfunded dispatch, then funded real dispatch.
    game, identity = own_fleet(engine, new_game(engine))
    game = act(engine, game, 'guard', fleet_id=identity)
    f = fleet(game, identity)
    routes = [caravans.route_quote(game, engine.maps, 'human', f['location'], r['id'], 1)
              for r in engine.maps.worlds['human']['locations'] if r['id'] != f['location']]
    route = max((r for r in routes if r), key=lambda r: r['years'])
    page.evaluate('async id=>loadGame(id)', game.id)
    navigation_locator(page, '[data-panel-target=merchant]').click()
    box = page.locator('#trade-orders-panel')
    expand(page, box)
    card = box.locator(f'[data-order-fleet="{identity}"]')
    expand(page, card)
    card.get_by_label('订单执行方式', exact=True).select_option('once')
    card.get_by_label('商路类型', exact=True).select_option('local')
    card.get_by_label('商路目的地', exact=True).select_option(route['destination'])
    card.get_by_label('订单商品', exact=True).select_option('dew_grass_seed')
    click_control(card.locator('[data-fleet-action=order_configure]'))
    page.wait_for_function('!busy')
    expand(page, box)
    expand(page, card)
    changed = engine._load(game.id)
    f = fleet(changed, identity)
    offer = trade_orders.candidate(changed, engine.maps, f, caravans.route_quote)
    wages = guard_wages(f, offer['transport']['years'])
    key = 'caravan:' + identity
    transfer_value(changed, key, 'background:human', balance(changed, key)-offer['cost']-wages+1, 'browser budget short by one')
    engine.store.save(changed)
    engine._load(game.id)
    frozen = engine.store._path(game.id).read_bytes()
    with page.expect_response(lambda r: '/fleet-action' in r.url) as response:
        click_control(card.locator('[data-fleet-action=order_dispatch]'))
    assert response.value.status == 400
    page.wait_for_function('!busy')
    assert engine.store._path(game.id).read_bytes() == frozen
    changed = engine._load(game.id)
    transfer_value(changed, 'player', key, 1, 'browser complete reserve')
    engine.store.save(changed)
    expand(page, box)
    expand(page, card)
    click_control(card.locator('[data-fleet-action=order_dispatch]'))
    page.wait_for_function('!busy')
    saved = engine._load(game.id)
    assert fleet(saved, identity)['cargo'] and balance(saved, key) == wages
    assert card.locator('[data-fleet-action=order_dispatch]').is_disabled()
    page.screenshot(path=str(output / f'a-{width}.png'))


def main():
    output = ROOT / 'build/economy-round3-browser'
    output.mkdir(exist_ok=True)
    signature = inputs_digest(ROOT)
    results = []
    with tempfile.TemporaryDirectory(prefix='economy-round3-browser-') as folder:
        engine = GameEngine(ROOT, Path(folder) / 'saves')
        class Handler(server.Handler):
            def log_message(self, *args): pass
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', Path(folder)):
            http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            threading.Thread(target=http.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    for width, height in [(1440, 1000), (393, 852)]:
                        browser = pw.chromium.launch(args=['--disable-gpu', '--renderer-process-limit=1', '--js-flags=--max-old-space-size=128'])
                        try:
                            page = browser.new_page(viewport=dict(width=width, height=height), reduced_motion='reduce')
                            page.route('**/assets/maps/**', lambda route: route.abort())
                            errors = []
                            page.on('pageerror', lambda error: errors.append(str(error)))
                            page.goto(f'http://127.0.0.1:{http.server_port}')
                            page.wait_for_function('configData && !busy')
                            click_control(page.locator('[data-theme-picker=start] [data-theme-choice=a]'))
                            verify(page, engine, output, width)
                            assert not errors, errors
                            results.append(dict(width=width, status='passed'))
                            print(f'Round 3 browser: {width} passed', flush=True)
                        finally:
                            browser.close()
            finally:
                http.shutdown()
                http.server_close()
    assert signature == inputs_digest(ROOT)
    (output / 'report.json').write_text(json.dumps(dict(source_sha256=signature, results=results), indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
