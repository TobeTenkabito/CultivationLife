"""Real HTTP/UI: four local contacts, read-only directory and funded follow-up."""
import json
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
from cultivation_life.rules import add_item, max_hp, max_mp
from cultivation_life.system.heavens.definitions import CONTACT_SITES
from cultivation_life.system.heavens.state import create_echo, get_echo


def main():
    output = ROOT / 'build/heavens-upper-browser'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        engine = GameEngine(ROOT, root / 'saves')
        keys = []
        for site in CONTACT_SITES:
            key = engine.create_game('诸天访学', 'supreme_metal', site.visitor_path, 4242, preset_id='core')['id']
            game = engine.store.load(key)
            p = game.player
            p.world, p.location_id, p.realm_index, p.path = site.world, site.location_id, 9, site.visitor_path
            p.immortal_power_converted, p.lifespan = site.world == 'celestial', None
            p.hp, p.mp = max_hp(p), max_mp(p)
            p.next_tribulation_age = 999999
            game.settings['silent_events'] = True
            add_item(p, 'spirit_stone', 100000)
            engine.store.save(game)
            keys.append(key)
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', root):
            httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(headless=True)
                    page = browser.new_page(viewport={'width':1440, 'height':1050})
                    errors, results = [], []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.goto(f'http://127.0.0.1:{httpd.server_port}')
                    page.wait_for_function('window.GameThemes && configData')
                    for key, site in zip(keys, CONTACT_SITES):
                        page.evaluate('async id=>{await loadGame(id)}', key)
                        if not page.locator('#heavens-card').is_visible():
                            page.locator('[data-panel-target=heavens]').click()
                        original = engine.store._path(key).read_bytes()
                        for remote in CONTACT_SITES:
                            page.get_by_role('tab',name='诸界',exact=True).click()
                            page.get_by_label('选择界域',exact=True).select_option(remote.world)
                            page.get_by_role('button',name='查看'+remote.name,exact=True).click()
                            page.wait_for_function('id=>game.heavens.target_id===id', arg=remote.id)
                            if remote.id != site.id:
                                assert page.locator('#heavens-content .heavens-actions button:enabled').count() == 0
                        page.get_by_role('tab',name='诸界',exact=True).click()
                        page.get_by_label('选择界域',exact=True).select_option(site.world)
                        page.get_by_role('button',name='查看'+site.name,exact=True).click()
                        page.wait_for_function('id=>game.heavens.target_id===id', arg=site.id)
                        assert engine.store._path(key).read_bytes() == original
                        label = '体察潮汐' if site.id == 'sea_echo' else f'体察{site.evidence[0]}'
                        page.get_by_role('button', name=label, exact=True).click()
                        page.locator('#game-confirm-backdrop:not(.hidden)').wait_for()
                        assert '20 年' in page.locator('#game-confirm-body').inner_text()
                        assert engine.store._path(key).read_bytes() == original
                        page.locator('#game-confirm-accept').click()
                        page.wait_for_function('!busy && game.heavens.next_command_seq===2')
                        work = engine.store.load(key)
                        echo = get_echo(work.heavens_state['runtime'], site.id)
                        assert echo and work.world_npcs[echo['visitor_id']].world == site.world
                        assert page.locator('#heavens-content h3').filter(has_text=site.name).is_visible()
                        for width in (1440,393):
                            page.set_viewport_size({'width':width, 'height':1050 if width==1440 else 852})
                            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                            assert page.locator('#heavens-content').evaluate('(el)=>el.scrollWidth<=el.clientWidth+1')
                            page.screenshot(path=str(output / f'{site.world}-{width}.png'))
                        results.append(dict(world=site.world, observation_years=work.heavens_state['runtime']['processed_years']))
                        page.set_viewport_size({'width':1440,'height':1050})
                    # Prepared evidence fixture: only the follow-up runs through the UI.
                    key, site = keys[-1], CONTACT_SITES[-1]
                    work = engine.store.load(key)
                    echo = get_echo(work.heavens_state['runtime'], site.id)
                    echo.update(observed_cycle=echo['cycle'], history_checked=True, exchanged=True, project_stones=20000)
                    work.heavens_state['runtime']['tasks'] = []
                    work.pending_event = None
                    engine.store.save(work)
                    page.evaluate('async id=>{await loadGame(id)}', key)
                    before = engine.store._path(key).read_bytes()
                    page.get_by_role('tab',name='往来',exact=True).click()
                    page.get_by_role('button',name='协作校订旧录',exact=True).click()
                    page.locator('#game-confirm-backdrop:not(.hidden)').wait_for()
                    assert '2,500' in page.locator('#game-confirm-body').inner_text()
                    assert engine.store._path(key).read_bytes() == before
                    page.locator('#game-confirm-accept').click()
                    page.wait_for_function('!busy && game.heavens.next_command_seq===3')
                    saved = engine.store.load(key)
                    assert saved.heavens_state['runtime']['tasks'][-1]['action'] == 'correspond'
                    assert get_echo(saved.heavens_state['runtime'], site.id)['project_stones'] == 17500
                    assert not errors, errors
                    (output/'report.json').write_text(json.dumps(dict(worlds=results, widths=[1440,393],
                        directory_read_only=True, foreign_actions_disabled=True, correspondence_submitted=True,
                        errors=errors), indent=2), encoding='utf-8')
                    browser.close()
            finally:
                httpd.shutdown()
                httpd.server_close()
    print('Four-world browser checks passed')


if __name__ == '__main__':
    main()
