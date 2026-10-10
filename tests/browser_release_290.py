"""Real activity shortcuts, organization books, contribution, arrays and clans."""
import importlib.util
import json
from pathlib import Path
import sys,tempfile,threading
from http.server import ThreadingHTTPServer
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from cultivation_life import server
from cultivation_life.engine import GameEngine
from scripts.browser_navigation import navigation_locator
from playwright.sync_api import sync_playwright
spec=importlib.util.spec_from_file_location('orgfixture',ROOT/'tests/fixtures/organizations-290.py')
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)


def main():
    output=ROOT/'build/organizations-290';output.mkdir(exist_ok=True);rows=[]
    with tempfile.TemporaryDirectory(dir=ROOT/'build') as directory:
        engine=GameEngine(ROOT,Path(directory)/'saves')
        class Quiet(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',Path(directory)):
            http=ThreadingHTTPServer(('127.0.0.1',0),Quiet);threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    for theme in 'abdf':
                        for width,height in [(1440,1000),(360,800),(412,915),(915,412)]:
                            made=engine.create_game('势力验收','supreme_earth','dao',290,custom_start=dict(world='human',realm_index=4,sect='new',sect_name='验收宗'))
                            identity=made['id'];fixture.prepare(engine,identity)
                            page=browser.new_page(viewport=dict(width=width,height=height));errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                            page.goto(f'http://127.0.0.1:{http.server_port}');page.wait_for_function('!!configData && !busy')
                            page.evaluate('(t)=>document.querySelector(`[data-theme-picker=start] [data-theme-choice=${t}]`).click()',theme)
                            page.evaluate('async id=>loadGame(id)',identity)
                            def load():page.evaluate('async id=>loadGame(id)',identity)
                            def settle():page.wait_for_function('!busy')
                            def library():
                                d=page.locator('#faction-card .organization-heritage')
                                if not d.evaluate('d=>d.open'):d.locator(':scope > summary').click()
                                return d
                            navigation_locator(page,'[data-panel-target=faction]').click()
                            library().locator('[data-heritage-action=heritage_learn]').click();settle()
                            assert any(t.id=='TECH_HUMAN_HERITAGE_1' for t in engine._load(identity).player.known_techniques)
                            library().locator('[data-heritage-action=heritage_copy]').click();settle()
                            assert any(i.technique_id=='TECH_HUMAN_HERITAGE_1' for i in engine._load(identity).player.inventory)
                            library().locator('select').select_option('TECH_HUMAN_HERITAGE_2');library().locator('button[type=submit]').click();settle()
                            assert len(engine._load(identity).sects[made['player']['faction_id']].heritage['books'])==2
                            dep=page.locator('#faction-card .organization-depot');dep.locator(':scope>summary').click()
                            dep.locator('[data-depot-action=depot_request]').first.click();settle()
                            assert engine._load(identity).player.faction_contribution==9
                            if not dep.evaluate('d=>d.open'):dep.locator(':scope>summary').click()
                            dep.locator('[data-depot-action=depot_cancel]').click();settle()
                            assert engine._load(identity).player.faction_contribution==10
                            navigation_locator(page,'[data-panel-target=map]').click()
                            page.locator('.teleport-controls>summary').click()
                            page.locator('[data-teleport-build]').click();page.locator('#game-confirm-accept').click();settle()
                            assert engine._load(identity).economy_v2['teleport_arrays']
                            page.screenshot(path=str(output/f'{theme}-{width}-array.png'))
                            fixture.activities(engine,identity,'scheduled');load()
                            assert page.locator('[data-navigation-category=economy]').evaluate('b=>b.classList.contains("navigation-notice")')
                            page.locator('[data-navigation-category=common]').click()
                            assert page.locator('#navigation-current-events [data-navigation-shortcut]').count()==2
                            page.locator('#navigation-current-events [data-navigation-shortcut=auction]').click()
                            page.wait_for_selector('#auction-card.panel-open');assert '预告' in page.locator('#auction-title').inner_text()
                            fixture.activities(engine,identity,'open');load();page.locator('[data-navigation-category=common]').click()
                            page.locator('#navigation-current-events [data-navigation-shortcut=exchange]').click()
                            page.wait_for_selector('#exchange-card.panel-open');assert '剩余' in page.locator('#exchange-description').inner_text()
                            fixture.activities(engine,identity,'closed');load();page.locator('[data-navigation-category=common]').click()
                            assert page.locator('#navigation-current-events').count()==0
                            page.locator('#navigation-close').click()
                            fixture.clan(engine,identity);load();navigation_locator(page,'[data-panel-target=family]').click()
                            page.locator('[data-family]:not(:disabled)').filter(has_text='申请加入').first.click();settle()
                            assert engine._load(identity).family_state['membership']['kin'] is False
                            assert '外姓修士' in page.locator('#family-card').inner_text()
                            fixture.succeed(engine,identity);load()
                            page.locator('[data-family-name]').fill('新本家仙族');page.locator('[data-family]').filter(has_text='使用一次更名资格').click();settle()
                            assert engine._load(identity).family.name=='新本家仙族'
                            page.reload();page.wait_for_function('!!configData && !busy');load()
                            navigation_locator(page,'[data-panel-target=family]').click()
                            assert page.locator('[data-family-name]').count()==0
                            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                            assert not errors,errors
                            page.screenshot(path=str(output/f'{theme}-{width}-family.png'));page.close()
                            rows.append(dict(theme=theme,width=width,status='passed'))
                    browser.close()
            finally:http.shutdown();http.server_close()
    (output/'report.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Release 290 organizations UI passed: 16 four-theme desktop/mobile/landscape cases, real free study, paid copy, contribution refund, array construction, activity lifecycle, outsider admission, succession, rename and reload')

if __name__=='__main__':main()
