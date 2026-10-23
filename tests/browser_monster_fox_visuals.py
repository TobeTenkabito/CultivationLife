"""Real HTTP/UI acceptance for DLC fox portraits and settled combat playback."""
import copy
import json
import random
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.content_registry import MONSTER_EVOLUTIONS
from cultivation_life.monster_visuals import fox_appearance
from scripts.browser_navigation import navigation_locator


def main():
    out=ROOT/'build/monster-fox-visuals';out.mkdir(parents=True,exist_ok=True)
    result={'forms':[],'widths':[]}
    with tempfile.TemporaryDirectory() as folder:
        engine=GameEngine(ROOT,Path(folder)/'saves')
        made=engine.create_game('狐族验收','supreme_water','monster',seed=4170,monster_species_id='fox',start_world='monster_realm')
        base=engine.store.load(made['id']);base.pending_event=None
        base.settings.update(silent_events=True,combat_popup=True)
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    page=browser.new_page(viewport=dict(width=1440,height=960),reduced_motion='reduce')
                    errors=[];requests=[]
                    page.on('pageerror',lambda e:errors.append(str(e)))
                    page.on('request',lambda r:requests.append((r.method,r.url)))
                    url=f'http://127.0.0.1:{http.server_port}'
                    page.goto(url);page.wait_for_function('!!configData && !!window.CombatReplay')
                    page.evaluate('GameThemes.ready')
                    page.locator('#theme-open').click()
                    page.locator('#theme-dialog [data-pixel-setting]').set_checked(True)
                    page.evaluate('GameThemes.saved')
                    page.locator('[data-close-dialog=theme-dialog]').click()
                    forms=[(n,'female') for n in ['FOX_SPIRIT','FOX_KING','FOX_MOON_DREAM','FOX_NINE_TAIL']]
                    forms += [(n,g) for n in ['FOX_ILLUSION_LORD','FOX_MOON_SOVEREIGN','FOX_NINE_FLAME_SOVEREIGN',
                                              'FOX_MYSTIC_7','FOX_MOON_7','FOX_ANCESTRAL_DREAM'] for g in ['female','male']]
                    for i,(node,gender) in enumerate(forms):
                        g=copy.deepcopy(base);p=g.player
                        p.realm_index=MONSTER_EVOLUTIONS[node]['realm_index'];p.layer=1;p.gender=gender
                        p.monster_evolution_id=node;p.monster_evolution_history=['FOX_KING',node]
                        expected=fox_appearance(p)
                        target=dict(target_name='演武修士',path='dao',gender='male',combat_type='cultivator',
                                    target_realm_index=p.realm_index,target_power=engine._player_battle_power(g)*(4 if i%2 else .2))
                        engine._combat(g,target,False,random.Random(4170))
                        assert g.last_combat_report['visual']['hero']==expected['combat']
                        engine.store.save(g)
                        page.evaluate('id=>loadGame(id)',made['id'])
                        page.wait_for_function('id=>game?.player?.visual_actor===id',arg=expected['static'])
                        portrait=expected['static'].removeprefix('actor.monster.')+'-portrait.png'
                        page.wait_for_function('''file=>{const im=document.querySelector('.pixel-portrait');return !im.hidden&&im.complete&&im.naturalWidth===128&&im.src.endsWith(file)}''',arg=portrait)
                        page.locator('.hud-identity').click()
                        page.wait_for_function('id=>document.querySelector(".pixel-details-art canvas").dataset.actor===id',arg=expected['static'])
                        if i in [0,3,8,10,14,15]:page.screenshot(path=str(out/f'{expected["combat"]}-details.png'))
                        page.keyboard.press('Escape')
                        navigation_locator(page,'#battle-report-open').click()
                        page.wait_for_function('CombatReplay.diagnostics().active&&!document.querySelector("[data-combat-replay]").disabled')
                        saved=engine.store._path(made['id']).read_bytes();before=page.evaluate('JSON.stringify(game)')
                        requests.clear()
                        for at in [0,1.5,2.1,3,6,10,10000]:
                            page.evaluate('t=>CombatReplay.seek(t)',at)
                            diag=page.evaluate('CombatReplay.diagnostics()')
                            assert diag['actors']['hero']['id']==expected['combat']
                            assert diag['decodedBytes']<64*1024*1024
                            for b in diag['bounds'].values():
                                assert b[0]>=0 and b[1]>=0 and b[2]<=diag['viewport'][0] and b[3]<=diag['viewport'][1]
                        assert page.locator('[data-combat-meter=hero] progress').evaluate('p=>p.value')==g.last_combat_report['player_combat_state']
                        page.locator('[data-combat-replay]').click();page.locator('[data-combat-pause]').click()
                        assert not any('/api/' in u for _,u in requests)
                        assert engine.store._path(made['id']).read_bytes()==saved
                        assert page.evaluate('JSON.stringify(game)')==before
                        page.evaluate('CombatReplay.seek(3)')
                        if i in [0,3,8,10,14,15]:page.screenshot(path=str(out/f'{expected["combat"]}-combat.png'))
                        if i in [3,14]:
                            for width in [800,390,320]:
                                page.set_viewport_size(dict(width=width,height=844));page.wait_for_timeout(100)
                                page.evaluate('CombatReplay.seek(3)')
                                assert page.locator('#battle-animation').evaluate('n=>n.scrollWidth<=n.clientWidth+1')
                                result['widths'].append([expected['combat'],width])
                            page.set_viewport_size(dict(width=1440,height=960))
                        result['forms'].append(dict(node=node,gender=gender,actor=expected['combat'],decoded_bytes=diag['decodedBytes']))
                        page.keyboard.press('Escape')
                        assert page.evaluate('CombatReplay.diagnostics().cache===0')
                    # Real domain-only projection uses the fox domain pose, not a human dragon clip.
                    from dataclasses import asdict
                    from test_domain_combat import state,voisinage
                    from cultivation_life.content_registry import WORLD_SYSTEMS
                    g=copy.deepcopy(base);p=g.player
                    p.realm_index=7;p.monster_evolution_id='FOX_ANCESTRAL_DREAM';p.monster_evolution_history=['FOX_NINE_TAIL','FOX_ANCESTRAL_DREAM']
                    p.transcendence=state()
                    with patch.dict(WORLD_SYSTEMS,transcendent_combat=dict(voisinages=[asdict(voisinage())])):
                        engine._combat(g,dict(target_name='域中对手',combat_type='cultivator',target_realm_index=7,
                                              target_power=engine._player_battle_power(g)),False,random.Random(1))
                    assert any(r.get('voisinage') for r in g.last_combat_report['rounds'])
                    engine.store.save(g);page.evaluate('id=>loadGame(id)',made['id'])
                    navigation_locator(page,'#battle-report-open').click()
                    page.wait_for_function('CombatReplay.diagnostics().active&&!document.querySelector("[data-combat-replay]").disabled')
                    page.evaluate('CombatReplay.seek(1)')
                    assert page.evaluate('CombatReplay.diagnostics().actors.hero.mode')=='domain'
                    result['domain']=True
                    page.keyboard.press('Escape')
                    # Installed but disabled: filtered catalog and HTTP route reject all exclusive files.
                    active=[r for r in server.EXTENSION_REPORT if r.get('id')!='official.monster-bloodlines']
                    asset='/extension-assets/official.monster-bloodlines/visual/fox/fox-spirit-shared-figure.png'
                    with patch.object(server,'EXTENSION_REPORT',active):
                        assert page.request.get(url+asset).status==404
                        page.reload();page.wait_for_function('!!window.PixelLibrary');page.evaluate('GameThemes.ready')
                        requests.clear();page.evaluate('id=>loadGame(id)',made['id'])
                        navigation_locator(page,'#battle-report-open').click()
                        page.wait_for_timeout(500)
                        assert not page.evaluate('CombatReplay.diagnostics().active')
                        assert not any('/extension-assets/official.monster-bloodlines/' in u for _,u in requests)
                    assert not errors,errors
                    result.update(status='passed',errors=errors,disabled_fallback=True)
                    browser.close()
            finally:http.shutdown();http.server_close()
    (out/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
