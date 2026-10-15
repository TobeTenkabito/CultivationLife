"""One page at a time: actual pending-parcel claims and possessed refinement denial."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
import browser_other_systems_audit_fixes as harness
from test_other_systems_audit_fixes import new_game, snapshot
from test_repository_followup_fixes import join, post_working, cross
from test_spirit_inheritance import prepared
from test_inheritance_audit_fixes import enter_test_host
from scripts.browser_navigation import navigation_locator, click_control, reveal_subpage


def verify(page, engine, width):
    # This harness uses the real engine service for initial posting; UI submits the claim.
    def act(identity, operation, **payload):
        assert operation == 'merchant-action'
        return engine.merchant_action(identity, payload['action'], payload)
    game = join(engine, act, new_game(engine, realm=4))
    world, location = game.player.world, game.player.location_id
    game, identity = post_working(engine, act, game)
    cross(engine, game, 'demon')
    engine.advance(game.id, 'rest', 1)
    game = engine._load(game.id)
    assert game.merchant_state['posted'][-1].get('delivery_goods')
    cross(engine, game, world, location)
    page.evaluate('async id=>loadGame(id)', game.id)
    click_control(navigation_locator(page, '[data-panel-target=merchant]'))
    button = page.locator(f'.merchant-order[data-order-id="{identity}"]').get_by_role('button', name='领取产物', exact=True, include_hidden=True)
    reveal_subpage(page, button)
    assert button.is_enabled()
    changed = engine._load(game.id)
    cross(engine, changed, 'demon')
    frozen = snapshot(engine, game.id)
    requests = []
    observe = lambda request: requests.append((request.method, request.url))
    page.on('request', observe)
    try:
        harness.click_post(page, 'merchant-action', button, status=400)
        assert engine.store._path(game.id).read_bytes() == frozen
        assert sum(method=='POST' and url.endswith('/merchant-action') for method,url in requests)==1
        assert sum(method=='GET' and url.endswith('/'+game.id) for method,url in requests)==1
    finally:
        page.remove_listener('request', observe)
    assert button.is_disabled()
    page.evaluate('renderButtons()')
    assert button.is_disabled()
    changed = engine._load(game.id)
    goods = changed.merchant_state['posted'][-1]['delivery_goods']
    expected_ids = {r['id'] for r in goods['crafting_materials']}
    cross(engine, changed, world, location)
    page.evaluate('async id=>loadGame(id)', game.id)
    assert button.is_enabled()
    harness.click_post(page, 'merchant-action', button)
    saved = engine._load(game.id)
    assert expected_ids <= {r['id'] for r in saved.player.crafting_materials}
    assert saved.merchant_state['posted'][-1]['delivery_claimed']
    assert page.get_by_role('button', name='领取产物', exact=True).count() == 0
    page.wait_for_function('!busy && !document.body.classList.contains("busy")')
    click_control(page.locator('#merchant-toggle'))

    game, _ = prepared(engine, path='ghost')
    game.player.immortal_aperture['current'] = 0
    engine.store.save(game)
    page.evaluate('async id=>loadGame(id)', game.id)
    click_control(navigation_locator(page, '[data-panel-target=immortal-aperture]'))
    refine = page.locator('#immortal-aperture-content').get_by_role('button', name='凝练仙灵力', exact=True)
    assert refine.is_enabled()
    changed = engine._load(game.id)
    enter_test_host(changed)
    engine.store.save(changed)
    frozen = snapshot(engine, game.id)
    harness.click_post(page, 'aperture-action', refine, status=400)
    assert engine.store._path(game.id).read_bytes() == frozen
    assert refine.is_disabled()
    page.evaluate('renderButtons()')
    assert refine.is_disabled()
    click_control(page.locator('#immortal-aperture-toggle'))
    click_control(navigation_locator(page, '[data-panel-target=ghost-soul]'))
    harness.click_post(page, 'ghost-leave-host', page.get_by_role('button', name='主动离舍', exact=True))
    click_control(page.locator('#ghost-soul-toggle'))
    click_control(navigation_locator(page, '[data-panel-target=immortal-aperture]'))
    assert refine.is_enabled()
    harness.click_post(page, 'aperture-action', refine)
    assert engine._load(game.id).player.immortal_aperture['current'] == 250
    page.wait_for_function('!busy && !document.body.classList.contains("busy")')
    print(f'Followup repair UI {width}px: stale claim reload, local pickup, one reward, possessed denial and return refinement', flush=True)


if __name__ == '__main__':
    harness.verify = verify
    harness.main()
