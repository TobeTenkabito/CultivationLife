"""Real server, portrait/detail clicks and settled Asura battles at two viewport sizes."""
import json
import math
import random
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
from scripts.browser_navigation import navigation_locator
from cultivation_life.rules import max_hp, max_mp


def verify(page, engine, identity, out):
    page.evaluate('GameThemes.ready')
    page.locator('#theme-open').click()
    page.locator('#theme-dialog [data-pixel-setting]').set_checked(True)
    page.evaluate('GameThemes.saved')
    page.locator('[data-close-dialog=theme-dialog]').click()
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    for gender in ['male', 'female']:
        game = engine.store.load(identity)
        game.player.gender = gender
        game.player.hp, game.player.mp = max_hp(game.player), max_mp(game.player)
        game.pending_event = None
        game.settings.update(silent_events=True, combat_popup=True)
        engine._combat(game, dict(target_name='修罗心魔演武', path='demonic', gender=gender, race='human',
            combat_type='trial', visual_variant='heart_demon', target_realm_index=9,
            target_power=engine._player_battle_power(game)*.5), False, random.Random(613))
        engine.store.save(game)
        actor = 'asura-hero-'+gender
        for width, height in [(1440, 960), (390, 844)]:
            page.set_viewport_size(dict(width=width, height=height))
            page.evaluate('id=>loadGame(id)', identity)
            page.wait_for_function('id=>game.player.visual_actor==="actor.path."+id', arg=actor)
            page.wait_for_function('id=>{const im=document.querySelector(".pixel-portrait");return im?.complete&&im.naturalWidth===128&&im.src.includes(id+"-portrait.png")}', arg=actor)
            if page.locator('#battle-report-card').is_visible():
                page.locator('#battle-report-toggle').click()
            page.locator('.hud-identity').click()
            page.wait_for_function('id=>document.querySelector(".pixel-details-art canvas")?.dataset.actor==="actor.path."+id', arg=actor)
            page.screenshot(path=str(out/f'{actor}-detail-{width}.png'))
            page.locator('[data-close-dialog=player-details-dialog]').click()
            navigation_locator(page, '#battle-report-open').click()
            page.wait_for_function('CombatReplay.diagnostics().active&&!document.querySelector("[data-combat-replay]").disabled')
            before = page.evaluate('JSON.stringify(game)')
            saved = engine.store._path(identity).read_bytes()
            page.evaluate('''for(let t=0;t<=CombatReplay.diagnostics().duration;t+=.25){
                CombatReplay.seek(t);
                const d=CombatReplay.diagnostics();
                if(!d.participants.every(p=>p.bounds.every(Number.isFinite)))throw Error('Invalid character bounds');
            }''')
            page.evaluate('CombatReplay.seek(2.1)')
            diag = page.evaluate('CombatReplay.diagnostics()')
            (out/f'{actor}-diagnostics-{width}.json').write_text(json.dumps(diag, indent=2), encoding='utf8')
            for participant in diag['participants']:
                assert all(isinstance(v, (int, float)) and math.isfinite(v) for v in participant['bounds']), participant
            assert diag['actors']['hero']['id'] == diag['actors']['npc']['id'] == actor
            assert diag['decodedBytes'] < 64*1024*1024
            assert page.evaluate('JSON.stringify(game)') == before
            assert engine.store._path(identity).read_bytes() == saved
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
            page.screenshot(path=str(out/f'{actor}-battle-{width}.png'))
            page.locator('#battle-report-toggle').click()
    assert not errors, errors
    return dict(forms=2, viewports=[1440, 390], details=True, real_settled_battles=True,
                mirror_playback=True, read_only=True, page_errors=errors)


def main():
    from playwright.sync_api import sync_playwright
    from cultivation_life import server
    from cultivation_life.engine import GameEngine
    out = ROOT/'build/asura-characters'
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        engine = GameEngine(ROOT, Path(folder)/'saves')
        made = engine.create_game('修罗立绘验收', 'heavenly', 'demonic', seed=613, preset_id='asura_upper')
        class Handler(server.Handler):
            def log_message(self, *args):
                pass
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', Path(folder)):
            http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            threading.Thread(target=http.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    page = browser.new_page(viewport=dict(width=1440, height=960), reduced_motion='reduce')
                    page.goto(f'http://127.0.0.1:{http.server_port}')
                    page.wait_for_function('typeof configData!=="undefined" && !!configData')
                    result = verify(page, engine, made['id'], out)
                    browser.close()
            finally:
                http.shutdown()
                http.server_close()
    (out/'validation.json').write_text(json.dumps(result, indent=2), encoding='utf8')
    print(result)


if __name__ == '__main__':
    main()
