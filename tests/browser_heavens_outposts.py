"""Real HTTP clicks for frontier authorization, construction, stale UI and return."""
import json
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
from cultivation_life.system.heavens.outpost_runtime import get
from cultivation_life.system.heavens.outpost_runtime import wallet
from cultivation_life.system.economy.ledger import balance
from test_heavens_outposts import frontier
from scripts.browser_navigation import navigation_locator


def main():
    output = ROOT / 'build/heavens-outposts-browser'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        engine, key, _ = frontier.__wrapped__(Path(folder))
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', Path(folder)):
            httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(headless=True)
                    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
                    page.set_default_timeout(60000)
                    errors, commands = [], []
                    page.on('pageerror', lambda e: errors.append(str(e)))
                    page.on('request', lambda r: commands.append(r.post_data_json) if r.method == 'POST' and r.url.endswith('/heavens-command') else None)
                    page.goto(f'http://127.0.0.1:{httpd.server_port}')
                    page.wait_for_function('window.GameThemes && configData')
                    page.evaluate('async id => loadGame(id)', key)
                    navigation_locator(page, '[data-panel-target=heavens]').click()
                    page.get_by_role('tab', name='诸界', exact=True).click()
                    page.get_by_role('button', name='查看跨界开拓', exact=True).click()
                    page.get_by_role('button', name='查看天剑宗·异界分驻地', exact=True).click()

                    def choose(action):
                        page.get_by_label('选择开拓事务', exact=True).select_option(action)

                    def act(action, *, stale=False):
                        choose(action)
                        seq = page.evaluate('game.heavens.next_command_seq')
                        page.locator(f'[data-heavens-action={action}]').click()
                        page.locator('#game-confirm-backdrop:not(.hidden)').wait_for()
                        if stale:
                            g = engine.store.load(key)
                            engine.heavens_command(key, g.heavens_state['command_seq']+1, g.heavens_state['revision'], 'configure', None, {'watch': False})
                        page.locator('#game-confirm-accept').click()
                        page.wait_for_function('seq => !busy && game.heavens.next_command_seq >= seq+1', arg=seq)
                        page.wait_for_timeout(150)

                    # A real second-window mutation invalidates the displayed
                    # quote. One POST, authoritative refresh, no replay.
                    act('outpost_authorize', stale=True)
                    assert get(engine.store.load(key), 'outpost:tianjian') is None
                    assert len([c for c in commands if c['action'] == 'outpost_authorize']) == 1
                    act('outpost_authorize')
                    page.get_by_role('tab', name='派驻与补给', exact=True).click()
                    act('outpost_dispatch')
                    person = get(engine.store.load(key), 'outpost:tianjian')['units'][0]['person_id']
                    page.get_by_role('tab', name='授权与往返', exact=True).click()
                    for _ in range(8): act('outpost_wait')
                    assert engine.store.load(key).world_npcs[person].world == 'demon'
                    act('outpost_depart')
                    assert engine.store.load(key).player.world == 'demon'
                    for _ in range(10): act('outpost_wait')
                    assert get(engine.store.load(key), 'outpost:tianjian')['status'] == 'active'
                    page.get_by_role('tab', name='驻地与仓储', exact=True).click()
                    assert '当地经费' in page.locator('#heavens-body').inner_text()
                    for theme in 'abdf':
                        page.locator('#heavens-toggle').click()
                        page.locator('#theme-open').click()
                        page.locator(f'[data-theme-picker=dialog] [data-theme-choice={theme}]').click()
                        page.evaluate('GameThemes.saved')
                        page.locator('[data-close-dialog=theme-dialog]').click()
                        navigation_locator(page, '[data-panel-target=heavens]').click()
                        for width, height in ((1440,1000),(412,915),(915,412)):
                            page.set_viewport_size({'width':width,'height':height})
                            page.wait_for_timeout(100)
                            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
                            page.screenshot(path=str(output / f'{theme}-{width}.png'))
                    page.set_viewport_size({'width':1440,'height':1000})
                    act('outpost_suspend')
                    act('outpost_activate')
                    # Real prepared treasure choices remain available while
                    # frontier operations are blocked by a pending event.
                    g = engine.store.load(key)
                    g.pending_event = engine._prepare_treasure_reward_event(g, random.Random(2))
                    engine.store.save(g)
                    page.evaluate('async id=>loadGame(id)', key)
                    choose('outpost_suspend')
                    assert page.locator('[data-heavens-action=outpost_suspend]').is_disabled()
                    event_id = engine.store.load(key).pending_event['id']
                    page.locator('#heavens-toggle').click()
                    page.locator('#event-choices button').first.click()
                    page.wait_for_function('id=>!busy && game.pending_event?.id !== id', arg=event_id)
                    assert not page.evaluate('busy')
                    navigation_locator(page, '[data-panel-target=heavens]').click()
                    page.get_by_role('tab', name='授权与往返', exact=True).click()
                    act('outpost_return')
                    assert engine.store.load(key).player.world == 'human'
                    assert engine.store.load(key).sects['tianjian'].world == 'human'
                    g = engine.store.load(key)
                    before_supply = balance(g, wallet(get(g, 'outpost:tianjian')))
                    page.get_by_role('tab', name='派驻与补给', exact=True).click()
                    act('outpost_supply')
                    courier = next(u['person_id'] for u in get(engine.store.load(key), 'outpost:tianjian')['units'] if u['courier'])
                    page.get_by_role('tab', name='授权与往返', exact=True).click()
                    for _ in range(8): act('outpost_wait')
                    g = engine.store.load(key)
                    row = get(g, 'outpost:tianjian')
                    unit = next(u for u in row['units'] if u['person_id'] == courier)
                    assert g.world_npcs[courier].world == 'demon' and not unit['delivered']
                    assert balance(g, wallet(row)) == before_supply
                    act('outpost_depart')
                    unit = next(u for u in get(engine.store.load(key), 'outpost:tianjian')['units'] if u['person_id'] == courier)
                    assert unit['delivered']
                    for _ in range(8): act('outpost_wait')
                    assert engine.store.load(key).world_npcs[courier].world == 'human'
                    act('outpost_return')
                    unit = next(u for u in get(engine.store.load(key), 'outpost:tianjian')['units'] if u['person_id'] == courier)
                    assert unit['phase'] == 'home'
                    page.reload()
                    page.wait_for_function('window.GameThemes && configData')
                    page.evaluate('async id=>loadGame(id)', key)
                    assert get(engine.store.load(key), 'outpost:tianjian')['visit']['status'] == 'returned'
                    assert not errors, errors
                    (output / 'report.json').write_text(json.dumps(dict(commands=len(commands),themes=4,viewports=3,errors=errors),ensure_ascii=False,indent=2),encoding='utf-8')
                    browser.close()
                    print('PASS: frontier HTTP clicks, stale rejection, original NPC/build/supply accounts, four themes, events and reload return')
            finally:
                httpd.shutdown()


if __name__ == '__main__':
    main()
