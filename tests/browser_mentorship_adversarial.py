"""Real old admission and expulsion choices against the new school ledger."""
import json
import random
import sys
import tempfile
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.models import SectNpc
from cultivation_life.runtime import encode_rng
from cultivation_life.system import mentorship as m
from scripts.browser_navigation import navigation_locator, click_control


def main():
    with tempfile.TemporaryDirectory(dir=ROOT/'build') as directory:
        engine = GameEngine(ROOT, Path(directory)/'saves')
        view = engine.create_game('师承对抗验收','supreme_metal','dao',913,
                                 custom_start=dict(world='human',realm_index=3,layer=5,sect='new'))
        game = engine._load(view['id']);p = game.player;game.pending_event = None
        old = SectNpc('old-mentor-browser','已故师父','',4,6,100,900,world=p.world,location_id=p.location_id)
        teacher = SectNpc('new-mentor-browser','新师父验收','长老',4,8,100,900,world=p.world,
                          location_id=p.location_id,faction_id=p.faction_id,spirit_root='supreme_metal')
        game.world_npcs[old.id] = old;game.sects[p.faction_id].npcs.append(teacher)
        p.master = game.link_relationship({'id':old.id})
        m.admit(game,old.id,'player');p.master['items'] = {'npc_training_dao_body_1':4}
        old.alive = False;game.rng_state = encode_rng(random.Random(1));engine.store.save(game)
        class Handler(server.Handler):
            def log_message(self,*args): pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',Path(directory)):
            http = ThreadingHTTPServer(('127.0.0.1',0),Handler)
            threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch();page = browser.new_page(viewport=dict(width=1440,height=960))
                    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                    page.goto(f'http://127.0.0.1:{http.server_port}')
                    page.wait_for_function('!!configData&&!busy')
                    def load():
                        page.evaluate('''async id=>{await loadGame(id);await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));}''',game.id)
                        page.wait_for_function('!busy')
                    load()
                    if not page.locator('#faction-card').is_visible(): navigation_locator(page,'[data-panel-target=faction]').click()
                    row = page.locator('#faction-roster-list .roster-row').filter(has_text=teacher.name)
                    with page.expect_response(lambda r:r.url.endswith('/faction-relationship')) as response:
                        click_control(row.get_by_role('button',name='拜师',exact=True,include_hidden=True))
                    assert response.value.ok,response.value.text();page.wait_for_function('!busy')
                    saved = engine.store.load(game.id)
                    assert saved.player.master['id']==teacher.id
                    history=m.record(saved,old.id,'player')
                    assert history['status']=='departed' and history['former_relation']['items']['npc_training_dao_body_1']==4
                    event = next(e for e in engine.events_by_id.values() if any(
                        effect.get('type')=='relationship_sanction' and effect.get('role')=='master'
                        for choice in e.get('choices',[]) for effect in choice.get('effects',[])))
                    saved.pending_event=engine._instantiate_event(event,saved,random.Random(2))
                    saved.pending_event['runtime']={'role':'master','id':teacher.id,'name':teacher.name}
                    engine.store.save(saved);load()
                    with page.expect_response(lambda r:r.url.endswith('/choice')) as response:
                        page.locator('#event-choices button').filter(has_text='领命退出师门').click()
                    assert response.value.ok,response.value.text();page.wait_for_function('!busy')
                    saved=engine.store.load(game.id)
                    assert saved.player.master is None and saved.pending_event is None
                    assert m.record(saved,teacher.id,'player')['status']=='expelled'
                    assert m.record(saved,old.id,'player')['former_relation']['items']['npc_training_dao_body_1']==4
                    assert not errors,errors
                    browser.close();print(json.dumps({'ok':True,'dead_master_readmission':True,'legacy_expulsion_choice':True,'original_gifts_preserved':True}))
            finally:http.shutdown();http.server_close()


if __name__=='__main__':main()
