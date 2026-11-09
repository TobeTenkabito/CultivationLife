"""Actual case requests and clicks, both themes, stale quotes and annual followups."""
import copy
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
from cultivation_life.building_rules import config
from cultivation_life.system.earth_temple_rules import state,temple
from cultivation_life.system.earth_disputes import current
from cultivation_life.system.economy.ledger import balance
from cultivation_life.system.economy.state import local_market
from cultivation_life.content_registry import ITEM_CATALOG,restricted_acquisition
from test_earth_temple import build
from test_earth_network import fund,ground,choose
from test_economy_enterprises import buy
from scripts.westward_navigation import open_westward
from scripts.browser_navigation import navigation_locator,click_control,set_theme


def main():
    out=ROOT/'build/earth-disputes-browser';out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='earth-disputes-') as folder:
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
                        g=engine._load(engine.create_game('六事听讼','supreme_metal','dao',360,preset_id='true_immortal')['id'])
                        g.pending_event=None;g.player.next_tribulation_age=None;g.heavenly_court['open_election']=None
                        g.player.location_id=next(c['location_id'] for c in config()['cities']['celestial'] if c['population']=='mixed')
                        g.settings.update(silent_events=True,combat_popup=False,court_election_popup=False)
                        engine.store.save(g);fund(engine,g.id);build(engine,g.id)
                        if theme=='dark' and width==1440:
                            buy(engine,engine._load(g.id),'farm');ground(engine,g.id)
                            engine.building_action(g.id,'construct');choose(engine,g.id,'level:1');choose(engine,g.id,'plan:1:professional');choose(engine,g.id,'confirm');choose(engine,g.id,'leave')
                            saved=engine._load(g.id);cave=next(r for r in saved.building_state['records'].values() if r.get('subtype')=='cave')
                            engine.building_action(g.id,'manage',building_id=cave['id']);choose(engine,g.id,'destroy');choose(engine,g.id,'destroy:',True);choose(engine,g.id,'leave')
                            saved=engine._load(g.id);market=local_market(saved)
                            key=next(k for k,r in market['commodities'].items() if k in ITEM_CATALOG and not restricted_acquisition('item',k) and r['tier']<=9)
                            market['commodities'][key]['stock']=0;engine.store.save(saved)
                        page=browser.new_page(viewport=dict(width=width,height=height),reduced_motion='reduce');page.set_default_timeout(90000)
                        errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                        page.goto(base);page.wait_for_function('!!configData && !busy');set_theme(page,theme);page.evaluate('id=>loadGame(id)',g.id)
                        open_westward(page,'地仙庙域')
                        open_westward(page,'地仙庙域')
                        def tab(name):page.locator(f'.earth-temple [data-subpage="{name}"]').click()
                        def action(name,target=None,status=200):
                            locator=page.locator(f'[data-earth-action=earth_{name}]'+(f'[data-earth-target={json.dumps(target,ensure_ascii=False)}]' if target is not None else ''))
                            with page.expect_response(lambda r:r.url.endswith('/yaochi-action')) as response:click_control(locator)
                            assert response.value.status==status,response.value.text()
                            page.wait_for_function('!busy')
                        def work():
                            with patch('cultivation_life.engine.orchestration.advancement._finish_action_events',return_value=None):action('work')
                        def accept(kind):
                            target=page.locator(f'[data-case-kind={kind}] [data-earth-action=earth_case_accept]').get_attribute('data-earth-target')
                            action('case_accept',target)
                        def select(name,finish=False):
                            selector=f'[data-case-plan={name}] [data-earth-action=earth_case_{"resolve" if finish else "plan"}]'
                            target=page.locator(selector).get_attribute('data-earth-target');action('case_resolve' if finish else 'case_plan',target)
                        tab('地方争议');snapshot=engine.store._path(g.id).read_bytes();tab('庙务');tab('地方争议')
                        assert engine.store._path(g.id).read_bytes()==snapshot and page.locator('.earth-case-card').count()==6
                        action('case_report')
                        assert page.locator('.utility-panel.panel-open').evaluate('n=>n.scrollWidth<=n.clientWidth+2')
                        page.locator('.utility-panel.panel-open').evaluate('n=>n.scrollTop=0');page.screenshot(path=str(out/f'{theme}-{width}-reports.png'),animations='disabled')
                        if theme=='dark' and width==1440:
                            assert len(state(engine._load(g.id))['cases']['reports'])==6
                            target=page.locator('[data-case-kind=supply] [data-earth-action=earth_case_decline]').get_attribute('data-earth-target')
                            before=engine._load(g.id);inventory=copy.deepcopy(before.player.inventory);cash=balance(before,'player')
                            action('case_decline',target);saved=engine._load(g.id)
                            assert saved.player.inventory==inventory and balance(saved,'player')==cash and state(saved)['trust']==50
                        # Stale real visible accept button is rejected and recovers to current case.
                        target=page.locator('[data-case-kind=property] [data-earth-action=earth_case_accept]').get_attribute('data-earth-target')
                        payload=page.evaluate("target=>({action:'earth_case_accept',target_id:game.yaochi.earth.token+'|'+target})",target)
                        assert page.request.post(base+f'/api/games/{g.id}/yaochi-action',data=payload).status==200
                        action('case_accept',target,400)
                        age=engine._load(g.id).player.age;annual=engine._advance_world_year
                        def interrupt(game,rng,news,**kwargs):
                            result=annual(game,rng,news,**kwargs)
                            if game.player.age==age+2:
                                event=engine._instantiate_event(engine.events_by_id['EVT_SECT_FIRST_WARNING_001'],game,random.Random(1))
                                event['_followup_event']=engine._prepare_treasure_reward_event(game,random.Random(2));game.pending_event=event;return False
                            return result
                        with patch.object(engine,'_advance_world_year',side_effect=interrupt):action('work')
                        assert current(engine._load(g.id))['progress']==2
                        assert page.locator('[data-earth-action=earth_work]').is_disabled()
                        page.locator('.utility-panel.panel-open .section-title > button[id$="-toggle"]').click();click_control(page.locator('#event-choices button'))
                        page.wait_for_function('!busy && game.pending_event?.id!=="EVT_SECT_FIRST_WARNING_001"')
                        click_control(page.locator('#event-choices button:enabled').first);page.wait_for_function('!busy && !game.pending_event')
                        open_westward(page,'地仙庙域');work();action('case_prepare')
                        page.locator('.earth-case-active').scroll_into_view_if_needed();page.screenshot(path=str(out/f'{theme}-{width}-choices.png'),animations='disabled')
                        select('open');assert not temple(engine._load(g.id))['public'];work();select('open',True)
                        assert temple(engine._load(g.id))['public'] and not current(engine._load(g.id))
                        accept('road');work();action('case_prepare');select('bypass');work();select('bypass',True)
                        assert state(engine._load(g.id))['cases']['reports']['road']['delay']==2
                        if theme=='dark' and width==1440:
                            for kind,option in [('water','canal'),('guard','repair'),('rebuild','restore')]:
                                accept(kind);work();action('case_prepare');select(option);work()
                                cash=balance(engine._load(g.id),'player');select(option,True)
                                assert not current(engine._load(g.id)) and balance(engine._load(g.id),'player')<=cash
                            assert engine._load(g.id).building_state['records'][cave['id']]['status']=='intact'
                            assert engine._load(g.id).player.formation_ground_arrays[0]['durability']==100
                        assert not current(engine._load(g.id))
                        tab('庙务');assert page.locator('[data-earth-action=earth_accept]:enabled').count()==3
                        assert page.locator('[data-earth-action=earth_cultivate]').is_disabled()
                        assert not errors,errors
                        page.close();print(f'{theme} {width}x{height}: real reports, stale recovery, timed cases, followup, outcomes and layout passed',flush=True)
                    browser.close()
            finally:http.shutdown();http.server_close()


if __name__=='__main__':main()
