"""Real component purchases, assembly, training, silent setting and all themes."""
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
from cultivation_life.rules import add_item, max_mp

class Quiet(server.Handler):
    def log_message(self,*args):pass

def main():
    with tempfile.TemporaryDirectory() as directory:
        server.PERSISTENCE_ROOT=Path(directory)
        engine=server.ENGINE=GameEngine(ROOT,Path(directory)/'saves')
        game=engine.store.load(engine.create_game('工坊验收','supreme_metal','demonic',1550,preset_id='asura_upper')['id'])
        game.player.asura_cultivation.update(conversion=5,body_level=20,souls=10000)
        add_item(game.player,'spirit_stone',100000000)
        parts=['puppet_asura_9_core_array','puppet_asura_9_shell_dragon','puppet_asura_9_energy_crystal']
        for id_ in parts:add_item(game.player,id_)
        game.player.mp=max_mp(game.player)
        game.pending_event=None
        engine.store.save(game)
        other=[]
        for preset,path,label in [('nether_upper','monster','幽元'),('reincarnation_upper','ghost','轮回元力')]:
            made=engine.create_game('元力验收','supreme_metal',path,1541,preset_id=preset,
                                   **({'monster_species_id':'serpent'} if path=='monster' else {}))
            other.append((made['id'],label))
        httpd=ThreadingHTTPServer(('127.0.0.1',0),Quiet)
        threading.Thread(target=httpd.serve_forever,daemon=True).start()
        errors=[]
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch()
                page=browser.new_page(viewport={'width':1440,'height':1000})
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(f'http://127.0.0.1:{httpd.server_port}')
                page.wait_for_function('configData !== null')
                page.evaluate('(id)=>loadGame(id)',game.id)
                page.evaluate("UtilityPanels.open('settings')")
                page.locator('#setting-silent-events').check()
                page.wait_for_function('game.settings.silent_events === true')
                assert engine.store.load(game.id).settings['silent_events']
                page.evaluate("UtilityPanels.open('market')")
                for id_ in parts:
                    page.locator(f'#puppet-market-offers .market-buy[data-offer-id$="{id_}"]').click()
                    page.wait_for_function('(id)=>game.player.inventory.some(x=>x.id===id && x.quantity===2)',arg=id_)
                page.evaluate("UtilityPanels.open('puppet-workshop')")
                page.get_by_label('成品形态',exact=True).select_option('dragon')
                page.wait_for_function("document.querySelector('#craft-puppet').disabled === false")
                assert '高阶肉身 5层' in page.locator('.puppet-result').inner_text()
                page.locator('#craft-puppet').click()
                page.wait_for_function('game.demonic_system.puppets.length === 1')
                assert engine.store.load(game.id).player.puppets[0]['form']=='dragon'
                page.evaluate("UtilityPanels.open('captive')")
                training=page.locator('.owned-training').first
                training.locator('summary').click()
                training.get_by_label('培养方向').select_option('body')
                training.get_by_label('培养轮数').select_option('5')
                training.get_by_role('button',name='培养炼体 · 5轮',exact=True).click()
                page.wait_for_function('game.demonic_system.puppets[0].immortal_body_level === 15')
                for theme in 'abcdef':
                    page.evaluate('(t)=>document.querySelector(`[data-theme-picker=dialog] [data-theme-choice=${t}]`).click()',theme)
                    for width,height in [(1440,1000),(412,915),(932,430)]:
                        page.set_viewport_size({'width':width,'height':height})
                        page.evaluate("UtilityPanels.open('puppet-workshop')")
                        assert page.locator('#puppet-workshop').evaluate('e=>e.scrollWidth<=e.clientWidth+1'),(theme,width)
                        page.get_by_label('成品形态',exact=True).select_option('bird')
                        assert page.locator('#craft-puppet').is_disabled()
                        page.get_by_label('成品形态',exact=True).select_option('dragon')
                        page.wait_for_function("document.querySelector('#craft-puppet').disabled === false")
                        if width==1440:page.screenshot(path=str(ROOT/'build'/f'puppet-1550-{theme}.png'))
                        page.evaluate("UtilityPanels.open('settings')")
                        assert page.locator('#setting-silent-events').is_checked()
                page.set_viewport_size({'width':1440,'height':1000})
                for id_,label in other:
                    page.evaluate('(id)=>loadGame(id)',id_)
                    for theme in 'abcdef':
                        page.evaluate('(t)=>document.querySelector(`[data-theme-picker=dialog] [data-theme-choice=${t}]`).click()',theme)
                        assert label in page.locator('#hud-mp').inner_text()
                        assert '仙灵力' not in page.locator('#hud-mp').inner_text()
                        page.evaluate("UtilityPanels.open('immortal-aperture')")
                        page.wait_for_function("label=>document.querySelector('#immortal-aperture-card').innerText.includes(label)",arg=label)
                assert not errors,errors
                browser.close()
        finally:httpd.shutdown()
    print('Puppet UI passed: real materials purchase, preview, assembly, training, silent settings and six themes; native energy labels verified.')

if __name__=='__main__':main()
