"""Real UI permits for all 34 directions and upper-tier local campaigns."""
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
from cultivation_life.engine import GameEngine
from cultivation_life.system.heavens.outpost_runtime import get
from cultivation_life.system.heavens.outpost_conquest import current
from cultivation_life.system.heavens.outpost_routes import ENDPOINTS,peers,target_for,profile
from test_heavens_peer_worlds import origins,bundle_for
from scripts.browser_navigation import navigation_locator,set_theme


def main():
    output=ROOT/'build/heavens-peer-browser';output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        engine=GameEngine(ROOT,Path(folder)/'saves')
        initial=origins.__wrapped__(engine)
        bundles={source:bundle_for(engine,initial,source,peers(source)[0]) for source in initial}
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
                    errors,commands,verified=[],[],[]
                    page.on('pageerror',lambda error:errors.append(str(error)))
                    page.on('request',lambda request:commands.append(request.post_data_json) if request.method=='POST' and request.url.endswith('/heavens-command') else None)
                    page.on('dialog',lambda dialog:dialog.accept())
                    page.goto(f'http://127.0.0.1:{http.server_port}')
                    page.wait_for_function('window.GameThemes && configData')

                    def open_game(key):
                        page.evaluate('''async id=>{await loadGame(id);await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));}''',key)
                        navigation_locator(page,'[data-panel-target=heavens]').click()
                        page.get_by_role('tab',name='诸界',exact=True).click()
                        page.get_by_role('button',name='查看跨界开拓',exact=True).click()

                    def select_project(identity):
                        name=page.evaluate('id=>game.heavens.outposts.find(p=>p.id===id).name',identity)
                        page.get_by_role('button',name='查看'+name,exact=True).click()

                    def command(key,action,stale=False):
                        label='选择征战事务' if action in {'outpost_military_authorize','outpost_war_start','outpost_war_fight','outpost_war_vassal','outpost_war_stop','outpost_war_settle'} else '选择经营事务' if action in {'outpost_develop','outpost_invest'} else '选择开拓事务'
                        page.get_by_label(label,exact=True).select_option(action)
                        seq=page.evaluate('game.heavens.next_command_seq')
                        control=page.locator(f'[data-heavens-action={action}]')
                        if control.is_disabled():
                            page.screenshot(path=str(output/'failure.png'))
                            (output/'failure.html').write_text(page.content(),encoding='utf-8')
                            (output/'failure-save.json').write_text(json.dumps(engine.store.load(key).to_dict(),ensure_ascii=False),encoding='utf-8')
                            raise AssertionError(page.locator('#heavens-detail-body').inner_text())
                        control.click()
                        page.locator('#game-confirm-backdrop:not(.hidden)').wait_for()
                        if stale:
                            game=engine.store.load(key)
                            engine.heavens_command(key,game.heavens_state['command_seq']+1,game.heavens_state['revision'],'configure',None,{'watch':False})
                        with page.expect_response(lambda response:response.url.endswith('/heavens-command')) as response:
                            page.locator('#game-confirm-accept').click()
                        if stale:
                            assert response.value.status!=200
                        else:
                            assert response.value.status==200,response.value.text()
                        page.wait_for_function('seq=>!busy && game.heavens.next_command_seq>=seq+1',arg=seq)

                    # Every source uses its own real save and original organization.
                    # All permits and military mandates are clicked at its real HQ.
                    for source,bundle in bundles.items():
                        key,owner=bundle[1],bundle[4]
                        open_game(key)
                        for destination in peers(source):
                            identity=target_for(owner,source,destination)
                            select_project(identity)
                            page.get_by_role('tab',name='授权与往返',exact=True).click()
                            if source in {'spirit','celestial'} and destination==peers(source)[0]:
                                command(key,'outpost_authorize',True)
                                assert get(engine.store.load(key),identity) is None
                            command(key,'outpost_authorize')
                            page.get_by_role('tab',name='征战与归附',exact=True).click()
                            command(key,'outpost_military_authorize')
                            row=get(engine.store.load(key),identity)
                            assert row['source']==source and row['military']['destination']==destination
                            verified.append([source,destination])
                            page.get_by_role('button',name='‹ 返回开拓目录',exact=True).click()
                        print('permits:',source,flush=True)

                    examples=[]
                    for source in ('spirit','celestial'):
                        bundle=bundles[source];key,identity,owner,enemy=bundle[1],bundle[3],bundle[4],bundle[5]
                        destination=peers(source)[0];terms=profile(source)
                        open_game(key);select_project(identity)
                        page.get_by_role('tab',name='派驻与补给',exact=True).click()
                        command(key,'outpost_dispatch');command(key,'outpost_dispatch')
                        page.get_by_role('tab',name='授权与往返',exact=True).click()
                        for _ in range(16):command(key,'outpost_wait')
                        command(key,'outpost_depart')
                        for _ in range(10):command(key,'outpost_wait')
                        game=engine.store.load(key);row=get(game,identity)
                        assert game.player.world==destination and row['status']=='active'
                        assert row['visit']['return_fare']==8*terms['annual']
                        assert game.sects[owner].world==source
                        untouched={i:json.dumps(r,sort_keys=True) for i,r in game.heavens_state['runtime']['outposts'].items() if i!=identity}
                        page.get_by_role('tab',name='地方经营',exact=True).click()
                        command(key,'outpost_develop')
                        for _ in range(3):command(key,'outpost_invest')
                        page.get_by_role('tab',name='征战与归附',exact=True).click()
                        page.get_by_label('选择征战事务',exact=True).select_option('outpost_war_start')
                        page.get_by_label('征战目标',exact=True).select_option(enemy)
                        command(key,'outpost_war_start')
                        game=engine.store.load(key);war=current(game,get(game,identity))
                        worker=war['roster']['attacker'][0]
                        assert war['logistics']['sides']['attacker']['mobilized']==terms['war_budget']
                        page.get_by_label('选择征战事务',exact=True).select_option('outpost_war_fight')
                        assert page.locator('[data-heavens-action=outpost_war_fight]').is_disabled()
                        page.get_by_role('tab',name='授权与往返',exact=True).click()
                        for _ in range(30):
                            game=engine.store.load(key);war=current(game,get(game,identity))
                            if war['campaign_phase']=='engaged':break
                            command(key,'outpost_wait')
                        else:raise AssertionError('Original upper-tier worker never reached the actual battlefield')
                        assert engine.store.load(key).world_npcs[worker].location_id==war['location_id']
                        page.get_by_role('tab',name='征战与归附',exact=True).click()
                        for theme in 'abdf':
                            set_theme(page,theme)
                            for width,height in ((1440,1000),(412,915),(915,412)):
                                page.set_viewport_size({'width':width,'height':height})
                                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                                page.screenshot(path=str(output/f'{source}-{theme}-{width}.png'))
                        page.set_viewport_size({'width':1440,'height':1000})
                        command(key,'outpost_war_stop')
                        page.get_by_role('tab',name='授权与往返',exact=True).click()
                        for _ in range(30):
                            game=engine.store.load(key)
                            if current(game,get(game,identity)) is None:break
                            command(key,'outpost_wait')
                        else:raise AssertionError('Original upper-tier worker never returned')
                        game=engine.store.load(key)
                        assert game.world_npcs[worker].location_id==ENDPOINTS[destination]
                        assert all(json.dumps(game.heavens_state['runtime']['outposts'][i],sort_keys=True)==record for i,record in untouched.items())
                        command(key,'outpost_return')
                        assert engine.store.load(key).player.world==source
                        examples.append(dict(source=source,destination=destination,original_worker=worker,war_budget=terms['war_budget'],actual_local_round_trip=True,personal_round_trip=True))
                        print('local campaign:',source,flush=True)
                    assert len(verified)==34 and not errors,(verified,errors)
                    report=dict(directions=verified,commands=len(commands),stale_recoveries=2,examples=examples,themes=4,sizes=3,page_errors=errors)
                    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
                    print(json.dumps(report,ensure_ascii=False));browser.close()
            except Exception:
                if 'key' in locals():
                    (output/'failure-save.json').write_text(json.dumps(engine.store.load(key).to_dict(),ensure_ascii=False),encoding='utf-8')
                if 'page' in locals():
                    try:
                        page.screenshot(path=str(output/'failure.png'))
                        (output/'failure.html').write_text(page.content(),encoding='utf-8')
                    except Exception:pass
                raise
            finally:http.shutdown();http.server_close()


if __name__=='__main__':main()
