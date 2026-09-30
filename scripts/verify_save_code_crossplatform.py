import json
import sys
import tempfile
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine


class QuietHandler(server.Handler):
    def log_message(self, *args): pass


def main():
    expected = json.loads((ROOT/'build/transfer-fixtures/from-windows.json').read_bytes())
    code = (ROOT/'build/from-android-1513.txt').read_text(encoding='utf-8')
    with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
        server.PERSISTENCE_ROOT = Path(folder)
        engine = server.ENGINE = GameEngine(ROOT, Path(folder)/'saves')
        httpd = ThreadingHTTPServer(('127.0.0.1',0),QuietHandler)
        threading.Thread(target=httpd.serve_forever,daemon=True).start()
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch();page=browser.new_page()
                page.goto(f'http://127.0.0.1:{httpd.server_port}')
                page.wait_for_function('window.SaveCode && configData')
                result=page.evaluate('''async code=>{
                    const payload=await SaveCode.decode(code);
                    const preview=await api('/api/save-transfer/preview',{method:'POST',body:JSON.stringify({payload})});
                    return api('/api/save-transfer/import',{method:'POST',body:JSON.stringify({payload,existing_hash:preview.existing_hash})});
                }''',code)
                assert result['id']==expected['id']
                assert json.loads(engine.store._path(result['id']).read_bytes())==expected
                browser.close()
        finally: httpd.shutdown()
    print('Windows -> signed Android 12 -> Windows save code roundtrip passed; all JSON fields preserved')


if __name__=='__main__': main()
