"""Real HTTP survey, isolated subpages, reload and four-theme responsive checks."""
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
from cultivation_life.models import SectNpc
from cultivation_life.rules import max_hp, max_mp


def main():
    output = ROOT/'build/heavens-survey-browser'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        engine = GameEngine(ROOT, root/'saves')
        key = engine.create_game('遗址同勘', 'supreme_metal', 'dao', 4242, preset_id='core')['id']
        game = engine.store.load(key)
        p = game.player
        p.world, p.location_id, p.realm_index = 'human', 'wudi_plain', 4
        p.lifespan, p.next_tribulation_age = None, 999999
        p.hp, p.mp = max_hp(p), max_mp(p)
        npc = SectNpc('survey-resident', '温砚', '', 4, 1, 80, 1000, spirit_root='supreme_water',
                      world='human', affinity=30, location_id='wudi_plain', encountered_player=True)
        game.world_npcs[npc.id] = npc
        game.settings['silent_events'] = True
        engine.store.save(game)
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', root):
            httpd = ThreadingHTTPServer(('127.0.0.1',0), server.Handler)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(headless=True)
                    page = browser.new_page(viewport={'width':1440,'height':1050})
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.goto(f'http://127.0.0.1:{httpd.server_port}')
                    page.wait_for_function('window.GameThemes && configData')
                    page.evaluate('async id=>{await loadGame(id)}', key)
                    page.locator('[data-panel-target=heavens]').click()
                    page.get_by_role('tab',name='异象',exact=True).click()
                    page.get_by_role('button',name='查看因果遗址',exact=True).click()
                    def act(label, years):
                        disk = engine.store._path(key).read_bytes()
                        seq = page.evaluate('game.heavens.next_command_seq')
                        page.get_by_role('button',name=label,exact=True).click()
                        page.locator('#game-confirm-backdrop:not(.hidden)').wait_for()
                        assert f'{years} 年' in page.locator('#game-confirm-body').inner_text()
                        assert engine.store._path(key).read_bytes() == disk
                        page.locator('#game-confirm-accept').click()
                        page.wait_for_function('seq=>!busy && game.heavens.next_command_seq===seq+1', arg=seq)
                    act('进入因果遗址',0)
                    act('退出因果遗址',0)
                    page.get_by_role('tab',name='同勘',exact=True).click()
                    page.get_by_label('勘察居民',exact=True).select_option(npc.id)
                    disk = engine.store._path(key).read_bytes()
                    for theme in 'abdf':
                        page.locator('#theme-open').click()
                        page.locator(f'[data-theme-picker=dialog] [data-theme-choice={theme}]').click()
                        page.evaluate('GameThemes.saved')
                        page.locator('[data-close-dialog=theme-dialog]').click()
                        for width in (1440,393):
                            page.set_viewport_size({'width':width,'height':1050 if width==1440 else 852})
                            page.locator('[data-survey] h3').scroll_into_view_if_needed()
                            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'), (theme,width)
                            assert page.locator('#heavens-content').evaluate('(el)=>el.scrollWidth<=el.clientWidth+1'), (theme,width)
                            assert page.get_by_role('button',name='进入因果遗址',exact=True).count() == 0
                            assert page.get_by_role('button',name='读取合法抄本',exact=True).count() == 0
                            page.screenshot(path=str(output/f'{theme}-{width}.png'))
                    assert engine.store._path(key).read_bytes() == disk
                    act('邀约勘察',0)
                    for _ in range(2): act('等候一年',1)
                    saved = engine.store.load(key)
                    assert saved.world_npcs[npc.id].world == 'rift'
                    assert saved.world_npcs[npc.id].age == 82
                    act('等候一年',1)
                    assert engine.store.load(key).world_npcs[npc.id].age == 82
                    page.reload()
                    page.wait_for_function('window.GameThemes && configData')
                    page.evaluate('async id=>{await loadGame(id)}',key)
                    if not page.locator('#heavens-card').is_visible():
                        page.locator('[data-panel-target=heavens]').click()
                    page.get_by_role('tab',name='行程',exact=True).click()
                    page.get_by_role('button',name='查看同勘',exact=True).click()
                    page.locator('[data-survey=active]').wait_for()
                    page.get_by_role('tab',name='入口',exact=True).click()
                    act('进入因果遗址',0)
                    page.get_by_role('tab',name='同勘',exact=True).click()
                    for _ in range(8): act('等候一年',1)
                    assert engine.store.load(key).world_npcs[npc.id].age == 90
                    act('交换勘察笔记',0)
                    act('等候一年',1)
                    assert engine.store.load(key).world_npcs[npc.id].world == 'human'
                    page.get_by_role('tab',name='调查',exact=True).click()
                    assert '缩短为 3 年' in page.locator('[data-ruins]').inner_text()
                    for label,years in [('观察阵纹',2),('查证两端关联',4),('读取合法抄本',3)]:
                        act(label,years)
                    assert len(engine.store.load(key).player.formation_materials) == 1
                    assert not errors, errors
                    (output/'report.json').write_text(json.dumps(dict(themes=list('abdf'),widths=[1440,393],
                        outside_frozen=True,reload=True,shared_read_years=3,unique_material=True,errors=errors),indent=2),encoding='utf-8')
                    browser.close()
            finally:
                httpd.shutdown()
                httpd.server_close()
    print('Causal ruins survey browser checks passed')


if __name__ == '__main__':
    main()
