"""Measure an actual browser click in an isolated spirit-world, realm-8 save."""
from pathlib import Path
import argparse
import json
import statistics
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=ROOT)
    parser.add_argument('--snapshot', type=Path, help='Read-only initial snapshot for matching another revision')
    parser.add_argument('--seed', type=int, default=2110)
    parser.add_argument('--samples', type=int, default=3)
    parser.add_argument('--browser', choices=['msedge', 'chromium'], default='msedge')
    parser.add_argument('--output', type=Path, default=ROOT/'build/spirit-action-benchmark.json')
    args = parser.parse_args()
    if not 1 <= args.samples <= 20:
        parser.error('--samples must be between 1 and 20')
    source = args.source_root.resolve()
    sys.path.insert(0, str(source))
    from cultivation_life import server
    from cultivation_life.engine import GameEngine
    from cultivation_life.models import GameState
    from cultivation_life.save_schema import migrate_document
    from scripts.release_evidence import inputs_digest
    from playwright.sync_api import sync_playwright

    signature = inputs_digest(source)
    snapshot_path = args.output.with_suffix('.initial.json')
    if args.snapshot and args.snapshot.resolve() in {args.output.resolve(), snapshot_path.resolve()}:
        raise ValueError('Output must not overwrite the input snapshot')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        engine = GameEngine(source, Path(directory)/'saves')
        if args.snapshot:
            initial = GameState.from_dict(migrate_document(json.loads(args.snapshot.read_text(encoding='utf-8'))))
            if initial.player.world != 'spirit' or initial.player.realm_index != 8:
                raise ValueError('Benchmark snapshot must be a spirit-world realm-8 character')
        else:
            made = engine.create_game('灵界百年基准', 'supreme_earth', 'dao', args.seed,
                                      custom_start=dict(world='spirit', realm_index=8,
                                                        sect='new', sect_name='基准宗'))
            initial = engine._load(made['id'])
        if initial.pending_event or initial.active_trial or not initial.player.alive:
            raise ValueError('Benchmark snapshot must be alive and free of an event or trial')
        # The regular user setting suppresses only optional tide notifications.
        # All nine DLCs, NPC simulation and treasury/cargo settlement stay active.
        initial.settings['guixu_event_popup'] = False
        raw = initial.to_dict()
        snapshot_path.write_text(json.dumps(raw, ensure_ascii=False), encoding='utf-8')

        class Quiet(server.Handler):
            def log_message(self, *unused):
                pass

        with patch.object(server, 'ENGINE', engine), \
             patch.object(server, 'PERSISTENCE_ROOT', Path(directory)):
            http = ThreadingHTTPServer(('127.0.0.1', 0), Quiet)
            threading.Thread(target=http.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(headless=True, **({'channel':'msedge'} if args.browser == 'msedge' else {}))
                    page = browser.new_page(viewport=dict(width=1440, height=1000))
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.goto(f'http://127.0.0.1:{http.server_port}')
                    page.wait_for_function('!!configData && !busy')
                    dlcs = page.evaluate('configData.extensions.filter(r=>r.status==="loaded").map(r=>r.id)')
                    if len(dlcs) != 9:
                        raise ValueError(f'All nine official DLCs must be loaded; found {dlcs}')
                    results = []
                    for sample in range(args.samples):
                        game = GameState.from_dict(json.loads(json.dumps(raw)))
                        engine.store.save(game)
                        page.evaluate('async id=>loadGame(id)', game.id)
                        age = game.player.age
                        page.evaluate('performance.clearResourceTimings();window.__actionStart=performance.now()')
                        page.locator('#cultivate-action').click()
                        page.wait_for_function('age=>!busy && game.player.age===age', arg=age+100, timeout=120000)
                        page.evaluate('()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))')
                        row = page.evaluate('''()=>({total_ms:performance.now()-window.__actionStart,
                            api_ms:performance.getEntriesByType("resource").find(r=>r.name.endsWith("/advance")).duration,
                            years:100})''')
                        results.append(row)
                        print(sample+1, row, flush=True)
                    if errors:
                        raise RuntimeError(errors)
                    report = dict(inputs_sha256=signature, browser=args.browser, browser_version=browser.version,
                                  dlcs=dlcs, results=results, initial_snapshot=str(snapshot_path),
                                  median_ms=statistics.median(r['total_ms'] for r in results),
                                  median_api_ms=statistics.median(r['api_ms'] for r in results))
                    browser.close()
            finally:
                http.shutdown()
                http.server_close()
    if signature != inputs_digest(source):
        raise RuntimeError('Production source changed during measurement')
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
