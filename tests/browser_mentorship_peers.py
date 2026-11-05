"""Real peer menu clicks, original rewards, stale recovery and spar animation."""
import json
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.models import SectNpc
from cultivation_life.content_registry import ITEM_CATALOG, TECHNIQUE_CATALOG
from cultivation_life.rules import can_player_practice_technique
from cultivation_life.runtime import now_iso
from cultivation_life.system import mentorship as m
from cultivation_life.system.npc_techniques import learn
from scripts.browser_navigation import navigation_locator, click_control, reveal_subpage, set_theme


def main():
    with tempfile.TemporaryDirectory(dir=ROOT/'build') as directory:
        engine = GameEngine(ROOT,Path(directory)/'saves')
        view = engine.create_game('同门交流验收','supreme_metal','dao',930,
                                 custom_start=dict(world='human',realm_index=3,layer=5,sect='new'))
        game = engine.store.load(view['id']);p = game.player;game.pending_event = None
        teacher = SectNpc('peer-browser-master','授业师父','',4,7,100,1000,
                          world=p.world,location_id=p.location_id,spirit_root=p.spirit_root)
        game.world_npcs[teacher.id] = teacher;p.master = game.link_relationship({'id':teacher.id})
        m.admit(game,teacher.id,'player')
        npc = m.person(game,next(k for k in m.rows(game,teacher.id) if k != 'player'))
        npc.affinity = 60;npc.treasure_item_id = next(iter(ITEM_CATALOG));npc.treasure_looted = False
        known = {t.id for t in p.known_techniques}
        art = next(t for t in TECHNIQUE_CATALOG.values() if t.id not in known and can_player_practice_technique(p,t))
        learn(npc,art);p.opportunity = 0;game.settings['combat_popup'] = False
        engine.store.save(game)
        class Handler(server.Handler):
            def log_message(self,*args): pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',Path(directory)):
            http = ThreadingHTTPServer(('127.0.0.1',0),Handler)
            threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch();page = browser.new_page(viewport=dict(width=1440,height=960))
                    errors = [];page.on('pageerror',lambda error:errors.append(str(error)))
                    page.goto(f'http://127.0.0.1:{http.server_port}');page.wait_for_function('!!configData&&!busy')
                    page.evaluate('id=>loadGame(id)',game.id);page.wait_for_function('!busy&&!!game')
                    navigation_locator(page,'[data-panel-target=relationship]').click()
                    panel = page.locator('#mentorship-panel');reveal_subpage(page,panel)
                    row = panel.locator(f'[data-mentorship-npc="{npc.id}"]')
                    select = row.get_by_role('combobox',name=f'{npc.name}同门交流',include_hidden=True)
                    submit = row.get_by_role('button',name='办理同门事务',exact=True,include_hidden=True)
                    def choose(action):
                        details = select.locator('xpath=ancestor::details[1]')
                        reveal_subpage(page,details)
                        if not details.evaluate('n=>n.open'): click_control(details.locator('summary'))
                        select.select_option(action)
                    for action in ('peer_consult','peer_item','peer_technique'):
                        choose(action)
                        with page.expect_response(lambda r:r.url.endswith('/mentorship-action')) as response:
                            click_control(submit)
                        assert response.value.ok,response.value.text();page.wait_for_function('!busy')
                        assert select.input_value()==action, 'successful refresh must retain the selected action'
                        assert select.locator('xpath=ancestor::details[1]').evaluate('n=>n.open')
                        choose(action)
                        assert submit.is_disabled()
                    saved = engine.store.load(game.id)
                    assert saved.player.opportunity > 0 and art.id in {t.id for t in saved.player.known_techniques}
                    assert m.person(saved,npc.id).treasure_item_id is None
                    # Stale enabled spar must be rejected, refresh, and remain disabled.
                    select.select_option('peer_spar')
                    m.record(saved,teacher.id,'player')['rank'] = 'registered'
                    saved.updated_at = now_iso();engine.store.save(saved)
                    before = saved.player.opportunity
                    with page.expect_response(lambda r:r.url.endswith('/mentorship-action')) as response:
                        click_control(submit)
                    assert not response.value.ok;page.wait_for_function('!busy&&game.mentorship.master.rank==="registered"')
                    choose('peer_spar');assert submit.is_disabled()
                    assert engine.store.load(game.id).player.opportunity == before
                    saved = engine.store.load(game.id);m.record(saved,teacher.id,'player')['rank'] = 'true'
                    saved.updated_at = now_iso();engine.store.save(saved)
                    page.evaluate('id=>loadGame(id)',game.id);page.wait_for_function('!busy')
                    for palette in ('light','dark'):
                        set_theme(page,palette)
                        for width in (1440,390):
                            page.set_viewport_size(dict(width=width,height=960))
                            choose('peer_spar');assert not submit.is_disabled()
                            select.scroll_into_view_if_needed()
                            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                            page.screenshot(path=str(ROOT/'build'/f'mentorship-peers-{palette}-{width}.png'),full_page=True)
                    with page.expect_response(lambda r:r.url.endswith('/mentorship-action')) as response:
                        click_control(submit)
                    assert response.value.ok,response.value.text();page.wait_for_function('!busy')
                    saved = engine.store.load(game.id)
                    assert saved.player.opportunity > before and saved.player.alive and m.person(saved,npc.id).alive
                    navigation_locator(page,'#battle-report-open').click()
                    page.wait_for_function('CombatReplay.diagnostics().active && !document.querySelector("[data-combat-replay]").disabled')
                    assert len(page.evaluate('CombatReplay.diagnostics().participants')) == 2
                    page.evaluate('CombatReplay.seek(.6)')
                    page.screenshot(path=str(ROOT/'build'/'mentorship-peers-combat.png'),full_page=True)
                    assert not errors,errors
                    browser.close()
                    print(json.dumps(dict(ok=True,actions=4,stale=True,combat_animation=True,screens=[1440,390])))
            finally: http.shutdown();http.server_close()


if __name__ == '__main__': main()
