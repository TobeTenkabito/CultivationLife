"""Real HTTP loading, commands, stale recovery, atlas layout and four themes."""
import importlib.util,json,sys,tempfile,threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from cultivation_life import server
from cultivation_life.engine import GameEngine
from scripts.browser_navigation import navigation_locator
from playwright.sync_api import sync_playwright
spec=importlib.util.spec_from_file_location('mcfixture',ROOT/'tests/fixtures/civilizations-2100.py');fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)

def main():
    output=ROOT/'build/civilizations-2100';output.mkdir(exist_ok=True);rows=[]
    with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
        engine=GameEngine(ROOT,Path(folder)/'saves')
        class Quiet(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            http=ThreadingHTTPServer(('127.0.0.1',0),Quiet);threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    for theme in 'abdf':
                        for width,height in [(1440,1000),(360,800),(412,915),(915,412)]:
                            made=engine.create_game('万灵点击验收','supreme_earth','monster',2100,custom_start=dict(world='monster_realm',realm_index=7),monster_species_id='fox');identity=made['id'];fixture.prepare(engine,identity)
                            page=browser.new_page(viewport=dict(width=width,height=height),has_touch=width<1000);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                            page.goto(f'http://127.0.0.1:{http.server_port}');page.wait_for_function('!!configData&&!busy')
                            page.evaluate('(t)=>document.querySelector(`[data-theme-picker=start] [data-theme-choice=${t}]`).click()',theme)
                            page.evaluate('async id=>loadGame(id)',identity)
                            assert not errors,errors
                            assert page.locator('#game-screen').is_visible(),page.evaluate('({id:game?.id,toast:document.querySelector("#toast")?.textContent})')
                            assert not engine.store.load(identity).monster_civilization_state
                            navigation_locator(page,'[data-panel-target=civilizations]').click();page.wait_for_selector('.mc-region')
                            assert not engine.store.load(identity).monster_civilization_state
                            page.locator('[data-civilization-action=observe]').click();page.wait_for_selector('.mc-species')
                            assert engine.store.load(identity).monster_civilization_state
                            page.locator('[data-civilization-action=protect]').click();page.wait_for_function('!busy')
                            page.wait_for_function('document.querySelector("#civilizations-content")?.textContent.includes("现有护育安排")')
                            state=engine.store._path(identity).read_bytes()
                            current=page.locator('.mc-region').get_attribute('data-region')
                            other=page.locator('[aria-label="栖地记录"] option').evaluate_all('(options)=>options.map(o=>o.value)')
                            page.locator('[aria-label="栖地记录"]').select_option(next(r for r in other if r!=current))
                            assert page.locator('.mc-region').count()==1 and page.locator('[data-civilization-action=observe]').count()==0
                            page.locator(f'[data-civilization-region="{current}"]').click()
                            assert page.locator('.mc-region.current').count()==1
                            assert engine.store._path(identity).read_bytes()==state
                            page.locator('[data-civilization-tab=clans]').click();page.locator('[aria-label="新氏族名称"]').fill('青丘望月氏')
                            page.locator('[data-civilization-action=found]').click();page.wait_for_function('document.querySelector(".mc-clan-tree")?.textContent.includes("青丘望月氏")')
                            assert '青丘望月氏' in page.locator('.mc-clan-tree').inner_text()
                            page.locator('[aria-label="分支名称"]').fill('望月支');page.locator('[data-civilization-action=branch]').click();page.wait_for_function('!busy')
                            page.wait_for_function('document.querySelector(".mc-clan-tree")?.textContent.includes("望月支")')
                            # Real stale submission: another command changes revision before a clicked button.
                            page.evaluate('async id=>{const v=await api(`/api/games/${id}/civilizations-view`,{method:"POST",body:"{}"});await api(`/api/games/${id}/civilizations-action`,{method:"POST",body:JSON.stringify({action:"law",target_id:"eldest_eligible",expected_revision:v.revision})});}',identity)
                            page.locator('[data-civilization-action=leave]').click();page.wait_for_function('!busy')
                            page.wait_for_function('document.querySelector("#toast").textContent.includes("已更新")')
                            page.locator('[data-civilization-tab=journal]').click();page.wait_for_selector('.mc-timeline li')
                            assert '分出' in page.locator('.mc-timeline').inner_text()
                            page.screenshot(path=str(output/f'{theme}-{width}-journal.png'))
                            page.locator('[data-civilization-tab=ecology]').click();page.wait_for_timeout(350)
                            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                            assert page.locator('#civilizations-content svg').count()>0
                            page.screenshot(path=str(output/f'{theme}-{width}-ecology.png'))
                            assert not errors,errors
                            page.close();rows.append(dict(theme=theme,width=width,status='passed'))
                    # Court is reached through the original palace, not a second institution.
                    made=engine.create_game('王庭点击验收','supreme_earth','monster',2100,custom_start=dict(world='nether',realm_index=9),monster_species_id='fox');fixture.prepare(engine,made['id'])
                    page=browser.new_page();page.goto(f'http://127.0.0.1:{http.server_port}');page.wait_for_function('!!configData&&!busy');page.evaluate('async id=>loadGame(id)',made['id'])
                    navigation_locator(page,'[data-panel-target=civilizations]').click();page.wait_for_selector('.mc-region');page.locator('[data-civilization-action=observe]').click();page.wait_for_selector('.mc-species')
                    navigation_locator(page,'[data-panel-target=upper-institution]').click();page.get_by_role('button',name='万灵王庭 · 诸族正统').click();page.wait_for_selector('.mc-vote-track')
                    assert [x.strip() for x in page.locator('.mc-vote-track span').all_text_contents()]==['鳞祖 5','羽祖 4','兽祖 3','介祖 2','灵植门阀 1']
                    assert page.locator('[data-civilization-action=regime]').is_disabled()
                    page.screenshot(path=str(output/'court.png'));page.close()
                    # Actual clicks through every page of the entire retained journal.
                    from cultivation_life.system.monster_civilizations import core
                    made=engine.create_game('史册分页验收','supreme_earth','dao',2100,custom_start=dict(world='human',realm_index=4));fixture.prepare(engine,made['id'])
                    stored=engine.store.load(made['id']);core.activate(stored)
                    for i in range(192):core.fact(stored,'human','observation',stored.player.location_id,f'史事{i:03}',[core.PLAYER],'observed')
                    engine.store.save(stored)
                    page=browser.new_page();page.goto(f'http://127.0.0.1:{http.server_port}');page.wait_for_function('!!configData&&!busy');page.evaluate('async id=>loadGame(id)',stored.id)
                    navigation_locator(page,'[data-panel-target=civilizations]').click();page.wait_for_selector('.mc-region');page.locator('[data-civilization-tab=journal]').click()
                    baseline=engine.store._path(stored.id).read_bytes()
                    for index in range(1,16):
                        page.get_by_role('button',name='下一页',exact=True).click()
                        page.wait_for_function('(n)=>document.querySelector(".mc-tab-content .mc-actions span")?.textContent.startsWith(`${n+1}页`)',arg=index)
                    assert page.get_by_role('button',name='下一页',exact=True).is_disabled()
                    assert '史事000' in page.locator('.mc-timeline li').last.inner_text()
                    assert engine.store._path(stored.id).read_bytes()==baseline
                    page.close();browser.close()
            finally:http.shutdown();http.server_close()
    (output/'report.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Civilizations UI passed: 16 four-theme responsive cases, real observation, protection, founding, branch, stale submission recovery, all 16 journal pages and original palace court')

if __name__=='__main__':main()
