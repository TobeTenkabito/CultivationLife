"""Real page navigation, stale quotes, interruption/rewards and both pixel themes."""
import random
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
from cultivation_life.system.yaochi_rules import config
from scripts.westward_navigation import open_westward
from scripts.browser_navigation import navigation_locator, click_control, set_theme


def main():
    output = ROOT / 'build/yaochi-westward-browser'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='yaochi-westward-ui-') as folder:
        engine = GameEngine(ROOT, Path(folder) / 'saves')
        class Handler(server.Handler):
            def log_message(self, *args): pass
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', Path(folder)):
            http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            threading.Thread(target=http.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{http.server_port}'
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    for theme, width, height in [('light', 1440, 1000), ('dark', 1440, 1000), ('light', 390, 844), ('dark', 390, 844), ('dark', 754, 365)]:
                        made = engine.create_game('瑶池专修验收', 'supreme_metal', 'dao', 360, preset_id='true_immortal')
                        g = engine._load(made['id'])
                        g.pending_event = None
                        g.player.location_id = config()['location_id']
                        g.player.next_tribulation_age = None
                        g.player.immortal_body.update(level=20, manuals=['jade_marrows'], active_manual='jade_marrows')
                        g.yaochi_state.update(merit=2000, earned=2000)
                        g.heavenly_court.update(player_merit=50, open_election=None)
                        g.settings.update(silent_events=True, combat_popup=False, court_election_popup=False)
                        engine.store.save(g)
                        page = browser.new_page(viewport=dict(width=width, height=height), reduced_motion='reduce')
                        errors = []
                        page.on('pageerror', lambda error: errors.append(str(error)))
                        page.goto(base)
                        page.wait_for_function('!!configData && !busy')
                        set_theme(page, theme)
                        page.evaluate('id=>loadGame(id)', g.id)
                        open_westward(page,'专修')
                        page.locator('#yaochi-practice').wait_for()
                        assert page.locator('.yaochi-service').count() == 4
                        assert page.locator('[data-service=body] [data-westward-action=westward_start_merit]').is_disabled()
                        path = engine.store._path(g.id)
                        snapshot = path.read_bytes()
                        page.locator('[aria-label="五光坛神光"]').select_option('light_li')
                        assert page.locator('[data-service=light_li] [data-westward-action=westward_start_merit]').is_disabled()
                        page.locator('[aria-label="五光坛神光"]').select_option('light_kun')
                        open_westward(page,'资材')
                        assert page.locator('.yaochi-purchase').first.is_visible()
                        open_westward(page,'专修')
                        assert path.read_bytes() == snapshot
                        assert page.locator('.utility-panel.panel-open').evaluate('n=>n.scrollWidth<=n.clientWidth+2')
                        page.screenshot(path=str(output / f'{theme}-{width}-overview.png'), animations='disabled')
                        click_control(page.locator('[data-westward-action=westward_adopt]'))
                        page.wait_for_function('!busy && game.yaochi.westward.adopted')
                        # Mutate the authoritative balance, then click the still-visible old quote.
                        response = page.request.post(base + f'/api/games/{g.id}/yaochi-action', data=dict(action='exchange_court_merit', amount=1))
                        assert response.status == 200
                        with page.expect_response(lambda r: r.url.endswith('/yaochi-action')) as stale:
                            click_control(page.locator('[data-service=trace] [data-westward-action=westward_start_merit]'))
                        assert stale.value.status == 400
                        page.wait_for_function('!busy && game.yaochi.merit===1960')
                        assert not engine._load(g.id).yaochi_state.get('westward', {}).get('project')
                        page.locator('[aria-label="专修支付方式"]').select_option('court')
                        click_control(page.locator('[data-service=trace] [data-westward-action=westward_start_court]'))
                        page.wait_for_function('!busy && !!game.yaochi.westward.project')
                        assert page.evaluate('game.yaochi.westward.merit') == 41
                        assert page.evaluate('game.yaochi.westward.qualification') == 51
                        open_westward(page,'委托')
                        commissions = page.locator('#yaochi-content section').filter(has=page.get_by_role('heading', name='接取委托', exact=True))
                        assert commissions.locator('button').count() > 0
                        assert commissions.locator('button:enabled').count() == 0
                        assert '请先结清或交接' in commissions.inner_text()
                        open_westward(page,'专修')
                        page.locator('.utility-panel.panel-open .section-title > button[id$="-toggle"]').click()
                        navigation_locator(page, '[data-panel-target=heavenly-court]').click()
                        assert '功德资历' in page.locator('.court-summary').inner_text()
                        assert '可用功德' in page.locator('.court-summary').inner_text()
                        page.locator('#heavenly-court-toggle').click()
                        open_westward(page,'专修')
                        started = engine._load(g.id)
                        age, traces = started.player.age, started.player.immortal_traces
                        original = engine._advance_world_year
                        def interrupt(game, rng, news, **kwargs):
                            result = original(game, rng, news, **kwargs)
                            if game.player.age == age + 3:
                                warning = engine._instantiate_event(engine.events_by_id['EVT_SECT_FIRST_WARNING_001'], game, random.Random(1))
                                warning['_followup_event'] = engine._prepare_treasure_reward_event(game, random.Random(2))
                                game.pending_event = warning
                                return False
                            return result
                        with patch.object(engine, '_advance_world_year', side_effect=interrupt):
                            click_control(page.locator('[data-westward-action=westward_work]'))
                            page.wait_for_function('!busy && !!game.pending_event')
                        saved = engine._load(g.id)
                        assert saved.yaochi_state['westward']['project']['progress'] == 3
                        assert saved.player.immortal_traces == traces + 1
                        # Original event page must resolve both the interruption and its queued reward.
                        page.locator('.utility-panel.panel-open .section-title > button[id$="-toggle"]').click()
                        page.locator('#event-choices button').click()
                        page.wait_for_function('!busy && game.pending_event?.id !== "EVT_SECT_FIRST_WARNING_001"')
                        page.locator('#event-choices button').first.click()
                        page.wait_for_function('!busy && !game.pending_event')
                        open_westward(page,'专修')
                        assert not page.locator('[data-westward-action=westward_work]').is_disabled()
                        assert page.locator('[data-service=trace] [data-westward-action=westward_start_court]').is_disabled()
                        page.screenshot(path=str(output / f'{theme}-{width}-progress.png'), animations='disabled')
                        click_control(page.locator('.yaochi-exit summary'))
                        click_control(page.locator('[data-westward-action=westward_cancel]'))
                        page.wait_for_function('!busy && !game.yaochi.westward.project')
                        assert page.evaluate('game.yaochi.westward.merit') == 50  # 9 returned; 1 paid.
                        open_westward(page,'委托')
                        assert commissions.locator('button:enabled').count() > 0
                        click_control(commissions.locator('button').first)
                        page.wait_for_function('!busy && !!game.yaochi.job')
                        open_westward(page,'专修')
                        assert page.locator('[data-service=trace] [data-westward-action=westward_start_court]').is_disabled()
                        assert not errors, errors
                        page.close()
                        print(f'{theme} {width}x{height}: real tabs, readonly viewing, stale rejection/recovery, escrow, interrupted work, followup reward and refund passed', flush=True)
                    browser.close()
            finally:
                http.shutdown()
                http.server_close()


if __name__ == '__main__':
    main()
