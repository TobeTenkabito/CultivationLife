"""Real skin commands, reload, render, failures, and mobile character details."""
import copy
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
    output = ROOT / 'build/release-301-ui'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT / 'build') as folder:
        engine = GameEngine(ROOT, Path(folder) / 'saves')
        made = engine.create_game('换装验收', 'supreme_metal', 'dao', 301, gender='female', custom_start=dict(world='spirit', realm_index=7))
        game = engine._load(made['id'])
        game.pending_event = None
        engine.store.save(game)
        engine.get_game(game.id)
        baseline = engine.store.load(game.id).to_dict()
        class Quiet(server.Handler):
            def log_message(self, *args): pass
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', Path(folder)):
            http = ThreadingHTTPServer(('127.0.0.1', 0), Quiet)
            threading.Thread(target=http.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    page = browser.new_page(viewport=dict(width=1440, height=960))
                    errors = []
                    page.on('pageerror', lambda e: errors.append(str(e)))
                    page.goto(f'http://127.0.0.1:{http.server_port}')
                    page.wait_for_function('!!configData&&!busy')
                    page.evaluate('async id=>loadGame(id)', game.id)
                    page.locator('#theme-open').click()
                    page.locator('#theme-dialog [data-pixel-setting]').set_checked(True)
                    page.evaluate('GameThemes.saved')
                    page.locator('[data-close-dialog=theme-dialog]').click()
                    for width in [1440, 390, 320]:
                        page.set_viewport_size(dict(width=width, height=960 if width > 400 else 844))
                        page.locator('.hud-identity').click()
                        page.wait_for_function('!document.querySelector(".pixel-details-art").hidden')
                        page.screenshot(path=str(output / f'wardrobe-entry-{width}.png'))
                        bounds=page.locator('#character-skins-open').evaluate('button=>({button:button.getBoundingClientRect().toJSON(),art:document.querySelector(".pixel-details-art").getBoundingClientRect().toJSON(),height:innerHeight})')
                        b,art=bounds['button'],bounds['art']
                        assert b['top']>=art['bottom'] and b['top']-art['bottom']<30 and b['right']<=art['right'] and b['left']>=art['left'] and b['bottom']<=bounds['height'],bounds
                        page.locator('#character-skins-open').click()
                        page.keyboard.press('Escape')
                        assert page.locator('#player-details-dialog').evaluate('d=>d.open')
                        assert page.locator('#character-skins-open').evaluate('b=>document.activeElement===b')
                        page.locator('#character-skins-open').click()
                        page.locator('[data-skin-id="actor.path.dao-nascent-hero-female"]').click()
                        page.wait_for_function('!busy&&game.player.character_skins.selected==="actor.path.dao-nascent-hero-female"')
                        page.wait_for_function('document.querySelector(".pixel-details-art canvas").dataset.actor==="actor.path.dao-nascent-hero-female"')
                        assert page.locator('#character-skins').evaluate('d=>d.scrollWidth<=d.clientWidth+1')
                        assert page.locator('.skin-gallery img').evaluate_all('xs=>xs.every(x=>x.complete&&x.naturalWidth>0)')
                        page.screenshot(path=str(output / f'skins-{width}.png'))
                        page.locator('[data-skin-id=""]').click()
                        page.wait_for_function('!busy&&!game.player.character_skins.selected')
                        page.locator('#character-skins-close').click()
                        page.locator('[data-close-dialog=player-details-dialog]').click()
                    # The entry is also available when artwork is turned off.
                    page.locator('#theme-open').click()
                    page.locator('#theme-dialog [data-pixel-setting]').set_checked(False)
                    page.evaluate('GameThemes.saved')
                    page.locator('[data-close-dialog=theme-dialog]').click()
                    page.locator('.hud-identity').click()
                    page.locator('#character-skins-open').click()
                    assert page.locator('#character-skins').evaluate('d=>d.open')
                    page.locator('#character-skins-close').click()
                    page.locator('[data-close-dialog=player-details-dialog]').click()
                    page.locator('#theme-open').click()
                    page.locator('#theme-dialog [data-pixel-setting]').set_checked(True)
                    page.evaluate('GameThemes.saved')
                    page.locator('[data-close-dialog=theme-dialog]').click()
                    # Invalid real command must leave selection and gameplay untouched.
                    response = page.request.post(f'http://127.0.0.1:{http.server_port}/api/games/{game.id}/character-skin', data=dict(skin_id='locked'))
                    assert response.status == 400
                    after = engine.store.load(game.id).to_dict()
                    for row in (baseline, after):
                        row.pop('updated_at', None)
                        row['player'].pop('character_skins', None)
                    assert baseline == after
                    # Real battle reports must use each new actor and decode its
                    # action sheet, including the terminal defeat pose.
                    page.set_viewport_size(dict(width=1440, height=960))
                    for path in ('dao', 'demonic'):
                        for gender in ('male', 'female'):
                            for realm, stage in ((4, 'nascent'), (7, 'integration')):
                                created = engine.create_game('动作验收', 'supreme_metal', path, 301, gender=gender,
                                    custom_start=dict(world='human' if realm == 4 else 'spirit', realm_index=realm))
                                battle = engine._load(created['id'])
                                battle.pending_event = None
                                actor = f'{path}-{stage}-hero-{gender}'
                                engine._combat(battle, dict(target_name='演武对手',
                                    target_power=engine._player_battle_power(battle)*2.5,
                                    target_realm_index=realm, combat_type='cultivator', path=path, gender=gender),
                                    path == 'demonic', random.Random(81))
                                assert battle.last_combat_report['visual']['hero'] == actor
                                engine.store.save(battle)
                                page.evaluate('id=>loadGame(id)', battle.id)
                                navigation_locator(page, '#battle-report-open').click()
                                try:
                                    page.wait_for_function('CombatReplay.diagnostics().active && !document.querySelector("[data-combat-replay]").disabled')
                                except Exception:
                                    print(json.dumps(dict(actor=actor, errors=errors, diagnostics=page.evaluate('CombatReplay.diagnostics()'), text=page.locator('#battle-report-card').inner_text()), ensure_ascii=False), flush=True)
                                    page.screenshot(path=str(output / 'combat-failure.png'))
                                    raise
                                for at in (2, 10000):
                                    page.evaluate('at=>CombatReplay.seek(at)', at)
                                    info = page.evaluate('CombatReplay.diagnostics()')
                                    assert info['actors']['hero']['id'] == actor, info
                                    bounds = info['bounds']['hero']
                                    assert bounds[0]>=0 and bounds[1]>=0 and bounds[2]<=info['viewport'][0] and bounds[3]<=info['viewport'][1], info
                                assert info['actors']['hero']['mode'] == 'defeat', info
                                page.screenshot(path=str(output / f'combat-{actor}.png'))
                                page.keyboard.press('Escape')
                    assert not errors, errors
                    browser.close()
            finally:
                http.shutdown()
                http.server_close()
    print(json.dumps(dict(status='passed', real_skin_commands=True, responsive_widths=[1440,390,320], unchanged_gameplay=True, real_battle_actors=8)))


if __name__ == '__main__': main()
