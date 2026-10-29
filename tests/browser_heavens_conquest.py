"""Real mandate, local deployment, personal map travel, battle and vassal treaty."""
import json
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.system.heavens.outpost_runtime import get
from cultivation_life.system.heavens.outpost_conquest import current, wars
from cultivation_life.system.economy import organizations
from cultivation_life.rules import max_hp,max_mp
from test_heavens_outposts import frontier,quiet,act,dispatch,wait,load
from scripts.browser_navigation import navigation_locator,set_theme


def main():
    output=ROOT/'build/heavens-conquest-browser';output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        bundle=quiet(frontier.__wrapped__(Path(folder)));engine,key,_=bundle
        game=load(bundle)
        game.player.realm_index,game.player.layer=5,5
        game.player.hp,game.player.mp=max_hp(game.player),max_mp(game.player)
        for npc in game.sects['tianjian'].npcs:
            npc.realm_index,npc.layer=5,5
        engine.store.save(game)
        act(bundle,'outpost_authorize');dispatch(bundle);dispatch(bundle);wait(bundle,16)
        act(bundle,'outpost_depart');wait(bundle,10)
        game=load(bundle)
        enemy=next(s for s in game.sects.values() if s.world=='demon' and s.kind=='sect' and s.npcs)
        site=next(loc for loc,_ in engine.maps._graphs['demon']['red_marrow_city'] if not engine.maps.location('demon',loc).get('min_realm_index',0))
        enemy.location_id=site
        for npc in enemy.npcs:
            npc.location_id='red_marrow_city';npc.realm_index=1;npc.layer=1;npc.lifespan=99999;npc.next_tribulation_age=999999
        enemy.npcs[0].location_id=site
        organizations.register(game,'sect',enemy.id,'demon')
        game.intrigue_state['factions']['sect:'+enemy.id]['resources']=100000
        engine.store.save(game);act(bundle,'outpost_return')
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch(headless=True)
                    page=browser.new_page(viewport={'width':1440,'height':1000})
                    page.set_default_timeout(90000)
                    errors,commands=[],[]
                    page.on('pageerror',lambda e:errors.append(str(e)))
                    page.on('request',lambda r:commands.append(r.post_data_json) if r.method=='POST' and r.url.endswith('/heavens-command') else None)
                    page.on('dialog',lambda d:d.accept())
                    page.goto(f'http://127.0.0.1:{http.server_port}')
                    page.wait_for_function('window.GameThemes && configData')
                    page.evaluate('''async id=>{await loadGame(id);await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));}''',key)
                    navigation_locator(page,'[data-panel-target=heavens]').click()
                    page.get_by_role('tab',name='诸界',exact=True).click()
                    page.get_by_role('button',name='查看跨界开拓',exact=True).click()
                    page.get_by_role('button',name='查看天剑宗·异界分驻地',exact=True).click()

                    def command(action,stale=False):
                        label='选择征战事务' if action in {'outpost_military_authorize','outpost_war_start','outpost_war_fight','outpost_war_vassal','outpost_war_stop','outpost_war_settle'} else '选择经营事务' if action in {'outpost_develop','outpost_invest'} else '选择开拓事务'
                        page.get_by_label(label,exact=True).select_option(action)
                        seq=page.evaluate('game.heavens.next_command_seq')
                        page.locator(f'[data-heavens-action={action}]').click()
                        page.locator('#game-confirm-backdrop:not(.hidden)').wait_for()
                        if stale:
                            g=engine.store.load(key)
                            engine.heavens_command(key,g.heavens_state['command_seq']+1,g.heavens_state['revision'],'configure',None,{'watch':False})
                        with page.expect_response(lambda r:r.url.endswith('/heavens-command')) as response:
                            page.locator('#game-confirm-accept').click()
                        if not stale and response.value.status!=200:
                            page.screenshot(path=str(output/'failure.png'))
                            (output/'failure-save.json').write_text(json.dumps(engine.store.load(key).to_dict(),ensure_ascii=False),encoding='utf-8')
                            raise AssertionError(response.value.text())
                        page.wait_for_function('seq=>!busy && game.heavens.next_command_seq>=seq+1',arg=seq)

                    page.get_by_role('tab',name='征战与归附',exact=True).click()
                    command('outpost_military_authorize',True)
                    assert not get(engine.store.load(key),'outpost:tianjian').get('military')
                    assert len([c for c in commands if c['action']=='outpost_military_authorize'])==1
                    command('outpost_military_authorize')
                    page.get_by_role('tab',name='授权与往返',exact=True).click();command('outpost_depart')
                    page.get_by_role('tab',name='地方经营',exact=True).click();command('outpost_develop');command('outpost_invest');command('outpost_invest')
                    page.get_by_role('tab',name='征战与归附',exact=True).click()
                    page.get_by_label('选择征战事务',exact=True).select_option('outpost_war_start')
                    page.get_by_label('征战目标',exact=True).select_option(enemy.id)
                    command('outpost_war_start')
                    g=engine.store.load(key);row=get(g,'outpost:tianjian');war=current(g,row)
                    worker=war['roster']['attacker'][0]
                    assert g.world_npcs[worker].location_id=='red_marrow_city'
                    page.get_by_label('选择征战事务',exact=True).select_option('outpost_war_fight')
                    assert page.locator('[data-heavens-action=outpost_war_fight]').is_disabled()

                    def travel(destination):
                        page.locator('#heavens-toggle').click()
                        navigation_locator(page,'[data-panel-target=map]').click()
                        page.locator('#map-view-tabs button',has_text='地域地图').click()
                        with page.expect_response(lambda r:r.url.endswith('/map-travel')) as response:
                            page.locator(f'#map-locations .map-travel[data-destination="{destination}"]').click()
                        assert response.value.status==200,response.value.text()
                        page.wait_for_function('loc=>!busy && game.map.current===loc',arg=destination)
                        page.locator('#map-toggle').click()
                        navigation_locator(page,'[data-panel-target=heavens]').click()

                    travel(site)
                    page.get_by_role('tab',name='征战与归附',exact=True).click()
                    command('outpost_war_fight')
                    g=engine.store.load(key);row=get(g,'outpost:tianjian')
                    assert current(g,row)['frontier']['player_last_year']==g.player.age
                    assert current(g,row)['battles']>=1 and g.last_combat_report
                    if page.locator('#battle-report-card').is_visible():
                        page.locator('#battle-report-card').get_by_role('button',name='关闭',exact=True).click()
                    assert page.locator('[data-heavens-action=outpost_war_fight]').is_disabled()
                    travel('red_marrow_city')
                    page.get_by_role('tab',name='授权与往返',exact=True).click()
                    for _ in range(130):
                        g=engine.store.load(key);row=get(g,'outpost:tianjian');war=current(g,row)
                        if war and war['status']=='peace_ready' and war.get('winner')=='attacker' and war['war_score']>=55:break
                        if war is None:raise AssertionError('Original campaign ended without an attacker victory')
                        command('outpost_wait')
                    else:raise AssertionError('Original military failed to produce a real vassalization victory')
                    page.get_by_role('tab',name='征战与归附',exact=True).click()
                    for theme in 'abdf':
                        set_theme(page,theme)
                        for width,height in ((1440,1000),(412,915),(915,412)):
                            page.set_viewport_size({'width':width,'height':height})
                            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                            page.screenshot(path=str(output/f'{theme}-{width}.png'))
                    page.set_viewport_size({'width':1440,'height':1000})
                    command('outpost_war_vassal')
                    page.get_by_role('tab',name='授权与往返',exact=True).click()
                    for _ in range(80):
                        g=engine.store.load(key);row=get(g,'outpost:tianjian')
                        if current(g,row) is None:break
                        command('outpost_wait')
                    else:raise AssertionError('Original military failed to return')
                    from cultivation_life.world_state import race_pair
                    g=engine.store.load(key);row=get(g,'outpost:tianjian')
                    assert g.sect_relations[race_pair('tianjian',enemy.id)]['overlord']=='tianjian'
                    assert g.world_npcs[worker].location_id=='red_marrow_city' and g.sects['tianjian'].world=='human'
                    assert wars(g,row)[-1]['logistics']['refunded']
                    assert not errors,errors
                    report=dict(commands=len(commands),original_worker=worker,enemy=enemy.id,real_map_round_trip=True,
                                personal_battle=True,vassal=True,returned=True,themes=4,sizes=3,page_errors=errors)
                    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
                    print(json.dumps(report,ensure_ascii=False));browser.close()
            except Exception:
                if 'page' in locals():
                    try:
                        page.screenshot(path=str(output/'failure.png'))
                        (output/'failure.html').write_text(page.content(),encoding='utf-8')
                    except Exception:
                        pass
                raise
            finally:http.shutdown();http.server_close()


if __name__=='__main__':main()
