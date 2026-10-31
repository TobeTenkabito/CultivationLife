"""Concurrent real HTTP reads during unchanged hundred-year actions."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
from http.server import ThreadingHTTPServer
import importlib.util
import itertools
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch
from urllib.request import Request, urlopen
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cultivation_life import runtime, server
from cultivation_life.engine import GameEngine
from cultivation_life.models import GameState
from cultivation_life.storage import _summary_facts, _public_summary
from cultivation_life.content_registry import REALMS, WORLD_SYSTEMS, PATH_NAMES
from cultivation_life.version import BASE_GAME_VERSION
from scripts.release_evidence import inputs_digest

PATHS = ['/api/config', '/api/ui-preferences', '/api/visual-assets', '/api/fleet-goods',
    '/api/domain-styles', '/api/games', '/api/achievements', '/api/authored-lineages']
SEEDS = (315, 7701, 9003)


class FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        value = datetime(2026, 10, 31, tzinfo=timezone.utc)
        return value.astimezone(tz) if tz else value.replace(tzinfo=None)


def reference():
    path = ROOT/'tests/fixtures/api_serialization_332.py'
    spec = importlib.util.spec_from_file_location('cultivation_life._reference_http_serialization', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch(base, path, *, body=None, probe=None):
    request = Request(base+path, method='POST' if body is not None else 'GET',
        data=json.dumps(body).encode() if body is not None else None,
        headers={'Content-Type':'application/json', 'Origin':base, 'X-Benchmark-Probe':probe or ''})
    start = time.perf_counter()
    with urlopen(request, timeout=120) as response:
        result = json.loads(response.read())
        assert response.status == 200
    return result, round((time.perf_counter()-start)*1000, 3)


def one(mode, seed, document, expected, oracle, expected_static, expected_results):
    with tempfile.TemporaryDirectory(prefix='concurrent-api-', dir=ROOT/'build') as directory, ExitStack() as stack:
        folder = Path(directory)
        stack.enter_context(patch.object(runtime, 'datetime', FixedDatetime))
        engine = GameEngine(ROOT, folder/'saves')
        engine.achievements.ensure_global_metadata()
        engine.store.save(GameState.from_dict(document))
        entered, active = threading.Event(), threading.Event()
        original_year, original_action = engine._advance_world_year, engine.advance
        def year(*args, **kwargs):
            entered.set()
            return original_year(*args, **kwargs)
        def action(*args, **kwargs):
            active.set()
            try:
                return original_action(*args, **kwargs)
            finally:
                active.clear()
        stack.enter_context(patch.object(engine, '_advance_world_year', year))
        stack.enter_context(patch.object(engine, 'advance', action))
        # Match the previous frozen annual scenario, not a gameplay override.
        stack.enter_context(patch.object(engine, '_advance_guixu_calendar', return_value=False))
        identifiers = itertools.count()
        def fresh_id():
            data = f'benchmark:{seed}:{next(identifiers)}'.encode()
            return uuid.UUID(bytes=hashlib.blake2s(data, digest_size=16).digest())
        request_ids = SimpleNamespace(uuid4=uuid.uuid4)
        stack.enter_context(patch('uuid.uuid4', side_effect=fresh_id))
        stack.enter_context(patch.object(server, 'uuid', request_ids))
        stack.enter_context(patch.object(server, 'ENGINE', engine))
        stack.enter_context(patch.object(server, 'PERSISTENCE_ROOT', folder))
        for key, value in dict(ENGINE=engine, ENGINE_ROOT=server.ENGINE_ROOT,
                PERSISTENCE_ROOT=folder, uuid=request_ids).items():
            stack.enter_context(patch.object(oracle, key, value, create=True))

        committed_games = [engine.store._path(document['id']).read_bytes()]
        committed_accounts = [engine.achievements.metadata.path.read_bytes()]
        replace = Path.replace
        def observed_replace(path, target):
            result = replace(path, target)
            target = Path(target)
            # Called inside the short I/O lock. No summary/account callbacks:
            # never introduce a reverse lock order in the observer itself.
            if target == engine.store._path(document['id']):
                committed_games.append(target.read_bytes())
            elif target == engine.achievements.metadata.path:
                committed_accounts.append(target.read_bytes())
            return result
        stack.enter_context(patch.object(Path, 'replace', observed_replace))
        sent_during_action = {}
        class Quiet(server.Handler):
            def log_message(self, *args):
                pass
            def _send_json(self, body, status):
                probe = self.headers.get('X-Benchmark-Probe')
                if probe:
                    acquired = engine.store.lock.acquire(blocking=False)
                    if acquired:
                        engine.store.lock.release()
                    sent_during_action[probe] = active.is_set() and not acquired
                return super()._send_json(body, status)
        if mode == 'reference':
            Quiet.do_GET = oracle.local_request(server.Handler.do_GET.__wrapped__)
            Quiet.do_POST = oracle.local_request(server.Handler.do_POST.__wrapped__)
        http = ThreadingHTTPServer(('127.0.0.1', 0), Quiet)
        threading.Thread(target=http.serve_forever, daemon=True).start()
        base = f'http://127.0.0.1:{http.server_port}'
        try:
            # Warm directory/asset declarations without hydrating the game.
            for path in PATHS:
                result, _ = fetch(base, path)
                if path not in {'/api/games', '/api/achievements'}:
                    assert expected_static.setdefault(path, result) == result
            with ThreadPoolExecutor(max_workers=len(PATHS)+1) as pool:
                advancing = pool.submit(fetch, base, f'/api/games/{document["id"]}/advance',
                    body=dict(action='rest', years=1))
                assert entered.wait(15), 'Action did not enter its real annual simulation'
                queries = {path:pool.submit(fetch, base, path, probe=path) for path in PATHS}
                responses = {path:future.result(timeout=120) for path, future in queries.items()}
                action_response, action_ms = advancing.result(timeout=120)
            final = engine.store.load(document['id']).to_dict()
            assert final['player']['age']-document['player']['age'] == 100
            assert final['last_saved_with_game_version'] == BASE_GAME_VERSION
            normalized = dict(final)
            normalized.pop('updated_at')
            expected = dict(expected, last_saved_with_game_version=BASE_GAME_VERSION)
            assert normalized == expected, f'Frozen full state/RNG mismatch: {mode} seed {seed}'
            complete = dict(model=final, response=action_response,
                metadata=json.loads(engine.achievements.metadata.path.read_bytes()))
            assert expected_results.setdefault(seed, complete) == complete, 'Reference/current complete outputs differ'

            valid_summaries = [dict(games=[_public_summary(_summary_facts(json.loads(raw)), len(raw),
                (REALMS, WORLD_SYSTEMS, PATH_NAMES))]) for raw in committed_games]
            valid_accounts = []
            for raw in committed_accounts:
                with patch.object(engine.achievements.metadata, 'read', return_value=json.loads(raw)):
                    valid_accounts.append(engine.achievements.public_catalog())
            for path, (body, _) in responses.items():
                if path == '/api/games':
                    assert body in valid_summaries, 'List exposed an uncommitted/mixed save document'
                elif path == '/api/achievements':
                    assert body in valid_accounts, 'Account response was not a complete committed generation'
                else:
                    assert body == expected_static[path]
            if mode == 'reference':
                assert not any(sent_during_action.values())
            else:
                assert all(sent_during_action.get(path) for path in PATHS), 'Read missed the actual action interval'
            return dict(mode=mode, seed=seed, action_ms=action_ms,
                latency_ms={path:value[1] for path, value in responses.items()},
                sent_while_action_owned_directory=sent_during_action,
                frozen_state_rng_equal=True, complete_response_and_account_equal=True,
                all_reads_match_committed_generations=True)
        finally:
            http.shutdown(); http.server_close()


def audit(output, fixture_dir, runs):
    output.mkdir(parents=True, exist_ok=True)
    signature = inputs_digest(ROOT)
    sources = {str(path):sha(path) for path in [Path(__file__), ROOT/'tests/fixtures/api_serialization_332.py']}
    fixtures = {seed:(fixture_dir/f'input-{seed}.json', fixture_dir/f'expected-{seed}.json') for seed in SEEDS}
    initial = {str(path):sha(path) for pair in fixtures.values() for path in pair}
    oracle = reference()
    expected_static, expected_results, rows = {}, {}, []
    for repeat in range(runs):
        for index, seed in enumerate(SEEDS):
            document, expected = (json.loads(path.read_text(encoding='utf-8')) for path in fixtures[seed])
            for mode in (('reference','current') if (repeat+index)%2==0 else ('current','reference')):
                result = one(mode, seed, document, expected, oracle, expected_static, expected_results)
                rows.append(dict(repeat=repeat, **result))
                print(json.dumps(rows[-1]), flush=True)
    summary = {}
    for path in PATHS:
        medians = {mode:round(statistics.median(row['latency_ms'][path] for row in rows if row['mode']==mode),3)
                   for mode in ('reference','current')}
        summary[path] = dict(medians_ms=medians,
            reduction_percent=round((1-medians['current']/medians['reference'])*100,2))
    assert signature == inputs_digest(ROOT)
    assert initial == {str(path):sha(path) for pair in fixtures.values() for path in pair}
    assert sources == {name:sha(Path(name)) for name in sources}
    report = dict(inputs_sha256=signature, source_sha256=sources, fixture_sha256=initial,
        runs_per_seed=runs, samples=rows, summary=summary,
        scope='Real hundred-year HTTP POST plus eight concurrent GETs. Alternating frozen pre-batch HTTP adapter/current policy in the same controller. Default GC and shared game/account writer serialization retained. Guixu interruption disabled only as in the frozen annual fixture. Fixed wall clock and fresh gameplay UUIDs isolate full-state comparisons; HTTP request IDs use an independent UUID stream. Summaries/accounts must match whole observed atomic commits. Latencies include loopback network/client decode and CPU/GIL contention, not native-device or hard real-time guarantees.')
    (output/'performance.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(report=str(output/'performance.json'))), flush=True)


if __name__ == '__main__':
    if os.environ.get('PYTHONHASHSEED') != '0':
        raise SystemExit(subprocess.call([sys.executable, '-X','utf8', *sys.argv], env=dict(os.environ, PYTHONHASHSEED='0')))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT/'build/architecture-batch4-20261031')
    parser.add_argument('--fixture-dir', type=Path, default=ROOT/'build/architecture-batch1-20261031/economy-fixed-seed')
    parser.add_argument('--runs', type=int, default=3)
    args = parser.parse_args()
    if args.runs < 1:
        parser.error('--runs must be positive')
    audit(args.output_dir.resolve(), args.fixture_dir.resolve(), args.runs)
