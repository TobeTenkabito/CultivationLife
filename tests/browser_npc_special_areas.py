"""Real dungeon UI audit: read-only training, blocked POST, exit recovery."""
import sys
import copy
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
from cultivation_life.system import trial_sites
from cultivation_life.relationship_records import find_person
from scripts.browser_navigation import navigation_locator, reveal_subpage
from browser_npc_recruitment_adversarial import load
from test_npc_development_special_areas import make_game, enter_guixu, stable
from test_trial_sites import enter, complete_events, act


def main():
    with tempfile.TemporaryDirectory() as folder:
        e=GameEngine(ROOT,Path(folder))
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',e),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    for width,height in [(1440,960),(390,844)]:
                        for kind in ('guixu','trial'):
                            g=make_game(e)
                            n=find_person(g,'outside-student')
                            g.player.dao_companion=g.link_relationship({'id':n.id})
                            g.player.offspring=[dict(copy.deepcopy(n.to_dict()),cultivation_started=True)]
                            if kind=='guixu':g=enter_guixu(e,g)
                            else:
                                g.player.location_id=trial_sites.bound_site(g,e.maps,'human')['location_id']
                                find_person(g,'outside-student').location_id=g.player.location_id
                                e.store.save(g);enter(e,g);complete_events(e,g.id)
                            page=browser.new_page(viewport=dict(width=width,height=height))
                            errors=[];page.on('pageerror',lambda ex:errors.append(str(ex)))
                            base=f'http://127.0.0.1:{http.server_port}'
                            page.context.set_extra_http_headers({'Origin':base})
                            page.goto(base)
                            assert not errors,errors
                            page.wait_for_function("typeof configData!=='undefined'&&!!configData&&!busy")
                            load(page,g.id)
                            before=stable(e,g.id)
                            navigation_locator(page,'[data-panel-target=npc-development]').click()
                            page.wait_for_function("document.querySelector('#npc-development-dialog').textContent.includes('归墟')||document.querySelector('#npc-development-dialog').textContent.includes('试境')")
                            assert not page.locator('#npc-development-submit').count()
                            assert e.store._path(g.id).read_bytes()==before
                            for route,payload in [('npc-development',dict(action='train',kind='npc',
                                target_id='outside-student',axis='body',method='infuse',batches=1,
                                revision=e.store.load(g.id).updated_at)),('disciple-gift',dict(
                                disciple_id='outside-student',kind='technique',content_id='TECH_BASIC_QI'))]:
                                response=page.request.post(base+f'/api/games/{g.id}/{route}',data=payload)
                                assert response.status==400 and e.store._path(g.id).read_bytes()==before
                            page.locator('#npc-development-dialog > header button').click()
                            navigation_locator(page,'[data-panel-target=relationship]').click()
                            button=page.locator('#relationship-list .relationship-row').filter(has_text='outside-student').locator('button').filter(has_text='传功')
                            reveal_subpage(page,button)
                            assert button.is_disabled(),f'{kind}: legacy teaching appears available inside dungeon'
                            companion=page.locator('#dao-companion-list button').filter(has_text='替换其主修')
                            reveal_subpage(page,companion)
                            assert companion.is_disabled()
                            navigation_locator(page,'[data-panel-target=family]').click()
                            family=page.locator('[data-family-member="outside-student"] button').filter(has_text='传授')
                            reveal_subpage(page,family)
                            assert family.is_disabled()
                            if kind=='guixu':e.guixu_action(g.id,'return',{})
                            else:act(e,g.id,'pause')
                            load(page,g.id)
                            navigation_locator(page,'[data-panel-target=npc-development]').click()
                            page.wait_for_selector('#npc-development-submit')
                            page.get_by_label('培养方向',exact=True).select_option('body')
                            page.get_by_label('培养方式',exact=True).select_option('infuse')
                            with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/npc-development')) as response:
                                page.locator('#npc-development-submit').click()
                            assert response.value.ok,response.value.text()
                            page.wait_for_function('!busy')
                            assert find_person(e.store.load(g.id),'outside-student').body_training==20
                            assert not errors,errors
                            page.screenshot(path=str(ROOT/'build'/f'npc-special-{kind}-{width}.png'))
                            page.close()
                    browser.close()
            finally:http.shutdown();http.server_close()
    print('Special-area UI passed: Guixu and trial, desktop/mobile, blocked new/legacy requests, exit recovery')


if __name__=='__main__':main()
