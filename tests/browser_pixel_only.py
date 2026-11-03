import json,sys,tempfile,threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine

def main():
    output=ROOT/'build/pixel-only';output.mkdir(exist_ok=True);results=[]
    with tempfile.TemporaryDirectory(prefix='pixel-only-') as d:
        folder=Path(d);e=GameEngine(ROOT,folder/'saves');identity=e.create_game('双主题验收','supreme_metal','dao',350)['id']
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',e),patch.object(server,'PERSISTENCE_ROOT',folder):
            http=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    for width,height in [(1440,1000),(390,844),(754,365)]:
                        for palette in ('light','dark'):
                            page=browser.new_page(viewport=dict(width=width,height=height),reduced_motion='reduce');errors=[]
                            page.on('pageerror',lambda x:errors.append(str(x)))
                            page.add_init_script("localStorage.setItem('cultivation-appearance',JSON.stringify({theme:'b',pixel_art:false,pixel_theme:'dark'}));window.__visualModes=[];new MutationObserver(()=>__visualModes.push(document.documentElement.dataset.visual)).observe(document,{subtree:true,attributes:true,attributeFilter:['data-visual']});")
                            base=f'http://127.0.0.1:{http.server_port}';page.goto(base);page.wait_for_function('!!configData&&!busy');page.evaluate('GameThemes.ready')
                            assert page.locator('[data-pixel-setting],[data-theme-choice]').count()==0
                            assert page.locator('[data-theme-picker=start] [data-pixel-theme-choice]').count()==2
                            page.locator(f'[data-theme-picker=start] [data-pixel-theme-choice={palette}]').click();page.evaluate('GameThemes.saved')
                            page.evaluate('id=>loadGame(id)',identity);before=e.store._path(identity).read_bytes()
                            assert page.evaluate('document.documentElement.dataset.visual')=='pixel'
                            assert page.evaluate('document.documentElement.dataset.pixelTheme')==palette
                            assert page.evaluate('__visualModes.every(mode=>mode!=="text")')
                            for payload in ({'theme':'b'},{'theme':'d'},{'theme':'f'},{'pixel_art':False}):
                                assert page.request.post(base+'/api/ui-preferences',data=payload).status==400
                            page.locator('#theme-open').click()
                            assert page.locator('#theme-dialog [data-pixel-theme-choice]').count()==2
                            page.locator('#theme-dialog [data-dock-label-setting]').set_checked(False)
                            page.evaluate('GameThemes.saved');page.locator('[data-close-dialog=theme-dialog]').click()
                            page.screenshot(path=str(output/f'{palette}-{width}.png'))
                            page.reload();page.wait_for_function('!!configData&&!busy');page.evaluate('GameThemes.ready')
                            assert page.evaluate('GameThemes.preferences.pixel_theme')==palette
                            assert page.evaluate('GameThemes.preferences.compact_docks') is False
                            assert e.store._path(identity).read_bytes()==before and not errors,errors
                            results.append(dict(palette=palette,width=width,old_cache_cannot_restore=True,readonly=True,reload=True));page.close()
                    browser.close()
            finally:http.shutdown();http.server_close()
    (output/'report.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8')
    print('Pixel-only UI passed: six layouts/palettes, stale cache, immutable rendering mode, atomic rejection and save isolation')
if __name__=='__main__':main()
