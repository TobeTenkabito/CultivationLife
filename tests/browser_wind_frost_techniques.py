"""Real activation and paid battle replay in both themes and three widths."""
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
from cultivation_life.rules import max_hp,max_mp
from cultivation_life.ui_preferences import write_ui_preferences
from test_technique_secrets import prepare
from browser_technique_secrets import open_art
from scripts.browser_navigation import navigation_locator,click_control,set_theme


def main():
    out=ROOT/'build/wind-frost-browser';out.mkdir(parents=True,exist_ok=True)
    checks=[]
    with tempfile.TemporaryDirectory() as folder:
        folder=Path(folder);e=GameEngine(ROOT,folder/'saves');write_ui_preferences(folder,{'pixel_art':True})
        original=e.store.load(e.create_game('风岚霜剑','supreme_water','dao',14731,preset_id='core')['id'])
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',e),patch.object(server,'PERSISTENCE_ROOT',folder):
            http=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    try:
                        for theme in ('light','dark'):
                            for identity,kind in [('manual_demon_dance','wind'),('manual_frost_sky','frost')]:
                                g=prepare(e,original,identity)
                                page=browser.new_page(viewport=dict(width=1440,height=1000),reduced_motion='reduce')
                                errors=[];page.on('pageerror',lambda err:errors.append(str(err)))
                                page.goto(f'http://127.0.0.1:{http.server_port}');page.wait_for_function('!!configData')
                                page.evaluate('id=>loadGame(id)',g.id);page.evaluate('GameThemes.ready');set_theme(page,theme)
                                open_art(page,identity)
                                with page.expect_response(lambda r:r.url.endswith('/secret-art')) as response:
                                    click_control(page.get_by_role('button',name='施展秘术' if kind=='wind' else '激活秘术',exact=True))
                                assert response.value.status==200
                                page.wait_for_function('!busy')
                                before=e.store._path(g.id).read_bytes()
                                repeat=page.request.post(response.value.url,data=response.value.request.post_data_json)
                                assert repeat.status==400 and e.store._path(g.id).read_bytes()==before
                                g=e.store.load(g.id)
                                if kind=='wind':assert len(g.player.puppets)==2
                                g.player.duel_technique_ids=[g.player.combat_techniques[0].id]
                                g.player.hp=max_hp(g.player);g.player.mp=max_mp(g.player)
                                power=e._player_battle_power(g)
                                target=dict(target_name='风霜演武',target_power=power,target_realm_index=g.player.realm_index,
                                    combat_type='cultivator',max_rounds=6,natural_terrain='开阔',members=[dict(npc_id='wind-frost-foe',
                                    name='试招修士',power=power,realm_index=g.player.realm_index,path='dao',gender='male',kind='cultivator')])
                                e._combat(g,target,False,random.Random(151));e.store.save(g)
                                page.keyboard.press('Escape');page.evaluate('id=>loadGame(id)',g.id)
                                navigation_locator(page,'#battle-report-open').click()
                                page.wait_for_function('CombatReplay.diagnostics().active && !document.querySelector("[data-combat-replay]").disabled')
                                beat=page.evaluate('''async kind=>{
                                  const A=await(await fetch('/assets/pixel/combat/manifest.json')).json();
                                  const library=await PixelLibrary.ensure();
                                  const ids=new Set(Object.values(game.last_combat_report.visual.teams).flat().map(m=>m.asset));
                                  for(const def of Object.values(library.assets).filter(a=>a.combat_actors?.some(id=>ids.has(id)))){
                                    const extra=await(await fetch(def.file)).json();Object.assign(A.actors,extra.actors);Object.assign(A.actions,extra.actions);
                                  }
                                  const p=CombatReplay.build(game.last_combat_report,A);
                                  const r=p.rounds.find(r=>r.side==='hero'&&r.techniqueFx.includes(kind));
                                  if(!r)throw Error('No paid authored visual');
                                  for(const row of game.last_combat_report.rounds){
                                    const real=TechniqueFx.paid(row,'player');
                                    const unpaid=structuredClone(row);if(unpaid.voisinage?.technique_effects)unpaid.voisinage.technique_effects.events=[];
                                    if(TechniqueFx.paid(unpaid,'player').length)throw Error('Unpaid visual');
                                    if(real.length>2)throw Error('Unbounded effect list');
                                  }
                                  return r.start+.9;
                                }''',kind)
                                before=e.store._path(g.id).read_bytes()
                                for width,height in [(1440,1000),(390,844),(320,740)]:
                                    page.set_viewport_size(dict(width=width,height=height));page.wait_for_timeout(100)
                                    page.evaluate('t=>CombatReplay.seek(t)',beat)
                                    changed=page.evaluate('''t=>{
                                      const canvas=document.querySelector('#battle-animation canvas'),ctx=canvas.getContext('2d');
                                      const pixels=()=>ctx.getImageData(0,0,canvas.width,canvas.height).data;
                                      const draw=TechniqueFx.draw,withEffect=pixels();let withoutEffect;
                                      try{TechniqueFx.draw=()=>{};CombatReplay.seek(t);withoutEffect=pixels();}
                                      finally{TechniqueFx.draw=draw;CombatReplay.seek(t);}
                                      let changed=0;for(let i=0;i<withEffect.length;i+=4){
                                        if(withEffect[i]!==withoutEffect[i]||withEffect[i+1]!==withoutEffect[i+1]||withEffect[i+2]!==withoutEffect[i+2])changed++;
                                      }
                                      return changed;
                                    }''',beat)
                                    assert changed>10,(kind,width,changed)
                                    assert page.locator('#battle-report-card').evaluate('n=>n.scrollWidth<=n.clientWidth+1')
                                    page.locator('#battle-animation canvas').screenshot(path=str(out/f'{kind}-{theme}-{width}.png'))
                                assert not errors,errors
                                page.keyboard.press('Escape')
                                assert page.evaluate('CombatReplay.diagnostics().cache===0')
                                assert e.store._path(g.id).read_bytes()==before
                                checks.append(dict(theme=theme,kind=kind,widths=[1440,390,320],paid_visual=True,readonly=True))
                                page.close()
                    finally:browser.close()
            finally:http.shutdown();http.server_close()
    (out/'checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Wind/frost browser passed: real activation, duplicate rejection, paid visuals, two themes, three widths, readonly/disposal')


if __name__=='__main__':main()
