"""Real browser interaction with isolated NPC and touch bloodline fixtures."""
import random
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
from cultivation_life.system.monster_bloodline_system import grant_random_species_bloodline_trait


class QuietHandler(server.Handler):
    def log_message(self, *args):
        pass


def main():
    with tempfile.TemporaryDirectory(dir=ROOT/'build') as directory:
        server.PERSISTENCE_ROOT = Path(directory)
        engine = server.ENGINE = GameEngine(ROOT, Path(directory)/'saves')
        shown = engine.create_game('血脉明鉴', 'supreme_water', 'monster', seed=1441, monster_species_id='serpent')
        game = engine.store.load(shown['id']); game.pending_event = None
        game.player.realm_index = 4; game.player.layer = 1; game.player.age = 330; game.player.lifespan = 2000
        grant_random_species_bloodline_trait(game.player, random.Random(8))
        game.player.faction_id = 'tianjian'
        npc = game.sects['tianjian'].npcs[0]
        game.player.master = engine._relationship_snapshot(npc.id, npc.name, npc.realm_index, npc.layer, 'tianjian', npc.age, npc.lifespan, world=npc.world)
        engine.store.save(game)
        httpd = ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        errors = []
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page(viewport={'width':412, 'height':915}, has_touch=True)
                page.on('pageerror', lambda err: errors.append(str(err)))
                page.goto(f'http://127.0.0.1:{httpd.server_port}')
                page.wait_for_function('configData !== null')
                page.evaluate('(id) => loadGame(id)', game.id)
                page.evaluate("UtilityPanels.open('bloodline')")
                chip = page.locator('#bloodline-card .bloodline-detail').first
                chip.locator('summary').tap()
                assert chip.get_attribute('open') is not None
                assert chip.locator('p').is_visible() and len(chip.locator('p').inner_text()) > 8
                page.screenshot(path=str(ROOT/'build/bloodline-touch-1440.png'))
                page.evaluate("UtilityPanels.close('bloodline'); UtilityPanels.open('relationship')")
                # The relationship panel id is resolved through its visible button.
                page.get_by_role('button', name='请教修行', exact=True).click()
                page.wait_for_function("game.history.some(r=>r.event_id==='SYS_MASTER_CONSULT')")
                assert page.get_by_role('button', name='请教修行', exact=True).is_disabled()
                page.set_viewport_size({'width':1440, 'height':1080})
                page.evaluate("UtilityPanels.close('relationship'); UtilityPanels.open('faction')")
                page.wait_for_timeout(400)
                assert '道侣' in page.locator('#faction-roster-list').inner_text()
                page.screenshot(path=str(ROOT/'build/npc-social-A-1440.png'))
                assert not errors, errors
                browser.close()
        finally:
            httpd.shutdown()
    print('NPC social, master consultation and touch bloodline UI passed')


if __name__ == '__main__':
    main()
