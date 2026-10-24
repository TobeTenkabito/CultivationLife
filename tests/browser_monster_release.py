"""Real HTTP/UI projection of every prepared form and actual evolution command."""
import json
import sys
import tempfile
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from fixtures.monster_visuals import monster_visual_cases,prepare_monster_visual,prepare_monster_evolution
from scripts.browser_navigation import navigation_locator, reveal_subpage


def verify(page,engine,identity,out,all_forms=True):
    cases=monster_visual_cases()
    assert len(cases)==143,len(cases)
    if not all_forms:
        selected={}
        for case in cases:
            stage='high' if case['realm']>=7 else 'low'
            if stage=='low' and case['realm']>1:continue
            selected.setdefault((case['species'],stage),case)
        cases=list(selected.values());assert len(cases)==16
    page.evaluate('GameThemes.ready')
    page.locator('#theme-open').click()
    page.locator('#theme-dialog [data-pixel-setting]').set_checked(True)
    page.evaluate('GameThemes.saved');page.locator('[data-close-dialog=theme-dialog]').click()
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    for i,case in enumerate(cases):
        prepare_monster_visual(engine,identity,case)
        page.evaluate('id=>loadGame(id)',identity)
        page.wait_for_function('id=>game?.player.visual_actor===id',arg=case['static'])
        page.wait_for_function('''file=>{const im=document.querySelector('.pixel-portrait');return !im.hidden&&im.complete&&im.naturalWidth===128&&im.src.endsWith(file)}''',arg=case['static'].removeprefix('actor.monster.')+'-portrait.png')
        if page.locator('#battle-report-card').is_visible():page.locator('#battle-report-toggle').click()
        page.locator('.hud-identity').click()
        page.wait_for_function('id=>document.querySelector(".pixel-details-art canvas")?.dataset.actor===id',arg=case['static'])
        page.locator('[data-close-dialog=player-details-dialog]').click()
        navigation_locator(page,'#battle-report-open').click()
        page.wait_for_function('CombatReplay.diagnostics().active&&!document.querySelector("[data-combat-replay]").disabled')
        saved=engine.store._path(identity).read_bytes();before=page.evaluate('JSON.stringify(game)')
        for at in [0,1.5,2.1,3,10000]:
            page.evaluate('t=>CombatReplay.seek(t)',at)
            diag=page.evaluate('CombatReplay.diagnostics()')
            assert diag['actors']['hero']['id']==case['combat']
            assert diag['decodedBytes']<64*1024*1024
            for box in diag['bounds'].values():
                assert box[0]>=0 and box[1]>=0 and box[2]<=diag['viewport'][0] and box[3]<=diag['viewport'][1]
        assert page.evaluate('JSON.stringify(game)')==before
        assert engine.store._path(identity).read_bytes()==saved
        if i in [0,len(cases)-1]:page.screenshot(path=str(out/f'monster-{i}.png'))
        page.locator('#battle-report-toggle').click()
        assert page.evaluate('CombatReplay.diagnostics().cache===0')
    # Prepare a legal bottleneck, then click the ordinary evolution button.
    prepare_monster_evolution(engine,identity);page.evaluate('id=>loadGame(id)',identity)
    assert page.evaluate('game.player.visual_actor')=='actor.monster.flora-spirit-shared'
    navigation_locator(page,'[data-panel-target=bloodline]').click()
    reveal_subpage(page,page.locator('.bloodline-candidate').filter(has_text='万灵古树').locator('button')).click()
    page.wait_for_function("!busy&&game.player.visual_actor==='actor.monster.flora-tree-lord-shared'")
    assert engine.store.load(identity).player.monster_evolution_id=='FLORA_TREE_LORD'
    assert not errors,errors
    return dict(forms=len(cases),real_evolution=True,read_only_replay=True)


def main():
    from playwright.sync_api import sync_playwright
    from cultivation_life import server
    from cultivation_life.engine import GameEngine
    out=ROOT/'build/monster-release';out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        engine=GameEngine(ROOT,Path(folder)/'saves')
        made=engine.create_game('八族外观验收','supreme_water','monster',seed=4190,monster_species_id='flora',start_world='monster_realm')
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch();page=browser.new_page(viewport=dict(width=1440,height=960),reduced_motion='reduce')
                    page.goto(f'http://127.0.0.1:{http.server_port}');page.wait_for_function('typeof configData!=="undefined" && !!configData')
                    result=verify(page,engine,made['id'],out)
                    browser.close()
            finally:http.shutdown();http.server_close()
    (out/'validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(result)


if __name__=='__main__':main()
