"""Real court inspection, independent appeals, combat and rescue UI."""
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
from cultivation_life.system.court_bureau_rules import state,active,HOME,COURT
from cultivation_life.system.court_inspection import active as inquiry
from cultivation_life.system.economy.ledger import transfer_value
from test_court_bureaus import officers
from test_court_justice import named
from scripts.browser_navigation import navigation_locator,click_control,set_theme

def main():
    out=ROOT/'build/court-justice-browser';out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='court-justice-') as folder:
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
                        g=engine._load(engine.create_game('御史听案','supreme_metal','dao',7410,preset_id='true_immortal')['id'])
                        g.pending_event=None;g.player.next_tribulation_age=None;g.heavenly_court['open_election']=None;g.player.location_id=HOME
                        g.settings.update(silent_events=True,combat_popup=False,court_election_popup=False)
                        g.heavenly_court['bureaus']=dict(completed={'audit':2})
                        transfer_value(g,'background:celestial',COURT,10**11,'验收原预算');engine.store.save(g);ids=officers(engine,g.id)
                        g=engine._load(g.id);g.player.disciples.append(g.link_relationship({'id':ids[0]}));engine.store.save(g)
                        page=browser.new_page(viewport=dict(width=width,height=height),reduced_motion='reduce');page.set_default_timeout(120000)
                        errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                        page.goto(base);page.wait_for_function('!!configData && !busy');set_theme(page,theme);page.evaluate('id=>loadGame(id)',g.id)
                        def open_court():
                            navigation_locator(page,'[data-panel-target=heavenly-court]').click()
                            page.locator('#heavenly-court-content > .panel-page-tabs [data-subpage="诸司任职"]').click()
                        def tab(name):page.locator(f'.bureau-pages > .panel-page-tabs [data-subpage="{name}"]').click()
                        def action(name,target=None,status=200):
                            control=page.locator(f'[data-bureau-action={name}]'+(f'[data-bureau-target={json.dumps(target,ensure_ascii=False)}]' if target is not None else '')).filter(visible=True).first
                            with page.expect_response(lambda r:r.url.endswith('/yaochi-action')) as response:click_control(control)
                            assert response.value.status==status,response.value.text();page.wait_for_function('!busy')
                        def work():
                            with patch('cultivation_life.engine.orchestration.advancement._finish_action_events',return_value=None):action('work')
                        def reload():page.evaluate('id=>loadGame(id)',g.id);page.wait_for_function('!busy')
                        def travel(dest):
                            page.locator('#heavenly-court-toggle').click();navigation_locator(page,'[data-panel-target=map]').click()
                            page.locator('#map-view-tabs [aria-controls=map-locations]').click()
                            for _ in range(6):
                                click_control(page.locator(f'#map-locations .map-travel[data-destination="{dest}"]'));page.wait_for_function('!busy')
                                if not engine._load(g.id).map_journey:break
                            assert engine._load(g.id).player.location_id==dest
                            page.locator('#map-toggle').click();open_court();tab('差事')
                        open_court();tab('任职');action('join','audit');action('promote');tab('属员');action('appoint',ids[0]);tab('监察')
                        snapshot=engine.store._path(g.id).read_bytes();tab('履历');tab('监察');assert engine.store._path(g.id).read_bytes()==snapshot
                        # Submit an old page after the actual original source is already registered.
                        token=page.locator('[data-bureau-action=case_open]').get_attribute('data-bureau-target')
                        payload=page.evaluate("target=>({action:'bureau_case_open',target_id:game.heavenly_court.bureaus.token+'|'+target})",token)
                        assert page.request.post(base+f'/api/games/{g.id}/yaochi-action',data=payload).status==200
                        action('case_open',token,400);identity=inquiry(engine._load(g.id))['id']
                        action('case_step',identity+'~accounts');age=engine._load(g.id).player.age;annual=engine._advance_world_year
                        def stop(game,rng,news,**kw):
                            result=annual(game,rng,news,**kw)
                            if game.player.age==age+2:
                                event=engine._instantiate_event(engine.events_by_id['EVT_SECT_FIRST_WARNING_001'],game,random.Random(1))
                                event['_followup_event']=engine._prepare_treasure_reward_event(game,random.Random(2));game.pending_event=event;return False
                            return result
                        with patch.object(engine,'_advance_world_year',side_effect=stop):action('work')
                        assert inquiry(engine._load(g.id))['work']['progress']==2 and page.locator('[data-bureau-action=work]').is_disabled()
                        page.locator('#heavenly-court-toggle').click();click_control(page.locator('#event-choices button'))
                        page.wait_for_function('!busy && game.pending_event?.id!=="EVT_SECT_FIRST_WARNING_001"')
                        click_control(page.locator('#event-choices button:enabled').first);page.wait_for_function('!busy && !game.pending_event')
                        open_court();tab('监察');work()
                        for step in ('site','hearing'):action('case_step',identity+'~'+step);work()
                        page.locator('[aria-label="监察申辩"]').select_option('acknowledge');action('case_defend',identity+'~acknowledge');action('case_propose',identity+'~recuse')
                        assert page.locator(f'[data-bureau-action=case_reviewer][data-bureau-target="{identity}~{ids[0]}"]').is_disabled()
                        action('case_reviewer',identity+'~'+ids[1]);work()
                        if theme=='dark' and width==1440:
                            action('case_cancel',identity)
                            assert page.locator(f'[data-bureau-action=case_appeal][data-bureau-target="{identity}"]').count()==0
                            action('case_resume',identity)
                        page.locator('[data-inquiry]').scroll_into_view_if_needed();page.screenshot(path=str(out/f'{theme}-{width}-inspection.png'),animations='disabled')
                        assert page.locator('#heavenly-court-card').evaluate('n=>n.scrollWidth<=n.clientWidth+2')
                        action('case_execute',identity);assert ids[0] not in state(engine._load(g.id))['staff']
                        if theme=='dark' and width==1440:
                            action('case_appeal',identity);action('case_defend',identity+'~acknowledge');action('case_propose',identity+'~clear')
                            assert page.locator(f'[data-bureau-action=case_reviewer][data-bureau-target="{identity}~{ids[1]}"]').is_disabled()
                            action('case_reviewer',identity+'~'+ids[2]);work();action('case_execute',identity)
                            tab('任职');action('join','patrol');named(engine,g.id);reload();tab('差事')
                            data=engine.get_game(g.id)['heavenly_court']['bureaus'];offer=next(o for o in data['offers'] if o.get('operation')=='bounty')
                            action('accept',offer['token']+'~player');job=active(engine._load(g.id))[0];work();action('fight',job['id']+'~repel')
                            assert engine._load(g.id).last_combat_report and engine._load(g.id).world_npcs['wanted'].alive
                            page.screenshot(path=str(out/'dark-1440-patrol.png'),animations='disabled');action('claim',job['id'])
                            named(engine,g.id,'patient',wounds=4);reload();tab('差事')
                            offer=next(o for o in engine.get_game(g.id)['heavenly_court']['bureaus']['offers'] if o.get('operation')=='rescue')
                            action('accept',offer['token']+'~player');job=active(engine._load(g.id))[0];work();action('evacuate',job['id'])
                            assert engine._load(g.id).world_npcs['patient'].location_id==HOME
                            travel(offer['evacuation']['destination']);action('claim',job['id'])
                            assert not active(engine._load(g.id)) and engine._load(g.id).world_npcs['patient'].location_id==offer['evacuation']['destination']
                        assert not errors,errors;page.close()
                        print(f'{theme} {width}x{height}: actual evidence, stale page, event followup, independent review, disposal and layout passed',flush=True)
                    browser.close()
            finally:http.shutdown();http.server_close()

if __name__=='__main__':main()
