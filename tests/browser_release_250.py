"""Real keyboard entry and instance-local society/event clicks in four themes."""
import sys
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


def main():
    output=ROOT/'build/release-250-browser';output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        engine=GameEngine(ROOT,Path(directory)/'saves')
        class Handler(server.Handler):
            def log_message(self,*_args): pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',Path(directory)):
            httpd=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            threading.Thread(target=httpd.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    for theme in 'abdf':
                        for width,height in [(1440,1000),(393,852)]:
                            page=browser.new_page(viewport=dict(width=width,height=height))
                            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                            page.goto(f'http://127.0.0.1:{httpd.server_port}')
                            page.wait_for_selector('#custom-start')
                            page.locator(f'[data-theme-picker=start] [data-theme-choice={theme}]').click()
                            page.locator('#custom-start > summary').click()
                            page.locator('#custom-world').select_option('celestial')
                            page.locator('#custom-realm').select_option('11')
                            page.locator('#custom-layer').select_option('9')
                            field=page.locator('#custom-sense');field.click();page.keyboard.type('160')
                            assert field.input_value()=='160'
                            assert field.get_attribute('inputmode')=='numeric'
                            page.locator('#custom-item-search').fill('spirit_stone')
                            page.locator('#custom-item').select_option('spirit_stone')
                            page.get_by_role('button',name='100 万',exact=True).click()
                            page.locator('#custom-add-item').click()
                            field=page.locator('#custom-bag-spirit_stone');field.click();page.keyboard.type('2500000')
                            assert field.input_value()=='2500000'
                            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                            page.locator('#custom-start').screenshot(path=str(output/f'{theme}-{width}-numbers.png'))
                            page.locator('#custom-start-submit').click()
                            page.wait_for_function('game && !busy && game.player.realm_index===11')
                            game=engine._load(page.evaluate('game.id'))
                            assert game.player.immortal_veins=={'9':27,'10':27,'11':24}
                            assert game.player.divine_sense_rank==160
                            assert next(i.quantity for i in game.player.inventory if i.id=='spirit_stone')==2500000
                            lost=engine.create_game('失落宗族','supreme_metal','dao',250,preset_id='lost_world')
                            page.evaluate('async id=>loadGame(id)',lost['id'])
                            page.locator('[data-panel-target=faction]').click()
                            panel=page.locator('#faction-card .spatial-society')
                            panel.get_by_role('button',name='拜入宗门 · 一年',exact=True).first.click()
                            page.wait_for_function('!busy && !!game.spatial.scene.joined_sect')
                            panel.get_by_role('button',name='请教本界传承 · 一年',exact=True).click()
                            page.wait_for_function('!busy')
                            assert any(t.id.startswith('SPATIAL_') for t in engine._load(lost['id']).player.known_techniques)
                            page.locator('[data-panel-target=family]').click()
                            panel=page.locator('#family-card .spatial-society')
                            card=panel.locator('[data-local-society]').first
                            card.get_by_role('button',name='前往驻地 · 一年').click()
                            page.wait_for_function('!busy && game.spatial.scene.society.families[0].here')
                            card.get_by_role('button',name='成为客卿 · 一年').click()
                            page.wait_for_function('!busy && game.spatial.scene.society.families[0].joined')
                            assert page.locator('#family-card').evaluate('e=>e.scrollWidth<=e.clientWidth+1')
                            page.locator('#family-card').screenshot(path=str(output/f'{theme}-{width}-family.png'))
                            page.locator('#family-toggle').click()
                            page.locator('[data-action=rest]').click()
                            page.wait_for_function('!busy && !!game.pending_event')
                            assert page.evaluate('game.pending_event.id.startsWith("EVT_WANDER_SHARED_")')
                            page.locator('#event-choices button').last.click()
                            page.wait_for_function('!busy && !game.pending_event')
                            assert not errors,errors
                            page.close()
                    browser.close()
            finally: httpd.shutdown()
    print('Release 250 UI passed: four themes, two widths, keyboard replacement, editable bag, upper birth, local societies and real shared event submission')


if __name__=='__main__': main()
