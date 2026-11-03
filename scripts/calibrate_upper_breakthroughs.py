"""Read-only four-path major-trial sampling on production snapshots and rounds.

Controlled preparation fixtures, not a population estimate. No user save IO,
game balance overrides, fabricated combat descriptors or artificial game loss.
"""
import argparse
import copy
import csv
import hashlib
import json
import math
import random
import sys
from collections import Counter
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from cultivation_life.content_registry import CONTENT_DOCUMENTS,ITEM_CATALOG,WORLD_SYSTEMS,MONSTER_EVOLUTIONS
from cultivation_life.models import Player,GameState,Technique
from cultivation_life.rules import combat_power,expected_combat_power,max_hp,max_mp
from cultivation_life.cultivation_coordinates import rank_for
from cultivation_life.system.doctrine.provider import ensure
from cultivation_life.system import asura,monster_true_form,ghost_soul_form
from cultivation_life.system.immortal_aperture import ensure_aperture
from cultivation_life.engine.progression import immortal_trials,asura_trials,upper_trials
from cultivation_life.system.combat.trials import load_battle,run_batch

FAMILIES=('immortal','demonic','monster','ghost')
PROFILES=('entry','ready','peak','low_energy','zero_energy','no_field','no_body')
WORLDS=dict(zip(FAMILIES,('celestial','asura','nether','reincarnation')))
EVENTS={e['id']:e for doc in CONTENT_DOCUMENTS.values() if isinstance(doc,dict) for e in doc.get('events',[]) if isinstance(e,dict) and 'id' in e}
ADAPTER=SimpleNamespace(events_by_id=EVENTS,_instantiate_event=lambda event,game,rng:copy.deepcopy(event))
UPPER_DEPS=upper_trials.Dependencies(lambda:EVENTS,ADAPTER._instantiate_event,None,None,None)


@lru_cache(maxsize=8)
def world(family,seed):
    p=Player('高阶突破校准','supreme_metal',path='dao' if family=='immortal' else family,
             world=WORLDS[family],realm_index=9,layer=9,body_training=100,
             immortal_power_converted=True,immortal_conversion_stage=5)
    game=GameState(f'trial-audit:{family}:{seed}',seed,p,'','')
    ensure(game)
    if family=='demonic':asura.ensure(game)
    return game


def variants(family,catalog='base'):
    if family=='immortal':return list(range(25))
    if family=='demonic':return list(asura.ROUTE_NAMES)
    base=[r['id'] for r in WORLD_SYSTEMS['upper_voisinages']['worlds'][WORLDS[family]]['fields']]
    if catalog=='base':return base
    dynamic=(['form:'+key for key in monster_true_form.catalog()] if family=='monster' else
             ['soul:'+key for key in ghost_soul_form.catalog()['forms']])
    return dynamic if catalog=='dynamic' else base+dynamic


def configure_field(game,family,variant,value,stage):
    p=game.player
    if family=='immortal':
        row=list(game.doctrine_state['definitions'].values())[variant];key=row['id'];level=(4,6,8)[stage]
        record=game.doctrine_state['player']
        record['active']=key if value else None
        record['origin']=key if level>4 else None
        record['progress'][key]=dict(level=level,experience=0)
        record['annotations'][key]=list(range(1,level+1))
        record['voisinage_training'][key]=dict(rank=value,stability=5,incursion=5,authority=5)
        manual=Technique(**copy.deepcopy(row['manuals'][0]));manual.level=level
        p.known_techniques=[manual]
        return row['name']
    if family=='demonic':
        s=p.asura_cultivation
        s.update(conversion=5,route=variant if value else None,level=(4,7,9)[stage],
                 domain_rank=max(1,value),domain_power=5,domain_name='校准'+asura.ROUTE_NAMES[variant]+'魔域')
        # Same stage of eightfold preparation; no random branch/power additions.
        s.update(branch=None,branch_level=1,powers=[])
        return asura.ROUTE_NAMES[variant]
    record=p.world_voisinages.setdefault(p.world,{})
    if variant.startswith('form:'):
        species=variant.split(':',1)[1];p.monster_species_id=species
        p.monster_evolution_id=next(key for key,row in MONSTER_EVOLUTIONS.items()
            if row.get('species')==species and key.endswith('_NETHER_TRUE_'+str(stage+1)))
        template=monster_true_form.catalog()[species]
        monster_true_form.configure(p,'true_form_confirm',template['effects'][0])
        data=monster_true_form.stored(p);key=data['blueprint_id']
        if value>=5:
            record.setdefault('levels',{})[key]=4
            monster_true_form.configure(p,'true_form_secondary',next(e for e in template['effects'] if e!=data['primary']))
        if value>=9:
            record['levels'][key]=8;monster_true_form.configure(p,'true_form_tuning','balanced')
        if value>=13:data['finalized']=True
    elif variant.startswith('soul:'):
        cause,route=variant.split(':',1)[1].split('.')
        ghost_soul_form.confirm(game,cause,route);data=ghost_soul_form.stored(p);key=data['blueprint_id']
        template=ghost_soul_form.catalog()['forms'][cause+'.'+route]
        if value>=5:
            record.setdefault('levels',{})[key]=4
            ghost_soul_form.configure(p,'soul_form_secondary',ghost_soul_form.effect_key(template['secondary_choices'][0]))
        if value>=9:
            record['levels'][key]=8
            ghost_soul_form.configure(p,'soul_form_feature',template['feature_choices'][0])
        if value>=13:data['finalized']=True
    else:key=variant
    record.setdefault('levels',{})[key]=value
    record['active']=key if value else None
    if variant.startswith('form:'):assert monster_true_form.definition(p) is not None
    if variant.startswith('soul:'):assert ghost_soul_form.definition(p) is not None
    return variant


def prepare(family,realm,profile,variant,world_seed,*,mp_ratio=None,aperture_ratio=None):
    game=copy.deepcopy(world(family,world_seed));p=game.player;stage=realm-9
    # Bloodline evolution reaches the upper monster gate at layer one.
    p.realm_index=realm;p.layer=1 if family=='monster' else 9;p.divine_sense_rank=rank_for(realm,p.layer)
    body=(20,35,50)[stage];training=5;field=(4,8,12)[stage]
    if profile=='entry':body=(10,20,30)[stage];training=0;field=(1,5,9)[stage]
    if profile=='peak':body=50;training=10;field=(4,8,13)[stage]
    if profile=='no_field':field=0
    if profile=='no_body':body=0;training=0
    p.immortal_body=dict(level=body,divine_lights={k:training for k in ('kun','zhen','kan','li','qian')})
    if family=='demonic':
        p.immortal_body={'level':0}
        p.asura_cultivation.update(body_level=body,aggregates={k:training for k in ('se','shou','xiang','xing','shi')},
                                    veins={str(k):27 for k in range(9,realm+1)})
    elif family=='monster':
        p.immortal_body=dict(level=0,monster=dict(level=body,training={k:training for k in ('xuanfu','nigu','liezang','feixue','shenhun')},reaction='auto'))
        p.monster_species_id='serpent'
        p.monster_evolution_id=next(key for key,row in MONSTER_EVOLUTIONS.items()
            if row.get('species')=='serpent' and key.endswith('_NETHER_TRUE_'+str(stage+1)))
    elif family=='ghost':p.immortal_body=dict(level=body,ghost_training={k:training for k in ('wuxiang','zhaoye','yuhun','wangqing','yinguo')})
    p.immortal_veins={str(k):27 for k in range(9,realm+1)} if family=='immortal' else {}
    p.combat_plan=dict(manual=True,stance='press',investment=0)
    gear=copy.deepcopy(ITEM_CATALOG[f'econ_{p.world}_{realm}_artifact_attack']);gear.quantity=1;p.inventory=[gear]
    name=configure_field(game,family,variant,field,stage)
    # A declared controlled benchmark (same convention as the existing trial calibrator).
    # This is NOT a naturally grown account or an estimate of player population power.
    p.outer_king_fixed_combat_power=expected_combat_power(realm,p.layer)-combat_power(p)
    energy=.25 if profile=='low_energy' else 0 if profile=='zero_energy' else 1
    ordinary_energy=energy if mp_ratio is None else mp_ratio
    pool_energy=energy if aperture_ratio is None else aperture_ratio
    p.hp=max_hp(p);p.mp=max_mp(p)*ordinary_energy
    ensure_aperture(p);p.immortal_aperture['current']=p.immortal_aperture['capacity']*pool_energy
    if family=='immortal':
        kind=('human_decline','heaven_decline','three_corpses')[stage]
        immortal_trials.start(ADAPTER,game,kind);immortal_trials.initialize(game,game.active_trial)
    elif family=='demonic':asura_trials.start(ADAPTER,game,'asura_breakthrough')
    else:upper_trials.start(UPPER_DEPS,game,family+'_upper')
    trial=game.active_trial;own=load_battle(trial['snapshot']).units['player'].unit.capabilities
    return trial,dict(family=family,realm=realm,source_layer=p.layer,profile=profile,variant=str(variant),variant_name=name,
        world_seed=world_seed,body=body,training=training,field_rank=field,energy_ratio=pool_energy,
        capacity=own.capacity,usable_capacity=own.usable_capacity,current=own.current,
        artifact_tier=own.artifact_tier,benchmark_power=combat_power(p),gear=gear.id)


def sample(trial,seed,max_rounds=240):
    battle=load_battle(trial['snapshot']);state=copy.deepcopy(trial['battle_state']);rng=random.Random(seed)
    outcome='ongoing';resource_shortage=False
    while state['round']<max_rounds:
        outcome,rows=run_batch(battle,state,rng,batch_size=min(24,max_rounds-state['round']))
        resource_shortage |= any('不足' in event for row in rows for event in row['events'])
        if outcome!='ongoing':break
    own=battle.units['player'];enemies=[s for k,s in battle.units.items() if k!='player']
    assert all(math.isfinite(v) for s in battle.units.values() for v in (s.vitality,s.body,s.current))
    assert 0<=own.current<=battle._usable_energy(own)+1e-6
    if outcome=='victory' and state['mode'] in {'three_corpses','asura_breakthrough','upper_final'}:
        assert battle.enemy_killed(),'Incapacitation or escape counted as lethal trial victory'
    return dict(seed=seed,outcome=outcome,rounds=state['round'],body_remaining=own.body,
        state_remaining=own.vitality,energy_remaining=own.current,mp_remaining=state['mp_ratio'],
        resource_shortage=resource_shortage,enemies_alive=sum(s.body>0 and s.vitality>0 for s in enemies))


def summary(family,realm,profile,results):
    counts=Counter(r['outcome'] for r in results);n=len(results)
    resolved=counts['victory']+counts['defeat']
    return dict(family=family,realm=realm,profile=profile,samples=n,outcomes=dict(counts),
        success_rate=counts['victory']/n,unresolved_rate=counts['ongoing']/n,
        success_among_resolved=counts['victory']/resolved if resolved else None,
        median_rounds=sorted(r['rounds'] for r in results)[n//2],
        mean_winning_energy=sum(r['energy_remaining'] for r in results if r['outcome']=='victory')/max(1,counts['victory']))


def extend(records,max_rounds):
    """Re-evaluate censored cases only; reuse exact snapshot/state/RNG duplicates."""
    output=[];prepared={};cache={}
    for original in records:
        row=dict(original)
        if row['outcome']=='ongoing':
            family=row['family'];variant=int(row['variant']) if family=='immortal' else row['variant']
            key=(family,row['realm'],row['profile'],variant,row['world_seed'])
            if key not in prepared:
                trial,meta=prepare(*key)
                payload=json.dumps([trial['snapshot'],trial['battle_state']],sort_keys=True)
                prepared[key]=(trial,meta,hashlib.sha256(payload.encode()).hexdigest())
            trial,meta,digest=prepared[key];identity=(digest,row['seed'],max_rounds)
            if identity not in cache:cache[identity]=sample(trial,row['seed'],max_rounds)
            row.update(meta);row.update(cache[identity])
        output.append(row)
    return output


def run(family,*,samples=32,world_seeds=(930211,930212),catalog='base',profiles=PROFILES,realms=(9,10,11),max_rounds=240,seed_offset=6000):
    records=[];groups=[]
    for realm in realms:
        for profile in profiles:
            results=[]
            for w in world_seeds:
                for v in variants(family,catalog):
                    # no_field still varies the chosen tradition's ordinary/semantic loadout.
                    trial,meta=prepare(family,realm,profile,v,w)
                    for index in range(samples):
                        result=sample(trial,seed_offset+index,max_rounds)
                        row={**meta,**result};records.append(row);results.append(row)
            group=summary(family,realm,profile,results)
            groups.append(group);print(json.dumps(group,ensure_ascii=False),flush=True)
    return records,groups


def main():
    p=argparse.ArgumentParser();p.add_argument('--family',choices=FAMILIES,required=True)
    p.add_argument('--samples',type=int,default=32);p.add_argument('--world-seeds',type=int,nargs='+',default=[930211,930212])
    p.add_argument('--catalog',choices=('base','dynamic','all'),default='base')
    p.add_argument('--profiles',choices=PROFILES,nargs='+',default=list(PROFILES));p.add_argument('--max-rounds',type=int,default=240)
    p.add_argument('--realms',type=int,choices=(9,10,11),nargs='+',default=[9,10,11])
    p.add_argument('--seed-offset',type=int,default=6000);p.add_argument('--output',type=Path,default=ROOT/'build/upper-breakthrough-rates')
    p.add_argument('--extend-csv',type=Path,help='Only resample ongoing rows of an existing family/catalog CSV with a larger budget')
    a=p.parse_args()
    if a.samples<1 or a.max_rounds<5:p.error('samples must be positive and max-rounds at least five')
    a.output.mkdir(parents=True,exist_ok=True)
    if a.extend_csv:
        with a.extend_csv.open(encoding='utf-8-sig',newline='') as f:records=list(csv.DictReader(f))
        records=[r for r in records if int(r['realm']) in a.realms and r['profile'] in a.profiles]
        if not records:p.error('No CSV rows match the selected realms/profiles')
        integers=('realm','source_layer','world_seed','body','training','field_rank','artifact_tier','seed','rounds','enemies_alive')
        decimals=('energy_ratio','capacity','usable_capacity','current','benchmark_power','body_remaining','state_remaining','energy_remaining','mp_remaining')
        for row in records:
            if row['family']!=a.family:p.error('CSV family differs from --family')
            for k in integers:
                if k in row:row[k]=int(row[k])
            row.setdefault('source_layer',1 if a.family=='monster' else 9)
            for k in decimals:
                if k in row:row[k]=float(row[k]) if row[k] not in ('','None') else None
            row['resource_shortage']=row['resource_shortage']=='True'
        records=extend(records,a.max_rounds)
        groups=[summary(a.family,realm,profile,rows) for realm in a.realms for profile in a.profiles
                if (rows:=[r for r in records if r['realm']==realm and r['profile']==profile])]
        for group in groups:print(json.dumps(group,ensure_ascii=False),flush=True)
    else:
        records,groups=run(a.family,samples=a.samples,world_seeds=tuple(a.world_seeds),catalog=a.catalog,
            profiles=tuple(a.profiles),realms=tuple(a.realms),max_rounds=a.max_rounds,seed_offset=a.seed_offset)
    suffix=a.family+'-'+a.catalog
    with (a.output/(suffix+'.csv')).open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for row in records for k in row)));writer.writeheader();writer.writerows(records)
    (a.output/(suffix+'.json')).write_text(json.dumps(dict(family=a.family,catalog=a.catalog,
        samples_per_variant=a.samples,world_seeds=a.world_seeds,seed_offset=a.seed_offset,max_rounds=a.max_rounds,
        profiles=a.profiles,realms=a.realms,groups=groups,cases=len(records)),ensure_ascii=False,indent=2),encoding='utf8')


if __name__=='__main__':main()
