"""Replay Guixu and war transitions against a pre-refactor baseline.

Digests cover complete results and persisted state (including RNG and history).
Use --output before migration, then --output and --compare after migration.
"""
from __future__ import annotations

import argparse
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
from cultivation_life.content_registry import GUIXU_TIDE_CONTENT
from cultivation_life.engine import GameEngine


def replay(seeds=(17, 9901, 44001), *, trace_directory=None):
    records = []
    ids = itertools.count(1)
    with patch('cultivation_life.runtime.datetime') as clock, patch(
        'uuid.uuid4', side_effect=lambda: uuid.UUID(int=next(ids)),
    ):
        clock.now.return_value = datetime(2026, 10, 3, tzinfo=timezone.utc)
        for seed in seeds:
            with tempfile.TemporaryDirectory() as folder:
                engine = GameEngine(ROOT, Path(folder))
                key = engine.create_game('ExpeditionReplay', 'supreme_water', 'dao', seed)['id']

                def step(label, action, rejects=False):
                    try:
                        value = action()
                    except ValueError as error:
                        if not rejects:
                            raise
                        value = {'rejected': str(error)}
                    else:
                        if rejects:
                            raise AssertionError(f'{label}: expected rejection')
                    raw = json.dumps([value, engine.store.load(key).to_dict()],
                                     sort_keys=True, ensure_ascii=False).encode()
                    if trace_directory:
                        trace_directory.mkdir(parents=True, exist_ok=True)
                        (trace_directory / f'{seed}-{label}.json').write_bytes(raw)
                    records.append([seed, label, hashlib.sha256(raw).hexdigest()])
                    return value

                def mutate(label, action):
                    def run():
                        game = engine.store.load(key)
                        result = action(game)
                        engine.store.save(game)
                        return result
                    return step(label, run)

                dungeon = next(d for d in GUIXU_TIDE_CONTENT['dungeons'] if d['world'] == 'human')

                def open_dungeon(game):
                    cycle = game.guixu_state['cycles'][dungeon['id']]
                    engine._open_guixu_cycle(game, dungeon, cycle, random.Random(seed))
                    game.pending_event = None
                    game.player.location_id = dungeon['entry_location_id']
                    game.player.realm_index = 3
                    game.player.layer = 1

                mutate('open-dungeon', open_dungeon)
                step('enter', lambda: engine.guixu_action(key, 'enter', {'dungeon_id': dungeon['id']}))
                session = engine.store.load(key).guixu_state['player_session']
                if session.get('pending_team_offer'):
                    step('accept-team', lambda: engine.guixu_action(key, 'team_accept', {}))
                step('invalid-move', lambda: engine.guixu_action(key, 'move', {'target_layer_id': 'final'}), True)
                step('search', lambda: engine.guixu_action(key, 'search', {}))
                session = engine.store.load(key).guixu_state['player_session']
                if session.get('pending_threat'):
                    step('surrender', lambda: engine.guixu_action(key, 'threat_surrender', {}))
                step('return', lambda: engine.guixu_action(key, 'return', {}))
                step('repeat-entry', lambda: engine.guixu_action(key, 'enter', {'dungeon_id': dungeon['id']}), True)
                mutate('close-dungeon', lambda g: engine._close_guixu_cycle(
                    g, dungeon, g.guixu_state['cycles'][dungeon['id']], random.Random(seed)))
                with patch.dict(GUIXU_TIDE_CONTENT, {'dungeons': []}):
                    step('dlc-disabled', lambda: engine.get_game(key))
                    step('disabled-entry', lambda: engine.guixu_action(key, 'enter', {'dungeon_id': dungeon['id']}), True)

                key = engine.create_game('WarReplay', 'none', 'dao', seed, preset_id='nascent')['id']

                def declare(game):
                    game.pending_event = None
                    game.player.faction_id = 'tianjian'
                    relation = engine._war_relation(game, 'sect', 'tianjian', 'wanmo')
                    engine._set_diplomatic_relation(game, relation, 'war', 'tianjian', 'wanmo', 'sect', -75)
                    return game.wars[0]['id']

                war_id = mutate('declare-war', declare)
                step('vanguard', lambda: engine.war_action(key, war_id, 'conquest'))
                step('vanguard-fight', lambda: engine.choose(key, 'fight'))

                def advance(game):
                    game.settings['auto_advance_player_wars'] = True
                    engine._advance_wars_unit(game, random.Random(seed))

                mutate('auto-war-round', advance)
                step('invalid-peace', lambda: engine.war_peace(key, war_id, 'invalid'), True)
                step('white-peace', lambda: engine.war_peace(key, war_id, 'white_peace'))
                def redeclare():
                    game = engine.store.load(key)
                    relation = engine._war_relation(game, 'sect', 'tianjian', 'wanmo')
                    return engine._set_diplomatic_relation(game, relation, 'war', 'tianjian', 'wanmo', 'sect', -75)
                step('truce-blocks-war', redeclare, True)
                step('reload', lambda: GameEngine(ROOT, Path(folder)).get_game(key))

                key = engine.create_game('WarDefeatReplay', 'none', 'dao', seed, preset_id='nascent')['id']
                war_id = mutate('second-war', declare)

                def call_allies(game):
                    engine._war_relation(game, 'sect', 'tianjian', 'puti').update(status='alliance', affinity=100.0)
                    return engine._call_war_allies(game, game.wars[0], 'attacker', random.Random(1))

                mutate('allied-roster', call_allies)

                def collapse(game):
                    war = game.wars[0]
                    war['war_score'] = -76.0
                    war['morale']['attacker'] = 0.0
                    engine._finish_war_by_morale(game, war)

                mutate('morale-collapse', collapse)
                step('accept-ai-peace', lambda: engine.war_action(key, war_id, 'accept_ai_peace'))

                key = engine.create_game('TrappedReplay', 'supreme_water', 'dao', seed)['id']
                mutate('trapped-open', open_dungeon)
                step('trapped-enter', lambda: engine.guixu_action(key, 'enter', {'dungeon_id': dungeon['id']}))

                def trap(game):
                    game.guixu_state['player_session']['remaining_days'] = 0
                    engine._close_guixu_cycle(game, dungeon, game.guixu_state['cycles'][dungeon['id']], random.Random(seed))

                mutate('tide-close', trap)
                step('trapped-body-training', lambda: engine.advance(key, 'body_train'))
                step('trapped-sense-training', lambda: engine.advance(key, 'sense_train'))
                with patch.dict(GUIXU_TIDE_CONTENT, {'dungeons': []}):
                    step('disabled-session-cleanup', lambda: engine.get_game(key))
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--compare', type=Path)
    parser.add_argument('--trace-directory', type=Path, help='Optional complete checkpoint data for diagnosing differences')
    args = parser.parse_args()
    records = replay(trace_directory=args.trace_directory)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(records, indent=2), encoding='utf-8')
    if args.compare and records != json.loads(args.compare.read_text(encoding='utf-8')):
        raise SystemExit('Replay differs from baseline; inspect checkpoint digests')
    print(f'{len(records)} expedition checkpoints' + (' match baseline' if args.compare else ' captured'))


if __name__ == '__main__':
    # Presentation code includes tags derived from sets. Pin their iteration
    # order across processes without changing or sorting gameplay output.
    if os.environ.get('PYTHONHASHSEED') != '0':
        raise SystemExit(subprocess.call(
            [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
            env={**os.environ, 'PYTHONHASHSEED': '0'},
        ))
    main()
