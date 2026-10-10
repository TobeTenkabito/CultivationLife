"""Real HTTP/Chromium material freight trips, separate detail pages and mobile layout."""
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
from cultivation_life.system.heavens.definitions import CONTACT_SITES, VISIT_DESTINATIONS, default_site
from cultivation_life.system.heavens.state import create_echo, get_echo
from test_heavens_upper_worlds import MATERIALS


from scripts.browser_navigation import navigation_locator

def main():
    output = ROOT / 'build/heavens-freight-browser'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        engine = GameEngine(ROOT, root / 'saves')
        ids = []
        for site in CONTACT_SITES:
            key = engine.create_game('诸天访学', 'supreme_metal', site.visitor_path, 4242, preset_id='core')['id']
            game = engine.store.load(key)
            p = game.player
            p.world, p.location_id, p.realm_index = site.world, site.location_id, 9
            p.immortal_power_converted, p.lifespan = site.world == 'celestial', None
            p.hp, p.mp = max_hp(p), max_mp(p)
            p.next_tribulation_age = 999999
            game.settings['silent_events'] = True
            add_item(p, 'spirit_stone', 100000)
            echo = create_echo(engine._dependencies.heavens, game, site.id)
            echo.update(history_checked=True, exchanged=True, correspondence_completed=True, project_stones=17500)
            engine.store.save(game)
            for action in ('visit_depart', 'visit_study', 'visit_return', 'mission_start', *(['mission_wait']*8)):
                current = engine.store.load(key)
                state = current.heavens_state
                engine.heavens_command(key, state['command_seq']+1, state['revision'], action, site.id, {})
            game=engine.store.load(key)
            game.player.formation_materials.append(dict(id='cargo-original', material_id=MATERIALS[CONTACT_SITES.index(site)], name='运往异界的原阵材', acquired_tier=9))
            engine.store.save(game)
            ids.append(key)
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', root):
            httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(headless=True)
                    page = browser.new_page(viewport={'width':1440,'height':1050})
                    errors, results = [], []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.goto(f'http://127.0.0.1:{httpd.server_port}')
                    page.wait_for_function('window.GameThemes && configData')
                    def act(label, years):
                        seq = page.evaluate('game.heavens.next_command_seq')
                        page.get_by_role('button',name=label,exact=True).click()
                        page.locator('#game-confirm-backdrop:not(.hidden)').wait_for()
                        assert f'{years} 年' in page.locator('#game-confirm-body').inner_text()
                        page.locator('#game-confirm-accept').click()
                        page.wait_for_function('seq=>!busy && game.heavens.next_command_seq===seq+1', arg=seq)
                    for index,(key,site) in enumerate(zip(ids,CONTACT_SITES)):
                        page.evaluate('async id=>{await loadGame(id)}', key)
                        if not page.locator('#heavens-card').is_visible():
                            navigation_locator(page,'[data-panel-target=heavens]').click()
                        page.get_by_role('tab',name='诸界',exact=True).click()
                        page.get_by_role('button',name='查看'+site.name,exact=True).click()
                        page.get_by_role('tab',name='运材',exact=True).click()
                        page.get_by_role('button',name='委托运送阵材',exact=True).wait_for()
                        before = engine.store.load(key)
                        disk = engine.store._path(key).read_bytes()
                        if index == 0:
                            for theme in 'abdf':
                                page.locator('#theme-open').click()
                                page.locator(f'[data-theme-picker=dialog] [data-theme-choice={theme}]').click()
                                page.evaluate('GameThemes.saved')
                                page.locator('[data-close-dialog=theme-dialog]').click()
                                for width in (1440,393):
                                    page.set_viewport_size({'width':width,'height':1050 if width==1440 else 852})
                                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                                    assert page.locator('#heavens-content').evaluate('(el)=>el.scrollWidth<=el.clientWidth+1')
                                    assert page.locator('#heavens-content .heavens-actions').count() == 1
                                    assert page.get_by_role('button',name='对照抄录',exact=True).count() == 0
                                    page.screenshot(path=str(output/f'{theme}-{width}-visit.png'))
                            assert engine.store._path(key).read_bytes() == disk
                        act('委托运送阵材',0)
                        saved=engine.store.load(key)
                        echo=get_echo(saved.heavens_state['runtime'],site.id)
                        identity=echo['visitor_id']
                        assert saved.world_npcs[identity].world==site.world
                        assert echo['project_stones']==4500
                        act('等候一年',1)
                        act('等候一年',1)
                        destination=default_site(VISIT_DESTINATIONS[site.id])
                        saved=engine.store.load(key)
                        assert saved.world_npcs[identity].world==destination.world
                        assert echo['visitor_id']==identity
                        assert not saved.player.formation_materials
                        assert get_echo(saved.heavens_state['runtime'],site.id)['freight']['delivered']
                        page.reload()
                        page.wait_for_function('window.GameThemes && configData')
                        page.evaluate('async id=>{await loadGame(id)}',key)
                        if not page.locator('#heavens-card').is_visible():
                            navigation_locator(page,'[data-panel-target=heavens]').click()
                        page.get_by_role('tab',name='行程',exact=True).click()
                        page.get_by_role('tab',name='货运',exact=True).click()
                        page.get_by_role('button',name='查看'+site.visitor_name+'的运材委托',exact=True).click()
                        page.get_by_role('button',name='等候一年',exact=True).wait_for()
                        for _ in range(2):
                            act('等候一年',1)
                        saved=engine.store.load(key)
                        mission=get_echo(saved.heavens_state['runtime'],site.id)['freight']
                        assert mission['status']=='completed' and mission['spent']==4000
                        assert saved.world_npcs[identity].world==site.world
                        assert saved.world_npcs[identity].age==before.world_npcs[identity].age+4
                        assert saved.player.world==site.world
                        act('领取托存物资与款项',0)
                        assert get_echo(engine.store.load(key).heavens_state['runtime'],site.id)['freight']['claimed']
                        assert page.get_by_role('button',name='委托运送阵材',exact=True).count()==0
                        results.append(dict(source=site.world,destination=destination.world,years=4,person_id=identity))
                    assert not errors,errors
                    (output/'report.json').write_text(json.dumps(dict(trips=results,themes=list('abdf'),
                        widths=[1440,393],reload_freight=True,navigation_read_only=True,errors=errors),indent=2),encoding='utf-8')
                    browser.close()
            finally:
                httpd.shutdown()
                httpd.server_close()
    print('Four-world civilian freight browser checks passed')


if __name__ == '__main__':
    main()
