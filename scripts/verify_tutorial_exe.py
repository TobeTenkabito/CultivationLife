"""Click both tutorial routes against the actual compiled server."""
import json
import runpy
import sys
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life.engine import GameEngine
from scripts.verify_handbook_revision import verify_revision
from fixtures.technique_names_release import prepare_technique_names


def verify_tutorial(base,with_dlc,folder):
    walk=runpy.run_path(str(ROOT/'tests/browser_tutorial_interface.py'))['walk']
    output=ROOT/'build/tutorial-exe';output.mkdir(exist_ok=True)
    for asset in ('tutorial.js','tutorial-interface.js','tutorial-steps.js','tutorial.css','handbook-content.js','index.html'):
        with urllib.request.urlopen(base+'/'+asset,timeout=10) as response:
            assert response.read()==(ROOT/'web'/asset).read_bytes(),asset
    with sync_playwright() as pw:
        browser=pw.chromium.launch()
        try:
            for palette,width,height in [('light',1440,960),('dark',412,915)]:
                page=browser.new_page(viewport=dict(width=width,height=height))
                errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(base);page.wait_for_function('!!configData&&!busy')
                page.locator('#theme-open').click()
                page.locator('#theme-dialog [data-pixel-setting]').check()
                page.locator(f'[data-theme-picker=dialog] [data-pixel-theme-choice={palette}]').click()
                page.locator('[data-close-dialog=theme-dialog]').click();page.evaluate('GameThemes.saved')
                identity=page.evaluate("async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'成品问道',spirit_root:'supreme_wood',path:'dao',seed:331})});await loadGame(g.id);return g.id;}")
                save=folder/'data/saves'/f'{identity}.json'
                before=save.read_bytes();original=json.loads(before)
                page.locator('#action-card [data-tutorial-open]').click()
                page.locator('#tutorial-interface-start').click()
                walk(page,output,f'{with_dlc}-{palette}',pause=width==412)
                assert save.read_bytes()==before,'Compiled interface tour changed a save'
                assert not page.locator('.tutorial-tour').is_visible()
                page.locator('#setting-tutorial-open').click();page.locator('#tutorial-start').click()
                page.wait_for_function('!busy&&game.tutorial.guide.active')
                for _ in range(32):
                    step=page.evaluate('game.tutorial.guide.step')
                    if page.locator('#guide-next').is_visible():page.locator('#guide-next').click()
                    else:
                        selector='[data-guide-choice=guide_accept]' if step=='mentor_choice' else page.evaluate('TutorialSteps[game.tutorial.guide.step].target')
                        page.locator(selector).filter(visible=True).first.click()
                    page.wait_for_function('(old)=>!busy&&(game.tutorial.guide.step!==old||game.tutorial.guide.completed)',arg=step)
                after=json.loads(save.read_bytes())
                assert after['player']['tutorial_state']['guide_completed']
                assert after['player']['age']==original['player']['age'] and after['rng_state']==original['rng_state']
                mentor=after['player']['master']['id']
                assert after['notable_npcs'][mentor]['realm_index']==3 and after['player']['faction_id']
                page.evaluate('(id)=>loadGame(id)',identity)
                assert not page.locator('.tutorial-tour').is_visible()
                naming=page.evaluate("async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'书名成品',spirit_root:'supreme_metal',path:'dao',seed:332})});return g.id;}")
                fixture_engine=GameEngine(ROOT,folder/'data/saves')
                prepare_technique_names(fixture_engine,naming)
                page.evaluate('id=>loadGame(id)',naming)
                verify_revision(page,fixture_engine,naming,output,f'{with_dlc}-{palette}-332')
                assert not errors,errors
                page.close()
                print(f'Compiled tutorial passed: DLC={with_dlc}, {palette}, {width}x{height}; view-only tour plus all 32 practice steps',flush=True)
        finally:browser.close()
