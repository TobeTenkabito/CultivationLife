"""Actual native-server HTTP load and browser clicks against the compiled EXE."""
import json,runpy,urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright
from scripts.browser_navigation import navigation_locator
ROOT=Path(__file__).resolve().parents[1]

def verify_npc_development(base,with_dlc,folder):
    from cultivation_life.engine import GameEngine
    prepare=runpy.run_path(str(ROOT/'tests/fixtures/npc_development_release.py'))['prepare_npc_development']
    def request(path,data=None):
        req=urllib.request.Request(base+path,data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=90) as r:return json.load(r)
    with sync_playwright() as pw:
        browser=pw.chromium.launch();page=browser.new_page(viewport=dict(width=390,height=844));errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)));page.goto(base);page.wait_for_function('!!configData&&!busy')
        cases=[('dao','true_immortal')]+([('demonic','asura_upper'),('monster','nether_upper'),('ghost','reincarnation_upper')] if with_dlc else [])
        for path,preset in cases:
            identity=request('/api/games',dict(name='成品育才验收',path=path,spirit_root='supreme_metal',seed=352,preset_id=preset,monster_species_id='serpent'))['id']
            prepare(GameEngine(ROOT,folder/'data/saves'),identity)
            page.evaluate('id=>loadGame(id)',identity);page.wait_for_function('!busy')
            navigation_locator(page,'[data-panel-target=npc-development]').click();page.wait_for_selector('[data-target-id=release-student]')
            page.locator('[data-target-id=release-student]').click()
            page.get_by_label('培养方向',exact=True).select_option('body_art');page.get_by_label('培养方式',exact=True).select_option('material');page.get_by_label('培养轮数',exact=True).select_option('1')
            page.locator('#npc-development-submit').click();page.wait_for_function('!busy&&document.querySelector("select[aria-label=肉身神通]")?.textContent.includes("当前3重")')
            page.get_by_label('培养方向',exact=True).select_option('technique_growth');page.locator('#npc-development-submit').click()
            page.wait_for_function('!busy&&document.querySelector("select[aria-label=研修功法]")?.textContent.includes("2重")')
            page.get_by_label('培养方向',exact=True).select_option('domain');page.locator('#npc-development-submit').click()
            page.wait_for_function('!busy&&document.querySelector("#npc-domain-activate")?.disabled&&document.querySelector("#npc-domain-activate")?.textContent.includes("已启用")')
            for form in ('bird','deva','dragon','yaksha','flora','serpent','kinnara','corpse-male','corpse-female','prisoner'):
                page.locator(f'[data-target-id=release-{form}]').click();page.wait_for_function('document.querySelector(".npc-development-art img")?.naturalWidth>0')
            page.locator('[data-target-id=release-bird]').click();page.locator('#npc-development-charge').click()
            page.wait_for_function('!busy&&document.querySelector(".npc-development-profile").textContent.includes("能源耐久 100")')
            page.screenshot(path=str(folder/f'npc-{path}.png'));page.locator('#npc-development-dialog>header button').click()
            navigation_locator(page,'#battle-report-open').click();page.wait_for_function('CombatReplay.diagnostics().active&&!document.querySelector("[data-combat-replay]").disabled')
            assert page.evaluate("game.last_combat_report.visual.teams.hero.some(n=>n.asset==='mechanical-bird')")
            page.keyboard.press('Escape')
        assert not errors,errors
        browser.close()
    print(f'NPC development final EXE: DLC={with_dlc}; actual refinement/techniques/domain/fuel/portraits/replay passed',flush=True)
