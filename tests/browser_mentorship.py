"""Real admission, rank appointment, old support buttons and stale UI recovery."""
import json
import random
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
from cultivation_life.runtime import encode_rng, now_iso
from cultivation_life.system import mentorship as m
from scripts.browser_navigation import navigation_locator, click_control, reveal_subpage


def main():
    with tempfile.TemporaryDirectory(dir=ROOT/'build') as directory:
        engine=GameEngine(ROOT,Path(directory)/'saves')
        state=engine.create_game('师门验收','supreme_metal','dao',570,
            custom_start=dict(world='human',realm_index=3,layer=5,sect='new'))
        game=engine.store.load(state['id']);p=game.player
        teacher=SectNpc('school-browser-teacher','验收师父','授业长老',4,7,80,900,
                        world=p.world,location_id=p.location_id,spirit_root=p.spirit_root,affinity=90,gender='female')
        student=SectNpc('school-browser-student','程澄验收','门人',1,2,25,200,
                        world=p.world,location_id=p.location_id,spirit_root=p.spirit_root,gender='male')
        game.sects[p.faction_id].npcs.extend([teacher,student])
        teacher.faction_id=student.faction_id=p.faction_id
        p.opportunity=100000;game.pending_event=None;game.rng_state=encode_rng(random.Random(1))
        engine.store.save(game)
        class Handler(server.Handler):
            def log_message(self,*args): pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',Path(directory)):
            http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch();page=browser.new_page(viewport=dict(width=1440,height=960))
                    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                    base=f'http://127.0.0.1:{http.server_port}'
                    page.goto(base);page.wait_for_function('!!configData&&!busy')
                    page.evaluate('id=>loadGame(id)',game.id);page.wait_for_function('!busy&&!!game')
                    assert not engine.store.load(game.id).mentorship_state
                    if not page.locator('#faction-card').is_visible(): navigation_locator(page,'[data-panel-target=faction]').click()
                    roster=page.locator('#faction-roster-list .roster-row').filter(has_text=teacher.name)
                    page.wait_for_function('!!game?.faction?.roster?.find(n=>n.id==="school-browser-teacher")')
                    assert not errors,errors
                    assert roster.count(),page.locator('#faction-roster-list').inner_text()
                    with page.expect_response(lambda r:r.url.endswith('/faction-relationship')) as response:
                        click_control(roster.get_by_role('button',name='拜师',exact=True,include_hidden=True))
                    assert response.value.ok,response.value.text()
                    page.wait_for_function('!busy')
                    current=engine.store.load(game.id)
                    assert current.player.master['id']==teacher.id
                    assert len(m.rows(current,teacher.id))==3
                    original={key for key in current.notable_npcs if key.startswith('school:')}
                    current.rng_state=encode_rng(random.Random(1));engine.store.save(current)
                    page.evaluate('id=>loadGame(id)',game.id);page.wait_for_function('!busy')
                    if not page.locator('#faction-card').is_visible(): navigation_locator(page,'[data-panel-target=faction]').click()
                    roster=page.locator('#faction-roster-list .roster-row').filter(has_text=student.name)
                    with page.expect_response(lambda r:r.url.endswith('/faction-relationship')) as response:
                        click_control(roster.get_by_role('button',name='收徒',exact=True,include_hidden=True))
                    assert response.value.ok,response.value.text()
                    page.wait_for_function('!busy')
                    navigation_locator(page,'[data-panel-target=relationship]').click()
                    panel=page.locator('#mentorship-panel')
                    reveal_subpage(page,panel)
                    page.wait_for_selector('#mentorship-panel')
                    assert len(engine.store.load(game.id).mentorship_state['schools'])==2
                    assert panel.locator('.npc-art-avatar img').count()>=3
                    row=panel.locator(f'[data-mentorship-npc="{student.id}"]')
                    choice=row.get_by_role('combobox',include_hidden=True);reveal_subpage(page,choice);choice.select_option('heir')
                    with page.expect_response(lambda r:r.url.endswith('/mentorship-action')) as response:
                        click_control(row.get_by_role('button',name='任命',exact=True,include_hidden=True))
                    assert response.value.ok,response.value.text();page.wait_for_function('!busy')
                    assert m.record(engine.store.load(game.id),'player',student.id)['rank']=='heir'
                    with page.expect_response(lambda r:r.url.endswith('/master-request')) as response:
                        click_control(page.locator('#relationship-list').get_by_role('button',name='请教修行',exact=True,include_hidden=True))
                    assert response.value.ok,response.value.text();page.wait_for_function('!busy')
                    assert page.locator('#relationship-list').get_by_role('button',name='请教修行',exact=True,include_hidden=True).is_disabled()
                    with page.expect_response(lambda r:r.url.endswith('/mentorship-action')) as response:
                        click_control(panel.get_by_role('button',name='呈交心得 · 机缘',exact=False,include_hidden=True).filter(has_not_text='自愿'))
                    assert response.value.ok,response.value.text();page.wait_for_function('!busy')
                    # A formerly enabled page is stale after an external command.
                    current=engine.store.load(game.id);r=m.record(current,teacher.id,'player')
                    r['rank']='registered';current.updated_at=now_iso();engine.store.save(current)
                    before=current.player.opportunity
                    with page.expect_response(lambda r:r.url.endswith('/mentorship-action')) as response:
                        click_control(panel.get_by_role('button',name='自愿呈交心得',exact=False,include_hidden=True))
                    assert not response.value.ok
                    page.wait_for_function('!busy&&game.mentorship.master.rank==="registered"')
                    assert engine.store.load(game.id).player.opportunity==before
                    assert page.locator('#relationship-list').get_by_role('button',name='请教修行',exact=True,include_hidden=True).is_disabled()
                    # The old route must reject the same restriction independently of UI.
                    response=page.request.post(base+f'/api/games/{game.id}/master-request',data={'kind':'consult'})
                    assert not response.ok
                    for width,height in [(1440,960),(390,844)]:
                        page.set_viewport_size(dict(width=width,height=height))
                        assert page.locator('#mentorship-panel').is_visible()
                        page.screenshot(path=str(ROOT/'build'/f'mentorship-{width}.png'))
                    assert {key for key in engine.store.load(game.id).notable_npcs if key.startswith('school:')}==original
                    # Exercise the generated-master event through its actual
                    # loaded choices, including rejection without school creation.
                    if page.locator('#relationship-card').is_visible(): page.locator('#relationship-toggle').click()
                    event_game=engine.create_game('事件师承','supreme_metal','dao',571,
                        custom_start=dict(world='human',realm_index=1))
                    accepted=False
                    for seed in range(10):
                        current=engine.store.load(event_game['id'])
                        current.pending_event=engine._instantiate_event(engine.events_by_id['EVT_MASTER_ENCOUNTER_001'],current,random.Random(seed))
                        current.rng_state=encode_rng(random.Random(seed));engine.store.save(current)
                        page.evaluate('''async id=>{await loadGame(id);await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));}''',current.id);page.wait_for_function('!busy&&game.pending_event?.id==="EVT_MASTER_ENCOUNTER_001"')
                        if page.locator('#relationship-card').is_visible(): page.locator('#relationship-toggle').click()
                        with page.expect_response(lambda r:r.url.endswith('/choice')) as response:
                            page.locator('#event-choices button').filter(has_text='执弟子礼').click()
                        assert response.value.ok,response.value.text();page.wait_for_function('!busy')
                        current=engine.store.load(current.id)
                        if current.player.master:
                            assert len(m.rows(current,current.player.master['id']))==3
                            accepted=True;break
                        assert not current.mentorship_state
                    assert accepted,'deterministic event fixtures did not produce an admission'
                    assert not errors,errors
                    browser.close()
                    print(json.dumps({'ok':True,'admission':'real faction clicks','peers':2,'rank':'heir',
                        'support':'old button','stale':'recovered','generated_master':'real event choice','screens':[1440,390]},ensure_ascii=False))
            finally:http.shutdown();http.server_close()


if __name__=='__main__':main()
