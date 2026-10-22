"""Run the exact compiled-release UI assertions against an isolated source server."""
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
from fixtures.visual_additions import prepare_visual_additions
from visual_additions_acceptance import verify


def main():
    output=ROOT/'build/alpha3-additions';output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder);engine=GameEngine(ROOT,root/'saves')
        game=engine.create_game('发行预检','heavenly','dao',323,preset_id='core')
        prepare_visual_additions(engine,game['id'])
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',root):
            httpd=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            threading.Thread(target=httpd.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch();page=browser.new_page(viewport={'width':1440,'height':960},reduced_motion='reduce')
                    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    page.goto(f'http://127.0.0.1:{httpd.server_port}');page.wait_for_function('!!configData')
                    verify(page,game['id'],output)
                    assert not errors,errors
                    browser.close()
            finally:httpd.shutdown();httpd.server_close()
    print('Alpha.3 shared acceptance passed')


if __name__=='__main__':main()
