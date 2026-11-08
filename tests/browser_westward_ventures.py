"""Two themes and three sizes: real page submissions, stale recovery and events."""
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
from cultivation_life.economy_content import material_id
from cultivation_life.system import yaochi_antiquity as ancient,court_projects as council
from test_westward_ventures import seats,training_offer
from test_earth_network import travel
from scripts.browser_navigation import navigation_locator,click_control,set_theme

def main():
    out=ROOT/'build/westward-ventures-browser';out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='westward-ventures-') as folder:
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
                        g=e._load(e.create_game('访古与议政验收','supreme_metal','dao',7410,preset_id='true_immortal')['id']);g.pending_event=None;g.player.next_tribulation_age=None
                        g.player.location_id=ancient.SITES['archive']['location'];g.heavenly_court['open_election']=None
                        g.settings.update(silent_events=True,combat_popup=False,court_election_popup=False)
                        add_item(g.player,'spirit_stone',10**8);add_item(g.player,material_id('celestial',4,'ore_conduct'),100);e.store.save(g)
                        page=browser.new_page(viewport=dict(width=width,height=height),reduced_motion='reduce');errors=[];page.on('pageerror',lambda x:errors.append(str(x)))
                        page.goto(base);page.wait_for_function('!!configData && !busy');set_theme(page,theme);page.evaluate('id=>loadGame(id)',g.id)
                        def panel(kind,tab):
                            if not page.locator('#'+kind+'-card').is_visible():navigation_locator(page,'[data-panel-target='+kind+']').click()
                            page.locator('#'+kind+'-content [data-subpage="'+tab+'"]').click()
                        def action(name,value=None,status=200):
                            node=page.locator('[data-venture-action="'+name+'"]'+('[data-venture-value="'+value+'"]' if value is not None else '')).first
                            if not node.is_visible():node.evaluate("n=>{let p=n.parentElement;while(p){if(p.tagName==='DETAILS')p.open=true;p=p.parentElement;}}")
                            with page.expect_response(lambda r:r.url.endswith('/yaochi-action')) as response:click_control(node)
                            assert response.value.status==status,response.value.text();page.wait_for_function('!busy')
                        def work(kind):
                            with patch('cultivation_life.engine.orchestration.advancement._finish_action_events',return_value=None):action(kind+'_work')
                        panel('yaochi','访古');path=e.store._path(g.id);before=path.read_bytes();panel('yaochi','仙会');panel('yaochi','访古');assert path.read_bytes()==before
                        payload=page.evaluate("({action:'antiquity_start',target_id:game.yaochi.antiquity.token+'|archive'})")
                        assert page.request.post(base+f'/api/games/{g.id}/yaochi-action',data=payload).status==200
                        action('antiquity_start','archive',400)
                        age=e._load(g.id).player.age;annual=e._advance_world_year
                        def stop(game,rng,news,**kw):
                            result=annual(game,rng,news,**kw)
                            if game.player.age==age+2:
                                ev=e._instantiate_event(e.events_by_id['EVT_SECT_FIRST_WARNING_001'],game,random.Random(1));ev['_followup_event']=e._prepare_treasure_reward_event(game,random.Random(2));game.pending_event=ev;return False
                            return result
                        with patch.object(e,'_advance_world_year',side_effect=stop):work('antiquity')
                        assert ancient.current(e._load(g.id))['progress']==2 and page.locator('[data-venture-action=antiquity_work]').is_disabled()
                        page.locator('#yaochi-toggle').click();click_control(page.locator('#event-choices button:enabled').first);page.wait_for_function('!busy && game.pending_event?.id!=="EVT_SECT_FIRST_WARNING_001"')
                        click_control(page.locator('#event-choices button:enabled').first);page.wait_for_function('!busy && !game.pending_event')
                        panel('yaochi','访古');work('antiquity');action('antiquity_open','study');work('antiquity')
                        page.screenshot(path=str(out/f'{theme}-{width}-antiquity.png'),animations='disabled')
                        action('antiquity_choose','salvage');assert page.locator('[data-venture-action=antiquity_return]').is_disabled()
                        travel(e,g.id,'expanse_celestial_8');page.evaluate('id=>loadGame(id)',g.id);panel('yaochi','访古');action('antiquity_return')
                        seats(e,g.id);training_offer(e,g.id);page.evaluate('id=>loadGame(id)',g.id);panel('heavenly-court','项目议政')
                        page.locator('[aria-label="公共修持预算目标"]').select_option(label='来访修士 · 公共修持');action('council_propose');work('council');action('council_vote')
                        assert council.current(e._load(g.id))['status']=='approved'
                        action('council_execute');work('council');action('council_finish');action('council_review');work('council');action('council_finish')
                        assert e._load(g.id).world_npcs['public-scholar'].layer==2
                        if theme=='dark' and width==1440:
                            from cultivation_life.building_rules import config as building_config
                            from test_earth_network import fund
                            from test_earth_temple import build,fulfill
                            site=next(r['location_id'] for r in building_config()['cities']['celestial'] if r['population']=='mixed')
                            travel(e,g.id,site);fund(e,g.id);build(e,g.id);page.evaluate('id=>loadGame(id)',g.id);panel('heavenly-court','项目议政')
                            host=page.locator('.ventures .gather-card').filter(has=page.locator('[aria-label="地仙神位与服务协议目标"]'))
                            with page.expect_response(lambda r:r.url.endswith('/yaochi-action')) as response:click_control(host.locator('[data-venture-action=council_propose]'))
                            assert response.value.status==200;page.wait_for_function('!busy');work('council');action('council_vote')
                            assert page.locator('[data-venture-action=council_execute]').is_disabled();action('council_public')
                            assert page.locator('[data-venture-action=council_execute]').is_disabled()
                            fulfill(e,g.id,'teach');page.evaluate('id=>loadGame(id)',g.id);panel('heavenly-court','项目议政')
                            action('council_execute');work('council');action('council_finish');action('council_review');work('council');action('council_finish')
                        assert page.locator('#heavenly-court-card').evaluate('n=>n.scrollWidth<=n.clientWidth+2')
                        page.screenshot(path=str(out/f'{theme}-{width}-council.png'),animations='disabled')
                        assert not errors,errors;page.close();print(f'{theme} {width}x{height}: real ruins, interruption, followup, stale restore, travel, vote, public training and receipt passed',flush=True)
                    browser.close()
            finally:http.shutdown();http.server_close()
if __name__=='__main__':main()
