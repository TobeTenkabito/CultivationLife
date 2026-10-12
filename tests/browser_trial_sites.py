"""Real HTTP and map/page clicks for eleven DLC trial worlds."""
import copy
import json
import random
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
from cultivation_life.rules import max_hp, max_mp
from cultivation_life.system import trial_sites
from cultivation_life.trial_site_schema import REALM_ROWS, WORLD_TIERS


def fixture(engine, world, remote=False):
    game = engine.store.load(engine.create_game('地图试境', 'heavenly', 'dao', 341, preset_id='core')['id'])
    game.player.world = world
    game.player.realm_index, game.player.layer = (9, 1) if world == 'celestial' else (3, 1)
    game.player.immortal_power_converted = True
    game.player.opportunity = 0
    game.player.hp, game.player.mp = max_hp(game.player), max_mp(game.player)
    game.settings['silent_events'] = True
    game.settings['combat_popup'] = False
    site = trial_sites.bound_site(game, engine.maps, world)
    game.player.location_id = site['location_id'] if not remote else next(r['id'] for r in engine.maps.worlds[world]['locations'] if r['id'] != site['location_id'])
    engine.store.save(game)
    engine.get_game(game.id)
    return engine.store.load(game.id)


def click_action(page, name):
    page.locator(f'#trial-site-panel [data-trial-action="{name}"]').click()
    page.wait_for_function('!busy')


def click_choice(page, name):
    page.locator(f'#trial-site-panel [data-trial-choice="{name}"]').click()
    page.wait_for_function('!busy')


def open_site(page):
    page.evaluate("UtilityPanels.open('map')")
    marker = page.locator('[data-trial-site]')
    assert marker.count() == 1
    marker.click()
    page.locator('#trial-site-panel').wait_for(state='visible')
    page.wait_for_function("getComputedStyle(document.querySelector('#trial-site-card')).opacity === '1'")


def main():
    output = ROOT / 'build/trial-sites-browser'
    output.mkdir(parents=True, exist_ok=True)
    evidence = []
    with tempfile.TemporaryDirectory() as folder:
        engine = GameEngine(ROOT, Path(folder) / 'saves')

        class Handler(server.Handler):
            def log_message(self, *args):
                pass

        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', Path(folder)):
            httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    cases = [(theme, world, width, height) for theme in ('a','b','d','f')
                             for world in ('human','spirit','celestial') for width,height in ((393,852),(852,393),(1440,960))]
                    cases += [('abdf'[index % 4], world, 393, 852) for index,world in enumerate(REALM_ROWS)
                              if world not in {'human','spirit','celestial'}]
                    for theme,world,width,height in cases:
                        page = browser.new_page(viewport=dict(width=width, height=height))
                        errors, posts = [], []
                        page.on('pageerror', lambda error: errors.append(str(error)))
                        page.on('request', lambda request: posts.append(request.post_data_json)
                                if request.method == 'POST' and request.url.endswith(('/choice', '/trial-site-action')) else None)
                        page.goto(f'http://127.0.0.1:{httpd.server_port}')
                        page.wait_for_function('window.GameThemes && configData')
                        page.locator(f'[data-theme-picker=start] [data-theme-choice={theme}]').click()
                        game = fixture(engine, world)
                        original = game.to_dict()
                        page.evaluate('async id => loadGame(id)', game.id)
                        open_site(page)
                        assert page.locator('.trial-site-floor').count() == len(REALM_ROWS[world])
                        assert '探索零耗时' in page.locator('#trial-site-panel').inner_text()
                        assert page.locator('.trial-progress').count() == 1
                        if width >= 1000:
                            page.locator('#trial-site-toggle').click()
                            shortcut = page.locator('#strategy-dock [data-panel-target="trial-site"]')
                            assert shortcut.is_visible()
                            assert page.evaluate("getComputedStyle(document.querySelector('[data-panel-target=trial-site]')).backgroundImage.includes('linear-gradient')")
                            shortcut.click()
                        page.screenshot(path=str(output / f'{world}-{theme}-{width}-layers.png'))
                        click_action(page, 'enter')
                        assert page.evaluate('game.pending_event.id.startsWith("SYS_TRIAL_SITE_")')
                        assert page.locator('.trial-mechanism').count() == 5
                        assert page.locator('.trial-meter-track').count() == 2
                        assert page.evaluate('game.trial_site.session.name') in page.locator('.trial-session-heading').inner_text()
                        page.screenshot(path=str(output / f'{world}-{theme}-{width}-event.png'))
                        blueprint = copy.deepcopy(engine.store.load(game.id).trial_site_state)
                        page.reload()
                        page.wait_for_function('configData')
                        page.evaluate('async id => loadGame(id)', game.id)
                        open_site(page)
                        assert engine.store.load(game.id).trial_site_state == blueprint

                        # Submit one actual choice outside the stale UI,
                        # then prove one old click only refreshes it.
                        old = page.evaluate('game.pending_event.id')
                        engine.choose(game.id, 'c', event_id=old)
                        engine.get_game(game.id)
                        raw = engine.store._path(game.id).read_bytes()
                        count = len(posts)
                        click_choice(page, 'c')
                        assert len(posts) == count + 1
                        assert engine.store._path(game.id).read_bytes() == raw
                        assert page.evaluate('game.trial_site.session.event_index') == 1

                        # Disabled options stay disabled after a real
                        # reload; both paid routes use the same gate.
                        saved = engine.store.load(game.id)
                        hp, mp = saved.player.hp, saved.player.mp
                        saved.player.hp, saved.player.mp = 1., 0.
                        engine.store.save(saved)
                        page.evaluate('async id => loadGame(id)', game.id)
                        assert page.locator('[data-trial-choice="a"]').is_disabled()
                        assert page.locator('[data-trial-choice="b"]').is_disabled()
                        assert page.locator('[data-trial-choice="pause"]').is_enabled()
                        saved = engine.store.load(game.id)
                        saved.player.hp, saved.player.mp = hp, mp
                        engine.store.save(saved)
                        page.evaluate('async id => loadGame(id)', game.id)
                        click_choice(page, 'pause')
                        assert not page.evaluate('game.trial_site.active')
                        click_action(page, 'enter')
                        assert page.evaluate('game.trial_site.session.event_index') == 1

                        # Every remaining node is chosen through a
                        # visible real button, using test-only truth.
                        for _ in range(4):
                            saved = engine.store.load(game.id)
                            _, floor = trial_sites.current(saved)
                            outcomes = trial_sites.situation(floor)[2]
                            choice = min(outcomes, key=lambda key: (outcomes[key][2], outcomes[key][3].get('treasure') is False))
                            click_choice(page, choice)
                        assert page.evaluate('game.trial_site.session.status') == 'ready'
                        assert not page.evaluate('busy')
                        page.screenshot(path=str(output / f'{world}-{theme}-{width}.png'))
                        click_action(page, 'fight')
                        assert page.evaluate('game.trial_site.session.status') == 'won'
                        click_action(page, 'claim')
                        assert page.evaluate('game.trial_site.cleared') == 1
                        assert not page.evaluate('game.trial_site.active')
                        assert engine.store.load(game.id).player.age == original['player']['age']
                        assert engine.store.load(game.id).diplomacy_unit == original['diplomacy_unit']
                        assert not errors, errors
                        evidence.append(dict(world=world, theme=theme, width=width, height=height, passed=True))
                        print(f'Trial map UI passed: {world} {theme} {width}x{height}', flush=True)
                        page.close()
                    # An icon elsewhere on the same world map provides details,
                    # while its real challenge button remains unavailable.
                    page = browser.new_page()
                    game = fixture(engine, 'human', remote=True)
                    page.goto(f'http://127.0.0.1:{httpd.server_port}')
                    page.wait_for_function('configData')
                    page.evaluate('async id => loadGame(id)', game.id)
                    open_site(page)
                    assert page.locator('[data-trial-action="enter"]').is_disabled()
                    assert not engine.store.load(game.id).trial_site_state
                    # Shortcut uses normal travel; after a real trip, the
                    # current layer can start without any implicit teleport.
                    before_age = game.player.age
                    page.locator('[data-trial-travel]').click()
                    page.wait_for_function('!busy')
                    assert page.evaluate('game.player.location_id === game.trial_site.location_id')
                    assert engine.store.load(game.id).player.age > before_age
                    assert not engine.store.load(game.id).trial_site_state
                    click_action(page, 'enter')
                    assert page.evaluate('game.trial_site.active')
                    with patch.object(trial_sites, 'enabled', lambda: False):
                        page.evaluate('async id => loadGame(id)', game.id)
                        page.locator('[data-panel-target="trial-site"]').wait_for(state='hidden')
                        page.locator('#trial-site-card').wait_for(state='hidden')
                        assert not engine.store.load(game.id).trial_site_state['active']
                    page.evaluate('async id => loadGame(id)', game.id)
                    open_site(page)
                    click_action(page, 'enter')
                    assert page.evaluate('game.trial_site.session.event_index') == 0
                    page.close()
                    browser.close()
            finally:
                httpd.shutdown()
                httpd.server_close()
    (output / 'report.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf8')
    print(f'Trial sites UI passed: {len(evidence)} world/theme/viewport cases; visual floors, shortcut, normal travel, DLC freeze/re-enable, five choices, combat, rewards and zero time')


if __name__ == '__main__':
    main()
