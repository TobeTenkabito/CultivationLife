"""Actual HTTP/page actions: lease, production, fair events, awards and both themes."""
import random,sys,tempfile,threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.rules import add_item
from cultivation_life.system.yaochi_rules import config
from cultivation_life.system.yaochi_fair_rules import active
from cultivation_life.system.yaochi_garden import estate
from test_yaochi_fair import opponent,array,damage
from scripts.browser_navigation import navigation_locator,click_control,set_theme

def main():
    out=ROOT/'build/yaochi-fair-browser';out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='yaochi-fair-ui-') as folder:
        e=GameEngine(ROOT,Path(folder)/'saves')
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',e),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            http=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=http.serve_forever,daemon=True).start();base=f'http://127.0.0.1:{http.server_port}'
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    for theme,width,height in [('light',1440,1000),('dark',1440,1000),('light',390,844),('dark',390,844),('dark',754,365)]:
                        if len(sys.argv)>1 and sys.argv[1]!=f'{theme}-{width}':continue
                        g=e._load(e.create_game('仙圃与仙会验收','supreme_metal','dao',7410,preset_id='true_immortal')['id']);g.pending_event=None;g.player.next_tribulation_age=None;g.player.location_id=config()['location_id']
                        g.player.immortal_body.update(level=20,manuals=['jade_marrows'],active_manual='jade_marrows');g.yaochi_state.update(merit=100000,earned=100000);g.heavenly_court['open_election']=None
                        g.settings.update(silent_events=True,combat_popup=False,court_election_popup=False);add_item(g.player,'spirit_stone',10**8);e.store.save(g);n=opponent(e,g.id)
                        page=browser.new_page(viewport=dict(width=width,height=height),reduced_motion='reduce');errors=[];page.on('pageerror',lambda x:errors.append(str(x)))
                        page.goto(base);page.wait_for_function('!!configData && !busy');set_theme(page,theme);page.evaluate('id=>loadGame(id)',g.id)
                        def open_pool():
                            if not page.locator('#yaochi-card').is_visible():navigation_locator(page,'[data-panel-target=yaochi]').click()
                        def tab(name):page.locator(f'#yaochi-content [data-subpage="{name}"]').click()
                        def action(name,value=None,status=200):
                            node=page.locator(f'[data-gather-action="{name}"]'+(f'[data-gather-value="{value}"]' if value is not None else '')).first
                            if not node.is_visible():
                                node.evaluate("n=>{let p=n.parentElement;while(p){if(p.tagName==='DETAILS')p.open=true;p=p.parentElement;}}")
                            with page.expect_response(lambda r:r.url.endswith('/yaochi-action')) as response:click_control(node)
                            assert response.value.status==status,response.value.text();page.wait_for_function('!busy')
                        def work(kind):
                            with patch('cultivation_life.engine.orchestration.advancement._finish_action_events',return_value=None):action(kind+'_work')
                        open_pool();tab('仙圃');path=e.store._path(g.id);before=path.read_bytes();tab('仙会');tab('仙圃');assert path.read_bytes()==before
                        payload=page.evaluate("({action:'garden_lease',target_id:game.yaochi.garden.token+'|'})")
                        assert page.request.post(base+f'/api/games/{g.id}/yaochi-action',data=payload).status==200
                        action('garden_lease',status=400);assert page.locator('[data-gather-action=garden_fund]').is_visible()
                        action('garden_fund');page.locator('[aria-label="仙圃批数"]').fill('2');action('garden_configure');action('garden_order');action('garden_start');work('garden');action('garden_deliver')
                        assert estate(e._load(g.id))['produced']>=8 and not estate(e._load(g.id))['stock']
                        assert page.locator('#yaochi-card').evaluate('n=>n.scrollWidth<=n.clientWidth+2')
                        page.screenshot(path=str(out/f'{theme}-{width}-garden.png'),animations='disabled')
                        tab('仙会');action('fair_join','supply');age=e._load(g.id).player.age;annual=e._advance_world_year
                        def stop(game,rng,news,**kw):
                            result=annual(game,rng,news,**kw)
                            if game.player.age==age+2:
                                event=e._instantiate_event(e.events_by_id['EVT_SECT_FIRST_WARNING_001'],game,random.Random(1));event['_followup_event']=e._prepare_treasure_reward_event(game,random.Random(2));game.pending_event=event;return False
                            return result
                        with patch.object(e,'_advance_world_year',side_effect=stop):work('fair')
                        assert active(e._load(g.id))['progress']==2 and page.locator('[data-gather-action=fair_work]').is_disabled()
                        page.locator('#yaochi-toggle').click();click_control(page.locator('#event-choices button'));page.wait_for_function('!busy && game.pending_event?.id!=="EVT_SECT_FIRST_WARNING_001"')
                        click_control(page.locator('#event-choices button:enabled').first);page.wait_for_function('!busy && !game.pending_event');open_pool();tab('仙会');work('fair')
                        assert page.locator('[data-gather-action=fair_deliver]').is_disabled()
                        # Seed only owned goods; real page submission transfers that same inventory.
                        saved=e._load(g.id)
                        for key,num in active(saved)['materials'].items():add_item(saved.player,key,num)
                        e.store.save(saved);page.evaluate('id=>loadGame(id)',g.id);open_pool();tab('仙会');action('fair_deliver')
                        assert page.locator('[data-gather-action=fair_join][data-gather-value=supply]').is_disabled()
                        page.screenshot(path=str(out/f'{theme}-{width}-fair.png'),animations='disabled')
                        if theme=='dark' and width==1440:
                            action('fair_join','duel~'+n);work('fair');action('fair_fight');assert e._load(g.id).last_combat_report
                            array(e,g.id);page.evaluate('id=>loadGame(id)',g.id);open_pool();tab('仙会');action('fair_join','guard~'+n);work('fair');action('fair_fight','hold')
                            assert e._load(g.id).last_combat_report['formation_integrity_end'] is not None
                            from cultivation_life.system.building_assets import local_rows
                            building=next(r for r in local_rows(e._load(g.id)) if r.get('source_id')==estate(e._load(g.id))['id'])
                            damage(e,g.id,building['id']);page.evaluate('id=>loadGame(id)',g.id);open_pool();tab('仙圃');action('garden_rebuild')
                            assert estate(e._load(g.id))['building_status']=='intact'
                        assert not errors,errors;page.close();print(f'{theme} {width}x{height}: actual lease, production, stale recovery, interrupted fair, followup, award and layout passed',flush=True)
                    browser.close()
            finally:http.shutdown();http.server_close()
if __name__=='__main__':main()
