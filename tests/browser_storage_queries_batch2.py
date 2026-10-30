"""Real save-menu reads, external edits, schema rejection and confirmed deletion."""
import hashlib
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from unittest.mock import patch
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from scripts.release_evidence import inputs_digest


def refresh(page):
    with page.expect_response(lambda response: urlparse(response.url).path == '/api/games'
                              and response.request.method == 'GET') as pending:
        page.evaluate('showStart()')
    response = pending.value
    assert response.ok
    # Reading the body also waits for completion. Response.finished() in the
    # bundled Playwright leaves a close-wait task alive until page teardown.
    response.json()
    page.evaluate('async()=>{await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));}')


def run():
    output = ROOT / 'build/architecture-batch2-20261031/browser'
    output.mkdir(parents=True, exist_ok=True)
    signature = inputs_digest(ROOT)
    rows = []
    with tempfile.TemporaryDirectory(dir=ROOT / 'build') as directory:
        folder = Path(directory)
        engine = GameEngine(ROOT, folder / 'saves')
        class Quiet(server.Handler):
            def log_message(self, *args):
                pass
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', folder):
            http = ThreadingHTTPServer(('127.0.0.1', 0), Quiet)
            threading.Thread(target=http.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    for width, height in ((1440, 1000), (393, 852)):
                        ids = [engine.create_game(name, 'heavenly', 'dao', 280, preset_id='core')['id']
                               for name in ('甲卷', '乙卷')]
                        for _ in range(2):
                            for identity in ids:
                                engine.get_game(identity)
                        path = engine.store._path(ids[0])
                        original, other = path.read_bytes(), engine.store._path(ids[1]).read_bytes()
                        metadata = engine.achievements.metadata.path.read_bytes()
                        info = path.stat()
                        page = browser.new_page(viewport=dict(width=width, height=height))
                        errors = []
                        page.on('pageerror', lambda error: errors.append(str(error)))
                        page.on('dialog', lambda dialog: dialog.accept())
                        page.goto(f'http://127.0.0.1:{http.server_port}')
                        page.wait_for_function('configData && document.querySelectorAll(".save-entry").length>=2')
                        row = page.locator(f'[data-save-id="{ids[0]}"]')
                        row.locator('.save-resume').click()
                        page.wait_for_function('id=>!busy&&game?.id===id', arg=ids[0])
                        assert path.read_bytes() == original
                        refresh(page)
                        row.wait_for()
                        changed = json.loads(original)
                        changed['player']['name'] = '丙卷'
                        raw = json.dumps(changed, ensure_ascii=False, separators=(',', ':')).encode()
                        assert len(raw) == len(original)
                        path.write_bytes(raw)
                        os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns))
                        refresh(page)
                        page.wait_for_function('id=>document.querySelector(`[data-save-id="${id}"] strong`)?.textContent==="丙卷"', arg=ids[0])
                        changed['version'] = 10
                        obsolete = json.dumps(changed, ensure_ascii=False, separators=(',', ':')).encode()
                        path.write_bytes(obsolete)
                        os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns))
                        refresh(page)
                        page.wait_for_function('id=>document.querySelector(`[data-save-id="${id}"] .save-resume`)?.disabled', arg=ids[0])
                        response = page.request.get(f'http://127.0.0.1:{http.server_port}/api/games/{ids[0]}')
                        assert response.status == 400 and path.read_bytes() == obsolete
                        path.write_bytes(original)
                        os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns))
                        refresh(page)
                        page.wait_for_function('id=>{const n=document.querySelector(`[data-save-id="${id}"] .save-resume`);return n&&!n.disabled;}', arg=ids[0])
                        assert row.locator('strong').inner_text() == '甲卷'
                        second = page.locator(f'[data-save-id="{ids[1]}"]')
                        second.locator('.save-delete').click()
                        page.locator('#game-confirm-cancel').click()
                        assert engine.store._path(ids[1]).read_bytes() == other
                        second.locator('.save-delete').click()
                        page.locator('#game-confirm-accept').click()
                        second.wait_for(state='detached')
                        assert not engine.store._path(ids[1]).exists()
                        assert path.read_bytes() == original
                        assert engine.achievements.metadata.path.read_bytes() == metadata
                        assert not errors, errors
                        page.screenshot(path=str(output / f'{width}.png'))
                        rows.append(dict(width=width, passed=True, same_size_same_mtime_refresh=True,
                                         schema10_disabled_and_rejected=True, real_delete_confirm_cancel=True))
                        page.close()
                    browser.close()
            finally:
                http.shutdown(); http.server_close()
    assert signature == inputs_digest(ROOT), 'Runtime changed during browser validation'
    (output / 'result.json').write_text(json.dumps(dict(inputs_sha256=signature, layouts=rows), indent=2)+'\n', encoding='utf-8')
    print('Save summary browser passed: desktop/mobile, external overwrite, old-schema rejection and real deletion')


if __name__ == '__main__':
    run()
