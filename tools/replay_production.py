"""Deterministic economy/crafting/formation replay; compare against a prior checkout.

Run before and after a refactor with --output, then pass the first JSON to
--compare. Digests cover complete return values and saves, including RNG/history.
Intentional rule/content changes require a reviewed new baseline.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import random
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cultivation_life.engine import GameEngine
from cultivation_life.rules import add_item
from cultivation_life.system.crafting_system import crafting_material_definitions, make_crafting_material_instance
from cultivation_life.system.formation_system import formation_material_definitions, make_formation_material_instance


def replay(seeds=(44001, 55001, 17007)):
    records = []
    ids = itertools.count(1)
    with patch('cultivation_life.runtime.datetime') as clock, patch(
        'uuid.uuid4', side_effect=lambda: uuid.UUID(int=next(ids)),
    ):
        clock.now.return_value = datetime(2026, 10, 3, tzinfo=timezone.utc)
        for seed in seeds:
            with tempfile.TemporaryDirectory() as folder:
                engine = GameEngine(ROOT, Path(folder))
                created = engine.create_game('ProductionReplay', 'supreme_metal', 'dao', seed, preset_id='core')
                key = created['id']

                def step(label, action, *, rejects=False):
                    try:
                        value = action()
                    except ValueError as error:
                        if not rejects:
                            raise
                        value = {'rejected': str(error)}
                    else:
                        if rejects:
                            raise AssertionError(f'{label}: invalid operation unexpectedly succeeded')
                    saved = engine.store.load(key).to_dict()
                    raw = json.dumps([value, saved], sort_keys=True, ensure_ascii=False).encode()
                    records.append([seed, label, hashlib.sha256(raw).hexdigest()])
                    return value

                step('created', lambda: created)
                game = engine.store.load(key)
                game.pending_event = None
                add_item(game.player, 'spirit_stone', 10_000_000)
                defs = crafting_material_definitions()
                rng = random.Random(seed)
                materials = [make_crafting_material_instance(defs[name], rng, source='Replay', origin_world='human')
                             for name in ('human_cold_iron', 'human_cloud_silk', 'human_cloud_silk', 'human_sun_fire')]
                game.player.crafting_materials.extend(materials)
                engine.store.save(game)
                payload = dict(mold_id='umbrella', name='ReplayArtifact', primary_id=materials[0]['id'],
                               secondary_a_id=materials[1]['id'], secondary_b_id=materials[2]['id'],
                               quench_id=materials[3]['id'], allocations={'combat_power': 20, 'max_hp': 10})
                step('craft-preview', lambda: engine.preview_crafting(key, payload))
                step('duplicate-material', lambda: engine.preview_crafting(key, payload | {
                    'secondary_b_id': materials[1]['id']}), rejects=True)
                step('blueprint', lambda: engine.save_crafting_blueprint(key, payload))
                shown = step('forge', lambda: engine.forge_crafted_artifact(key, payload))
                artifact_id = shown['crafting_system']['artifacts'][0]['id']
                step('consumed-material', lambda: engine.forge_crafted_artifact(key, payload), rejects=True)

                game = engine.store.load(key)
                defs_array = formation_material_definitions()
                array_materials = [make_formation_material_instance(defs_array[name], source='Replay', origin_world='human')
                                  for name in ('human_greenwood_stake', 'human_red_sun_sand', 'human_xuanyin_stone')]
                game.player.formation_materials.extend(array_materials)
                engine.store.save(game)
                array_payload = {'name': 'ReplayArray', 'slots': [row['id'] for row in array_materials] + [None] * 6, 'activate': True}
                step('formation-preview', lambda: engine.preview_formation(key, array_payload))
                shown = step('formation-save', lambda: engine.save_formation(key, array_payload))
                loadout = shown['formation_system']['active_formation_id']
                step('formation-release', lambda: engine.deactivate_formation(key))
                step('formation-reactivate', lambda: engine.activate_formation(key, loadout))
                shown = step('ground-deploy', lambda: engine.deploy_ground_formation(key, 'player'))
                ground = shown['formation_system']['ground_arrays'][0]['id']
                game = engine.store.load(key)
                game.player.formation_ground_arrays[0]['durability'] = 50
                game.player.formation_repair_supplies['human_array_marrow'] = 1
                engine.store.save(game)
                step('ground-repair', lambda: engine.repair_ground_formation(key, ground, 'human_array_marrow', 1))
                step('ground-withdraw', lambda: engine.withdraw_ground_formation(key, ground))
                step('ground-double-withdraw', lambda: engine.withdraw_ground_formation(key, ground), rejects=True)

                game = engine.store.load(key)
                engine._schedule_exchange(game, rng)
                game.player.location_id = game.exchange_state['location_id']
                engine._open_exchange(game, rng)
                offer = game.exchange_state['offers'][0]
                demanded = []
                for demand in offer['demands']:
                    for _ in range(demand['quantity']):
                        item = make_crafting_material_instance(defs[demand['definition_id']], rng, source='Replay', origin_world='human')
                        game.player.crafting_materials.append(item)
                        demanded.append({'id': item['id'], 'quantity': 1})
                engine.store.save(game)
                step('exchange-identity', lambda: engine.exchange_action(key, 'identity', {'alias': '青笠客'}))
                exchange_payload = {'offer_id': offer['id'], 'materials': demanded}
                step('exchange-trade', lambda: engine.exchange_action(key, 'trade', exchange_payload))
                step('exchange-repeat', lambda: engine.exchange_action(key, 'trade', exchange_payload), rejects=True)

                game = engine.store.load(key)
                engine._schedule_auction(game, rng)
                game.player.location_id = game.auction_state['location_id']
                engine.store.save(game)
                step('auction-consign', lambda: engine.crafted_artifact_action(key, artifact_id, 'consign'))
                game = engine.store.load(key)
                engine._open_auction(game, rng)
                engine.store.save(game)
                lot = next(row for row in game.auction_state['lots'] if row.get('seller_id') != 'player')
                step('auction-bid', lambda: engine.place_auction_bid(key, lot['id']))
                game = engine.store.load(key)
                engine._cancel_auction_for_world_change(game)
                engine.store.save(game)
                step('auction-cancel-refund', lambda: engine.present(game))

                game.auction_state = {'id': 'replay-black', 'status': 'black_market', 'world': 'human',
                                      'location_id': game.player.location_id, 'location_name': 'Replay',
                                      'black_market_results': []}
                engine.store.save(game)
                step('black-search', lambda: engine.search_black_market(key, '.*'))
                game = engine.store.load(key)
                for kind in ('crafting_material', 'formation_material', 'formation_supply'):
                    result = next(row for row in game.auction_state['black_market_results'] if row['kind'] == kind)
                    step('black-buy-' + kind, lambda result=result: engine.buy_black_market_item(key, result['id'], 2))
                step('invalid-search', lambda: engine.search_black_market(key, '['), rejects=True)
                step('reload', lambda: GameEngine(ROOT, Path(folder)).get_game(key))
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--compare', type=Path)
    args = parser.parse_args()
    records = replay()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(records, indent=2), encoding='utf-8')
    if args.compare:
        expected = json.loads(args.compare.read_text(encoding='utf-8'))
        if records != expected:
            raise SystemExit('Replay differs from baseline; inspect checkpoint digests')
    print(f'{len(records)} production checkpoints' + (' match baseline' if args.compare else ' captured'))


if __name__ == '__main__':
    main()
