"""Final executable: two palettes and actual four-body cultivation/reports."""
import json,runpy,urllib.request,urllib.error
from pathlib import Path
from playwright.sync_api import sync_playwright
from scripts.browser_navigation import navigation_locator,click_control,reveal_subpage
ROOT=Path(__file__).resolve().parents[1]

def verify_body_ui(base,with_dlc,folder):
    from cultivation_life.engine import GameEngine
    fixture=runpy.run_path(str(ROOT/'tests/fixtures/body_ui_release.py'))
    def request(path,data=None):
        req=urllib.request.Request(base+path,data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=90) as r:return json.load(r)
    assert request('/api/ui-preferences')['pixel_art'] is True
    for old in ('a','b','d','f'):
        try:urllib.request.urlopen(base+f'/themes/{old}.css')
        except urllib.error.HTTPError as e:assert e.code==404
        else:raise AssertionError('Retired theme shipped')
    for data in ({'pixel_art':False},{'theme':'b'}):
        try:request('/api/ui-preferences',data)
        except urllib.error.HTTPError as e:assert e.code==400
        else:raise AssertionError('Retired appearance accepted')
    with sync_playwright() as pw:
        browser=pw.chromium.launch()
        page=browser.new_page(viewport=dict(width=1440,height=1000),reduced_motion='reduce');errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)));page.goto(base);page.wait_for_function('!!configData&&!busy')
        assert page.locator('[data-theme-choice],[data-pixel-setting]').count()==0
        assert page.locator('[data-theme-picker=start] [data-pixel-theme-choice]').count()==2
        for family in (fixture['PRESETS'] if with_dlc else ['dao']):
            data=dict(name='成品炼体验收',path=family,spirit_root='supreme_metal',seed=350,preset_id=fixture['PRESETS'][family])
            if family=='monster':data['monster_species_id']='serpent'
            identity=request('/api/games',data)['id'];engine=GameEngine(ROOT,folder/'data/saves')
            fixture['prepare_body_ui'](engine,identity)
            page.evaluate('id=>loadGame(id)',identity)
            for palette in ('light','dark'):
                click_control(page.locator('#theme-open'));page.locator(f'#theme-dialog [data-pixel-theme-choice={palette}]').click()
                page.evaluate('GameThemes.saved');page.locator('[data-close-dialog=theme-dialog]').click()
                assert page.evaluate('document.documentElement.dataset.visual')=='pixel'
                panel=fixture['PANELS'][family];navigation_locator(page,f'[data-panel-target={panel}]').click()
                assert page.locator(f'#{panel}-card').evaluate('n=>n.scrollWidth<=n.clientWidth+2')
                if palette=='light':
                    before=page.evaluate(fixture['LEVELS'][family]);click_control(page.locator(fixture['BUTTONS'][family]))
                    page.wait_for_function(f'!busy&&{fixture["LEVELS"][family]}==={before+1}')
                click_control(page.locator(f'#{panel}-toggle'))
            navigation_locator(page,'#battle-report-open').click();page.locator('#battle-round-list section').first.wait_for(state='attached')
            reveal_subpage(page,page.locator('#battle-round-list'))
            if not page.locator('.battle-round-details').evaluate('n=>n.open'):
                click_control(page.locator('.battle-round-details>summary'))
            page.wait_for_function('document.querySelector("#battle-round-list").innerText.length>0')
            click_control(page.locator('#battle-report-toggle'))
        assert not errors,errors
        browser.close()
    print(f'Final EXE body/UI verified: DLC={with_dlc}',flush=True)
