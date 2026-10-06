"""Run the complete fixed M3 case in base-only and each supported official DLC."""
import concurrent.futures
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = ['test_heavens_frontier.py', 'test_heavens_campaign.py', 'test_heavens_settlement.py']


def run(manifest, cases=CASES, output_name='heavens-m3-dlc-matrix'):
    name = manifest.parent.name if manifest else 'base-only'
    identity = json.loads(manifest.read_text(encoding='utf-8'))['id'] if manifest else None
    started = time.perf_counter()
    output = ROOT/'build'/output_name
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        app = Path(folder)
        shutil.copytree(ROOT/'content', app/'content')
        if manifest:
            shutil.copytree(manifest.parent, app/'dlc'/manifest.parent.name)
        env = {**os.environ, 'CULTIVATION_APP_ROOT':str(app), 'PYTHONIOENCODING':'utf-8'}
        code = '''import json, sys, pytest
from cultivation_life.content_registry import EXTENSION_REPORT
loaded = [r['id'] for r in EXTENSION_REPORT if r['status'] == 'loaded']
assert loaded == json.loads(sys.argv[1]), EXTENSION_REPORT
print(json.dumps(EXTENSION_REPORT, ensure_ascii=False), flush=True)
raise SystemExit(pytest.main(sys.argv[2:]))
'''
        args = [sys.executable, '-u', '-c', code, json.dumps([identity] if identity else []),
                *[str(ROOT/'tests'/case) for case in cases], '-q', '--disable-warnings',
                '-o', f'cache_dir={app / "pytest-cache"}']
        with (output/(name+'.log')).open('w', encoding='utf-8') as log:
            result = subprocess.run(args, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    row = dict(id=identity or 'base-only', exit_code=result.returncode, seconds=round(time.perf_counter()-started, 2))
    print(json.dumps(row), flush=True)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--settlement-only', action='store_true', help='Recheck final R3 changes in all profiles')
    parser.add_argument('--case', action='append', help='Explicit pytest path relative to tests; may be repeated')
    parser.add_argument('--output-name', help='Name of the report directory under build')
    args = parser.parse_args()
    cases = ['test_heavens_settlement.py', 'test_heavens_frontier.py::test_actual_road_and_recon_route_roundtrip_uses_one_npc_year_per_elapsed_year'] if args.settlement_only else CASES
    output_name = 'heavens-m3-dlc-settlement-final' if args.settlement_only else 'heavens-m3-dlc-matrix'
    if args.case:
        cases = args.case
    if args.output_name:
        if Path(args.output_name).name != args.output_name or args.output_name in {'.', '..'}:
            parser.error('output-name must be one directory name')
        output_name = args.output_name
    manifests = [None, *sorted((ROOT/'dlc').glob('*/manifest.json'))]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(lambda manifest: run(manifest, cases, output_name), manifests))
    (ROOT/'build'/output_name/'report.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
    if not all(row['exit_code'] == 0 for row in rows):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
