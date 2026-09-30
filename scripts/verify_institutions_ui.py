"""Six-theme institutions: map identity, contact actions and legacy affiliation."""
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine


class Quiet(server.Handler):
    def log_message(self, *args): pass


def main():
    with tempfile.TemporaryDirectory(dir=ROOT / 'build') as directory:
        server.PERSISTENCE_ROOT = Path(directory)
        engine = server.ENGINE = GameEngine(ROOT, Path(directory) / 'saves')
        game = engine.store.load(engine.create_game('机构往来', 'supreme_metal', 'dao', 1513,
                                                   preset_id='true_immortal')['id'])
        game.pending_event = None
        game.heavenly_court['open_election'] = None
        game.player.location_id = 'expanse_celestial_8'
        game.sects['yaochi'].kind = 'sect'
        game.player.faction_id = 'yaochi'
        game.player.faction_contribution = 231
        engine.store.save(game)
        httpd = ThreadingHTTPServer(('127.0.0.1', 0), Quiet)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        errors = []
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                page = browser.new_page()
                page.emulate_media(reduced_motion='reduce')
                page.on('pageerror', lambda err: errors.append(str(err)))
                page.goto(f'http://127.0.0.1:{httpd.server_port}')
                page.wait_for_function('configData!==null')
                page.evaluate('(id)=>loadGame(id)', game.id)
                assert page.evaluate('game.player.faction_id===null && game.player.institution_affiliations.yaochi.legacy_contribution===231')
                assert page.evaluate("game.faction.available.every(s=>!['heavenly_court','yaochi'].includes(s.id))")
                for theme in 'abcdef':
                    page.evaluate('(t)=>document.querySelector(`[data-theme-picker=dialog] [data-theme-choice=${t}]`).click()', theme)
                    page.evaluate('GameThemes.saved')
                    for width, height in [(1440,1080), (412,915), (915,412)]:
                        page.set_viewport_size(dict(width=width, height=height))
                        page.evaluate("UtilityPanels.open('map')")
                        page.get_by_role('button', name='活动与据点', exact=True).click()
                        page.get_by_role('button', name='势力驻地', exact=True).click()
                        for name in ('天庭', '瑶池'):
                            row = page.locator('.map-directory-entry').filter(has=page.locator('strong', has_text=name))
                            assert row.count() == 1 and '机构驻地' in row.inner_text()
                            assert row.locator('.map-directory-seal').inner_text() == '署'
                        page.evaluate("UtilityPanels.open('relationship')")
                        page.get_by_role('button', name='机构人物', exact=True).click()
                        assert page.locator('.contact-person').count() == 6
                        assert '机构往来' in page.locator('.contact-detail').inner_text()
                        for panel in ('relationship', 'yaochi', 'heavenly-court'):
                            page.evaluate('(p)=>UtilityPanels.open(p)', panel)
                            assert page.locator(f'#{panel}-card').evaluate('e=>e.scrollWidth<=e.clientWidth+1'), (theme,width,panel)
                        page.evaluate("UtilityPanels.open('yaochi')")
                        assert '旧制贡献 231' in page.locator('#yaochi-content').inner_text()
                        if width == 412:
                            page.screenshot(path=str(ROOT / f'build/institution-{theme}-1513.png'))
                page.evaluate("UtilityPanels.open('relationship')")
                target = page.locator('.contact-person[aria-pressed=true]').get_attribute('data-npc-id')
                before = engine._find_npc(engine.store.load(game.id), target).affinity
                page.locator('[data-contact-action=improve]').click()
                page.wait_for_function('(id)=>!busy&&game.world_npcs.some(n=>n.id===id&&n.contact_actions.improve)', arg=target)
                assert engine._find_npc(engine.store.load(game.id), target).affinity > before
                saved = engine.store.load(game.id)
                saved.player.world = 'spirit'
                saved.player.realm_index = 8
                saved.player.location_id = engine.maps.default_location('spirit')
                engine.store.save(saved)
                page.evaluate('(id)=>loadGame(id)', game.id)
                assert page.evaluate("game.world_npcs.every(n=>n.contact_source!=='institution')")
                browser.close()
            assert not errors, errors
        finally:
            httpd.shutdown()
    print('Institution UI passed: six themes, three viewports, institution maps, six officials, real contact, legacy record and same-world scope.')


if __name__ == '__main__':
    main()
