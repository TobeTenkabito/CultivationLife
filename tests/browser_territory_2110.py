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
                            page.evaluate('async id=>loadGame(id)',identity);navigation_locator(page,'[data-panel-target=map]').click()
                            page.wait_for_selector('#map-locations')
                            assert page.locator('#map-locations').is_visible() and not page.locator('#map-atlas').is_visible()
                            page.locator('#map-view-tabs button',has_text='可视地图').click();page.wait_for_selector('#map-atlas svg')
                            assert not page.locator('#map-locations').is_visible()
                            assert page.locator('[data-atlas-view=decisions]').is_visible()
                            page.screenshot(path=str(output/f'{theme}-{width}-first-map.png'))
                            before=engine.store._path(identity).read_bytes()
                            page.locator(f'[data-atlas-location="{prepared["source"]}"]').click()
                            assert page.locator('.atlas-detail').get_attribute('data-selected-location')==prepared['source']
                            assert engine.store._path(identity).read_bytes()==before
                            page.locator('[aria-label="地图地点"]').select_option(prepared['destination'])
                            page.locator('[data-atlas-view=decisions]').click()
                            assert page.locator('[data-organization-action=build_outpost]').is_visible()
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
                            assert page.locator('[data-organization-action=build_outpost]').is_disabled()
                            saved=engine.store.load(identity);saved.economy_v2['markets'][f'human:{prepared["destination"]}']['commodities'][material]['stock']=50;engine.store.save(saved)
                            page.evaluate('async id=>loadGame(id)',identity)
                            page.locator('[data-organization-action=build_outpost]').click();page.wait_for_function('!busy && game.map.territory.locations.some(r=>r.outpost)')
                            fixture.assert_outpost(engine,identity)
                            page.locator('[aria-label="地方政策"]').select_option('patrol')
                            page.locator('[data-organization-action=territory_policy]').click();page.wait_for_function('!busy')
                            actual=engine.store.load(identity);assert actual.intrigue_state['territory']['holdings']['human'][prepared['destination']][prepared['owner']]['policy']=='patrol'
                            page.screenshot(path=str(output/f'{theme}-{width}-decisions.png'))
                            page.locator('.atlas-relocations>summary').click();form=page.locator('.atlas-relocation-form').first
                            form.locator('select').select_option(prepared['destination']);form.locator('button').click()
                            page.wait_for_function('!busy && game.map.locations.find(r=>r.current).influences.some(r=>r.owned && r.headquarters)')
                            fixture.assert_relocated(engine,identity)
                            # Discoverable shortcuts in the actual DLC panel,
                            # with lazy map rendering and no gameplay mutation.
                            stored=engine.store._path(identity).read_bytes()
                            for view in ['decisions','influence']:
                                navigation_locator(page,'[data-panel-target=intrigue]').click()
                                page.locator(f'[data-territory-entry={view}]').click()
                                assert page.locator('#map-card').evaluate('n=>n.classList.contains("panel-open")')
                                assert not page.locator('#map-locations').is_visible()
                                assert page.locator(f'[data-atlas-view={view}]').get_attribute('aria-pressed')=='true'
                            assert engine.store._path(identity).read_bytes()==stored
                            page.locator('[data-atlas-display=list]').click()
                            assert page.locator('.atlas-region-meter progress').count()>0
                            assert page.locator('.atlas-region-meter progress[value="100"]').count()>0
                            page.screenshot(path=str(output/f'{theme}-{width}-influence-list.png'))
                            page.locator('[data-atlas-display=map]').click()
                            page.screenshot(path=str(output/f'{theme}-{width}-map.png'))
                            page.reload();page.wait_for_function('!!configData && !busy');page.evaluate('async id=>{while(busy)await new Promise(resolve=>setTimeout(resolve,50));await loadGame(id)}',identity);page.wait_for_function('(id)=>game?.id===id && !busy && !document.querySelector("#game-screen").classList.contains("hidden")',arg=identity);navigation_locator(page,'[data-panel-target=map]').click();page.locator('#map-view-tabs button',has_text='可视地图').click();page.wait_for_selector('#map-atlas svg')
                            assert '100' in page.locator('.atlas-detail').inner_text()
                            stored=engine.store._path(identity).read_bytes()
                            page.evaluate('showStart();renderButtons()')
                            assert page.evaluate("Array.from(document.querySelectorAll('#map-atlas [data-atlas-unavailable]')).every(b=>b.disabled)")
                            assert engine.store._path(identity).read_bytes()==stored
                            page.evaluate('async id=>loadGame(id)',identity)
                            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1') and not errors,errors
                            rows.append(dict(theme=theme,width=width,status='passed'));page.close()
                    # UI eligibility is projected rather than hidden. Use real
                    # game loading for non-members, ordinary members and DLC-off.
                    from cultivation_life.content_registry import WORLD_SYSTEMS
                    for role in ['non-member','ordinary-member','dlc-off']:
                        for width,height in [(1440,1000),(360,800)]:
                            made=engine.create_game('资格验收','supreme_earth','dao',2120,custom_start=dict(world='human',realm_index=4,sect='new',sect_name='验收宗'))
                            prepared=fixture.prepare(engine,made['id']);saved=engine.store.load(made['id'])
                            if role=='non-member':saved.player.faction_id=None
                            elif role=='ordinary-member':
                                saved.player.realm_index=1;saved.player.layer=1
                                entity=saved.sects[prepared['owner']];entity.founded_by_player=False
                                entity.npcs[0].realm_index=4
                                saved.intrigue_state['factions'][f'sect:{entity.id}']['controller_id']=entity.npcs[0].id
                            engine.store.save(saved)
                            enabled=WORLD_SYSTEMS['intrigue_dlc']['enabled']
                            try:
                                if role=='dlc-off':WORLD_SYSTEMS['intrigue_dlc']['enabled']=False
                                page=browser.new_page(viewport=dict(width=width,height=height));errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                                page.goto(f'http://127.0.0.1:{http.server_port}');page.wait_for_function('!!configData && !busy');page.evaluate('async id=>loadGame(id)',made['id']);navigation_locator(page,'[data-panel-target=map]').click();page.locator('#map-view-tabs button',has_text='可视地图').click()
                                stored=engine.store._path(made['id']).read_bytes()
                                page.locator('[data-atlas-view=decisions]').click()
                                expected={'non-member':'尚未加入本界','ordinary-member':'暂无决策权','dlc-off':'尚未启用'}[role]
                                assert expected in page.locator('.atlas-detail').inner_text(),(role,page.locator('.atlas-detail').inner_text())
                                assert page.evaluate("Array.from(document.querySelectorAll('[data-organization-action]:not([data-organization-action=relocate])')).every(n=>n.disabled)")
                                page.evaluate('renderButtons()')
                                assert page.evaluate("Array.from(document.querySelectorAll('[data-organization-action]:not([data-organization-action=relocate])')).every(n=>n.disabled)")
                                assert page.locator('[data-atlas-view=guide]').count()==0
                                page.locator('[data-atlas-view=influence]').click()
                                assert engine.store._path(made['id']).read_bytes()==stored
                                assert not errors,errors
                                rows.append(dict(role=role,width=width,status='passed'));page.close()
                            finally:WORLD_SYSTEMS['intrigue_dlc']['enabled']=enabled
                    browser.close()
            finally:http.shutdown()
    assert signature==inputs_digest(ROOT)
    (output/'report.json').write_text(json.dumps(dict(inputs_sha256=signature,cases=rows),ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Territory UI passed: {len(rows)} theme/viewport cases; real SVG selection, paid materials, policy vote, headquarters vote and reload')

if __name__=='__main__':main()
