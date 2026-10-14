"""Real submits and stale-page recovery, one Chromium page per layout."""
import json
import sys
import tempfile
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.rules import add_item
from cultivation_life.system.economy.ledger import balance, transfer_value
from scripts.browser_navigation import navigation_locator, click_control, reveal_subpage
from test_economy_audit_round2 import advanced_estate, sect_estate, open_auction, held


def expand(page, box):
    reveal_subpage(page, box)
    if box.get_attribute('open') is None:
        click_control(box.locator(':scope > summary'))


def new_game(engine):
    game = engine._load(engine.create_game('经营边界', 'supreme_metal', 'dao', 419, preset_id='core')['id'])
    game.pending_event = None
    game.player.realm_index = 2
    game.player.next_tribulation_age = None
    transfer_value(game, 'background:human', 'player', 10**9, 'test actual operating capital')
    engine.store.save(game)
    return engine._load(game.id)


def estate_card(page, game_id, key, scope=None):
    page.evaluate('async id=>loadGame(id)', game_id)
    if scope:
        navigation_locator(page, '[data-panel-target=faction]').click()
        expand(page, page.locator('#faction-card .organization-business'))
        box = page.locator('#enterprise-panel-' + scope)
    else:
        navigation_locator(page, '[data-panel-target=map]').click()
        click_control(page.get_by_role('button', name='本地市场', exact=True))
        expand(page, page.locator('.economy-overview'))
        box = page.locator('#enterprise-panel')
    expand(page, box)
    card = box.locator(f'[data-estate-id="{key}"]')
    expand(page, card)
    return card


def verify(page, engine, base, output, width):
    game, key, _ = advanced_estate(engine, new_game(engine))
    card = estate_card(page, game.id, key)
    start = card.locator('[data-estate-action=start]')
    assert not start.is_disabled()
    changed = engine._load(game.id)
    changed.player.realm_index = 2
    engine.store.save(changed)
    engine._load(game.id)
    frozen = engine.store._path(game.id).read_bytes()
    with page.expect_response(lambda r: '/fleet-action' in r.url) as response:
        click_control(start)
    assert response.value.status == 400
    page.wait_for_function('!busy && game.player.realm_index === 2')
    assert engine.store._path(game.id).read_bytes() == frozen
    assert start.is_disabled()
    assert not engine._load(game.id).economy_v2['estates'][key]['job']

    game, key = sect_estate(engine, new_game(engine))
    card = estate_card(page, game.id, key, scope='sect')
    expand(page, card.locator('details').filter(has=page.get_by_text('仓储与交易', exact=True)))
    card.get_by_label('仓储商品', exact=True).select_option('dew_grass_seed')
    withdraw = card.locator('[data-estate-action=withdraw]')
    assert not withdraw.is_disabled()
    response = page.request.post(base + f'/api/games/{game.id}/leave-faction', data={})
    assert response.ok
    changed = engine._load(game.id)
    changed.intrigue_state['factions']['sect:tianjian']['controller_id'] = 'player'
    engine.store.save(changed)
    engine._load(game.id)
    frozen = engine.store._path(game.id).read_bytes()
    with page.expect_response(lambda r: '/fleet-action' in r.url) as response:
        click_control(withdraw)
    assert response.value.status == 400
    page.wait_for_function('!busy && !game.player.faction_id')
    assert engine.store._path(game.id).read_bytes() == frozen
    assert not page.locator(f'#enterprise-panel-sect [data-estate-id="{key}"]').count()
    assert engine._load(game.id).economy_v2['estates'][key]['stock']['dew_grass_seed'] == 3

    game = open_auction(engine, new_game(engine))
    item = 'econ_human_5_artifact_attack'
    add_item(game.player, item)
    engine.store.save(game)
    page.evaluate('async id=>loadGame(id)', game.id)
    navigation_locator(page, '[data-panel-target=auction]').click()
    page.locator('#auction-consign-item').select_option(item)
    page.locator('#auction-start-price').fill(str(engine._catalog_price('item', item) * 5))
    click_control(page.locator('#auction-consign-form button[type=submit]'))
    page.wait_for_function('!busy && game.auction_system.lots.some(r=>r.seller === "player")')
    changed = engine._load(game.id)
    transfer_value(changed, 'background:human', 'player', balance(changed, 'background:human'), 'test exhausted buyer')
    engine.store.save(changed)
    for count in range(int(engine._auction_rules()['auction_rounds'])):
        click_control(page.locator('#auction-advance-round'))
        page.wait_for_function('(count)=>!busy && game.auction_system.round === count', arg=count + 1)
    page.wait_for_function('!busy && game.auction_system.status === "black_market"')
    assert page.locator('#black-market-section').is_visible()
    assert page.locator('#auction-lots-section').is_hidden()
    assert page.evaluate('game.auction_system.lots.find(r=>r.seller === "player").unsold')
    saved = engine._load(game.id)
    assert held(saved.player, item) == 1
    assert any('流拍并原物退回' in h.summary for h in saved.history)
    frozen = engine.store._path(game.id).read_bytes()
    page.reload()
    page.wait_for_function('configData && !busy')
    page.evaluate('async id=>loadGame(id)', game.id)
    assert engine.store._path(game.id).read_bytes() == frozen
    assert held(engine._load(game.id).player, item) == 1
    navigation_locator(page, '[data-panel-target=auction]').click()
    page.screenshot(path=str(output / f'a-{width}.png'))
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')


def main():
    output = ROOT / 'build/economy-round2-browser'
    output.mkdir(exist_ok=True)
    results = []
    with tempfile.TemporaryDirectory(prefix='economy-round2-browser-') as folder:
        engine = GameEngine(ROOT, Path(folder) / 'saves')
        class Handler(server.Handler):
            def log_message(self, *args): pass
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', Path(folder)):
            http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            threading.Thread(target=http.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{http.server_port}'
            try:
                with sync_playwright() as pw:
                    for width, height in [(1440, 1000), (393, 852)]:
                        browser = pw.chromium.launch(args=['--disable-gpu', '--renderer-process-limit=1'])
                        try:
                            page = browser.new_page(viewport=dict(width=width, height=height), reduced_motion='reduce')
                            page.route('**/assets/maps/**', lambda route: route.abort())
                            errors = []
                            page.on('pageerror', lambda error: errors.append(str(error)))
                            page.goto(base)
                            page.wait_for_function('configData && !busy')
                            click_control(page.locator('[data-theme-picker=start] [data-theme-choice=a]'))
                            verify(page, engine, base, output, width)
                            assert not errors, errors
                            results.append(dict(theme='a', width=width, status='passed'))
                            print(f'Round 2 browser: {width} passed', flush=True)
                            page.close()
                        finally:
                            browser.close()
            finally:
                http.shutdown()
                http.server_close()
    (output / 'report.json').write_text(json.dumps(results, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
