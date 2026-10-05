"""Compare closed mode with a pre-M0 source tree using the time replay.

Only the intentional schema increment, empty heavens container and framework
description correction and new pure UI projections are normalized.
Old NPCs, resources, clocks and RNG are hashed.
Use separate processes with the same extension configuration for each tree.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace


def normalized_digest(raw):
    value = json.loads(raw)
    document = value[1]
    if document.get('heavens_state', {}) != {}:
        raise ValueError('Closed-mode replay unexpectedly created heavens state')
    document.pop('heavens_state', None)
    public_heavens = value[0].pop('heavens', None)
    if public_heavens and (public_heavens['records'] or public_heavens['generation_enabled']):
        raise ValueError('Closed replay exposed generated heavens content')
    panels = value[0].get('spatial', {}).get('panels', [])
    if 'heavens' in panels:
        panels.remove('heavens')  # New read/settings/escrow UI, not world simulation.
    if document['version'] not in (8, 9):
        raise ValueError('M0 comparison accepts only schemas 8 and 9')
    document['version'] = 8
    descriptions = {
        '凌驾于仙界、修罗界、幽冥界与轮回界之上的跨界系统框架；未来承载诸界往来、战争、盟约与共同大事。',
        '宇宙整体之中诸界、修行、往来与共同变化的系统框架；修士只能认识一隅。',
    }
    for stage in value[0].get('world_route', {}).get('stages', []):
        if stage.get('system') == 'heavens':
            if stage.get('description') not in descriptions:
                raise ValueError('Unexpected framework description in M0 replay')
            stage['description'] = 'heavens M0 description correction'
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--compare', type=Path)
    parser.add_argument('--trace-directory', type=Path)
    args = parser.parse_args()
    root = args.source_root.resolve()
    spec = importlib.util.spec_from_file_location('heavens_time_replay', root / 'tools/replay_time_flow.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Replace only the replay's hash sink, never the game's hashlib functions.
    count = 0
    def capture(raw):
        nonlocal count
        if args.trace_directory:
            args.trace_directory.mkdir(parents=True, exist_ok=True)
            (args.trace_directory / f'{count:03}.json').write_bytes(raw)
        count += 1
        return normalized_digest(raw)
    module.hashlib = SimpleNamespace(sha256=capture)
    # M1 defaults new games on; this replay explicitly exercises closed mode.
    from cultivation_life.content_registry import WORLD_SYSTEMS
    WORLD_SYSTEMS['heavens_framework']['enabled'] = False
    records = module.replay()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(records, indent=2), encoding='utf-8')
    if args.compare and records != json.loads(args.compare.read_text(encoding='utf-8')):
        raise SystemExit('Closed-mode replay differs from pre-M0 baseline')
    print(f'{len(records)} closed-mode checkpoints' + (' match baseline' if args.compare else ' captured'))


if __name__ == '__main__':
    if os.environ.get('PYTHONHASHSEED') != '0':
        raise SystemExit(subprocess.call([sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
                                        env={**os.environ, 'PYTHONHASHSEED': '0'}))
    main()
