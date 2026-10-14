"""One real page at a time: stale deliveries, death, suppression and possession."""
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
import browser_other_systems_audit_fixes as harness
from test_relationship_possession_audit_fixes import captive_game, relationship_game
from test_other_systems_audit_fixes import snapshot
from cultivation_life.runtime import encode_rng
from scripts.browser_navigation import navigation_locator, click_control, reveal_subpage


def panel(page, name):
    click_control(navigation_locator(page, f'[data-panel-target={name}]'))


def relationship_button(page, label):
    return page.locator('#relationship-list').get_by_role('button', name=label, exact=True, include_hidden=True).first


def stale_rejection(page, engine, identity, endpoint, button):
    frozen = snapshot(engine, identity)
    requests = []
    observe = lambda request: requests.append((request.method, request.url))
    page.on('request', observe)
    try:
        harness.click_post(page, endpoint, button, status=400)
        assert engine.store._path(identity).read_bytes() == frozen
        assert sum(method == 'POST' and url.endswith('/' + endpoint) for method, url in requests) == 1
        assert sum(method == 'GET' and url.endswith('/' + identity) for method, url in requests) == 1
        page.wait_for_function('!busy && !document.body.classList.contains("busy")')
    finally:
        page.remove_listener('request', observe)


def verify(page, engine, width):
    game = relationship_game(engine, 'monster_realm')
    page.evaluate('async id=>loadGame(id)', game.id)
    panel(page, 'relationship')
    gift = relationship_button(page, '赠物')
    reveal_subpage(page, gift)
    page.locator('#relationship-list .disciple-gifts select').first.select_option('healing_pill')
    assert gift.is_enabled()
    engine.cross_world(game.id, 'phantom_underworld')
    stale_rejection(page, engine, game.id, 'disciple-gift', gift)
    for label in ['赠物', '传功', '请教修行', '索要物品', '请教功法', '收入门下']:
        assert relationship_button(page, label).is_disabled(), label
    assert relationship_button(page, '婉拒').is_enabled()
    engine.cross_world(game.id, 'monster_realm')
    page.evaluate('async id=>loadGame(id)', game.id)
    page.locator('#relationship-list .disciple-gifts select').first.select_option('healing_pill')
    harness.click_post(page, 'disciple-gift', relationship_button(page, '赠物'))
    assert engine._load(game.id).player.disciples[0]['items']['healing_pill'] == 1
    harness.click_post(page, 'disciple-request', relationship_button(page, '收入门下'))
    assert len(engine._load(game.id).player.disciples) == 2
    local = engine._load(game.id)
    local.rng_state = encode_rng(random.Random(1))
    engine.store.save(local)
    inventory_before = sum(row.quantity for row in local.player.inventory)
    harness.click_post(page, 'master-request', relationship_button(page, '索要物品'))
    assert sum(row.quantity for row in engine._load(game.id).player.inventory) == inventory_before + 1
    stale = relationship_button(page, '请教修行')
    assert stale.is_enabled()
    dying = engine._load(game.id)
    dying.player.lifespan = dying.player.age
    engine.store.save(dying)
    engine.advance(game.id, 'rest', 1)
    assert not engine._load(game.id).player.alive
    stale_rejection(page, engine, game.id, 'master-request', stale)
    for button in page.locator('#relationship-list button').all():
        assert button.is_disabled()
    click_control(page.locator('#relationship-toggle'))

    game, target = captive_game(engine)
    page.evaluate('async id=>loadGame(id)', game.id)
    panel(page, 'captive')
    possess = page.locator('#captive-list').get_by_role('button', name='夺舍', exact=True, include_hidden=True)
    reveal_subpage(page, possess)
    assert possess.is_enabled()
    engine.manage_secret_art(game.id, 'suppress', 'activate', 3, 1)
    stale_rejection(page, engine, game.id, 'captive-action', possess)
    assert possess.is_disabled()
    page.evaluate('renderButtons()')
    assert possess.is_disabled()
    assert '压制' in possess.get_attribute('title')
    engine.manage_secret_art(game.id, 'suppress', 'cancel')
    page.evaluate('async id=>loadGame(id)', game.id)
    harness.click_post(page, 'captive-action', possess)
    assert engine._load(game.id).player.ghost_host_body
    click_control(page.locator('#captive-toggle'))
    panel(page, 'secret-art')
    assert page.locator('#secret-suppress-activate').is_disabled()
    assert '离舍' in page.locator('#secret-suppress-activate').get_attribute('title')
    click_control(page.locator('#secret-art-toggle'))
    panel(page, 'ghost-soul')
    harness.click_post(page, 'ghost-leave-host', page.get_by_role('button', name='主动离舍', exact=True))
    final = engine._load(game.id).player
    assert (final.realm_index, final.layer, final.opportunity) == (4, 5, 321)
    print(f'Relationship/possession UI passed: {width}px; stale cross-world/death/possession rejection, single reload, disabled controls, return gifts/recruitment/reward, legal possession and leave', flush=True)


if __name__ == '__main__':
    harness.verify = verify
    harness.main()
