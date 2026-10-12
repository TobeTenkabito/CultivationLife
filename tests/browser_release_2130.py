"""Actual preset files, horizontal tabs and independent leader appointment."""
import json,sys,tempfile,threading,os
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from scripts.browser_navigation import navigation_locator
from scripts.release_evidence import inputs_digest


def main():
    output=ROOT/'build/release-2130-ui';output.mkdir(exist_ok=True);checks=[];signature=inputs_digest(ROOT)
    with tempfile.TemporaryDirectory(dir=ROOT/'build') as directory:
        engine=GameEngine(ROOT,Path(directory)/'saves')
        class Quiet(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',Path(directory)):
            http=ThreadingHTTPServer(('127.0.0.1',0),Quiet);threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    for theme in os.environ.get('VERIFY_THEMES','abdf'):
                        for width,height in [(1440,960),(393,852),(852,393)]:
                            print('Layout',theme,width,flush=True)
                            page=browser.new_page(viewport=dict(width=width,height=height));errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                            page.add_init_script('Object.hasOwn = undefined')
                            page.goto(f'http://127.0.0.1:{http.server_port}');page.wait_for_selector('#custom-start')
                            page.locator(f'[data-theme-picker=start] [data-theme-choice={theme}]').click()
                            page.locator('#custom-start>summary').click()
                            page.locator('#new-game-form [name=name]').fill('预设行者')
                            page.locator('#custom-realm').select_option('4')
                            page.locator('#custom-sect').select_option('new');page.locator('#custom-sect-name').fill('听松宗')
                            page.locator('#custom-family').select_option('new');page.locator('#custom-family-name').fill('听松仙族')
                            with page.expect_download() as download:page.locator('#custom-preset-export').click()
                            path=Path(directory)/'preset.json';download.value.save_as(path)
                            expected=json.loads(path.read_text(encoding='utf-8'))
                            assert expected['payload']['custom_start']['sect_name']=='听松宗'
                            page.locator('#custom-sect-name').fill('尚未载入')
                            page.locator('#custom-preset-file').set_input_files(path)
                            page.get_by_role('status').filter(has_text='预设已载入').wait_for()
                            assert page.locator('#custom-sect-name').input_value()=='听松宗'
                            bad=Path(directory)/'invalid.json';bad.write_text('{"format":"wrong"}',encoding='utf-8')
                            page.locator('#custom-preset-file').set_input_files(bad)
                            page.get_by_role('status').filter(has_text='导入失败').wait_for()
                            assert page.locator('#custom-sect-name').input_value()=='听松宗'
                            page.locator('#custom-start-submit').click();page.wait_for_function('game && !busy')
                            identity=page.evaluate('game.id');raw=engine.store.load(identity)
                            assert raw.player.realm_index==4 and raw.sects[raw.player.faction_id].name=='听松宗'
                            assert raw.family.name=='听松仙族'
                            before=engine.store._path(identity).read_bytes()
                            counts={}
                            for panel in ['faction','family','relationship','inventory','transformation','captive','merchant']:
                                print('Panel',panel,flush=True)
                                navigation_locator(page,f'[data-panel-target={panel}]').click()
                                host=page.locator(f'#{panel}-card');host.wait_for(state='visible')
                                tabs=host.locator('.panel-page-tabs').first
                                if not tabs.count():
                                    counts[panel]=0;continue
                                names=tabs.locator(':scope>button').all_text_contents();counts[panel]=len(names)
                                for name in names:
                                    tabs.locator(':scope>button').filter(has_text=name).first.click()
                                    assert tabs.locator('[aria-selected=true]').count()==1
                                    assert tabs.locator('[aria-selected=true]').inner_text()==name
                                page.wait_for_function('(id)=>!document.querySelector(id).getAnimations({subtree:true}).some(a=>a.playState==="running"&&a.effect.getTiming().iterations!==Infinity)',arg=f'#{panel}-card')
                                if host.evaluate('(n)=>n.scrollWidth>n.clientWidth+1'):page.screenshot(path=str(output/'overflow.png'))
                                assert host.evaluate('(n)=>n.scrollWidth<=n.clientWidth+1'),(panel,host.evaluate('(n)=>[...n.querySelectorAll("*")].filter(e=>e.getBoundingClientRect().right>n.getBoundingClientRect().right).map(e=>[e.tagName,e.className,e.getBoundingClientRect().width]).slice(0,10)'))
                                if panel in ['faction','family','merchant','relationship']:
                                    tabs.locator(':scope>button').first.click()
                                    page.screenshot(path=str(output/f'{theme}-{width}-{panel}.png'))
                            assert all(counts[p]>1 for p in ['faction','family','relationship','inventory','merchant']),counts
                            assert engine.store._path(identity).read_bytes()==before
                            navigation_locator(page,'[data-panel-target=intrigue]').click()
                            leader=page.locator('.intrigue-sect').get_by_label('掌门候选人')
                            candidate=leader.locator('option').first.get_attribute('value')
                            leader.select_option(candidate)
                            page.locator('.intrigue-sect').get_by_role('button',name='任命掌门',exact=True).click()
                            page.wait_for_function('!busy')
                            persisted=engine.store.load(identity)
                            assert persisted.intrigue_state['factions']['sect:'+persisted.player.faction_id]['positions']['leader']==candidate
                            assert page.evaluate('game.intrigue_system.sections.find(s=>s.kind==="sect").control_authority')
                            assert not errors,errors
                            checks.append(dict(theme=theme,width=width,tabs=counts,status='passed'));page.close()
                    browser.close()
            finally:http.shutdown();http.server_close()
    assert signature==inputs_digest(ROOT),'Final source changed during acceptance'
    (output/'report.json').write_text(json.dumps(dict(inputs_sha256=signature,cases=checks),ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Release 2130 UI passed: {len(checks)} layouts, actual preset export/import/create, invalid file rollback, parallel subpages, treasury-neutral navigation and real leader appointment')
if __name__=='__main__':main()
