"""Exercise final compiled HTTP, real page input, payments, combat and handbook."""
import copy
import json
from pathlib import Path
import runpy
import urllib.request

from playwright.sync_api import sync_playwright
from scripts.browser_navigation import navigation_locator, click_control, reveal_subpage, set_theme

ROOT=Path(__file__).resolve().parents[1]


def verify_techniques(base,with_dlc,folder):
    from cultivation_life.engine import GameEngine
    prepare=runpy.run_path(str(ROOT/'tests/fixtures/technique_release.py'))['prepare_technique_release']
    def request(path,data=None):
        req=urllib.request.Request(base+path,data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=90) as response:return json.load(response)
    engine=GameEngine(ROOT,folder/'data/saves')
    def create(mode):
        identity=request('/api/games',dict(name='成品功法验收',path='dao',spirit_root='heavenly',seed=713,preset_id='core'))['id']
        prepare(engine,identity,mode);return identity
    with sync_playwright() as pw:
        browser=pw.chromium.launch()
        page=browser.new_page(viewport=dict(width=1440,height=1000),reduced_motion='reduce')
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(base);page.wait_for_function('!!configData&&!busy')
        for palette in ('light','dark'):
            identity=create('secret');page.evaluate('async id=>loadGame(id)',identity);set_theme(page,palette)
            navigation_locator(page,'[data-panel-target=secret-art]').click()
            click_control(page.locator('#secret-tab-known'));page.locator('#secret-art-filter').select_option('linked')
            click_control(page.locator('[data-secret-art=manual_five_color_ice]'))
            assert page.locator('#secret-root-detail li').count()==5
            with page.expect_response(lambda r:r.url.endswith('/secret-art')) as response:
                click_control(page.get_by_role('button',name='激活秘术',exact=True))
            assert response.value.status==200
            page.wait_for_function("!busy&&game.secret_arts.library.find(a=>a.id==='manual_five_color_ice').activated")
            saved=engine.store.load(identity);assert not saved.player.formation_materials
            before=copy.deepcopy(saved.player.to_dict())
            assert page.request.post(response.value.url,data=response.value.request.post_data_json).status==400
            assert engine.store.load(identity).player.to_dict()==before
            click_control(page.locator('#secret-art-toggle'))
            identity=create('battle');page.evaluate('async id=>loadGame(id)',identity)
            click_control(page.locator('.hud-identity'))
            summary=page.locator('details.techniques>summary');reveal_subpage(page,summary)
            if not summary.evaluate('n=>n.parentElement.open'):click_control(summary)
            select=page.locator('#duel-technique-select');reveal_subpage(page,select)
            values=select.locator('option').evaluate_all("nodes=>nodes.map(n=>n.value).filter(Boolean)")
            assert values;select.select_option(values[0]);click_control(page.locator('#duel-technique-add'))
            page.wait_for_function('!busy&&game.player.duel_techniques.selected.length===7')
            assert page.locator('#duel-technique-add').is_disabled()
            click_control(page.locator('[data-close-dialog=player-details-dialog]'))
            # The combat is settled inside the EXE through the ordinary public action.
            result=request(f'/api/games/{identity}/advance',dict(action='hunt_beast',years=1))
            assert result['last_combat_report']
            page.evaluate('async id=>loadGame(id)',identity)
            navigation_locator(page,'#battle-report-open').click()
            page.wait_for_function('CombatReplay.diagnostics().active&&!document.querySelector("[data-combat-replay]").disabled')
            assert page.locator('.combat-technique[data-book]').count()==7
            stored=engine.store._path(identity).read_bytes()
            page.evaluate('CombatReplay.seek(CombatReplay.diagnostics().duration)')
            assert engine.store._path(identity).read_bytes()==stored
            assert page.locator('#battle-mechanisms').evaluate('n=>n.scrollWidth<=n.clientWidth+2')
            click_control(page.locator('#battle-report-toggle'))
            page.evaluate("TutorialGuide.showChapter('combat-review')")
            assert '55.68' in page.locator('#tutorial-handbook [data-chapter=combat-review]').inner_text()
            page.evaluate("TutorialGuide.showChapter('secret-arts')")
            assert '107门' in page.locator('#tutorial-handbook [data-chapter=secret-arts]').inner_text()
            if page.locator('#settings-toggle').is_visible():click_control(page.locator('#settings-toggle'))
            expansion=runpy.run_path(str(ROOT/'tests/fixtures/technique_release.py'))['prepare_expansion_release']
            for mode,art in [('wind','manual_demon_dance'),('frost','manual_frost_sky')]:
                identity=create('secret')
                expansion(engine,identity,mode);page.evaluate('async id=>loadGame(id)',identity)
                navigation_locator(page,'[data-panel-target=secret-art]').click()
                click_control(page.locator('#secret-tab-known'));page.locator('#secret-art-filter').select_option('linked')
                click_control(page.locator(f'[data-secret-art={art}]'))
                with page.expect_response(lambda r:r.url.endswith('/secret-art')) as response:
                    click_control(page.locator('#secret-root-detail .secret-art-command'))
                assert response.value.status==200
                page.wait_for_function('id=>!busy&&game.secret_arts.library.find(a=>a.id===id).activated',arg=art)
                saved=engine.store.load(identity)
                assert saved.player.secret_art_state['manuals'][art]['activated']
                if mode=='wind':assert len(saved.player.puppets)==2 and all(a['realm_index']==4 for a in saved.player.puppets)
                stored=engine.store._path(identity).read_bytes()
                assert page.request.post(response.value.url,data=response.value.request.post_data_json).status==400
                assert engine.store._path(identity).read_bytes()==stored
                click_control(page.locator('#secret-art-toggle'))
            expansion(engine,identity,'crowd');page.evaluate('async id=>loadGame(id)',identity)
            navigation_locator(page,'#battle-report-open').click()
            page.wait_for_function('CombatReplay.diagnostics().active&&!document.querySelector("[data-combat-replay]").disabled')
            assert len(page.evaluate('CombatReplay.diagnostics().participants'))==24, page.evaluate('({shown:CombatReplay.diagnostics().participants.length,teams:Object.fromEntries(Object.entries(game.last_combat_report.visual.teams).map(([k,v])=>[k,v.length])),target:game.last_combat_report.target_name})')
            assert page.evaluate('typeof TechniqueFx.draw==="function"')
            stored=engine.store._path(identity).read_bytes()
            page.evaluate('CombatReplay.seek(CombatReplay.diagnostics().duration)')
            assert engine.store._path(identity).read_bytes()==stored
            click_control(page.locator('#battle-report-toggle'))
        assert not errors,errors
        browser.close()
    print(f'Final EXE technique/secret/combat/handbook passed: DLC={with_dlc}',flush=True)
