"""Replay identity changes, soul lifecycles and Buddhist assemblies against a baseline."""
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

from cultivation_life.content_registry import REALMS, TECHNIQUE_CATALOG
from cultivation_life.engine import GameEngine
from cultivation_life.rules import add_item, learn_technique, max_hp, max_mp, opportunity_required
from cultivation_life.runtime import decode_rng, encode_rng


def replay():
    records, identities = [], itertools.count(1)
    with patch('cultivation_life.runtime.datetime') as clock, patch(
        'uuid.uuid4', side_effect=lambda: uuid.UUID(int=next(identities)),
    ):
        clock.now.return_value = datetime(2026, 10, 3, tzinfo=timezone.utc)
        for seed in (17, 9901, 44001):
            with tempfile.TemporaryDirectory() as directory:
                engine = GameEngine(ROOT, Path(directory))
                key = engine.create_game('KeyFlows', 'supreme_fire', 'demonic', seed)['id']

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

                def mutate(label, action):
                    def run():
                        game = engine.store.load(key)
                        result = action(game)
                        engine.store.save(game)
                        return result
                    return step(label, run)

                def setup_demonic(game):
                    p = game.player
                    game.pending_event = None
                    p.realm_index, p.layer = 3, 1
                    p.hp, p.mp = max_hp(p), max_mp(p)
                    p.next_tribulation_age = None
                    p.lifespan = 10000
                    p.foreign_souls = [dict(id='foreign', name='Foreign', strength=1, progress=0,
                        required=8, remaining_bonus=0, refined=False)]
                    p.prisoners = [dict(id=key, name=key, gender='female', realm_index=1, layer=1,
                        combat_power=20, path='dao', world=p.world, age=25, lifespan=120, affinity=0)
                        for key in ('release', 'recruit', 'execute')]
                mutate('prepare-demonic', setup_demonic)
                step('release-captive', lambda: engine.captive_action(key, 'release', 'release'))
                step('recruit-captive', lambda: engine.manage_concubine(key, 'recruit', 'recruit'))
                step('cauldron', lambda: engine.manage_concubine(key, 'recruit', 'cauldron'))
                step('cauldron-repeat', lambda: engine.manage_concubine(key, 'recruit', 'cauldron'), True)
                step('convert-puppet', lambda: engine.manage_concubine(key, 'recruit', 'corpse'))
                step('execute-captive', lambda: engine.captive_action(key, 'execute', 'execute'))
                step('refine-secluded', lambda: engine.secluded_refine_foreign_souls(key))
                step('refine-empty', lambda: engine.secluded_refine_foreign_souls(key), True)
                mutate('demonic-annual', lambda game: engine._annual_demonic_update(game, random.Random(seed)))

                key = engine.create_game('GhostFlows', 'mutated_yin', 'ghost', seed)['id']
                def setup_ghost(game):
                    game.pending_event = None
                    p = game.player
                    p.realm_index, p.layer = 2, REALMS[2].layers
                    p.opportunity = opportunity_required(p)
                    p.next_tribulation_age = None
                    p.ghost_wangsheng_energy = 8
                mutate('prepare-ghost', setup_ghost)
                step('spend-wangsheng', lambda: engine.spend_wangsheng(key))
                step('prepare-reincarnation', lambda: engine.prepare_ghost_reincarnation(key))
                mutate('cancel-reincarnation-prompt', lambda game: setattr(game, 'pending_event', None))
                step('reincarnate', lambda: engine.reincarnate_ghost(key))
                step('reincarnate-again', lambda: engine.reincarnate_ghost(key), True)
                mutate('soul-erosion', lambda game: engine._apply_soul_erosion_units(game, 2))
                def prepare_possession(game):
                    game.player.prisoners = [dict(id='body', name='Host', realm_index=1, layer=1,
                        path='dao', race='human', spirit_root='heavenly', age=25, lifespan=120)]
                    engine._die(game, 'Replay battle', 'SYS_COMBAT', offer_captive_possession=True)
                mutate('battle-death', prepare_possession)
                step('battle-possession', lambda: engine.post_battle_possess(key, 'body'))
                step('leave-body', lambda: engine.leave_possessed_body(key))
                step('leave-again', lambda: engine.leave_possessed_body(key), True)

                key = engine.create_game('AssemblyFlows', 'supreme_wood', 'buddhist', seed)['id']
                art = copy.deepcopy(next(t for t in TECHNIQUE_CATALOG.values() if t.path == 'buddhist'))
                def setup_buddhist(game):
                    game.pending_event = None
                    game.player.realm_index, game.player.layer = 1, 1
                    game.player.next_tribulation_age = None
                    game.player.location_id = next(s.location_id for s in game.sects.values() if s.world == 'human' and not s.extinct)
                    learn_technique(game.player, art)
                    add_item(game.player, 'spirit_stone', 1000000)
                mutate('prepare-assembly', setup_buddhist)
                step('start-assembly', lambda: engine.buddhist_action(key, 'start', technique=art.id))
                for stage in range(3):
                    def resolve(game):
                        pending = game.buddhist_state['assembly']['pending']
                        assert pending, 'Expected an assembly event'
                        rng = decode_rng(game.seed, game.rng_state)
                        game.pending_event = None
                        result = engine._resolve_buddhist_assembly({'action': 'teach'}, game, pending, rng)
                        game.rng_state = encode_rng(rng)
                        return result
                    mutate(f'assembly-resolve-{stage}', resolve)
                    if stage < 2:
                        step(f'assembly-continue-{stage}', lambda: engine.buddhist_action(key, 'continue'))
                step('assembly-cancel-empty', lambda: engine.buddhist_action(key, 'cancel'), True)
                step('reload', lambda: GameEngine(ROOT, Path(directory)).get_game(key))
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
    print(f'{len(records)} key-flow checkpoints' + (' match baseline' if args.compare else ' captured'))


if __name__ == '__main__':
    if os.environ.get('PYTHONHASHSEED') != '0':
        raise SystemExit(subprocess.call([sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
                                        env={**os.environ, 'PYTHONHASHSEED': '0'}))
    main()
