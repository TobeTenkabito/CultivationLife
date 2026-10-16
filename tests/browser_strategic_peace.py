"""Single low-memory browser: actual treaty, consent, combat and map navigation."""
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
from cultivation_life.engine.composition.strategic_war import bind
from cultivation_life.system.strategic_war import peace
from cultivation_life.system.territory import state as territory
from test_strategic_peace import finished, economic_fixture
from test_strategic_war import own_campaign
from scripts.browser_navigation import navigation_locator, click_control
from browser_strategic_war import post


def main():
    evidence=ROOT/'build'/'strategic-peace-ui';evidence.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='strategic-peace-browser-') as directory:
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
                        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                        page.goto(f'http://127.0.0.1:{http.server_port}');page.wait_for_function('!!configData')
                        g,row,c,asset=economic_fixture(engine)
                        loser=g.sects[c['defender_id']]
                        territory.ensure(g,engine.maps,row['world'])[loser.location_id][loser.id]['outpost']=True
                        engine.store.save(g);page.evaluate('async id=>loadGame(id)',g.id)
                        navigation_locator(page,'[data-panel-target=war]').click()
                        root=page.locator('#strategic-war-panel');root.get_by_role('tab',name='议事',exact=True).click()
                        assert root.get_by_role('radiogroup',name='选择和谈条件').get_by_role('radio').count()==7
                        for width,height in [(1440,960),(393,852),(852,393)]:
                            page.set_viewport_size(dict(width=width,height=height))
                            for theme in ('a','b','d','f'):
                                page.evaluate('(v)=>document.documentElement.dataset.theme=v',theme)
                                for name in ('加重赔款','拆除战区据点','退出争议战区','移交战败宗产业','长期休战'):
                                    root.get_by_role('radio',name=name,exact=True).check()
                                    assert root.evaluate('(r)=>r.scrollWidth<=r.clientWidth+1')
                                root.locator('.strategy-peace').screenshot(path=str(evidence/f'terms-{theme}-{width}.png'))
                        # A changed original treasury must reject the on-screen quote
                        # once, then restore the actual page and clear busy state.
                        root.get_by_role('radio',name='战争赔款',exact=True).check()
                        stale=engine._load(g.id)
                        from cultivation_life.system.economy import depot
                        payer=peace.quote(bind(engine),stale,stale.strategic_war_state['wars'][0],'attacker','reparations')[0]['payer']['id']
                        stale.intrigue_state['factions'][depot.treasury(stale,stale.sects[payer]).removeprefix('organization:')]['resources']=0
                        engine.store.save(stale);before=engine.store._path(g.id).read_bytes()
                        post(page,root.get_by_role('button',name='提交条件和约'),400)
                        assert engine.store._path(g.id).read_bytes()==before
                        # Real accepted economic treaty keeps the original plot.
                        g,row,c,asset=economic_fixture(engine);engine.store.save(g)
                        page.evaluate('async id=>loadGame(id)',g.id);root.get_by_role('tab',name='议事',exact=True).click()
                        root.get_by_role('radio',name='移交战败宗产业',exact=True).check()
                        with patch.object(engine,'_vote_probability',return_value=1.):post(page,root.get_by_role('button',name='提交条件和约'))
                        assert engine._load(g.id).economy_v2['estates'][asset['id']]['owner_id']==c['attacker_id']
                        assert '已履约' in root.locator('.strategy-peace').inner_text()
                        # Defeated player's organizations receive a real pending
                        # proposal. The UI accepts it only via the explicit button.
                        g,row,c=finished(engine,'defender');peace.propose(bind(engine),g,row,'defender','reparations');engine.store.save(g)
                        page.evaluate('async id=>loadGame(id)',g.id);root.get_by_role('tab',name='议事',exact=True).click()
                        post(page,root.get_by_role('button',name='接受和约'))
                        assert engine._load(g.id).strategic_war_state['wars'][0]['treaty']['total']>0
                        # Organization consent alone cannot sign for the whole race,
                        # including when every current NPC representative votes no.
                        g,row,c=own_campaign(engine);g.player.realm_index=4;g.player.layer=1
                        assert engine._has_sect_voice(g) and not engine._has_race_voice(g)
                        peace.propose(bind(engine),g,row,'defender','white_peace');engine.store.save(g)
                        page.evaluate('async id=>loadGame(id)',g.id);root.get_by_role('tab',name='议事',exact=True).click()
                        assert '有效代表多数通过' in root.locator('.strategy-peace').inner_text()
                        post(page,root.get_by_role('button',name='接受和约'))
                        rejected=engine._load(g.id).strategic_war_state['wars'][0]
                        assert rejected['status']=='active' and not rejected.get('treaty')
                        assert rejected['peace_proposal']['status']=='rejected'
                        assert root.get_by_role('button',name='接受和约').count()==0
                        assert root.get_by_role('button',name='提出总停战').is_disabled()
                        assert not page.locator('body').evaluate('(n)=>n.classList.contains("busy")')
                        # A victorious local owner without a race seat retains the
                        # real proceeds while NPC representatives conduct diplomacy.
                        g,row,c=finished(engine);g.player.realm_index=4;g.player.layer=1
                        row['objectives_done_age']=g.player.age;g.player.age+=25
                        peace.advance(bind(engine),g,row);engine.store.save(g)
                        page.evaluate('async id=>loadGame(id)',g.id);root.get_by_role('tab',name='议事',exact=True).click()
                        assert '已履约' in root.locator('.strategy-peace').inner_text()
                        assert engine._load(g.id).strategic_war_state['wars'][0]['treaty']['total']>0
                        # Campaign markers survive all phases and both projections.
                        g,row,c=own_campaign(engine);engine.store.save(g)
                        for phase,status,text in [('marching','active','集结'),('engaged','active','交锋'),('returning','withdrawing','撤军')]:
                            actual=engine._load(g.id);child=next(w for w in actual.wars if w['id']==c['id'])
                            child.update(campaign_phase=phase,status=status);engine.store.save(actual)
                            page.evaluate('async id=>loadGame(id)',g.id)
                            navigation_locator(page,'[data-panel-target=map]').click()
                            page.locator('#map-view-tabs').get_by_role('button',name='可视地图',exact=True).click()
                            atlas=page.locator('#map-atlas');atlas.get_by_role('combobox',name='地图地点').select_option(c['location_id'])
                            for width,height in [(1440,960),(393,852),(852,393)]:
                                page.set_viewport_size(dict(width=width,height=height))
                                for theme in ('a','b','d','f'):
                                    page.evaluate('(v)=>document.documentElement.dataset.theme=v',theme)
                                    for mode in ('3d','flat'):
                                        atlas.locator(f'[data-atlas-mode="{mode}"]').click()
                                        assert atlas.locator(f'[data-atlas-location="{c["location_id"]}"] .atlas-war-marker').text_content()==text
                                        assert atlas.locator(f'[data-map-campaign="{c["id"]}"]').count()==1
                                        assert atlas.evaluate('(r)=>r.scrollWidth<=r.clientWidth+1')
                                    if phase=='engaged':atlas.screenshot(path=str(evidence/f'map-{theme}-{width}.png'))
                            atlas.locator(f'[data-map-campaign="{c["id"]}"]').get_by_role('button',name='查看战役').click()
                            assert root.get_by_role('tab',name='战役',exact=True).get_attribute('aria-selected')=='true'
                            assert root.locator(f'[data-campaign-id="{c["id"]}"]').get_attribute('aria-pressed')=='true'
                        # Actual personal combat is the ordinary detailed resolver.
                        g,row,c=own_campaign(engine);c['campaign_phase']='engaged';g.player.location_id=c['location_id']
                        for journeys in c['journeys'].values():
                            for j in journeys:
                                j.update(phase='stationed',remaining=0);bind(engine).find_person(g,j['person_id']).location_id=c['location_id']
                        engine.store.save(g);page.evaluate('async id=>loadGame(id)',g.id)
                        root.get_by_role('tab',name='战役',exact=True).click()
                        root.locator(f'[data-campaign-id="{c["id"]}"]').click()
                        post(page,root.get_by_role('button',name='亲自参加会战'))
                        actual=next(w for w in engine._load(g.id).wars if w['id']==c['id'])
                        assert actual['battles']==1 and any('玩家参战' in l['title'] for l in actual['logs'])
                        assert root.get_by_role('button',name='亲自参加会战').is_disabled()
                        assert not errors,errors
                        print('Strategic peace browser passed: seven real term cards; four themes x three sizes; stale quote recovery; original title transfer; explicit consent with representative majority; NPC diplomacy for owners without a race seat; both map projections and three campaign phases; actual personal battle and cooldown',flush=True)
                    finally:browser.close()
            finally:http.shutdown();http.server_close();thread.join(timeout=2)


if __name__=='__main__':main()
