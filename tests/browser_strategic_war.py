"""One browser and one page: four themes, actual commands and stale recovery."""
import sys
import tempfile
import threading
import random
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.engine.composition.strategic_war import bind
from cultivation_life.system.strategic_war.lifecycle import advance
from cultivation_life.system.strategic_war import lifecycle
from cultivation_life.system.strategic_war.materialization import materialize
from test_strategic_war import scenario
from test_strategic_dispatch import reserve_game
from scripts.browser_navigation import navigation_locator, click_control


def post(page,target,status=200):
    with page.expect_response(lambda r:r.url.endswith('/strategic-war')) as response:
        click_control(target)
    assert response.value.status==status,response.value.text()
    page.wait_for_function('!busy')


def main():
    evidence=ROOT/'build'/'strategic-war-ui';evidence.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='strategic-war-browser-') as directory:
        engine=GameEngine(ROOT,Path(directory)/'saves')
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',Path(directory)):
            http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch(args=['--disable-gpu','--renderer-process-limit=1','--js-flags=--max-old-space-size=128'])
                    try:
                        page=browser.new_page(viewport=dict(width=1440,height=960),reduced_motion='reduce')
                        errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                        page.goto(f'http://127.0.0.1:{http.server_port}')
                        page.wait_for_function('!!configData')
                        game,row=scenario(engine)
                        game.player.faction_id='taixuan';game.sects['taixuan'].founded_by_player=True
                        engine.store.save(game)
                        page.evaluate('async id=>loadGame(id)',game.id)
                        navigation_locator(page,'[data-panel-target=war]').click()
                        root=page.locator('#strategic-war-panel');root.wait_for(state='visible')
                        root.get_by_role('tab',name='议事',exact=True).click()
                        post(page,root.get_by_role('button',name='批准 太玄门 出征'))
                        saved=engine._load(game.id)
                        assert any(c['org']['id']=='taixuan' for c in saved.strategic_war_state['wars'][0]['commitments'])
                        saved,row,chosen,reserve=reserve_game(engine);game=saved
                        # A second approved reserve exercises two-window races;
                        # ordinary initialization only needs one funded reserve.
                        extra=materialize(bind(engine),saved,row['world'],row['attacker'],random.Random(89))
                        lifecycle.commit(bind(engine),saved,row,extra)
                        engine.store.save(saved)
                        page.evaluate('async id=>loadGame(id)',game.id)
                        root.get_by_role('tab',name='战役',exact=True).click()
                        root.locator(f'[data-campaign-id="{chosen["id"]}"]').click()
                        selector=root.get_by_role('combobox',name='选择闲置宗门')
                        selector.select_option(reserve.id)
                        post(page,root.get_by_role('button',name='调入此战役',exact=True))
                        deployed=engine._load(game.id)
                        target=next(w for w in deployed.wars if w['id']==chosen['id'])
                        assert any(r['org']['id']==reserve.id for r in target['reinforcements'])
                        assert root.locator('.strategy-unit').count()>=3
                        assert not root.locator(f'select[aria-label="选择闲置宗门"] option[value="{reserve.id}"]').count()
                        for width,height in [(1440,960),(393,852),(852,393)]:
                            page.set_viewport_size(dict(width=width,height=height))
                            for theme in ('a','b','d','f'):
                                page.evaluate('(theme)=>document.documentElement.dataset.theme=theme',theme)
                                root.get_by_role('tab',name='态势',exact=True).click()
                                assert root.locator('svg').count()==1
                                assert root.evaluate('(r)=>r.scrollWidth<=r.clientWidth+1')
                                root.screenshot(path=str(evidence/f'{theme}-{width}.png'))
                                root.get_by_role('tab',name='战役',exact=True).click()
                                assert root.locator('.strategy-campaign').count()==2
                                root.locator(f'[data-campaign-id="{chosen["id"]}"]').click()
                                assert root.locator('.strategy-army').count()==2
                                assert root.evaluate('(r)=>r.scrollWidth<=r.clientWidth+1')
                                root.screenshot(path=str(evidence/f'dispatch-{theme}-{width}.png'))
                                root.get_by_role('tab',name='议事',exact=True).click()
                                assert root.evaluate('(r)=>r.scrollWidth<=r.clientWidth+1')
                        # Another window consumes a reserve. The stale page must
                        # reject once, reread and remove that organization.
                        root.get_by_role('tab',name='战役',exact=True).click()
                        root.locator(f'[data-campaign-id="{chosen["id"]}"]').click()
                        view=engine.get_game(game.id)['war_system']['strategic']
                        current=view['wars'][0]
                        options=next(c['dispatch_choices'] for c in current['campaigns'] if c['id']==chosen['id'])
                        assert options
                        option=options[0]
                        root.get_by_role('combobox',name='选择闲置宗门').select_option(option['id'])
                        engine.strategic_war_action(game.id,dict(action='dispatch',war_id=current['id'],campaign_id=chosen['id'],
                            org_id=option['id'],org_kind=option['kind'],expected_cost=option['cost'],
                            expected_revision=current['revision'],command_id='other-window-dispatch',command_seq=view['command_seq']))
                        before=engine.store._path(game.id).read_bytes()
                        post(page,root.get_by_role('button',name='调入此战役',exact=True),400)
                        assert engine.store._path(game.id).read_bytes()==before
                        assert not root.locator(f'select[aria-label="选择闲置宗门"] option[value="{option["id"]}"]').count()
                        post(page,root.get_by_role('button',name='本部固守',exact=True))
                        held=next(w for w in engine._load(game.id).wars if w['id']==chosen['id'])
                        assert held['org_stances']['taixuan']=='hold'
                        post(page,root.get_by_role('button',name='撤回本组织',exact=True))
                        withdrawn=next(w for w in engine._load(game.id).wars if w['id']==chosen['id'])
                        assert withdrawn['status']=='active' and 'taixuan' in withdrawn['withdrawn_orgs']
                        assert any(j['phase'] in {'outbound','stationed'} for j in withdrawn['journeys']['attacker']
                                   if withdrawn['roster_owner'][j['person_id']]!= 'taixuan')
                        root.get_by_role('tab',name='议事',exact=True).click()
                        # Real stale command, no retry: revoke authority behind the page.
                        target=root.get_by_role('button',name='提出总停战')
                        assert not target.is_disabled()
                        stale=engine._load(game.id);stale.player.faction_id=None
                        stale.player.lineage_race=stale.player.allegiance_race=stale.player.race='sunwing'
                        engine.store.save(stale)
                        before=engine.store._path(game.id).read_bytes()
                        post(page,target,400)
                        assert engine.store._path(game.id).read_bytes()==before
                        assert root.get_by_role('button',name='提出总停战').is_disabled()
                        assert not errors,errors
                        print('Strategic war browser passed: actual commitment and idle dispatch, coalition cards, four themes × desktop/portrait/landscape, stale permission denial and busy recovery',flush=True)
                    finally:browser.close()
            finally:
                http.shutdown();http.server_close();thread.join(timeout=2)


if __name__=='__main__':main()
