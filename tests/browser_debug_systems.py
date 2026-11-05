"""Real desktop/mobile Registry forms, pure inspection and isolated high growth."""
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
from cultivation_life.debug.gateway import runtime
from cultivation_life.debug.capabilities import CAPABILITIES
from cultivation_life.system.monster_body import config
from cultivation_life.rules import add_item
from browser_npc_recruitment_adversarial import load


def main():
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);e=GameEngine(ROOT,root/'data'/'saves')
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',e),patch.object(server,'APP_ROOT',root),patch.object(server,'PERSISTENCE_ROOT',root):
            http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    for width,height in [(1440,960),(390,844)]:
                        g=e._load(e.create_game('功能调试验收','supreme_metal','monster',111,preset_id='nether_upper',monster_species_id='serpent')['id'])
                        g.pending_event=None;g.player.body_training=100;g.player.opportunity=10**12;g.player.next_tribulation_age=None
                        g.player.immortal_body['monster']={'level':9}
                        for row in config()['mechanisms']:
                            for key in row['recipe']:add_item(g.player,key,10000)
                        e.store.save(g)
                        page=browser.new_page(viewport=dict(width=width,height=height));errors=[]
                        page.on('pageerror',lambda error:errors.append(str(error)))
                        base=f'http://127.0.0.1:{http.server_port}';page.context.set_extra_http_headers({'Origin':base})
                        page.goto(base);page.wait_for_function("typeof configData!=='undefined'&&!!configData&&!busy")
                        load(page,g.id);source=e.store._path(g.id).read_bytes()
                        page.keyboard.press('Backquote');page.wait_for_function('!busy')
                        def command(text):
                            page.locator('#debug-console-input').fill(text);page.locator('#debug-console-input').press('Enter')
                            page.wait_for_function('!busy&&!document.querySelector("#debug-console-input").disabled')
                            assert 'debug-error' not in (page.locator('#debug-console-output pre').last.get_attribute('class') or ''),page.locator('#debug-console-output').inner_text()
                        command('debug start');command('snapshot create before_systems')
                        sid=page.evaluate("sessionStorage.getItem('cultivation-debug-session')");m=runtime(ROOT,root,e)
                        page.locator('#debug-systems > summary').click()
                        def prepare():
                            page.locator('#debug-system-prepare').click()
                            page.wait_for_function('!busy&&!document.querySelector("#debug-system-inspect").disabled')
                        prepare()
                        assert page.locator('#debug-system-command option').count()==len(CAPABILITIES)
                        before=m._path(sid).read_bytes()
                        page.locator('#debug-system-section').select_option('/upper_voisinages')
                        page.locator('#debug-system-inspect').click()
                        page.wait_for_function('!busy&&!document.querySelector("#debug-system-inspect").disabled')
                        assert 'monster_body' in page.locator('#debug-system-view').inner_text()
                        assert m._path(sid).read_bytes()==before
                        page.locator('#debug-system-search').fill('upper voisinage')
                        assert page.locator('#debug-system-command option').count()==1
                        page.locator('#debug-system-arg-action').select_option(label='monster_body_train')
                        page.locator('#debug-system-arg-expected_level').fill('9')
                        page.locator('#debug-systems > summary').scroll_into_view_if_needed()
                        page.screenshot(path=str(ROOT/'build'/f'debug-systems-{width}.png'))
                        with page.expect_response(lambda r:r.url.endswith('/api/debug/command') and r.request.post_data_json.get('command')=='upper voisinage') as response:
                            page.locator('#debug-system-apply').click()
                        assert response.value.ok,response.value.text();page.wait_for_function('!busy')
                        assert m.load(sid)['current']['game']['player']['immortal_body']['monster']['level']==10
                        assert page.locator('#debug-system-apply').is_disabled()
                        command('setting set manual_combat_plan true')
                        prepare();page.locator('#debug-system-search').fill('combat plan')
                        page.locator('#debug-system-arg-puppet_supply').select_option(label='false')
                        with page.expect_response(lambda r:r.url.endswith('/api/debug/command') and r.request.post_data_json.get('command')=='combat plan') as response:
                            page.locator('#debug-system-apply').click()
                        assert response.value.ok,response.value.text();page.wait_for_function('!busy')
                        assert not m.load(sid)['current']['game']['player']['combat_plan']['puppet_supply']
                        command('snapshot restore before_systems')
                        assert m.load(sid)['current']['game']['player']['immortal_body']['monster']['level']==9
                        assert page.locator('#debug-system-apply').is_disabled()
                        assert e.store._path(g.id).read_bytes()==source and not errors,errors
                        command('debug stop');page.close()
                    browser.close()
            finally:http.shutdown();http.server_close()
    print('All-systems Debug browser passed: desktop/mobile, complete catalog, pure inspection, high body, boolean fields, stale controls, snapshot, source isolation')


if __name__=='__main__':main()
