"""Real browser appointment, road travel, interrupted work, audit and officer dispatch."""
import json
import random
import sys
import tempfile
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.content_registry import WORLD_SYSTEMS
from cultivation_life.system.court_bureau_rules import state,active,HOME,COURT
from cultivation_life.system.economy.ledger import transfer_value
from test_court_bureaus import officers
from scripts.browser_navigation import navigation_locator,click_control,set_theme

def main():
    out=ROOT/'build/court-bureaus-browser';out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='court-bureaus-') as folder:
        engine=GameEngine(ROOT,Path(folder)/'saves')
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            http=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
            base=f'http://127.0.0.1:{http.server_port}'
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    for theme,width,height in [('light',1440,1000),('dark',1440,1000),('light',390,844),('dark',390,844),('dark',754,365)]:
                        if len(sys.argv)>1 and sys.argv[1]!=f'{theme}-{width}':continue
                        g=engine._load(engine.create_game('玉京听事','supreme_metal','dao',7410,preset_id='true_immortal')['id'])
                        g.pending_event=None;g.player.next_tribulation_age=None;g.heavenly_court['open_election']=None;g.player.location_id=HOME
                        g.settings.update(silent_events=True,combat_popup=False,court_election_popup=False)
                        if theme=='dark' and width==1440:
                            # Prior service qualification; appointments and dispatch still use real UI.
                            g.heavenly_court['bureaus']=dict(completed={'patrol':2})
                        transfer_value(g,'background:celestial',COURT,10**11,'验收原府库预算')
                        engine.store.save(g);ids=officers(engine,g.id)
                        page=browser.new_page(viewport=dict(width=width,height=height),reduced_motion='reduce');page.set_default_timeout(120000)
                        errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                        page.goto(base);page.wait_for_function('!!configData && !busy');set_theme(page,theme);page.evaluate('id=>loadGame(id)',g.id)
                        def open_court():
                            navigation_locator(page,'[data-panel-target=heavenly-court]').click()
                            page.locator('#heavenly-court-content > .panel-page-tabs [data-subpage="诸司任职"]').click()
                        def tab(name):page.locator(f'.bureau-pages > .panel-page-tabs [data-subpage="{name}"]').click()
                        def action(name,target=None,status=200):
                            locator=page.locator(f'[data-bureau-action={name}]'+(f'[data-bureau-target={json.dumps(target,ensure_ascii=False)}]' if target is not None else '')).filter(visible=True)
                            with page.expect_response(lambda r:r.url.endswith('/yaochi-action')) as response:click_control(locator.first)
                            assert response.value.status==status,response.value.text();page.wait_for_function('!busy')
                        def work():
                            with patch('cultivation_life.engine.orchestration.advancement._finish_action_events',return_value=None):action('work')
                        def travel(dest):
                            if page.locator('#heavenly-court-card').is_visible():page.locator('#heavenly-court-toggle').click()
                            navigation_locator(page,'[data-panel-target=map]').click();page.locator('#map-view-tabs [aria-controls=map-locations]').click()
                            for _ in range(6):
                                click_control(page.locator(f'#map-locations .map-travel[data-destination="{dest}"]'));page.wait_for_function('!busy')
                                if not engine._load(g.id).map_journey:break
                            assert engine._load(g.id).player.location_id==dest
                            page.locator('#map-toggle').click();open_court();tab('差事')
                        open_court();snapshot=engine.store._path(g.id).read_bytes();tab('履历');tab('任职')
                        assert engine.store._path(g.id).read_bytes()==snapshot
                        assert page.locator('[data-bureau-office]').count()==4
                        page.screenshot(path=str(out/f'{theme}-{width}-offices.png'),animations='disabled')
                        action('join','patrol');tab('差事')
                        target=page.locator('[data-bureau-action=accept]:enabled').first.get_attribute('data-bureau-target')
                        payload=page.evaluate("target=>({action:'bureau_accept',target_id:game.heavenly_court.bureaus.token+'|'+target})",target)
                        assert page.request.post(base+f'/api/games/{g.id}/yaochi-action',data=payload).status==200
                        action('accept',target,400)
                        job=active(engine._load(g.id))[0];assert page.locator('[data-bureau-action=work]').is_disabled()
                        travel(job['location']);age=engine._load(g.id).player.age;annual=engine._advance_world_year
                        def stop(game,rng,news,**kw):
                            result=annual(game,rng,news,**kw)
                            if game.player.age==age+2:
                                event=engine._instantiate_event(engine.events_by_id['EVT_SECT_FIRST_WARNING_001'],game,random.Random(1))
                                event['_followup_event']=engine._prepare_treasure_reward_event(game,random.Random(2));game.pending_event=event;return False
                            return result
                        with patch.object(engine,'_advance_world_year',side_effect=stop):action('work')
                        assert active(engine._load(g.id))[0]['progress']==2 and page.locator('[data-bureau-action=work]').is_disabled()
                        page.locator('#heavenly-court-toggle').click();click_control(page.locator('#event-choices button'))
                        page.wait_for_function('!busy && game.pending_event?.id!=="EVT_SECT_FIRST_WARNING_001"')
                        click_control(page.locator('#event-choices button:enabled').first);page.wait_for_function('!busy && !game.pending_event')
                        open_court();tab('差事');work()
                        assert page.locator('#heavenly-court-card').evaluate('n=>n.scrollWidth<=n.clientWidth+2')
                        page.locator('.bureau-current').scroll_into_view_if_needed();page.screenshot(path=str(out/f'{theme}-{width}-case.png'),animations='disabled')
                        action('claim',job['id']);assert not active(engine._load(g.id));travel(HOME);tab('任职');action('join','audit');tab('差事')
                        action('accept');work();audit=active(engine._load(g.id))[0];action('claim',audit['id'])
                        assert state(engine._load(g.id))['jobs'][0]['audited']['difference']==0
                        tab('任职');action('join','land');tab('差事');assert not page.locator('[data-bureau-action=accept]:enabled').count()
                        tab('任职');action('join','works');tab('属员')
                        assert page.locator('[data-bureau-action=appoint]:enabled').count()==0
                        if theme=='dark' and width==1440:
                            # Independent qualified supervisor fixture keeps the original
                            # per-window patrol lock; never clear or reroll accepted jobs.
                            g=engine._load(engine.create_game('玉京掌司','supreme_metal','dao',7410,preset_id='true_immortal')['id'])
                            g.pending_event=None;g.player.next_tribulation_age=None;g.heavenly_court['open_election']=None;g.player.location_id=HOME
                            g.settings.update(silent_events=True,combat_popup=False,court_election_popup=False)
                            g.heavenly_court['bureaus']=dict(completed={'patrol':2})
                            transfer_value(g,'background:celestial',COURT,10**11,'验收原府库预算');engine.store.save(g);ids=officers(engine,g.id)
                            page.locator('#heavenly-court-toggle').click();page.evaluate('id=>loadGame(id)',g.id);open_court()
                            tab('任职');action('join','patrol');action('promote');tab('属员');action('appoint',ids[0]);action('appoint',ids[1]);tab('差事')
                            for card in page.locator('[data-bureau-offer]').all():
                                card.locator('select').select_option(ids[0])
                                if card.locator('[data-bureau-action=accept]').is_enabled():
                                    target=card.locator('[data-bureau-action=accept]').get_attribute('data-bureau-target');break
                            action('accept',target);delegated=active(engine._load(g.id))[0]
                            page.locator('#heavenly-court-toggle').click()
                            for _ in range(4):
                                with patch('cultivation_life.engine.orchestration.advancement._finish_action_events',return_value=None):
                                    with page.expect_response(lambda r:r.url.endswith('/advance')) as response:click_control(page.locator('[data-action=rest]'))
                                    assert response.value.status==200,response.value.text();page.wait_for_function('!busy')
                                if active(engine._load(g.id))[0]['phase']=='ready':break
                            assert active(engine._load(g.id))[0]['phase']=='ready', (engine._load(g.id).player.age,active(engine._load(g.id))[0])
                            open_court();travel(delegated['location']);action('review',delegated['id']);work();action('claim',delegated['id'])
                            travel(HOME);recovery=page.locator('.bureau-current details');recovery.locator('summary').click();action('handover',delegated['id'])
                            assert not active(engine._load(g.id)) and engine._load(g.id).world_npcs[ids[0]].location_id==HOME
                            tab('属员');page.screenshot(path=str(out/'dark-1440-officers.png'),animations='disabled')
                            assert 'jade_capital' not in page.locator('.bureau-pages').inner_text()
                            with patch.dict(WORLD_SYSTEMS['yaochi_westward'],enabled=False):
                                page.evaluate('id=>loadGame(id)',g.id);page.wait_for_function('!busy');tab('属员')
                                action('release',ids[0]);action('release',ids[1]);tab('任职');action('resign')
                                assert not state(engine._load(g.id)).get('office')
                        assert not errors,errors
                        page.close();print(f'{theme} {width}x{height}: appointments, stale recovery, original road, paid work, followup, actual audit and layout passed',flush=True)
                    browser.close()
            finally:http.shutdown();http.server_close()

if __name__=='__main__':main()
