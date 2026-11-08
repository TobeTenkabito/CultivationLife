"""Finale 1.0: actual pages, stale recovery, event followup and original rebuilding."""
import random,runpy,sys,tempfile,threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.system import purple_east as story
from scripts.browser_navigation import navigation_locator,click_control,set_theme

def main():
    out=ROOT/'build/westward-finale-browser';out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='westward-finale-') as folder:
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
                        gid=e.create_game('紫气东来验收','supreme_metal','dao',7410,preset_id='true_immortal')['id']
                        runpy.run_path(str(ROOT/'tests/fixtures/westward_release.py'))['prepare_westward'](e,gid)
                        page=browser.new_page(viewport=dict(width=width,height=height),reduced_motion='reduce');errors=[];page.on('pageerror',lambda x:errors.append(str(x)))
                        page.goto(base);page.wait_for_function('!!configData && !busy');set_theme(page,theme);page.evaluate('id=>loadGame(id)',gid)
                        def panel(tab):
                            if not page.locator('#yaochi-card').is_visible():navigation_locator(page,'[data-panel-target=yaochi]').click()
                            page.locator('#yaochi-content [data-subpage="'+tab+'"]').click()
                        def action(name,label=None,status=200):
                            node=page.locator('[data-finale-action="'+name+'"]')
                            if label:node=node.filter(has_text=label)
                            node=node.first
                            with page.expect_response(lambda r:r.url.endswith('/yaochi-action')) as response:click_control(node)
                            assert response.value.status==status,response.value.text();page.wait_for_function('!busy')
                        def work():
                            with patch('cultivation_life.engine.orchestration.advancement._finish_action_events',return_value=None):action('purple_work')
                        def step():work();action('purple_submit')
                        panel('仙籍与功德');assert page.locator('.finale-current').inner_text().startswith('散仙')
                        assert page.locator('[data-finale-action=identity_retire]').is_disabled()
                        panel('紫气东来');path=e.store._path(gid);before=path.read_bytes();panel('仙籍与功德');panel('紫气东来');assert path.read_bytes()==before
                        payload=page.evaluate("({action:'purple_start',target_id:game.yaochi.purple_east.token+'|'})")
                        assert page.request.post(base+f'/api/games/{gid}/yaochi-action',data=payload).status==200
                        action('purple_start',status=400)
                        age=e._load(gid).player.age;annual=e._advance_world_year
                        def stop(game,rng,news,**kw):
                            result=annual(game,rng,news,**kw)
                            if game.player.age==age+2:
                                ev=e._instantiate_event(e.events_by_id['EVT_SECT_FIRST_WARNING_001'],game,random.Random(1));ev['_followup_event']=e._prepare_treasure_reward_event(game,random.Random(2));game.pending_event=ev;return False
                            return result
                        with patch.object(e,'_advance_world_year',side_effect=stop):work()
                        assert story.work(e._load(gid))['progress']==2 and page.locator('[data-finale-action=purple_work]').is_disabled()
                        page.locator('#yaochi-toggle').click();click_control(page.locator('#event-choices button:enabled').first);page.wait_for_function('!busy && game.pending_event?.id!=="EVT_SECT_FIRST_WARNING_001"')
                        click_control(page.locator('#event-choices button:enabled').first);page.wait_for_function('!busy && !game.pending_event')
                        panel('紫气东来');step();action('purple_mitigate','出资');step()
                        assert page.locator('.gather-card').filter(has_text='公共修持').locator('[data-finale-action=purple_plan]').is_disabled()
                        page.screenshot(path=str(out/f'{theme}-{width}-hearing.png'),animations='disabled')
                        action('purple_civic');step();action('purple_plan','提交方案');step();action('purple_build');step()
                        g=e._load(gid);assert story.state(g)['phase']=='complete' and story.original(g)['owner']==dict(kind='player',id=gid) and story.original(g)['public']
                        page.evaluate('id=>loadGame(id)',gid);panel('紫气东来');assert not page.locator('[data-finale-action=purple_start]').count()
                        assert page.locator('#yaochi-card').evaluate('n=>n.scrollWidth<=n.clientWidth+2')
                        page.screenshot(path=str(out/f'{theme}-{width}-complete.png'),animations='disabled')
                        panel('专修');assert page.locator('.yaochi-service').count()==4
                        with page.expect_response(lambda r:r.url.endswith('/yaochi-action')) as response:click_control(page.locator('[data-service=guidance] [data-westward-action=westward_start_merit]'))
                        assert response.value.status==200;page.wait_for_function('!busy')
                        with patch('cultivation_life.engine.orchestration.advancement._finish_action_events',return_value=None):
                            with page.expect_response(lambda r:r.url.endswith('/yaochi-action')) as response:click_control(page.locator('[data-westward-action=westward_work]'))
                        assert response.value.status==200;page.wait_for_function('!busy');assert e._load(gid).yaochi_state['westward']['project']['progress']==10
                        with page.expect_response(lambda r:r.url.endswith('/yaochi-action')):click_control(page.locator('[data-westward-action=westward_claim]'))
                        page.wait_for_function('!busy');assert not e._load(gid).yaochi_state['westward'].get('project')
                        assert page.locator('[data-service=body] [data-westward-action=westward_start_merit]').is_disabled()
                        page.screenshot(path=str(out/f'{theme}-{width}-guidance.png'),animations='disabled')
                        assert not errors,errors;page.close();print(f'{theme} {width}x{height}: four chapters, real rights, reload, event followup, stale recovery, guidance and disabled options passed',flush=True)
                    browser.close()
            finally:http.shutdown();http.server_close()
if __name__=='__main__':main()
