"""Real map/story/secret clicks in both pixel themes and three viewport shapes."""
import json
import sys
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
from cultivation_life.models import Technique
from cultivation_life.rules import qi_level_threshold
from cultivation_life.soul_secret_content import STORIES
from cultivation_life.soul_rules import SECRETS
from scripts.browser_navigation import navigation_locator, set_theme
from browser_building_visits import enter, choice
from browser_soul_lifecycle import select_secret


def main():
    output = ROOT / 'build/soul-scenery-ui'
    output.mkdir(parents=True, exist_ok=True)
    results = []
    with tempfile.TemporaryDirectory() as folder:
        engine = GameEngine(ROOT, Path(folder) / 'saves')
        class Quiet(server.Handler):
            def log_message(self, *args):
                pass
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', Path(folder)):
            http = ThreadingHTTPServer(('127.0.0.1', 0), Quiet)
            threading.Thread(target=http.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    page = browser.new_page()
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    base = f'http://127.0.0.1:{http.server_port}'
                    page.goto(base)
                    page.wait_for_function('!!configData&&!busy')
                    layouts = [(1440, 960), (390, 844), (844, 390)] * 2
                    for index, (key, tale) in enumerate(STORIES.items()):
                        width, height = layouts[index]
                        theme = 'light' if index < 3 else 'dark'
                        game = engine._load(engine.create_game('风景传承验收', 'supreme_metal', 'dao', 361 + index, preset_id='core')['id'])
                        game.pending_event = None
                        p = game.player
                        p.realm_index = 4
                        p.layer = 1
                        p.lifespan = 10000
                        p.location_id = tale['location']
                        if key != 'second_nascent':
                            target = key.removeprefix('path_')
                            p.path = 'ghost' if target == 'dao' else 'dao'
                            p.known_techniques.append(Technique(id='scene-' + target, name='验收传承功法', path=target))
                            p.qi_experience = {q: qi_level_threshold(10) for q in ('spirit', 'demon', 'yin')}
                        engine.store.save(game)
                        page.set_viewport_size(dict(width=width, height=height))
                        set_theme(page, theme)
                        page.evaluate('async id=>loadGame(id)', game.id)
                        page.wait_for_function('!busy&&!!game?.soul')
                        navigation_locator(page, '[data-panel-target=secret-art]').click()
                        select_secret(page, 'soul_' + key, SECRETS[key][0], known=False)
                        assert tale['name'] in page.locator('#secret-root-detail').inner_text()
                        assert page.locator('[data-soul-action=study]').count() == 0
                        assert page.locator('[data-soul-action=convert]').count() == 0
                        page.locator('#secret-art-toggle').click()
                        enter(page, 'scenery:human:' + tale['building'])
                        choice(page, 'secret:main')
                        choice(page, 'secret:read')
                        # A stale award button must recover to the authoritative page, not award.
                        if index == 0:
                            event = page.evaluate('game.pending_event.id')
                            reply = page.request.post(base + f'/api/games/{game.id}/choice', data=dict(choice_id='back', event_id=event))
                            assert reply.ok, reply.text()
                            page.locator('#event-choices button').first.click()
                            page.wait_for_function('old=>!busy&&game.pending_event.id!==old', arg=event)
                            assert key not in engine.store.load(game.id).player.nascent_state.get('known', [])
                            choice(page, 'secret:main')
                            choice(page, 'secret:read')
                        before = engine.store.load(game.id)
                        choice(page, 'secret:learn')
                        after = engine.store.load(game.id)
                        assert after.player.inventory == before.player.inventory
                        assert after.player.age == before.player.age and after.rng_state == before.rng_state
                        page.screenshot(path=str(output / f'story-{key}.png'), animations='disabled')
                        choice(page, 'secret:main')
                        choice(page, 'secret:read')
                        assert page.locator('#event-choices button').first.is_disabled()
                        choice(page, 'leave')
                        assert not page.evaluate('game.buildings.inside')
                        assert page.locator('#soul-details [data-soul-action=convert]').count() == 0
                        navigation_locator(page, '[data-panel-target=secret-art]').click()
                        select_secret(page, 'soul_' + key, SECRETS[key][0])
                        if key != 'second_nascent':
                            assert page.locator('[data-soul-action=convert]').count() == 0
                            before = engine.store._path(game.id).read_bytes()
                            page.locator('[data-soul-activate]').click()
                            assert page.locator('[data-soul-action=convert]').is_enabled()
                            assert engine.store._path(game.id).read_bytes() == before
                            if index == 0:
                                # Closing/reopening and reloading cannot retain an armed confirmation.
                                page.locator('#secret-art-toggle').click()
                                navigation_locator(page, '[data-panel-target=secret-art]').click()
                                assert page.locator('[data-soul-action=convert]').count() == 0
                                page.locator('[data-soul-activate]').click()
                                page.evaluate('async id=>loadGame(id)', game.id)
                                if not page.locator('#secret-art-card').evaluate("n=>n.classList.contains('panel-open')"):
                                    navigation_locator(page, '[data-panel-target=secret-art]').click()
                                select_secret(page, 'soul_' + key, SECRETS[key][0])
                                assert page.locator('[data-soul-action=convert]').count() == 0
                                page.locator('[data-soul-activate]').click()
                                # Another client changes the exact source resource, without a soul command.
                                current = engine.store.load(game.id)
                                original_path = current.player.path
                                current.player.qi_experience['spirit'] = 0
                                engine.store.save(current)
                                engine.get_game(game.id)
                                unchanged = engine.store._path(game.id).read_bytes()
                                with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/soul')) as response:
                                    page.locator('[data-soul-action=convert]').click()
                                assert response.value.status == 400
                                page.wait_for_function('!busy&&game.soul.conversions.find(r=>r.id==="dao").available===0')
                                assert page.evaluate('game.player.path') == original_path
                                assert page.locator('[data-soul-action=convert]').count() == 0
                                assert engine.store._path(game.id).read_bytes() == unchanged
                                page.locator('[data-soul-activate]').click()
                            assert page.locator('#secret-art-card').evaluate('n=>n.scrollWidth<=n.clientWidth+2')
                            page.screenshot(path=str(output / f'convert-{theme}-{width}.png'), animations='disabled')
                            location = page.evaluate('game.player.location_id')
                            page.locator('[data-soul-action=convert]').click()
                            page.wait_for_function('path=>!busy&&game.player.path===path', arg=target)
                            assert page.evaluate('game.player.location_id') == location
                            assert page.locator('[data-soul-action=convert]').count() == 0
                        else:
                            # An inherited secret stays visible after rank loss, but cannot refine.
                            current = engine.store.load(game.id)
                            from cultivation_life.models import SectNpc
                            npc = SectNpc('audit-lower-refine', '验收俘虏', '散修', 4, 1, 30, 10000, spirit_root='supreme_metal')
                            current.world_npcs[npc.id] = npc
                            current.player.prisoners.append(current.detain_person(npc.to_dict()))
                            current.player.realm_index = 3
                            engine.store.save(current)
                            page.evaluate('async id=>loadGame(id)', game.id)
                            navigation_locator(page, '[data-panel-target=nascent]').click()
                            assert page.locator('[data-soul-action=refine]').is_disabled()
                            page.evaluate('renderButtons()')
                            assert page.locator('[data-soul-action=refine]').is_disabled()
                        results.append(dict(secret=key, theme=theme, width=width, passed=True))
                    assert not errors, errors
                    browser.close()
            finally:
                http.shutdown()
                http.server_close()
    (output / 'report.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Scenery secrets: six real acquisitions, repeat/stale rejection and five confirmed conversions passed.', flush=True)


if __name__ == '__main__':
    main()
