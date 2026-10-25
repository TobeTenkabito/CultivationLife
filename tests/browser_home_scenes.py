"""Real page map travel, legacy panel layout, choice submission and finite CG."""
import json,sys,tempfile,threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from fixtures.home_scenes import thunder,mirrors
from scripts.browser_navigation import navigation_locator

def verify(page,engine,identity,out,with_dlc=True):
    page.set_viewport_size(dict(width=1440,height=960))
    page.evaluate('GameThemes.ready');page.locator('#theme-open').click()
    page.locator('#theme-dialog [data-pixel-setting]').set_checked(True);page.evaluate('GameThemes.saved');page.locator('[data-close-dialog=theme-dialog]').click()
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.evaluate('id=>loadGame(id)',identity)
    page.wait_for_selector('.pixel-world-view')
    saved=engine.store._path(identity).read_bytes()
    for mode in ['influence','events','caravans','buildings','terrain']:
        page.locator(f'[data-home-map-mode={mode}]').click()
        assert page.locator('.pixel-world-view').get_attribute('data-mode')==mode
    assert engine.store._path(identity).read_bytes()==saved
    destination=page.evaluate('game.map.locations.find(p=>!p.current&&p.travel_status==="ok").id')
    page.locator('select[aria-label="浏览绘景地域"]').select_option(destination)
    page.locator('.home-map-travel').click();page.wait_for_function('!busy')
    assert engine.store.load(identity).player.location_id==destination
    for width,height in [(1440,960),(1024,768),(390,844),(320,740)]:
        page.set_viewport_size(dict(width=width,height=height));page.wait_for_timeout(180)
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),width
        if width>=1024:
            assert page.locator('.pixel-landscape').bounding_box()['height']<=721
            if page.locator('#ghost-system-panel').is_visible():
                assert page.locator('.ghost-system-copy').bounding_box()['width']>=180
                page.locator('.ghost-ledger').evaluate('n=>n.open=true')
                assert page.locator('.ghost-system-copy').bounding_box()['width']>=180
        else:
            page.locator('#pixel-scenery-toggle').click();page.locator('[data-home-map-mode=buildings]').click()
            assert page.evaluate('document.querySelector("#pixel-scenery-drawer").scrollWidth<=document.querySelector("#pixel-scenery-drawer").clientWidth+1')
            page.get_by_role('button',name='收起绘景',exact=True).click()
        page.screenshot(path=str(out/f'home-{width}.png'))
    thunder(engine,identity);page.evaluate('id=>loadGame(id)',identity)
    page.wait_for_selector('#event-cinematic canvas',state='visible');assert page.locator('#event-card').is_visible()
    assert page.locator('#action-card').is_hidden()
    before=engine.store._path(identity).read_bytes();page.locator('#event-cinematic button').filter(has_text='重播').click();page.wait_for_timeout(4300)
    assert engine.store._path(identity).read_bytes()==before
    assert not page.evaluate('EventScenes.inspect().playing')
    page.locator('#event-choices button').first.click();page.wait_for_function('!busy')
    assert page.evaluate('game.trial.step===2'),page.evaluate('({trial:game.trial,alive:game.player.alive,event:game.pending_event,toast:document.querySelector("#toast")?.textContent,errors:window.__errors})')
    page.wait_for_function('document.querySelector(".event-cinematic-caption").textContent.includes("已结算")')
    for width,height in [(1440,960),(390,844),(320,740)]:
        page.set_viewport_size(dict(width=width,height=height));page.wait_for_timeout(180)
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        r=page.locator('#event-cinematic canvas').bounding_box();assert r['width']<=width and r['height']<=440
        page.screenshot(path=str(out/f'thunder-{width}.png'))
    page.locator('#event-cinematic button').filter(has_text='收起动画').click();assert not page.evaluate('EventScenes.inspect().frame')
    for _ in range(2):page.locator('#event-choices button').first.click();page.wait_for_function('!busy')
    assert engine.store.load(identity).active_trial is None
    assert page.locator('#action-card').is_visible()
    mirrors(engine,identity);page.evaluate('id=>loadGame(id)',identity)
    navigation_locator(page,'#battle-report-open').click()
    page.wait_for_function('CombatReplay.diagnostics().active&&!document.querySelector("[data-combat-replay]").disabled')
    page.evaluate('CombatReplay.seek(2)');diag=page.evaluate('CombatReplay.diagnostics()')
    assert {p['visualVariant'] for p in diag['teams']['npc']}=={'corpse_self','corpse_primal','corpse_superego'}
    assert all(p['id']==diag['actors']['hero']['id'] for p in diag['teams']['npc'])
    # Walk every participant's attack, guard and defeat, including enemy turns.
    page.evaluate('for(let t=0;t<=CombatReplay.diagnostics().duration;t+=.5)CombatReplay.seek(t)')
    page.evaluate('CombatReplay.seek(2)')
    page.screenshot(path=str(out/'mirrors.png'));page.locator('#battle-report-toggle').click()
    assert not errors,errors
    return dict(layout=True,map_modes=5,travel=True,event_choices=3,mirror_variants=3,read_only_playback=True)

def main():
    from playwright.sync_api import sync_playwright
    from cultivation_life import server
    from cultivation_life.engine import GameEngine
    out=ROOT/'build/home-scenes';out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        engine=GameEngine(ROOT,Path(folder)/'saves');made=engine.create_game('主页验收','mutated_yin','ghost',606)
        game=engine.store.load(made['id']);game.settings.update(silent_events=True,combat_popup=False);engine.store.save(game)
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            http=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch();page=browser.new_page(viewport=dict(width=1440,height=960),reduced_motion='reduce')
                    page.goto(f'http://127.0.0.1:{http.server_port}');page.wait_for_function('typeof configData!=="undefined"&&!!configData')
                    result=verify(page,engine,made['id'],out);browser.close()
            finally:http.shutdown();http.server_close()
    (out/'validation.json').write_text(json.dumps(result,indent=2));print(result)

if __name__=='__main__':main()

