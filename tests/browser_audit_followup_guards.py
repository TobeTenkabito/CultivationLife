"""Serial browser proof: stale soul-custody commands, rewards and actual movement."""
import copy
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
import browser_other_systems_audit_fixes as harness
from scripts.browser_navigation import navigation_locator, click_control, reveal_subpage
from test_audit_round56_fixes import controlled_ghost
from test_audit_followup_guards import interrupted_ghost_journey


def verify(page, engine, width):
    game, npc = controlled_ghost(engine)
    npc.age, npc.lifespan = 30, 10000
    engine.store.save(game)
    page.evaluate('async id=>loadGame(id)', game.id)
    click_control(navigation_locator(page, '[data-panel-target=ghost-soul]'))
    wait = page.locator('#ghost-constraint-actions').get_by_role('button', name='忍耐一年', exact=True, include_hidden=True)
    reveal_subpage(page, wait)
    assert wait.is_enabled()
    # A legitimate pending event appears after the old button was rendered.
    changed = engine._load(game.id)
    changed.pending_event = engine._instantiate_event(engine.events_by_id['EVT_SECT_FIRST_WARNING_001'], changed, random.Random(1))
    reward = engine._prepare_treasure_reward_event(changed, random.Random(11))
    changed.pending_event['_followup_event'] = copy.deepcopy(reward)
    engine.store.save(changed)
    engine.get_game(game.id)
    snapshot = engine.store._path(game.id).read_bytes()
    requests = []
    observer = lambda req: requests.append((req.method, req.url))
    page.on('request', observer)
    try:
        harness.click_post(page, 'ghost-constraint', wait, status=400)
        assert engine.store._path(game.id).read_bytes() == snapshot
        assert sum(m == 'POST' and u.endswith('/ghost-constraint') for m,u in requests) == 1
        assert sum(m == 'GET' and u.endswith('/'+game.id) for m,u in requests) == 1
    finally:
        page.remove_listener('request', observer)
    page.wait_for_function('!busy && !document.body.classList.contains("busy")')
    page.evaluate('renderButtons()')
    assert page.locator('#ghost-constraint-actions button:enabled').count() == 0
    click_control(page.locator('#ghost-soul-toggle'))
    harness.click_post(page, 'choice', harness.choice_button(page, engine, game.id, 'acknowledge'))
    assert engine.store.load(game.id).pending_event['runtime'] == reward['runtime']
    harness.click_post(page, 'choice', harness.choice_button(page, engine, game.id, 'pill'))
    click_control(navigation_locator(page, '[data-panel-target=ghost-soul]'))
    reveal_subpage(page, wait)
    assert wait.is_enabled()
    before_age = engine.store.load(game.id).player.age
    harness.click_post(page, 'ghost-constraint', wait)
    assert engine.store.load(game.id).player.age == before_age + 1
    click_control(page.locator('#ghost-soul-toggle'))

    game, destination = interrupted_ghost_journey(engine)
    origin = game.player.location_id
    page.evaluate('async id=>loadGame(id)', game.id)
    click_control(navigation_locator(page, '[data-panel-target=ghost-soul]'))
    harness.click_post(page, 'ghost-constraint', wait)
    saved = engine.store.load(game.id)
    assert saved.player.location_id != origin and saved.map_journey is None
    assert saved.market_location_id == saved.player.location_id
    assert page.evaluate('game.player.location_id') == saved.player.location_id
    page.wait_for_function('!busy && !document.body.classList.contains("busy")')
    print(f'Followup guard UI {width}px: stale custody denied once, all custody buttons disabled, followup reward, wait recovery, forced move clears journey and refreshes market', flush=True)


if __name__ == '__main__':
    harness.verify = verify
    harness.main()
