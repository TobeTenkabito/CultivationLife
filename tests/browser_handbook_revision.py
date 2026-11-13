"""No user saves: real current-catalog reload, upgrade and handbook searches."""
import json
import copy
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.content_registry import TECHNIQUE_CATALOG
from fixtures.technique_names_release import prepare_technique_names
from scripts.verify_handbook_revision import verify_revision
from scripts.release_evidence import inputs_digest
from scripts.browser_navigation import set_theme


def main():
    output=ROOT/'build/handbook-revision';output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='handbook-332-') as folder:
        engine=GameEngine(ROOT,Path(folder)/'saves')
        class Quiet(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            http=ThreadingHTTPServer(('127.0.0.1',0),Quiet)
            threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    for theme,width,height in [('light',1440,960),('dark',1440,960),('light',412,915),('dark',390,844)]:
                        page=browser.new_page(viewport=dict(width=width,height=height))
                        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                        page.goto(f'http://127.0.0.1:{http.server_port}');page.wait_for_function('!!configData&&!busy')
                        page.evaluate('GameThemes.ready')
                        set_theme(page,theme)
                        identity=engine.create_game('旧籍新编','supreme_metal','dao',332)['id']
                        prepare_technique_names(engine,identity,('抱朴养真经','晦烛含魄篇'))
                        game=engine._load(identity)
                        longest=copy.deepcopy(max((book for book in TECHNIQUE_CATALOG.values() if book.id.startswith('TECH_OPEN_')),key=lambda book:len(book.name)))
                        game.player.known_techniques.append(longest)
                        engine.store.save(game)
                        page.evaluate('id=>loadGame(id)',identity)
                        verify_revision(page,engine,identity,output,f'{theme}-{width}',extra_names=(longest.name,))
                        assert not errors,errors
                        page.close()
                        print(f'{theme} {width}x{height}: old display reload, actual upgrade and fourteen handbook chapters passed',flush=True)
                    browser.close()
            finally:http.shutdown();http.server_close()
    (output/'report.json').write_text(json.dumps(dict(status='passed',inputs_sha256=inputs_digest(ROOT),scenarios=4),indent=2),encoding='utf-8')


if __name__=='__main__':main()
