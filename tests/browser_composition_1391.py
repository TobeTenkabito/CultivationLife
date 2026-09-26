"""Acceptance of the approved independent SVG compositions and their live controls."""
import json
import shutil
import sys
import tempfile
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine


def main():
    output=ROOT/'design/release-v1.39.1-comparison'
    output.mkdir(exist_ok=True)
    references=ROOT/'design/main-ui-concepts-20260927-r3'
    themes=json.loads((references/'concepts.json').read_text(encoding='utf-8'))
    with tempfile.TemporaryDirectory() as folder:
        store=Path(folder)
        engine=GameEngine(ROOT,store/'data/saves')
        gid=engine.create_game('青玄','heavenly','dao',1391,preset_id='core')['id']
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',store):
            httpd=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
            threading.Thread(target=httpd.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch(headless=True)
                    page=browser.new_page(viewport={'width':1480,'height':1080},reduced_motion='reduce')
                    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    page.goto(f'http://127.0.0.1:{httpd.server_port}')
                    page.wait_for_function('configData && window.ThemeComposition')
                    page.evaluate('async id=>{await loadGame(id);render(game)}',gid)
                    initial=page.evaluate('JSON.stringify(game)')
                    for t in themes:
                        theme=t['id']
                        page.locator('#theme-open').click()
                        page.locator(f'[data-theme-picker=dialog] [data-theme-choice={theme}]').click()
                        page.evaluate('GameThemes.saved');page.keyboard.press('Escape')
                        page.evaluate('scrollTo(0,0)')
                        def box(selector):return page.locator(selector).bounding_box()
                        action=box('#action-card');hud=box('.hud-identity');hp=box('#hud-hp');core=box('#cultivate-action');body=box('#body-train-action');rest=box('[data-action=rest]');journal=box('.history-card')
                        if theme=='a':
                            assert hud['y']<core['y'] and core['height']>body['height']*1.8
                        elif theme=='b':
                            assert core['x']+core['width']<body['x'] and hp['x']>hud['x']+hud['width']-5
                            assert box('#hud-opportunity')['y']>hud['y']+hud['height']
                        elif theme=='c':
                            assert page.locator('#action-card').evaluate("n=>getComputedStyle(n).borderTopWidth")=='0px'
                            assert core['width']>body['width']*1.4
                            assert page.locator('#history-list').evaluate("n=>getComputedStyle(n).display")=='grid'
                        elif theme=='d':
                            assert abs(core['y']-body['y'])<2 and abs(core['height']-body['height'])<2
                            assert rest['y']>=core['y']+core['height']
                        elif theme=='e':
                            assert box('#main-scenery')['y']<action['y']
                            assert box('#player-hud')['y']>=box('.journal-area')['y']+box('.journal-area')['height']
                            assert page.locator('#player-hud').evaluate("n=>getComputedStyle(n).position")=='relative'
                        elif theme=='f':
                            assert journal['x']>=action['x']+action['width']-1
                            assert body['y']>=core['y']+core['height']-1 and abs(body['x']-core['x'])<2
                        page.screenshot(path=str(output/f'{theme}-actual.png'),clip={'x':120,'y':0,'width':1240,'height':1020},animations='disabled',style='.strategy-dock{visibility:hidden!important}')
                        shutil.copy2(references/f"{theme}-{t['name']}.svg",output/f'{theme}-reference.svg')
                        # Every category retains its real actions, selection and focus through a reflow.
                        for tab,selector in [('living','[data-action=treasure]'),('combat','[data-action=hunt_beast]'),('daily','#cultivate-action')]:
                            page.locator(f'[data-action-tab={tab}]').click()
                            assert page.locator(selector).is_visible()
                            assert page.locator(f'[data-action-tab={tab}]').get_attribute('aria-selected')=='true'
                            assert page.evaluate('JSON.stringify(game)')==initial
                        page.locator('.journal-letter>button').click()
                        assert page.locator('.journal-text').text_content()==page.evaluate('game.history[0].summary')
                        page.keyboard.press('Escape')
                        for width in [1024,800,430]:
                            page.set_viewport_size({'width':width,'height':1000})
                            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),(theme,width)
                            for selector in ['#hud-hp','#hud-mp','#hud-opportunity','#cultivate-action']:
                                assert page.locator(selector).is_visible(),(theme,width,selector)
                        page.set_viewport_size({'width':1480,'height':1080})
                    page.locator('#action-units').fill('2');page.locator('#action-units').dispatch_event('change')
                    assert '2 年' in page.locator('#cultivate-action .action-duration').text_content()
                    age=page.evaluate('game.player.age')
                    with page.expect_request(lambda r:r.url.endswith('/advance') and r.method=='POST') as pending:
                        page.locator('#cultivate-action').click()
                    assert pending.value.post_data_json['years']==2
                    page.wait_for_function('!busy && game.player.age>'+str(age))
                    page.emulate_media(reduced_motion='no-preference')
                    page.locator('[data-panel-target=merchant]').click()
                    assert page.locator('#merchant-card').evaluate("n=>getComputedStyle(n,'::after').display")=='block'
                    assert page.locator('#merchant-card').evaluate("n=>getComputedStyle(n,'::after').animationName")=='book-turn'
                    page.emulate_media(reduced_motion='reduce')
                    assert page.locator('#merchant-card').evaluate("n=>getComputedStyle(n,'::after').animationName")=='none'
                    assert not errors,errors
                    browser.close()
            finally:
                httpd.shutdown();httpd.server_close()
    buttons=''.join(f'<button data-theme="{t["id"]}">{t["id"].upper()} · {t["name"]}</button>' for t in themes)
    html='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>六主题原稿与实装对照 · 1.39.1</title><style>*{box-sizing:border-box}body{margin:0;padding:24px;background:#e8e7df;color:#2d4437;font-family:"Microsoft YaHei",sans-serif}h1{font-size:24px}p{font-size:14px;line-height:1.8}nav{display:flex;gap:10px;flex-wrap:wrap;margin:22px 0}button{font:inherit;border:1px solid #b5c1b0;border-radius:5px;background:#f6f5ed;color:#315c47;padding:10px 18px;cursor:pointer}button[aria-pressed=true]{background:#315c47;color:#fff}main{display:grid;grid-template-columns:1fr 1fr;gap:20px}figure{margin:0}figcaption{padding:10px 0}img{display:block;width:100%;border:1px solid #ccc}a{color:inherit}@media(max-width:800px){main{grid-template-columns:1fr}}</style><h1>六主题 · 原稿与实装对照</h1><p>左侧为获选的第三版 SVG，右侧为 v1.39.1 实际游戏截图（同一真实测试存档，仅截取主界面，侧栏不纳入对照）。姓名、数值、功法可用状态和纪事随存档变化；未将示例来信伪装为真实奖励。窄窗口会按各主题独立重排。</p><nav>BUTTONS</nav><main><figure><figcaption>原 SVG 预览</figcaption><a id="reference-link"><img id="reference" alt="原 SVG"></a></figure><figure><figcaption>实际主界面</figcaption><a id="actual-link"><img id="actual" alt="实装截图"></a></figure></main><script>function select(t){document.querySelector('#reference').src=t+'-reference.svg';document.querySelector('#actual').src=t+'-actual.png';document.querySelector('#reference-link').href=t+'-reference.svg';document.querySelector('#actual-link').href=t+'-actual.png';document.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',b.dataset.theme===t));}document.querySelectorAll('button').forEach(b=>b.onclick=()=>select(b.dataset.theme));select('a');</script></html>'''.replace('BUTTONS',buttons)
    (output/'index.html').write_text(html,encoding='utf-8')
    print('Independent SVG compositions, action tabs, three viewport widths, real journal and two-unit action passed')


if __name__=='__main__':main()
