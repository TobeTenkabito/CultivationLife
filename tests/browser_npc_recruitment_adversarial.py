"""Real event -> letter -> disciple -> training, including forged/stale POSTs."""
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
from cultivation_life.relationship_records import find_person
from cultivation_life.runtime import now_iso, encode_rng
from scripts.browser_navigation import navigation_locator, click_control, reveal_subpage
from test_other_systems_audit_fixes import snapshot


def load(page, identity):
    page.evaluate('''async id=>{await loadGame(id);await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));}''', identity)


def main():
    with tempfile.TemporaryDirectory() as folder:
        engine = GameEngine(ROOT, Path(folder))
        class Handler(server.Handler):
            def log_message(self, *_args): pass
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', Path(folder)):
            http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            threading.Thread(target=http.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    for width, height in [(1440, 960), (390, 844)]:
                        page = browser.new_page(viewport=dict(width=width, height=height))
                        errors = []; page.on('pageerror', lambda e: errors.append(str(e)))
                        page.on('dialog', lambda d: d.accept())
                        g = engine.store.load(engine.create_game('收徒对抗', 'supreme_metal', 'dao', 353)['id'])
                        g.player.realm_index, g.player.layer = 3, 8
                        g.player.body_training = 60; g.player.opportunity = 100000
                        g.pending_event = engine._instantiate_event(engine.events_by_id['EVT_DISCIPLE_ENCOUNTER_001'], g, random.Random(7))
                        engine.store.save(g)
                        base = f'http://127.0.0.1:{http.server_port}'
                        page.context.set_extra_http_headers({'Origin': base})
                        page.goto(base); page.wait_for_function('!!configData&&!busy'); load(page, g.id)
                        with page.expect_response(lambda r: r.url.endswith('/choice')) as response:
                            page.locator('#event-choices button').filter(has_text='收下拜师帖').click()
                        assert response.value.ok, response.value.text()
                        page.wait_for_function('!busy&&!game.pending_event&&game.player.disciple_requests.length===1')
                        g = engine.store.load(g.id); identity = g.player.disciple_requests[0]['id']
                        assert find_person(g, identity).location_id == g.player.location_id
                        path = engine.store._path(g.id)
                        before = snapshot(engine, g.id)
                        bad = page.request.post(base+f'/api/games/{g.id}/disciple-request', data=dict(request_id=identity, accept='false'))
                        assert bad.status == 400, bad.text()
                        assert path.read_bytes() == before
                        navigation_locator(page, '[data-panel-target=relationship]').click()
                        # The candidate grows after the page was rendered. Submission rechecks facts.
                        n = find_person(g, identity); rank = n.realm_index; n.realm_index = 4
                        engine.store.save(g); before = snapshot(engine, g.id)
                        with page.expect_response(lambda r: r.url.endswith('/disciple-request')) as response:
                            click_control(page.locator('.pending-request button').filter(has_text='收入门下'))
                        assert response.value.status == 400 and path.read_bytes() == before
                        page.wait_for_function('!busy')
                        load(page, g.id)
                        if not page.locator('#relationship-card').is_visible(): navigation_locator(page, '[data-panel-target=relationship]').click()
                        assert page.locator('.pending-request button').filter(has_text='收入门下').is_disabled()
                        n.realm_index = rank; engine.store.save(g); load(page, g.id)
                        if not page.locator('#relationship-card').is_visible(): navigation_locator(page, '[data-panel-target=relationship]').click()
                        with page.expect_response(lambda r: r.url.endswith('/disciple-request')) as response:
                            click_control(page.locator('.pending-request button').filter(has_text='收入门下'))
                        assert response.value.ok, response.value.text()
                        page.wait_for_function('!busy&&game.player.disciples.length===1')
                        before = snapshot(engine, g.id)
                        replay = page.request.post(base+f'/api/games/{g.id}/disciple-request', data=dict(request_id=identity, accept=True))
                        assert replay.status == 400 and path.read_bytes() == before
                        navigation_locator(page, '[data-panel-target=npc-development]').click()
                        page.wait_for_selector('#npc-development-submit')
                        page.get_by_label('培养方向', exact=True).select_option('body')
                        page.get_by_label('培养方式', exact=True).select_option('infuse')
                        g = engine.store.load(g.id); n = find_person(g, identity)
                        old_body, old_cost = n.body_training, g.player.opportunity
                        revision = g.updated_at
                        # Another window changed the save: stale training cannot charge.
                        g.updated_at = now_iso(); engine.store.save(g); before = snapshot(engine, g.id)
                        with page.expect_response(lambda r: r.request.method == 'POST' and r.url.endswith('/npc-development')) as response:
                            page.locator('#npc-development-submit').click()
                        assert response.value.status == 400 and path.read_bytes() == before
                        page.wait_for_function('!busy')
                        for change in [dict(batches=True), dict(method=[]), dict(axis={}), dict(kind='prisoner')]:
                            payload = dict(revision=g.updated_at, action='train', kind='npc', target_id=identity, axis='body', method='infuse', batches=1)
                            bad = page.request.post(base+f'/api/games/{g.id}/npc-development', data=payload | change)
                            assert bad.status == 400, bad.text()
                            assert path.read_bytes() == before
                        legacy = page.request.post(base+f'/api/games/{g.id}/disciple-gift', data=dict(disciple_id=identity, kind='item', content_id='missing', expected_revision=revision))
                        assert legacy.status == 400 and path.read_bytes() == before
                        page.keyboard.press('Escape'); load(page, g.id)
                        navigation_locator(page, '[data-panel-target=npc-development]').click()
                        page.wait_for_selector('#npc-development-submit')
                        page.get_by_label('培养方向', exact=True).select_option('body')
                        page.get_by_label('培养方式', exact=True).select_option('infuse')
                        with page.expect_response(lambda r: r.request.method == 'POST' and r.url.endswith('/npc-development')) as response:
                            page.locator('#npc-development-submit').click()
                        assert response.value.ok, response.value.text()
                        page.wait_for_function('!busy')
                        after = engine.store.load(g.id); trained = find_person(after, identity)
                        assert trained.body_training > (old_body or 0) and after.player.opportunity < old_cost
                        assert trained.location_id == g.player.location_id
                        assert after.player.disciples[0].person is trained
                        assert after.player.age == g.player.age and after.rng_state == g.rng_state
                        # A cached encounter becomes a disciple through the real contact UI.
                        target = dict(combat_type='cultivator', target_name='偶遇同道',
                            members=[dict(realm_index=1, layer=1, power=100, race='human')])
                        engine._cache_encounter_target(after, target, random.Random(11))
                        contact_id = target['members'][0]['npc_id']
                        after.rng_state = encode_rng(random.Random(1)); engine.store.save(after)
                        page.keyboard.press('Escape'); load(page, g.id)
                        if not page.locator('#relationship-card').is_visible(): navigation_locator(page, '[data-panel-target=relationship]').click()
                        search = page.get_by_label('搜索重要人物', exact=True)
                        reveal_subpage(page, search); search.fill(target['members'][0]['name'])
                        page.locator(f'.contact-person[data-npc-id="{contact_id}"]').click()
                        with page.expect_response(lambda r: r.url.endswith('/npc-contact')) as response:
                            click_control(page.locator('[data-contact-action=disciple]'))
                        assert response.value.ok, response.value.text()
                        page.wait_for_function('!busy&&game.player.disciples.length===2')
                        saved = engine.store.load(g.id); contact = find_person(saved, contact_id)
                        assert contact.location_id == g.player.location_id
                        assert saved.player.disciples[-1].person is contact
                        assert not any(r['id'] == contact_id for r in saved.encounter_npc_cache)
                        projected = page.request.get(base+f'/api/games/{g.id}/npc-development').json()
                        assert not next(r for r in projected['targets'] if r['id'] == contact_id)['reason']
                        assert not errors, errors
                        page.screenshot(path=str(ROOT/'build'/f'npc-recruitment-adversarial-{width}.png'))
                        page.close()
                    browser.close()
            finally:
                http.shutdown(); http.server_close()
    print('NPC recruitment adversarial browser checks passed (desktop + mobile)')


if __name__ == '__main__': main()
