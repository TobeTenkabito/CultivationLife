"""Serial single-page checks for destroyed assets and stale cross-world/war UI."""
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
import browser_other_systems_audit_fixes as harness
from scripts.browser_navigation import navigation_locator, click_control, reveal_subpage
from test_audit_round56_fixes import war_game, planted_field
from test_pending_audit_fixes import local_game, new, captive, convert
from test_regional_rifts import node, enter
from cultivation_life.rules import max_hp, max_mp


def verify(page, engine, width):
    def show(identity, panel):
        page.evaluate('async id=>loadGame(id)', identity)
        click_control(navigation_locator(page, f'[data-panel-target={panel}]'))

    def reject_once(identity, endpoint, target):
        snapshot = engine.store._path(identity).read_bytes()
        requests = []
        observer = lambda req: requests.append((req.method, req.url))
        page.on('request', observer)
        try:
            harness.click_post(page, endpoint, target, status=400)
            assert engine.store._path(identity).read_bytes() == snapshot
            assert sum(m == 'POST' and u.endswith('/'+endpoint) for m, u in requests) == 1
            assert sum(m == 'GET' and u.endswith('/'+identity) for m, u in requests) == 1
        finally:
            page.remove_listener('request', observer)
        page.wait_for_function('!busy && !document.body.classList.contains("busy")')

    game = new(engine)
    captive(game, 'browser-puppet', realm=2)
    game = convert(engine, game, 'browser-puppet')
    game.player.puppets[0]['control'] = 0
    engine.store.save(game)
    show(game.id, 'captive')
    row = page.locator('#puppet-list .puppet-row')
    reinforce = row.get_by_role('button', name=re.compile('加固控制'), include_hidden=True)
    reveal_subpage(page, reinforce)
    assert reinforce.is_enabled()
    harness.click_post(page, 'puppet-action', reinforce)
    game = engine.store.load(game.id)
    assert game.player.puppets[0]['control'] > 0
    # The old UI is left open while a real battle destroys its support body.
    game.player.puppets[0]['control'] = 10
    power = engine._player_battle_power(game) * 1.5
    engine._combat(game, dict(target_name='强敌', target_power=power, target_realm_index=4,
        target_layer=1, combat_type='cultivator', members=[dict(name='强敌', power=power,
        realm_index=4, layer=1, path='dao', race='human')]), False, random.Random(19))
    assert not game.player.puppets[0]['alive']
    game.player.hp, game.player.mp = max_hp(game.player), max_mp(game.player)
    engine.store.save(game)
    reject_once(game.id, 'puppet-action', reinforce)
    assert '已毁坏或陨落' in row.inner_text()
    assert row.get_by_role('button', include_hidden=True).all_text_contents() == ['解除']
    assert page.evaluate('game.demonic_system.puppets[0].annual_opportunity') == 0
    harness.click_post(page, 'puppet-action', row.get_by_role('button', name='解除', exact=True))
    assert not engine.store.load(game.id).player.puppets
    click_control(page.locator('#captive-toggle'))

    game = planted_field(engine, local_game(engine))
    crop = game.player.spirit_field['plots'][0]['id']
    engine.irrigate_spirit_crop(game.id, crop)
    show(game.id, 'spirit-field')
    harvest = page.locator('#spirit-field-plots').get_by_role('button', name='采收', exact=True, include_hidden=True)
    reveal_subpage(page, harvest)
    assert harvest.is_enabled()
    game = engine.store.load(game.id)
    enter(engine, game.id, node(engine, game, 'spirit'))
    reject_once(game.id, 'spirit-field-harvest', harvest)
    page.evaluate('renderButtons()')
    assert harvest.is_disabled()
    assert page.locator('#spirit-field-plots button:enabled').count() == 0
    assert '留在原界面' in page.locator('#spirit-field-note').inner_text()
    game = engine.store.load(game.id)
    enter(engine, game.id, node(engine, game, 'human'))
    page.evaluate('async id=>loadGame(id)', game.id)
    reveal_subpage(page, harvest)
    assert harvest.is_enabled()
    harness.click_post(page, 'spirit-field-harvest', harvest)
    assert not engine.store.load(game.id).player.spirit_field['plots']
    click_control(page.locator('#spirit-field-toggle'))

    game, war = war_game(engine)
    show(game.id, 'war')
    vanguard = page.locator('#war-list').get_by_role('button', name='先锋出阵', exact=True, include_hidden=True)
    reveal_subpage(page, vanguard)
    assert vanguard.is_enabled()
    engine.war_action(game.id, war['id'], 'retreat')
    reject_once(game.id, 'war-action', vanguard)
    assert page.locator('#war-list').get_by_role('button', name='先锋出阵', exact=True, include_hidden=True).count() == 0
    assert engine.store.load(game.id).pending_event is None
    click_control(page.locator('#war-toggle'))
    # Active vanguard events still load and submit through the visible choice.
    game, war = war_game(engine)
    show(game.id, 'war')
    harness.click_post(page, 'war-action', page.locator('#war-list').get_by_role('button', name='先锋出阵', exact=True, include_hidden=True))
    click_control(page.locator('#war-toggle'))
    harness.click_post(page, 'choice', harness.choice_button(page, engine, game.id, 'fight'))
    assert engine.store.load(game.id).pending_event is None
    page.wait_for_function('!busy && !document.body.classList.contains("busy")')
    print(f'Audit round 5/6 UI {width}px: zero-control reinforce, stale destroyed puppet cleanup, remote field denial/return harvest, stale vanguard denial and active battle submit', flush=True)


if __name__ == '__main__':
    harness.verify = verify
    harness.main()
