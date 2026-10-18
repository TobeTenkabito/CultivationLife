"""Run existing exact-state replays across releases with one explicit identity.

Only the base-game version is normalized, before runtime imports. Responses,
saves, RNG, history and achievement metadata retain their complete comparisons.
Each invocation runs one replay in its own deterministic process.
"""
from __future__ import annotations

import argparse
import importlib
import os
from pathlib import Path
import re
import runpy
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REPLAYS = dict(lifecycle='replay_lifecycle.py', time='replay_time_flow.py',
               key='replay_key_flows.py', groups='replay_three_groups.py')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kind', choices=REPLAYS, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--compare', type=Path)
    parser.add_argument('--runtime-archive', type=Path)
    parser.add_argument('--identity-version', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'\d+\.\d+\.\d+', args.identity_version):
        parser.error('identity-version must be an explicit semantic version')
    if os.environ.get('PYTHONHASHSEED') != '0':
        raise SystemExit(subprocess.call([sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
            env=os.environ | {'PYTHONHASHSEED': '0', 'CULTIVATION_APP_ROOT': str(ROOT)}))
    os.environ['CULTIVATION_APP_ROOT'] = str(ROOT)
    sys.path.insert(0, str(args.runtime_archive.resolve() if args.runtime_archive else ROOT))
    version = importlib.import_module('cultivation_life.version')
    version.BASE_GAME_VERSION = args.identity_version
    version.BASE_GAME_VERSION_TUPLE = tuple(map(int, args.identity_version.split('.')))
    importlib.import_module('cultivation_life').__version__ = args.identity_version
    script = ROOT / 'tools' / REPLAYS[args.kind]
    sys.argv = [str(script), '--output', str(args.output)]
    if args.compare:
        sys.argv += ['--compare', str(args.compare)]
    if args.runtime_archive and args.kind == 'lifecycle':
        sys.argv += ['--runtime-archive', str(args.runtime_archive)]
    runpy.run_path(str(script), run_name='__main__')


if __name__ == '__main__':
    main()
