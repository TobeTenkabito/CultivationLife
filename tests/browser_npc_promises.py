"""Click promised duels, recover stale forms and preserve actual event rewards."""
import random
import os
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
from cultivation_life.models import SectNpc
from scripts.browser_navigation import navigation_locator,click_control,reveal_subpage


def prepare(engine):
    identity=engine.create_game('凤仪亭验收','supreme_metal','dao',329,preset_id='core')['id']
    g=engine._load(identity);p=g.player;p.gender='female';g.pending_event=None
    actor=SectNpc('promise-lover','吕奉先','故人',3,1,80,10000,world=p.world,
        location_id=p.location_id,affinity=80,spirit_root='supreme_metal')
    owner=SectNpc('promise-owner','董仲颖','正主',1,1,50,10000,world=p.world,
        location_id=p.location_id,spirit_root='supreme_metal')
    other=SectNpc('promise-away','远方人物','故人',1,1,50,10000,world=p.world,
        location_id='elsewhere',spirit_root='supreme_metal')
    g.notable_npcs.update({n.id:n for n in (actor,owner,other)})
    p.dao_companion={'id':actor.id,'since_age':p.age}
    engine._set_concubine_status(g,dict(owner_id=owner.id,owner_name=owner.name,
        owner_realm_index=1,owner_layer=1,owner_realm_name='练气',owner_world=p.world),forced=True)
    engine.store.save(g)
    return identity


def main():
    output=ROOT/'build'/'npc-promise-ui';output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        engine=GameEngine(ROOT,Path(directory)/'saves')
        class Quiet(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',Path(directory)):
            http=ThreadingHTTPServer(('127.0.0.1',0),Quiet)
            threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    smoke=bool(os.environ.get('NPC_PROMISE_UI_SMOKE'))
                    for theme in ('a' if smoke else 'abdf'):
                        for width,height in (((1440,1000),) if smoke else ((1440,1000),(412,915),(915,412))):
                            identity=prepare(engine)
                            page=browser.new_page(viewport={'width':width,'height':height})
                            page.set_default_timeout(60000)
                            errors=[];posts=[]
                            page.on('pageerror',lambda error:errors.append(str(error)))
                            page.on('dialog',lambda dialog:dialog.accept())
                            page.on('request',lambda req:posts.append(req.post_data_json) if req.method=='POST' and req.url.endswith('/npc-contact') else None)
                            page.goto(f'http://127.0.0.1:{http.server_port}')
                            page.wait_for_function('!!configData')
                            page.evaluate('t=>document.querySelector(`[data-theme-picker=dialog] [data-theme-choice="${t}"]`).click()',theme)
                            page.evaluate('GameThemes.saved')
                            page.evaluate('async id=>loadGame(id)',identity)
                            def open_form():
                                navigation_locator(page,'[data-panel-target=relationship]').click()
                                search=page.locator('#npc-contacts input[type=search]')
                                reveal_subpage(page,search).fill('吕奉先')
                                click_control(page.locator('#npc-contacts .contact-person').first)
                                click_control(page.locator('[data-contact-action=promise]'))
                                page.get_by_label('指定交战目标',exact=True).select_option('promise-owner')
                            open_form()
                            assert not page.locator('.contact-promise option[value="promise-away"]').count()
                            assert page.locator('.contact-promise').evaluate('e=>e.scrollWidth<=e.clientWidth+2')
                            if theme=='a' and width==1440:
                                g=engine._load(identity)
                                event=engine._prepare_treasure_reward_event(g,random.Random(3))
                                follow=engine._prepare_treasure_reward_event(g,random.Random(4))
                                event['_followup_event']=follow;g.pending_event=event;engine.store.save(g)
                                with page.expect_response(lambda r:r.url.endswith('/npc-contact')) as response:
                                    page.get_by_role('button',name='确认约战',exact=True).click()
                                assert response.value.status==400
                                page.wait_for_function('!busy && !!game.pending_event')
                                actual=engine.store.load(identity)
                                assert actual.pending_event['runtime']==event['runtime']
                                assert actual.pending_event['_followup_event']['runtime']==follow['runtime']
                                assert actual.notable_npcs['promise-owner'].alive
                                assert len(posts)==1
                                navigation_locator(page,'[data-panel-target=relationship]').click()
                                assert page.locator('[data-contact-action=promise]').is_disabled()
                                for _ in range(2):
                                    with page.expect_response(lambda r:r.url.endswith('/choice')):
                                        click_control(page.locator('#event-choices button').first)
                                    page.wait_for_function('!busy')
                                assert engine.store.load(identity).pending_event is None
                                claimed=[r for r in engine.store.load(identity).history if r.result=='treasure_claimed']
                                assert len(claimed)==2
                                open_form()
                            with page.expect_response(lambda r:r.url.endswith('/npc-contact')) as response:
                                page.get_by_role('button',name='确认约战',exact=True).click()
                            assert response.value.status==200
                            page.wait_for_function('!busy')
                            actual=engine.store.load(identity)
                            assert not actual.notable_npcs['promise-owner'].alive
                            assert actual.player.milestones['fengyi_pavilion']==1
                            assert actual.player.concubine_status is None
                            assert page.locator('[data-contact-action=promise]').is_disabled()
                            assert posts[-1]['target_id']=='promise-owner'
                            page.screenshot(path=str(output/f'{theme}-{width}.png'),animations='disabled')
                            page.reload()
                            try:page.wait_for_function('!!configData')
                            except Exception:
                                print('Reload errors:',errors,flush=True)
                                print(page.locator('body').inner_text()[-1200:],flush=True)
                                page.screenshot(path=str(output/'reload-failure.png'))
                                raise
                            page.evaluate('async id=>loadGame(id)',identity)
                            assert not page.evaluate('game.new_achievements.some(r=>r.name==="凤仪亭")')
                            assert not errors,errors
                            page.close()
                    browser.close()
            finally:
                http.shutdown();http.server_close()
    print('NPC promises UI passed: real duel, Fengyi unlock, stale recovery, two rewards, no repeated POST, '+('smoke case' if smoke else 'four themes x three viewports'))


if __name__=='__main__':main()
