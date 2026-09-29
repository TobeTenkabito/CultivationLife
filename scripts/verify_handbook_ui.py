"""Handbook configuration matrix and real browser reading, without user saves."""
import copy
import json
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine


class Quiet(server.Handler):
    def log_message(self, *args):
        pass


def verify_matrix(page, config):
    packages = page.evaluate('TutorialHandbook.packages')
    reports = []
    for mask in range(1 << len(packages)):
        extensions = [dict(id=id_, name=name, kind='dlc', enabled=bool(mask & (1 << i)),
                           status='loaded' if mask & (1 << i) else 'disabled')
                      for i, (key, id_, name, *_) in enumerate(packages)]
        reports.append(dict(**config, extensions=extensions))
    results = page.evaluate('(configs)=>configs.map(c=>TutorialHandbook.build(c))', reports)
    for mask, chapters in enumerate(results):
        by_id = {c['id']: c for c in chapters}
        assert len(by_id) == len(chapters)
        assert 'routes' in by_id and 'worlds' in by_id and 'save' in by_id
        for i, (key, *_) in enumerate(packages):
            assert (f'dlc-{key}' in by_id) == bool(mask & (1 << i)), (mask, key)
        route_text = json.dumps(by_id['routes'], ensure_ascii=False)
        assert '妖界与幻冥界都是二级' in route_text
        assert '魔气必须达到 8 级' in route_text
        assert ('没有本体替代' in route_text) == (not bool(mask & 1))
        assert ('不按灵气与阴气经验分流' in route_text) == (not bool(mask & 64))
        intelligence = by_id['commissions']['sections'][-1][1]
        assert ('每颗星有一次线索尝试' in intelligence) == bool(mask & 16)
    # Enabled preferences are not necessarily loaded: errors/pending restart stay inactive.
    for status in ('disabled', 'error', 'incompatible'):
        cfg = {**config, 'extensions': [dict(id=p[1], name=p[2], kind='dlc',
                      enabled=True, next_enabled=True, status=status) for p in packages]}
        assert not any(c['id'].startswith('dlc-') for c in page.evaluate('c=>TutorialHandbook.build(c)', cfg))
    active = copy.deepcopy(reports[-1])
    for row in active['extensions']:
        row.update(next_enabled=False)
    page.evaluate('c=>TutorialGuide.configure(c)', active)
    assert page.locator('[data-chapter^="dlc-"]').count() == 7
    assert '待重启' in page.locator('.handbook-edition').inner_text()
    # An obsolete filter must not hide every chapter when configuration changes.
    page.evaluate("document.querySelectorAll('.handbook-categories button').forEach(b=>{if(b.textContent==='DLC')b.click();})")
    page.evaluate('c=>TutorialGuide.configure(c)', reports[0])
    assert page.locator('.handbook-categories [aria-pressed=true]').inner_text() == '全部'
    mod = {**config, 'extensions':[dict(id='example',name='示例',kind='mod',status='loaded')]}
    page.evaluate('c=>TutorialGuide.configure(c)',mod)
    assert '纯本体规则' not in page.locator('.handbook-edition').inner_text()
    print(f"Chapters: base {len(results[0])}, all DLC {len(results[-1])}",flush=True)
    print('128 DLC combinations, failed loads and restart preferences passed', flush=True)
    return reports[0], reports[-1]


def main():
    with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
        server.PERSISTENCE_ROOT = Path(folder)
        engine = server.ENGINE = GameEngine(ROOT, Path(folder)/'saves')
        httpd = ThreadingHTTPServer(('127.0.0.1', 0), Quiet)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        errors = []
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                page = browser.new_page(viewport={'width': 1440, 'height': 1000})
                page.on('pageerror', lambda e: errors.append(str(e)))
                page.goto(f'http://127.0.0.1:{httpd.server_port}')
                page.wait_for_function('configData && window.TutorialGuide')
                config = page.evaluate('({base_game:configData.base_game})')
                pure, full = verify_matrix(page, config)
                page.evaluate("async()=>{let g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'百科验收',spirit_root:'supreme_wood',path:'dao',seed:1481})});await loadGame(g.id);}")
                page.wait_for_function('game && !busy')
                key = page.evaluate('game.id')
                before = engine.store._path(key).read_bytes()
                page.evaluate("UtilityPanels.open('settings')")
                for theme in 'abcdef':
                    page.evaluate('(t)=>document.querySelector(`[data-theme-choice="${t}"]`).click()', theme)
                    page.evaluate('GameThemes.saved')
                    for cfg, label in ((pure, 'base'), (full, 'full')):
                        page.evaluate('c=>TutorialGuide.configure(c)', cfg)
                        page.locator('.handbook-categories button', has_text='全部').click()
                        for width, height in ((1440,1000),(412,915),(915,412)):
                            page.set_viewport_size({'width':width,'height':height})
                            page.locator('#handbook-search').fill('魔气')
                            assert page.locator('[data-chapter="routes"]').is_visible()
                            assert page.locator('[data-chapter="routes"]').get_attribute('open') is not None
                            assert page.locator('#handbook-search').evaluate('e=>e.scrollWidth<=e.clientWidth+2')
                            assert page.locator('#settings-card').evaluate('e=>e.scrollWidth<=e.clientWidth+2')
                            if width==412 and label=='full':
                                page.locator('[data-chapter="routes"] summary').scroll_into_view_if_needed()
                                page.screenshot(path=str(ROOT/f'build/handbook-{theme}-mobile.png'))
                        page.locator('#handbook-search').fill('并不存在的词条123')
                        assert page.locator('#tutorial-handbook details:visible').count()==0
                        assert '没有匹配章节' in page.locator('.handbook-matches').inner_text()
                        page.locator('#handbook-search').fill('')
                        dlc_tab=page.locator('.handbook-categories button',has_text='DLC')
                        if label=='full':
                            dlc_tab.click()
                            assert page.locator('#tutorial-handbook details:visible').count()==7
                            page.locator('[data-chapter="dlc-buddhist"] summary').click()
                            assert '不能跨大境界' in page.locator('[data-chapter="dlc-buddhist"]').inner_text()
                        else:
                            assert dlc_tab.count()==0
                    print(f'Theme {theme}: full/base, desktop/portrait/landscape, search and filters passed',flush=True)
                assert engine.store._path(key).read_bytes() == before, 'Reading changed save/time/RNG'
                assert not errors, errors
                browser.close()
        finally:
            httpd.shutdown()
    print('Handbook UI passed: no save mutations or JavaScript errors')


if __name__ == '__main__':
    main()
