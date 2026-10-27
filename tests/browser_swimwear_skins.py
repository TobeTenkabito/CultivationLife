"""Real wardrobe clicks, reload, rank rejection and settled-battle skin rendering."""
import json
import random
import sys
import tempfile
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cultivation_life import server
from cultivation_life.engine import GameEngine
from playwright.sync_api import sync_playwright
from scripts.browser_navigation import navigation_locator


def main():
    out = ROOT / 'build/swimwear-ui'
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT / 'build') as folder:
        engine = GameEngine(ROOT, Path(folder) / 'saves')
        class Quiet(server.Handler):
            def log_message(self, *args): pass
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', Path(folder)):
            http = ThreadingHTTPServer(('127.0.0.1', 0), Quiet)
            threading.Thread(target=http.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{http.server_port}'
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    page = browser.new_page(viewport=dict(width=1440, height=960), reduced_motion='reduce')
                    errors = []
                    page.on('pageerror', lambda e: errors.append(str(e)))
                    page.goto(base)
                    page.wait_for_function('!!configData&&!busy')
                    page.locator('#theme-open').click()
                    page.locator('#theme-dialog [data-pixel-setting]').set_checked(True)
                    page.evaluate('GameThemes.saved')
                    page.locator('[data-close-dialog=theme-dialog]').click()
                    for style, gender, path in [('sunny', 'female', 'dao'), ('sunny', 'male', 'demonic'),
                                                ('moon', 'female', 'monster'), ('moon', 'male', 'ghost')]:
                        rank = 4 if style == 'sunny' else 5
                        made = engine.create_game('沧海游衣', 'supreme_metal', 'dao', 327, gender=gender,
                                                  custom_start=dict(world='human' if rank == 4 else 'spirit', realm_index=rank))
                        game = engine._load(made['id'])
                        # Disposable fixtures exercise nonhuman and optional paths without touching user saves.
                        game.player.path = path
                        game.player.race = 'monster' if path == 'monster' else 'human'
                        game.player.lineage_race = game.player.race
                        game.pending_event = None
                        engine.store.save(game)
                        page.evaluate('id=>loadGame(id)', game.id)
                        page.wait_for_function('!busy')
                        actor = f'swim-{style}-{gender}'
                        key = 'actor.cosmetic.' + actor
                        page.locator('.hud-identity').click()
                        page.locator('#character-skins').evaluate('node=>node.open=false')
                        page.locator('#character-skins summary').click()
                        if style == 'sunny':
                            moon = f'actor.cosmetic.swim-moon-{gender}'
                            locked = page.locator(f'[data-skin-id="{moon}"]')
                            assert locked.is_disabled() and '化神期解锁' in locked.inner_text()
                            saved = engine.store._path(game.id).read_bytes()
                            response = page.request.post(f'{base}/api/games/{game.id}/character-skin', data=dict(skin_id=moon))
                            assert response.status == 400
                            assert engine.store._path(game.id).read_bytes() == saved
                        page.locator(f'[data-skin-id="{key}"]').click()
                        page.wait_for_function('key=>!busy&&game.player.character_skins.selected===key', arg=key)
                        page.wait_for_function('key=>document.querySelector(".pixel-details-art canvas").dataset.actor===key', arg=key)
                        page.wait_for_function('actor=>{const im=document.querySelector(".pixel-portrait");return im.complete&&im.naturalWidth===128&&im.src.includes(actor+"-portrait.png")}', arg=actor)
                        for width in (1440, 390, 320, 844):
                            page.set_viewport_size(dict(width=width, height=960 if width == 1440 else 844 if width < 400 else 390))
                            page.locator(f'[data-skin-id="{key}"]').scroll_into_view_if_needed()
                            assert page.locator('#player-details-dialog').evaluate('d=>d.scrollWidth<=d.clientWidth+1')
                            page.wait_for_function('Array.from(document.querySelectorAll(".skin-gallery img")).every(im=>im.complete&&im.naturalWidth>0)')
                            page.screenshot(path=str(out / f'{actor}-{width}.png'))
                        page.locator('[data-close-dialog=player-details-dialog]').click()
                        page.reload()
                        page.wait_for_function('!!configData&&!busy')
                        page.evaluate('id=>loadGame(id)', game.id)
                        page.wait_for_function('key=>game.player.visual_actor===key', arg=key)
                        # Play a real settled fight; seek exercises all selected character assets and defeat endpoint.
                        battle = engine._load(game.id)
                        battle.pending_event = None
                        engine._combat(battle, dict(target_name='演武灵兽', combat_type='beast',
                            target_realm_index=rank, target_power=engine._player_battle_power(battle)*2.5),
                            False, random.Random(327))
                        assert battle.last_combat_report['visual']['hero'] == actor
                        engine.store.save(battle)
                        page.set_viewport_size(dict(width=1440, height=960))
                        page.evaluate('id=>loadGame(id)', game.id)
                        navigation_locator(page, '#battle-report-open').click()
                        page.wait_for_function('CombatReplay.diagnostics().active&&!document.querySelector("[data-combat-replay]").disabled')
                        for at in (0, 1.5, 2.1, 10000):
                            page.evaluate('at=>CombatReplay.seek(at)', at)
                            info = page.evaluate('CombatReplay.diagnostics()')
                            assert info['actors']['hero']['id'] == actor
                            assert info['decodedBytes'] < 64*1024*1024
                        page.screenshot(path=str(out / f'{actor}-combat.png'))
                        page.locator('#battle-report-toggle').click()
                    assert not errors, errors
                    browser.close()
            finally:
                http.shutdown()
                http.server_close()
    result = dict(status='passed', forms=4, real_skin_commands=True, reload=True, rank_rejection=True,
                  widths=[1440, 390, 320, 844], real_battle_replays=4)
    (out / 'validation.json').write_text(json.dumps(result, indent=2), encoding='utf8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
