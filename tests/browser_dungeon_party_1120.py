"""Real UI: carry original party, attack a newcomer, then verify event reputation."""
import sys
import random
import tempfile
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.models import SectNpc
from cultivation_life.rules import max_hp,max_mp
from cultivation_life.relationship_records import find_person
from browser_seeded_dungeons import panel_view


def main():
    with tempfile.TemporaryDirectory() as folder:
        engine=GameEngine(ROOT,Path(folder)/'saves')
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    for theme,width,height in (('light',1440,960),('dark',393,852)):
                        page=browser.new_page(viewport=dict(width=width,height=height),reduced_motion='reduce')
                        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                        page.goto(f'http://127.0.0.1:{http.server_port}');page.wait_for_function('!!configData')
                        page.locator(f'[data-theme-picker=start] [data-pixel-theme-choice={theme}]').click()
                        game=engine.store.load(engine.create_game('同行与灭杀验收','heavenly','dao',342,preset_id='core')['id'])
                        game.player.realm_index=4;game.player.layer=9
                        game.player.hp=max_hp(game.player);game.player.mp=max_mp(game.player)
                        npc=SectNpc(id='outside-browser',name='旧日同道',title='散修',realm_index=4,layer=1,
                            age=30,lifespan=1000,world='human',location_id=game.player.location_id,affinity=100,encountered_player=True)
                        game.world_npcs[npc.id]=npc;game.player.party=[{'id':npc.id}]
                        game.settings['combat_popup']=True;engine.store.save(game)
                        page.evaluate('async id=>{await loadGame(id);UtilityPanels.open("dungeon");}',game.id)
                        page.locator('[data-dungeon-action=discover]').click();page.wait_for_function('!busy&&game.dungeons.used===1')
                        saved=engine.store.load(game.id);site=next(iter(saved.dungeon_state['instances'].values()))
                        role=site['roles'][site['nodes'][0]['actor']]
                        role.update(realm=1,true_realm=1,layer=1,power_factor=.1,purpose='seek')
                        for r in site['roles'].values():r['offer_step']=99
                        site['nodes'][0]['kind']='trace';engine.store.save(saved)
                        page.locator('[data-dungeon-action=enter]').click();page.wait_for_function('!busy&&game.dungeons.active')
                        assert page.evaluate('game.dungeons.session.party_count')==2
                        panel_view(page,'team')
                        card=page.locator(f'.dungeon-person[data-person-id="{role["id"]}"]')
                        card.locator('summary').click()
                        attack=card.locator('[data-dungeon-action=slay]')
                        assert attack.is_enabled() and 'dungeon-button--danger' in attack.get_attribute('class')
                        attack.click();page.wait_for_function('!busy&&!!game.last_combat_report')
                        page.locator('#battle-report-card').wait_for(state='visible')
                        page.locator('#battle-report-toggle').click()
                        saved=engine.store.load(game.id);site=saved.dungeon_state['instances'][site['id']]
                        assert not find_person(saved,role['id'],include_inactive=True).alive and saved.player.infamy>0
                        assert not site['claims'] and site['party']==[npc.id]
                        assert card.locator('[data-dungeon-action=slay]').count()==0
                        page.locator('[data-choice=seize]').click();page.wait_for_function('!busy')
                        assert len(engine.store.load(game.id).dungeon_state['instances'][site['id']]['claims'])==1
                        page.locator('[data-dungeon-action=exit]').click();page.wait_for_function('!busy&&!game.dungeons.active')
                        assert any(r['id']==npc.id for r in engine.store.load(game.id).player.party)
                        page.keyboard.press('Escape')
                        saved=engine.store.load(game.id);infamy=saved.player.infamy;renown=saved.player.renown
                        event=engine.events_by_id['EVT_REALM_COMMON_MORTAL_01']
                        saved.pending_event=engine._instantiate_event(event,saved,random.Random(1));engine.store.save(saved)
                        page.evaluate('async id=>{await loadGame(id);}',game.id)
                        page.locator('#event-choices button').filter(has_text='入场应试').click()
                        page.wait_for_function('!busy&&!game.pending_event')
                        saved=engine.store.load(game.id)
                        assert saved.player.infamy==infamy and saved.player.renown==renown+1
                        assert not errors,errors
                        page.close()
                    browser.close()
            finally:http.shutdown();http.server_close()
    print('Dungeon party browser passed: two themes, local original allies, lethal button, death and infamy, single reward, party retained, real event renown')


if __name__=='__main__':main()
