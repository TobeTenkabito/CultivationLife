"""Exercise the same new school controls on the final executable."""
import json,runpy,urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright
from scripts.browser_navigation import navigation_locator,click_control,reveal_subpage
ROOT=Path(__file__).resolve().parents[1]

def verify_mentorship(base,with_dlc,folder):
    from cultivation_life.engine import GameEngine
    prepare=runpy.run_path(str(ROOT/'tests/fixtures/mentorship_release.py'))['prepare_mentorship']
    req=urllib.request.Request(base+'/api/games',data=json.dumps(dict(name='成品师门验收',path='dao',spirit_root='supreme_metal',seed=353,
        custom_start=dict(world='human',realm_index=3,layer=5,sect='new'))).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=90) as response:identity=json.load(response)['id']
    prepare(GameEngine(ROOT,folder/'data/saves'),identity)
    with sync_playwright() as pw:
        browser=pw.chromium.launch();page=browser.new_page(viewport=dict(width=1440,height=960));errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)));page.goto(base);page.wait_for_function('!!configData&&!busy')
        page.evaluate('id=>loadGame(id)',identity);page.wait_for_function('!busy&&!!game')
        navigation_locator(page,'[data-panel-target=relationship]').click()
        row=page.locator('[data-mentorship-npc="school:release-mentor:0"]')
        select=row.get_by_role('combobox',name='云岫同门交流',include_hidden=True)
        details=select.locator('xpath=ancestor::details[1]');reveal_subpage(page,details)
        if not details.evaluate('n=>n.open'):click_control(details.locator('summary'))
        for action in ('peer_consult','peer_item','peer_technique','peer_spar'):
            select.select_option(action)
            with page.expect_response(lambda r:r.url.endswith('/mentorship-action')) as response:
                click_control(row.get_by_role('button',name='办理同门事务',include_hidden=True))
            assert response.value.ok,response.value.text();page.wait_for_function('!busy')
            assert select.input_value()==action and details.evaluate('n=>n.open')
            assert row.get_by_role('button',name='办理同门事务',include_hidden=True).is_disabled()
        assert page.evaluate('game.player.opportunity>0')
        page.screenshot(path=str(folder/'mentorship.png'),full_page=True)
        navigation_locator(page,'#battle-report-open').click()
        page.wait_for_function('CombatReplay.diagnostics().active&&!document.querySelector("[data-combat-replay]").disabled')
        assert len(page.evaluate('CombatReplay.diagnostics().participants'))==2
        assert not errors,errors
        browser.close()
    print(f'Mentorship final EXE: DLC={with_dlc}; four actual commands, preserved selections and real replay passed',flush=True)
