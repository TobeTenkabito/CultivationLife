"""Compare travel, merchant and immortal commands, including full saved state."""
from __future__ import annotations

import argparse
import copy
import hashlib
import itertools
import json
import os
import random
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cultivation_life.engine import GameEngine
from cultivation_life.models import Technique
from cultivation_life.rules import add_item, learn_technique


def replay():
    records = []
    ids = itertools.count(1)
    with patch('cultivation_life.runtime.datetime') as clock, patch(
        'uuid.uuid4', side_effect=lambda: uuid.UUID(int=next(ids)),
    ):
        clock.now.return_value = datetime(2026, 10, 3, tzinfo=timezone.utc)
        for seed in (17, 9901, 44001):
            with tempfile.TemporaryDirectory() as directory:
                engine = GameEngine(ROOT, Path(directory))
                key = engine.create_game('ThreeGroups', 'heavenly', 'dao', seed, preset_id='core')['id']

                def step(label, action, rejects=False):
                    try:
                        result = action()
                    except ValueError as error:
                        if not rejects:
                            raise
                        result = {'rejected': str(error)}
                    else:
                        if rejects:
                            raise AssertionError(f'{label}: expected rejection')
                    raw = json.dumps([result, engine.store.load(key).to_dict()],
                                     ensure_ascii=False, sort_keys=True).encode()
                    records.append([seed, label, hashlib.sha256(raw).hexdigest()])
                    return result

                game = engine._load(key)
                game.pending_event = None
                game.player.next_tribulation_age = None
                add_item(game.player, 'spirit_stone', 10**9)
                engine.store.save(game)
                origin = game.player.location_id
                destination = next(row['id'] for row in engine.maps.worlds['human']['locations']
                    if row['id'] != origin and engine.maps.travel_plan('human', origin, row['id'], game.player.realm_index).status == 'ok')
                step('travel', lambda: engine.travel_map(key, destination))
                step('travel-invalid', lambda: engine.travel_map(key, 'missing-location'), True)

                game = engine._load(key)
                game.pending_event = None
                alliance = game.merchant_state['worlds']['human'][0]
                game.player.location_id = alliance['offices'][0]['location_id']
                engine.store.save(game)
                step('join', lambda: engine.merchant_action(key, 'join', {'alliance_id': alliance['id']}))
                step('join-again', lambda: engine.merchant_action(key, 'join', {'alliance_id': alliance['id']}), True)
                step('post', lambda: engine.merchant_action(key, 'post', {'kind': 'intel', 'stars': 1}))
                game = engine._load(key)
                order = game.merchant_state['posted'][-1]
                order.update(status='working', started_age=game.player.age, finish_age=game.player.age + 2,
                             will_finish=True, worker='ReplayWorker')
                game.player.age += 2
                def settle():
                    engine._advance_merchant_year(game)
                    engine.store.save(game)
                    return engine.present(game)
                step('delivery', settle)
                step('delivery-repeat', settle)
                step('post-refund', lambda: engine.merchant_action(key, 'post', {'kind': 'intel', 'stars': 1}))
                game = engine._load(key)
                game.player.age = game.merchant_state['posted'][-1]['deadline']
                step('refund', settle)
                step('refund-repeat', settle)
                step('merchant-reload', lambda: GameEngine(ROOT, Path(directory)).get_game(key))

                key = engine.create_game('ImmortalReplay', 'supreme_metal', 'dao', seed, preset_id='true_immortal')['id']
                game = engine._load(key)
                game.pending_event = None
                game.heavenly_court['open_election'] = None
                game.player.next_tribulation_age = None
                game.player.opportunity = 10**10
                add_item(game.player, 'immortal_trace', 10000)
                add_item(game.player, 'spirit_stone', 10**9)
                definition = next(d for d in game.doctrine_state['definitions'].values() if len(d['manuals']) >= 6)
                for manual in definition['manuals']:
                    learn_technique(game.player, Technique(**copy.deepcopy(manual)))
                game.doctrine_state['player']['progress'][definition['id']] = {'level': 0, 'experience': 0}
                engine.store.save(game)
                with patch('cultivation_life.system.immortal_system.decode_rng', return_value=random.Random(2)):
                    step('vein-failure', lambda: engine.immortal_action(key, 'open_vein'))
                with patch('cultivation_life.system.immortal_system.decode_rng', return_value=random.Random(1)):
                    step('vein-success', lambda: engine.immortal_action(key, 'open_vein'))
                step('body-reject', lambda: engine.immortal_action(key, 'select_body_manual', supply_id='missing'), True)
                step('explore', lambda: engine.doctrine_action(key, 'explore', definition['id']))
                step('activate-reject', lambda: engine.doctrine_action(key, 'activate', definition['id']), True)
                step('aperture-reject', lambda: engine.aperture_action(key, 'missing'), True)
                step('upper-voisinage-reject', lambda: engine.upper_voisinage_action(key, 'train', 'missing'), True)
                step('immortal-reload', lambda: GameEngine(ROOT, Path(directory)).get_game(key))
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
        raise SystemExit('Replay differs from baseline')
    print(f'{len(records)} three-group checkpoints' + (' match baseline' if args.compare else ' captured'))


if __name__ == '__main__':
    if os.environ.get('PYTHONHASHSEED') != '0':
        raise SystemExit(subprocess.call([sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
                                        env={**os.environ, 'PYTHONHASHSEED': '0'}))
    main()
