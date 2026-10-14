"""Sequential real page submissions for audit fixes; two low-memory layouts."""
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
from cultivation_life.system.economy import state, market_governance, depot
from cultivation_life.system.economy.ledger import balance, transfer_value
from scripts.browser_navigation import navigation_locator, click_control, reveal_subpage
from test_release_290 import clan_game, game_at
from test_economy_audit_followup import captured_fleet


def expand(page, box):
    reveal_subpage(page, box)
    if box.get_attribute('open') is None:
        click_control(box.locator(':scope > summary'))


def main():
    output = ROOT / 'build/economy-followup-browser'
    output.mkdir(exist_ok=True)
    reports = []
    with tempfile.TemporaryDirectory(prefix='economy-followup-') as folder:
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
                            game, family = clan_game(engine)
                            game.player.realm_index = 2
                            state.ensure_regional_market(game, engine.maps, 'human', family.location_id)
                            market = game.economy_v2['markets']['human:' + family.location_id]
                            market_governance.assign(game, market, 'sect', family.id, 'browser-audit')
                            engine.store.save(game)
                            page.evaluate('async id=>loadGame(id)', game.id)
                            navigation_locator(page, '[data-panel-target=family]').click()
                            click_control(page.locator('[data-family]:not(:disabled)').filter(has_text='申请加入').first)
                            page.wait_for_function('!busy && game.family && game.family.player_member_type === "外姓修士"')
                            saved = engine._load(game.id)
                            assert saved.economy_v2['markets'][market['id']]['control']['kind'] == 'family'
                            frozen = engine.store._path(game.id).read_bytes()
                            page.reload()
                            page.wait_for_function('configData && !busy')
                            page.evaluate('async id=>loadGame(id)', game.id)
                            assert engine.store._path(game.id).read_bytes() == frozen
                            # Manual procurement reaches the actual HTTP command and fiscal receipt.
                            game, entity = game_at(engine)
                            storage = depot.ensure(game, entity)
                            engine.store.save(game)
                            row = game.economy_v2['organizations']['organization:sect:' + entity.id]
                            before = balance(game, 'organization:sect:' + entity.id)
                            expense = row.get('pending_expense', 0)
                            page.evaluate('async id=>loadGame(id)', game.id)
                            navigation_locator(page, '[data-panel-target=faction]').click()
                            box = page.locator('#faction-card .organization-depot')
                            expand(page, box)
                            item = next(k for k, r in depot.catalog('human').items() if r['kind'] == 'item'
                                        and game.economy_v2['markets']['human:' + entity.location_id]['commodities'].get(r['id'], {}).get('stock', 0) >= 1)
                            box.locator('[aria-label="采购物资"]').select_option(item)
                            click_control(box.locator('.depot-purchase button[type=submit]'))
                            page.wait_for_function('!busy')
                            saved = engine._load(game.id)
                            paid = before - balance(saved, 'organization:sect:' + entity.id)
                            assert paid > 0 and saved.economy_v2['organizations']['organization:sect:' + entity.id]['pending_expense'] - expense == paid
                            # A second client leaves the sect; the stale guard click must recover.
                            game = engine._load(engine.create_game('护卫权限', 'supreme_metal', 'dao', 419, preset_id='core')['id'])
                            game.pending_event = None
                            transfer_value(game, 'background:human', 'player', 10000, 'test guard capital')
                            game, key = captured_fleet(engine, game)
                            page.evaluate('async id=>loadGame(id)', game.id)
                            navigation_locator(page, '[data-panel-target=merchant]').click()
                            expand(page, page.locator('#fleet-network-content > details').first)
                            guard = page.locator(f'#fleet-network-content [data-fleet-id="{key}"] [data-fleet-action=guard]')
                            assert not guard.is_disabled()
                            response = page.request.post(base + f'/api/games/{game.id}/leave-faction', data={})
                            assert response.ok
                            frozen = engine.store._path(game.id).read_bytes()
                            click_control(guard)
                            page.wait_for_function('!busy && !game.player.faction_id')
                            assert engine.store._path(game.id).read_bytes() == frozen
                            assert guard.count() == 0
                            assert not page.locator(f'#fleet-network-content [data-fleet-id="{key}"] [data-fleet-action=fund]').count()
                            assert not errors, errors
                            page.screenshot(path=str(output / f'a-{width}.png'))
                            reports.append(dict(theme='a', width=width, status='passed'))
                            page.close()
                        finally:
                            browser.close()
            finally:
                http.shutdown()
                http.server_close()
    (output / 'report.json').write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Audit browser: {len(reports)} layouts passed; actual join/reload, procurement and stale guard recovery')


if __name__ == '__main__':
    main()
