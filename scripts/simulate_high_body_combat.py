"""Seeded high-body matchups on the production battle ledger; no user saves.

This is a correctness harness, not a claim about live-game balance. Ordinary
damage inputs are controlled fixtures; body profiles and settlement are real.
"""
import argparse
from collections import Counter
from dataclasses import asdict
from itertools import product
import json,math,random,sys,time
from pathlib import Path
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from cultivation_life.system.combat.contracts import CombatCapabilities,Combatant,VoisinageDefinition,VoisinageEffect
from cultivation_life.system.combat.voisinages import VoisinageBattle
from cultivation_life.system.combat.trials import dump_battle,load_battle
from cultivation_life.system.divine_lights import profile as light_profile
from cultivation_life.system.wuyun import profile as aggregate_profile
from cultivation_life.system.monster_body import profile as monster_profile,config as monster_config
from cultivation_life.system.ghost_body import profile as ghost_profile

FAMILIES=('immortal','demonic','monster','ghost')
SCENARIOS=('strike','single','heal','suppress','low_energy','capture')


def canonical(value):return json.loads(json.dumps(value,sort_keys=True,allow_nan=False))


def profile(family,rank):
    actor=SimpleNamespace(path={'immortal':'dao'}.get(family,family),ghost_host_body=None,ghost_core_state=None,
        spirit_state={},immortal_body={'level':50,'divine_lights':{k:rank for k in ('kun','zhen','kan','li','qian')},
            'monster':{'level':50,'training':{r['id']:rank for r in monster_config()['mechanisms']}} ,
            'ghost_training':{k:rank for k in ('wuxiang','zhaoye','yuhun','wangqing','yinguo')}},
        asura_cultivation={'body_level':50,'aggregates':{k:rank for k in ('se','shou','xiang','xing','shi')}})
    lights,levels=light_profile(actor,player=True)
    rows=aggregate_profile(actor,player=True) or monster_profile(actor,player=True) or ghost_profile(actor,player=True)
    return dict(divine_lights=lights,divine_light_levels=levels,body_mechanisms=rows)


def make_battle(left,right,rank,group,scenario,seed):
    units=[];size=2 if group else 1
    for side,family in (('player',left),('enemy',right)):
        enemies=tuple(f'enemy-{i}' for i in range(size)) if side=='player' else tuple(['player']+(['ally-1'] if group else []))
        for index in range(size):
            key=('player' if index==0 else 'ally-1') if side=='player' else f'enemy-{index}'
            kind='suppress' if scenario=='suppress' else 'strike'
            effects=(VoisinageEffect(kind,35,.085,target_mode='single' if scenario=='single' else 'all'),)
            if scenario=='heal':effects+= (VoisinageEffect('restore_body',22,.12,target='self'),VoisinageEffect('restore_field',19,.15,target='self'))
            domain=VoisinageDefinition('audit:'+key,'模拟邻域','audit',1,115+index*3,26,13,kind,35,.085,
                authority=145,stability=125,incursion=165,max_targets=3,effects=effects)
            usable=400 if seed%2 else 1000
            current=usable*(.3 if scenario=='low_energy' else 1.)
            caps=CombatCapabilities(capacity=1000,current=current,usable_capacity=usable,resource_tier=2,
                force_tier=2,artifact_tier=2,attack_cost=3,voisinages=(domain,),attainments={'audit':1},
                target_ids=enemies,resource_link='legacy_mp' if index==0 and seed%2 else 'independent',
                **profile(family,rank))
            units.append(Combatant(key,f'{family}:{key}',side,100,caps,
                integrity=.7 if scenario=='heal' else 1.,body_integrity=.7 if scenario=='heal' else 1.))
    battle=VoisinageBattle(units,contest_ratio=1.25)
    if scenario=='capture':battle.set_objectives('capture','kill')
    return battle


def step(battle,rng,round_no):
    pm=battle.mp_ratio('player',1.);em=battle.mp_ratio('enemy',1.)
    frame=battle.begin_round(round_no,player_condition=max(.05,1-battle.ordinary_loss('player')),
        enemy_condition=max(.05,1-battle.ordinary_loss('enemy')),player_mp=pm,enemy_mp=em,
        rng=rng,first_side='player' if round_no%2 else 'enemy')
    if frame.ordinary and battle.verdict() is None:
        pm=battle.mp_ratio('player',pm);em=battle.mp_ratio('enemy',em)
        battle.sync_resources(player_mp=max(0,pm-.035),enemy_mp=max(0,em-.035))
        battle.ordinary_damage(.07*rng.uniform(.85,1.15),.07*rng.uniform(.85,1.15))
    battle.finish_round(player_mp=battle.mp_ratio('player',pm),enemy_mp=battle.mp_ratio('enemy',em))
    return battle.report()


def invariants(battle):
    assert not battle._body_queue,'Unsettled events at round boundary'
    assert battle._body_chain==(),'Leaked causal context'
    for key,state in battle.units.items():
        cap=state.unit.capabilities;limit=cap.capacity if cap.usable_capacity is None else cap.usable_capacity
        for value in (state.vitality,state.body,state.current,state.karma_spent,state.field_strain):assert math.isfinite(value),(key,value)
        assert -1e-9<=state.vitality<=1+1e-9 and 0<=state.body<=1+1e-9,key
        assert -1e-9<=state.current<=limit+1e-9,key
        threshold=next((r.effects['karma_threshold'] for r in cap.body_mechanisms if 'karma_threshold' in r.effects),1.)
        assert 0<=state.karma_spent<threshold+1e-9,key
        assert not state.death_observed or state.vitality<=0 or state.body<=0,'Dead unit revived'
    if battle._body_round:
        for key,tokens in battle._body_round.allowances.items():
            for token in tokens:assert len(token.chain)==len(set(token.chain)),(key,token.chain)
        for key in battle._body_round.muted:assert not battle._body_round.effective[key],key
    canonical(battle.report())


def run_case(left,right,rank,group,scenario,seed,*,max_rounds=24,replay=True,permutation=False):
    battle=make_battle(left,right,rank,group,scenario,seed);rng=random.Random(seed)
    reordered=None
    if permutation:
        reordered=VoisinageBattle([s.unit for s in reversed(tuple(battle.units.values()))],contest_ratio=battle.contest_ratio)
        reordered.set_objectives(battle.objectives['player'],battle.objectives['enemy'])
        reordered_rng=random.Random(seed)
    trace=Counter();checked=permutation_checks=0
    for n in range(1,max_rounds+1):
        resumed=None
        if replay and n%3==0:
            resumed=load_battle(canonical(dump_battle(battle)));other=random.Random();other.setstate(rng.getstate())
        report=step(battle,rng,n);invariants(battle)
        if reordered is not None:
            step(reordered,reordered_rng,n);invariants(reordered)
            assert canonical(dump_battle(reordered)['states'])==canonical(dump_battle(battle)['states']),'Roster order changes battle state'
            assert reordered.verdict()==battle.verdict() and reordered_rng.getstate()==rng.getstate(),'Roster order changes outcome or RNG'
            permutation_checks+=1
        if resumed is not None:
            second=step(resumed,other,n);invariants(resumed)
            assert canonical(second)==canonical(report),'Resumed battle report differs'
            assert canonical(dump_battle(resumed))==canonical(dump_battle(battle)),'Resumed battle ledger differs'
            assert other.getstate()==rng.getstate(),'Resumed battle RNG differs'
            checked+=1
        trace.update(r['kind'] for r in battle._light_trace)
        if battle.verdict() is not None:break
    return dict(rounds=n,outcome=battle.verdict() or 'round_limit',replays=checked,permutation_checks=permutation_checks,events=dict(trace))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--seeds',type=int,default=8);parser.add_argument('--rounds',type=int,default=24)
    parser.add_argument('--output',type=Path,default=ROOT/'build/high-body-simulation.json');args=parser.parse_args()
    started=time.perf_counter();matrix={};failures=[];events=Counter();total_rounds=total_replays=total_permutations=cases=0
    for left,right,rank,group,scenario,seed in product(FAMILIES,FAMILIES,(0,5,10),(False,True),SCENARIOS,range(args.seeds)):
        cases+=1;label=f'{left}/{right}';row=matrix.setdefault(label,Counter())
        try:
            result=run_case(left,right,rank,group,scenario,seed,max_rounds=args.rounds,permutation=True)
            total_rounds+=result['rounds'];total_replays+=result['replays'];events.update(result['events']);row[result['outcome']]+=1
            total_permutations+=result['permutation_checks']
        except Exception as error:
            failures.append(dict(left=left,right=right,rank=rank,group=group,scenario=scenario,seed=seed,
                error=f'{type(error).__name__}: {error}'))
    payload=dict(cases=cases,rounds=total_rounds,replays=total_replays,permutation_checks=total_permutations,elapsed_seconds=round(time.perf_counter()-started,3),
        matrix=matrix,events=dict(events),failures=failures,scope='Production body profiles and shared battle ledger; fixture ordinary damage; round_limit is a simulation bound, not gameplay truncation.')
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in payload.items() if k not in {'matrix','events','failures','scope'}},ensure_ascii=False))
    print(f'Failures: {len(failures)}; report: {args.output}')
    if failures:raise SystemExit(1)


if __name__=='__main__':main()
