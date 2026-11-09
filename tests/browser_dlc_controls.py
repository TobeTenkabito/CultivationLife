"""Real two-palette DLC/base navigation, disabled controls and preserved actions."""
import runpy, sys, tempfile, threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from scripts.westward_navigation import open_westward
from scripts.browser_navigation import navigation_locator,click_control,set_theme

def main():
    out=ROOT/'build/dlc-controls-browser';out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='dlc-controls-') as folder:
        e=GameEngine(ROOT,Path(folder)/'saves')
        g=e.create_game('扩展按钮验收','supreme_metal','dao',360,preset_id='true_immortal')
        runpy.run_path(str(ROOT/'tests/fixtures/westward_release.py'))['prepare_westward'](e,g['id'])
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',e),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    for theme,width,height in [('light',1440,1000),('dark',1440,1000),('light',390,844),('dark',390,844),('dark',754,365)]:
                        page=browser.new_page(viewport=dict(width=width,height=height),reduced_motion='reduce')
                        errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                        page.goto(f'http://127.0.0.1:{http.server_port}');page.wait_for_function('!!configData&&!busy')
                        set_theme(page,theme);page.evaluate('id=>loadGame(id)',g['id'])
                        # Render the real shared stylesheet for every owner, including families
                        # whose gameplay is unavailable to this Dao character. Do not bypass gates.
                        swatches=page.evaluate("""() => {
                          const families=['asura','buddhist','ghost','guixu','intrigue','bloodline','civilizations','sage','tianji','authored','trial-sites','yaochi-westward'];
                          const box=document.createElement('section');box.id='dlc-palette-verification';
                          box.style.cssText='position:fixed;inset:20px;z-index:99999;padding:24px;background:var(--paper);display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;align-content:start;overflow:auto';
                          document.body.append(box);
                          for(const id of families){const b=document.createElement('button');b.dataset.dlc=id;b.textContent=id;box.append(b);}
                          return [...box.children].map(n=>({id:n.dataset.dlc,color:getComputedStyle(n).color,bg:getComputedStyle(n).backgroundColor}));
                        }""")
                        assert len({row['color'] for row in swatches})==12,swatches
                        assert len({row['bg'] for row in swatches})==12,swatches
                        page.screenshot(path=str(out/f'{theme}-{width}-palette.png'),animations='disabled')
                        page.evaluate("document.querySelector('#dlc-palette-verification').remove()")
                        open_westward(page,'委托');open_westward(page,'专修')
                        page.locator('#yaochi-practice').wait_for()
                        if width==754:
                            page.add_style_tag(path=str(ROOT/'android/app/src/main/mobile/mobile.css'))
                            page.locator('#immortal-practice-card').evaluate('n=>n.scrollTop=n.scrollHeight')
                            open_westward(page,'仙籍与功德');open_westward(page,'专修')
                        assert page.locator('[data-panel-target=buildings],[data-panel-target=immortal-register],[data-panel-target=immortal-fair]').count()==0
                        assert page.locator('#yaochi-content [data-subpage="地仙庙域"],#yaochi-content [data-subpage="专修"],#yaochi-content [data-subpage="仙圃"]').count()==0
                        if width>900:
                            assert page.locator('.left-dock [data-panel-target=immortal-practice]').count()==1
                            assert page.locator('#strategy-dock [data-panel-target=immortal-estate]').count()==1
                        else:
                            assert page.locator('[data-panel-target=immortal-practice]').get_attribute('data-navigation-group')=='practice'
                            assert page.locator('[data-panel-target=immortal-estate]').get_attribute('data-navigation-group')=='worlds'

                        page.wait_for_function("!!document.querySelector('[data-service=trace] button[data-dlc]')")
                        disabled=page.locator('[data-service=body] [data-westward-action=westward_start_merit]')
                        assert disabled.is_disabled()
                        for owner,names in [('immortal-practice',['专修','仙籍与功德']),('immortal-estate',['访古','紫气东来']),('yaochi',['仙会'])]:
                            for name in names:
                                open_westward(page,name)
                                assert page.locator(f'#{owner}-content [data-subpage="{name}"]').get_attribute('data-dlc')=='yaochi-westward'
                        open_westward(page,'专修')
                        base=page.locator('#yaochi-content [data-subpage="委托"]');assert base.get_attribute('data-dlc') is None
                        dlc=page.locator('#immortal-practice-content [data-subpage="专修"]')
                        assert 'DLC' in dlc.evaluate("n=>getComputedStyle(n,'::after').content")
                        assert dlc.evaluate('n=>getComputedStyle(n).backgroundColor')!=base.evaluate('n=>getComputedStyle(n).backgroundColor')
                        if not page.evaluate('game.yaochi.westward.adopted'):
                            click_control(page.locator('[data-westward-action=westward_adopt]'))
                            page.wait_for_function('!busy&&game.yaochi.westward.adopted')
                        click_control(page.locator('[data-service=trace] [data-westward-action=westward_start_merit]'))
                        page.wait_for_function('!busy&&!!game.yaochi.westward.project')
                        click_control(page.locator('.yaochi-exit summary'));click_control(page.locator('[data-westward-action=westward_cancel]'))
                        page.wait_for_function('!busy&&!game.yaochi.westward.project&&game.yaochi.merit===2000')
                        assert disabled.is_disabled()
                        assert page.locator('#immortal-practice-card').evaluate('n=>n.scrollWidth<=n.clientWidth+2')
                        page.screenshot(path=str(out/f'{theme}-{width}-yaochi.png'),animations='disabled')
                        page.locator('#immortal-practice-toggle').click()
                        navigation_locator(page,'[data-panel-target=heavenly-court]').click()
                        assert page.locator('[data-subpage="天庭政务"]').get_attribute('data-dlc') is None
                        for name in ['诸司任职','项目议政']:
                            b=page.locator(f'[data-subpage="{name}"]');assert b.get_attribute('data-dlc')=='yaochi-westward';click_control(b)
                        page.screenshot(path=str(out/f'{theme}-{width}-court.png'),animations='disabled')
                        page.locator('#heavenly-court-toggle').click()
                        nav=navigation_locator(page,'[data-panel-target=authored]');assert nav.get_attribute('data-dlc')=='authored';nav.click()
                        page.wait_for_function("!!document.querySelector('#authored-content button[data-dlc=authored]')")
                        assert page.locator('#authored-content button[data-dlc=authored]').first.evaluate("n=>getComputedStyle(n).getPropertyValue('--dlc-ink').trim()") != page.locator('#immortal-practice-content button[data-dlc=yaochi-westward]').first.evaluate("n=>getComputedStyle(n).getPropertyValue('--dlc-ink').trim()")
                        page.locator('#authored-toggle').click()
                        # Recent shortcut is rebuilt through the original navigation, including DLC ownership.
                        if page.locator('[data-navigation-category=common]').is_visible():
                            page.locator('[data-navigation-category=common]').click()
                            assert page.locator('[data-navigation-shortcut=authored]').get_attribute('data-dlc')=='authored'
                        assert not errors,errors
                        page.close();print(f'{theme} {width}x{height}: base/DLC styles, real escrow/refund, disabled material and shortcut passed',flush=True)
                    browser.close()
            finally:http.shutdown();http.server_close()

if __name__=='__main__':main()
