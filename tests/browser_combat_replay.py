"""Real hunting/HTTP reports, replay truth, disposal, legacy/DLC fallback."""
import copy
import hashlib
import json
import random
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
from playwright.sync_api import sync_playwright
from cultivation_life import server, content_registry as registry
from cultivation_life.content_registry import ACTIONS
from cultivation_life.engine import GameEngine
from cultivation_life.rules import add_item
from cultivation_life.combat_visuals import combat_identity
from scripts.browser_navigation import navigation_locator
from fixtures.visual_release import prepare_visual_release


def main():
    output = ROOT/'build/combat-replay'
    output.mkdir(parents=True, exist_ok=True)
    results = dict(hunts=[], widths=[], lifecycle=[], performance={}, defeats=[], mixed=[])
    with tempfile.TemporaryDirectory() as folder:
        engine = GameEngine(ROOT, Path(folder)/'saves')
        class Handler(server.Handler):
            def log_message(self, *args): pass
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', Path(folder)):
            http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            threading.Thread(target=http.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    page = browser.new_page(viewport=dict(width=1440, height=960), reduced_motion='reduce')
                    errors, requests = [], []
                    page.on('pageerror', lambda e: errors.append(str(e)))
                    page.on('request', lambda req: requests.append((req.method, req.url)))
                    page.goto(f'http://127.0.0.1:{http.server_port}')
                    page.wait_for_function('!!configData && !!window.CombatReplay')
                    page.evaluate('GameThemes.ready')

                    def make(path='dao', gender='male'):
                        identity = engine.create_game('演武验收', 'heavenly', path, 941, preset_id='demonic_core' if path=='demonic' else 'core', gender=gender)['id']
                        game = engine.store.load(identity)
                        game.pending_event = None
                        game.settings.update(silent_events=True, combat_popup=True)
                        engine.store.save(game)
                        page.evaluate('id=>loadGame(id)', identity)
                        return identity

                    def pixel(value):
                        page.locator('#theme-open').click()
                        page.locator('#theme-dialog [data-pixel-setting]').set_checked(value)
                        page.evaluate('GameThemes.saved')
                        page.locator('[data-close-dialog=theme-dialog]').click()

                    def check_defeat(side, actor):
                        info=page.evaluate('CombatReplay.diagnostics()')
                        assert info['defeat'] and info['defeat']['side']==side, info
                        assert page.evaluate('''async()=>{
                          const A=await(await fetch('/assets/pixel/combat/manifest.json')).json();
                          const p=CombatReplay.build(game.last_combat_report,A),r=p.finisher??p.rounds.at(-1);
                          if(r.side===p.defeat.side||Math.abs(p.defeat.start-r.contacts.at(-1)-.2)>.0001)return false;
                          if(p.finisher){
                            const health=CombatReplay.sample(p,p.finisher.start).health;
                            for(const t of [...r.contacts,p.defeat.start,p.duration]){
                              const next=CombatReplay.sample(p,t).health;
                              if(next.hero!==health.hero||next.npc!==health.npc)return false;
                            }
                          }
                          return true;
                        }''')
                        snapshots=[]
                        for at in [info['defeat']['start']+.1, info['defeat']['start']+.6, info['duration']]:
                            page.evaluate('at=>CombatReplay.seek(at)',at)
                            state=page.evaluate('CombatReplay.diagnostics()')
                            assert state['actors'][side]['id']==actor and state['actors'][side]['mode']=='defeat'
                            bounds=state['bounds'][side]
                            assert bounds[0]>=0 and bounds[1]>=0 and bounds[2]<=state['viewport'][0] and bounds[3]<=state['viewport'][1], state
                            snapshots.append(page.locator('#battle-animation canvas').evaluate('''c=>{
                              let hash=2166136261;for(const v of c.getContext('2d').getImageData(0,0,c.width,c.height).data)hash=Math.imul(hash^v,16777619);return hash>>>0;
                            }'''))
                        assert len(set(snapshots))>=2, (side,actor)
                        assert state['decodedBytes']<64*1024*1024 and state['cache']<=20
                        results['defeats'].append(dict(side=side,actor=actor,decoded_bytes=state['decodedBytes']))

                    identity = make()
                    assert not any('/pixel/combat/' in url for _,url in requests)
                    pixel(True)
                    for kind, name in [('avian','青翎灵鹫'), ('quadruped','裂岩妖狼'), ('insect','碧甲刀螳')]:
                        if kind != 'avian': identity = make('demonic','female')
                        page.locator('[data-action-tab=combat]').click()
                        with patch.dict(ACTIONS['hunt_beast']['combat'], target_names=[name]):
                            page.locator('[data-action=hunt_beast]').click()
                            page.wait_for_function('!busy && !!game.last_combat_report')
                        page.wait_for_function('CombatReplay.diagnostics().active && !document.querySelector("[data-combat-replay]").disabled')
                        report = page.evaluate('game.last_combat_report')
                        assert report['visual']['enemy'] == kind
                        assert page.evaluate('CombatReplay.diagnostics().rounds') == len(report['rounds'])*2
                        assert page.evaluate('''async()=>{
                          const A=await(await fetch('/assets/pixel/combat/manifest.json')).json(),r=game.last_combat_report;
                          const p=CombatReplay.build(r,A),s=CombatReplay.sample;
                          if(p.rounds[0].side!==(r.rounds[0].initiative==='player'?'hero':'npc'))return false;
                          for(const turn of p.rounds){
                            const row=r.rounds.find(x=>x.round===turn.number),target=turn.side==='hero'?'npc':'hero',i=target==='hero'?0:1;
                            const before=s(p,turn.contacts[0]-.001).health[target],after=s(p,turn.contacts.at(-1)+.001).health[target];
                            if(Math.abs(before-row.ordinary_exchange.before[i])>.01||Math.abs(after-row.ordinary_exchange.after[i])>.01)return false;
                          }return true;
                        }''')
                        original = engine.store._path(identity).read_bytes()
                        game_json = page.evaluate('JSON.stringify(game)')
                        page.evaluate('CombatReplay.seek(10000)')
                        fallen=page.evaluate('CombatReplay.diagnostics().defeat')
                        if fallen:
                            check_defeat(fallen['side'],report['visual']['enemy'] if fallen['side']=='npc' else report['visual']['hero'])
                        assert page.locator('#battle-round-progress>span:not(.complete)').count()==0
                        for side, key in [('hero','player'), ('npc','enemy')]:
                            actual = page.locator(f'[data-combat-meter={side}] progress').evaluate('p=>p.value')
                            assert actual == report['rounds'][-1][f'{key}_combat_state']
                        # Replaying is local: no API calls, reward/time/RNG/save writes.
                        requests.clear()
                        page.locator('[data-combat-replay]').click()
                        page.wait_for_timeout(160)
                        page.locator('[data-combat-pause]').click()
                        assert not any('/api/' in url for _,url in requests)
                        assert engine.store._path(identity).read_bytes() == original
                        assert page.evaluate('JSON.stringify(game)') == game_json
                        stats = page.evaluate('CombatReplay.diagnostics()')
                        assert stats['decodedBytes'] < 64*1024*1024
                        results['hunts'].append(dict(kind=kind, actual_rounds=len(report['rounds']), **stats))
                        for width,height in [(1440,960),(800,600),(390,844),(320,740)]:
                            page.set_viewport_size(dict(width=width,height=height))
                            page.wait_for_timeout(100)
                            page.evaluate('CombatReplay.seek(2.6)')
                            assert page.locator('#battle-report-card').evaluate('n=>n.scrollWidth<=n.clientWidth+1')
                            assert page.locator('#battle-animation').evaluate('n=>n.scrollWidth<=n.clientWidth+1')
                            assert page.locator('#battle-animation canvas').evaluate("c=>new Set(c.getContext('2d').getImageData(0,0,c.width,c.height).data).size>100")
                            page.screenshot(path=str(output/f'{kind}-{width}.png'))
                            results['widths'].append(dict(kind=kind,width=width))
                        page.set_viewport_size(dict(width=1440,height=960))
                        for i in range(5):
                            page.locator('#battle-report-toggle').click()
                            assert page.evaluate('CombatReplay.diagnostics().cache===0 && !CombatReplay.diagnostics().raf')
                            assert page.locator('#battle-animation canvas').evaluate('c=>c.width===0&&c.height===0')
                            navigation_locator(page,'#battle-report-open').click()
                            page.wait_for_function('CombatReplay.diagnostics().active && !document.querySelector("[data-combat-replay]").disabled')
                        results['lifecycle'].append(kind)
                        page.keyboard.press('Escape')
                    # Full real human reports include both initiatives and all supported casts.
                    for path in ['dao','demonic']:
                        for gender in ['male','female']:
                            identity = make(path,gender)
                            game = engine.store.load(identity)
                            assert game.player.path == path and game.player.gender == gender
                            engine._combat(game, dict(target_name='试剑同道', target_power=engine._player_battle_power(game)*.95,
                                target_realm_index=game.player.realm_index, combat_type='cultivator', gender=gender,path=path),False,random.Random(17))
                            engine.store.save(game)
                            page.evaluate('id=>loadGame(id)',identity)
                            navigation_locator(page,'#battle-report-open').click()
                            page.wait_for_function('CombatReplay.diagnostics().active && !document.querySelector("[data-combat-replay]").disabled')
                            page.evaluate('CombatReplay.seek(3)')
                            page.screenshot(path=str(output/f'{path}-{gender}.png'))
                            page.keyboard.press('Escape')
                    # Every NPC variant retains its own appearance when down;
                    # all four protagonist defeat clips run after a real loss.
                    for faction in ('dao','demonic'):
                        for sex in ('male','female'):
                            identity=make(faction,sex)
                            game=engine.store.load(identity)
                            engine._combat(game,dict(target_name='败阵对手',target_power=engine._player_battle_power(game)*20,
                                target_realm_index=game.player.realm_index,combat_type='cultivator',path=faction,gender=sex),faction=='demonic',random.Random(81))
                            engine.store.save(game);page.evaluate('id=>loadGame(id)',identity)
                            navigation_locator(page,'#battle-report-open').click()
                            page.wait_for_function('CombatReplay.diagnostics().active && !document.querySelector("[data-combat-replay]").disabled')
                            check_defeat('hero',f'{faction}-{sex}')
                            page.set_viewport_size(dict(width=320,height=740));page.wait_for_timeout(100)
                            check_defeat('hero',f'{faction}-{sex}')
                            page.screenshot(path=str(output/f'defeat-{faction}-{sex}-320.png'))
                            page.set_viewport_size(dict(width=1440,height=960));page.keyboard.press('Escape')
                            for variant in (1,2,3):
                                identity=make();game=engine.store.load(identity)
                                actor=f'{faction}-{variant}-'+('m' if sex=='male' else 'f')
                                target=dict(combat_type='cultivator',gender=sex,path=faction,target_power=engine._player_battle_power(game)*.05,
                                    target_realm_index=game.player.realm_index)
                                for salt in range(100):
                                    target['target_name']=f'立绘验收{salt}'
                                    if combat_identity(game,target)['enemy']==actor:break
                                assert combat_identity(game,target)['enemy']==actor
                                engine._combat(game,target,False,random.Random(91));engine.store.save(game)
                                page.evaluate('id=>loadGame(id)',identity)
                                navigation_locator(page,'#battle-report-open').click()
                                page.wait_for_function('CombatReplay.diagnostics().active && !document.querySelector("[data-combat-replay]").disabled')
                                check_defeat('npc',actor)
                                page.set_viewport_size(dict(width=320,height=740));page.wait_for_timeout(100)
                                check_defeat('npc',actor)
                                page.screenshot(path=str(output/f'defeat-{actor}-320.png'))
                                page.set_viewport_size(dict(width=1440,height=960));page.keyboard.press('Escape')
                    # Mixed and field-only reports are settled by the real core;
                    # the browser builds attack beats only from ordinary facts.
                    from dataclasses import asdict
                    from test_domain_combat import state as field_state, voisinage
                    from cultivation_life.content_registry import WORLD_SYSTEMS
                    from cultivation_life.models import SectNpc
                    for mode in ('mixed','field-only','field-then-ordinary'):
                        identity=make();game=engine.store.load(identity)
                        game.player.transcendence=field_state(current=200) if mode=='field-then-ordinary' else field_state()
                        npc=SectNpc('mixed-enemy','混合战斗', '',game.player.realm_index,1,100,None,
                                    path='demonic',gender='female',transcendence=field_state() if mode=='mixed' else None)
                        game.notable_npcs[npc.id]=npc
                        definition=voisinage(effect='strike',effect_power=.03) if mode=='field-then-ordinary' else voisinage()
                        with patch.dict(WORLD_SYSTEMS,transcendent_combat=dict(voisinages=[asdict(definition)])):
                            engine._combat(game,dict(npc_id=npc.id,target_name=npc.name,combat_type='cultivator',
                                target_realm_index=npc.realm_index,target_power=engine._player_battle_power(game)),False,random.Random(1))
                        engine.store.save(game);page.evaluate('id=>loadGame(id)',identity)
                        navigation_locator(page,'#battle-report-open').click()
                        report=page.evaluate('game.last_combat_report')
                        if mode!='field-only':
                            page.wait_for_function('CombatReplay.diagnostics().active && !document.querySelector("[data-combat-replay]").disabled')
                            ordinary=[r for r in report['rounds'] if r.get('ordinary_exchange')]
                            assert ordinary and all(r.get('voisinage') for r in ordinary)
                            if mode=='field-then-ordinary':
                                assert report['rounds'][0]['initiative']=='voisinage' and 'ordinary_exchange' not in report['rounds'][0]
                            assert page.evaluate('CombatReplay.diagnostics().rounds')==sum(sum(r['ordinary_exchange']['actors'].values()) for r in ordinary)
                            page.evaluate('CombatReplay.seek(10000)')
                            assert page.locator('[data-combat-meter=hero] progress').evaluate('p=>p.value')==report['player_combat_state']
                        else:
                            assert report['visual']['domains'] and all('ordinary_exchange' not in r for r in report['rounds'])
                            page.wait_for_function('CombatReplay.diagnostics().active && !document.querySelector("[data-combat-replay]").disabled')
                            assert page.evaluate('CombatReplay.diagnostics().rounds') == 0
                            assert page.evaluate('CombatReplay.diagnostics().domainStages.length') > 0
                            page.evaluate('CombatReplay.seek(10000)')
                            assert page.locator('[data-combat-meter=hero] progress').evaluate('p=>p.value') == report['player_combat_state']
                        results['mixed'].append(dict(mode=mode,rounds=len(report['rounds'])))
                        page.keyboard.press('Escape')
                    # Successful endurance trials do not imply that the enemy
                    # was defeated. Pending and field-final results also stay up.
                    page.evaluate('''async()=>{
                      const A=await(await fetch('/assets/pixel/combat/manifest.json')).json();
                      const base=structuredClone(game.last_combat_report);
                      const row={round:1,initiative:'player',ordinary_exchange:{opening:[100,100],before:[100,100],after:[80,80]},player_combat_state:80,enemy_combat_state:80};
                      Object.assign(base,{visual:{schema_version:1,hero:'dao-male',enemy:'dao-1-f'},rounds:[row],player_combat_state_max:100,enemy_combat_state_max:100,player_combat_state:80,enemy_combat_state:80});
                      for(const [outcome,objective] of [['ongoing','kill'],['stalemate','repel'],['victory','survive']]){
                        Object.assign(base,{outcome,objective,result:outcome});if(CombatReplay.build(base,A).defeat)throw Error('False defeat CG');
                      }
                      Object.assign(base,{outcome:'victory',objective:'repel',result:'victory'});
                      base.rounds.push({round:2,initiative:'voisinage',voisinage:{},player_combat_state:80,enemy_combat_state:80});
                      if(CombatReplay.build(base,A).defeat)throw Error('Field defeat animated as ordinary');
                      base.rounds=[...Array(24)].map((_,i)=>({...row,round:i+1}));
                      base.outcome=base.result='ongoing';
                      if(CombatReplay.build(base,A).rounds.length!==48)throw Error('Trial ordinary rounds truncated');
                      row.ordinary_exchange.actors={player:true,enemy:false};base.rounds=[row];
                      if(CombatReplay.build(base,A).rounds.length!==1)throw Error('Invented enemy attack');
                      for(const initiative of ['player','enemy'])for(const outcome of ['victory','defeat']){
                        row.initiative=initiative;row.ordinary_exchange.actors={player:true,enemy:true};
                        Object.assign(base,{rounds:[row],outcome,result:outcome});
                        const p=CombatReplay.build(base,A),winner=outcome==='victory'?'hero':'npc',last=p.finisher??p.rounds.at(-1);
                        if(p.rounds.length!==2||!p.defeat||last.side!==winner)throw Error('Loser collapses after own attack');
                        if(p.rounds[0].side!==(initiative==='player'?'hero':'npc'))throw Error('Initiative changed');
                        if(p.events.length!==2)throw Error('Finisher invented ordinary damage');
                        for(const t of [last.contacts.at(-1)+.001,p.duration]){
                          const s=CombatReplay.sample(p,t);
                          if(s.health.hero!==80||s.health.npc!==80)throw Error('Finisher changed settled state');
                        }
                        const before=CombatReplay.sample(p,p.defeat.start-.01),after=CombatReplay.sample(p,p.defeat.start+.01);
                        if(before.actors[p.defeat.side].mode!=='hit'||after.actors[p.defeat.side].mode!=='defeat')throw Error('Missing hit before collapse');
                      }
                      Object.assign(base,{outcome:'defeat',result:'defeat'});
                      row.ordinary_exchange.actors={player:true,enemy:false};
                      const noWinnerAction=CombatReplay.build(base,A);
                      if(noWinnerAction.finisher||noWinnerAction.defeat||noWinnerAction.rounds.length!==1)throw Error('Unauthorized enemy finishing attack');
                    }''')
                    # Natal icon uses the recorded mold, not the current bag or a placeholder.
                    identity = make('dao','female')
                    prepare_visual_release(engine, identity)
                    game = engine.store.load(identity)
                    engine._combat(game,dict(target_name='御宝同道',target_power=engine._player_battle_power(game)*.95,
                        target_realm_index=game.player.realm_index,combat_type='cultivator',gender='male',path='dao'),False,random.Random(18))
                    engine.store.save(game)
                    page.evaluate('id=>loadGame(id)',identity)
                    navigation_locator(page,'#battle-report-open').click()
                    page.wait_for_function('CombatReplay.diagnostics().active && !document.querySelector("[data-combat-replay]").disabled')
                    assert any('/gear.umbrella.png' in url for _,url in requests)
                    assert page.evaluate('game.last_combat_report.visual.natal_mold_id') == 'umbrella'
                    # The tab background policy freezes visual time without touching the game.
                    page.locator('[data-combat-replay]').click()
                    page.wait_for_timeout(120)
                    page.evaluate("Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'))")
                    t=page.evaluate('CombatReplay.diagnostics().time')
                    page.wait_for_timeout(180)
                    assert page.evaluate('CombatReplay.diagnostics().time') == t
                    assert not page.evaluate('CombatReplay.diagnostics().raf')
                    page.evaluate("delete document.hidden;document.dispatchEvent(new Event('visibilitychange'))")
                    page.wait_for_function('t=>CombatReplay.diagnostics().time>t',arg=t)
                    # OS reduced motion takes effect immediately; no automatic restart.
                    page.emulate_media(reduced_motion='no-preference')
                    page.wait_for_timeout(100)
                    page.emulate_media(reduced_motion='reduce')
                    page.wait_for_function('!CombatReplay.diagnostics().playing')
                    results['performance']['natal']=page.evaluate('CombatReplay.diagnostics()')
                    # Scroll off the actual arena: visual time pauses while reading rounds.
                    page.locator('[data-combat-replay]').click()
                    page.locator('.battle-round-details summary').click()
                    page.locator('#battle-report-card').evaluate('n=>n.scrollTop=n.scrollHeight')
                    page.wait_for_function('!CombatReplay.diagnostics().onscreen')
                    t=page.evaluate('CombatReplay.diagnostics().time')
                    page.wait_for_timeout(150)
                    assert page.evaluate('CombatReplay.diagnostics().time') == t
                    assert not page.evaluate('CombatReplay.diagnostics().raf')
                    page.locator('#battle-report-card').evaluate('n=>n.scrollTop=0')
                    page.wait_for_function('CombatReplay.diagnostics().onscreen')
                    page.wait_for_function('t=>CombatReplay.diagnostics().time>t',arg=t)
                    page.keyboard.press('Escape')
                    # Turning off the optional view unloads the entire combat scene.
                    pixel(False)
                    navigation_locator(page,'#battle-report-open').click()
                    assert page.locator('#battle-animation').is_hidden()
                    assert page.evaluate('CombatReplay.diagnostics().cache===0')
                    page.keyboard.press('Escape')
                    # Real previously bound private natal survives disabling its DLC,
                    # but neither the catalog nor replay may request the private PNG.
                    identity=make()
                    game=engine.store.load(identity)
                    add_item(game.player,'guixu_canghai_equipment_01')
                    engine.store.save(game)
                    engine.natal_artifact_action(identity,'bind','guixu_canghai_equipment_01')
                    game=engine.store.load(identity)
                    engine._combat(game,dict(target_name='旧宝切磋',target_power=engine._player_battle_power(game)*.95,
                        target_realm_index=game.player.realm_index,combat_type='cultivator',gender='female',path='dao'),False,random.Random(27))
                    engine.store.save(game)
                    with patch.object(server,'EXTENSION_REPORT',[]), patch.object(registry,'EXTENSION_REPORT',[]):
                        requests.clear();page.reload();page.wait_for_function('!!configData');page.evaluate('GameThemes.ready')
                        page.evaluate('id=>loadGame(id)',identity);pixel(True)
                        navigation_locator(page,'#battle-report-open').click()
                        page.wait_for_function('CombatReplay.diagnostics().active && !document.querySelector("[data-combat-replay]").disabled')
                        assert not page.evaluate("PixelLibrary.catalog.items.guixu_canghai_equipment_01")
                        assert page.evaluate('DomainFields.catalog.every(style=>!style.owner)')
                        assert not any('/extension-assets/' in url for _,url in requests)
                        original=engine.store._path(identity).read_bytes()
                        # Aborted loading and rapid report changes must not blank the last scene.
                        page.evaluate('''()=>{for(let i=0;i<15;i++){CombatReplay.sync(game.last_combat_report,true);CombatReplay.close();}CombatReplay.sync(game.last_combat_report,true)}''')
                        page.wait_for_function('CombatReplay.diagnostics().active && !document.querySelector("[data-combat-replay]").disabled')
                        assert page.evaluate('CombatReplay.diagnostics().cache<=14')
                        assert engine.store._path(identity).read_bytes()==original
                        # Missing art never prevents closing or reading the text report.
                        page.keyboard.press('Escape')
                        page.route('**/assets/pixel/combat/*-attack.png',lambda route:route.abort())
                        navigation_locator(page,'#battle-report-open').click()
                        page.wait_for_function('document.querySelector("#battle-animation").hidden')
                        assert page.locator('#battle-key-events').is_visible()
                        assert page.evaluate('CombatReplay.diagnostics().cache===0')
                        page.keyboard.press('Escape')
                        page.unroute('**/assets/pixel/combat/*-attack.png')
                    assert not errors, errors
                    browser.close()
            finally:
                http.shutdown(); http.server_close()
    inputs=[*list((ROOT/'web').glob('combat-*.*')),ROOT/'web/app.js',ROOT/'web/index.html',
            ROOT/'web/visual-assets.js',ROOT/'web/assets/pixel/combat/manifest.json',ROOT/'content/world.json',
            ROOT/'cultivation_life/version.py',ROOT/'cultivation_life/combat_visuals.py',ROOT/'cultivation_life/visual_selection.py',
            ROOT/'cultivation_life/system/combat_system.py',ROOT/'cultivation_life/engine/engine_combat_runtime.py',
            ROOT/'cultivation_life/system/combat/trials.py',ROOT/'scripts/prepare_combat_assets.py',ROOT/'scripts/combat_asset_scale.json',
            *list((ROOT/'cultivation_life/engine/progression').glob('*trials.py'))]
    results['source_sha256']={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    results['status']='passed'
    (output/'checks.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(results,ensure_ascii=False))


if __name__=='__main__': main()
