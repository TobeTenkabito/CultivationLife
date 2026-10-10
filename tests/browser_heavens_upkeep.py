"""Real HTTP facilities in four highest worlds, four themes and separate pages."""
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
from cultivation_life.system.formation_system import make_formation_material_instance
from cultivation_life.system.heavens.definitions import CONTACT_SITES
from cultivation_life.system.heavens.state import create_echo, get_echo


from scripts.browser_navigation import navigation_locator

def main():
    output = ROOT / 'build/heavens-upkeep-browser'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        engine = GameEngine(ROOT, root / 'saves')
        ids = []
        for site in CONTACT_SITES:
            key = engine.create_game('护持测试', 'supreme_metal', site.visitor_path, 4242, preset_id='core')['id']
            game = engine.store.load(key)
            p = game.player
            p.world, p.location_id, p.realm_index = site.world, site.location_id, 9
            p.immortal_power_converted, p.lifespan = site.world == 'celestial', None
            p.hp, p.mp = max_hp(p), max_mp(p)
            p.next_tribulation_age = 999999
            game.settings['silent_events'] = True
            add_item(p, 'spirit_stone', 100000)
            echo = create_echo(engine._dependencies.heavens, game, site.id)
            echo.update(history_checked=True, exchanged=True, observed_cycle=0)
            definition = next(d for d in engine._formation_material_defs().values()
                              if d.get('world') == site.world and d.get('tier') == 9)
            material = make_formation_material_instance(definition, source='护持验收', origin_world=site.world)
            p.formation_materials.append(material)
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
                    def open_detail(key, site):
                        page.evaluate('async id=>{await loadGame(id)}', key)
                        if not page.locator('#heavens-card').is_visible():
                            navigation_locator(page,'[data-panel-target=heavens]').click()
                        page.get_by_role('tab',name='行程',exact=True).click()
                        page.get_by_role('tab',name='护持',exact=True).click()
                        back = page.get_by_role('button',name='‹ 返回护持目录',exact=True)
                        if back.count(): back.click()
                        assert page.locator('#heavens-content .heavens-destination').count() == 4
                        page.get_by_role('button',name='查看'+site.name,exact=True).click()
                        page.locator('[data-upkeep]').wait_for()
                    def act(label):
                        seq = page.evaluate('game.heavens.next_command_seq')
                        page.get_by_role('button',name=label,exact=True).click()
                        page.locator('#game-confirm-backdrop:not(.hidden)').wait_for()
                        assert '0 年' in page.locator('#game-confirm-body').inner_text()
                        page.locator('#game-confirm-accept').click()
                        page.wait_for_function('seq=>!busy && game.heavens.next_command_seq===seq+1', arg=seq)
                    for index,(key,site) in enumerate(zip(ids,CONTACT_SITES)):
                        open_detail(key,site)
                        page.get_by_label('维护阵材',exact=True).select_option(index=0)
                        before = engine.store._path(key).read_bytes()
                        page.get_by_role('button',name='部署托管护持',exact=True).click()
                        page.locator('#game-confirm-backdrop:not(.hidden)').wait_for()
                        assert '30000' in page.locator('#game-confirm-body').inner_text().replace(',','')
                        assert engine.store._path(key).read_bytes() == before
                        page.locator('#game-confirm-cancel').click()
                        act('部署托管护持')
                        page.locator('[data-upkeep=active]').wait_for()
                        deployed = engine.store.load(key)
                        row = get_echo(deployed.heavens_state['runtime'],site.id)['upkeep']
                        assert row['escrow']['total'] == 30000 and row['progress'] == 0
                        assert not deployed.player.formation_materials
                        disk = engine.store._path(key).read_bytes()
                        if index == 0:
                            for theme in 'abdf':
                                page.locator('#theme-open').click()
                                page.locator(f'[data-theme-picker=dialog] [data-theme-choice={theme}]').click()
                                page.locator('[data-close-dialog=theme-dialog]').click()
                                for width in (1440,393):
                                    page.set_viewport_size({'width':width,'height':1050 if width==1440 else 852})
                                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                                    assert page.locator('#heavens-content').evaluate('(el)=>el.scrollWidth<=el.clientWidth+1')
                                    assert page.locator('#heavens-content .heavens-actions').count() == 1
                                    assert page.get_by_role('button',name='资助迁居',exact=True).count() == 0
                                    assert page.get_by_role('button',name='对照抄录',exact=True).count() == 0
                                    page.screenshot(path=str(output/f'{theme}-{width}-active.png'))
                            assert engine.store._path(key).read_bytes() == disk
                        if index == 3:
                            remote = engine.store.load(key)
                            remote.player.world, remote.player.location_id, remote.player.realm_index = 'human', 'muling_desert', 4
                            remote.player.hp, remote.player.mp = max_hp(remote.player), max_mp(remote.player)
                            engine.store.save(remote)
                            state = remote.heavens_state
                            response = page.request.post(f'http://127.0.0.1:{httpd.server_port}/api/games/{key}/heavens-command',
                                data=dict(command_seq=state['command_seq']+1,expected_revision=state['revision'],
                                          action='mirror_enter',target_id='mirror_field',options={}))
                            assert response.ok,response.text()
                            assert engine.store.load(key).player.world == 'rift'
                        page.reload()
                        page.wait_for_function('window.GameThemes && configData')
                        open_detail(key,site)
                        page.locator('[data-upkeep=active]').wait_for()
                        if index%2:
                            act('终止托管护持')
                            page.locator('[data-upkeep=cancelled]').wait_for()
                            final = get_echo(engine.store.load(key).heavens_state['runtime'],site.id)
                            assert final['upkeep']['escrow']['refunded'] == 30000 and not final['maintained']
                        else:
                            page.evaluate('async () => mutate(`/api/games/${game.id}/advance`, {action:"rest",years:1})')
                            page.locator('[data-upkeep=completed]').wait_for()
                            final = get_echo(engine.store.load(key).heavens_state['runtime'],site.id)
                            assert final['upkeep']['progress'] == 50 and final['maintained']
                            assert final['upkeep']['escrow']['spent'] == 30000
                        assert page.get_by_role('button',name='部署托管护持',exact=True).count() == 0
                        results.append(dict(world=site.world,status=final['upkeep']['status'],progress=final['upkeep']['progress'],
                                            remote_in_mirror=index == 3))
                    assert not errors,errors
                    (output/'report.json').write_text(json.dumps(dict(facilities=results,themes=list('abdf'),
                        widths=[1440,393],reload=True,preview_read_only=True,errors=errors),indent=2),encoding='utf-8')
                    browser.close()
            finally:
                httpd.shutdown()
                httpd.server_close()
    print('Four-world upkeep browser checks passed')


if __name__ == '__main__':
    main()
