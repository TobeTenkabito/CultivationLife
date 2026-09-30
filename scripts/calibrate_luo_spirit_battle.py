"""Replay the authored Luo encounter with fixed player profiles and RNG seeds.

python scripts/calibrate_luo_spirit_battle.py --samples 200
Uses the production story adapter, capability binding and round resolver.
Extra combat power is a flat bonus, with no extra gear traits or allies.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import random
import sys
from types import SimpleNamespace
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cultivation_life.content_registry import WORLD_SYSTEMS
from cultivation_life.engine.engine_event_runtime import _resolve_story_combat_check, _story_unit_full_power
from cultivation_life.engine.engine_combat_runtime import _player_combat_units
from cultivation_life.engine.combat_capabilities import bind_capabilities
from cultivation_life.models import GameState, Player
from cultivation_life.rules import combat_power, max_hp, max_mp, combat_root_mana_cost_multiplier
from cultivation_life.system.combat_system import PlayerCombatSystem


def fixture(power, *, body=100, mp_ratio=1):
    player = Player('校准修士', 'supreme_metal', world='spirit', realm_index=8, layer=7,
                    body_training=body, divine_sense_rank=26)
    player.hp, player.mp = max_hp(player), max_mp(player) * mp_ratio
    player.outer_king_fixed_combat_power = power - combat_power(player)
    if player.outer_king_fixed_combat_power < 0:
        raise ValueError('Requested rating is below this profile\'s intrinsic combat power')
    game = GameState('calibration', 1, player, '', '')
    captured = {}

    def capture(_game, target, _lethal, _rng):
        captured.update(target)
        return 'victory', ''

    deps = SimpleNamespace(_combat=capture, _story_unit_full_power=_story_unit_full_power,
                           _public_party=lambda game: [])
    _resolve_story_combat_check(deps, {'checks': [{'stat': 'combat_power', 'value': 55_000_000}]},
                               game, {'id': 'EVT_MA_LIANG_005', '_choice_id': 'attack_bottle'}, random.Random(0))
    units = _player_combat_units(deps, game, captured)
    return game, captured, units


def replay(fixture_data, seed):
    game, target, units = copy.deepcopy(fixture_data)
    binding = bind_capabilities(game, units, target, WORLD_SYSTEMS['transcendent_combat'])
    player = game.player
    return PlayerCombatSystem.resolve(
        player, units, target, False, random.Random(seed),
        current_hp_ratio=player.hp / max_hp(player), current_mp_ratio=player.mp / max_mp(player),
        battlefield_tags=[target['natural_terrain'], *target['artificial_conditions']],
        mana_cost_multiplier=combat_root_mana_cost_multiplier(player, 8, 7), phases=binding.battle,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples', type=int, default=200)
    args = parser.parse_args()
    if args.samples < 1:
        parser.error('--samples must be positive')
    for body, mp in ((100, 1), (0, 1), (100, .7)):
        for millions in (55, 65, 75, 85, 95, 105, 115, 125, 140):
            data = fixture(millions * 1_000_000, body=body, mp_ratio=mp)
            counts = Counter(replay(data, seed).outcome for seed in range(args.samples))
            print(json.dumps(dict(power=millions * 1_000_000, body=body, mp_ratio=mp,
                                  samples=args.samples, outcomes=dict(counts)), ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
