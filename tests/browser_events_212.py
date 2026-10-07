"""Real HTTP event choices, stale displays and relationship interception."""
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
from cultivation_life.system.ghost_system import ensure_ghost_cultivation_state
from cultivation_life.system.possession_system import enter_host_body
from test_ghost_phase_two import GhostPhaseTwoTests


def verify_ghost_controls(page, engine):
    game = engine.store.load(engine.create_game('魂位验收', 'mutated_yin', 'ghost', 212)['id'])
    player = game.player
    player.realm_index, player.layer = 4, 5
    ensure_ghost_cultivation_state(player)
    player.hp, player.mp = max_hp(player), max_mp(player)
    player.ghost_bound_souls = [GhostPhaseTwoTests._soul()]
    player.ghost_soul_slots = {'胎光': 'soul-a'}
    game.pending_event = engine._instantiate_event(engine.events_by_id['EVT_SECT_FIRST_WARNING_001'], game, random.Random(1))
    engine.store.save(game)
    page.evaluate('async id => loadGame(id)', game.id)
    page.locator('[data-panel-target=ghost-soul]').click()
    page.get_by_role('button', name='卸下', exact=True).click()
    page.wait_for_function('!busy && game.ghost_system.phase_two.slots.every(s => !s.soul_id)')
    assert engine.store.load(game.id).pending_event['id'] == 'EVT_SECT_FIRST_WARNING_001'
    page.get_by_role('button', name='入魂位', exact=True).click()
    page.wait_for_function('!busy && game.ghost_system.phase_two.slots.some(s => s.soul_id)')

    game = engine.store.load(game.id)
    game.pending_event = None
    game.ghost_parade = dict(status='active', announced=True, world=game.player.world,
                            location_id=game.player.location_id, start_age=game.player.age,
                            end_age=game.player.age + 10, participated=False,
                            souls=[GhostPhaseTwoTests._soul('parade-soul')])
    engine.store.save(game)
    page.evaluate('async id => loadGame(id)', game.id)
    page.locator('[data-panel-target=ghost-parade]').click()
    page.get_by_role('button', name='参悟夜行', exact=True).click()
    page.wait_for_function('!busy && game.ghost_system.phase_two.parade.participated')
    assert page.get_by_role('button', name='本次已参悟', exact=True).is_disabled()
    page.get_by_role('button', name='结交', exact=True).click()
    page.wait_for_function('!busy && game.ghost_system.phase_two.parade.souls[0].befriended')
    assert page.get_by_role('button', name='本次已结交', exact=True).is_disabled()

    game = engine.store.load(game.id)
    host = dict(id='host-a', name='沈青', race='human', path='dao', spirit_root='supreme_metal',
                realm_index=3, layer=2, age=214, lifespan=730, combat_power=2000)
    enter_host_body(game.player, host)
    engine.store.save(game)
    page.evaluate('async id => loadGame(id)', game.id)
    page.locator('[data-panel-target=ghost-soul]').click()
    assert page.get_by_role('button', name='入魂位', exact=True).is_disabled()
    page.get_by_role('button', name='主动离舍', exact=True).click()
    page.wait_for_function("!busy && game.ghost_system.phase_two.state === 'free'")
    game = engine.store.load(game.id)
    game.player.ghost_captor = dict(host, world=game.player.world, location_id=game.player.location_id)
    engine.store.save(game)
    page.evaluate('async id => loadGame(id)', game.id)
    for label in ('忍耐一年', '反抗拘魂者', '夺舍拘魂者'):
        assert page.get_by_role('button', name=label, exact=True).is_enabled()


def main():
    output = ROOT / 'build/events-browser-212'
    output.mkdir(exist_ok=True)
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
                    for theme in ('a', 'b', 'd', 'f'):
                        for width, height in ((393, 852), (1440, 960)):
                            page = browser.new_page(viewport=dict(width=width, height=height))
                            errors, submissions = [], []
                            page.on('pageerror', lambda error: errors.append(str(error)))
                            page.on('request', lambda req: submissions.append(req.post_data_json)
                                    if req.method == 'POST' and req.url.endswith('/choice') else None)
                            page.on('dialog', lambda dialog: dialog.accept())
                            page.goto(f'http://127.0.0.1:{httpd.server_port}')
                            page.wait_for_function('window.GameThemes && configData')
                            page.locator(f'[data-theme-picker=start] [data-theme-choice={theme}]').click()
                            for kind, label in (('master', '截杀师父'), ('companion', '截杀道侣')):
                                game = engine.store.load(engine.create_game('旧事验收', 'heavenly', 'demonic', 212, preset_id='core')['id'])
                                player = game.player
                                player.path, player.realm_index, player.layer = 'demonic', 4, 3
                                player.hp, player.mp = max_hp(player), max_mp(player)
                                player.faction_id = 'tianjian'
                                target, leader = game.sects[player.faction_id].npcs[:2]
                                target.alive, target.realm_index, target.layer = True, 1, 1
                                target.treasure_item_id = None
                                leader.alive, leader.realm_index, leader.layer = True, 5, 9
                                setattr(player, 'master' if kind == 'master' else 'dao_companion', target.to_dict())
                                engine.store.save(game)
                                page.evaluate('async id => loadGame(id)', game.id)
                                page.locator('[data-panel-target=relationship]').click()
                                page.get_by_role('button', name=label, exact=True).click()
                                page.wait_for_function("!busy && game.pending_event?.id === 'EVT_SECT_FIRST_WARNING_001'")
                                # Return from the relationship window to the main event card.
                                page.keyboard.press('Escape')
                                page.locator('#event-choices button').click()
                                page.wait_for_function('!busy && !game.pending_event')
                                assert engine.store.load(game.id).pending_event is None
                                assert submissions[-1]['event_id'] == 'EVT_SECT_FIRST_WARNING_001'

                            def show_warning():
                                current = engine.store.load(game.id)
                                current.pending_event = engine._instantiate_event(
                                    engine.events_by_id['EVT_SECT_FIRST_WARNING_001'], current, random.Random(1))
                                engine.store.save(current)
                                page.evaluate('async id => loadGame(id)', game.id)
                                return engine.store.load(game.id)

                            # Another tab already consumed the event. One failed POST must
                            # refresh the display, never replay the player's action.
                            current = show_warning()
                            current.pending_event = None
                            engine.store.save(current)
                            before = engine.store._path(game.id).read_bytes()
                            count = len(submissions)
                            page.locator('#event-choices button').click()
                            page.wait_for_function('!busy && !game.pending_event')
                            assert page.locator('#action-card').is_visible()
                            assert page.locator('#event-choices button').count() == 0
                            assert len(submissions) == count + 1
                            assert engine.store._path(game.id).read_bytes() == before

                            # A different current event must not consume a stale choice.
                            current = show_warning()
                            reward = engine._prepare_treasure_reward_event(current, random.Random(2))
                            current.pending_event = reward
                            engine.store.save(current)
                            before = engine.store._path(game.id).read_bytes()
                            count = len(submissions)
                            page.locator('#event-choices button').click()
                            page.wait_for_function('(id) => !busy && game.pending_event?.id === id', arg=reward['id'])
                            assert len(submissions) == count + 1
                            assert engine.store._path(game.id).read_bytes() == before
                            assert page.locator('#event-choices button').count() == len(reward['choices'])
                            page.screenshot(path=str(output / f'{theme}-{width}.png'))
                            page.locator('#event-choices button').first.click()
                            page.wait_for_function('!busy && !game.pending_event')
                            verify_ghost_controls(page, engine)
                            assert not errors, errors
                            page.close()
                    browser.close()
            finally:
                httpd.shutdown()
                httpd.server_close()
    print('Events UI passed: four themes, mobile/desktop, interception, stale-state recovery, rewards and ghost controls')


if __name__ == '__main__':
    main()
