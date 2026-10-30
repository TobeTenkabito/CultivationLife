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
    positions = {row[0]: i for i, row in enumerate(packages)}
    reports = []
    for mask in range(1 << len(packages)):
        extensions = [dict(id=id_, name=name, kind='dlc', enabled=bool(mask & (1 << i)),
                           status='loaded' if mask & (1 << i) else 'disabled')
                      for i, (key, id_, name, *_) in enumerate(packages)]
        reports.append(dict(**config, extensions=extensions))
    # Keep only compact assertions across the bridge, rather than 2048 copies
    # of every chapter. Each configuration is still assembled and checked.
    results = page.evaluate('''configs=>configs.map(c=>{
        const chapters=TutorialHandbook.build(c,{player:{realm_index:9,world:'asura'},asura:{available:true}});
        const by=Object.fromEntries(chapters.map(c=>[c.id,c]));
        const economics=['economic-materials','economic-recipes','economic-demand','economic-estates','economic-war'];
        const text=JSON.stringify(economics.map(id=>by[id]));
        return {ids:chapters.map(c=>c.id),count:chapters.length,
          economics:economics.every(id=>!!by[id]),
          quantities:['四十五种','七十二种','一百零八种'].every(s=>text.includes(s)),
          playerLanguage:['分桶','缓存','代表商品','后台循环','聚合近似'].every(s=>!text.includes(s)),
          validUnits:!JSON.stringify(by).includes('500 年'),
          routes:JSON.stringify(by.routes),intelligence:by.commissions.sections.at(-1)[1]};
    })''', reports)
    for mask, row in enumerate(results):
        by_id = set(row['ids'])
        assert len(by_id) == row['count']
        assert {'routes','worlds','save','heavens-outposts','second-nascent','interface-guide'} <= by_id
        assert all(row[k] for k in ('economics','quantities','playerLanguage','validUnits')), mask
        for i, (key, *_) in enumerate(packages):
            chapter_id = 'trial-sites' if key == 'trial' else f'dlc-{key}'
            assert (chapter_id in by_id) == bool(mask & (1 << i)), (mask, key)
        route_text = row['routes']
        assert '妖界与幻冥界都是二级' in route_text
        assert '魔气必须达到 8 级' in route_text
        assert ('没有本体替代' in route_text) == (not bool(mask & (1 << positions['monster'])))
        assert ('不按灵气与阴气经验分流' in route_text) == (not bool(mask & (1 << positions['buddhist'])))
        intelligence = row['intelligence']
        assert ('每颗星有一次线索尝试' in intelligence) == bool(mask & (1 << positions['tianji']))
    # Enabled preferences are not necessarily loaded: errors/pending restart stay inactive.
    for status in ('disabled', 'error', 'incompatible'):
        cfg = {**config, 'extensions': [dict(id=p[1], name=p[2], kind='dlc',
                      enabled=True, next_enabled=True, status=status) for p in packages]}
        assert not any(c['id'].startswith('dlc-') or c['id']=='trial-sites' for c in page.evaluate('c=>TutorialHandbook.build(c)', cfg))
    active = copy.deepcopy(reports[-1])
    for row in active['extensions']:
        row.update(next_enabled=False)
    page.evaluate('c=>TutorialGuide.configure(c)', active)
    assert page.locator('[data-chapter^="dlc-"], [data-chapter="trial-sites"]').count() == len(packages)-1
    assert '待重启' in page.locator('.handbook-edition').inner_text()
    # An obsolete filter must not hide every chapter when configuration changes.
    page.evaluate("document.querySelectorAll('.handbook-categories button').forEach(b=>{if(b.textContent==='DLC')b.click();})")
    page.evaluate('c=>TutorialGuide.configure(c)', reports[0])
    assert page.locator('.handbook-categories [aria-pressed=true]').inner_text() == '全部'
    mod = {**config, 'extensions':[dict(id='example',name='示例',kind='mod',status='loaded')]}
    page.evaluate('c=>TutorialGuide.configure(c)',mod)
    assert '纯本体规则' not in page.locator('.handbook-edition').inner_text()
    print(f"Chapters: base {results[0]['count']}, all DLC {results[-1]['count']}",flush=True)
    print(f'{1 << len(packages)} DLC combinations, failed loads and restart preferences passed', flush=True)
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
                page.evaluate("async()=>{let g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'百科验收',spirit_root:'supreme_wood',path:'demonic',preset_id:'asura_upper',seed:1481})});await loadGame(g.id);}")
                page.wait_for_function('game && !busy')
                key = page.evaluate('game.id')
                before = engine.store._path(key).read_bytes()
                page.evaluate("UtilityPanels.open('settings')")
                for theme in 'abdf':
                    page.evaluate('(t)=>document.querySelector(`[data-theme-choice="${t}"]`).click()', theme)
                    page.evaluate('GameThemes.saved')
                    for cfg, label in ((pure, 'base'), (full, 'full')):
                        page.evaluate('c=>TutorialGuide.configure(c)', cfg)
                        try:
                            page.locator('.handbook-categories button', has_text='全部').click()
                        except Exception:
                            print(page.evaluate('JSON.stringify([document.querySelector("#settings-card"),document.querySelector(".handbook-categories button")].map(e=>({rect:e.getBoundingClientRect().toJSON(),scrollTop:e.scrollTop,style:{height:getComputedStyle(e).height,maxHeight:getComputedStyle(e).maxHeight,top:getComputedStyle(e).top,bottom:getComputedStyle(e).bottom,overflow:getComputedStyle(e).overflow,transform:getComputedStyle(e).transform}})))'),flush=True)
                            page.screenshot(path=str(ROOT/'build/handbook-failure-280.png'))
                            raise
                        for width, height in ((1440,1000),(412,915),(915,412)):
                            page.set_viewport_size({'width':width,'height':height})
                            page.locator('#handbook-search').fill('魔气')
                            assert page.locator('[data-chapter="routes"]').is_visible()
                            assert page.locator('[data-chapter="routes"]').get_attribute('open') is not None
                            assert page.locator('#handbook-search').evaluate('e=>e.scrollWidth<=e.clientWidth+2')
                            assert page.locator('#settings-card').evaluate('e=>e.scrollWidth<=e.clientWidth+2')
                            for term, chapter in (('九类原料', 'economic-materials'), ('军需', 'economic-war'), ('掌柜', 'economic-estates')):
                                page.locator('#handbook-search').fill(term)
                                article = page.locator(f'[data-chapter="{chapter}"]')
                                assert article.is_visible() and article.get_attribute('open') is not None
                                assert page.locator('#settings-card').evaluate('e=>e.scrollWidth<=e.clientWidth+2')
                                if term == '九类原料' and width == 412 and label == 'full':
                                    article.locator('summary').scroll_into_view_if_needed()
                                    page.screenshot(path=str(ROOT/f'build/handbook-economy-{theme}-mobile.png'))
                            page.locator('#handbook-search').fill('魔气')
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
                            assert page.locator('#tutorial-handbook details:visible').count()==page.evaluate('TutorialHandbook.packages.length')
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
