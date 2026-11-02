"""Real HTTP unlock, thumbnails/details, battle snapshot, motion and disposal."""
import sys,tempfile,threading,json,io
from PIL import Image,ImageChops
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.rules import add_item
from browser_divine_lights import prepare_battle
from scripts.browser_navigation import navigation_locator,click_control


def main():
    output=ROOT/'build/divine-light-natural';output.mkdir(exist_ok=True)
    results=[]
    with tempfile.TemporaryDirectory(prefix='light-animation-') as folder:
        engine=GameEngine(ROOT,Path(folder)/'saves')
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            http=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    for theme,width,height in [('light',1440,1000),('dark',390,844),('light',754,365)]:
                        made=engine.create_game('五光环身','supreme_metal','dao',356,preset_id='true_immortal')
                        g=engine._load(made['id']);g.pending_event=None;g.player.next_tribulation_age=None
                        g.player.immortal_body.update(level=9,manuals=['jade_marrows'],active_manual='jade_marrows',failures=100)
                        for key in ('immortal_jade_herb','nine_leaf_immortal_lingzhi'):add_item(g.player,key,10000)
                        engine.store.save(g)
                        page=browser.new_page(viewport=dict(width=width,height=height),reduced_motion='no-preference')
                        errors=[];requests=[];page.on('pageerror',lambda e:errors.append(str(e)))
                        page.on('request',lambda r:requests.append((r.method,r.url)))
                        page.goto(f'http://127.0.0.1:{http.server_port}');page.wait_for_function('!!configData&&!busy')
                        page.locator('#theme-open').click();page.locator('#theme-dialog [data-pixel-setting]').set_checked(True)
                        page.locator(f'#theme-dialog [data-pixel-theme-choice={theme}]').click();page.locator('[data-close-dialog=theme-dialog]').click()
                        page.evaluate('GameThemes.saved');page.evaluate('id=>loadGame(id)',g.id)
                        assert page.locator('.pixel-portrait-frame [data-light]').count()==0
                        navigation_locator(page,'[data-panel-target=immortal-body]').click()
                        click_control(page.get_by_role('button',name='以仙药淬炼下一层',exact=True))
                        page.wait_for_function('!busy&&game.player.visual_lights.length===1')
                        click_control(page.locator('#immortal-body-toggle'))
                        assert page.locator('.pixel-portrait-frame [data-light=kun]').count()==1
                        page.locator('.hud-identity').click();page.locator('.pixel-details-art:not([hidden])').wait_for()
                        assert page.locator('.pixel-details-art [data-light]').count()==1
                        click_control(page.locator('[data-close-dialog=player-details-dialog]'))
                        for level,count in [(20,2),(30,3),(40,4),(50,5)]:
                            saved=engine._load(g.id);saved.player.immortal_body['level']=level;engine.store.save(saved)
                            page.evaluate('id=>loadGame(id)',g.id)
                            page.wait_for_function('count=>document.querySelectorAll(".pixel-portrait-frame [data-light]").length===count',arg=count)
                            assert page.locator('.pixel-portrait-frame [data-light]').count()==count
                        page.locator('.hud-identity').click();page.locator('.pixel-details-art:not([hidden])').wait_for()
                        assert page.locator('.pixel-details-art [data-light]').count()==5
                        assert page.locator('#player-details-dialog').evaluate('n=>n.scrollWidth<=n.clientWidth+1')
                        path=engine.store._path(g.id);before=path.read_bytes();requests.clear()
                        orbit=page.locator('.pixel-details-art [data-light=li] path').last
                        first=orbit.evaluate('n=>getComputedStyle(n).strokeDashoffset');page.wait_for_timeout(180)
                        assert first!=orbit.evaluate('n=>getComputedStyle(n).strokeDashoffset')
                        # Compare actual composited pixels: wisps are visible, the face stays clear.
                        figure=page.locator('.pixel-details-art')
                        figure.evaluate('n=>n.getAnimations({subtree:true}).forEach(a=>{a.pause();a.currentTime=1700;})')
                        lit=Image.open(io.BytesIO(figure.screenshot())).convert('RGB')
                        figure.evaluate('n=>n.querySelectorAll(".divine-light-orbits").forEach(s=>s.style.visibility="hidden")')
                        plain=Image.open(io.BytesIO(figure.screenshot())).convert('RGB')
                        figure.evaluate('n=>n.querySelectorAll(".divine-light-orbits").forEach(s=>s.style.visibility="")')
                        assert ImageChops.difference(lit,plain).getbbox(), 'Unlocked wisps must actually be visible'
                        w,h=lit.size;face=(int(w*.47),int(h*.13),int(w*.54),int(h*.20))
                        assert ImageChops.difference(lit.crop(face),plain.crop(face)).getbbox() is None, 'Light must not cover the face'
                        page.screenshot(path=str(output/f'{theme}-{width}-details.png'))
                        page.emulate_media(reduced_motion='reduce')
                        assert orbit.evaluate('n=>getComputedStyle(n).animationName')=='none'
                        assert path.read_bytes()==before
                        assert not any(method!='GET' and '/api/games/' in url for method,url in requests)
                        click_control(page.locator('[data-close-dialog=player-details-dialog]'))
                        saved=engine._load(g.id);saved.player.immortal_body['level']=0;engine.store.save(saved)
                        page.evaluate('id=>loadGame(id)',g.id)
                        page.wait_for_function('document.querySelectorAll(".pixel-portrait-frame>.divine-light-orbits").length===0')
                        assert page.locator('.pixel-portrait-frame>.divine-light-orbits').count()==0
                        assert page.locator('.pixel-details-art>.divine-light-orbits').count()==0
                        saved=engine._load(g.id);saved.player.immortal_body['level']=50;engine.store.save(saved)
                        prepare_battle(engine,engine._load(g.id));page.evaluate('id=>loadGame(id)',g.id)
                        navigation_locator(page,'#battle-report-open').click()
                        page.wait_for_function('CombatReplay.diagnostics().active&&!document.querySelector("[data-combat-replay]").disabled')
                        info=page.evaluate('CombatReplay.diagnostics()')
                        assert info['teams']['hero'][0]['visualLights']==['kun','zhen','kan','li','qian'],info
                        before=path.read_bytes();requests.clear()
                        page.evaluate('CombatReplay.seek(.45)')
                        page.locator('#battle-animation').screenshot(path=str(output/f'{theme}-{width}-battle.png'))
                        page.evaluate('CombatReplay.seek(2.4)')
                        page.locator('#battle-animation').screenshot(path=str(output/f'{theme}-{width}-battle-motion.png'))
                        # The same bounded painter really moves; no particle list or game RNG.
                        hashes=page.evaluate('''()=>{
                          const c=document.createElement('canvas');c.width=180;c.height=220;const x=c.getContext('2d');
                          return [0,1].map(t=>{x.clearRect(0,0,180,220);for(const front of [false,true])
                            DivineLightVisuals.draw(x,['kun','zhen','kan','li','qian'],{x:90,y:110,w:160,h:210},t,front);
                            let h=2166136261;for(const n of x.getImageData(0,0,180,220).data)h=Math.imul(h^n,16777619);return h>>>0;});
                        }''')
                        assert hashes[0]!=hashes[1]
                        page.evaluate('CombatReplay.seek(1.7)');page.evaluate('CombatReplay.seek(.45)')
                        assert path.read_bytes()==before
                        assert not any(method!='GET' and '/api/games/' in url for method,url in requests)
                        click_control(page.locator('#battle-report-toggle'))
                        assert page.evaluate('!CombatReplay.diagnostics().active&&!CombatReplay.diagnostics().raf')
                        assert page.locator('#battle-animation canvas').evaluate('c=>c.width===0&&c.height===0')
                        assert not errors,errors
                        results.append(dict(theme=theme,width=width,unlock_counts=[0,1,2,3,4,5],motion=True,reduced=True,readonly=True,disposed=True,face_clear=True,actual_wisps_visible=True,old_layers_removed=True))
                        page.close()
                    browser.close()
            finally:http.shutdown();http.server_close()
    (output/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Divine light animation: real unlock, all five colors, portrait/details, battle snapshot, motion/reduced motion, readonly and disposal passed in 3 layouts')


if __name__=='__main__':main()
