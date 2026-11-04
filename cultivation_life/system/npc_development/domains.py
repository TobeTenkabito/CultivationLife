"""Explicit, inexpensive NPC domain growth on the original transcendence record."""
import copy
from ...content_registry import WORLD_SYSTEMS, REALMS
from ...npc_development_content import UPPER
from ...rules import opportunity_required
from types import SimpleNamespace
from .upper import require_upper, grow_ledger


def options(game,facts):
    if game.player.world=='celestial':
        return [dict(axis='domain:'+k,name=d['name']) for k,d in sorted(game.doctrine_state.get('definitions',{}).items()) if k.startswith('celestial:')]
    return [dict(axis='domain:'+d['id'],name=d['name']) for d in WORLD_SYSTEMS['upper_voisinages']['worlds'].get(game.player.world,{}).get('fields',[])]


def plan(game,target,facts,batches,method,axis='domain'):
    require_upper(game,target,facts)
    if target.kind=='puppet':raise ValueError('傀儡仍以能源驱动出手，不修习人物邻域')
    if facts['realm_index']<9:raise ValueError('邻域培养须达到九阶')
    if (facts.get('transcendence') or {}).get('conversion',0)<1:
        raise ValueError('须先完成元力转化，再培养邻域')
    if method=='family':raise ValueError('家族灌顶不用于邻域培养')
    selected=axis[7:] if axis.startswith('domain:') else None
    if selected and axis not in {r['axis'] for r in options(game,facts)}:raise ValueError('邻域不属于当前界面')
    result=copy.deepcopy(facts);grow_ledger(game,target,facts,result)
    state=result['transcendence'];realm=facts['realm_index'];world=game.player.world
    if world=='celestial':
        definitions=game.doctrine_state.get('definitions',{})
        if state.get('doctrine'):
            from ..doctrine.npc_progression import record as settle_doctrine
            settled=copy.deepcopy(result)
            settle_doctrine(game,settled)
            state['doctrine']=settled['transcendence']['doctrine']
        old=state.get('doctrine') or {}
        if not old and state.get('voisinage_ids'):raise ValueError('已有专属传承，请沿原传承培养')
        key=selected or old.get('active')
        if not key:
            if state.get('voisinage_ids'):raise ValueError('已有专属传承，请沿原传承培养')
            key=next(iter(sorted(k for k in definitions if k.startswith('celestial:'))),None)
        if key not in definitions:raise ValueError('当前没有可承接的仙界道统')
        definition=definitions[key];record=copy.deepcopy(old)
        progress=record.setdefault('progress',{}).setdefault(key,dict(level=0,experience=0))
        before=progress['level'];limit=max(s['level'] for s in definition['stages'] if s['realm']<=realm)
        if record.get('origin') not in (None,key):limit=min(limit,4)
        if before>=4 and record.get('origin') not in (None,key):raise ValueError('非本源道统不能继续提升')
        if method=='infuse':
            teacher=game.doctrine_state.get('player',{}).get('progress',{}).get(key,{})
            limit=min(limit,teacher.get('level',0))
        rounds=min(batches,max(0,limit-before));after=before+rounds
        progress.update(level=after,experience=0)
        manuals=record.setdefault('manuals',[])
        if definition['manuals'][0]['id'] not in manuals:manuals.append(definition['manuals'][0]['id'])
        record.update(active=key,manual_level=max(after,record.get('manual_level',0)),
            annotations=list(range(1,after+1)),at=game.player.age,world=world,mentor=game.player.name,
            cultivated=True)
        if after>=5:record['origin']=key
        state['doctrine']=record
        name=definition['name']
    else:
        cfg=WORLD_SYSTEMS['upper_voisinages'];fields=cfg['worlds'][world]['fields']
        record=state.setdefault('world_voisinages',{}).setdefault(world,dict(levels={}))
        key=selected or record.get('active') or fields[0]['id']
        definition=next((d for d in fields if d['id']==key),None)
        if not definition:raise ValueError('已有专属邻域，请沿原传承培养')
        before=record.setdefault('levels',{}).get(key,0)
        limit=max(i+1 for i,r in enumerate(cfg['realms']) if r<=realm)
        if method=='infuse':limit=min(limit,game.player.world_voisinages.get(world,{}).get('levels',{}).get(key,0))
        rounds=min(batches,max(0,limit-before));after=before+rounds
        record['levels'][key]=after;record['active']=key;name=definition['name']
    if not rounds:raise ValueError('已达当前修为或施教者的邻域上限')
    # 1.5% of the cheapest ordinary player step; NPC materials are separate.
    reference=opportunity_required(SimpleNamespace(realm_index=9,layer=1))*.01*rounds
    return dict(axis=axis,label='培养邻域',batches=batches,rounds=rounds,gain=rounds,
        before=f'{name} {before}阶',after=f'{name} {after}阶',result=result,domain_reference=reference)


def activate(game,target,axis):
    from .targets import require,write
    from .growth import facts as normalize
    require(game,target)
    facts=normalize(target.facts(game));require_upper(game,target,facts)
    if target.kind=='puppet' or not isinstance(axis,str) or axis not in {r['axis'] for r in options(game,facts)}:
        raise ValueError('当前没有可启用的所选邻域')
    state=copy.deepcopy(facts.get('transcendence') or {})
    if facts['realm_index']<9 or state.get('conversion',0)<1:raise ValueError('须达到九阶并完成元力转化')
    key=axis[7:];world=game.player.world
    record=state.get('doctrine',{}) if world=='celestial' else state.get('world_voisinages',{}).get(world,{})
    level=record.get('progress',{}).get(key,{}).get('level',0) if world=='celestial' else record.get('levels',{}).get(key,0)
    if not level:raise ValueError('须先培养所选传承')
    if record.get('active')==key:raise ValueError('已在使用所选传承')
    record['active']=key;write(target,{'transcendence':state})
    return '已启用所选邻域传承，保留原有本源与元力余额。'


def source(owner):
    from ..combat.actor_state import read
    from ..combat.contracts import CapabilitySource
    from ..world_voisinage_projection import project
    world=read(owner,'world');state=read(owner,'transcendence') or {}
    if UPPER.get(read(owner,'path'))!=world or read(owner,'realm_index',0)<9:return CapabilitySource()
    record=state.get('world_voisinages',{}).get(world,{})
    key=record.get('active');rank=record.get('levels',{}).get(key,0)
    cfg=WORLD_SYSTEMS['upper_voisinages']
    definition=next((d for d in cfg['worlds'].get(world,{}).get('fields',[]) if d['id']==key),None)
    if not definition or not rank:return CapabilitySource()
    limit=max(i+1 for i,r in enumerate(cfg['realms']) if r<=read(owner,'realm_index'))
    rank=min(rank,limit)
    return CapabilitySource((project(definition,rank),),{key:rank})
