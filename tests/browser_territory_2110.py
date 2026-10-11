"""Real desktop/mobile map selection, material construction, policy and relocation."""
import importlib.util,json,sys,tempfile,threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from cultivation_life import server
from cultivation_life.engine import GameEngine
from scripts.browser_navigation import navigation_locator
from scripts.release_evidence import inputs_digest
from playwright.sync_api import sync_playwright
spec=importlib.util.spec_from_file_location('territory_fixture',ROOT/'tests/fixtures/territory-2110.py')
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)

def main():
    output=ROOT/'build/territory-2110';output.mkdir(exist_ok=True);rows=[];signature=inputs_digest(ROOT)
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
                            made=engine.create_game('地方验收','supreme_earth','dao',2110,custom_start=dict(world='human',realm_index=4,sect='new',sect_name='验收宗'))
                            prepared=fixture.prepare(engine,made['id']);identity=made['id']
                            page=browser.new_page(viewport=dict(width=width,height=height),has_touch=width<1000);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                            page.goto(f'http://127.0.0.1:{http.server_port}');page.wait_for_function('!!configData && !busy')
                            page.evaluate('(t)=>document.querySelector(`[data-theme-picker=start] [data-theme-choice=${t}]`).click()',theme)
                            page.evaluate('async id=>loadGame(id)',identity);navigation_locator(page,'[data-panel-target=map]').click();page.wait_for_selector('#map-atlas svg')
                            before=engine.store._path(identity).read_bytes()
                            page.locator(f'[data-atlas-location="{prepared["source"]}"]').click()
                            assert page.locator('.atlas-detail').get_attribute('data-selected-location')==prepared['source']
                            assert engine.store._path(identity).read_bytes()==before
                            page.locator('[aria-label="地图地点"]').select_option(prepared['destination'])
                            page.locator('.atlas-decisions>summary').click()
                            # The visible quote can expire before submission. A
                            # real failed POST must refresh once and unlock UI.
                            saved=engine.store.load(identity)
                            market=saved.economy_v2['markets'][f'human:{prepared["destination"]}']
                            from cultivation_life.system.territory.actions import construction_plan
                            material=construction_plan(saved,engine.maps,saved.sects[prepared['owner']],prepared['destination'])['materials'][0]['id']
                            market['commodities'][material]['stock']=0;engine.store.save(saved)
                            engine._load(identity);expired=engine.store._path(identity).read_bytes()
                            page.locator('[data-organization-action=build_outpost]').click()
                            page.wait_for_function('!busy && document.querySelector("#toast").classList.contains("show")')
                            assert engine.store._path(identity).read_bytes()==expired
                            page.locator('.atlas-decisions>summary').click()
                            assert page.locator('[data-organization-action=build_outpost]').is_disabled()
                            saved=engine.store.load(identity);saved.economy_v2['markets'][f'human:{prepared["destination"]}']['commodities'][material]['stock']=50;engine.store.save(saved)
                            page.evaluate('async id=>loadGame(id)',identity)
                            page.locator('.atlas-decisions>summary').click()
                            page.locator('[data-organization-action=build_outpost]').click();page.wait_for_function('!busy && game.map.territory.locations.some(r=>r.outpost)')
                            fixture.assert_outpost(engine,identity)
                            page.locator('.atlas-decisions>summary').click()
                            page.locator('[aria-label="地方政策"]').select_option('patrol')
                            page.locator('[data-organization-action=territory_policy]').click();page.wait_for_function('!busy')
                            actual=engine.store.load(identity);assert actual.intrigue_state['territory']['holdings']['human'][prepared['destination']][prepared['owner']]['policy']=='patrol'
                            page.locator('#map-atlas').screenshot(path=str(output/f'{theme}-{width}-map.png'))
                            page.locator('.atlas-relocations>summary').click();form=page.locator('.atlas-relocation-form').first
                            form.locator('select').select_option(prepared['destination']);form.locator('button').click()
                            page.wait_for_function('!busy && game.map.locations.find(r=>r.current).influences.some(r=>r.owned && r.headquarters)')
                            fixture.assert_relocated(engine,identity)
                            page.reload();page.wait_for_function('!!configData && !busy');page.evaluate('async id=>loadGame(id)',identity);navigation_locator(page,'[data-panel-target=map]').click();page.wait_for_selector('#map-atlas svg')
                            assert '100' in page.locator('.atlas-detail').inner_text()
                            stored=engine.store._path(identity).read_bytes()
                            page.evaluate('showStart();renderButtons()')
                            assert page.evaluate("Array.from(document.querySelectorAll('#map-atlas [data-atlas-unavailable]')).every(b=>b.disabled)")
                            assert engine.store._path(identity).read_bytes()==stored
                            page.evaluate('async id=>loadGame(id)',identity)
                            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1') and not errors,errors
                            rows.append(dict(theme=theme,width=width,status='passed'));page.close()
                    browser.close()
            finally:http.shutdown()
    assert signature==inputs_digest(ROOT)
    (output/'report.json').write_text(json.dumps(dict(inputs_sha256=signature,cases=rows),ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Territory UI passed: {len(rows)} theme/viewport cases; real SVG selection, paid materials, policy vote, headquarters vote and reload')

if __name__=='__main__':main()
