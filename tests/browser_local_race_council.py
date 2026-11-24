"""Real sect directory, council submission and two-window recovery."""
import sys
import random
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.system.economy.organization_accounts import register
from scripts.browser_navigation import navigation_locator, click_control


def run():
    class Quiet(server.Handler):
        def log_message(self, *args):
            pass

    with tempfile.TemporaryDirectory() as tmp:
        engine = GameEngine(ROOT, Path(tmp) / 'saves')
        game = engine.create_game('族中会商', 'supreme_metal', 'dao', 442,
                                  custom_start=dict(world='spirit', realm_index=8, layer=1))
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', Path(tmp)), \
                ThreadingHTTPServer(('127.0.0.1', 0), Quiet) as http, sync_playwright() as pw:
            threading.Thread(target=http.serve_forever, daemon=True).start()
            browser = pw.chromium.launch(args=['--disable-gpu'])
            try:
                first = browser.new_page(viewport=dict(width=1280, height=800))
                second = browser.new_page(viewport=dict(width=393, height=852))
                errors = []
                for page in (first, second):
                    page.on('pageerror', lambda err: errors.append(str(err)))
                    page.goto(f'http://127.0.0.1:{http.server_port}')
                    page.wait_for_function('!!configData')
                    page.evaluate('id=>loadGame(id)', game['id'])
                    navigation_locator(page, '[data-panel-target=faction]').click()
                    book = page.locator('#faction-summary details.race-factions')
                    click_control(book.locator('summary'))
                    sample = game['race_system']['races']['woodborn']['supported_factions']
                    assert all(r['name'] in book.inner_text() for r in sample if not r['active'])
                    navigation_locator(page, '[data-panel-target=race]').click()
                    page.get_by_role('combobox', name='议案', exact=True).wait_for()
                for page, expected in ((first, 200), (second, 400)):
                    with page.expect_response(lambda r: r.url.endswith('/race-council')) as response:
                        click_control(page.get_by_role('button', name='召集会商'))
                    assert response.value.status == expected, response.value.text()
                    page.wait_for_function('!busy')
                    assert page.get_by_role('button', name='召集会商').is_disabled()
                    fold = page.locator('.race-council details').first
                    click_control(fold.locator('summary'))
                    assert fold.locator('p').count() >= 2
                assert not errors, errors
                current = engine.store.load(game['id']).strategic_war_state
                assert current['command_seq'] == 1 and len(current['local_councils']['spirit']['human']['recent']) == 1
                joined = engine.create_faction(game['id'], '微澜宗')
                assert joined['faction']['member']
                first.evaluate('id=>loadGame(id)', game['id'])
                navigation_locator(first, '[data-panel-target=faction]').click()
                book = first.locator('#faction-summary details.race-factions')
                book.get_by_text('本界宗门名录', exact=True).wait_for()
                if not book.evaluate('(node)=>node.open'):
                    click_control(book.locator('summary'))
                book.get_by_text('微澜宗', exact=False).last.wait_for()
                assert '微澜宗' in book.inner_text() and all(r['name'] in book.inner_text() for r in sample)
                g = engine._load(game['id'])
                donor, receiver = g.sects[g.player.faction_id], g.sects['taixuan']
                for org, cash in ((donor, 5000), (receiver, 50)):
                    org.location_id = g.player.location_id
                    register(g, 'sect', org.id, 'spirit')['expected_upkeep'] = 100
                    g.intrigue_state['factions']['sect:' + org.id]['resources'] = cash
                engine.store.save(g)
                first.evaluate('id=>loadGame(id)', game['id'])
                navigation_locator(first, '[data-panel-target=race]').click()
                first.get_by_role('combobox', name='议案', exact=True).select_option('aid')
                first.get_by_role('combobox', name='议案所涉宗门').select_option(label='微澜宗济太玄门 · 250灵石')
                first.get_by_role('combobox', name='本宗回函').select_option('yes')
                rng = random.Random(9)
                with patch('cultivation_life.engine.actions.strategic_war.decode_rng', return_value=rng), \
                        patch.object(rng, 'random', return_value=0), first.expect_response(lambda r: r.url.endswith('/race-council')) as response:
                    click_control(first.get_by_role('button', name='召集会商'))
                assert response.value.status == 200, response.value.text()
                first.wait_for_function('!busy')
                funds = engine.store.load(g.id).intrigue_state['factions']
                assert [funds['sect:' + o.id]['resources'] for o in (donor, receiver)] == [4750, 300]
                print('Sect directory, stale council submission, donor consent and real treasury transfer passed.')
            finally:
                browser.close()
                http.shutdown()


if __name__ == '__main__':
    run()
