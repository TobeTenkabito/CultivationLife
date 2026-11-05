"""Real UI contracts, inheritance training, avatar and rebellion event choices."""
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
from cultivation_life.runtime import now_iso
from cultivation_life.system import mentorship as m, mentorship_advanced as a
from scripts.browser_navigation import click_control, navigation_locator, reveal_subpage


def main():
    with tempfile.TemporaryDirectory(dir=ROOT/'build') as directory:
        engine = GameEngine(ROOT, Path(directory)/'saves')
        view = engine.create_game('传承验收', 'supreme_metal', 'demonic', 435,
                                 custom_start={'world':'human', 'realm_index':4, 'layer':5, 'sect':'new'})
        game = engine._load(view['id']);p = game.player
        game.pending_event = None;p.opportunity = 10**9
        npc = SectNpc('inherit-browser', '传承验收弟子', '', 2, 1, 30, 500,
                       world=p.world, location_id=p.location_id, spirit_root='supreme_metal',
                       body_training=10, divine_sense_rank=17, gender='female')
        game.world_npcs[npc.id] = npc
        p.disciples.append(game.link_relationship({'id':npc.id}))
        m.admit(game, 'player', npc.id).update(rank='heir', loyalty=100)
        engine.store.save(game)
        class Handler(server.Handler):
            def log_message(self, *args): pass
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', Path(directory)):
            http = ThreadingHTTPServer(('127.0.0.1',0), Handler)
            threading.Thread(target=http.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch();page = browser.new_page(viewport={'width':1440,'height':960})
                    errors=[];page.on('pageerror', lambda e:errors.append(str(e)))
                    page.on('dialog', lambda dialog:dialog.accept())
                    base = f'http://127.0.0.1:{http.server_port}'
                    page.goto(base);page.wait_for_function('!!configData&&!busy')
                    def load():
                        page.evaluate('''async id=>{await loadGame(id);await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));}''', game.id)
                        page.wait_for_function('!busy')
                    def school():
                        if not page.locator('#relationship-card').is_visible(): navigation_locator(page,'[data-panel-target=relationship]').click()
                        reveal_subpage(page, page.locator('#mentorship-panel'))
                        page.wait_for_selector('#mentorship-panel')
                    def contract(action):
                        row = page.locator('[data-mentorship-npc="inherit-browser"]')
                        details = row.locator('details')
                        if details.get_attribute('open') is None: click_control(details.locator('summary'))
                        details.get_by_role('combobox').select_option(action)
                        with page.expect_response(lambda r:r.url.endswith('/mentorship-action')) as response:
                            click_control(details.get_by_role('button', name='办理传承事务', exact=True))
                        assert response.value.ok, response.value.text()
                        page.wait_for_function('!busy')
                    load();school();contract('pact_avatar')
                    assert m.record(engine.store.load(game.id), 'player', npc.id)['advanced']['pact_avatar']
                    row = page.locator('[data-mentorship-npc="inherit-browser"]')
                    click_control(row.get_by_role('button', name='培养', exact=True))
                    page.wait_for_selector('#npc-development-submit')
                    page.get_by_role('combobox', name='培养方式', exact=True).select_option('inherit_infuse')
                    with page.expect_response(lambda r:r.url.endswith('/npc-development')) as response:
                        page.locator('#npc-development-submit').click()
                    assert response.value.ok,response.value.text();page.wait_for_function('!busy')
                    assert a.precision(engine.store.load(game.id),npc.id)==2
                    page.locator('#npc-development-dialog').get_by_role('button',name='关闭',exact=True).click()
                    school();contract('refine_avatar')
                    current = engine.store.load(game.id)
                    assert a.avatar_person(current).id == npc.id and not current.player.disciples
                    assert page.locator('#mentorship-panel').get_by_text('身外化身',exact=False).count()
                    with page.expect_response(lambda r:r.url.endswith('/mentorship-action')) as response:
                        click_control(page.get_by_role('button',name='停止化身出战',exact=True))
                    assert response.value.ok,response.value.text();page.wait_for_function('!busy')
                    assert not engine.store.load(game.id).mentorship_state['avatar']['enabled']
                    # A stale enabled button must recover the latest ordinary state.
                    current = engine.store.load(game.id);current.updated_at=now_iso();engine.store.save(current)
                    with page.expect_response(lambda r:r.url.endswith('/mentorship-action')) as response:
                        click_control(page.get_by_role('button',name='启用化身出战',exact=True))
                    assert not response.value.ok;page.wait_for_function('!busy')
                    assert not engine.store.load(game.id).mentorship_state['avatar']['enabled']
                    for width in (1440,390):
                        page.set_viewport_size({'width':width,'height':960});page.wait_for_timeout(200)
                        page.screenshot(path=str(ROOT/'build'/f'mentorship-stage2-{width}.png'),full_page=True)
                        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                    # Real pending-event projection and option submission, not internal resolver.
                    current = engine.store.load(game.id)
                    current.pending_event = engine._instantiate_event(engine.events_by_id[a.EVENT], current, random.Random(1))
                    current.pending_event['runtime']={'rebels':[]}
                    engine.store.save(current);load()
                    if page.locator('#relationship-card').is_visible(): page.locator('#relationship-toggle').click()
                    with page.expect_response(lambda r:r.url.endswith('/choice')) as response:
                        page.locator('#event-choices button').filter(has_text='解除叛师').click()
                    assert response.value.ok,response.value.text();page.wait_for_function('!busy')
                    assert engine.store.load(game.id).pending_event is None
                    current = engine.store.load(game.id)
                    rebel = SectNpc('rebellion-browser', '叛师验收弟子', '', 2, 2, 30, 500,
                                    world=current.player.world, location_id=current.player.location_id,
                                    spirit_root='supreme_metal', gender='male')
                    current.world_npcs[rebel.id] = rebel
                    current.player.disciples.append(current.link_relationship({'id':rebel.id}))
                    m.admit(current, 'player', rebel.id).update(rank='true', loyalty=10)
                    current.mentorship_state['avatar']['enabled'] = True
                    current.settings['combat_popup'] = True
                    current.pending_event = engine._instantiate_event(engine.events_by_id[a.EVENT], current, random.Random(2))
                    current.pending_event['runtime'] = {'rebels':[rebel.id]}
                    engine.store.save(current);load()
                    with page.expect_response(lambda r:r.url.endswith('/choice')) as response:
                        page.locator('#event-choices button').filter(has_text='应战平叛').click()
                    assert response.value.ok,response.value.text();page.wait_for_function('!busy')
                    if not page.evaluate('CombatReplay.diagnostics().active'):
                        navigation_locator(page,'#battle-report-open').click()
                    page.wait_for_function('CombatReplay.diagnostics().active && !document.querySelector("[data-combat-replay]").disabled')
                    assert page.evaluate('game.last_combat_report.visual.teams.hero.some(n=>n.id==="inherit-browser"&&n.kind==="external_avatar")')
                    assert len(page.evaluate('CombatReplay.diagnostics().participants')) >= 3
                    page.evaluate('CombatReplay.seek(.8)')
                    page.screenshot(path=str(ROOT/'build'/'mentorship-stage2-combat.png'),full_page=True)
                    assert not errors,errors
                    browser.close()
                    print(json.dumps({'ok':True,'contracts':True,'precision':True,'avatar':True,'stale_recovery':True,'event_choice':True,'combat_animation':True,'screens':[1440,390]}))
            finally: http.shutdown();http.server_close()


if __name__=='__main__':main()
