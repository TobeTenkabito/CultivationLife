"""One real page: stale celestial cultivation rejects, freezes and resumes after leaving."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
import browser_other_systems_audit_fixes as harness
from test_spirit_inheritance import prepared
from test_inheritance_audit_fixes import activated_doctrine, enter_test_host
from test_other_systems_audit_fixes import snapshot
from scripts.browser_navigation import navigation_locator, click_control, reveal_subpage


def verify(page, engine, width):
    game, _ = prepared(engine, path='ghost')
    key = activated_doctrine(game)
    engine.store.save(game)
    page.evaluate('async id=>loadGame(id)', game.id)
    click_control(navigation_locator(page, '[data-panel-target=voisinage]'))
    growth = page.locator('#voisinage-content [data-doctrine-action=advance_voisinage]').first
    reveal_subpage(page, growth)
    details = page.locator('#voisinage-content [data-voisinage-id]').first
    if not details.evaluate('node=>node.open'):
        click_control(details.locator(':scope > summary'))
    growth.wait_for(state='visible')
    assert growth.is_enabled()
    possessed = engine._load(game.id)
    enter_test_host(possessed)
    engine.store.save(possessed)
    frozen = snapshot(engine, game.id)
    requests = []
    observe = lambda request: requests.append((request.method, request.url))
    page.on('request', observe)
    try:
        harness.click_post(page, 'immortal-action', growth, status=400)
        assert engine.store._path(game.id).read_bytes() == frozen
        assert sum(method == 'POST' and url.endswith('/immortal-action') for method, url in requests) == 1
        assert sum(method == 'GET' and url.endswith('/' + game.id) for method, url in requests) == 1
    finally:
        page.remove_listener('request', observe)
    page.wait_for_function('!busy && !document.body.classList.contains("busy")')
    assert growth.is_disabled()
    page.evaluate('renderButtons()')
    assert growth.is_disabled()
    assert all(button.is_disabled() for button in page.locator('#voisinage-content [data-doctrine-action]').all())
    click_control(page.locator('#voisinage-toggle'))
    click_control(navigation_locator(page, '[data-panel-target=ghost-soul]'))
    harness.click_post(page, 'ghost-leave-host', page.get_by_role('button', name='主动离舍', exact=True))
    assert engine._load(game.id).doctrine_state['player']['voisinage_training'][key]['rank'] == 1
    click_control(page.locator('#ghost-soul-toggle'))
    click_control(navigation_locator(page, '[data-panel-target=voisinage]'))
    reveal_subpage(page, growth)
    if not details.evaluate('node=>node.open'):
        click_control(details.locator(':scope > summary'))
    growth.wait_for(state='visible')
    assert growth.is_enabled()
    harness.click_post(page, 'immortal-action', growth)
    final = engine._load(game.id)
    assert final.player.path == 'ghost'
    assert final.doctrine_state['player']['voisinage_training'][key]['rank'] == 2
    page.wait_for_function('!busy && !document.body.classList.contains("busy")')
    assert page.locator('#voisinage-content [data-doctrine-action=activate]').first.is_disabled()
    print(f'Inheritance audit UI {width}px: one stale rejection/reload, frozen controls, leave and legal growth', flush=True)


if __name__ == '__main__':
    harness.verify = verify
    harness.main()
