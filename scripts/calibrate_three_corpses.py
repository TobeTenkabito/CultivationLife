"""Paired three-corpse trials across every generated doctrine in many worlds.

Uses the production trial adapter and round runner. No gameplay balance changes.
Raw per-fight CSV and profile JSON distinguish worlds, doctrines and battle rolls.
"""
import argparse
import copy
import csv
import json
import random
from collections import Counter, defaultdict
from dataclasses import replace
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
from pathlib import Path
from unittest.mock import patch
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.calibrate_immortal_trials import fixture, ADAPTER
from cultivation_life.engine.progression.immortal_trials import start, initialize
from cultivation_life.system.combat.trials import run_batch
from cultivation_life.system.immortal_aperture import ensure_aperture
from cultivation_life.rules import max_hp, max_mp, combat_power, expected_combat_power
from cultivation_life.models import Technique


PROFILES = [dict(id=f'r{r}-t{t}', rank=r, temper=t)
            for r in (4, 8, 9, 12, 13) for t in (0, 5, 10)]
PROFILES += [dict(id=f'r{r}-guard-i{i}', rank=r, temper=10, stance='guard', investment=i)
             for r in (8, 12, 13) for i in (0, 40)]
PROFILES += [dict(id=f'r12-press-i{i}', rank=12, temper=10, investment=i) for i in (40, 80)]
PROFILES += [dict(id=f'r12-energy{int(e*100)}', rank=12, temper=10, energy=e) for e in (.25, .5, .75)]
PROFILES += [dict(id=f'r{r}-secondary', rank=r, temper=10, level=4) for r in (12, 13)]
PROFILES += [dict(id=f'r12-power{power}', rank=12, temper=10, power=power) for power in (.5, 1.5)]
PROFILES += [dict(id='no-field', rank=0, temper=0)]
PROFILES += [dict(id=f'r13-boost{boost}', rank=13, temper=10, perfected_boost=boost)
             for boost in (1.1, 1.15, 1.25, 1.5)]
PROFILES += [dict(id=f'r{r}-five-layer', rank=r, temper=10, five_layer_model=True) for r in (4, 8, 12, 13)]
PROFILES += [dict(id=f'r{r}-five-cap5', rank=r, temper=10, five_layer_model=True, copy_cap=10) for r in (4, 8, 12, 13)]
PROFILES += [dict(id=f'r{r}-fusion{f}', rank=r, temper=10, fusion=f, eligible_only=True)
             for r in (8, 12, 13) for f in (0, 1, 8)]


@lru_cache(maxsize=16)
def world(seed):
    game = fixture('three_corpses', seed=seed, field_rank=0)
    p = game.player
    p.immortal_veins = {str(r): 27 for r in (9, 10, 11)}
    p.hp, p.mp = max_hp(p), max_mp(p)
    return game


def prepare(seed, index, profile):
    game = copy.deepcopy(world(seed))
    p, record = game.player, game.doctrine_state['player']
    d = list(game.doctrine_state['definitions'].values())[index]
    key, level = d['id'], profile.get('level', 8)
    if profile['rank']:
        record['progress'][key] = dict(level=level, experience=0)
        record['active'] = key
        record['origin'] = key if level > 4 else None
        record['annotations'][key] = list(range(1, level + 1))
        record['voisinage_training'][key] = dict(rank=profile['rank'],
            **{axis: profile['temper'] for axis in ('stability', 'incursion', 'authority')})
        manual = Technique(**copy.deepcopy(d['manuals'][0]))
        manual.level = level
        p.known_techniques = [manual]
        if profile.get('fusion'):
            from cultivation_life.system.doctrine.fusion import compile_manual
            from cultivation_life.system.doctrine.provider import config
            record['fusion'] = {key: {'level':profile['fusion'], 'experience':0}}
            p.known_techniques = [Technique(**copy.deepcopy(b)) for b in d['manuals']]
            fused = Technique(**compile_manual(seed, d, config()['words']))
            fused.level = profile['fusion']
            p.known_techniques.append(fused)
    p.hp, p.mp = max_hp(p), max_mp(p)
    p.outer_king_fixed_combat_power = 0
    p.outer_king_fixed_combat_power = expected_combat_power(11, 9) * profile.get('power', 1) - combat_power(p)
    p.combat_plan = dict(manual=True, stance=profile.get('stance', 'press'), investment=profile.get('investment', 0))
    ensure_aperture(p)
    p.immortal_aperture['current'] = p.immortal_aperture['capacity'] * profile.get('energy', 1)
    from cultivation_life.system.doctrine.voisinage_training import multiplier, base_multiplier
    with patch('cultivation_life.system.doctrine.voisinage_training.multiplier',
               side_effect=lambda value: (base_multiplier(value) * (profile['perfected_boost'] if value == 13 else 1)
                                         if 'perfected_boost' in profile else multiplier(value))):
        start(ADAPTER, game, 'three_corpses')
        battle = initialize(game, game.active_trial)
    if profile.get('five_layer_model'):
        # Laboratory-only projection: stage-end comparisons under five layers
        # per stage. Superego stays at 化境四层, now ordinal nine, not ten.
        new_rank = {4:5, 8:10, 12:15, 13:16}[profile['rank']]
        for owner in ('player', 'enemy-2'):
            state = battle.units[owner]
            old_rank = profile['rank'] if owner == 'player' else min(8, profile['rank'])
            target_rank = new_rank if owner == 'player' else min(profile.get('copy_cap', 9), new_rank)
            factor = (1 + .22 * (target_rank-1)) * 1.1 / multiplier(old_rank)
            fields = tuple(replace(f, **{axis:getattr(f,axis)*factor for axis in ('stability','incursion','authority')
                                        if getattr(f,axis) is not None}) for f in state.unit.capabilities.voisinages)
            state.unit = replace(state.unit, capabilities=replace(state.unit.capabilities, voisinages=fields))
    selected = battle.units['player'].unit.capabilities.voisinages
    effects = '+'.join(sorted({e.kind for f in selected for e in f.actions()})) or 'none'
    # Record actually bound resources: energy may be constrained by battle caps.
    return game, battle, d, effects


def simulate_profile(task):
    profile, seeds, repeats, max_rounds, folder = task
    rows, groups = [], defaultdict(Counter)
    for seed in seeds:
        for index in range(25):
            # Fixed definitions have seed-independent mechanics. Test them once,
            # without inflating their sample count by repeating identical worlds.
            if index < 2 and seed != seeds[0]:
                continue
            definition = list(world(seed).doctrine_state['definitions'].values())[index]
            if profile.get('eligible_only') and (len(definition['manuals']) < 6 or max(b['grade'] for b in definition['manuals']) > 11):
                continue
            game, original, definition, effects = prepare(seed, index, profile)
            group = 'fixed' if definition['fixed'] else 'generated'
            initial = original.units['player'].current
            for roll in range(repeats):
                battle = copy.deepcopy(original)
                state = copy.deepcopy(game.active_trial['battle_state'])
                rng = random.Random(910000 + roll)
                result = 'ongoing'
                while state['round'] < max_rounds and result == 'ongoing':
                    result, _ = run_batch(battle, state, rng, batch_size=min(24, max_rounds-state['round']))
                own = battle.units['player']
                row = dict(profile=profile['id'], world_seed=seed, doctrine=definition['id'],
                    name=definition['name'], group=group, effects=effects, roll=roll,
                    result=result, rounds=state['round'], initial_energy=initial,
                    remaining_energy=round(own.current, 3), body=round(own.body, 6),
                    surviving_corpses=sum(s.vitality > 0 for k,s in battle.units.items() if k != 'player'))
                rows.append(row)
                groups[group][result] += 1
    path = Path(folder) / (profile['id'] + '.csv')
    with path.open('w', encoding='utf-8', newline='') as output:
        if rows:
            writer = csv.DictWriter(output, fieldnames=rows[0].keys())
            writer.writeheader(); writer.writerows(rows)
    generated = [r for r in rows if r['group'] == 'generated']
    by_doctrine, by_effect = defaultdict(Counter), defaultdict(Counter)
    for r in generated:
        by_doctrine[(r['world_seed'], r['doctrine'])][r['result']] += 1
        by_effect[r['effects']][r['result']] += 1
    victories = [r for r in generated if r['result'] == 'victory']
    return dict(profile=profile, outcomes={g:dict(c) for g,c in groups.items()},
        generated_doctrines=len(by_doctrine),
        all_rolls_won=sum(c['victory'] == repeats for c in by_doctrine.values()),
        no_rolls_won=sum(c['victory'] == 0 for c in by_doctrine.values()),
        effects={k:dict(v) for k,v in sorted(by_effect.items())},
        maximum_rounds=max((r['rounds'] for r in generated), default=0),
        minimum_winning_energy=min((r['remaining_energy'] for r in victories), default=None),
        minimum_winning_body=min((r['body'] for r in victories), default=None),
        raw_file=path.name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--worlds', type=int, default=10)
    parser.add_argument('--repeats', type=int, default=5)
    parser.add_argument('--seed', type=int, default=15200)
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--max-rounds', type=int, default=480)
    parser.add_argument('--profiles', default='')
    parser.add_argument('--output', type=Path, default=ROOT/'build/three-corpses-1512')
    args = parser.parse_args()
    if min(args.worlds, args.repeats, args.max_rounds) < 1:
        parser.error('worlds, repeats and max-rounds must be positive')
    args.output.mkdir(parents=True, exist_ok=True)
    profiles = [p for p in PROFILES if (p['id'] in args.profiles.split(',') if args.profiles else not p.get('eligible_only') and not p.get('perfected_boost') and not p.get('five_layer_model'))]
    if not profiles: parser.error('No matching profiles')
    seeds = [args.seed + i * 7919 for i in range(args.worlds)]
    tasks = [(p,seeds,args.repeats,args.max_rounds,str(args.output)) for p in profiles]
    report = dict(world_seeds=seeds, battle_repeats=args.repeats, sampling_round_budget=args.max_rounds,
                  note='Ongoing is unresolved, never counted as failure; game itself has no round limit.', profiles=[])
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for result in pool.map(simulate_profile, tasks):
            report['profiles'].append(result)
            (args.output/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            print(json.dumps(result,ensure_ascii=False),flush=True)


if __name__ == '__main__':
    main()
