"""Live six-theme training, backlash, battle report and Dao Ancestor UI."""
import copy
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys
import tempfile
import threading

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.models import Technique
from cultivation_life.rules import max_hp,max_mp


class Quiet(server.Handler):
    def log_message(self,*args): pass


def main():
    with tempfile.TemporaryDirectory(dir=ROOT/'build') as directory:
        server.PERSISTENCE_ROOT=Path(directory)
        engine=server.ENGINE=GameEngine(ROOT,Path(directory)/'saves')
        game=engine.store.load(engine.create_game('天域验收','supreme_metal','dao',7429,preset_id='true_immortal')['id'])
        game.pending_event=None; game.heavenly_court['open_election']=None
        game.player.opportunity=1e12; game.player.immortal_traces=100000
        game.player.combat_plan=dict(manual=True,stance='guard',investment=40)
        definition=next(iter(game.doctrine_state['definitions'].values())); key=definition['id']
        game.player.known_techniques.append(Technique(**copy.deepcopy(definition['manuals'][0])))
        record=game.doctrine_state['player'];record['progress'][key]={'level':4,'experience':0};record['active']=key
        record['voisinage_training'][key]={'rank':1,'stability':10}
        engine.store.save(game)
        httpd=ThreadingHTTPServer(('127.0.0.1',0),Quiet)
        threading.Thread(target=httpd.serve_forever,daemon=True).start()
        errors=[]
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch();page=browser.new_page(viewport={'width':1440,'height':1000})
                page.emulate_media(reduced_motion='reduce')
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(f'http://127.0.0.1:{httpd.server_port}');page.wait_for_function('configData!==null')
                page.evaluate('(id)=>loadGame(id)',game.id)
                page.evaluate("UtilityPanels.open('voisinage')")
                page.locator(f'[data-voisinage-id="{key}"] > summary').click()
                page.get_by_role('button',name='修炼至初成2层',exact=True).click()
                page.wait_for_function("game.doctrines.voisinages.some(f=>f.cultivation.rank===2)")
                saved=engine.store.load(game.id); saved.doctrine_state['player']['voisinage_training'][key]['rank']=4
                saved.player.immortal_aperture['current']=saved.player.immortal_aperture['capacity']
                engine.store.save(saved);page.evaluate('(id)=>loadGame(id)',game.id)
                page.get_by_role('button',name='引动反噬 · 冲击化境1层',exact=True).click()
                page.wait_for_function("game.pending_event?.id==='EVT_IMMORTAL_TRIAL_VOISINAGE_BACKLASH'")
                page.evaluate("UtilityPanels.close('voisinage')")
                page.get_by_role('button',name='固守邻域，抵抗同化',exact=True).click()
                page.wait_for_function("game.last_combat_report?.result==='victory'")
                assert page.evaluate('game.last_combat_report.rounds.length')==5
                page.evaluate("battleReportOpen=false;renderBattleReport(game.last_combat_report)")
                saved=engine.store.load(game.id);saved.doctrine_state['player']['voisinage_training'][key]['rank']=12
                engine.store.save(saved);page.evaluate('(id)=>loadGame(id)',game.id)
                for theme in 'abcdef':
                    page.evaluate('(t)=>document.querySelector(`[data-theme-picker=dialog] [data-theme-choice=${t}]`).click()',theme)
                    for width in (1440,412):
                        page.set_viewport_size({'width':width,'height':1000 if width>500 else 915})
                        page.evaluate("UtilityPanels.open('voisinage')")
                        page.locator('.voisinage-stages').first.wait_for(state='visible')
                        page.wait_for_timeout(450)
                        assert '大成4层' in page.locator('#voisinage-content').inner_text()
                        assert '同化而亡' in page.locator('#voisinage-content').inner_text()
                        page.screenshot(path=str(ROOT/f'build/trial-training-{theme}-{width}.png'))
                        assert page.locator('#voisinage-card').evaluate('(e)=>e.scrollWidth<=e.clientWidth+1'), (theme,width,page.locator('#voisinage-card').evaluate('(e)=>[e.scrollWidth,e.clientWidth]'))
                        page.evaluate("UtilityPanels.close('voisinage')")
                saved=engine.store.load(game.id); saved.player.realm_index=12
                record=saved.doctrine_state['player']; record['origin']=key;record['progress'][key]['level']=9
                record['voisinage_training'][key]['rank']=13
                saved.player.hp=max_hp(saved.player);saved.player.mp=max_mp(saved.player)
                engine.store.save(saved);page.evaluate('(id)=>loadGame(id)',game.id)
                assert page.evaluate('game.player.dao_ancestor')
                page.evaluate("UtilityPanels.open('voisinage')")
                assert '培养境界 · 至臻' in page.locator('#voisinage-content').inner_text()
                assert '至臻1层' not in page.locator('#voisinage-content').inner_text()
                assert not errors,errors
                browser.close()
        finally: httpd.shutdown();httpd.server_close()
    print('Six-theme immortal trials UI passed: real training, five-round backlash, stages, mobile layout, Dao Ancestor.')


if __name__=='__main__':main()
