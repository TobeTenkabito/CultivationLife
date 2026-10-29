"""Real upper-panel navigation and commands without drawing sibling hidden panels."""
import json
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys
import tempfile
import threading
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cultivation_life import server
from cultivation_life.engine import GameEngine
from playwright.sync_api import sync_playwright
from scripts.browser_navigation import navigation_locator
from scripts.release_evidence import inputs_digest

ROOTS = {name: f'#{name}-content' for name in [
    'heavens', 'immortal-conversion', 'doctrine', 'immortal-veins', 'immortal-body',
    'voisinage', 'daomen', 'golden-light', 'yaochi', 'intrigue',
    'asura-conversion', 'asura-body', 'asura-veins', 'asura-route', 'asura-domain', 'asura-powers']}
ROOTS.update(sage='#sage-doctrine-list', **{'sage-inner-outer': '#sage-outer-list'})


def open_panel(page, name):
    navigation_locator(page, f'[data-panel-target="{name}"]').click()
    page.wait_for_selector(f'#{name}-card.panel-open')


def counts(page):
    # Deliver MutationObserver callbacks before comparing each independent root.
    return page.evaluate('async()=>{await Promise.resolve();return {...panelWrites};}')


def observe(page):
    page.evaluate('''roots=>{
      window.panelWrites=Object.fromEntries(Object.keys(roots).map(name=>[name,0]));
      for(const [name,selector] of Object.entries(roots)){
        const root=document.querySelector(selector);if(!root)throw new Error(selector);
        new MutationObserver(changes=>panelWrites[name]+=changes.length)
          .observe(root,{childList:true,subtree:true});
      }
    }''', ROOTS)


def verify(page, engine, identity, preset, output):
    observe(page)
    page.evaluate('id=>loadGame(id)', identity)
    assert not any(counts(page).values()), ('Hidden panel drew on load', counts(page))
    disk = engine.store._path(identity).read_bytes()
    metadata = engine.achievements.metadata.path.read_bytes()
    for name in ROOTS:
        if page.locator(f'#{name}-card').evaluate("n=>n.classList.contains('hidden')"):
            continue
        before = counts(page)
        open_panel(page, name)
        after = counts(page)
        assert after[name] > before[name], (preset, name, 'First open did not draw')
        assert all(after[other] == before[other] for other in ROOTS if other != name), (preset, name, before, after)
        page.keyboard.press('Escape')
    before = counts(page)
    page.evaluate('id=>loadGame(id)', identity)
    assert before == counts(page), 'Visited hidden panels rebuilt during a new response'
    assert engine.store._path(identity).read_bytes() == disk
    assert engine.achievements.metadata.path.read_bytes() == metadata

    # Use the original command, not an internal settlement function.
    if preset == 'true_immortal':
        open_panel(page, 'immortal-conversion')
        before = counts(page)
        stage = page.evaluate('game.doctrines.conversion.stage')
        control = page.locator('#immortal-conversion-content [data-doctrine-action=convert]')
        assert control.is_enabled()
        with page.expect_response(lambda r: r.url.endswith('/doctrine-action')) as submitted:
            control.click()
        assert submitted.value.ok, submitted.value.text()
        page.wait_for_function('stage=>!busy&&game.doctrines.conversion.stage===stage+1', arg=stage)
        after = counts(page)
        assert after['immortal-conversion'] > before['immortal-conversion']
        assert all(after[n] == before[n] for n in ROOTS if n != 'immortal-conversion')
        page.keyboard.press('Escape')
        open_panel(page, 'immortal-veins')
        assert '已开仙脉' in page.locator('#immortal-veins-content').inner_text()
        page.keyboard.press('Escape')
    if preset == 'confucian_void':
        open_panel(page, 'sage')
        before = counts(page)
        with page.expect_response(lambda r: r.url.endswith('/sage-doctrine')) as submitted:
            page.locator('#sage-doctrine-list').get_by_role('button', name='加入', exact=True).first.click()
        assert submitted.value.ok, submitted.value.text()
        page.wait_for_function('!busy&&!!game.sage_system.membership_id')
        after = counts(page)
        assert after['sage'] > before['sage'] and after['sage-inner-outer'] == before['sage-inner-outer']
        page.keyboard.press('Escape')
        open_panel(page, 'sage-inner-outer')
        assert page.locator('#sage-outer-list .sage-inner-outer-action[data-available="0"]').evaluate_all('ns=>ns.length>0&&ns.every(n=>n.disabled)')
        page.keyboard.press('Escape')

    if preset == 'asura_upper':
        open_panel(page, 'asura-conversion')
        before = counts(page)
        stage = page.evaluate('game.asura.conversion')
        with page.expect_response(lambda r: r.url.endswith('/asura')) as submitted:
            page.locator('#asura-conversion-content [data-asura-action=convert]').click()
        assert submitted.value.ok, submitted.value.text()
        page.wait_for_function('stage=>!busy&&game.asura.conversion===stage+1', arg=stage)
        after = counts(page)
        assert after['asura-conversion'] > before['asura-conversion']
        assert all(after[n] == before[n] for n in ROOTS if n != 'asura-conversion')
        page.keyboard.press('Escape')

    # Navigation stays disabled while a real action request is pending.
    held = []
    url = f'**/api/games/{identity}/advance'
    page.route(url, lambda route: held.append(route))
    page.locator('[data-action=rest]').click()
    page.wait_for_function('busy')
    assert held
    for name in ROOTS:
        assert page.locator(f'[data-panel-target="{name}"]').is_disabled(), name
    before = counts(page)
    held.pop().continue_()
    page.unroute(url)
    page.wait_for_function('!busy')
    assert before == counts(page), 'Hidden panel drew when the action completed'
    assert page.locator('[data-panel-target=heavens]').is_enabled()

    # Settings belongs to its own existing navigation even while heavens is closed.
    open_panel(page, 'settings')
    assert page.locator('#settings-heavens input[type=checkbox]').count() == 3
    assert counts(page)['heavens'] == before['heavens']
    page.keyboard.press('Escape')
    for width, height in [(1440, 960), (390, 844), (844, 390)]:
        page.set_viewport_size(dict(width=width, height=height))
        # Responsive navigation changes on animation frames. Observe its final
        # layout before choosing the actual visible desktop/category control.
        page.evaluate('()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
        open_panel(page, 'heavens')
        assert page.locator('#heavens-content [role=tablist]').count() > 0
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        page.screenshot(path=str(output / f'{preset}-{width}.png'))
        page.keyboard.press('Escape')


def main():
    output = ROOT / 'build/hidden-panels-round2-20261029/browser'
    output.mkdir(parents=True, exist_ok=True)
    signature = inputs_digest(ROOT)
    cases = ['core', 'true_immortal', 'celestial_developed', 'asura_upper', 'confucian_void', 'mahayana']
    with tempfile.TemporaryDirectory(prefix='deferred-upper-') as folder:
        engine = GameEngine(ROOT, Path(folder) / 'saves')
        class Quiet(server.Handler):
            def log_message(self, *args): pass
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', Path(folder)):
            http = ThreadingHTTPServer(('127.0.0.1', 0), Quiet)
            threading.Thread(target=http.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    for preset in cases:
                        identity = engine.create_game('按需上界', 'supreme_earth', 'dao', 281,
                            preset_id='true_immortal' if preset == 'celestial_developed' else preset)['id']
                        game = engine.store.load(identity)
                        game.pending_event = None
                        game.settings['silent_events'] = True
                        game.player.next_tribulation_age = None
                        game.player.opportunity = 10**8
                        if preset == 'true_immortal':
                            game.player.immortal_power_converted = False
                            game.player.immortal_conversion_stage = 0
                        if preset == 'asura_upper':
                            game.player.asura_cultivation['conversion'] = 0
                        if preset == 'confucian_void':
                            game.player.haoran_exp = 0
                        if preset == 'celestial_developed':
                            game.player.immortal_body['level'] = 20
                            key = next(k for k in game.doctrine_state['definitions'] if k.startswith('celestial:'))
                            game.doctrine_state['player']['progress'][key] = {'level': 4, 'experience': 0}
                            game.doctrine_state['player']['voisinage_training'][key] = {'rank': 1}
                            game.doctrine_state['player']['active'] = key
                        engine.store.save(game)
                        engine.get_game(identity)
                        page = browser.new_page(viewport=dict(width=1440, height=960))
                        errors = []
                        page.on('pageerror', lambda e: errors.append(str(e)))
                        page.goto(f'http://127.0.0.1:{http.server_port}')
                        page.wait_for_function('!!configData&&!busy')
                        page.evaluate('GameThemes.ready')
                        verify(page, engine, identity, preset, output)
                        assert not errors, errors
                        print(preset, 'passed', flush=True)
                        page.close()
                    browser.close()
            finally:
                http.shutdown(); http.server_close()
    assert signature == inputs_digest(ROOT)
    report = dict(inputs_sha256=signature, status='passed', presets=cases, panels=list(ROOTS),
        checks=['no-hidden-draw', 'independent-siblings', 'visited-hidden', 'save-and-metadata-bytes',
                'real-conversion', 'real-asura-conversion', 'real-doctrine-membership', 'unavailable-stays-disabled',
                'busy-navigation', 'settings-ownership', 'desktop-mobile-landscape'])
    (output / 'validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
