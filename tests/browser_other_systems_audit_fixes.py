"""One browser/page at a time: stale reincarnation, earned rewards and real forging."""
import copy
import random
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.content_registry import REALMS
from cultivation_life.rules import opportunity_required
from scripts.browser_navigation import navigation_locator, click_control
from test_other_systems_audit_fixes import new_game, snapshot, reincarnation_choices, guixu_recipe


def choice_button(page, engine, identity, choice):
    choices = engine._load(identity).pending_event['choices']
    index = next(i for i,row in enumerate(choices) if row['id']==choice)
    return page.locator('#event-choices button').nth(index)


def click_post(page, endpoint, target, status=200):
    with page.expect_response(lambda response: response.url.endswith('/'+endpoint)) as response:
        click_control(target)
    assert response.value.status == status
    page.wait_for_function('!busy')


def verify(page, engine, width):
    commit, cancel = reincarnation_choices(engine)
    game = new_game(engine, 'ghost', 4, REALMS[4].layers)
    game.player.opportunity = opportunity_required(game.player)
    engine.store.save(game)
    page.evaluate('async id=>loadGame(id)', game.id)
    click_post(page, 'ghost-reincarnation-prompt', page.locator('#ghost-reincarnate-action'))
    pending = copy.deepcopy(engine._load(game.id).pending_event)
    stale = choice_button(page, engine, game.id, commit)
    assert not stale.is_disabled()
    # Reproduce a schema10 prompt saved by the old suppressed-entry bug.
    changed = engine._load(game.id)
    changed.pending_event = None
    engine.store.save(changed)
    engine.manage_secret_art(game.id, 'suppress', 'activate', 1, REALMS[1].layers)
    changed = engine._load(game.id)
    changed.player.opportunity = opportunity_required(changed.player)
    reward = engine._prepare_treasure_reward_event(changed, random.Random(11))
    pending['_followup_event'] = copy.deepcopy(reward)
    changed.pending_event = pending
    engine.store.save(changed)
    frozen = snapshot(engine, game.id)
    requests = []
    observe = lambda request: requests.append((request.method, request.url))
    page.on('request', observe)
    try:
        click_post(page, 'choice', stale, status=400)
        assert engine.store._path(game.id).read_bytes() == frozen
        assert choice_button(page, engine, game.id, commit).is_disabled()
        assert sum(method=='POST' and url.endswith('/choice') for method,url in requests)==1
        assert sum(method=='GET' and url.endswith('/'+game.id) for method,url in requests)==1
    finally:
        page.remove_listener('request', observe)
    assert not choice_button(page, engine, game.id, cancel).is_disabled()
    click_post(page, 'choice', choice_button(page, engine, game.id, cancel))
    assert engine._load(game.id).pending_event['runtime']==reward['runtime']
    click_post(page, 'choice', choice_button(page, engine, game.id, 'pill'))
    page.wait_for_function('!busy && !game.pending_event')
    assert not engine._load(game.id).player.ghost_reincarnation_imprints
    assert page.locator('#ghost-reincarnate-action').is_hidden()
    navigation_locator(page, '[data-panel-target=secret-art]').click()
    click_post(page, 'secret-art', page.locator('#secret-suppress-cancel'))
    assert engine._load(game.id).player.cultivation_suppression is None
    click_control(page.locator('#secret-art-toggle'))

    # The same ordinary controls still perform one legal reset.
    game = new_game(engine, 'ghost', 4, REALMS[4].layers)
    game.player.opportunity = opportunity_required(game.player)
    engine.store.save(game)
    page.evaluate('async id=>loadGame(id)', game.id)
    click_post(page, 'ghost-reincarnation-prompt', page.locator('#ghost-reincarnate-action'))
    click_post(page, 'choice', choice_button(page, engine, game.id, commit))
    saved = engine._load(game.id).player
    assert (saved.realm_index, saved.layer, saved.opportunity)==(1,1,0)
    assert saved.ghost_reincarnation_imprints=={'4':1}

    # Actual five-slot form, preview and confirmation consume the exact low-rank materials.
    game = new_game(engine, realm=12)
    _, primary, payload = guixu_recipe(engine, game, 'human')
    frozen = snapshot(engine, game.id)
    page.evaluate('async id=>loadGame(id)', game.id)
    navigation_locator(page, '[data-panel-target=crafting]').click()
    page.locator('#crafting-mode').select_option('free')
    page.locator('#crafting-mold').select_option(payload['mold_id'])
    for selector, key in [('primary','primary_id'),('secondary-a','secondary_a_id'),
                          ('secondary-b','secondary_b_id'),('quench','quench_id')]:
        page.locator('#crafting-'+selector).select_option(payload[key])
    for control in page.locator('#crafting-allocations input[data-stat]').all(): control.fill('0')
    page.locator('#crafting-allocations input[data-stat=combat_power]').fill('20')
    click_post(page, 'crafting-preview', page.locator('#crafting-preview'))
    assert engine.store._path(game.id).read_bytes()==frozen
    assert '主材基准 元婴' in page.locator('#crafting-preview-result h4').inner_text()
    click_control(page.locator('#crafting-preview-result').get_by_role('button', name='确认开炉'))
    click_post(page, 'crafting-forge', page.get_by_role('button', name='开炉炼器', exact=True))
    saved = engine._load(game.id).player
    assert saved.crafted_artifacts[-1]['scaling_realm_index']==4
    assert saved.crafting_sequence==1
    assert not any(item.id==primary.id for item in saved.inventory)
    print(f'Other system fixes UI passed: {width}px, stale denial, disabled choice, cancel, earned reward, legal reset, real forge', flush=True)


def main():
    with tempfile.TemporaryDirectory(prefix='other-system-browser-') as directory:
        engine = GameEngine(ROOT, Path(directory)/'saves')
        class Handler(server.Handler):
            def log_message(self,*args): pass
        with patch.object(server,'ENGINE',engine), patch.object(server,'PERSISTENCE_ROOT',Path(directory)):
            http = ThreadingHTTPServer(('127.0.0.1',0),Handler)
            thread = threading.Thread(target=http.serve_forever,daemon=True)
            thread.start()
            try:
                with sync_playwright() as pw:
                    for width,height in [(1440,960),(393,852)]:
                        browser=pw.chromium.launch(args=['--disable-gpu','--renderer-process-limit=1','--js-flags=--max-old-space-size=128'])
                        try:
                            page=browser.new_page(viewport=dict(width=width,height=height),reduced_motion='reduce')
                            page.route('**/assets/maps/**',lambda route:route.abort())
                            errors=[]
                            page.on('pageerror',lambda error:errors.append(str(error)))
                            page.on('dialog',lambda dialog:dialog.accept())
                            page.goto(f'http://127.0.0.1:{http.server_port}')
                            page.wait_for_function('configData && !busy')
                            page.locator('[data-theme-picker=start] [data-theme-choice=a]').click()
                            verify(page,engine,width)
                            assert not errors,errors
                        finally: browser.close()
            finally:
                http.shutdown();http.server_close();thread.join(timeout=2)


if __name__=='__main__': main()
