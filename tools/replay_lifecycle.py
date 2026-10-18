"""Compare response preparation and regional settlement against a source archive."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import itertools
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def replay(snapshots=None):
    from cultivation_life.engine import GameEngine
    from cultivation_life.engine.world import regions
    from cultivation_life.models import HistoryRecord
    from cultivation_life.rules import max_hp, max_mp
    from cultivation_life.system import spatial

    records = []
    identifiers = itertools.count(1)
    scenarios = [
        ('dao', 'human', 3), ('ghost', 'human', 3), ('demonic', 'human', 3),
        ('buddhist', 'human', 3), ('confucian', 'human', 3), ('monster', 'human', 3),
        ('dao', 'celestial', 9), ('buddhist', 'celestial', 9),
        ('demonic', 'asura', 9), ('ghost', 'nether', 9),
        ('confucian', 'reincarnation', 9),
    ]
    with patch('cultivation_life.runtime.datetime') as clock, patch(
        'uuid.uuid4', side_effect=lambda: uuid.UUID(int=next(identifiers)),
    ):
        clock.now.return_value = datetime(2026, 10, 18, tzinfo=timezone.utc)
        for seed in (17, 91):
            for path, world, rank in scenarios:
                with tempfile.TemporaryDirectory() as directory:
                    engine = GameEngine(ROOT, Path(directory))
                    label = f'{seed}:{path}:{world}'

                    def capture(phase, result):
                        value = dict(label=label, phase=phase, result=result,
                                     save=engine.store.load(identity).to_dict(),
                                     metadata=engine.achievements.metadata.read())
                        raw = json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
                        if snapshots:
                            (snapshots / f'{len(records):03}.json.gz').write_bytes(gzip.compress(raw))
                        records.append(dict(label=label, phase=phase,
                                            sha256=hashlib.sha256(raw).hexdigest()))

                    result = engine.create_game('LifecycleReplay', 'supreme_metal', path, seed,
                        monster_species_id='fox' if path == 'monster' else None,
                        custom_start=dict(world=world, realm_index=rank, layer=1,
                                          divine_sense_rank=23, sect='new', family='new'))
                    identity = result['id']
                    capture('create', result)
                    capture('load', engine.get_game(identity))
                    capture('load-repeat', engine.get_game(identity))
                    game = engine._load(identity)
                    game.settings.update(silent_events=True, guixu_event_popup=False)
                    game.player.next_tribulation_age = None
                    game.player.opportunity = 0
                    game.pending_event = None
                    engine.store.save(game)
                    deps = getattr(engine._dependencies, 'regions', engine)
                    regions.ensure(deps, game)
                    news = []
                    for _ in range(3):
                        game.player.age += 1
                        engine._advance_world_year(game, random.Random(game.player.age), news,
                                                   encounters=False)
                    engine.store.save(game)
                    capture('regional-years', dict(news=news, shown=engine.present(game)))
                    for destination in sorted({'human', 'spirit'} - {world}):
                        regions.synchronize(deps, game, [destination])
                        engine.store.save(game)
                        capture('catch-up:' + destination, engine.present(game))
                        regions.synchronize(deps, game, [destination])
                        engine.store.save(game)
                        capture('catch-up-repeat:' + destination, engine.present(game))
                    if world != 'human':
                        continue
                    game.player.realm_index, game.player.layer = 4, 1
                    game.player.hp, game.player.mp = max_hp(game.player), max_mp(game.player)
                    game.pending_event = None
                    rift = spatial.new_rift(game, random.Random(8), engine.maps, controlled=True)
                    engine.store.save(game)
                    with patch.object(spatial, 'outcome_weights', return_value={'secluded': 1}):
                        result = engine.spatial_action(identity, 'enter', {'target_id': rift['id']})
                    capture('instance-entry', result)
                    capture('instance-reload', engine.get_game(identity))
                    game = engine._load(identity)
                    game.history.append(HistoryRecord('REPLAY_MARK', 1, game.player.age,
                        'Lifecycle', None, 'mark', 'Read-only view boundary', {}, ['self']))
                    engine.store.save(game)
                    capture('instance-view', engine.present(game))
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--compare', type=Path)
    parser.add_argument('--runtime-archive', type=Path)
    parser.add_argument('--snapshots', type=Path)
    args = parser.parse_args()
    os.environ['CULTIVATION_APP_ROOT'] = str(ROOT)
    sys.path.insert(0, str(args.runtime_archive.resolve() if args.runtime_archive else ROOT))
    if args.snapshots:
        args.snapshots.mkdir(parents=True, exist_ok=True)
    records = replay(args.snapshots)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(records, ensure_ascii=False), encoding='utf-8')
    if args.compare:
        before = json.loads(args.compare.read_text(encoding='utf-8'))
        changed = [(a['label'], a['phase']) for a, b in zip(before, records) if a != b]
        if len(before) != len(records) or changed:
            raise SystemExit(f'Lifecycle replay differs: {changed[:20]}')
    print(f'{len(records)} lifecycle checkpoints' + (' match baseline' if args.compare else ' captured'))


if __name__ == '__main__':
    if os.environ.get('PYTHONHASHSEED') != '0':
        raise SystemExit(subprocess.call([sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
                                        env={**os.environ, 'PYTHONHASHSEED': '0'}))
    main()
