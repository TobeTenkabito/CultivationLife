"""Compare ordinary settlement and RNG against an explicit pre-change Git ref."""
import argparse
import copy
import hashlib
import importlib.util
import json
import random
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cultivation_life.engine import GameEngine
from cultivation_life.system.combat_system import PlayerCombatSystem
from cultivation_life.system.combat.contracts import CombatCapabilities, Combatant, VoisinageDefinition
from cultivation_life.system.combat.voisinages import VoisinageBattle
from cultivation_life.system.combat import trials


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-ref', required=True)
    args = parser.parse_args()
    relative = 'cultivation_life/system/combat_system.py'
    baseline = subprocess.run(['git','rev-parse',args.baseline_ref], cwd=ROOT, capture_output=True, check=True).stdout.decode().strip()
    source = subprocess.run(['git','show',f'{baseline}:{relative}'], cwd=ROOT, capture_output=True, check=True).stdout.decode('utf-8')
    name = 'cultivation_life.system._combat_replay_baseline'
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader=None))
    sys.modules[name] = module
    exec(compile(source, name, 'exec'), module.__dict__)
    cases, timings = [], {'before':[], 'after':[]}
    with tempfile.TemporaryDirectory() as directory:
        engine = GameEngine(ROOT, Path(directory)/'saves')
        game = engine.store.load(engine.create_game('benchmark','heavenly','dao',902,preset_id='core')['id'])
        units = engine._player_combat_units(game)
        own = sum(unit.power*unit.integrity for unit in units)
        for seed in range(20):
            for ratio in [.2,.9,4.]:
                target = dict(target_name='beast',target_power=own*ratio,target_realm_index=game.player.realm_index,combat_type='beast')
                ra, rb = random.Random(seed), random.Random(seed)
                outputs = []
                for label, system, rng in [('before',module.PlayerCombatSystem,ra),('after',PlayerCombatSystem,rb)]:
                    start = time.perf_counter()
                    value = system.resolve(game.player,copy.deepcopy(units),copy.deepcopy(target),False,rng,
                                           current_hp_ratio=1,current_mp_ratio=1).to_dict()
                    timings[label].append((time.perf_counter()-start)*1000)
                    for row in value['rounds']:
                        row.pop('ordinary_exchange',None)
                    outputs.append(value)
                assert outputs[0] == outputs[1] and ra.getstate() == rb.getstate(), (seed,ratio)
                cases.append(dict(seed=seed,ratio=ratio,rounds=len(outputs[0]['rounds'])))
    stage_cases = []
    definition = VoisinageDefinition('benchmark-field','测试域','benchmark',4,100,120,40,'suppress',20)
    caster = CombatCapabilities(capacity=1000,current=800,force_tier=2,ward_tier=2,resource_tier=2,
        voisinages=(definition,),attainments={'benchmark':4},stance='press')
    trial_name = 'cultivation_life.system.combat._replay_trial_baseline'
    trial_source = subprocess.run(['git','show',f'{baseline}:cultivation_life/system/combat/trials.py'],cwd=ROOT,capture_output=True,check=True).stdout.decode('utf-8')
    old_trials = importlib.util.module_from_spec(importlib.util.spec_from_loader(trial_name,loader=None))
    sys.modules[trial_name] = old_trials
    exec(compile(trial_source,trial_name,'exec'),old_trials.__dict__)
    for seed in range(6):
        for mode, own_caps, enemy_caps in [('mixed',caster,caster),('field-only',caster,CombatCapabilities()),
                                           ('enemy-field',CombatCapabilities(),caster)]:
            values, states, random_states = [], [], []
            for system in (module.PlayerCombatSystem,PlayerCombatSystem):
                rng = random.Random(seed)
                battle = VoisinageBattle([Combatant('player','你','player',own,own_caps),
                                         Combatant('enemy-0','敌人','enemy',own,enemy_caps)])
                value = system.resolve(game.player,copy.deepcopy(units),dict(target_name='测试域',target_power=own,
                    target_realm_index=game.player.realm_index,max_rounds=5),False,rng,
                    current_hp_ratio=1,current_mp_ratio=1,phases=battle).to_dict()
                for row in value['rounds']:
                    row.pop('ordinary_exchange',None)
                values.append(value);states.append(trials.dump_battle(battle));random_states.append(rng.getstate())
            assert values[0] == values[1] and states[0] == states[1] and random_states[0] == random_states[1], (mode,seed)
            stage_cases.append(dict(mode=mode,seed=seed,rounds=len(values[0]['rounds'])))
        for mode in ('human_decline','voisinage_backlash','three_corpses'):
            values, states, random_states = [], [], []
            for runner in (old_trials.run_batch,trials.run_batch):
                rng = random.Random(seed)
                battle = VoisinageBattle([Combatant('player','你','player',1000,caster),
                                         Combatant('enemy-0','劫相','enemy',1000,caster)])
                state = dict(mode=mode,round=0,mp_ratio=1,stats={side:{key:100 for key in
                    ('might','guard','mobility','sense','sustain','breach')} for side in ('player','enemy')})
                outcome, rows = runner(battle,state,rng,batch_size=6)
                for row in rows:
                    row.pop('ordinary_exchange',None)
                values.append((outcome,rows,state));states.append(trials.dump_battle(battle));random_states.append(rng.getstate())
            assert values[0] == values[1] and states[0] == states[1] and random_states[0] == random_states[1], (mode,seed)
            stage_cases.append(dict(mode=mode,seed=seed,rounds=len(values[0][1])))
    result = dict(status='passed',baseline_ref=baseline,cases=cases,stage_cases=stage_cases,
                  source_sha256=hashlib.sha256((ROOT/relative).read_bytes()).hexdigest(),
                  timing_ms={key:dict(median=statistics.median(value),mean=statistics.mean(value)) for key,value in timings.items()},
                  scope='ordinary, mixed, pure-field and trial settlement/RNG comparison; timings cover ordinary copy and serialization, not annual economy')
    output = ROOT/'build/combat-replay'
    output.mkdir(parents=True,exist_ok=True)
    (output/'settlement-baseline.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=result['status'],cases=len(cases),stage_cases=len(stage_cases),timing_ms=result['timing_ms'])))


if __name__ == '__main__':
    main()
