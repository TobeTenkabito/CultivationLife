"""Actual Fengyi reward, wardrobe commands and painted demonic-fan attack."""
import json
import random
import sys
import tempfile
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.models import SectNpc
from scripts.browser_navigation import navigation_locator,set_theme
from browser_historical_skins import capture_preview,verify_painted_effects

KEY='actor.cosmetic.diaochan-female'


def main():
    out=ROOT/'build/diaochan-ui';out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
        e=GameEngine(ROOT,Path(folder)/'saves')
        g=e._load(e.create_game('凤仪','supreme_metal','demonic',329,gender='female',preset_id='demonic_core')['id'])
        g.pending_event=g.active_trial=None;e.store.save(g)
        class Quiet(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',e),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            http=ThreadingHTTPServer(('127.0.0.1',0),Quiet)
            threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    page=browser.new_page(viewport=dict(width=1440,height=960),reduced_motion='reduce')
                    errors=[];page.on('pageerror',lambda error:errors.append(error.stack or str(error)))
                    base=f'http://127.0.0.1:{http.server_port}'
                    page.goto(base);page.wait_for_function('!!configData&&!busy');page.evaluate('GameThemes.ready')
                    page.locator('#theme-open').click();page.locator('#theme-dialog [data-pixel-setting]').check()
                    page.evaluate('GameThemes.saved');page.locator('[data-close-dialog=theme-dialog]').click()
                    page.evaluate('id=>loadGame(id)',g.id)
                    page.locator('.hud-identity').click();page.locator('#character-skins-open').click()
                    button=page.locator(f'[data-skin-id="{KEY}"]')
                    assert button.is_disabled() and '凤仪亭' in button.inner_text()
                    endpoint=base+f'/api/games/{g.id}/character-skin'
                    assert page.request.post(endpoint,data=dict(skin_id=KEY)).status==400
                    page.locator('#character-skins-close').click();page.locator('[data-close-dialog=player-details-dialog]').click()
                    g=e._load(g.id);p=g.player
                    lover=SectNpc('diaochan-lover','道侣','故人',3,1,80,10000,world=p.world,location_id=p.location_id,affinity=80,spirit_root='supreme_metal')
                    owner=SectNpc('diaochan-owner','正主','正主',1,1,50,10000,world=p.world,location_id=p.location_id,affinity=0,spirit_root='supreme_metal')
                    g.notable_npcs.update({lover.id:lover,owner.id:owner});p.dao_companion={'id':lover.id,'since_age':p.age}
                    e._set_concubine_status(g,dict(owner_id=owner.id,owner_name=owner.name,owner_realm_index=1,owner_layer=1,owner_realm_name='练气',owner_world=p.world),forced=True)
                    e.store.save(g);e.contact_action(g.id,lover.id,'promise',owner.id,g.diplomacy_unit)
                    page.evaluate('id=>loadGame(id)',g.id)
                    for theme in ['light','dark']:
                        set_theme(page,theme)
                        page.locator('.hud-identity').click();page.locator('#character-skins-open').click()
                        page.locator(f'[data-skin-id="{KEY}"]').click()
                        page.wait_for_function('key=>!busy&&game.player.visual_actor===key',arg=KEY)
                        for width,height in [(1440,960),(390,844),(844,390)]:
                            page.set_viewport_size(dict(width=width,height=height));button.scroll_into_view_if_needed()
                            assert page.locator('#character-skins').evaluate('n=>n.scrollWidth<=n.clientWidth+2')
                            page.screenshot(path=str(out/f'wardrobe-{theme}-{width}.png'))
                        page.set_viewport_size(dict(width=1440,height=960))
                        page.locator('#character-skins-close').click();page.locator('[data-close-dialog=player-details-dialog]').click()
                    page.reload();page.wait_for_function('!!configData&&!busy');page.evaluate('id=>loadGame(id)',g.id)
                    assert page.evaluate('game.player.visual_actor')==KEY
                    g=e._load(g.id);g.pending_event=None
                    e._combat(g,dict(target_name='裂岩妖狼',combat_type='beast',target_realm_index=1,target_power=e._player_battle_power(g)*2.5),False,random.Random(329))
                    assert g.last_combat_report['visual']['hero']=='diaochan-female';e.store.save(g)
                    page.evaluate('id=>loadGame(id)',g.id);navigation_locator(page,'#battle-report-open').click()
                    page.wait_for_function('CombatReplay.diagnostics().active&&!document.querySelector("[data-combat-replay]").disabled')
                    before=e.store._path(g.id).read_bytes()
                    page.evaluate('''()=>{const old=SpellEffects;let found=false;
                      window.SpellEffects={...old,draw(s,m,state,h){
                        if(m.attacker?.actor.cast_effect==='diaochan_phoenix'&&state.round&&state.time-state.round.contacts[0]>=0&&state.time-state.round.contacts[0]<.22){
                          if(!h.image(HistoricalEffects.sheetFor(m.attacker.actor)))throw Error('Phoenix atlas not decoded');
                          if(!m.attacker.actor.animations[state.round.action].sheet.endsWith('-casting.png'))throw Error('Generic pose used');
                          window.historicalPreviewStart=state.round.start;found=true;
                        }return old.draw(s,m,state,h);}};
                      try{for(let t=0;t<CombatReplay.diagnostics().duration&&!found;t+=.2)CombatReplay.seek(t);if(!found)throw Error('No actual fan attack');}
                      finally{window.SpellEffects=old;}}''')
                    verify_painted_effects(page,'diaochan-female')
                    capture_preview(page,out/'diaochan-attack.webm')
                    for width,height in [(1440,960),(390,844),(844,390)]:
                        page.set_viewport_size(dict(width=width,height=height))
                        page.locator('#battle-animation').scroll_into_view_if_needed()
                        page.evaluate('CombatReplay.seek(historicalPreviewStart+2.25)')
                        assert page.evaluate('CombatReplay.diagnostics().decodedBytes')<96*1024*1024
                        page.screenshot(path=str(out/f'attack-{width}.png'))
                    page.locator('#battle-report-toggle').click();assert page.evaluate('CombatReplay.diagnostics().cache')==0
                    pattern='**/assets/pixel/diaochan/diaochan-fx.png';page.route(pattern,lambda route:route.abort())
                    navigation_locator(page,'#battle-report-open').click()
                    page.wait_for_function('CombatReplay.diagnostics().active&&!document.querySelector("[data-combat-replay]").disabled')
                    page.evaluate('CombatReplay.seek(historicalPreviewStart+2.15)');page.locator('#battle-report-toggle').click();page.unroute(pattern)
                    assert e.store._path(g.id).read_bytes()==before
                    g=e._load(g.id);g.player.path='dao';e.store.save(g)
                    assert page.request.post(endpoint,data=dict(skin_id=KEY)).status==400
                    assert not errors,errors
                    browser.close()
            finally:http.shutdown();http.server_close()
    (out/'validation.json').write_text(json.dumps(dict(status='passed',real_fengyi=True,wardrobe=True,current_path_gate=True,fx_frames=12,painted_cast_poses=6,themes=2,widths=[1440,390,844],readonly=True,fallback=True),indent=2),encoding='utf8')
    print('Diao Chan browser passed: real Fengyi reward, wardrobe, path gate, dedicated fan/phoenix attack, twelve frames, both directions, fallback and disposal')


if __name__=='__main__':main()
