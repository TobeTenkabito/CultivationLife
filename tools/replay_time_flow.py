"""Compare ordinary actions and travel, including interruption and full saves."""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import subprocess
import sys
import tempfile
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cultivation_life.engine import GameEngine


def replay():
    records = []
    identifiers = itertools.count(1)
    scenarios = [
        ('rest', 1, 'normal'), ('rest', 2, 'normal'), ('cultivate', 2, 'normal'),
        ('commission', 2, 'normal'), ('treasure', 2, 'normal'),
        ('rest', 2, 'interrupted'), ('rest', 2, 'death'),
        ('travel', 1, 'normal'), ('travel', 2, 'normal'),
        ('travel', 2, 'interrupted'), ('travel', 2, 'death'),
        ('travel', 2, 'zero'), ('travel', 2, 'lethal'),
    ]
    with patch('cultivation_life.runtime.datetime') as clock, patch(
        'uuid.uuid4', side_effect=lambda: uuid.UUID(int=next(identifiers)),
    ):
        clock.now.return_value = datetime(2026, 10, 3, tzinfo=timezone.utc)
        for seed in (17, 9901, 44001):
            for action, realm, outcome in scenarios:
                with tempfile.TemporaryDirectory() as directory:
                    engine = GameEngine(ROOT, Path(directory))
                    key = engine.create_game('TimeReplay', 'heavenly', 'dao', seed, preset_id='core')['id']
                    game = engine._load(key)
                    game.pending_event = None
                    game.player.realm_index, game.player.layer = realm, 1
                    game.player.next_tribulation_age = None
                    engine.store.save(game)
                    original_year = engine._advance_world_year

                    def annual(actual, rng, news, **kwargs):
                        result = original_year(actual, rng, news, **kwargs)
                        if outcome == 'death':
                            engine._die(actual, 'Time replay death', 'SYS_TIME_REPLAY')
                            return False
                        return False if outcome == 'interrupted' else result

                    engine._advance_world_year = annual
                    if action == 'travel':
                        origin = game.player.location_id
                        destination = next(row['id'] for row in engine.maps.worlds['human']['locations']
                            if row['id'] != origin and engine.maps.travel_plan('human', origin, row['id'], realm).status == 'ok')
                        plan = engine.maps.travel_plan('human', origin, destination, realm)
                        # Force duration and arrival hazards while retaining real route/map data.
                        plan = replace(plan, years=0 if outcome == 'zero' else 11,
                                       status='lethal' if outcome == 'lethal' else 'ok',
                                       warning='Time replay hazard' if outcome == 'lethal' else '')
                        with patch.object(engine.maps, 'travel_plan', return_value=plan):
                            result = engine.travel_map(key, destination)
                    else:
                        result = engine.advance(key, action, 3)
                    label = f'{action}-{realm}-{outcome}'
                    for phase, value in [('result', result), ('reload', engine.get_game(key))]:
                        raw = json.dumps([value, engine.store.load(key).to_dict()],
                                         ensure_ascii=False, sort_keys=True).encode()
                        records.append([seed, label, phase, hashlib.sha256(raw).hexdigest()])
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--compare', type=Path)
    args = parser.parse_args()
    records = replay()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(records, indent=2), encoding='utf-8')
    if args.compare and records != json.loads(args.compare.read_text(encoding='utf-8')):
        raise SystemExit('Time replay differs from baseline')
    print(f'{len(records)} time checkpoints' + (' match baseline' if args.compare else ' captured'))


if __name__ == '__main__':
    if os.environ.get('PYTHONHASHSEED') != '0':
        raise SystemExit(subprocess.call([sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
                                        env={**os.environ, 'PYTHONHASHSEED': '0'}))
    main()
