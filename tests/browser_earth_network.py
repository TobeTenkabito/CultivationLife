"""Actual facility/branch clicks in both pixel themes, including stale/event recovery."""
import random
import json
import copy
import sys
import tempfile
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.models import SectNpc
from cultivation_life.building_rules import config
from cultivation_life.system.earth_temple_rules import state, root, slots
from cultivation_life.system.economy.ledger import balance
from scripts.browser_navigation import navigation_locator, click_control, set_theme
from test_earth_network import fund, adjacent, travel, make_city, ground
from test_earth_temple import build
from browser_buildings import choice
from cultivation_life.system.building_projects import quote


def main():
    output = ROOT / 'build/earth-network-browser'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='earth-network-ui-') as folder:
        engine = GameEngine(ROOT, Path(folder) / 'saves')
        class Handler(server.Handler):
            def log_message(self, *args): pass
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', Path(folder)):
            http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            threading.Thread(target=http.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{http.server_port}'
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    for theme, width, height in [('light',1440,1000), ('dark',1440,1000), ('light',390,844), ('dark',390,844), ('dark',754,365)]:
                        if len(sys.argv)>1 and sys.argv[1]!=f'{theme}-{width}': continue
                        g = engine._load(engine.create_game('分庙专项验收', 'supreme_metal', 'dao', 360, preset_id='true_immortal')['id'])
                        g.pending_event = None
                        g.player.location_id = next(c['location_id'] for c in config()['cities']['celestial'] if c['population']=='mixed')
                        g.player.next_tribulation_age = None
                        g.heavenly_court['open_election'] = None
                        g.settings.update(silent_events=True, combat_popup=False, court_election_popup=False)
                        engine.store.save(g); fund(engine,g.id); build(engine,g.id)
                        source=g.player.location_id; destination=adjacent(engine,g.id)
                        travel(engine,g.id,destination); make_city(engine,g.id); travel(engine,g.id,source)
                        array_id,supply=ground(engine,g.id)
                        page = browser.new_page(viewport=dict(width=width,height=height), reduced_motion='reduce')
                        page.set_default_timeout(90000)
                        errors=[]; page.on('pageerror',lambda error:errors.append(str(error)))
                        page.goto(base); page.wait_for_function('!!configData && !busy')
                        set_theme(page,theme); page.evaluate('id=>loadGame(id)',g.id)
                        navigation_locator(page,'[data-panel-target=yaochi]').click()
                        page.locator('#yaochi-content [data-subpage="地仙庙域"]').click()
                        def tab(name):
                            page.locator(f'.earth-temple [data-subpage="{name}"]').click()
                        def action(name, target=None, status=200):
                            selector=f'[data-earth-action=earth_{name}]'
                            if target is not None: selector+=f'[data-earth-target={json.dumps(target,ensure_ascii=False)}]'
                            with page.expect_response(lambda r:r.url.endswith('/yaochi-action')) as response:
                                click_control(page.locator(selector))
                            assert response.value.status==status,response.value.text()
                            page.wait_for_function('!busy')
                        tab('专项设施')
                        original=engine.store._path(g.id).read_bytes()
                        tab('庙域名录'); tab('专项设施')
                        assert engine.store._path(g.id).read_bytes()==original
                        page.get_by_label('第1席专项设施',exact=True).select_option('watch')
                        # Submit the same visible quote twice: second real click must recover.
                        payload=page.evaluate("({action:'earth_facility',target_id:game.yaochi.earth.token+'|0:watch'})")
                        assert page.request.post(base+f'/api/games/{g.id}/yaochi-action',data=payload).status==200
                        action('facility','0:watch',400)
                        assert page.evaluate('game.yaochi.earth.facilities.works.progress')==0
                        assert page.locator('[data-earth-action=earth_facility]:enabled').count()==0
                        age=engine._load(g.id).player.age; annual=engine._advance_world_year
                        def interrupt(game,rng,news,**kwargs):
                            result=annual(game,rng,news,**kwargs)
                            if game.player.age==age+3:
                                warning=engine._instantiate_event(engine.events_by_id['EVT_SECT_FIRST_WARNING_001'],game,random.Random(1))
                                warning['_followup_event']=engine._prepare_treasure_reward_event(game,random.Random(2))
                                game.pending_event=warning; return False
                            return result
                        with patch.object(engine,'_advance_world_year',side_effect=interrupt): action('work')
                        assert state(engine._load(g.id))['works']['progress']==3
                        assert page.locator('[data-earth-action=earth_work]').is_disabled()
                        page.locator('#yaochi-toggle').click()
                        click_control(page.locator('#event-choices button'))
                        page.wait_for_function('!busy && game.pending_event?.id!=="EVT_SECT_FIRST_WARNING_001"')
                        click_control(page.locator('#event-choices button:enabled').first)
                        page.wait_for_function('!busy && !game.pending_event')
                        navigation_locator(page,'[data-panel-target=yaochi]').click()
                        with patch('cultivation_life.engine.orchestration.advancement._finish_action_events',return_value=None): action('work')
                        assert state(engine._load(g.id))['works']['progress']==20
                        action('complete_works')
                        assert slots(engine._load(g.id))==['watch',None]
                        page.get_by_label('第2席专项设施',exact=True).select_option('watch')
                        assert page.locator('[data-earth-target="1:watch"]').is_disabled()
                        page.get_by_label('第2席专项设施',exact=True).select_option('care')
                        action('facility','1:care')
                        with patch('cultivation_life.engine.orchestration.advancement._finish_action_events',return_value=None): action('work')
                        action('complete_works')
                        assert slots(engine._load(g.id))==['watch','care']
                        assert page.locator('#yaochi-card').evaluate('n=>n.scrollWidth<=n.clientWidth+2')
                        page.locator('#yaochi-card').evaluate('n=>n.scrollTop=0')
                        page.screenshot(path=str(output/f'{theme}-{width}-facilities.png'),animations='disabled')
                        if theme=='dark' and width==1440:
                            saved=engine._load(g.id); ledger=copy.deepcopy(state(saved)); identity=state(saved)['temple_id']
                            cash=balance(saved,'player')
                            page.locator('#yaochi-toggle').click()
                            navigation_locator(page,'[data-panel-target=map]').click()
                            page.locator('#map-view-tabs [aria-controls=map-locations]').click()
                            building=page.locator(f'#map-locations [data-building-id="{identity}"]')
                            click_control(building.locator('[data-building-action=manage]'))
                            page.wait_for_function('!busy && !!game.pending_event')
                            choice(page,'destroy'); choice(page,page.evaluate('game.pending_event.choices.find(c=>c.id.startsWith("destroy:")).id'))
                            choice(page,'rebuild')
                            saved=engine._load(g.id); cost=quote(saved,'rebuild',saved.building_state['records'][identity])
                            assert cost['coins']==8400000000
                            choice(page,page.evaluate('game.pending_event.choices.find(c=>c.id.startsWith("rebuild:")).id')); choice(page,'leave')
                            saved=engine._load(g.id)
                            assert balance(saved,'player')==cash-cost['coins'] and slots(saved)==['watch','care']
                            assert state(saved)==ledger
                            if page.locator('#map-card').is_visible(): page.locator('#map-toggle').click()
                            navigation_locator(page,'[data-panel-target=yaochi]').click(); tab('专项设施')
                        service=page.locator('[data-facility-service=watch] [data-earth-action=earth_special]')
                        target=service.get_attribute('data-earth-target')
                        before=engine._load(g.id).player.formation_repair_supplies[supply]
                        action('special',target)
                        saved=engine._load(g.id)
                        assert saved.player.formation_repair_supplies.get(supply,0)<before
                        assert next(a for a in saved.player.formation_ground_arrays if a['id']==array_id)['durability']>40
                        assert state(saved)['duty']['progress']==0 and not state(saved)['allowance']
                        tab('庙务'); click_control(page.locator('.earth-current .yaochi-exit summary')); action('cancel')
                        tab('专项设施')
                        click_control(page.locator('[data-facility-slot="0"] .earth-construction summary'))
                        page.get_by_label('第1席专项设施',exact=True).select_option('teach')
                        action('facility','0:teach')
                        cash=balance(engine._load(g.id),'player')
                        click_control(page.locator('.earth-works .yaochi-exit summary')); action('cancel_works')
                        assert balance(engine._load(g.id),'player')==cash and slots(engine._load(g.id))==[None,'care']
                        if theme=='dark' and width==1440:
                            page.get_by_label('第1席专项设施',exact=True).select_option('teach')
                            action('facility','0:teach')
                            with patch('cultivation_life.engine.orchestration.advancement._finish_action_events',return_value=None): action('work')
                            action('complete_works')
                            saved=engine._load(g.id); saved.player.opportunity=10**10
                            pupil=SectNpc('earth-ui-pupil','本地门人','门人',2,1,30,300,world='celestial',location_id=source,spirit_root='supreme_metal')
                            saved.world_npcs[pupil.id]=pupil
                            saved.player.disciples.append(saved.link_relationship({'id':pupil.id})); engine.store.save(saved)
                            from cultivation_life.system.npc_development.service import quote as training_quote
                            price=training_quote(saved,'npc',pupil.id,'cultivation')
                            page.evaluate('id=>loadGame(id)',g.id); page.wait_for_function('!busy'); tab('专项设施')
                            target=page.locator('[data-facility-service=teach] [data-earth-action=earth_special]').get_attribute('data-earth-target')
                            action('special',target)
                            saved=engine._load(g.id)
                            assert saved.player.opportunity==10**10-price['opportunity']
                            assert saved.world_npcs[pupil.id].layer==price['result']['layer']
                            assert saved.player.disciples[-1].person is saved.world_npcs[pupil.id]
                            tab('庙务'); click_control(page.locator('.earth-current .yaochi-exit summary')); action('cancel')
                        # Real map route, followed by branch construction at the original city.
                        page.locator('#yaochi-toggle').click()
                        navigation_locator(page,'[data-panel-target=map]').click()
                        page.locator('#map-view-tabs [aria-controls=map-locations]').click()
                        for _ in range(5):
                            click_control(page.locator(f'#map-locations .map-travel[data-destination="{destination}"]'))
                            page.wait_for_function('!busy')
                            if not engine._load(g.id).map_journey: break
                        assert engine._load(g.id).player.location_id==destination
                        page.locator('#map-toggle').click()
                        navigation_locator(page,'[data-panel-target=yaochi]').click(); tab('庙域名录')
                        assert page.locator('[data-earth-action=earth_cultivate]').is_disabled()
                        target=page.locator('[data-earth-action=earth_build]:enabled').first.get_attribute('data-earth-target')
                        action('build',target)
                        assert len(root(engine._load(g.id))['branches'])==1
                        assert page.evaluate('game.yaochi.earth.local && game.yaochi.earth.allowance===0')
                        assert page.locator('.earth-network-site').count()==2
                        assert page.locator('.earth-network-site.is-local').count()==1
                        assert page.locator('#yaochi-card').evaluate('n=>n.scrollWidth<=n.clientWidth+2')
                        page.locator('#yaochi-card').evaluate('n=>n.scrollTop=0')
                        page.screenshot(path=str(output/f'{theme}-{width}-network.png'),animations='disabled')
                        assert not errors,errors
                        page.close()
                        print(f'{theme} {width}x{height}: paid slots, stale/event/followup recovery, actual repair, replacement, map travel and branch passed',flush=True)
                    browser.close()
            finally:
                http.shutdown(); http.server_close()


if __name__=='__main__': main()
