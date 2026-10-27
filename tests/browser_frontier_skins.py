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


def main():
    out = ROOT / 'build/frontier-ui'
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
                    page.on('pageerror', lambda e: errors.append(str(e)))
                    page.goto(base)
                    page.wait_for_function('!!configData&&!busy')
                    page.locator('#theme-open').click()
                    page.locator('#theme-dialog [data-pixel-setting]').set_checked(True)
                    page.evaluate('GameThemes.saved')
                    page.locator('[data-close-dialog=theme-dialog]').click()
                    for style, gender, path in [('frontier', 'female', 'dao'), ('frontier', 'male', 'demonic'),
                                                ('swim-integration', 'female', 'monster'), ('swim-integration', 'male', 'ghost')]:
                        rank = 7 if style == 'swim-integration' else 1
                        made = engine.create_game('沧海游衣', 'supreme_metal', 'dao', 327, gender=gender,
                                                  custom_start=dict(world='spirit' if rank==7 else 'human', realm_index=rank))
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
                        effect = 'revolver' if style == 'frontier' else None
                        key = 'actor.cosmetic.' + actor
                        page.locator('.hud-identity').click()
                        page.locator('#character-skins-open').click()
                        if style=='frontier':
                            locked=page.locator(f'[data-skin-id="actor.cosmetic.swim-integration-{gender}"]')
                            assert locked.is_disabled() and '合体期解锁' in locked.inner_text()
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
                        for at in (0, 1.5, 2.1):
                            page.evaluate('at=>CombatReplay.seek(at)', at)
                            info = page.evaluate('CombatReplay.diagnostics()')
                            assert info['actors']['hero']['id'] == actor
                            assert info['decodedBytes'] < 64*1024*1024
                        if effect:
                            page.evaluate("""style=>{
                              const original=SpellEffects;let found=false;
                              window.SpellEffects={...original,draw(s,m,state,helpers){
                                if(m.attacker?.actor.cast_effect===style&&state.round&&
                                   state.time-state.round.contacts[0]>-.1&&state.time-state.round.contacts[0]<0)found=true;
                                return original.draw(s,m,state,helpers);
                              }};
                              try {
                                for(let t=0;t<CombatReplay.diagnostics().duration&&!found;t+=.025)CombatReplay.seek(t);
                                if(!found)throw Error('Selected costume did not reach live attack renderer');
                              } finally {window.SpellEffects=original;}
                            }""", effect)
                            page.screenshot(path=str(out / f'{actor}-combat.png'))
                            verify_effects(page, effect)
                        page.evaluate('at=>CombatReplay.seek(at)', 10000)
                        page.locator('#battle-report-toggle').click()
                    assert not errors, errors
                    browser.close()
            finally:
                http.shutdown()
                http.server_close()
    result = dict(status='passed', forms=4, real_skin_commands=True, reload=True, integration_rank_gate=True,
                  widths=[1440, 390, 320, 844], real_battle_replays=4)
    (out / 'validation.json').write_text(json.dumps(result, indent=2), encoding='utf8')
    print(json.dumps(result))


def verify_effects(page, style):
    # Actual renderer dispatch and deterministic no-RNG effects, both travel directions.
    result = page.evaluate("""style=>{
      const canvas=()=>Object.assign(document.createElement('canvas'),{width:600,height:360});
      const s={scale:1,width:600,height:360,rear:canvas(),front:canvas(),projectile:canvas()};
      const ctx=c=>c.getContext('2d'), helper={context:ctx,projectClip:(c,m,s,draw)=>draw()};
      const hash=()=>[s.rear,s.front,s.projectile].map(c=>c.toDataURL()).join('|');
      const clear=()=>[s.rear,s.front,s.projectile].forEach(c=>ctx(c).clearRect(0,0,600,360));
      const r={start:0,contacts:[2.1]}, actor={cast_effect:style};
      const original=Math.random;Math.random=()=>{throw Error('Cosmetic consumed RNG');};
      try {
        const samples=[];
        for(const dir of [1,-1]) {
          const m={attacker:{actor,hand:[dir===1?100:500,180],dir},contact:dir===1?500:100,hitY:180};
          for(const time of [2.025,2.075,2.1,2.5,4]) {
            clear();const blank=hash();SpellEffects.draw(s,m,{round:r,time},helper);const first=hash();
            clear();SpellEffects.draw(s,m,{round:r,time},helper);
            if(hash()!==first)throw Error('Nondeterministic effect');
            if(time<3&&first===blank)throw Error('Missing revolver effect');
            if(time===4&&first!==blank)throw Error('Expired particles');
            samples.push(first);
          }
        }
        if(FrontierEffects.draw(s,{attacker:{actor:{faction:'dao'}}},{round:r,time:2.05},helper))throw Error('Default actor overridden');
        return samples.length===10;
      } finally {Math.random=original;}
    }""", style)
    assert result


if __name__ == '__main__':
    main()
