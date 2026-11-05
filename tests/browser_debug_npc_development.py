"""Desktop/mobile Debug workbench and ordinary NPC dialog use one isolated save."""
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
from cultivation_life.models import GameState
from cultivation_life.relationship_records import find_person
from scripts.browser_navigation import navigation_locator
from test_npc_development_special_areas import make_game
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
                        g=make_game(e);page=browser.new_page(viewport=dict(width=width,height=height))
                        errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                        base=f'http://127.0.0.1:{http.server_port}'
                        page.context.set_extra_http_headers({'Origin':base});page.goto(base)
                        page.wait_for_function("typeof configData!=='undefined'&&!!configData&&!busy")
                        load(page,g.id);source=e.store._path(g.id).read_bytes()
                        page.keyboard.press('Backquote');page.wait_for_function('!busy')
                        def command(text):
                            page.locator('#debug-console-input').fill(text)
                            page.locator('#debug-console-input').press('Enter')
                            page.wait_for_function('!busy&&!document.querySelector("#debug-console-input").disabled')
                            assert page.locator('#debug-console-output pre').last.get_attribute('class')!='debug-error',page.locator('#debug-console-output').inner_text()
                        command('debug start');command('snapshot create before_npc')
                        sid=page.evaluate("sessionStorage.getItem('cultivation-debug-session')")
                        m=runtime(ROOT,root,e)
                        page.locator('#debug-npc-development > summary').click()
                        before=m._path(sid).read_bytes()
                        page.locator('#debug-npc-read').click()
                        page.wait_for_function('!busy&&!document.querySelector("#debug-npc-target").disabled')
                        assert m._path(sid).read_bytes()==before
                        page.locator('#debug-npc-axis').select_option('body')
                        page.locator('#debug-npc-method').select_option('infuse')
                        assert not page.locator('#debug-npc-apply').is_disabled()
                        def apply():
                            with page.expect_response(lambda r:r.url.endswith('/api/debug/command') and r.request.post_data_json.get('command')=='npc development') as response:
                                page.locator('#debug-npc-apply').click()
                            assert response.value.ok,response.value.text()
                            page.wait_for_function('!busy&&!document.querySelector("#debug-npc-target").disabled')
                        apply()
                        def saved():return GameState.from_dict(m.load(sid)['current']['game'])
                        assert find_person(saved(),'outside-student').body_training==20
                        # Select the original asset and unload/reinstall a used energy source.
                        page.locator('#debug-npc-target').select_option(label='机关 · puppet')
                        page.locator('#debug-npc-action').select_option('charge')
                        page.locator('#debug-npc-source').select_option('spare:saved-energy');apply()
                        assert saved().player.puppets[0]['operating_energy']==23
                        page.locator('#debug-npc-supply').click()
                        page.wait_for_function('!busy&&!document.querySelector("#debug-npc-target").disabled')
                        assert not saved().player.combat_plan['puppet_supply']
                        page.locator('#debug-npc-development > summary').scroll_into_view_if_needed()
                        page.screenshot(path=str(ROOT/'build'/f'debug-npc-{width}.png'))
                        command('snapshot restore before_npc')
                        assert page.locator('#debug-npc-apply').is_disabled()
                        assert find_person(saved(),'outside-student').body_training==10
                        assert saved().player.puppets[0]['operating_energy']==47
                        # The independent gameplay dialog must also work in Debug mode.
                        page.locator('#debug-console header button').click()
                        navigation_locator(page,'[data-panel-target=npc-development]').click()
                        page.wait_for_selector('#npc-development-submit')
                        page.get_by_label('培养方向',exact=True).select_option('body')
                        page.get_by_label('培养方式',exact=True).select_option('infuse')
                        with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/npc-development')) as response:
                            page.locator('#npc-development-submit').click()
                        assert response.value.ok,response.value.text()
                        page.wait_for_function('!busy')
                        assert find_person(saved(),'outside-student').body_training==20
                        assert e.store._path(g.id).read_bytes()==source and not errors,errors
                        page.locator('#npc-development-dialog > header button').click()
                        page.keyboard.press('Backquote');command('debug stop')
                        assert not page.evaluate('DebugConsole.active()')
                        assert e.store._path(g.id).read_bytes()==source
                        page.close()
                    browser.close()
            finally:http.shutdown();http.server_close()
    print('Debug NPC browser passed: desktop/mobile, pure read, growth, energy, supply, snapshot, normal dialog, source isolation')


if __name__=='__main__':main()
