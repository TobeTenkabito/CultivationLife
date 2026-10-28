"""Real wardrobe clicks, reload, rank rejection and settled-battle skin rendering."""
import json
import random
import sys
import tempfile
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cultivation_life import server
from cultivation_life.engine import GameEngine
from playwright.sync_api import sync_playwright
from scripts.browser_navigation import navigation_locator
from browser_historical_skins import capture_preview


def main():
    out = ROOT / 'build/holiday-ui'
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT / 'build') as folder:
        engine = GameEngine(ROOT, Path(folder) / 'saves')
        class Quiet(server.Handler):
            def log_message(self, *args): pass
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', Path(folder)):
            http = ThreadingHTTPServer(('127.0.0.1', 0), Quiet)
            threading.Thread(target=http.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{http.server_port}'
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    page = browser.new_page(viewport=dict(width=1440, height=960), reduced_motion='reduce')
                    errors = []
                    page.on('pageerror', lambda e: errors.append(e.stack or str(e)))
                    page.on('requestfailed', lambda request: print('Request failed:', request.url, request.failure, flush=True))
                    page.goto(base)
                    page.wait_for_function('!!configData&&!busy')
                    page.locator('#theme-open').click()
                    page.locator('#theme-dialog [data-pixel-setting]').set_checked(True)
                    page.evaluate('GameThemes.saved')
                    page.locator('[data-close-dialog=theme-dialog]').click()
                    for style, gender, path in [('christmas', 'female', 'dao'), ('christmas', 'male', 'demonic'),
                                                ('halloween', 'female', 'monster'), ('halloween', 'male', 'ghost')]:
                        rank = 1
                        made = engine.create_game('沧海游衣', 'supreme_metal', 'dao', 327, gender=gender,
                                                  custom_start=dict(world='human', realm_index=rank))
                        game = engine._load(made['id'])
                        # Disposable fixtures exercise nonhuman and optional paths without touching user saves.
                        game.player.path = path
                        game.player.race = 'monster' if path == 'monster' else 'human'
                        game.player.lineage_race = game.player.race
                        game.pending_event = None
                        engine.store.save(game)
                        page.evaluate('id=>loadGame(id)', game.id)
                        page.wait_for_function('!busy')
                        actor = f'{style}-{gender}'
                        effect = 'halloween-bats' if actor == 'halloween-male' else style
                        key = 'actor.cosmetic.' + actor
                        page.locator('.hud-identity').click()
                        page.locator('#character-skins-open').click()
                        page.locator(f'[data-skin-id="{key}"]').click()
                        page.wait_for_function('key=>!busy&&game.player.character_skins.selected===key', arg=key)
                        page.wait_for_function('key=>document.querySelector(".pixel-details-art canvas").dataset.actor===key', arg=key)
                        page.wait_for_function('actor=>{const im=document.querySelector(".pixel-portrait");return im.complete&&im.naturalWidth===128&&im.src.includes(actor+"-portrait.png")}', arg=actor)
                        for width in (1440, 390, 320, 844):
                            page.set_viewport_size(dict(width=width, height=960 if width == 1440 else 844 if width < 400 else 390))
                            page.locator(f'[data-skin-id="{key}"]').scroll_into_view_if_needed()
                            assert page.locator('#character-skins').evaluate('d=>d.scrollWidth<=d.clientWidth+1')
                            page.wait_for_function('Array.from(document.querySelectorAll(".skin-gallery img")).every(im=>im.complete&&im.naturalWidth>0)')
                            page.screenshot(path=str(out / f'{actor}-{width}.png'))
                        page.locator('#character-skins-close').click()
                        page.locator('[data-close-dialog=player-details-dialog]').click()
                        page.reload()
                        page.wait_for_function('!!configData&&!busy')
                        page.evaluate('id=>loadGame(id)', game.id)
                        page.wait_for_function('key=>game.player.visual_actor===key', arg=key)
                        # Play a real settled fight; seek exercises all selected character assets and defeat endpoint.
                        battle = engine._load(game.id)
                        battle.pending_event = None
                        engine._combat(battle, dict(target_name='演武灵兽', combat_type='beast',
                            target_realm_index=rank, target_power=engine._player_battle_power(battle)*2.5),
                            False, random.Random(327))
                        assert battle.last_combat_report['visual']['hero'] == actor
                        engine.store.save(battle)
                        page.set_viewport_size(dict(width=1440, height=960))
                        page.evaluate('id=>loadGame(id)', game.id)
                        navigation_locator(page, '#battle-report-open').click()
                        page.wait_for_function('CombatReplay.diagnostics().active&&!document.querySelector("[data-combat-replay]").disabled')
                        saved_before = engine.store._path(game.id).read_bytes()
                        for at in (0, 1.5, 2.1):
                            page.evaluate('at=>CombatReplay.seek(at)', at)
                            info = page.evaluate('CombatReplay.diagnostics()')
                            assert info['actors']['hero']['id'] == actor
                            assert info['decodedBytes'] < 64*1024*1024
                        page.evaluate("""style=>{
                          const original=SpellEffects;let found=false;
                          window.SpellEffects={...original,draw(s,m,state,helpers){
                            if(m.attacker?.actor.holiday_effect===style&&state.round&&
                               state.time-state.round.contacts[0]>-.5&&state.time-state.round.contacts[0]<-.15){
                              if(style==='christmas'){
                                const image=helpers.image(ChristmasEffects.sheet);
                                if(!image||image.width!==1536||image.height!==1152)throw Error('Painted snow not decoded in real replay');
                                window.historicalPreviewStart=state.round.start;
                              }
                              found=true;
                            }
                            return original.draw(s,m,state,helpers);
                          }};
                          try {
                            for(let t=0;t<CombatReplay.diagnostics().duration&&!found;t+=.1)CombatReplay.seek(t);
                            if(!found)throw Error('Selected costume did not reach live attack renderer');
                          } finally {window.SpellEffects=original;}
                        }""", effect)
                        page.screenshot(path=str(out / f'{actor}-combat.png'))
                        verify_effects(page, effect)
                        if style=='christmas':
                            verify_snow_frames(page)
                            capture_preview(page, out/f'{actor}.webm')
                            for width,height in [(1440,960),(390,844),(844,390)]:
                                page.set_viewport_size(dict(width=width,height=height))
                                page.evaluate('()=>CombatReplay.seek(historicalPreviewStart+2.25)')
                                info=page.evaluate('CombatReplay.diagnostics()')
                                assert all(0<=p['bounds'][0]<p['bounds'][2]<=info['viewport'][0]+1 for p in info['participants'])
                                page.screenshot(path=str(out/f'{actor}-impact-{width}.png'))
                            page.set_viewport_size(dict(width=1440,height=960))
                        page.evaluate('at=>CombatReplay.seek(at)', 10000)
                        page.locator('#battle-report-toggle').click()
                        assert page.evaluate('CombatReplay.diagnostics().cache')==0
                        if style=='christmas':
                            pattern='**/assets/pixel/holiday/christmas-keyframes.png'
                            page.route(pattern,lambda route:route.abort())
                            navigation_locator(page,'#battle-report-open').click()
                            page.wait_for_function('CombatReplay.diagnostics().active&&!document.querySelector("[data-combat-replay]").disabled')
                            page.evaluate('()=>CombatReplay.seek(historicalPreviewStart+2.1)')
                            page.locator('#battle-report-toggle').click()
                            page.unroute(pattern)
                        assert engine.store._path(game.id).read_bytes()==saved_before
                    assert not errors, errors
                    browser.close()
            finally:
                http.shutdown()
                http.server_close()
    result = dict(status='passed', forms=4, real_skin_commands=True, reload=True, no_rank_gate=True,
                  widths=[1440, 390, 320, 844], real_battle_replays=4,
                  painted_snow_frames=16, missing_snow_fallback=True, readonly_replay=True)
    (out / 'validation.json').write_text(json.dumps(result, indent=2), encoding='utf8')
    print(json.dumps(result))


def verify_effects(page, style):
    # Actual renderer dispatch and deterministic no-RNG effects, both travel directions.
    result = page.evaluate("""async style=>{
      const bitmap=style==='christmas'?await createImageBitmap(await (await fetch(ChristmasEffects.sheet)).blob()):null;
      const canvas=()=>Object.assign(document.createElement('canvas'),{width:600,height:360});
      const s={scale:1,width:600,height:360,rear:canvas(),front:canvas(),projectile:canvas()};
      const ctx=c=>c.getContext('2d'), helper={context:ctx,projectClip:(c,m,s,draw)=>draw(),image:()=>bitmap};
      const hash=()=>[s.rear,s.front,s.projectile].map(c=>c.toDataURL()).join('|');
      const clear=()=>[s.rear,s.front,s.projectile].forEach(c=>ctx(c).clearRect(0,0,600,360));
      const r={start:0,contacts:[2.1]}, actor={holiday_effect:style};
      const original=Math.random;Math.random=()=>{throw Error('Cosmetic consumed RNG');};
      try {
        const samples=[];
        for(const dir of [1,-1]) {
          const m={attacker:{actor,hand:[dir===1?100:500,180],dir},contact:dir===1?500:100,hitY:180};
          for(const time of [.4,1.6,2.1,2.5,4]) {
            clear();const blank=hash();SpellEffects.draw(s,m,{round:r,time},helper);const first=hash();
            clear();SpellEffects.draw(s,m,{round:r,time},helper);
            if(hash()!==first)throw Error('Nondeterministic effect');
            if(time<3&&first===blank)throw Error('Missing holiday effect');
            if(time===4&&first!==blank)throw Error('Expired particles');
            samples.push(first);
          }
        }
        if(HolidayEffects.theme({faction:'dao'})!==null)throw Error('Default actor overridden');
        return samples.length===10;
      } finally {Math.random=original;bitmap?.close();}
    }""", style)
    assert result


def verify_snow_frames(page):
    page.evaluate('''async()=>{
      const im=await createImageBitmap(await (await fetch(ChristmasEffects.sheet)).blob());
      const canvas=()=>Object.assign(document.createElement('canvas'),{width:700,height:450});
      const s={scale:1,width:700,height:450,ground:430,rear:canvas(),front:canvas(),projectile:canvas()};
      const context=c=>c.getContext('2d');let clips=0;
      const helpers={context,image:()=>im,projectClip:(c,m,s,draw)=>{clips++;draw();}};
      const clear=()=>[s.rear,s.front,s.projectile].forEach(c=>context(c).clearRect(0,0,700,450));
      const hash=()=>[s.rear,s.front,s.projectile].map(c=>c.toDataURL()).join('|');
      const phases=[[-1.9,-.7],[-.7,0],[0,.45],[.45,1.2]];
      const ages=phases.flatMap(([a,b])=>[0,1,2,3].map(i=>a+(b-a)*(i+.3)/4));
      const random=Math.random;Math.random=()=>{throw Error('Snow consumed RNG');};
      try{
        for(const dir of [1,-1]){
          const m={attacker:{actor:{holiday_effect:'christmas'},hand:[dir===1?160:540,220],dir},contact:dir===1?520:180,hitY:220};
          const draw=age=>{clear();ChristmasEffects.draw(s,m,{round:{contacts:[2.1]},time:2.1+age},helpers);return hash();};
          const first=ages.map(draw);
          if(new Set(first).size!==16||new Set(ages.map(a=>ChristmasEffects.sample(a).index)).size!==16)throw Error('Missing snow keyframes');
          for(let i=15;i>=0;i--)if(draw(ages[i])!==first[i])throw Error('Snow reverse seek differs');
          clear();const blank=hash();
          for(const age of [-2,1.21,4])if(draw(age)!==blank)throw Error('Snow escaped lifetime');
          if(ChristmasEffects.draw(s,m,{round:{contacts:[2.1]},time:2.1},{...helpers,image:()=>null}))throw Error('Snow blocked missing-image fallback');
        }
        if(clips!==16)throw Error('Snow bypasses travel clipping');
        if(ChristmasEffects.sheetFor({holiday_effect:'halloween'})!==undefined)throw Error('Snow applied to Halloween');
      }finally{Math.random=random;im.close();}
    }''')


if __name__ == '__main__':
    main()
