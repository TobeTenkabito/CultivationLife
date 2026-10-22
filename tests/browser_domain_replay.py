"""Real engine domain battles, real game-page entry and disposal."""
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.ui_preferences import write_ui_preferences
from fixtures.visual_additions import prepare_domain_battle
from domain_replay_acceptance import verify


def main():
    output=ROOT/'build/domain-replay';output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder);engine=GameEngine(ROOT,root/'saves')
        write_ui_preferences(root,{'pixel_art':True,'reduced_motion':True})
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',root),patch('cultivation_life.runtime.persistence_root',return_value=root):
            http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch();page=browser.new_page(viewport=dict(width=1440,height=960),reduced_motion='reduce')
                    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    page.add_init_script('Array.prototype.at=undefined;Array.prototype.findLast=undefined')
                    page.goto(f'http://127.0.0.1:{http.server_port}');page.wait_for_function('!!configData');page.evaluate('GameThemes.ready')
                    for kind in ['control','contest','mutual','mixed','group']:
                        made=engine.create_game('邻域验收','heavenly','dao',151,preset_id='core')
                        prepare_domain_battle(engine,made['id'],kind)
                        verify(page,made['id'],output,kind)
                    assert not errors,errors
                    browser.close()
            finally:http.shutdown();http.server_close()
    print('Domain battle replay acceptance passed: control, contest, mutual, mixed, 3 widths, stable/no writes/disposal')


if __name__=='__main__':main()
