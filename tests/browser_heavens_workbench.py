"""Right-hand navigation, illustrated dossiers and registry-backed debug workbench."""
import json
from pathlib import Path
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine


def main():
    output = ROOT / 'build/heavens-ui-workbench'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        engine = GameEngine(ROOT, root / 'data/saves')
        made = engine.create_game('行录调试', 'heavenly', 'dao', 881, preset_id='core')
        saved = engine.store.load(made['id'])
        saved.player.location_id = 'wudi_plain'
        saved.pending_event = None
        saved.settings['silent_events'] = True
        engine.store.save(saved)
        (root / 'game_config.txt').write_text('Debug=False', encoding='utf-8')

        class QuietHandler(server.Handler):
            def log_message(self, *_args):
                pass

        httpd = ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'APP_ROOT', root), patch.object(server, 'PERSISTENCE_ROOT', root):
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    page = browser.new_page(viewport={'width': 1440, 'height': 1050}, has_touch=True)
                    errors = []
                    page.on('pageerror', lambda e: errors.append(str(e)))
                    page.goto(f'http://127.0.0.1:{httpd.server_port}')
                    page.wait_for_function('configData !== null')
                    page.evaluate('async id=>loadGame(id)', made['id'])
                    source = engine.store._path(made['id']).read_bytes()
                    for name in ('heavens', 'relationship'):
                        assert page.locator(f'#strategy-dock [data-panel-target={name}]').count() == 1
                        assert page.locator(f'.left-dock [data-panel-target={name}]').count() == 0
                    page.locator('[data-panel-target=heavens]').click()
                    assert page.locator('#heavens-card').bounding_box()['x'] > 200
                    checks = []
                    for theme in 'abdf':
                        page.evaluate('t=>document.querySelector(`[data-theme-choice="${t}"]`).click()', theme)
                        for width, height in ((1440,1050),(393,852),(320,852),(780,360)):
                            page.set_viewport_size({'width':width,'height':height})
                            for tab in ('见闻','诸界'):
                                page.get_by_role('tab',name=tab,exact=True).click()
                                assert page.locator('.heavens-landscape svg').count() == 1
                                assert page.locator('.heavens-feature').evaluate('e=>e.scrollHeight<=e.clientHeight+1')
                                assert page.locator('#heavens-body').evaluate('e=>e.scrollWidth<=e.clientWidth+1')
                                checks.append((theme,width,tab))
                            if width in (1440,393):
                                page.screenshot(path=str(output/f'{theme}-{width}-atlas.png'))
                    assert engine.store._path(made['id']).read_bytes() == source
                    page.locator('#heavens-toggle').click()
                    page.keyboard.press('Backquote')
                    page.wait_for_function('!busy')

                    def command(text):
                        page.locator('#debug-console-input').fill(text)
                        page.locator('#debug-console-input').press('Enter')
                        ready()

                    def ready():
                        page.wait_for_function('!busy && !document.querySelector("#debug-console-input").disabled')

                    command('debug start')
                    command('snapshot create heavens_before')
                    page.locator('#debug-heavens>summary').click()
                    page.get_by_role('button',name='读取诸天',exact=True).click()
                    page.wait_for_function('!busy && !document.querySelector("#debug-heavens-target").disabled && document.querySelector("#debug-heavens-action").options.length>0')
                    assert page.evaluate('document.activeElement.id') != 'debug-console-input'
                    assert page.locator('#debug-heavens-target option').count() >= 12
                    assert page.locator('#debug-heavens-target').input_value() == 'human_beacon'
                    assert page.get_by_role('button',name='在副本执行').is_disabled()
                    # A response arriving after an option edit must not arm an old action.
                    page.evaluate("""()=>{
                      document.querySelectorAll('#debug-heavens button')[1].click();
                      document.querySelector('#debug-heavens-options').dispatchEvent(new Event('input'));
                    }""")
                    ready()
                    assert page.get_by_role('button',name='在副本执行').is_disabled()
                    page.get_by_role('button',name='预览行动',exact=True).click()
                    page.get_by_role('button',name='在副本执行').wait_for(state='visible')
                    page.wait_for_function('!document.querySelector("#debug-heavens button:last-child").disabled')
                    assert page.evaluate('document.activeElement.id') != 'debug-console-input'
                    age = page.evaluate('game.player.age')
                    page.get_by_role('button',name='在副本执行',exact=True).click()
                    page.wait_for_function("!busy && game.heavens.incidents.find(r=>r.id==='human_beacon').stage!=='unseen'",timeout=120000)
                    ready()
                    assert page.evaluate('game.player.age') > age
                    assert engine.store._path(made['id']).read_bytes() == source
                    for width,height in ((1440,1050),(393,852),(780,360)):
                        page.set_viewport_size({'width':width,'height':height})
                        for theme in 'abdf':
                            page.evaluate('t=>document.querySelector(`[data-theme-choice="${t}"]`).click()',theme)
                            assert page.locator('#debug-heavens').evaluate('e=>e.scrollWidth<=e.clientWidth+1')
                            for control in page.locator('#debug-heavens select,#debug-heavens button').all():
                                assert control.bounding_box()['height'] >= 44
                        page.locator('#debug-heavens').scroll_into_view_if_needed()
                        page.screenshot(path=str(output/f'console-{width}.png'))
                    command('snapshot restore heavens_before')
                    assert page.evaluate("game.heavens.incidents.find(r=>r.id==='human_beacon').stage") == 'unseen'
                    assert page.get_by_role('button',name='在副本执行').is_disabled()
                    assert not errors, errors
                    assert page.locator('#debug-console-output .debug-error').count() == 0
                    (output/'report.json').write_text(json.dumps({'views':checks,'debug_execution':True,'source_unchanged':True,'snapshot_restore':True,'errors':errors},ensure_ascii=False,indent=2),encoding='utf-8')
                    browser.close()
            finally:
                httpd.shutdown()
                httpd.server_close()
    print('Right dock, 48 atlas views, four-theme console, real isolated execution and snapshot restore passed')


if __name__ == '__main__':
    main()
