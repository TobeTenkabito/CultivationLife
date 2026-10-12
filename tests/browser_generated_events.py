"""Real page clicks for base generated events, stale pages and queued rewards."""
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


def fixture(engine):
    game = engine.store.load(engine.create_game('种子异闻', 'heavenly', 'dao', 431, preset_id='core')['id'])
    game.player.realm_index, game.player.layer = 1, 1
    game.player.opportunity = 0
    game.player.hp, game.player.mp = max_hp(game.player), max_mp(game.player)
    game.settings['silent_events'] = True
    engine.store.save(game)
    return game


def explore(page):
    button = page.locator('[data-action="generated_explore"]')
    if not button.is_visible():
        page.locator('#tab-living').click()
    button.click()
    try:
        page.wait_for_function('!busy && game.generated_event.pending && game.pending_event')
    except Exception:
        page.screenshot(path=str(ROOT / 'build/generated-events-browser/failure.png'))
        print(page.evaluate('({busy, id:game?.id, alive:game?.player.alive, event:game?.pending_event?.id, generated:game?.generated_event, dialogs:[...document.querySelectorAll("dialog[open]")].map(d=>d.textContent), toast:document.querySelector("#toast")?.textContent})'), flush=True)
        raise


def pick(page, choice_id):
    # Read only the public order so the actual click remains on the real UI.
    ids = page.evaluate('game.pending_event.choices.map(c => c.id)')
    page.locator('#event-choices button').nth(ids.index(choice_id)).click()


def main():
    output = ROOT / 'build/generated-events-browser'
    output.mkdir(parents=True, exist_ok=True)
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
                            page.on('dialog', lambda dialog: dialog.accept())
                            page.on('request', lambda request: submissions.append(request.post_data_json)
                                    if request.method == 'POST' and request.url.endswith('/choice') else None)
                            page.goto(f'http://127.0.0.1:{httpd.server_port}')
                            page.wait_for_function('window.GameThemes && configData')
                            page.locator(f'[data-theme-picker=start] [data-theme-choice={theme}]').click()
                            game = fixture(engine)
                            page.evaluate('async id => loadGame(id)', game.id)
                            explore(page)
                            saved = engine.store.load(game.id)
                            record = saved.generated_event_state['active']
                            event_id = record['id']
                            public = page.evaluate('game.pending_event')
                            assert 'runtime' not in public
                            assert all('result_text' not in row and 'effects' not in row for row in public['choices'])
                            page.reload()
                            page.wait_for_function('configData')
                            page.evaluate('async id => loadGame(id)', game.id)
                            assert page.evaluate('game.pending_event.id') == event_id
                            assert engine.store.load(game.id).generated_event_state['active'] == record
                            page.locator('#event-card').scroll_into_view_if_needed()
                            page.screenshot(path=str(output / f'{theme}-{width}.png'))
                            correct = next(row for row in record['choices'] if row['reward'])
                            pick(page, correct['id'])
                            page.wait_for_function('!busy && !game.pending_event')
                            saved = engine.store.load(game.id)
                            assert saved.generated_event_state['last_result']['signal'] == correct['signal']
                            assert saved.generated_event_state['active'] is None

                            # An old page from the same family must not resolve
                            # the next unique generated event or replay a POST.
                            explore(page)
                            old_id = page.evaluate('game.pending_event.id')
                            engine.choose(game.id, 'leave', event_id=old_id)
                            new = engine.advance(game.id, 'generated_explore')
                            engine.get_game(game.id)
                            before = engine.store._path(game.id).read_bytes()
                            count = len(submissions)
                            pick(page, 'leave')
                            page.wait_for_function('(id) => !busy && game.pending_event?.id === id', arg=new['pending_event']['id'])
                            assert len(submissions) == count + 1
                            assert engine.store._path(game.id).read_bytes() == before

                            current = engine.store.load(game.id)
                            current.player.hp, current.player.mp = 1, 0
                            engine.store.save(current)
                            page.evaluate('async id => loadGame(id)', game.id)
                            options = page.evaluate('game.pending_event.choices')
                            for index, row in enumerate(options):
                                button = page.locator('#event-choices button').nth(index)
                                assert button.is_enabled() if row['id'] == 'leave' else button.is_disabled()
                            pick(page, 'leave')
                            page.wait_for_function('!busy && !game.pending_event')

                            # An earned ordinary reward behind a generated
                            # event remains stable and can actually be claimed.
                            current = engine.store.load(game.id)
                            current.pending_event = engine._dependencies.advancement._prepare_generated_event(current)
                            reward = engine._prepare_treasure_reward_event(current, random.Random(19))
                            current.pending_event['_followup_event'] = reward
                            engine.store.save(current)
                            page.evaluate('async id => loadGame(id)', game.id)
                            pick(page, 'leave')
                            page.wait_for_function('(id) => !busy && game.pending_event?.id === id', arg=reward['id'])
                            assert page.evaluate('game.pending_event.runtime') == reward['runtime']
                            pick(page, 'pill')
                            page.wait_for_function('!busy && !game.pending_event')
                            assert engine.store.load(game.id).pending_event is None
                            assert page.locator('#action-card').is_visible()
                            if not page.locator('[data-action="generated_explore"]').is_visible():
                                page.locator('#tab-living').click()
                            assert page.locator('[data-action="generated_explore"]').is_enabled()
                            assert not errors, errors
                            print(f'Generated events UI passed: {theme} {width}x{height}', flush=True)
                            page.close()
                    browser.close()
            finally:
                httpd.shutdown()
                httpd.server_close()
    print('Generated events UI passed: four themes, mobile/desktop, real time/action, reload, hidden data, stale recovery, disabled choices and rewards')


if __name__ == '__main__':
    main()
