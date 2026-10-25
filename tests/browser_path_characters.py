"""Real HTTP, details/card clicks and real settled battle playback for three DLCs."""
import json,math,sys,tempfile,threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from fixtures.path_characters import path_character_cases,prepare_path_character
from scripts.browser_navigation import navigation_locator,reveal_subpage

def verify(page,engine,identity,out):
    assert page.evaluate('VisualAssets.actor(null)===null && VisualAssets.actor(undefined)===null')
    page.evaluate('GameThemes.ready');page.locator('#theme-open').click()
    page.locator('#theme-dialog [data-pixel-setting]').set_checked(True)
    page.evaluate('GameThemes.saved');page.locator('[data-close-dialog=theme-dialog]').click()
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    for case in path_character_cases():
        prepare_path_character(engine,identity,case);page.evaluate('id=>loadGame(id)',identity)
        page.wait_for_function('id=>game.player.visual_actor===id',arg=case['static'])
        page.wait_for_function('id=>{const im=document.querySelector(".pixel-portrait");return im?.complete&&im.naturalWidth===128&&im.src.includes(id+"-portrait.png")}',arg=case['combat'])
        if page.locator('#battle-report-card').is_visible():page.locator('#battle-report-toggle').click()
        page.locator('.hud-identity').click()
        page.wait_for_function('id=>document.querySelector(".pixel-details-art canvas")?.dataset.actor===id',arg=case['static'])
        page.locator('[data-close-dialog=player-details-dialog]').click()
        navigation_locator(page,'#battle-report-open').click()
        page.wait_for_function('CombatReplay.diagnostics().active&&!document.querySelector("[data-combat-replay]").disabled')
        saved=engine.store._path(identity).read_bytes();before=page.evaluate('JSON.stringify(game)')
        for t in [0,1.5,2.1,3,10000]:
            page.evaluate('t=>CombatReplay.seek(t)',t);d=page.evaluate('CombatReplay.diagnostics()')
            assert d['actors']['hero']['id']==case['combat'] and d['actors']['npc']['id']==case['npc']
            assert d['decodedBytes']<64*1024*1024
            assert all(isinstance(v,(int,float)) and math.isfinite(v) for p in d['participants'] for v in p['bounds']),d['participants']
        page.screenshot(path=str(out/(case['combat']+'.png')));page.locator('#battle-report-toggle').click()
        navigation_locator(page,'[data-panel-target=relationship]').click()
        search=page.locator('#npc-contacts input[type=search]');reveal_subpage(page,search);search.fill('三道同道')
        page.locator('.contact-person').click();page.locator('.npc-art-contact-figure').click()
        page.wait_for_function('id=>{const im=document.querySelector("#npc-art-dialog .npc-art-figure");return im?.complete&&im.naturalWidth===256&&im.src.includes(id)}',arg=case['npc'])
        page.locator('#npc-art-dialog button').click();page.locator('#relationship-toggle').click()
        assert page.evaluate('JSON.stringify(game)')==before and engine.store._path(identity).read_bytes()==saved
    # Core hero must also discover the enemy's optional action manifest.
    case=path_character_cases()[-2];prepare_path_character(engine,identity,case,True);page.evaluate('id=>loadGame(id)',identity)
    if not page.locator('#battle-report-card').is_visible():navigation_locator(page,'#battle-report-open').click()
    page.wait_for_function('CombatReplay.diagnostics().active&&!document.querySelector("[data-combat-replay]").disabled')
    assert page.evaluate('CombatReplay.diagnostics().actors.npc.id')==case['npc']
    page.locator('#battle-report-toggle').click();assert not errors,errors
    return dict(forms=6,npcs=6,core_hero_dlc_enemy=True,read_only=True)

def main():
    from playwright.sync_api import sync_playwright
    from cultivation_life import server
    from cultivation_life.engine import GameEngine
    out=ROOT/'build/path-characters';out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        engine=GameEngine(ROOT,Path(folder)/'saves');made=engine.create_game('三道外观验收','heavenly','dao',seed=510,preset_id='core')
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            http=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch();page=browser.new_page(viewport=dict(width=1440,height=960),reduced_motion='reduce')
                    page.goto(f'http://127.0.0.1:{http.server_port}');page.wait_for_function('typeof configData!=="undefined" && !!configData')
                    result=verify(page,engine,made['id'],out)
                    page.set_viewport_size(dict(width=390,height=844));verify(page,engine,made['id'],out)
                    browser.close()
            finally:http.shutdown();http.server_close()
    (out/'validation.json').write_text(json.dumps(result,indent=2),encoding='utf8');print(result)

if __name__=='__main__':main()
