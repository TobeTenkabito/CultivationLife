"""Real two-theme settings, hover navigation, achievement skins and water impact."""
import json
import random
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from cultivation_life import server
from cultivation_life.engine import GameEngine
from playwright.sync_api import sync_playwright
from scripts.browser_navigation import navigation_locator,set_theme
from browser_frontier_skins import verify_effects
from fixtures.tide_release import earn_legend


def main():
    out=ROOT/'build/tide-ui';out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
        engine=GameEngine(ROOT,Path(folder)/'saves')
        class Quiet(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            http=ThreadingHTTPServer(('127.0.0.1',0),Quiet)
            threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch();page=browser.new_page(viewport=dict(width=1440,height=960),reduced_motion='reduce')
                    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    base=f'http://127.0.0.1:{http.server_port}'
                    page.goto(base);page.wait_for_function('!!configData&&!busy')
                    page.locator('#theme-open').click()
                    page.locator('#theme-dialog [data-pixel-setting]').check()
                    page.evaluate('GameThemes.saved')
                    assert page.locator('#theme-dialog [data-theme-choice]:visible').count()==0
                    assert page.locator('#theme-dialog [data-pixel-theme-choice]:visible').count()==2
                    page.locator('#theme-dialog [data-pixel-theme-choice=dark]').click()
                    page.evaluate('GameThemes.saved')
                    page.locator('[data-close-dialog=theme-dialog]').click()
                    for gender in ['female','male']:
                        made=engine.create_game('海潮验收','supreme_metal','dao',323,gender=gender,custom_start=dict(world='human',realm_index=1))
                        game=engine._load(made['id']);game.pending_event=None;engine.store.save(game)
                        page.evaluate('id=>loadGame(id)',game.id);page.wait_for_function('!busy')
                        key=f'actor.cosmetic.swim-tide-{gender}'
                        if gender=='female':
                            page.locator('.hud-identity').click();page.locator('#character-skins-open').click()
                            locked=page.locator(f'[data-skin-id="{key}"]');assert locked.is_disabled() and '传奇故事' in locked.inner_text()
                            reject=page.request.post(base+f'/api/games/{game.id}/character-skin',data=dict(skin_id=key));assert reject.status==400
                            page.locator('#character-skins-close').click();page.locator('[data-close-dialog=player-details-dialog]').click()
                            earn_legend(engine,game.id)
                            page.evaluate('id=>loadGame(id)',game.id);page.wait_for_function('!busy')
                        assert page.evaluate('game.player.realm_index')==1
                        # Only machine preferences change when choosing palettes or dock labels.
                        before=engine.store._path(game.id).read_bytes()
                        for palette in ['light','dark']:
                            set_theme(page,palette)
                            assert page.evaluate('document.documentElement.dataset.pixelTheme')==palette
                            assert page.evaluate('document.documentElement.dataset.theme')=='a'
                            market=page.locator('[data-panel-target=market]')
                            assert market.locator('small').is_hidden()
                            market.hover();assert page.locator('#desktop-dock-tooltip').inner_text()=='坊市'
                            market.focus();assert page.locator('#desktop-dock-tooltip').is_visible()
                            page.screenshot(path=str(out/f'{palette}-desktop.png'))
                        page.locator('#theme-open').click()
                        page.locator('#theme-dialog [data-dock-label-setting]').uncheck();page.evaluate('GameThemes.saved')
                        page.locator('[data-close-dialog=theme-dialog]').click()
                        assert market.locator('small').is_visible()
                        assert engine.store._path(game.id).read_bytes()==before
                        page.reload();page.wait_for_function('!!configData&&!busy');page.evaluate('id=>loadGame(id)',game.id)
                        page.wait_for_function('!busy')
                        assert page.evaluate('GameThemes.preferences.pixel_theme')=='dark'
                        assert not page.evaluate('GameThemes.preferences.compact_docks')
                        page.locator('#theme-open').click();page.locator('#theme-dialog [data-dock-label-setting]').check()
                        page.evaluate('GameThemes.saved');page.locator('[data-close-dialog=theme-dialog]').click()
                        page.locator('.hud-identity').click();page.locator('#character-skins-open').click()
                        page.locator(f'[data-skin-id="{key}"]').click();page.wait_for_function('key=>!busy&&game.player.visual_actor===key',arg=key)
                        for width,height in [(1440,960),(390,844),(844,390),(320,740)]:
                            page.set_viewport_size(dict(width=width,height=height))
                            page.locator(f'[data-skin-id="{key}"]').scroll_into_view_if_needed()
                            assert page.locator('#character-skins').evaluate('n=>n.scrollWidth<=n.clientWidth+2')
                            page.screenshot(path=str(out/f'{gender}-wardrobe-{width}.png'))
                        page.locator('#character-skins-close').click();page.locator('[data-close-dialog=player-details-dialog]').click()
                        battle=engine._load(game.id);battle.pending_event=None
                        engine._combat(battle,dict(target_name='演武灵兽',combat_type='beast',target_realm_index=1,target_power=engine._player_battle_power(battle)*2.5),False,random.Random(323))
                        assert battle.last_combat_report['visual']['hero']==f'swim-tide-{gender}'
                        engine.store.save(battle);page.set_viewport_size(dict(width=1440,height=960))
                        page.evaluate('id=>loadGame(id)',game.id);page.wait_for_function('!busy')
                        navigation_locator(page,'#battle-report-open').click()
                        page.wait_for_function('CombatReplay.diagnostics().active&&!document.querySelector("[data-combat-replay]").disabled')
                        page.evaluate('''()=>{
                          const original=SpellEffects;let found=false;
                          window.SpellEffects={...original,draw(s,m,state,helpers){
                            if(m.attacker?.actor.cast_effect==='tidal_wave'&&state.round&&state.time-state.round.contacts[0]>=0&&state.time-state.round.contacts[0]<.12){
                              const bitmap=helpers.image(TideEffects.sheet);
                              if(!bitmap||bitmap.width!==1536)throw Error('Painted water atlas not decoded in real replay');
                              found=true;
                            }
                            return original.draw(s,m,state,helpers);
                          }};
                          try{for(let t=0;t<CombatReplay.diagnostics().duration&&!found;t+=.04)CombatReplay.seek(t);if(!found)throw Error('No actual tide attack');}
                          finally{window.SpellEffects=original;}
                        }''')
                        page.screenshot(path=str(out/f'{gender}-wave-impact.png'))
                        verify_effects(page,'tidal_wave')
                        verify_painted_frames(page)
                        page.locator('#battle-report-toggle').click()
                    assert not errors,errors
                    browser.close()
            finally:http.shutdown();http.server_close()
    (out/'validation.json').write_text(json.dumps(dict(passed=True,palettes=2,forms=2,achievement_gate=True,low_realm_unlock=True,hover_focus=True,reload=True,actual_water_attacks=True)),encoding='utf-8')
    print('Tide/theme browser passed: two palettes, hover/focus setting, global achievement and low-realm skins, real water attacks')

def verify_painted_frames(page):
    page.evaluate('''async()=>{
      const atlas=await createImageBitmap(await (await fetch(TideEffects.sheet)).blob());
      const canvas=()=>Object.assign(document.createElement('canvas'),{width:700,height:450});
      const s={scale:1,rear:canvas(),front:canvas(),projectile:canvas()};
      const context=c=>c.getContext('2d'),h={context,projectClip:(c,m,s,draw)=>draw(),image:()=>atlas};
      const m={attacker:{actor:{cast_effect:'tidal_wave'},hand:[170,230],dir:1},contact:470,hitY:230};
      const ages=[-1.1,-.97,-.82,-.66,-.58,-.43,-.28,-.13,.02,.12,.22,.32,.42,.56,.7,.84];
      const indices=new Set(),pictures=new Set();
      const draw=age=>{
        for(const c of [s.rear,s.front,s.projectile])context(c).clearRect(0,0,c.width,c.height);
        TideEffects.draw(s,m,{round:{contacts:[2]},time:2+age},h);
        return [s.front,s.projectile].map(c=>c.toDataURL()).join('|');
      };
      try{
        const first=ages.map(age=>{indices.add(TideEffects.sample(age).index);const picture=draw(age);pictures.add(picture);return picture;});
        if(indices.size!==16||pictures.size!==16)throw Error('Water keyframes repeated or skipped');
        for(let i=ages.length-1;i>=0;i--)if(draw(ages[i])!==first[i])throw Error('Reverse seeking changed water animation');
        for(const age of [-2,.95,4])if(TideEffects.sample(age)!==null)throw Error('Water animation escaped lifetime');
        const neutral={...m,attacker:{...m.attacker,actor:{faction:'dao'}}};
        if(TideEffects.draw(s,neutral,{round:{contacts:[2]},time:2},h))throw Error('Water overrides regular attacks');
      }finally{atlas.close();}
    }''')


if __name__=='__main__':main()
