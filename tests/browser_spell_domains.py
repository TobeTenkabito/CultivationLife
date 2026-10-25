"""Real path-gated editor submissions, cast playback and settled thunder CG."""
import hashlib
import json
import random
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from playwright.sync_api import sync_playwright
from cultivation_life import server, content_registry as registry
from cultivation_life.engine import GameEngine
from cultivation_life.ui_preferences import write_ui_preferences
from fixtures.home_scenes import thunder
from scripts.browser_navigation import navigation_locator
from domain_ink_acceptance import verify_outline


def main():
    out=ROOT/'build/spell-domains';out.mkdir(parents=True,exist_ok=True)
    results={'paths':{},'styles':[],'controls':[],'outlines':{},'widths':[1440,390,320]}
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder);engine=GameEngine(ROOT,root/'saves')
        write_ui_preferences(root,{'pixel_art':True,'reduced_motion':True})
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',root),patch('cultivation_life.runtime.persistence_root',return_value=root):
            http=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch();page=browser.new_page(viewport=dict(width=1440,height=1000),reduced_motion='reduce')
                    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    page.goto(f'http://127.0.0.1:{http.server_port}');page.wait_for_function('!!configData');page.evaluate('GameThemes.ready')
                    if '--fallback-only' in sys.argv:
                        identity=engine.create_game('加载回退','supreme_metal','dao',643,preset_id='core')['id']
                        game=engine.store.load(identity);game.pending_event=None;game.settings.update(silent_events=True,combat_popup=False)
                        engine._combat(game,dict(target_name='同道',target_power=engine._player_battle_power(game)*.9,path='dao',gender='female'),False,random.Random(12));engine.store.save(game)
                        page.route('**/api/domain-styles',lambda route:route.fulfill(status=503,body='{}'))
                        page.evaluate('id=>loadGame(id)',identity);before=engine.store._path(identity).read_bytes()
                        navigation_locator(page,'#battle-report-open').click()
                        page.wait_for_function('CombatReplay.diagnostics().active&&!document.querySelector("[data-combat-replay]").disabled')
                        page.evaluate('CombatReplay.seek(3)');assert page.evaluate('DomainFields.catalog.length')==13
                        page.locator('#battle-report-toggle').click();page.unroute('**/api/domain-styles')
                        navigation_locator(page,'#battle-report-open').click()
                        page.wait_for_function('CombatReplay.diagnostics().active&&!document.querySelector("[data-combat-replay]").disabled')
                        assert page.evaluate('DomainFields.catalog.length')==30
                        assert engine.store._path(identity).read_bytes()==before and not errors
                        (out/'fallback-validation.json').write_text(json.dumps({'status':'passed','failed_vocabulary_playback':True,'retry':True,'source_sha256':hashlib.sha256((ROOT/'web/combat-replay.js').read_bytes()).hexdigest()},indent=2),encoding='utf8')
                        browser.close();print('Optional style failure: playback, retry and read-only passed');return
                    ids={};pictures=set()
                    for path,count in [('dao',13),('demonic',18),('monster',18),('ghost',18),('confucian',14),('buddhist',14)]:
                        made=engine.create_game('特效验收','supreme_metal',path,641,preset_id='core' if path=='dao' else None if path=='buddhist' else path+'_core',monster_species_id='fox' if path=='monster' else None)
                        identity=ids[path]=made['id'];game=engine.store.load(identity)
                        game.pending_event=None;game.settings.update(silent_events=True,combat_popup=False)
                        engine._combat(game,dict(target_name='试法同道',target_power=engine._player_battle_power(game)*.9,path=path,gender='female'),False,random.Random(12))
                        engine.store.save(game)
                        page.evaluate('id=>loadGame(id)',identity)
                        before=engine.store._path(identity).read_bytes()
                        if not page.locator('[data-voisinage-editor]').is_visible():
                            page.locator('.settings-dock [data-panel-target="settings"]').click()
                        page.locator('[data-voisinage-editor]').click()
                        page.wait_for_function('VoisinageEditor.status().ready')
                        choices=page.locator('#ve-outline option').evaluate_all('rows=>rows.map(r=>r.value)');assert len(choices)==count,(path,choices)
                        base={'mist','star','frost','lotus','sword','seal','water','mountain','wood','thunder','moon','void','time'}
                        for style in [s for s in choices if s not in results['outlines']]:
                            page.locator('#ve-outline').select_option(style);page.locator('#ve-pattern').select_option(style)
                            page.locator('#ve-scene').select_option('control')
                            pictures.add(page.locator('#ve-canvas').evaluate('c=>c.toDataURL()'))
                            page.locator('#ve-canvas').screenshot(path=str(out/f'domain-{style}.png'))
                            results['outlines'][style]=verify_outline(page,style)
                            page.locator('#ve-save').click();page.wait_for_function('!VoisinageEditor.status().busy')
                            assert '已保存' in page.locator('#ve-status').inner_text()
                            if style not in base:results['styles'].append(style)
                        controls=page.locator('#ve-control option').evaluate_all('rows=>rows.map(r=>r.value)')
                        assert len(controls)==({'dao':14,'monster':16}.get(path,15)),(path,controls)
                        legacy={'rings','talismans','stars','lotus','pillars','crystal'}
                        for control in [r for r in controls if r not in legacy and r not in results['controls']]:
                            page.locator('#ve-control').select_option(control);page.locator('#ve-scene').select_option('control')
                            page.locator('#ve-canvas').screenshot(path=str(out/f'control-{control}.png'))
                            page.locator('#ve-save').click();page.wait_for_function('!VoisinageEditor.status().busy')
                            assert '已保存' in page.locator('#ve-status').inner_text()
                            results['controls'].append(control)
                        # Server reads the save; a spoofed path cannot authorize foreign styles.
                        value=dict(outline='ghost-mist' if path!='ghost' else 'demon-rift',pattern='mist',palette='#89abcd',control='rings',density=65)
                        previous=(root/'data/ui_preferences.json').read_bytes()
                        response=page.request.post(f'http://127.0.0.1:{http.server_port}/api/ui-preferences',data={'game_id':identity,'voisinage_appearance':value})
                        assert response.status==400,response.text()
                        response=page.request.post(f'http://127.0.0.1:{http.server_port}/api/ui-preferences',data={'game_id':identity,'path':'ghost','voisinage_appearance':value})
                        assert response.status==400,response.text()
                        assert (root/'data/ui_preferences.json').read_bytes()==previous
                        page.locator('#ve-cancel').click()
                        page.locator('.settings-dock [data-panel-target="settings"]').click()
                        navigation_locator(page,'#battle-report-open').click()
                        page.wait_for_function('CombatReplay.diagnostics().active&&!document.querySelector("[data-combat-replay]").disabled')
                        for width,height in [(1440,1000),(390,844),(320,740)]:
                            page.set_viewport_size(dict(width=width,height=height));page.wait_for_timeout(100)
                            page.evaluate('CombatReplay.seek(3.0)')
                            assert page.locator('#battle-animation').evaluate('n=>n.scrollWidth<=n.clientWidth+1')
                            page.locator('#battle-animation canvas').screenshot(path=str(out/f'cast-{path}-{width}.png'))
                        page.evaluate('for(let t=0;t<Math.min(30,CombatReplay.diagnostics().duration);t+=.2)CombatReplay.seek(t)')
                        assert engine.store._path(identity).read_bytes()==before
                        assert page.evaluate('CombatReplay.diagnostics().decodedBytes')<96*1024*1024
                        page.locator('#battle-report-toggle').click();assert not page.evaluate('CombatReplay.diagnostics().raf')
                        page.set_viewport_size(dict(width=1440,height=1000));results['paths'][path]=count
                    assert len(pictures)==30
                    assert len(results['controls'])==14
                    from cultivation_life.domain_styles import controls as control_catalog
                    for row in [r for r in control_catalog(all_paths=True) if r.get('owner')]:
                        disabled_one=[r for r in registry.EXTENSION_REPORT if r['id']!=row['owner']]
                        with patch.object(registry,'EXTENSION_REPORT',disabled_one):
                            identity=ids[row.get('path') or 'dao']
                            response=page.request.get(f'http://127.0.0.1:{http.server_port}/api/domain-styles?id={identity}').json()
                            assert row['id'] not in response['available_controls']
                            value=dict(outline='mist',pattern='mist',palette='jade',control=row['id'],density=65)
                            assert page.request.post(f'http://127.0.0.1:{http.server_port}/api/ui-preferences',data={'game_id':identity,'voisinage_appearance':value}).status==400
                    # Disabled packages disappear from the catalog and stale submissions fail.
                    disabled=[r for r in registry.EXTENSION_REPORT if r['id'] not in {'official.asura-manifestation','official.monster-bloodlines','official.ghost-reincarnation'}]
                    with patch.object(registry,'EXTENSION_REPORT',disabled):
                        for path,style in [('demonic','asura-prison'),('monster','monster-origin'),('ghost','ghost-rebirth')]:
                            response=page.request.get(f'http://127.0.0.1:{http.server_port}/api/domain-styles?id={ids[path]}').json()
                            assert len(response['catalog'])==21 and len(response['available'])==15
                            value=dict(outline=style,pattern='mist',palette='jade',control='rings',density=65)
                            response=page.request.post(f'http://127.0.0.1:{http.server_port}/api/ui-preferences',data={'game_id':ids[path],'voisinage_appearance':value})
                            assert response.status==400
                    identity=ids['dao'];thunder(engine,identity);page.evaluate('id=>loadGame(id)',identity)
                    page.wait_for_selector('#event-cinematic canvas',state='visible')
                    chosen=page.evaluate('EventScenes.inspect().variant')
                    assert chosen in ['forked-storm','violet-net','gold-lances']
                    page.reload();page.wait_for_function('!!configData');page.evaluate('GameThemes.ready');page.evaluate('id=>loadGame(id)',identity)
                    page.wait_for_selector('#event-cinematic canvas',state='visible')
                    assert page.evaluate('EventScenes.inspect().variant')==chosen
                    page.locator('#event-choices button').first.click();page.wait_for_function('!busy')
                    page.wait_for_function('document.querySelector(".event-cinematic-caption").textContent.includes("已结算")')
                    assert page.evaluate('EventScenes.inspect().variant')==chosen
                    before=engine.store._path(identity).read_bytes()
                    page.locator('#event-cinematic button').filter(has_text='重播').click()
                    assert page.evaluate('EventScenes.inspect().variant')==chosen
                    page.wait_for_function('EventScenes.inspect().phase==="strike"');page.wait_for_timeout(220)
                    page.locator('#event-cinematic button').filter(has_text='暂停').click()
                    page.locator('#event-cinematic canvas').screenshot(path=str(out/'thunder-strike.png'))
                    for width,height in [(390,844),(320,740)]:
                        page.set_viewport_size(dict(width=width,height=height));page.locator('#event-cinematic canvas').screenshot(path=str(out/f'thunder-{width}.png'))
                        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                    assert engine.store._path(identity).read_bytes()==before
                    page.locator('#event-cinematic button').filter(has_text='收起动画').click();assert not page.evaluate('EventScenes.inspect().frame')
                    assert not errors,errors
                    browser.close()
            finally:http.shutdown();http.server_close()
    assert len(results['outlines'])==30
    results.update(status='passed',readonly=True,forged_path_rejected=True,disabled_dlc_rejected=True)
    results['source_sha256']={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ['web/spell-effects.js','web/domain-motifs.js','web/domain-ink.js','web/voisinage-fields.js','web/combat-domains.js','web/tribulation-effects.js','web/event-scenes.js','web/voisinage-editor.js']}
    (out/'validation.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(results,ensure_ascii=False))


if __name__=='__main__':main()
