"""One low-memory browser exercises renamed items and legacy command payloads."""
import copy
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
from cultivation_life.content_registry import TECHNIQUE_CATALOG
from cultivation_life.engine import GameEngine
from test_content_naming import legacy_fixture
from scripts.browser_navigation import navigation_locator, click_control, reveal_subpage


def main():
    output = ROOT / 'build/content-naming-browser'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='content-naming-browser-') as folder:
        engine = GameEngine(ROOT, Path(folder) / 'saves')
        game = legacy_fixture(engine)
        game.player.known_techniques.append(copy.deepcopy(TECHNIQUE_CATALOG['TECH_CICADA_METAMORPHOSIS']))
        engine.store.save(game)
        class Handler(server.Handler):
            def log_message(self, *args): pass
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', Path(folder)):
            http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            threading.Thread(target=http.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(args=['--disable-gpu', '--renderer-process-limit=1', '--js-flags=--max-old-space-size=128'])
                    try:
                        page = browser.new_page(viewport=dict(width=1280, height=900), reduced_motion='reduce')
                        page.set_default_timeout(10000)
                        errors = []
                        page.on('pageerror', lambda error: errors.append(str(error)))
                        page.on('dialog', lambda dialog: dialog.accept())
                        page.goto(f'http://127.0.0.1:{http.server_port}')
                        page.wait_for_function('!!configData')
                        page.evaluate('async id=>loadGame(id)', game.id)
                        click_control(page.locator('.hud-identity'))
                        click_control(page.locator('.technique-library summary'))
                        known = page.locator('#known-technique-list .known-technique').filter(has_text='黄庭内景经')
                        assert 'Lv.5' in known.inner_text()
                        special = page.locator('#known-technique-list .known-technique').filter(has_text='蝉蜕玄章')
                        assert '成功夺舍次数上限 +1' in special.inner_text()
                        # The real button posts the identifier used by a pre-update page.
                        page.route('**/technique-upgrade', lambda route: route.continue_(post_data=json.dumps({'technique_id': 'TECH_COMMON_NASCENT'})))
                        with page.expect_response(lambda response: response.url.endswith('/technique-upgrade')) as response:
                            known.locator('.technique-upgrade').click()
                        assert response.value.status == 200, response.value.text()
                        page.wait_for_function('!busy && game.player.known_techniques.some(t=>t.name==="黄庭内景经"&&t.level===6)')
                        assert 'Lv.6' in known.inner_text()
                        assert known.locator('.technique-upgrade').is_disabled()
                        page.locator('[data-close-dialog=player-details-dialog]').click()
                        navigation_locator(page, '[data-panel-target=inventory]').click()
                        crystal = page.locator('#inventory-list .item').filter(has_text='离照玄晶')
                        crystal.wait_for(state='attached')
                        reveal_subpage(page, crystal)
                        crystal.wait_for(state='visible')
                        assert '离照玄晶' in page.locator('#inventory-list').inner_text()
                        custom = page.locator('#inventory-list .item').filter(has_text='婴神太虚录')
                        assert custom.count() == 1
                        bottle = page.locator('#inventory-list .item').filter(has_text='麟趾玉液')
                        # Fixture inventory is deliberately old; add the new starter bottle
                        # in a second ordinary save so its renamed ID is also clickable.
                        fresh = engine._load(game.id)
                        from cultivation_life.rules import add_item
                        add_item(fresh.player, 'qilin_blessing_elixir')
                        engine.store.save(fresh)
                        page.keyboard.press('Escape')
                        page.evaluate('async id=>loadGame(id)', game.id)
                        navigation_locator(page, '[data-panel-target=inventory]').click()
                        bottle.wait_for(state='attached')
                        reveal_subpage(page, bottle)
                        bottle.wait_for(state='visible')
                        assert bottle.count() == 1
                        page.route('**/use-item', lambda route: route.continue_(post_data=json.dumps({'item_id': 'heroic_progeny_elixir'})))
                        with page.expect_response(lambda response: response.url.endswith('/use-item')) as response:
                            click_control(bottle.get_by_role('button', name='服用', exact=True))
                        assert response.value.status == 200, response.value.text()
                        page.wait_for_function('!busy && game.player.guaranteed_progeny')
                        assert bottle.count() == 0
                        saved = engine.store.load(game.id)
                        assert saved.player.technique.level == 6
                        assert next(i.quantity for i in saved.player.inventory if i.id == 'radiant_flame_crystal') == 7
                        assert next(i.quantity for i in saved.player.inventory if i.technique_id == 'TECH_YELLOW_COURT_INNER') == 1
                        assert not errors, errors
                        page.screenshot(path=str(output / 'inventory.png'))
                        (output / 'result.json').write_text(json.dumps(dict(passed=True, page_errors=errors, checks=['legacy-upgrade', 'new-labels', 'custom-name', 'special-effect', 'legacy-starter-use', 'quantities']), ensure_ascii=False, indent=2), encoding='utf-8')
                        print('Content naming browser: passed')
                    finally:
                        browser.close()
            finally:
                http.shutdown()
                http.server_close()


if __name__ == '__main__': main()
