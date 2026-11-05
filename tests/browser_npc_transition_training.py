"""Real new/legacy teaching clicks in both independent-space types."""
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
from cultivation_life.relationship_records import find_person
from cultivation_life.runtime import now_iso
from scripts.browser_navigation import navigation_locator, click_control
from test_npc_transition_training import spatial_students
from test_other_systems_audit_fixes import snapshot
from browser_npc_recruitment_adversarial import load


def main():
    with tempfile.TemporaryDirectory() as folder:
        engine=GameEngine(ROOT,Path(folder))
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    for width,height in [(1440,960),(390,844)]:
                        for kind in ('lost','secluded'):
                            g=engine.store.load(engine.create_game('空间传法','supreme_metal','dao',771,
                                custom_start=dict(world='human',realm_index=5,layer=3))['id'])
                            g.pending_event=None;g.player.body_training=60;g.player.opportunity=100000
                            scene=spatial_students(engine,g,kind)
                            page=browser.new_page(viewport=dict(width=width,height=height))
                            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                            base=f'http://127.0.0.1:{http.server_port}'
                            page.context.set_extra_http_headers({'Origin':base})
                            page.goto(base);page.wait_for_function('!!configData&&!busy');load(page,g.id)
                            before=snapshot(engine,g.id)
                            navigation_locator(page,'[data-panel-target=npc-development]').click()
                            page.wait_for_selector('#npc-development-submit')
                            assert page.locator('#npc-development-submit').is_disabled()
                            assert engine.store._path(g.id).read_bytes()==before
                            bad=page.request.post(base+f'/api/games/{g.id}/npc-development',data=dict(
                                action='train',kind='npc',target_id='new-student',axis='body',
                                method='material',batches=1,revision=engine.store.load(g.id).updated_at))
                            assert bad.status==400 and engine.store._path(g.id).read_bytes()==before
                            page.get_by_label('培养方向',exact=True).select_option('technique')
                            # A valid page becomes stale before its real teaching button is clicked.
                            g=engine.store.load(g.id);g.updated_at=now_iso();engine.store.save(g)
                            before=snapshot(engine,g.id)
                            with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/npc-development')) as response:
                                page.get_by_role('button',name='传授所选功法').click()
                            assert response.value.status==400 and engine.store._path(g.id).read_bytes()==before
                            page.wait_for_function('!busy')
                            page.wait_for_function("!document.querySelector('#npc-development-dialog select').disabled")
                            with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/npc-development')) as response:
                                page.get_by_role('button',name='传授所选功法').click()
                            assert response.value.ok,response.value.text()
                            page.wait_for_function('!busy')
                            page.locator('#npc-development-dialog > header button').click()
                            navigation_locator(page,'[data-panel-target=relationship]').click()
                            row=page.locator('#relationship-list .relationship-row').filter(has_text='old-student')
                            with page.expect_response(lambda r:r.url.endswith('/disciple-gift')) as response:
                                click_control(row.locator('button').filter(has_text='传功'))
                            assert response.value.ok,response.value.text()
                            page.wait_for_function('!busy')
                            saved=engine.store.load(g.id)
                            for identity in ('new-student','old-student'):
                                n=find_person(saved,identity)
                                assert n.technique_levels['TECH_BASIC_QI']==1
                                assert n.location_id==scene['location_id']
                            assert saved.player.opportunity==g.player.opportunity
                            load(page,g.id)
                            navigation_locator(page,'[data-panel-target=npc-development]').click()
                            page.get_by_label('培养方向',exact=True).select_option('body')
                            assert page.locator('#npc-development-submit').is_disabled()
                            assert not errors,errors
                            page.screenshot(path=str(ROOT/'build'/f'npc-transition-{kind}-{width}.png'))
                            page.close()
                    browser.close()
            finally:
                http.shutdown();http.server_close()
    print('NPC transition browser checks passed: both spaces, desktop/mobile, stale recovery, new/legacy teaching')


if __name__=='__main__':main()
