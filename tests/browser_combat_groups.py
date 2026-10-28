"""Real multi-unit settlement -> browser CG, without replay writes or fake HP."""
import hashlib
import json
import random
import statistics
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.ui_preferences import write_ui_preferences
from scripts.browser_navigation import navigation_locator


def fixture(engine, case, *, terrain='开阔', conditions=None, enemy_scale=1):
    identity = engine.create_game('群战验收', 'heavenly', 'dao', 772, preset_id='core', gender='female')['id']
    game = engine.store.load(identity)
    game.pending_event = None
    game.settings.update(silent_events=True, combat_popup=True)
    power = engine._player_battle_power(game)
    own = []
    if case == 'corpses':
        own = [('corpse', 'male'), ('corpse', 'female')]
    elif case == 'mechanical-living':
        own = [('mechanical', None), ('living', 'female')]
    elif case in ('companions-beasts', 'demonic-duplicates', 'three-one'):
        people = list(game.world_npcs.values())[:2]
        for i, npc in enumerate(people):
            npc.gender = 'male' if case == 'demonic-duplicates' else ('male', 'female')[i]
            npc.path = 'demonic' if case == 'demonic-duplicates' else 'dao'
            npc.world = game.player.world
            game.player.party.append(dict(id=npc.id))
    elif case == 'display-cap':
        own = [('mechanical', None)] * 5
    for i, (kind, sex) in enumerate(own):
        game.player.puppets.append(dict(id=f'support-{i}', name=f'随行{i+1}', type=kind, gender=sex,
            combat_power=power*.23, realm_index=game.player.realm_index, alive=True,
            durability=100, corpse_integrity=100, control=100, path='dao'))
    total = sum(row.power * row.integrity for row in engine._player_combat_units(game))
    members = [dict(npc_id=f'group-foe-{i}', name=f'敌阵{i+1}', power=total*enemy_scale/3,
                    realm_index=game.player.realm_index, kind='cultivator', path='dao', gender=('male','female','male')[i])
               for i in range(1 if case in ('three-one','one-one') else 3)]
    if case == 'companions-beasts':
        for row, name in zip(members, ('青翎灵鹫', '裂岩妖狼', '碧甲刀螳')):
            row.update(kind='beast', name=name)
    if case == 'demonic-duplicates':
        for row in members:
            row.update(path='demonic', gender='male')
    target = dict(target_name='联合演武', target_power=total*.95*enemy_scale, target_realm_index=game.player.realm_index,
                  combat_type='cultivator', members=members, max_rounds=3,
                  natural_terrain=terrain, artificial_conditions=conditions or [])
    engine._combat(game, target, False, random.Random(151))
    engine.store.save(game)
    return identity


def main():
    out = ROOT/'build/combat-replay/groups'
    out.mkdir(parents=True, exist_ok=True)
    checks, terrains, timings = [], [], []
    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        engine = GameEngine(ROOT, directory/'saves')
        write_ui_preferences(directory, {'pixel_art': True})
        class Handler(server.Handler):
            def log_message(self, *args):
                pass
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', directory):
            http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            threading.Thread(target=http.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch()
                    page = browser.new_page(viewport=dict(width=1440, height=1080), reduced_motion='reduce')
                    errors, requests = [], []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.on('request', lambda request: requests.append((request.method, request.url)))
                    page.goto(f'http://127.0.0.1:{http.server_port}')
                    page.wait_for_function('!!window.CombatReplay && !!configData')
                    page.evaluate('GameThemes.ready')
                    for case in ('corpses', 'mechanical-living', 'companions-beasts', 'demonic-duplicates', 'display-cap', 'one-three', 'three-one'):
                        identity = fixture(engine, case)
                        page.evaluate('id=>loadGame(id)', identity)
                        navigation_locator(page, '#battle-report-open').click()
                        page.wait_for_function('CombatReplay.diagnostics().active && !document.querySelector("[data-combat-replay]").disabled')
                        before = engine.store._path(identity).read_bytes()
                        state = page.evaluate('CombatReplay.diagnostics()')
                        assert len(state['participants']) == (4 if case in ('one-three', 'three-one') else 6)
                        assert state['cache'] <= 36 and state['decodedBytes'] < 96*1024*1024
                        assert page.evaluate('''async()=>{
                          const A=await(await fetch('/assets/pixel/combat/manifest.json')).json();Object.assign(A.actors,(await(await fetch('/assets/pixel/hunt-beasts/manifest.json')).json()).actors);const r=game.last_combat_report;
                          const p=CombatReplay.build(r,A),sample=CombatReplay.sample;
                          for(const row of r.rounds){
                            const beats=p.rounds.filter(b=>b.number===row.round);
                            const expected=(row.ordinary_exchange.actors.player?p.teams.hero.length:0)+(row.ordinary_exchange.actors.enemy?p.teams.npc.length:0);
                            if(beats.length!==expected)return false;
                            for(const side of ['hero','npc']){
                              const turns=beats.filter(b=>b.side===side);if(!turns.length)continue;
                              const target=side==='hero'?'npc':'hero',i=target==='hero'?0:1;
                              if(Math.abs(sample(p,turns.at(-1).contacts.at(-1)+.001).health[target]-row.ordinary_exchange.after[i])>.01)return false;
                            }
                          }
                          const used=new Set();
                          for(const side of ['hero','npc'])for(const m of p.teams[side]){
                            const asset=A.actors[m.asset];if(m.gender&&asset.sex&&m.gender!==asset.sex)return false;used.add(m.asset);
                          }
                          if(p.defeat){
                            const last=p.finisher??p.rounds.at(-1);
                            if(last.side===p.defeat.side)return false;
                            if(Math.abs(p.defeat.start-last.contacts.at(-1)-.2)>.0001)return false;
                          }
                          return true;
                        }''')
                        if case == 'demonic-duplicates':
                            assets = page.evaluate('Object.values(game.last_combat_report.visual.teams).flat().filter(m=>m.kind!=="player").map(m=>m.asset)')
                            assert len(set(assets)) == 3 and all(a.startswith('demonic-') and a.endswith('-m') for a in assets)
                        # Seek each actual actor's attack contact and a guard response.
                        beats = page.evaluate('''async()=>{
                          const A=await(await fetch('/assets/pixel/combat/manifest.json')).json();Object.assign(A.actors,(await(await fetch('/assets/pixel/hunt-beasts/manifest.json')).json()).actors);
                          return CombatReplay.build(game.last_combat_report,A).rounds.slice(0,6).map(b=>b.contacts[0]+.04);
                        }''')
                        requests.clear()
                        for width, height in ((1440,1080), (800,900), (390,844), (320,740)):
                            page.set_viewport_size(dict(width=width,height=height))
                            page.wait_for_timeout(90)
                            for at in [0, *beats, state['duration']]:
                                page.evaluate('at=>CombatReplay.seek(at)', at)
                                current = page.evaluate('CombatReplay.diagnostics()')
                                for member in current['participants']:
                                    x,y,right,bottom = member['bounds']
                                    assert x>=0 and y>=0 and right<=current['viewport'][0]+1 and bottom<=current['viewport'][1]+1, (case,width,member,current['viewport'])
                            assert page.locator('#battle-report-card').evaluate('n=>n.scrollWidth<=n.clientWidth+1')
                            page.evaluate('at=>CombatReplay.seek(at)', beats[min(1,len(beats)-1)])
                            page.locator('#battle-animation canvas').screenshot(path=str(out/f'{case}-{width}.png'))
                        timings += current['renderMs']
                        page.evaluate('CombatReplay.seek(10000)')
                        for side, key in [('hero','player'),('npc','enemy')]:
                            assert page.locator(f'[data-combat-meter={side}] progress').evaluate('n=>n.value') == page.evaluate(f'game.last_combat_report.{key}_combat_state')
                        page.locator('[data-combat-replay]').click()
                        page.wait_for_timeout(120)
                        page.keyboard.press('Escape')
                        assert page.evaluate('!CombatReplay.diagnostics().active && !CombatReplay.diagnostics().raf && CombatReplay.diagnostics().cache===0')
                        assert engine.store._path(identity).read_bytes() == before
                        assert not any('/api/' in url for _,url in requests)
                        checks.append(dict(case=case, members=len(state['participants']), decoded_bytes=state['decodedBytes'], images=state['cache']))
                        page.set_viewport_size(dict(width=1440,height=1080))
                    # Real losses expose all five support down endpoints, not
                    # only the enemy's down pose in an otherwise winning fight.
                    for case in ('corpses','mechanical-living','companions-beasts'):
                        identity=fixture(engine,case,enemy_scale=20)
                        page.evaluate('id=>loadGame(id)',identity)
                        navigation_locator(page,'#battle-report-open').click()
                        page.wait_for_function('CombatReplay.diagnostics().active && !document.querySelector("[data-combat-replay]").disabled')
                        before=engine.store._path(identity).read_bytes()
                        state=page.evaluate('CombatReplay.diagnostics()')
                        assert state['defeat'] and state['defeat']['side']=='hero', state
                        times=page.evaluate('''async()=>{
                          const A=await(await fetch('/assets/pixel/combat/manifest.json')).json();Object.assign(A.actors,(await(await fetch('/assets/pixel/hunt-beasts/manifest.json')).json()).actors);const p=CombatReplay.build(game.last_combat_report,A);
                          const beat=p.finisher??p.rounds.at(-1);
                          if(beat.side!=='npc')throw Error('Allies fall after their own attack');
                          return [beat.start,beat.contacts.at(-1)+.1,p.defeat.start+.1,p.defeat.start+.6,p.duration];
                        }''')
                        for width,height in ((1440,1080),(320,740)):
                            page.set_viewport_size(dict(width=width,height=height));page.wait_for_timeout(90)
                            for index,at in enumerate(times):
                                page.evaluate('at=>CombatReplay.seek(at)',at)
                                current=page.evaluate('CombatReplay.diagnostics()')
                                assert current['decodedBytes']<96*1024*1024 and current['cache']<=36
                                for member in current['participants']:
                                    x,y,right,bottom=member['bounds']
                                    assert x>=0 and y>=0 and right<=current['viewport'][0]+1 and bottom<=current['viewport'][1]+1
                                    if member['side']=='hero' and index>=2:
                                        assert member['mode']=='defeat'
                                if index in (1,4):
                                    page.locator('#battle-animation canvas').screenshot(path=str(out/f'loss-{case}-{index}-{width}.png'))
                        assert engine.store._path(identity).read_bytes()==before
                        page.keyboard.press('Escape')
                        checks.append(dict(case='loss-'+case,members=len(state['participants']),decoded_bytes=state['decodedBytes'],images=state['cache']))
                        page.set_viewport_size(dict(width=1440,height=1080))
                    for mode in ('single','group'):
                        for terrain,slug in [('开阔','open'),('狭窄','narrow'),('险要','peril')]:
                            conditions = ['大阵','禁空','禁神识'] if (mode,slug)==('group','peril') else []
                            identity = fixture(engine,'one-one' if mode=='single' else 'corpses', terrain=terrain,conditions=conditions)
                            requests.clear()
                            page.evaluate('id=>loadGame(id)',identity)
                            navigation_locator(page,'#battle-report-open').click()
                            page.wait_for_function('CombatReplay.diagnostics().active && !document.querySelector("[data-combat-replay]").disabled')
                            state = page.evaluate('CombatReplay.diagnostics()')
                            assert state['battlefield']['id'] == f'{mode}-{slug}' and state['conditions'] == conditions
                            paths = {url.split('?')[0].rsplit('/',1)[1] for _,url in requests if '/combat/terrain-' in url or '/combat/terrace.png' in url}
                            expected = 'terrace.png' if (mode,slug)==('single','open') else f'terrain-{mode}-{slug}.png'
                            assert paths == {expected}, paths
                            before = engine.store._path(identity).read_bytes()
                            for width,height in ((1440,1080),(390,844),(320,740)):
                                page.set_viewport_size(dict(width=width,height=height));page.wait_for_timeout(90)
                                page.evaluate('CombatReplay.seek(0)')
                                page.locator('#battle-animation canvas').screenshot(path=str(out/f'terrain-{mode}-{slug}-{width}.png'))
                                assert page.locator('#battle-animation').evaluate('n=>n.scrollWidth<=n.clientWidth+1')
                            assert engine.store._path(identity).read_bytes() == before
                            terrains.append(dict(mode=mode,terrain=terrain,file=expected,conditions=conditions))
                            page.keyboard.press('Escape')
                            page.set_viewport_size(dict(width=1440,height=1080))
                    assert page.evaluate('''async()=>{
                      const A=await(await fetch('/assets/pixel/combat/manifest.json')).json();Object.assign(A.actors,(await(await fetch('/assets/pixel/hunt-beasts/manifest.json')).json()).actors);
                      const report=structuredClone(game.last_combat_report);report.natural_terrain='未登记地形';
                      return CombatReplay.build(report,A).battlefield===null;
                    }''')
                    assert not errors, errors
                    browser.close()
            finally:
                http.shutdown()
                http.server_close()
    files = ['web/combat-replay.js','web/combat-renderer.js','web/combat-beasts.js','web/combat-replay.css',
             'web/index.html','cultivation_life/combat_visuals.py','cultivation_life/visual_selection.py',
             'scripts/prepare_combat_assets.py','scripts/combat_asset_scale.json','web/assets/pixel/combat/manifest.json']
    result = dict(status='passed', checks=checks, terrains=terrains, render_median_ms=statistics.median(timings),
        render_p95_ms=sorted(timings)[int(len(timings)*.95)], errors=errors,
        source_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in files})
    (out/'checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__ == '__main__':
    main()
