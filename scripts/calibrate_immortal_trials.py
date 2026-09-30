"""Reproducible trial profiles, real capability adapter and round runner.

python scripts/calibrate_immortal_trials.py --samples 25
"""
import argparse
import copy
import json
from pathlib import Path
import random
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cultivation_life.models import Player, GameState, Technique
from cultivation_life.content_registry import CONTENT_DOCUMENTS
from cultivation_life.rules import max_hp, max_mp, expected_combat_power, combat_power
from cultivation_life.system.doctrine.provider import ensure
from cultivation_life.system.immortal_aperture import ensure_aperture
from cultivation_life.engine.progression.immortal_trials import start, initialize
from cultivation_life.system.combat.trials import run_batch

EVENTS = {e['id']:e for e in CONTENT_DOCUMENTS['breakthrough_trial_events.json']['events']}
ADAPTER = SimpleNamespace(events_by_id=EVENTS, _instantiate_event=lambda event, game, rng: copy.deepcopy(event))


def fixture(kind, *, seed=7429, field_rank=4, doctrine_level=4, temper=0, energy=1, power_ratio=1,
            field_index=0, hp_ratio=1, stance='press', investment=0):
    realm = {'human_decline':9,'heaven_decline':10,'three_corpses':11,'voisinage_backlash':11}[kind]
    p = Player('劫战校准', 'supreme_metal', world='celestial', realm_index=realm, layer=9,
               body_training=100, divine_sense_rank=26 + (realm-8)*3,
               immortal_power_converted=True, immortal_conversion_stage=5, immortal_body={'level':20})
    p.hp, p.mp = max_hp(p) * hp_ratio, max_mp(p)
    p.combat_plan = dict(manual=True, stance=stance, investment=investment)
    p.outer_king_fixed_combat_power = expected_combat_power(realm, 9) * power_ratio - combat_power(p)
    game = GameState('trial-calibration', seed, p, '', '')
    ensure(game)
    d = list(game.doctrine_state['definitions'].values())[field_index]
    key = d['id']
    record = game.doctrine_state['player']
    if field_rank:
        record['progress'][key] = {'level':doctrine_level, 'experience':0}
        record['active'] = key
        record['origin'] = key if doctrine_level > 4 else None
        record['voisinage_training'][key] = dict(rank=field_rank, stability=temper, incursion=temper, authority=temper)
        p.known_techniques = [Technique(**d['manuals'][0])]
    ensure_aperture(p)
    p.immortal_aperture['current'] *= energy
    start(ADAPTER, game, kind, doctrine_id=key if kind=='voisinage_backlash' else None)
    return game


def replay(game, seed=0):
    game = copy.deepcopy(game)
    battle = initialize(game, game.active_trial)
    state = game.active_trial['battle_state']
    rng = random.Random(seed)
    # This is a sampling budget only. Unresolved long fights are reported as
    # ongoing, never converted to an in-game failure or artificial victory.
    for _ in range(20):
        outcome, rows = run_batch(battle, state, rng)
        if outcome != 'ongoing':
            return outcome, state['round'], battle.units['player'].current
    return 'ongoing', state['round'], battle.units['player'].current


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--samples', type=int, default=25)
    parser.add_argument('--recommended', action='store_true')
    args = parser.parse_args()
    profiles = []
    for ratio in (.5, .75, 1, 1.25):
        profiles.append(('human_decline',dict(field_rank=0,power_ratio=ratio)))
    for value in (0,1,4,8):
        for energy in (.1,.3,1):
            profiles.append(('heaven_decline',dict(field_rank=value,energy=energy)))
    for value in (4,8,12):
        for temper in (0,5,10):
            profiles.append(('voisinage_backlash',dict(field_rank=value,temper=temper)))
    for value in (1,4,8,9,12,13):
        profiles.append(('three_corpses',dict(field_rank=value,doctrine_level=8)))
    for value in (1,4,8):
        profiles.append(('heaven_decline',dict(field_rank=value,temper=5,stance='guard',investment=40)))
    for value in (4,8,12):
        profiles.append(('voisinage_backlash',dict(field_rank=value,temper=5,stance='guard',investment=40)))
    for value in (4,8,9,12,13):
        profiles.append(('three_corpses',dict(field_rank=value,doctrine_level=8,temper=5,stance='guard',investment=40)))
    if args.recommended:
        profiles = [('three_corpses',dict(field_rank=value,doctrine_level=8,temper=10,field_index=index))
                    for value in (4,8,9,12,13) for index in (0,1)]
    for kind, kwargs in profiles:
        results = {}
        remaining = []
        for seed in range(args.samples):
            selected = dict(field_index=seed % 25, **{})
            selected.update(kwargs)
            game = fixture(kind, seed=7429+(seed % 25), **selected)
            outcome, rounds, reserve = replay(game, seed)
            results[outcome] = results.get(outcome, 0) + 1
            if outcome=='victory': remaining.append(reserve)
        print(json.dumps(dict(kind=kind, **kwargs, samples=args.samples, outcomes=results,
                              minimum_winning_energy=min(remaining,default=None)),ensure_ascii=False),flush=True)


if __name__ == '__main__':
    main()
