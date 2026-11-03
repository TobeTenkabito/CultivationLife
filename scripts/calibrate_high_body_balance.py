"""Controlled equal-resource balance trials using the real six-stat damage curve.

All avatars have identical stats, gear and field definitions. Candidate values
are supplied to the original pure descriptor builders; no world or save IO.
"""
import argparse,copy,json,random,sys,time
from collections import Counter,defaultdict
from itertools import combinations,product
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from cultivation_life.content_registry import CONTENT_DOCUMENTS,WORLD_SYSTEMS
from cultivation_life.ghost_body_content import EFFECTS as GHOST_EFFECTS,IDS as GHOST_IDS,build as ghost_build
from cultivation_life.body_mechanism_content import build as demonic_build
from cultivation_life.monster_body_content import build as monster_build,UNLOCKS
from cultivation_life.system.combat.body_mechanisms import BodyMechanism
from cultivation_life.system.combat.contracts import Combatant,CombatCapabilities,VoisinageDefinition,VoisinageEffect
from cultivation_life.system.combat.ordinary import exchange_damage
from cultivation_life.system.combat.voisinages import VoisinageBattle

FAMILIES=('demonic','immortal','monster','ghost')
STYLES=('contested','aggressive','defensive','recovery')


def configuration():
    return copy.deepcopy(dict(immortal=CONTENT_DOCUMENTS['doctrines.json']['cultivation']['divine_lights'],
        demonic=WORLD_SYSTEMS['asura_manifestation']['five_aggregates'],
        monster=WORLD_SYSTEMS['monster_body']['mechanisms'],ghost=GHOST_EFFECTS))


def profile(family,rank,level,cfg,monster_choice='auto'):
    if family=='demonic':return tuple(demonic_build(r,rank) for r in cfg[family] if level>=r['unlock_level'])
    if family=='monster':
        choice=monster_choice if monster_choice=='auto' or rank>=UNLOCKS[monster_choice] else 'auto'
        return tuple(monster_build(r,rank,choice) for r in cfg[family] if level>=r['unlock_level'])
    if family=='ghost':return tuple(ghost_build(k,rank,effects=cfg[family]) for i,k in enumerate(GHOST_IDS,1) if level>=i*10)
    rows=[]
    for i,r in enumerate(cfg[family]):
        if level<r['unlock_level']:continue
        value=r['base']+rank*r['growth'];key=r['id']
        effects={'kun':dict(ward=2,seal_resist=r.get('resist_growth',0)*rank),
            'zhen':dict(heal_preserve=1,heal_bonus=r.get('heal_growth',0)*rank),
            'kan':dict(extra=1),'li':dict(erosion=value),'qian':dict(silence=1)}[key]
        rows.append(BodyMechanism(key,r['name'],effects,priority=i*10,chance=value if key in {'kan','qian'} else 1.,level=rank))
    return tuple(rows)


def match(left,right,rank,size,style,seed,cfg,*,level=50,limit=48,authority_scale=1.,monster_choice='auto',effect_power=.12):
    units=[];rng=random.Random(seed);first_side='player' if seed%2 else 'enemy'
    for side,family,prefix,opponent in [('player',left,'a','b'),('enemy',right,'b','a')]:
        for i in range(size):
            key=f'{prefix}{i}';targets=tuple(f'{opponent}{j}' for j in range(size))
            effects=(VoisinageEffect('strike',32,effect_power),)
            if style=='recovery':effects+=(VoisinageEffect('restore_body',26,.13,target='self'),VoisinageEffect('restore_field',20,.15,target='self'))
            incursion={'contested':120,'aggressive':170,'defensive':85,'recovery':120}[style]
            field=VoisinageDefinition('balance:'+key,'校准领域','balance',1,100*authority_scale,24,14,'strike',32,effect_power,
                incursion=incursion*authority_scale,stability=120*authority_scale,authority=110*authority_scale,max_targets=3,effects=effects)
            capacity=800 if seed%4<2 else 1600
            current=capacity*(.35 if seed%4==3 else 1.)
            caps=CombatCapabilities(capacity=capacity,current=current,usable_capacity=capacity,resource_tier=2,
                force_tier=2,artifact_tier=2,voisinages=(field,),attainments={'balance':1},target_ids=targets,
                body_mechanisms=profile(family,rank,level,cfg,monster_choice))
            units.append(Combatant(key,family,side,100,caps,integrity=.7 if style=='recovery' else 1.,body_integrity=.7 if style=='recovery' else 1.))
    battle=VoisinageBattle(units);events=Counter()
    for n in range(1,limit+1):
        condition={s:max(.05,1-battle.ordinary_loss(s)) for s in ('player','enemy')}
        frame=battle.begin_round(n,player_condition=condition['player'],enemy_condition=condition['enemy'],
            player_mp=1,enemy_mp=1,rng=rng,first_side=first_side)
        if frame.ordinary and battle.verdict() is None:
            power={}
            for side in ('player','enemy'):
                factors=frame.stat_factors[side]
                morale=sum(u.morale for u in battle.units.values() if u.unit.side==side)/size
                power[side]=dict(might=100*factors.get('might',1),guard=100*factors.get('guard',1),breach=100*factors.get('breach',1),
                    condition=max(.05,1-battle.ordinary_loss(side))*(.6+.4*morale/100))
            damage={}
            for side,enemy in [('player','enemy'),('enemy','player')]:
                a,b=power[side],power[enemy]
                damage[side]=exchange_damage(a['might']*a['condition'],b['guard']*(.72+.28*b['condition']),
                    a['breach']/max(1.,b['guard']),rng.uniform(.9,1.1),coefficient=.135,minimum=.035,maximum=.42)
            battle.ordinary_damage(damage['player'],damage['enemy'])
        battle.finish_round(player_mp=1,enemy_mp=1);events.update(r['kind'] for r in battle._light_trace)
        living={s:any(u.fighting for u in battle.units.values() if u.unit.side==s) for s in ('player','enemy')}
        if not all(living.values()):
            score=.5 if not any(living.values()) else float(living['player'])
            return score,n,False,events
    return .5,limit,True,events


def evaluate(cfg,*,seeds=8,ranks=(0,5,10),sizes=(1,2),styles=STYLES,level=50,limit=48,seed_offset=0,authority_scale=1.,monster_choice='auto',effect_power=.12):
    matrix={};splits=defaultdict(lambda:defaultdict(list));events=Counter();outcomes=Counter();rounds=cases=draws=0
    started=time.perf_counter()
    for left,right in combinations(FAMILIES,2):
        scores=[]
        for rank,size,style,seed in product(ranks,sizes,styles,range(seed_offset,seed_offset+seeds)):
            for a,b in ((left,right),(right,left)):
                score,n,draw,event=match(a,b,rank,size,style,seed,cfg,level=level,limit=limit,authority_scale=authority_scale,monster_choice=monster_choice,effect_power=effect_power)
                normalized=score if a==left else 1-score;scores.append(normalized)
                for label in (f'rank:{rank}',f'size:{size}',f'style:{style}'):
                    splits[label][f'{left}/{right}'].append(normalized)
                rounds+=n;cases+=1;draws+=draw;events.update(event)
                outcomes['win' if score==1 else 'loss' if score==0 else 'draw']+=1
        matrix[f'{left}/{right}']=round(sum(scores)/len(scores),6)
    totals={k:[] for k in FAMILIES}
    for key,score in matrix.items():
        a,b=key.split('/');totals[a].append(score);totals[b].append(1-score)
    overall={k:round(sum(v)/len(v),6) for k,v in totals.items()}
    return dict(cases=cases,rounds=rounds,round_limit_draws=draws,outcomes=dict(outcomes),matrix=matrix,overall=overall,
        splits={k:{p:round(sum(v)/len(v),6) for p,v in d.items()} for k,d in splits.items()},
        events=dict(events),elapsed_seconds=round(time.perf_counter()-started,3),
        methodology=dict(level=level,ranks=list(ranks),sizes=list(sizes),styles=list(styles),seeds=seeds,
            mirrored_sides=True,equal_stats=True,equal_equipment=True,real_damage_curve=True,round_limit=limit,
            seed_offset=seed_offset,authority_scale=authority_scale,monster_choice=monster_choice,effect_power=effect_power))


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path);p.add_argument('--seeds',type=int,default=8)
    p.add_argument('--level',type=int,default=50);p.add_argument('--ranks',type=int,nargs='+',default=[0,5,10])
    p.add_argument('--sizes',type=int,nargs='+',default=[1,2]);p.add_argument('--limit',type=int,default=48)
    p.add_argument('--seed-offset',type=int,default=0);p.add_argument('--authority-scale',type=float,default=1.)
    p.add_argument('--monster-choice',choices=('auto',*UNLOCKS),default='auto')
    p.add_argument('--effect-power',type=float,default=.12)
    p.add_argument('--output',type=Path,default=ROOT/'build/high-body-balance.json');p.add_argument('--export-config',type=Path)
    a=p.parse_args();cfg=json.loads(a.config.read_text(encoding='utf-8')) if a.config else configuration()
    if a.export_config:
        a.export_config.parent.mkdir(parents=True,exist_ok=True);a.export_config.write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding='utf-8')
    result=evaluate(cfg,seeds=a.seeds,ranks=a.ranks,sizes=a.sizes,level=a.level,limit=a.limit,
        seed_offset=a.seed_offset,authority_scale=a.authority_scale,monster_choice=a.monster_choice,effect_power=a.effect_power)
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('cases','rounds','round_limit_draws','matrix','overall','elapsed_seconds')},ensure_ascii=False))


if __name__=='__main__':main()
