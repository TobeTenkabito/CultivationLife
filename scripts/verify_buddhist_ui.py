"""A-theme live UI checks against isolated saves; never touches player progress."""
import copy
import sys
import tempfile
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.rules import add_item, learn_technique, max_hp, max_mp
from cultivation_life.content_registry import TECHNIQUE_CATALOG
from cultivation_life.system.buddhist_system import set_dharma_karma, site_state


class QuietHandler(server.Handler):
    def log_message(self, *args):
        pass


def main():
    with tempfile.TemporaryDirectory(prefix='buddhist-ui-', dir=ROOT/'build') as directory:
        isolated = Path(directory)
        server.PERSISTENCE_ROOT = isolated
        engine = server.ENGINE = GameEngine(ROOT, isolated/'data/saves')
        shown = engine.create_game('照尘', 'supreme_wood', 'buddhist', seed=111)
        game = engine._load(shown['id'])
        game.pending_event = None
        game.player.realm_index = 1; game.player.layer = 1
        game.player.hp = max_hp(game.player); game.player.mp = max_mp(game.player)
        art = copy.deepcopy(next(row for row in TECHNIQUE_CATALOG.values() if row.path == 'buddhist'))
        art.level = 7
        learn_technique(game.player, art)
        game.buddhist_state["wish"]["value"] = 100
        set_dharma_karma(game, 48)
        site_state(game.buddhist_state, 'human', game.player.location_id).update(temple=2, followers=680)
        add_item(game.player, 'spirit_stone', 100_000)
        engine.store.save(game)
        httpd = ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
        worker = threading.Thread(target=httpd.serve_forever, daemon=True); worker.start()
        base = f'http://127.0.0.1:{httpd.server_port}'
        errors = []
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                page = browser.new_page(viewport={'width':1440, 'height':1080}, device_scale_factor=1)
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(base)
                page.wait_for_function('configData !== null')
                page.evaluate('(id) => loadGame(id)', game.id)
                wish_dock = page.locator('[data-panel-target="buddhist-wish"]')
                assert wish_dock.evaluate('(n) => !!n.closest(".left-dock")')
                wish_dock.click()
                wish_panel = page.locator('#buddhist-wish-card')
                wish_panel.wait_for(state='visible')
                assert wish_panel.get_by_role('progressbar', name='愿力').get_attribute('value') == '100'
                assert wish_panel.evaluate('(p) => p.scrollWidth <= p.clientWidth + 2')
                page.screenshot(path=str(ROOT/'build/buddhist-wish-A-1430.png'))
                wish_panel.get_by_role('button', name='消耗 100 愿力 · 涅槃').click()
                page.wait_for_function('game.player.layer === 2 && game.buddhist_system.wish.value === 0')
                assert engine.store.load(game.id).buddhist_state['wish']['nirvana_units'] == 3
                page.locator('[data-panel-target="buddhist"]').click()
                panel = page.locator('#buddhist-card')
                panel.wait_for(state="visible", timeout=5000)
                assert panel.get_by_role('meter', name='业力').get_attribute('aria-valuenow') == '48'
                assert panel.locator('.dharma-blessing').count() == 6
                panel.locator('.dharma-blessing').first.click()
                page.wait_for_function('game.buddhist_system.blessings[0].selected')
                assert panel.locator('.dharma-blessing.selected').count() == 1
                page.screenshot(path=str(ROOT/'build/buddhist-A-1430.png'))
                assert panel.evaluate('(p) => p.scrollWidth <= p.clientWidth + 2')
                panel.get_by_role('button', name='开坛弘法', exact=True).click()
                page.wait_for_function('game.pending_event?.id.startsWith("EVT_DHARMA_")')
                assert engine.store.load(game.id).buddhist_state['assembly']['pending']
                # The server and the UI both retain the same event after reload.
                event_id = engine.store.load(game.id).pending_event['id']
                page.reload(); page.wait_for_function('configData !== null')
                page.evaluate('(id) => loadGame(id)', game.id)
                assert page.evaluate('game.pending_event.id') == event_id
                # Validate the actual shared inventory button, including mutated-root manuals.
                other = engine.create_game('补灵验收', 'supreme_wood', 'dao', seed=1420)
                books = engine._load(other['id']); books.pending_event = None
                books.player.world = 'monster_realm'; books.player.location_id = engine.maps.default_location('monster_realm')
                books.player.realm_index = 5; books.player.layer = 1
                add_item(books.player, 'yaoque_water'); add_item(books.player, 'yaoque_thunder')
                engine.store.save(books)
                page.evaluate('(id) => loadGame(id)', books.id)
                page.locator('[data-panel-target="inventory"]').click()
                page.locator('#inventory-card').get_by_role('button', name='参悟', exact=True).first.click()
                page.wait_for_function('game.player.additional_roots.length > 0')
                assert engine.store.load(books.id).player.additional_roots
                world_run = engine.create_game('轮回验收', 'supreme_water', 'dao', seed=1430)
                world_save = engine._load(world_run['id']); world_save.pending_event = None
                world_save.player.world = 'reincarnation'
                world_save.player.location_id = engine.maps.default_location('reincarnation')
                world_save.player.realm_index = 9; world_save.player.layer = 1
                engine.store.save(world_save)
                page.evaluate('(id) => loadGame(id)', world_save.id)
                page.locator('[data-panel-target="map"]').click()
                page.locator('#map-card').wait_for(state='visible')
                assert page.evaluate('game.map.locations.length') == 10
                assert page.locator('#map-card').get_by_text('莲灯山', exact=True).count() > 0
                page.screenshot(path=str(ROOT/'build/reincarnation-map-A-1430.png'))
                assert not errors, errors
                browser.close()
        finally:
            httpd.shutdown(); httpd.server_close(); worker.join(timeout=5)
        print('passed: A-theme left wish panel, live one-layer nirvana, Dharma panel, blessing toggle, saved assembly event, live root-book button, reincarnation map; no JavaScript errors')


if __name__ == '__main__':
    main()
