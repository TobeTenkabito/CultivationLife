"""Actual wardrobe submission, reload, two palettes and settled battle playback."""
import base64
import json
import random
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.world_state import race_pair
from playwright.sync_api import sync_playwright
from scripts.browser_navigation import navigation_locator, set_theme
from test_historical_skins import seed_kills, REWARDS


def main():
    out = ROOT / 'build/historical-skins-ui'; out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
        e = GameEngine(ROOT, Path(folder)/'saves')
        g = e._load(e.create_game('风雅', 'supreme_metal', 'ghost', 328, gender='male')['id'])
        g.pending_event = g.active_trial = None
        e.store.save(g)
        class Quiet(server.Handler):
            def log_message(self, *args): pass
        with patch.object(server, 'ENGINE', e), patch.object(server, 'PERSISTENCE_ROOT', Path(folder)):
            http = ThreadingHTTPServer(('127.0.0.1', 0), Quiet)
            threading.Thread(target=http.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    page = browser.new_page(viewport=dict(width=1440, height=960), reduced_motion='reduce')
                    errors = []; page.on('pageerror', lambda error: errors.append(str(error)))
                    base = f'http://127.0.0.1:{http.server_port}'
                    page.goto(base); page.wait_for_function('!!configData&&!busy')
                    page.locator('#theme-open').click()
                    page.locator('#theme-dialog [data-pixel-setting]').check()
                    page.evaluate('GameThemes.saved')
                    page.locator('[data-close-dialog=theme-dialog]').click()
                    page.evaluate('id=>loadGame(id)', g.id); page.wait_for_function('!busy')
                    page.locator('.hud-identity').click(); page.locator('#character-skins-open').click()
                    for skin in REWARDS:
                        key = 'actor.cosmetic.' + skin
                        assert page.locator(f'[data-skin-id="{key}"]').is_disabled()
                        assert page.request.post(base+f'/api/games/{g.id}/character-skin', data=dict(skin_id=key)).status == 400
                    page.locator('#character-skins-close').click()
                    page.locator('[data-close-dialog=player-details-dialog]').click()
                    g = e._load(g.id)
                    seed_kills(e, g, 100)
                    sects = [s for s in g.sects.values() if s.kind == 'sect' and not s.extinct and s.world == g.player.world]
                    own = sects[0]; g.player.faction_id = own.id
                    for other in sects[1:]:
                        g.sect_relations[race_pair(own.id, other.id)] = dict(status='vassal', overlord=own.id, subject=other.id)
                    e.achievements.evaluate(g); e.store.save(g)
                    for skin in REWARDS:
                        key = 'actor.cosmetic.' + skin
                        page.evaluate('id=>loadGame(id)', g.id); page.wait_for_function('!busy')
                        page.locator('.hud-identity').click(); page.locator('#character-skins-open').click()
                        page.locator(f'[data-skin-id="{key}"]').click()
                        page.wait_for_function('key=>!busy&&game.player.visual_actor===key', arg=key)
                        for theme in ['light', 'dark']:
                            # The settings dialog is modal, close wardrobe before opening it.
                            page.locator('#character-skins-close').click()
                            page.locator('[data-close-dialog=player-details-dialog]').click()
                            set_theme(page, theme)
                            page.locator('.hud-identity').click(); page.locator('#character-skins-open').click()
                            for width, height in [(1440,960),(390,844),(844,390)]:
                                page.set_viewport_size(dict(width=width, height=height))
                                page.locator(f'[data-skin-id="{key}"]').scroll_into_view_if_needed()
                                assert page.locator('#character-skins').evaluate('n=>n.scrollWidth<=n.clientWidth+2')
                                page.screenshot(path=str(out/f'{skin}-{theme}-{width}.png'))
                            page.set_viewport_size(dict(width=1440,height=960))
                        page.locator('#character-skins-close').click()
                        page.locator('[data-close-dialog=player-details-dialog]').click()
                        page.reload(); page.wait_for_function('!!configData&&!busy')
                        page.evaluate('id=>loadGame(id)', g.id); page.wait_for_function('!busy')
                        assert page.evaluate('game.player.visual_actor') == key
                        battle = e._load(g.id); battle.pending_event = None
                        e._combat(battle, dict(target_name='演武灵兽', combat_type='beast',
                            target_realm_index=1, target_power=e._player_battle_power(battle)*2.5), False, random.Random(328))
                        assert battle.last_combat_report['visual']['hero'] == skin
                        e.store.save(battle)
                        page.evaluate('id=>loadGame(id)', g.id); page.wait_for_function('!busy')
                        navigation_locator(page, '#battle-report-open').click()
                        page.wait_for_function('CombatReplay.diagnostics().active&&!document.querySelector("[data-combat-replay]").disabled')
                        before = e.store._path(g.id).read_bytes()
                        page.evaluate('''skin=>{
                          const original=SpellEffects; let found=false;
                          window.SpellEffects={...original, draw(s,m,state,h){
                            if(m.attacker?.actor.name.includes(skin==='seimei-male'?'晴明':'信长')&&state.round&&
                               state.time-state.round.contacts[0]>=0&&state.time-state.round.contacts[0]<.22){
                              if(m.attacker.actor.spell_palette?.length!==3)throw Error('Missing costume palette');
                              const image=h.image(HistoricalEffects.sheetFor(m.attacker.actor));
                              if(!image||image.width!==1536)throw Error('Painted effect atlas missing in real replay');
                              if(!m.attacker.actor.animations[state.round.action].sheet.endsWith('-casting.png'))throw Error('Generic casting pose used');
                              window.historicalPreviewStart=state.round.start;
                              found=true;
                            }
                            return original.draw(s,m,state,h);
                          }};
                          try{for(let t=0;t<CombatReplay.diagnostics().duration&&!found;t+=.2)CombatReplay.seek(t);
                            if(!found)throw Error('Costume did not attack in real replay');}
                          finally{window.SpellEffects=original;}
                        }''', skin)
                        page.screenshot(path=str(out/f'{skin}-combat.png'))
                        verify_painted_effects(page, skin)
                        capture_preview(page, out/f'{skin}.webm')
                        for width,height in [(390,844),(844,390)]:
                            page.set_viewport_size(dict(width=width,height=height))
                            page.evaluate('()=>CombatReplay.seek(historicalPreviewStart+2.25)')
                            info=page.evaluate('CombatReplay.diagnostics()')
                            assert info['decodedBytes'] < 96*1024*1024
                            assert all(0<=p['bounds'][0]<p['bounds'][2]<=info['viewport'][0]+1 for p in info['participants'])
                            page.screenshot(path=str(out/f'{skin}-combat-{width}.png'))
                        page.set_viewport_size(dict(width=1440,height=960))
                        assert e.store._path(g.id).read_bytes() == before
                        page.locator('#battle-report-toggle').click()
                        assert page.evaluate('CombatReplay.diagnostics().cache') == 0
                        effect_url=f'**/assets/pixel/historical/{skin.removesuffix("-male")}-fx.png'
                        page.route(effect_url, lambda route: route.abort())
                        navigation_locator(page, '#battle-report-open').click()
                        page.wait_for_function('CombatReplay.diagnostics().active&&!document.querySelector("[data-combat-replay]").disabled')
                        page.evaluate('()=>CombatReplay.seek(historicalPreviewStart+2.1)')
                        page.locator('#battle-report-toggle').click()
                        page.unroute(effect_url)
                        assert e.store._path(g.id).read_bytes() == before
                    assert not errors, errors
                    browser.close()
            finally:
                http.shutdown(); http.server_close()
    (out/'validation.json').write_text(json.dumps(dict(passed=True, skins=2, themes=2,
        viewport_sizes=3, actual_selection=True, replay_readonly=True,
        painted_keyframes=24, two_directions=True, deterministic=True,
        missing_effect_fallback=True, close_releases_cache=True)), encoding='utf-8')
    print('Historical skins browser passed: gates, wardrobe, real painted attacks, 24 VFX frames, both directions and deterministic seeking')


def verify_painted_effects(page, skin):
    page.evaluate('''async skin=>{
      const effect={'nobunaga-male':'nobunaga_command','seimei-male':'seimei_lunar','diaochan-female':'diaochan_phoenix'}[skin];
      if(!effect)throw Error('Unknown painted costume');
      const actor={cast_effect:effect},sheet=HistoricalEffects.sheetFor(actor);
      const im=await createImageBitmap(await (await fetch(sheet)).blob());
      const canvas=()=>Object.assign(document.createElement('canvas'),{width:700,height:450});
      const s={scale:1,width:700,height:450,ground:430,rear:canvas(),front:canvas(),projectile:canvas()};
      const context=c=>c.getContext('2d');let clipped=0;
      const helpers={context,image:()=>im,projectClip:(c,m,s,draw)=>{clipped++;draw();}};
      const clear=()=>[s.rear,s.front,s.projectile].forEach(c=>context(c).clearRect(0,0,700,450));
      const hash=()=>[s.rear,s.front,s.projectile].map(c=>c.toDataURL()).join('|');
      const phases=[[-1.4,-.65],[-.65,0],[0,.42],[.42,1.1]];
      const ages=phases.flatMap(([a,b])=>[0,1,2].map(i=>a+(b-a)*(i+.3)/3));
      const original=Math.random;Math.random=()=>{throw Error('Visuals consumed RNG');};
      try{
        for(const dir of [1,-1]){
          const m={attacker:{actor,hand:[dir===1?160:540,220],dir},contact:dir===1?520:180,hitY:220};
          const draw=age=>{clear();HistoricalEffects.draw(s,m,{round:{contacts:[2.1]},time:2.1+age},helpers);return hash();};
          const first=ages.map(draw);
          if(new Set(first).size!==12||new Set(ages.map(a=>HistoricalEffects.sample(a).index)).size!==12)throw Error('Repeated or skipped VFX frames');
          for(let i=11;i>=0;i--)if(draw(ages[i])!==first[i])throw Error('Reverse seeking changed effects');
          clear();const blank=hash();
          for(const age of [-2,1.1,4])if(draw(age)!==blank||HistoricalEffects.sample(age)!==null)throw Error('Effect escaped its lifetime');
          if(HistoricalEffects.draw(s,m,{round:{contacts:[2.1]},time:2.1},{...helpers,image:()=>null}))throw Error('Missing atlas blocks fallback');
        }
        if(clipped!==12)throw Error('Travelling effects failed to use target clipping');
        if(HistoricalEffects.sheetFor({faction:'dao'})!==undefined)throw Error('Default actor overrides');
      }finally{Math.random=original;im.close();}
    }''', skin)


def capture_preview(page, target):
    encoded = page.evaluate('''async()=>{
      const canvas=document.querySelector('#battle-animation canvas'), stream=canvas.captureStream(20);
      const recorder=new MediaRecorder(stream,{mimeType:'video/webm;codecs=vp9',videoBitsPerSecond:2500000});
      const chunks=[];recorder.ondataavailable=e=>{if(e.data.size)chunks.push(e.data);};
      const done=new Promise(resolve=>{recorder.onstop=()=>{
        stream.getTracks().forEach(t=>t.stop());
        const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);
        reader.readAsDataURL(new Blob(chunks,{type:'video/webm'}));
      };});
      CombatReplay.seek(historicalPreviewStart);recorder.start();
      const started=performance.now(),timer=setInterval(()=>{
        const elapsed=(performance.now()-started)/1000;
        CombatReplay.seek(historicalPreviewStart+Math.min(4.25,elapsed));
        if(elapsed>=4.25){clearInterval(timer);recorder.stop();}
      },50);
      return await done;
    }''')
    target.write_bytes(base64.b64decode(encoded))


if __name__ == '__main__': main()
