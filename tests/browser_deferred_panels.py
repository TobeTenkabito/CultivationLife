"""Real navigation, pending commands, character changes and stale-event recovery."""
import json
from http.server import ThreadingHTTPServer
from pathlib import Path
import random
import sys
import tempfile
import threading
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.engine.actions.exploration import enter_scene
from cultivation_life.rules import add_item
from cultivation_life.runtime import decode_rng, encode_rng
from cultivation_life.system import spatial
from playwright.sync_api import sync_playwright
from scripts.browser_navigation import navigation_locator
from scripts.release_evidence import inputs_digest


def open_panel(page, name):
    navigation_locator(page, f'[data-panel-target="{name}"]').click()
    page.wait_for_selector(f'#{name}-card.panel-open')


def check(page, engine, first, second, output):
    page.evaluate("""()=>{
      window.paintCalls={};
      for(const name of ['renderMap','paintMarket','paintCrafting','paintFormation','paintFaction','paintFamily',
          'paintWorldNpcs','paintWorldRoute','paintTransformationSystem','renderRelationships']){
        const original=window[name];paintCalls[name]=0;
        window[name]=(...args)=>{paintCalls[name]++;return original(...args);};
      }
    }""")
    page.evaluate('id=>loadGame(id)', first)
    assert not any(page.evaluate('paintCalls').values()), 'Closed panels drew on load'
    saved = engine.store._path(first).read_bytes()
    open_panel(page, 'faction')
    assert page.evaluate("""()=>{const node=document.querySelector('#faction-summary').firstElementChild;
      window.dispatchEvent(new Event('game:visual-ready'));return !!node&&node.isConnected;}""")
    page.keyboard.press('Escape')
    open_panel(page, 'market')
    assert page.evaluate('paintCalls.paintMarket') == 1
    assert engine.store._path(first).read_bytes() == saved
    offer = page.evaluate("game.market.offers.find(o=>!o.sold&&!o.economy_unavailable&&o.price<=game.market.spirit_stones)")
    assert offer
    page.locator(f'.market-buy[data-offer-id="{offer["id"]}"]').click()
    page.wait_for_function("id=>!busy&&game.market.offers.find(o=>o.id===id)?.sold", arg=offer['id'])
    assert page.evaluate('paintCalls.paintMarket') == 2, 'Open market did not update after actual purchase'
    page.keyboard.press('Escape')
    hidden_count = page.evaluate('paintCalls.paintMarket')
    held = []
    endpoint = f'**/api/games/{first}/advance'
    page.route(endpoint, lambda route: held.append(route))
    page.locator('[data-action="rest"]').click()
    page.wait_for_function('busy')
    assert page.locator('[data-panel-target="market"]').is_disabled()
    # Even a programmatically opened panel must apply the existing busy guard.
    page.evaluate("UtilityPanels.open('formation')")
    assert page.locator('#formation-card button, #formation-card input, #formation-card select').evaluate_all('ns=>ns.every(n=>n.disabled)')
    page.evaluate("UtilityPanels.close('formation')")
    assert len(held) == 1
    held.pop().continue_()
    page.unroute(endpoint)
    page.wait_for_function('!busy')
    assert page.evaluate('paintCalls.paintMarket') == hidden_count, 'Closed market rebuilt during action'
    assert page.locator('#formation-deactivate').is_disabled(), 'Unavailable action re-enabled after busy'
    open_panel(page, 'market')
    assert page.evaluate('paintCalls.paintMarket') == hidden_count + 1
    assert page.locator('#market-wallet').inner_text() == '灵石 ' + str(page.evaluate('game.market.spirit_stones'))
    page.keyboard.press('Escape')

    # Closing and a newer authoritative response invalidate an outstanding draft.
    open_panel(page, 'formation')
    preview_url = f'/api/games/{first}/formation-preview'
    profile = page.request.post(page.url.rstrip('/') + preview_url, data=page.evaluate('formationPayload(false)')).json()
    drafts = []
    page.route('**' + preview_url, lambda route: drafts.append(route))
    page.evaluate("""()=>{window.readingCalls=0;const original=renderFormationReading;
      window.renderFormationReading=(...args)=>{readingCalls++;return original(...args);};}""")
    page.locator('#formation-preview').click()
    page.wait_for_timeout(50)
    assert len(drafts) == 1
    page.keyboard.press('Escape')
    page.evaluate('id=>loadGame(id)', first)
    drafts.pop().fulfill(json=profile)
    page.unroute('**' + preview_url)
    page.wait_for_timeout(100)
    assert page.evaluate('readingCalls') == 0, 'Stale preview painted after a newer response'

    # Reset pending work and open panels when changing characters.
    page.evaluate("window.stalePaint=0;UtilityPanels.schedule('family',()=>stalePaint++)")
    page.locator('#new-game-button').click()
    page.evaluate("UtilityPanels.open('family')")
    assert page.evaluate('stalePaint') == 0
    page.evaluate('id=>loadGame(id)', second)
    assert page.locator('.utility-panel.panel-open').count() == 0
    open_panel(page, 'heavenly-court')
    assert '玉京仙都' in page.locator('#court-heading').inner_text()
    page.evaluate('id=>loadGame(id)', first)
    assert page.locator('#heavenly-court-card').evaluate("n=>n.classList.contains('hidden')")
    assert page.locator('[data-panel-target="heavenly-court"]').evaluate("n=>n.classList.contains('hidden')")
    open_panel(page, 'relationship')
    assert page.evaluate('paintCalls.renderRelationships') > 0
    page.keyboard.press('Escape')

    # Real stale POST: one refusal, one authoritative refresh, preserved reward.
    game = engine.store.load(first)
    warning = engine._instantiate_event(engine.events_by_id['EVT_SECT_FIRST_WARNING_001'], game, random.Random(1))
    reward = engine._prepare_treasure_reward_event(game, random.Random(2))
    game.pending_event = warning
    engine.store.save(game)
    page.evaluate('id=>loadGame(id)', first)
    game = engine.store.load(first)
    game.pending_event = reward
    engine.store.save(game)
    saved = engine.store._path(first).read_bytes()
    submissions = []
    page.on('request', lambda request: submissions.append(request.post_data_json)
        if request.method == 'POST' and request.url.endswith('/choice') else None)
    page.locator('#event-choices button').first.click()
    page.wait_for_function('id=>!busy&&game.pending_event?.id===id', arg=reward['id'])
    assert len(submissions) == 1
    assert engine.store._path(first).read_bytes() == saved
    open_panel(page, 'market')
    assert page.locator('.market-buy').evaluate_all('ns=>ns.length>0&&ns.every(n=>n.disabled)')
    page.keyboard.press('Escape')
    page.locator('#event-choices button').first.click()
    page.wait_for_function('!busy&&!game.pending_event')
    assert len(submissions) == 2
    assert page.locator('[data-action="rest"]').is_enabled()
    for width, height in [(1440, 960), (390, 844), (844, 390)]:
        page.set_viewport_size(dict(width=width, height=height))
        open_panel(page, 'relationship')
        page.screenshot(path=str(output / f'relationship-{width}.png'))
        page.keyboard.press('Escape')

    # Local society owns the same panels while inside a full-capacity lost world.
    game = engine.store.load(first)
    rng = decode_rng(game.seed, game.rng_state)
    scene = spatial.create_instance(game, rng, 'lost')
    scene['power_ceiling'] = 8
    enter_scene(engine._exploration_dependencies(), game, scene, rng)
    game.rng_state = encode_rng(rng)
    engine.store.save(game)
    engine.get_game(first)
    page.evaluate('id=>loadGame(id)', first)
    saved = engine.store._path(first).read_bytes()
    for name, suffix in [('faction', '宗门'), ('family', '家族')]:
        open_panel(page, name)
        assert page.locator(f'#{name}-title').inner_text() == scene['name'] + suffix
        assert page.locator(f'#{name}-content').evaluate('n=>n.hidden')
        assert page.locator(f'#{name}-card .spatial-society').is_visible()
        page.keyboard.press('Escape')
    assert saved == engine.store._path(first).read_bytes()

    page.set_viewport_size(dict(width=1440, height=960))
    page.evaluate('id=>loadGame(id)', second)
    saved = engine.store._path(second).read_bytes()
    page.locator('#theme-open').click()
    page.locator('#theme-dialog [data-pixel-setting]').check()
    page.evaluate('GameThemes.saved')
    page.locator('[data-close-dialog=theme-dialog]').click()
    page.wait_for_function('window.PixelLibrary?.active()')
    for name in ['market', 'faction', 'family', 'relationship', 'formation', 'natal-artifact']:
        open_panel(page, name)
        assert page.locator(f'#{name}-card').is_visible()
        page.keyboard.press('Escape')
    assert saved == engine.store._path(second).read_bytes()


def main():
    output = ROOT / 'build/hidden-panels-20261029/browser'
    output.mkdir(parents=True, exist_ok=True)
    signature = inputs_digest(ROOT)
    with tempfile.TemporaryDirectory(prefix='deferred-panel-browser-') as folder:
        engine = GameEngine(ROOT, Path(folder) / 'saves')
        identities = []
        for preset in ['core', 'true_immortal']:
            made = engine.create_game('按需绘制', 'heavenly', 'dao', 280, preset_id=preset)
            game = engine.store.load(made['id'])
            game.settings['silent_events'] = True
            game.pending_event = None
            game.player.next_tribulation_age = None
            add_item(game.player, 'spirit_stone', 1_000_000)
            engine.store.save(game)
            engine.get_game(game.id)
            identities.append(game.id)
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
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.goto(f'http://127.0.0.1:{http.server_port}')
                    page.wait_for_function('!!configData && !busy')
                    page.evaluate('GameThemes.ready')
                    check(page, engine, *identities, output)
                    assert not errors, errors
                    browser.close()
            finally:
                http.shutdown(); http.server_close()
    assert signature == inputs_digest(ROOT)
    report = dict(inputs_sha256=signature, status='passed',
        checks=['closed-paints', 'real-purchase', 'open-panel-updates', 'hidden-latest-response',
                'busy-and-unavailable', 'stale-preview', 'pending-reset', 'character-permissions',
                'stale-event-recovery', 'preserved-reward', 'desktop-mobile-landscape', 'lost-world-society', 'pixel-panels', 'asset-ready-node-identity'])
    (output / 'validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
