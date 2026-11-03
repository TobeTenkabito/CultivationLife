"""Real eightfold fields, six-stat damage, body interactions and causal replay.

All fixtures are offline and equal-resource. No player save is read or written.
The round budget records draws; it never changes production battle termination.
"""
import argparse,copy,json,random,sys,time
from collections import Counter,defaultdict
from dataclasses import replace
from itertools import combinations,product
from pathlib import Path
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from cultivation_life.system import asura
from cultivation_life.asura_discipline_content import ROUTES,build
from cultivation_life.system.combat.contracts import Combatant,CombatCapabilities
from cultivation_life.system.combat.voisinages import VoisinageBattle
from cultivation_life.system.combat.ordinary import exchange_damage
from cultivation_life.system.combat.trials import dump_battle,load_battle
from cultivation_life.system.combat.field_contracts import validate_memory,validate_leases
from scripts.simulate_high_body_combat import profile,invariants,canonical,FAMILIES


def make(left,right,rank,size,scenario,policy='balanced',families=('demonic','demonic')):
    units=[]
    for side,route,family,prefix in zip(('player','enemy'),(left,right),families,('a','b')):
        state=dict(route=route,level=9,domain_rank=13,domain_power=5,domain_name=asura.ROUTE_NAMES[route]+'演武域',
            branches={route:[{'id':f'branch:{i}'} for i in range(3)]},branch_level=9)
        if policy!='balanced':state['branch']='branch:'+str({'aggressive':1,'steady':2}[policy])
        owner=SimpleNamespace(asura_cultivation=state)
        field=asura.field_for(owner);discipline=build(state,asura.config())
        for i in range(size):
            key=f'{prefix}{i}';body=profile(family,rank)
            caps=CombatCapabilities(capacity=9000,current=1800 if scenario=='low_energy' else 9000,
                usable_capacity=9000,resource_tier=2,force_tier=2,artifact_tier=2,ward_tier=2,
                attack_cost=3,voisinages=(field,),attainments={field.attainment:1},field_discipline=discipline,
                **body)
            units.append(Combatant(key,f'{asura.ROUTE_NAMES[route]}·{family}{i}',side,100,caps,
                integrity=.55 if scenario=='wounded' else 1,body_integrity=.55 if scenario=='wounded' else 1,
                cultivation_rank=180))
    battle=VoisinageBattle(units)
    if scenario=='strain':
        for state in battle.units.values():state.field_strain=.3
    return battle


def step(battle,rng,n,first):
    frame=battle.begin_round(n,player_condition=max(.05,1-battle.ordinary_loss('player')),
        enemy_condition=max(.05,1-battle.ordinary_loss('enemy')),player_mp=1,enemy_mp=1,
        rng=rng,first_side=first)
    if frame.ordinary and battle.verdict() is None:
        factors=battle.semantic_ordinary_start();initiative=battle.semantic_initiative(first=='player')
        stats={}
        for side in ('player','enemy'):
            members=[battle.units[key] for key in sorted(battle.units) if battle.units[key].unit.side==side]
            morale=sum(s.morale for s in members)/len(members)
            condition=max(.05,1-battle.ordinary_loss(side))*(.6+.4*morale/100)
            stats[side]={key:100*factors[side].get(key,1)*initiative[side].get(key,1)*frame.stat_factors.get(side,{}).get(key,1)
                for key in ('might','guard','breach')}
            stats[side]['condition']=condition
        damage={}
        for side,other in (('player','enemy'),('enemy','player')):
            a,b=stats[side],stats[other]
            damage[side]=exchange_damage(a['might']*a['condition'],b['guard']*(.72+.28*b['condition']),
                a['breach']/max(1,b['guard']),rng.uniform(.9,1.1),coefficient=.135,minimum=.035,maximum=.42)
        battle.ordinary_damage(damage['player'],damage['enemy'])
    battle.finish_round(player_mp=1,enemy_mp=1)
    invariants(battle)
    assert not battle._field_reserved,'Reserved field action leaked across a round boundary'
    # Validate every mutable field ledger each round. Full descriptor/snapshot
    # reloads also happen initially and at each three-round continuation below.
    for state in battle.units.values():
        validate_memory(state.field_memory,battle.units)
        validate_leases(state.timed_controls,state.field_debts,battle.units)
    return canonical(battle.report())


def states(battle):
    return canonical({key:{k:v for k,v in vars(state).items() if k!='unit'}
        for key,state in battle.units.items()})


def run(left,right,rank,size,scenario,seed,*,limit=48,check=False,policy='balanced',families=('demonic','demonic')):
    battle=make(left,right,rank,size,scenario,policy,families);rng=random.Random(seed)
    reverse=None
    if check:
        reverse=load_battle(canonical(dump_battle(battle)));reverse.units=dict(reversed(tuple(reverse.units.items())))
        reverse_rng=random.Random(seed)
    events=Counter();replays=permutations=0
    for n in range(1,limit+1):
        resumed=None
        if check and n%3==0:
            resumed=load_battle(canonical(dump_battle(battle)));saved_rng=random.Random();saved_rng.setstate(rng.getstate())
        first='player' if seed%2 else 'enemy'
        report=step(battle,rng,n,first)
        if reverse is not None:
            other=step(reverse,reverse_rng,n,first)
            assert states(reverse)==states(battle),'Roster order changed state'
            assert other==report and reverse_rng.getstate()==rng.getstate(),'Roster order changed report or RNG'
            permutations+=1
        if resumed is not None:
            replay=step(resumed,saved_rng,n,first)
            assert replay==report and canonical(dump_battle(resumed))==canonical(dump_battle(battle)),'JSON continuation changed settlement'
            assert saved_rng.getstate()==rng.getstate(),'JSON continuation changed RNG'
            replays+=1
        events.update(e['kind'] for e in battle._light_trace)
        alive={side:any(s.fighting for s in battle.units.values() if s.unit.side==side) for side in ('player','enemy')}
        if not all(alive.values()):break
    score=.5 if all(alive.values()) or not any(alive.values()) else float(alive['player'])
    return dict(score=score,rounds=n,draw=all(alive.values()),events=dict(events),replays=replays,permutations=permutations)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scope',choices=('pvp','causal'),default='pvp')
    parser.add_argument('--seeds',type=int,default=8);parser.add_argument('--seed-offset',type=int,default=12000)
    parser.add_argument('--ranks',type=int,nargs='+',default=[0,5,10]);parser.add_argument('--sizes',type=int,nargs='+',default=[1,3])
    parser.add_argument('--rounds',type=int,default=48);parser.add_argument('--policy',choices=('balanced','aggressive','steady'),default='balanced')
    parser.add_argument('--output',type=Path,default=ROOT/'build/eightfold-simulation.json')
    args=parser.parse_args()
    if args.seeds<1 or args.rounds<1 or any(n not in (0,5,10) for n in args.ranks) or any(n not in (1,2,3) for n in args.sizes):parser.error('Invalid finite simulation budget')
    started=time.perf_counter();records=[];failures=[];counts=Counter();events=Counter();pairs=defaultdict(list)
    if args.scope=='pvp':
        cases=((left,right,rank,size,'normal',seed,swapped,('demonic','demonic'))
            for (left,right),rank,size,seed,swapped in product(combinations(ROUTES,2),args.ranks,args.sizes,
                range(args.seed_offset,args.seed_offset+args.seeds),(False,True)))
    else:
        cases=((route,ROUTES[(index+seed)%len(ROUTES)],rank,size,scenario,seed,False,(a,b))
            for (index,route),a,b,rank,size,scenario,seed in product(enumerate(ROUTES),FAMILIES,FAMILIES,args.ranks,args.sizes,
                ('normal','wounded','low_energy','strain'),range(args.seed_offset,args.seed_offset+args.seeds)))
    for left,right,rank,size,scenario,seed,swapped,families in cases:
        label=dict(left=left,right=right,rank=rank,size=size,scenario=scenario,seed=seed,swapped=swapped,families=families)
        counts['cases']+=1
        try:
            result=run(right if swapped else left,left if swapped else right,rank,size,scenario,seed,
                limit=args.rounds,check=args.scope=='causal',policy=args.policy,families=families)
            score=1-result['score'] if swapped else result['score']
            pairs[left+'/'+right].append(score);counts['rounds']+=result['rounds'];counts['draws']+=result['draw']
            counts['replays']+=result['replays'];counts['permutations']+=result['permutations'];events.update(result['events'])
            records.append(dict(label,score=score,rounds=result['rounds'],draw=result['draw']))
        except Exception as error:
            failures.append(dict(label,error=f'{type(error).__name__}: {error}'))
    matrix={key:sum(scores)/len(scores) for key,scores in pairs.items()}
    totals=defaultdict(list)
    if args.scope=='pvp':
        for pair,score in matrix.items():
            left,right=pair.split('/');totals[left].append(score);totals[right].append(1-score)
    output=dict(scope=args.scope,parameters=vars(args)|{'output':str(args.output)},counts=dict(counts),
        scores={k:sum(v)/len(v) for k,v in totals.items()},matrix=matrix,events=dict(events),failures=failures,records=records,
        elapsed_seconds=round(time.perf_counter()-started,2),
        methodology='Equal six-stat native eightfold fields and production body profiles. Real damage/fees/targets; finite diagnostic round budget, no user saves. Causal scope includes synthetic cross-family capability combinations.')
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:output[k] for k in ('scope','counts','scores','elapsed_seconds')},ensure_ascii=False));print('Failures:',len(failures))
    if failures:raise SystemExit(1)


if __name__=='__main__':main()
